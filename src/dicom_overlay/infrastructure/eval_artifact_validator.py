"""Verifier for large recognition-evaluation artifact sets.

The image harness has two layers:

* the small Gateway smoke verifier proves ``connect`` / ``chat.send`` image
  payload shape; and
* this verifier proves a large dataset run left complete, auditable artifacts.

It deliberately inspects files only. It does not call a model, read PHI, or
couple to OpenClaw internals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class EvalArtifactVerification:
    """CI-readable verification report for a large eval run."""

    ok: bool
    passed_checks: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "passed_checks": self.passed_checks,
                "failures": self.failures,
            },
            indent=2,
            ensure_ascii=False,
        )


def verify_eval_artifacts(
    *,
    eval_dir: Path,
    manifest_path: Path,
    min_cases: int,
    require_review: bool = True,
    require_perfect_mock: bool = True,
) -> EvalArtifactVerification:
    """Verify that an eval directory proves a complete large-image run.

    ``require_perfect_mock`` is intentionally scoped to mock/pipeline runs. Real
    model runs are expected to expose clinical misses in the scorecard, while
    the transport/schema/bbox artifact contract must still be complete.
    """
    failures: list[str] = []
    passed: list[str] = []

    manifest = _read_json(manifest_path, failures, label="manifest")
    scorecard_path = eval_dir / "scorecard.json"
    scorecard = _read_json(scorecard_path, failures, label="scorecard")

    manifest_count = _case_count(manifest)
    if manifest_count >= min_cases:
        passed.append("min_cases")
    else:
        failures.append(
            f"min_cases: manifest has {manifest_count}, expected at least {min_cases}"
        )

    if isinstance(scorecard, dict):
        _verify_scorecard(
            scorecard,
            min_cases=min_cases,
            require_perfect_mock=require_perfect_mock,
            failures=failures,
            passed=passed,
        )
        _verify_results(
            eval_dir / "results",
            min_cases=min_cases,
            result_count=_int_value(scorecard.get("result_count")),
            failures=failures,
            passed=passed,
        )
        _verify_multipass_trace(
            eval_dir / "multipass-trace.jsonl",
            failures=failures,
            passed=passed,
        )
        if require_review:
            _verify_review_artifacts(eval_dir / "review", min_cases, failures, passed)

    return EvalArtifactVerification(
        ok=not failures,
        passed_checks=passed,
        failures=failures,
    )


def _read_json(path: Path, failures: list[str], *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        failures.append(f"{label}: could not read {path}: {exc}")
        return None


def _case_count(manifest: Any) -> int:
    if not isinstance(manifest, dict):
        return 0
    cases = manifest.get("cases")
    return len(cases) if isinstance(cases, list) else 0


def _verify_scorecard(
    scorecard: dict[str, Any],
    *,
    min_cases: int,
    require_perfect_mock: bool,
    failures: list[str],
    passed: list[str],
) -> None:
    manifest_total = _int_value(scorecard.get("manifest_total"))
    result_count = _int_value(scorecard.get("result_count"))
    total = _int_value(scorecard.get("total"))
    scored = _int_value(scorecard.get("scored"))
    error_count = _int_value(scorecard.get("error_count"))

    if scorecard.get("is_partial"):
        failures.append("scorecard_complete: scorecard is partial")
    if manifest_total < min_cases:
        failures.append(
            f"scorecard_complete: manifest_total={manifest_total}, expected {min_cases}"
        )
    if result_count < min_cases:
        failures.append(
            f"scorecard_complete: result_count={result_count}, expected {min_cases}"
        )
    if total != result_count:
        failures.append(
            f"scorecard_complete: total={total} does not match result_count={result_count}"
        )
    if scored != result_count:
        failures.append(
            f"scorecard_complete: scored={scored} does not match result_count={result_count}"
        )
    if error_count:
        failures.append(f"scorecard_complete: error_count={error_count}")
    if not any(f.startswith("scorecard_complete") for f in failures):
        passed.append("scorecard_complete")

    if float(scorecard.get("schema_pass_rate", 0.0)) >= 1.0:
        passed.append("schema_gate")
    else:
        failures.append(
            f"schema_gate: schema_pass_rate={scorecard.get('schema_pass_rate')}"
        )

    if float(scorecard.get("bbox_in_bounds_rate", 0.0)) >= 1.0:
        passed.append("bbox_gate")
    else:
        failures.append(
            f"bbox_gate: bbox_in_bounds_rate={scorecard.get('bbox_in_bounds_rate')}"
        )

    misses = scorecard.get("cant_miss_missed", [])
    if isinstance(misses, list) and not misses:
        passed.append("cant_miss_gate")
    else:
        failures.append(f"cant_miss_gate: missed={misses}")

    if scorecard.get("gateway_mode") == "mock" and require_perfect_mock:
        if float(scorecard.get("strict_pass_rate", 0.0)) >= 1.0:
            passed.append("mock_perfect_gate")
        else:
            failures.append(
                f"mock_perfect_gate: strict_pass_rate={scorecard.get('strict_pass_rate')}"
            )


def _verify_results(
    results_dir: Path,
    *,
    min_cases: int,
    result_count: int,
    failures: list[str],
    passed: list[str],
) -> None:
    files = list(results_dir.glob("*.json")) if results_dir.exists() else []
    if len(files) < min_cases:
        failures.append(
            f"results_artifacts: {len(files)} result json files, expected {min_cases}"
        )
        return
    if len(files) != result_count:
        failures.append(
            f"results_artifacts: {len(files)} result json files, scorecard has {result_count}"
        )
        return
    missing_preflight: list[str] = []
    missing_signal_candidates: list[str] = []
    for path in files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            failures.append(f"results_artifacts: invalid JSON {path.name}")
            return
        quality = raw.get("local_image_quality") if isinstance(raw, dict) else None
        if not isinstance(quality, dict) or "low_signal" not in quality:
            missing_preflight.append(path.name)
            if len(missing_preflight) >= 5:
                break
        signal = (
            raw.get("local_signal_candidates") if isinstance(raw, dict) else None
        )
        if not isinstance(signal, dict) or "candidate_count" not in signal:
            missing_signal_candidates.append(path.name)
            if len(missing_signal_candidates) >= 5:
                break
    passed.append("results_artifacts")
    if missing_preflight:
        failures.append(
            "local_preflight_artifacts: missing local_image_quality in "
            + ", ".join(missing_preflight)
        )
        return
    passed.append("local_preflight_artifacts")
    if missing_signal_candidates:
        failures.append(
            "model_assist_artifacts: missing local_signal_candidates in "
            + ", ".join(missing_signal_candidates)
        )
        return
    passed.append("model_assist_artifacts")


def _verify_review_artifacts(
    review_dir: Path,
    min_cases: int,
    failures: list[str],
    passed: list[str],
) -> None:
    index_path = review_dir / "index.html"
    audit_path = review_dir / "bbox-audit.jsonl"
    if not index_path.exists():
        failures.append("review_artifacts: missing index.html")
        return
    if not audit_path.exists():
        failures.append("review_artifacts: missing bbox-audit.jsonl")
        return
    lines = [
        line
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(lines) < min_cases:
        failures.append(
            f"review_artifacts: bbox-audit has {len(lines)} rows, expected {min_cases}"
        )
        return
    reviewed_cases: set[str] = set()
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            failures.append("review_artifacts: bbox-audit contains invalid JSONL")
            return
        case = row.get("case") if isinstance(row, dict) else None
        if isinstance(case, str) and case:
            reviewed_cases.add(case)
    if len(reviewed_cases) < min_cases:
        failures.append(
            "review_artifacts: "
            f"{len(reviewed_cases)} unique reviewed cases, expected {min_cases}"
        )
        return
    passed.append("review_artifacts")


def _verify_multipass_trace(
    trace_path: Path,
    *,
    failures: list[str],
    passed: list[str],
) -> None:
    """Validate optional MultiPass trace rows when the artifact exists."""
    if not trace_path.exists():
        return
    lines = [line for line in trace_path.read_text(encoding="utf-8").splitlines() if line]
    for index, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            failures.append(
                f"multipass_trace_artifacts: invalid JSONL row {index}"
            )
            return
        if not isinstance(row, dict):
            failures.append(
                f"multipass_trace_artifacts: row {index} is not an object"
            )
            return
        case = row.get("case")
        if not isinstance(case, str) or not case:
            failures.append(
                f"multipass_trace_artifacts: row {index} missing case"
            )
            return
        count = row.get("local_candidate_count")
        regions = row.get("local_candidate_regions")
        if not isinstance(count, int):
            failures.append(
                f"multipass_trace_artifacts: row {index} missing local_candidate_count"
            )
            return
        if not isinstance(regions, list):
            failures.append(
                f"multipass_trace_artifacts: row {index} missing local_candidate_regions"
            )
            return
        if count != len(regions):
            failures.append(
                "multipass_trace_artifacts: "
                f"row {index} local_candidate_count={count} "
                f"but regions={len(regions)}"
            )
            return
        for region_index, region in enumerate(regions, start=1):
            if not _is_normalized_region(region):
                failures.append(
                    "multipass_trace_artifacts: "
                    f"row {index} region {region_index} is not a normalized bbox"
                )
                return
    passed.append("multipass_trace_artifacts")


def _is_normalized_region(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        x = float(value["x"])
        y = float(value["y"])
        w = float(value["w"])
        h = float(value["h"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        0.0 <= x <= 1.0
        and 0.0 <= y <= 1.0
        and 0.0 < w <= 1.0
        and 0.0 < h <= 1.0
        and x + w <= 1.0 + 1e-6
        and y + h <= 1.0 + 1e-6
    )


def _int_value(value: Any) -> int:
    return value if isinstance(value, int) else 0
