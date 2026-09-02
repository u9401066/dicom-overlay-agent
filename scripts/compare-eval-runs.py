"""Compare two eval scorecards case-by-case.

The intended use is a paired baseline-vs-MultiPass comparison:

    uv run python scripts/compare-eval-runs.py \
      --baseline data/experiments/<single-pass>/eval \
      --candidate data/experiments/<multipass>/eval

Both arguments may point either at an eval directory containing
``scorecard.json`` or at an experiment root containing ``eval/scorecard.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Any

_PARTIAL_WEIGHTS: dict[str, float] = {
    "severity_abnormal": 0.30,
    "severity_exact": 0.20,
    "keyword_recall": 0.35,
    "negative_recall": 0.15,
}

_DEFAULT_BOOTSTRAP_ITERATIONS = 10_000
_DEFAULT_PERMUTATION_ITERATIONS = 10_000
_DEFAULT_RANDOM_SEED = 20_260_806
_EXACT_RANDOM_SIGN_MAX_PAIRS = 16
_INFERENCE_ALPHA = 0.05

# These are the only protocol fields allowed to vary between experimental
# arms. Everything else in the fingerprint is a shared invariant and must be
# byte-for-byte equivalent after canonicalization.
_ARM_VARIANT_FLAGS = frozenset(
    {
        "analysis_prompt_profile",
        "ecgfounder_checkpoint_sha256",
        "ecgfounder_model_revision",
        "ecgfounder_paired_case_count",
        "ecgfounder_preprocessing_revision",
        "ecgfounder_waveform_evidence",
        "guardrail_hooks",
        "local_signal_candidates",
        "multi_pass",
        "multi_pass_bbox_calibrator",
        "multi_pass_max_ekg_systematic_probes",
        "multi_pass_max_targets",
        "refinement_crop_source",
        "require_perfect",
        "rhythm_strip_pass",
        "single_pass_bbox_calibrator",
    }
)


def resolve_eval_dir(path: Path) -> Path:
    """Return the eval artifact dir for either an eval dir or experiment root."""
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".json":
        return path.parent
    if (path / "scorecard.json").exists():
        return path
    if (path / "eval" / "scorecard.json").exists():
        return path / "eval"
    raise FileNotFoundError(
        f"{path} is neither an eval dir nor an experiment root with eval/scorecard.json"
    )


def resolve_scorecard_path(path: Path) -> Path:
    """Return the scorecard JSON for a JSON file, eval dir, or experiment root."""
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".json":
        return path
    eval_dir = resolve_eval_dir(path)
    return eval_dir / "scorecard.json"


def build_comparison(
    baseline_path: Path,
    candidate_path: Path,
    *,
    min_delta: float = 0.05,
    allow_incomplete: bool = False,
    allow_incompatible: bool = False,
    bootstrap_iterations: int = _DEFAULT_BOOTSTRAP_ITERATIONS,
    permutation_iterations: int = _DEFAULT_PERMUTATION_ITERATIONS,
    random_seed: int = _DEFAULT_RANDOM_SEED,
) -> dict[str, Any]:
    """Build a paired comparison report from two eval runs."""
    if bootstrap_iterations <= 0:
        raise ValueError("bootstrap_iterations must be positive")
    if permutation_iterations <= 0:
        raise ValueError("permutation_iterations must be positive")
    baseline_dir = resolve_eval_dir(baseline_path)
    candidate_dir = resolve_eval_dir(candidate_path)
    baseline_scorecard_path = resolve_scorecard_path(baseline_path)
    candidate_scorecard_path = resolve_scorecard_path(candidate_path)
    baseline = _load_scorecard(baseline_scorecard_path)
    candidate = _load_scorecard(candidate_scorecard_path)
    baseline_health = _scorecard_health(baseline, baseline_dir, baseline_scorecard_path)
    candidate_health = _scorecard_health(
        candidate, candidate_dir, candidate_scorecard_path
    )
    if not allow_incomplete:
        _require_complete("baseline", baseline_health)
        _require_complete("candidate", candidate_health)
    baseline_cases = _cases_by_label(baseline, include_errors=allow_incomplete)
    candidate_cases = _cases_by_label(candidate, include_errors=allow_incomplete)
    labels = sorted(set(baseline_cases) & set(candidate_cases))
    for label in labels:
        if _reference_signature(baseline_cases[label]) != _reference_signature(
            candidate_cases[label]
        ):
            raise ValueError(
                f"case {label!r} uses different reference labels between runs; "
                "re-run both protocols against the same manifest"
            )

    baseline_manifest = _protocol_manifest_identity(baseline_dir)
    candidate_manifest = _protocol_manifest_identity(candidate_dir)
    baseline_invariants = _protocol_shared_invariants(baseline_dir)
    candidate_invariants = _protocol_shared_invariants(candidate_dir)
    compatibility_issues = _protocol_compatibility_issues(
        baseline_health=baseline_health,
        candidate_health=candidate_health,
        baseline_manifest=baseline_manifest,
        candidate_manifest=candidate_manifest,
        baseline_invariants=baseline_invariants,
        candidate_invariants=candidate_invariants,
    )
    if compatibility_issues and not allow_incompatible:
        raise ValueError(
            "baseline and candidate are not protocol-compatible: "
            + "; ".join(compatibility_issues)
            + ". Pass --allow-incompatible only for an explicitly exploratory report."
        )
    if not allow_incomplete and set(baseline_cases) != set(candidate_cases):
        raise ValueError("baseline and candidate do not contain the same case set")

    rows = [
        _compare_case(
            label,
            baseline_cases[label],
            candidate_cases[label],
            min_delta=min_delta,
        )
        for label in labels
    ]
    status_counts = {
        "improved": sum(1 for row in rows if row["status"] == "improved"),
        "regressed": sum(1 for row in rows if row["status"] == "regressed"),
        "unchanged": sum(1 for row in rows if row["status"] == "unchanged"),
    }
    safety_status_counts = {
        "improved": sum(1 for row in rows if row["safety_status"] == "improved"),
        "regressed": sum(1 for row in rows if row["safety_status"] == "regressed"),
        "unchanged": sum(1 for row in rows if row["safety_status"] == "unchanged"),
    }
    return {
        "baseline_eval_dir": str(baseline_dir),
        "candidate_eval_dir": str(candidate_dir),
        "paired_cases": len(rows),
        "allow_incomplete": allow_incomplete,
        "allow_incompatible": allow_incompatible,
        "protocol_compatible": not compatibility_issues,
        "protocol_compatibility_issues": compatibility_issues,
        "baseline_health": baseline_health,
        "candidate_health": candidate_health,
        "baseline_manifest": baseline_manifest,
        "candidate_manifest": candidate_manifest,
        "baseline_shared_invariants": baseline_invariants,
        "candidate_shared_invariants": candidate_invariants,
        "baseline_only_cases": sorted(set(baseline_cases) - set(candidate_cases)),
        "candidate_only_cases": sorted(set(candidate_cases) - set(baseline_cases)),
        "headline": _headline(baseline, candidate, rows),
        "paired_sign_test": _paired_sign_test(rows),
        "paired_partial_credit_inference": _paired_partial_credit_inference(
            rows,
            bootstrap_iterations=bootstrap_iterations,
            permutation_iterations=permutation_iterations,
            random_seed=random_seed,
        ),
        "paired_binary_inference": _paired_binary_inference(rows),
        "case_status_counts": status_counts,
        "safety_case_status_counts": safety_status_counts,
        "clinical_safety": _clinical_safety(rows),
        "baseline_cost": _trace_cost(baseline_dir),
        "candidate_cost": _trace_cost(candidate_dir),
        "baseline_bbox_audit": _bbox_audit_summary(baseline_dir),
        "candidate_bbox_audit": _bbox_audit_summary(candidate_dir),
        "cases": rows,
    }


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    """Persist JSON and Markdown summaries."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "comparison.md").write_text(
        _markdown_report(report),
        encoding="utf-8",
    )


def _load_scorecard(scorecard_path: Path) -> dict[str, Any]:
    return json.loads(scorecard_path.read_text(encoding="utf-8"))


def _cases_by_label(
    scorecard: dict[str, Any],
    *,
    include_errors: bool,
) -> dict[str, dict[str, Any]]:
    cases = {}
    for case in scorecard.get("cases", []):
        if include_errors and case.get("error"):
            continue
        cases[str(case["case_label"])] = case
    return cases


def _reference_signature(case: dict[str, Any]) -> tuple[Any, ...]:
    return (
        case.get("expected_severity"),
        case.get("label_status", "asserted"),
        tuple(sorted((*case.get("keyword_hits", []), *case.get("keyword_misses", [])))),
        tuple(
            sorted((*case.get("negative_hits", []), *case.get("negative_misses", [])))
        ),
        tuple(sorted(case.get("cant_miss", []))),
        tuple(sorted(case.get("urgent_concerns", []))),
        tuple(sorted(case.get("target_axes", []))),
    )


def _protocol_manifest_identity(eval_dir: Path) -> dict[str, Any] | None:
    payload = _load_protocol_fingerprint(eval_dir)
    if payload is None:
        return None
    protocol = payload.get("protocol")
    manifest = protocol.get("manifest") if isinstance(protocol, dict) else None
    if not isinstance(manifest, dict):
        return None
    cases = manifest.get("cases")
    case_sequence = (
        [
            {
                "case": str(item.get("case") or ""),
                "image": str(item.get("image") or ""),
                "sha256": str(item.get("sha256") or ""),
            }
            for item in cases
            if isinstance(item, dict)
        ]
        if isinstance(cases, list)
        else []
    )
    return {
        "sha256": str(manifest.get("sha256") or ""),
        "selected_case_count": _int(manifest.get("selected_case_count")),
        "case_sequence_sha256": _canonical_digest(case_sequence),
    }


def _load_protocol_fingerprint(eval_dir: Path) -> dict[str, Any] | None:
    path = eval_dir / "protocol-fingerprint.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _file_identity(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    identities = [
        {
            "path": str(item.get("path") or ""),
            "sha256": str(item.get("sha256") or ""),
        }
        for item in value
        if isinstance(item, dict)
    ]
    return sorted(identities, key=lambda item: item["path"])


def _protocol_shared_invariants(eval_dir: Path) -> dict[str, Any] | None:
    payload = _load_protocol_fingerprint(eval_dir)
    protocol = payload.get("protocol") if payload else None
    if not isinstance(protocol, dict):
        return None

    source = protocol.get("source")
    source = source if isinstance(source, dict) else {}
    model = protocol.get("model")
    model = model if isinstance(model, dict) else {}
    openclaw = model.get("openclaw")
    openclaw = openclaw if isinstance(openclaw, dict) else {}
    flags = protocol.get("flags")
    flags = flags if isinstance(flags, dict) else {}
    manifest = _protocol_manifest_identity(eval_dir)
    components = {
        "source": {
            "available": bool(source.get("available")),
            "commit": str(source.get("commit") or ""),
            "dirty": bool(source.get("dirty")),
            "scope": sorted(
                str(path) for path in source.get("scope", []) if isinstance(path, str)
            )
            if isinstance(source.get("scope"), list)
            else [],
            "worktree_status_sha256": str(source.get("worktree_status_sha256") or ""),
            "tracked_diff_sha256": str(source.get("tracked_diff_sha256") or ""),
            "worktree_content_sha256": str(
                source.get("worktree_content_sha256") or ""
            ),
            "worktree_file_count": _int(source.get("worktree_file_count")),
        },
        "model_runtime": {
            "id": str(model.get("id") or ""),
            "gateway_mode": str(model.get("gateway_mode") or ""),
            "openclaw_version": str(openclaw.get("version") or ""),
            "openclaw_package_sha256": str(openclaw.get("package_sha256") or ""),
            "openclaw_cli_sha256": str(openclaw.get("cli_sha256") or ""),
        },
        "prompt_sources": _file_identity(protocol.get("prompts")),
        "skills": _file_identity(protocol.get("skills")),
        "clinical_rules": _file_identity(protocol.get("clinical_rules")),
        "manifest": manifest,
        "shared_flags": {
            key: flags[key] for key in sorted(flags) if key not in _ARM_VARIANT_FLAGS
        },
    }
    arm = {key: flags[key] for key in sorted(flags) if key in _ARM_VARIANT_FLAGS}
    return {
        "digest": _canonical_digest(components),
        "components": components,
        "arm": arm,
    }


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scorecard_health(
    scorecard: dict[str, Any],
    eval_dir: Path,
    scorecard_path: Path,
) -> dict[str, Any]:
    raw_result_count = _raw_result_count(eval_dir)
    case_count = len(scorecard.get("cases", []))
    manifest_total = scorecard.get("manifest_total")
    total = _int(scorecard.get("total"))
    scored = _int(scorecard.get("scored"))
    error_count = _int(scorecard.get("error_count"))
    is_partial = bool(scorecard.get("is_partial"))
    if manifest_total is not None and _int(manifest_total) != total:
        is_partial = True
    incomplete_reasons: list[str] = []
    if error_count:
        incomplete_reasons.append(f"error_count={error_count}")
    if scored != total:
        incomplete_reasons.append(f"scored={scored} total={total}")
    if is_partial:
        incomplete_reasons.append("is_partial=true")
    if scorecard.get("scorecard_kind") != "full_rebuild":
        incomplete_reasons.append("scorecard_kind is not full_rebuild")
    if raw_result_count is not None and raw_result_count != case_count:
        incomplete_reasons.append(
            f"raw_result_count={raw_result_count} case_count={case_count}"
        )
    scorer = scorecard.get("scorer_provenance")
    scorer_digest = str(scorer.get("digest") or "") if isinstance(scorer, dict) else ""
    comparability = scorecard.get("protocol_comparability")
    comparability_status = (
        str(comparability.get("status") or "")
        if isinstance(comparability, dict)
        else ""
    )
    if comparability_status != "comparable":
        incomplete_reasons.append(
            f"protocol_comparability_status={comparability_status or 'missing'}"
        )
    if not scorer_digest:
        incomplete_reasons.append("scorer_digest is missing")
    return {
        "scorecard": str(scorecard_path),
        "scorecard_kind": str(scorecard.get("scorecard_kind") or ""),
        "protocol_digest": str(scorecard.get("protocol_digest") or ""),
        "source_protocol_digest": str(scorecard.get("source_protocol_digest") or ""),
        "protocol_comparability_status": comparability_status,
        "scorer_digest": scorer_digest,
        "total": total,
        "scored": scored,
        "error_count": error_count,
        "case_count": case_count,
        "raw_result_count": raw_result_count,
        "manifest_total": _int(manifest_total) if manifest_total is not None else None,
        "is_partial": is_partial,
        "complete": not incomplete_reasons,
        "incomplete_reasons": incomplete_reasons,
    }


def _protocol_compatibility_issues(
    *,
    baseline_health: dict[str, Any],
    candidate_health: dict[str, Any],
    baseline_manifest: dict[str, Any] | None,
    candidate_manifest: dict[str, Any] | None,
    baseline_invariants: dict[str, Any] | None,
    candidate_invariants: dict[str, Any] | None,
) -> list[str]:
    issues: list[str] = []
    if baseline_manifest is None or candidate_manifest is None:
        issues.append("one or both protocol fingerprints lack manifest identity")
    elif baseline_manifest != candidate_manifest:
        issues.append("protocol fingerprints use different manifests")

    if baseline_invariants is None or candidate_invariants is None:
        issues.append("one or both protocol fingerprints lack shared invariants")
    elif baseline_invariants.get("digest") != candidate_invariants.get("digest"):
        baseline_components = baseline_invariants.get("components")
        candidate_components = candidate_invariants.get("components")
        baseline_components = (
            baseline_components if isinstance(baseline_components, dict) else {}
        )
        candidate_components = (
            candidate_components if isinstance(candidate_components, dict) else {}
        )
        mismatches = sorted(
            key
            for key in set(baseline_components) | set(candidate_components)
            if baseline_components.get(key) != candidate_components.get(key)
        )
        issues.append(
            "shared protocol invariants differ"
            + (f" ({', '.join(mismatches)})" if mismatches else "")
        )

    baseline_scorer = str(baseline_health.get("scorer_digest") or "")
    candidate_scorer = str(candidate_health.get("scorer_digest") or "")
    if not baseline_scorer or not candidate_scorer:
        issues.append("one or both scorecards lack scorer provenance")
    elif baseline_scorer != candidate_scorer:
        issues.append("scorecards use different scorer digests")

    for label, health in (
        ("baseline", baseline_health),
        ("candidate", candidate_health),
    ):
        status = str(health.get("protocol_comparability_status") or "")
        if status != "comparable":
            issues.append(
                f"{label} protocol is {status or 'missing comparability status'}"
            )
    return issues


def _raw_result_count(eval_dir: Path) -> int | None:
    results_dir = eval_dir / "results"
    if not results_dir.exists():
        return None
    return len(list(results_dir.glob("*.json")))


def _require_complete(label: str, health: dict[str, Any]) -> None:
    if health["complete"]:
        return
    reasons = ", ".join(health["incomplete_reasons"])
    raise ValueError(
        f"{label} scorecard is incomplete ({reasons}). "
        "Rerun a complete baseline/candidate or pass --allow-incomplete for "
        "exploratory comparison of non-error shared cases only."
    )


def _compare_case(
    label: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    min_delta: float,
) -> dict[str, Any]:
    base_partial = _case_partial_credit(baseline)
    cand_partial = _case_partial_credit(candidate)
    base_strict = _case_strict_pass(baseline)
    cand_strict = _case_strict_pass(candidate)
    delta = round(cand_partial - base_partial, 3)
    if cand_strict and not base_strict:
        status = "improved"
    elif base_strict and not cand_strict:
        status = "regressed"
    elif delta >= min_delta:
        status = "improved"
    elif delta <= -min_delta:
        status = "regressed"
    else:
        status = "unchanged"
    row = {
        "case": label,
        "image": candidate.get("image") or baseline.get("image"),
        "modality": candidate.get("modality") or baseline.get("modality"),
        "reference_complete": bool(
            baseline.get(
                "reference_complete",
                baseline.get("label_status", "asserted") == "asserted",
            )
        ),
        "clinical_scorable": bool(baseline.get("clinical_scorable", True)),
        "status": status,
        "partial_credit_delta": delta,
        "baseline_partial_credit": base_partial,
        "candidate_partial_credit": cand_partial,
        "baseline_strict_pass": base_strict,
        "candidate_strict_pass": cand_strict,
        "baseline_expected_severity": baseline.get("expected_severity"),
        "baseline_actual_severity": baseline.get("actual_severity"),
        "candidate_actual_severity": candidate.get("actual_severity"),
        "baseline_severity_match": bool(baseline.get("severity_match")),
        "candidate_severity_match": bool(candidate.get("severity_match")),
        "baseline_severity_abnormal_match": bool(
            baseline.get("severity_abnormal_match")
        ),
        "candidate_severity_abnormal_match": bool(
            candidate.get("severity_abnormal_match")
        ),
        "baseline_concept_false_positives": list(
            baseline.get("concept_false_positives", [])
        ),
        "candidate_concept_false_positives": list(
            candidate.get("concept_false_positives", [])
        ),
        "urgent_concerns": list(
            candidate.get("urgent_concerns") or baseline.get("urgent_concerns") or []
        ),
        "baseline_urgent_concern_hits": list(baseline.get("urgent_concern_hits", [])),
        "candidate_urgent_concern_hits": list(candidate.get("urgent_concern_hits", [])),
        "baseline_keyword_recall": _float(baseline.get("keyword_recall")),
        "candidate_keyword_recall": _float(candidate.get("keyword_recall")),
        "baseline_negative_recall": _float(baseline.get("negative_recall")),
        "candidate_negative_recall": _float(candidate.get("negative_recall")),
        "baseline_latency_ms": _int(baseline.get("latency_ms")),
        "candidate_latency_ms": _int(candidate.get("latency_ms")),
        "target_axes": candidate.get("target_axes")
        or baseline.get("target_axes")
        or [],
        "baseline_misses": {
            "keywords": baseline.get("keyword_misses", []),
            "negatives": baseline.get("negative_misses", []),
            "cant_miss": baseline.get("cant_miss_missed", []),
            "urgent_concerns": baseline.get("urgent_concern_missed", []),
        },
        "candidate_misses": {
            "keywords": candidate.get("keyword_misses", []),
            "negatives": candidate.get("negative_misses", []),
            "cant_miss": candidate.get("cant_miss_missed", []),
            "urgent_concerns": candidate.get("urgent_concern_missed", []),
        },
    }
    baseline_safety, candidate_safety = _case_safety_hits(row)
    safety_delta = candidate_safety - baseline_safety
    row.update(
        {
            "safety_status": (
                "improved"
                if safety_delta > 0
                else "regressed"
                if safety_delta < 0
                else "unchanged"
            ),
            "safety_observations": _case_safety_observation_count(row),
            "baseline_safety_hits": baseline_safety,
            "candidate_safety_hits": candidate_safety,
            "safety_hit_delta": safety_delta,
        }
    )
    return row


def _case_safety_observations(row: dict[str, Any], prefix: str) -> list[bool]:
    expected = row["baseline_expected_severity"]
    abnormal_match = bool(row[f"{prefix}_severity_abnormal_match"])
    observations: list[bool] = []
    if row["reference_complete"] and expected in {"normal", "info"}:
        observations.extend(
            (
                abnormal_match,
                abnormal_match and not bool(row[f"{prefix}_concept_false_positives"]),
            )
        )
    elif row["reference_complete"] and expected in {"warning", "critical"}:
        observations.append(abnormal_match)
    if row["reference_complete"] and expected == "critical":
        observations.append(bool(row[f"{prefix}_severity_match"]))
    urgent_hits = set(row[f"{prefix}_urgent_concern_hits"])
    observations.extend(concern in urgent_hits for concern in row["urgent_concerns"])
    return observations


def _case_safety_hits(row: dict[str, Any]) -> tuple[int, int]:
    return (
        sum(_case_safety_observations(row, "baseline")),
        sum(_case_safety_observations(row, "candidate")),
    )


def _case_safety_observation_count(row: dict[str, Any]) -> int:
    return len(_case_safety_observations(row, "baseline"))


def _binary_pair_summary(pairs: list[tuple[bool, bool]]) -> dict[str, Any]:
    baseline_hits = sum(1 for baseline, _candidate in pairs if baseline)
    candidate_hits = sum(1 for _baseline, candidate in pairs if candidate)
    total = len(pairs)
    improved = sum(1 for baseline, candidate in pairs if candidate and not baseline)
    regressed = sum(1 for baseline, candidate in pairs if baseline and not candidate)
    return {
        "pairs": total,
        "baseline_hits": baseline_hits,
        "candidate_hits": candidate_hits,
        "baseline_rate": round(baseline_hits / total, 3) if total else None,
        "candidate_rate": round(candidate_hits / total, 3) if total else None,
        "rate_delta": (
            round((candidate_hits - baseline_hits) / total, 3) if total else None
        ),
        "paired_exact_test": _exact_sign_test(improved, regressed),
    }


def _clinical_safety(rows: list[dict[str, Any]]) -> dict[str, Any]:
    normal_rows = [
        row
        for row in rows
        if row["reference_complete"]
        if row["baseline_expected_severity"] in {"normal", "info"}
    ]
    abnormal_rows = [
        row
        for row in rows
        if row["reference_complete"]
        if row["baseline_expected_severity"] in {"warning", "critical"}
    ]
    critical_rows = [
        row
        for row in rows
        if row["reference_complete"] and row["baseline_expected_severity"] == "critical"
    ]

    normal_severity_pairs = [
        (
            row["baseline_severity_abnormal_match"],
            row["candidate_severity_abnormal_match"],
        )
        for row in normal_rows
    ]
    normal_clean_pairs = [
        (
            row["baseline_severity_abnormal_match"]
            and not row["baseline_concept_false_positives"],
            row["candidate_severity_abnormal_match"]
            and not row["candidate_concept_false_positives"],
        )
        for row in normal_rows
    ]
    abnormal_detection_pairs = [
        (
            row["baseline_severity_abnormal_match"],
            row["candidate_severity_abnormal_match"],
        )
        for row in abnormal_rows
    ]
    critical_exact_pairs = [
        (row["baseline_severity_match"], row["candidate_severity_match"])
        for row in critical_rows
    ]
    urgent_pairs: list[tuple[bool, bool]] = []
    for row in rows:
        baseline_hits = set(row["baseline_urgent_concern_hits"])
        candidate_hits = set(row["candidate_urgent_concern_hits"])
        urgent_pairs.extend(
            (concern in baseline_hits, concern in candidate_hits)
            for concern in row["urgent_concerns"]
        )

    normal_clean = _binary_pair_summary(normal_clean_pairs)
    normal_clean["baseline_false_positive_cases"] = (
        normal_clean["pairs"] - normal_clean["baseline_hits"]
    )
    normal_clean["candidate_false_positive_cases"] = (
        normal_clean["pairs"] - normal_clean["candidate_hits"]
    )
    normal_clean["baseline_false_positive_rate"] = (
        round(1.0 - normal_clean["baseline_rate"], 3)
        if normal_clean["baseline_rate"] is not None
        else None
    )
    normal_clean["candidate_false_positive_rate"] = (
        round(1.0 - normal_clean["candidate_rate"], 3)
        if normal_clean["candidate_rate"] is not None
        else None
    )
    return {
        "normal_severity_safe": _binary_pair_summary(normal_severity_pairs),
        "normal_without_false_positive": normal_clean,
        "abnormal_detection": _binary_pair_summary(abnormal_detection_pairs),
        "critical_exact_recall": _binary_pair_summary(critical_exact_pairs),
        "urgent_concern_recall": _binary_pair_summary(urgent_pairs),
    }


def _headline(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    paired_delta = (
        round(statistics.mean(row["partial_credit_delta"] for row in rows), 3)
        if rows
        else 0.0
    )
    headline = {
        "baseline_strict_pass_rate": _scorecard_strict_rate(baseline),
        "candidate_strict_pass_rate": _scorecard_strict_rate(candidate),
        "strict_pass_rate_delta": round(
            _scorecard_strict_rate(candidate) - _scorecard_strict_rate(baseline),
            3,
        ),
        "baseline_mean_partial_credit": _scorecard_partial_credit(baseline),
        "candidate_mean_partial_credit": _scorecard_partial_credit(candidate),
        "aggregate_partial_credit_delta": round(
            _scorecard_partial_credit(candidate) - _scorecard_partial_credit(baseline),
            3,
        ),
        "partial_credit_delta": paired_delta,
        "paired_mean_partial_credit_delta": paired_delta,
        "baseline_keyword_recall": _float(baseline.get("mean_keyword_recall")),
        "candidate_keyword_recall": _float(candidate.get("mean_keyword_recall")),
        "keyword_recall_delta": round(
            _float(candidate.get("mean_keyword_recall"))
            - _float(baseline.get("mean_keyword_recall")),
            3,
        ),
        "baseline_cant_miss_missed": list(baseline.get("cant_miss_missed", [])),
        "candidate_cant_miss_missed": list(candidate.get("cant_miss_missed", [])),
        "baseline_urgent_concern_missed": list(
            baseline.get("urgent_concern_missed", [])
        ),
        "candidate_urgent_concern_missed": list(
            candidate.get("urgent_concern_missed", [])
        ),
        "baseline_sla_rates": {
            stage: _scorecard_sla_rate(baseline, stage)
            for stage in (
                "initial_response",
                "first_crop_refinement",
                "total",
            )
        },
        "candidate_sla_rates": {
            stage: _scorecard_sla_rate(candidate, stage)
            for stage in (
                "initial_response",
                "first_crop_refinement",
                "total",
            )
        },
        "baseline_raw_json_clean_rate": _float(
            baseline.get("raw_json_clean_rate", 1.0)
        ),
        "candidate_raw_json_clean_rate": _float(
            candidate.get("raw_json_clean_rate", 1.0)
        ),
        "baseline_json_repair_total_count": _int(
            baseline.get("json_repair_total_count")
        ),
        "candidate_json_repair_total_count": _int(
            candidate.get("json_repair_total_count")
        ),
    }
    for field in (
        "diagnosis_exact_set_accuracy",
        "diagnosis_complete_recall_rate",
        "single_diagnosis_exact_set_accuracy",
        "multi_diagnosis_3_to_5_exact_set_accuracy",
        "multi_diagnosis_3_to_5_complete_recall_rate",
        "normal_control_specificity",
    ):
        baseline_value = _float(baseline.get(field))
        candidate_value = _float(candidate.get(field))
        headline[f"baseline_{field}"] = baseline_value
        headline[f"candidate_{field}"] = candidate_value
        headline[f"{field}_delta"] = round(candidate_value - baseline_value, 3)
    for field, getter in (
        ("normal_control_clean_read_rate", _scorecard_normal_clean_read_rate),
        (
            "normal_control_review_burden_rate",
            _scorecard_normal_review_burden_rate,
        ),
    ):
        baseline_value = getter(baseline)
        candidate_value = getter(candidate)
        headline[f"baseline_{field}"] = baseline_value
        headline[f"candidate_{field}"] = candidate_value
        headline[f"{field}_delta"] = round(candidate_value - baseline_value, 3)
    return headline


def _normal_control_cases(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        case
        for case in scorecard.get("cases", [])
        if isinstance(case, dict)
        and case.get("expected_severity") == "normal"
        and case.get("clinical_scorable", True) is not False
        and not case.get("error")
    ]


def _scorecard_normal_clean_read_rate(scorecard: dict[str, Any]) -> float:
    explicit = scorecard.get("normal_control_clean_read_rate")
    if explicit is not None:
        return _float(explicit)
    controls = _normal_control_cases(scorecard)
    if not controls:
        return 0.0
    clean = sum(
        1
        for case in controls
        if case.get("actual_severity") == "normal"
        and _int(case.get("finding_count")) == 0
        and not case.get("concept_false_positives", [])
    )
    return round(clean / len(controls), 3)


def _scorecard_normal_review_burden_rate(scorecard: dict[str, Any]) -> float:
    explicit = scorecard.get("normal_control_review_burden_rate")
    if explicit is not None:
        return _float(explicit)
    controls = _normal_control_cases(scorecard)
    if not controls:
        return 0.0
    return round(1.0 - _scorecard_normal_clean_read_rate(scorecard), 3)


def _paired_sign_test(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Exact two-sided sign test over improved vs regressed paired cases."""
    improved = sum(1 for row in rows if row["status"] == "improved")
    regressed = sum(1 for row in rows if row["status"] == "regressed")
    return _exact_sign_test(improved, regressed)


def _exact_sign_test(improved: int, regressed: int) -> dict[str, Any]:
    """Exact two-sided sign test for discordant paired binary outcomes."""
    n = improved + regressed
    if n == 0:
        p_value = 1.0
    else:
        smaller = min(improved, regressed)
        tail = sum(math.comb(n, k) for k in range(smaller + 1)) / (2**n)
        p_value = min(1.0, 2 * tail)
    return {
        "improved": improved,
        "regressed": regressed,
        "informative_pairs": n,
        "two_sided_p": p_value,
    }


def _paired_partial_credit_inference(
    rows: list[dict[str, Any]],
    *,
    bootstrap_iterations: int = _DEFAULT_BOOTSTRAP_ITERATIONS,
    permutation_iterations: int = _DEFAULT_PERMUTATION_ITERATIONS,
    random_seed: int = _DEFAULT_RANDOM_SEED,
) -> dict[str, Any]:
    """Quantify paired change in the weak-label partial-credit score."""
    deltas = [
        _float(row["candidate_partial_credit"]) - _float(row["baseline_partial_credit"])
        for row in rows
    ]
    mean_delta = statistics.mean(deltas) if deltas else None
    bootstrap = _paired_bootstrap_mean_ci(
        deltas,
        iterations=bootstrap_iterations,
        seed=random_seed,
    )
    permutation = _paired_random_sign_test(
        deltas,
        monte_carlo_iterations=permutation_iterations,
        seed=random_seed,
    )
    ci_positive = bootstrap["lower"] is not None and bootstrap["lower"] > 0.0
    permutation_significant = (
        permutation["two_sided_p"] is not None
        and permutation["two_sided_p"] < _INFERENCE_ALPHA
    )
    return {
        "metric": "weak_label_partial_credit",
        "metric_note": (
            "Partial credit is a weak-label composite score, not diagnostic accuracy."
        ),
        "paired_cases": len(deltas),
        "mean_delta": round(mean_delta, 6) if mean_delta is not None else None,
        "bootstrap_95_ci": bootstrap,
        "random_sign_permutation_test": permutation,
        "significant_improvement": {
            "alpha": _INFERENCE_ALPHA,
            "supported": bool(ci_positive and permutation_significant),
            "criterion": (
                "paired bootstrap 95% CI lower bound > 0 and two-sided paired "
                "random-sign permutation p < 0.05"
            ),
            "ci_excludes_zero_in_positive_direction": ci_positive,
            "permutation_p_below_alpha": permutation_significant,
        },
    }


def _paired_bootstrap_mean_ci(
    deltas: list[float],
    *,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": len(deltas) >= 2,
        "method": "paired_case_percentile_bootstrap",
        "confidence_level": 0.95,
        "paired_cases": len(deltas),
        "iterations": iterations,
        "seed": seed,
        "lower": None,
        "upper": None,
        "reason": None,
    }
    if len(deltas) < 2:
        result["reason"] = "requires_at_least_two_paired_cases"
        return result

    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(sum(rng.choices(deltas, k=n)) / n for _ in range(iterations))
    result["lower"] = round(_percentile(means, 0.025), 6)
    result["upper"] = round(_percentile(means, 0.975), 6)
    return result


def _paired_random_sign_test(
    deltas: list[float],
    *,
    monte_carlo_iterations: int,
    seed: int,
) -> dict[str, Any]:
    n = len(deltas)
    observed = abs(statistics.mean(deltas)) if deltas else None
    result: dict[str, Any] = {
        "available": n >= 2,
        "method": "not_computed",
        "paired_cases": n,
        "statistic": "absolute_mean_paired_delta",
        "observed_statistic": round(observed, 6) if observed is not None else None,
        "iterations": 0,
        "seed": seed,
        "two_sided_p": None,
        "reason": None,
    }
    if n < 2:
        result["reason"] = "requires_at_least_two_paired_cases"
        return result

    observed_sum = abs(sum(deltas))
    tolerance = 1e-12
    if n <= _EXACT_RANDOM_SIGN_MAX_PAIRS:
        assignments = 1 << n
        extreme = 0
        for mask in range(assignments):
            signed_sum = sum(
                value if mask & (1 << index) else -value
                for index, value in enumerate(deltas)
            )
            if abs(signed_sum) >= observed_sum - tolerance:
                extreme += 1
        result.update(
            {
                "method": "exact_random_sign_enumeration",
                "iterations": assignments,
                "seed": None,
                "two_sided_p": extreme / assignments,
            }
        )
        return result

    magnitude_counts: dict[float, int] = {}
    for value in deltas:
        magnitude = abs(value)
        if magnitude <= tolerance:
            continue
        magnitude_counts[magnitude] = magnitude_counts.get(magnitude, 0) + 1
    magnitude_groups = tuple(magnitude_counts.items())
    rng = random.Random(seed)
    extreme = 0
    for _ in range(monte_carlo_iterations):
        signed_sum = sum(
            (2 * rng.getrandbits(count).bit_count() - count) * magnitude
            for magnitude, count in magnitude_groups
        )
        if abs(signed_sum) >= observed_sum - tolerance:
            extreme += 1
    result.update(
        {
            "method": "monte_carlo_random_sign",
            "iterations": monte_carlo_iterations,
            "two_sided_p": (extreme + 1) / (monte_carlo_iterations + 1),
        }
    )
    return result


def _percentile(sorted_values: list[float], quantile: float) -> float:
    position = (len(sorted_values) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    fraction = position - lower_index
    return (
        sorted_values[lower_index] * (1.0 - fraction)
        + sorted_values[upper_index] * fraction
    )


def _paired_binary_inference(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible_normal = [
        row
        for row in rows
        if row["reference_complete"]
        and row["clinical_scorable"]
        and row["baseline_expected_severity"] in {"normal", "info"}
    ]
    normal_pairs = [
        (
            bool(row["baseline_severity_abnormal_match"])
            and not bool(row["baseline_concept_false_positives"]),
            bool(row["candidate_severity_abnormal_match"])
            and not bool(row["candidate_concept_false_positives"]),
        )
        for row in eligible_normal
    ]
    eligible_critical = [
        row
        for row in rows
        if row["reference_complete"]
        and row["clinical_scorable"]
        and row["baseline_expected_severity"] == "critical"
    ]
    critical_pairs = [
        (
            _critical_safety_correct(row, "baseline"),
            _critical_safety_correct(row, "candidate"),
        )
        for row in eligible_critical
    ]
    return {
        "normal_detection": {
            "population": ("reference-complete, clinically scorable normal/info cases"),
            "correctness_definition": (
                "non-abnormal severity classification with no concept false positive"
            ),
            **_mcnemar_exact_test(normal_pairs),
        },
        "critical_safety": {
            "population": ("reference-complete, clinically scorable critical cases"),
            "correctness_definition": (
                "exact critical severity with no missed cant-miss or urgent concern"
            ),
            **_mcnemar_exact_test(critical_pairs),
        },
    }


def _critical_safety_correct(row: dict[str, Any], prefix: str) -> bool:
    misses = row[f"{prefix}_misses"]
    return bool(row[f"{prefix}_severity_match"]) and not (
        misses["cant_miss"] or misses["urgent_concerns"]
    )


def _mcnemar_exact_test(pairs: list[tuple[bool, bool]]) -> dict[str, Any]:
    a = sum(1 for baseline, candidate in pairs if baseline and candidate)
    b = sum(1 for baseline, candidate in pairs if baseline and not candidate)
    c = sum(1 for baseline, candidate in pairs if not baseline and candidate)
    d = sum(1 for baseline, candidate in pairs if not baseline and not candidate)
    discordant = b + c
    result: dict[str, Any] = {
        "available": len(pairs) >= 2,
        "method": "mcnemar_exact_two_sided",
        "paired_cases": len(pairs),
        "a_both_correct": a,
        "b_baseline_correct_candidate_incorrect": b,
        "c_baseline_incorrect_candidate_correct": c,
        "d_both_incorrect": d,
        "discordant_pairs": discordant,
        "two_sided_p": None,
        "reason": None,
    }
    if len(pairs) < 2:
        result["reason"] = "requires_at_least_two_paired_cases"
        return result
    if discordant == 0:
        result["two_sided_p"] = 1.0
        result["reason"] = "no_discordant_pairs"
        return result
    smaller = min(b, c)
    tail = sum(math.comb(discordant, k) for k in range(smaller + 1)) / (2**discordant)
    result["two_sided_p"] = min(1.0, 2 * tail)
    return result


def _scorecard_strict_rate(scorecard: dict[str, Any]) -> float:
    if "strict_pass_rate" in scorecard:
        return _float(scorecard["strict_pass_rate"])
    cases = scorecard.get("cases", [])
    if not cases:
        return 0.0
    return round(sum(1 for case in cases if _case_strict_pass(case)) / len(cases), 3)


def _scorecard_partial_credit(scorecard: dict[str, Any]) -> float:
    if "mean_partial_credit" in scorecard:
        return _float(scorecard["mean_partial_credit"])
    cases = scorecard.get("cases", [])
    if not cases:
        return 0.0
    return round(sum(_case_partial_credit(case) for case in cases) / len(cases), 3)


def _scorecard_sla_rate(
    scorecard: dict[str, Any],
    stage: str,
) -> float | None:
    metrics = scorecard.get("sla_metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    stage_metrics = metrics.get(stage)
    stage_metrics = stage_metrics if isinstance(stage_metrics, dict) else {}
    value = stage_metrics.get("rate")
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _case_partial_credit(case: dict[str, Any]) -> float:
    if "partial_credit" in case:
        return _float(case["partial_credit"])
    breakdown = {
        "severity_abnormal": 1.0 if case.get("severity_abnormal_match") else 0.0,
        "severity_exact": 1.0 if case.get("severity_match") else 0.0,
        "keyword_recall": _float(case.get("keyword_recall", 1.0)),
        "negative_recall": _float(case.get("negative_recall", 1.0)),
    }
    return round(
        sum(breakdown[name] * weight for name, weight in _PARTIAL_WEIGHTS.items()),
        3,
    )


def _case_strict_pass(case: dict[str, Any]) -> bool:
    if "strict_pass" in case:
        return bool(case["strict_pass"])
    return (
        bool(case.get("severity_match"))
        and not case.get("keyword_misses")
        and not case.get("negative_misses")
        and bool(case.get("schema_ok"))
        and bool(case.get("bbox_in_bounds"))
        and not case.get("cant_miss_missed")
        and not case.get("error")
    )


def _trace_cost(eval_dir: Path) -> dict[str, Any]:
    path = eval_dir / "multipass-trace.jsonl"
    usage = _session_usage(eval_dir)
    if not path.exists():
        return {
            "traced_cases": 0,
            "mean_openclaw_analyze_calls": None,
            "mean_zoom_passes": None,
            "mean_crop_calls": None,
            "mean_tokens_per_traced_case": None,
            **usage,
        }
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    total_tokens = usage.get("total_tokens")
    return {
        "traced_cases": len(rows),
        "mean_openclaw_analyze_calls": _mean_field(rows, "openclaw_analyze_calls"),
        "mean_zoom_passes": _mean_field(rows, "zoom_passes"),
        "mean_crop_calls": _mean_field(rows, "crop_calls"),
        "mean_tokens_per_traced_case": (
            round(float(total_tokens) / len(rows), 3)
            if rows and isinstance(total_tokens, (int, float))
            else None
        ),
        **usage,
    }


def _session_usage(eval_dir: Path) -> dict[str, Any]:
    """Aggregate provider-reported usage from OpenClaw session messages."""

    sessions_dir = eval_dir.parent / "openclaw-state" / "agents" / "main" / "sessions"
    empty = {
        "usage_records": 0,
        "total_input_tokens": None,
        "total_output_tokens": None,
        "total_cache_read_tokens": None,
        "total_cache_write_tokens": None,
        "total_tokens": None,
        "total_cost_usd": None,
    }
    if not sessions_dir.is_dir():
        return empty

    totals = {
        "input": 0,
        "output": 0,
        "cacheRead": 0,
        "cacheWrite": 0,
        "totalTokens": 0,
    }
    total_cost = 0.0
    records = 0
    for path in sessions_dir.glob("*.jsonl"):
        if path.name.endswith(".trajectory.jsonl"):
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = row.get("message")
            usage = message.get("usage") if isinstance(message, dict) else None
            if not isinstance(usage, dict):
                continue
            records += 1
            for key in totals:
                totals[key] += _int(usage.get(key))
            cost = usage.get("cost")
            if isinstance(cost, dict):
                total_cost += _float(cost.get("total"))

    if not records:
        return empty
    return {
        "usage_records": records,
        "total_input_tokens": totals["input"],
        "total_output_tokens": totals["output"],
        "total_cache_read_tokens": totals["cacheRead"],
        "total_cache_write_tokens": totals["cacheWrite"],
        "total_tokens": totals["totalTokens"],
        "total_cost_usd": round(total_cost, 8),
    }


def _bbox_audit_summary(eval_dir: Path) -> dict[str, Any]:
    path = eval_dir / "review" / "bbox-audit.jsonl"
    if not path.exists():
        return {"bbox_count": 0, "low_signal_count": 0, "low_signal_rate": None}
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    low = sum(1 for row in rows if row.get("low_signal"))
    return {
        "bbox_count": len(rows),
        "low_signal_count": low,
        "low_signal_rate": round(low / len(rows), 3) if rows else 0.0,
    }


def _mean_field(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [_float(row.get(field)) for row in rows if row.get(field) is not None]
    return round(statistics.mean(values), 3) if values else None


def _format_optional_rate(value: object) -> str:
    return "n/a" if value is None else f"{_float(value):.1%}"


def _markdown_report(report: dict[str, Any]) -> str:
    headline = report["headline"]
    counts = report["case_status_counts"]
    safety_counts = report["safety_case_status_counts"]
    sign_test = report["paired_sign_test"]
    partial_inference = report["paired_partial_credit_inference"]
    binary_inference = report["paired_binary_inference"]
    safety = report["clinical_safety"]
    baseline_cost = report["baseline_cost"]
    candidate_cost = report["candidate_cost"]
    lines = [
        "# Eval Run Comparison",
        "",
        f"- Baseline: `{report['baseline_eval_dir']}`",
        f"- Candidate: `{report['candidate_eval_dir']}`",
        f"- Baseline scorecard: `{report['baseline_health']['scorecard']}` "
        f"({report['baseline_health']['scorecard_kind'] or 'unspecified'})",
        f"- Candidate scorecard: `{report['candidate_health']['scorecard']}` "
        f"({report['candidate_health']['scorecard_kind'] or 'unspecified'})",
        f"- Candidate protocol status: "
        f"{report['candidate_health']['protocol_comparability_status'] or 'unspecified'}",
        f"- Baseline / candidate scorer digest: "
        f"{report['baseline_health']['scorer_digest'] or 'legacy'} / "
        f"{report['candidate_health']['scorer_digest'] or 'legacy'}",
        f"- Paired cases: {report['paired_cases']}",
        f"- Partial-credit improved / regressed / unchanged: "
        f"{counts['improved']} / {counts['regressed']} / {counts['unchanged']}",
        f"- Safety improved / regressed / unchanged: "
        f"{safety_counts['improved']} / {safety_counts['regressed']} / "
        f"{safety_counts['unchanged']}",
        f"- Strict pass delta: {headline['strict_pass_rate_delta']:.1%}",
        f"- Mean partial-credit delta: {headline['partial_credit_delta']:.1%}",
        f"- Paired mean partial-credit delta: "
        f"{headline['paired_mean_partial_credit_delta']:.1%}",
        f"- Keyword recall delta: {headline['keyword_recall_delta']:.1%}",
        "- Candidate SLA (initial / first crop / total): "
        f"{_format_optional_rate(headline['candidate_sla_rates']['initial_response'])} / "
        f"{_format_optional_rate(headline['candidate_sla_rates']['first_crop_refinement'])} / "
        f"{_format_optional_rate(headline['candidate_sla_rates']['total'])}",
        "- Raw JSON clean rate (baseline / candidate): "
        f"{headline['baseline_raw_json_clean_rate']:.1%} / "
        f"{headline['candidate_raw_json_clean_rate']:.1%} "
        f"(repairs {headline['baseline_json_repair_total_count']} / "
        f"{headline['candidate_json_repair_total_count']})",
        f"- Diagnosis exact-set delta: "
        f"{headline['diagnosis_exact_set_accuracy_delta']:.1%}",
        f"- Diagnosis complete-recall delta: "
        f"{headline['diagnosis_complete_recall_rate_delta']:.1%}",
        f"- 3-5 diagnosis exact-set / complete-recall delta: "
        f"{headline['multi_diagnosis_3_to_5_exact_set_accuracy_delta']:.1%} / "
        f"{headline['multi_diagnosis_3_to_5_complete_recall_rate_delta']:.1%}",
        f"- Normal-control specificity delta: "
        f"{headline['normal_control_specificity_delta']:.1%}",
        f"- Paired sign-test p-value: {sign_test['two_sided_p']}",
        "",
        "## Paired Statistical Inference",
        "",
        _format_partial_credit_inference(partial_inference),
        _format_mcnemar("Normal detection", binary_inference["normal_detection"]),
        _format_mcnemar("Critical safety", binary_inference["critical_safety"]),
        "- Interpretation note: weak-label partial credit is a composite score, "
        "not diagnostic accuracy.",
        "",
        "## Runtime And Provider Usage",
        "",
        _format_usage("Baseline", baseline_cost),
        _format_usage("Candidate", candidate_cost),
        "",
        "## Safety And Clinical Detection",
        "",
        _format_binary_metric("Normal severity-safe", safety["normal_severity_safe"]),
        _format_binary_metric(
            "Normal without false positive",
            safety["normal_without_false_positive"],
        ),
        _format_binary_metric("Abnormal detection", safety["abnormal_detection"]),
        _format_binary_metric("Critical exact recall", safety["critical_exact_recall"]),
        _format_binary_metric("Urgent concern recall", safety["urgent_concern_recall"]),
        "",
        "## Top Improvements",
        "",
    ]
    sorted_rows = sorted(
        report["cases"], key=lambda row: row["partial_credit_delta"], reverse=True
    )
    for row in sorted_rows[:20]:
        lines.append(
            f"- `{row['case']}`: {row['partial_credit_delta']:+.1%} "
            f"({row['baseline_partial_credit']:.1%} -> "
            f"{row['candidate_partial_credit']:.1%}, {row['status']})"
        )
    lines.extend(["", "## Top Regressions", ""])
    for row in sorted_rows[-20:]:
        if row["partial_credit_delta"] >= 0:
            continue
        lines.append(
            f"- `{row['case']}`: {row['partial_credit_delta']:+.1%} "
            f"({row['baseline_partial_credit']:.1%} -> "
            f"{row['candidate_partial_credit']:.1%}, {row['status']})"
        )
    return "\n".join(lines) + "\n"


def _format_partial_credit_inference(inference: dict[str, Any]) -> str:
    bootstrap = inference["bootstrap_95_ci"]
    permutation = inference["random_sign_permutation_test"]
    supported = inference["significant_improvement"]["supported"]
    if not bootstrap["available"] or not permutation["available"]:
        return (
            "- Weak-label partial-credit inference: not available "
            f"(n={inference['paired_cases']}; requires at least two paired cases)"
        )
    seed = permutation["seed"] if permutation["seed"] is not None else "not used"
    return (
        f"- Weak-label partial-credit mean delta: {inference['mean_delta']:+.1%}; "
        f"paired bootstrap 95% CI [{bootstrap['lower']:+.1%}, "
        f"{bootstrap['upper']:+.1%}] "
        f"(iterations={bootstrap['iterations']}, seed={bootstrap['seed']}); "
        f"two-sided random-sign p={permutation['two_sided_p']} "
        f"(method={permutation['method']}, iterations={permutation['iterations']}, "
        f"seed={seed}); significant improvement supported={supported}"
    )


def _format_mcnemar(label: str, result: dict[str, Any]) -> str:
    b = result["b_baseline_correct_candidate_incorrect"]
    c = result["c_baseline_incorrect_candidate_correct"]
    context = (
        f"population={result['population']}; "
        f"correctness={result['correctness_definition']}"
    )
    if not result["available"]:
        return (
            f"- {label} McNemar exact: not available "
            f"(n={result['paired_cases']}, b={b}, c={c}; requires at least two "
            f"pairs); {context}"
        )
    return (
        f"- {label} McNemar exact: n={result['paired_cases']}, "
        f"b={b} (baseline correct/candidate incorrect), "
        f"c={c} (baseline incorrect/candidate correct), "
        f"two-sided p={result['two_sided_p']}; {context}"
    )


def _format_binary_metric(label: str, metric: dict[str, Any]) -> str:
    total = metric["pairs"]
    if not total:
        return f"- {label}: not measured (0 paired observations)"
    return (
        f"- {label}: {metric['baseline_hits']}/{total} "
        f"({metric['baseline_rate']:.1%}) -> {metric['candidate_hits']}/{total} "
        f"({metric['candidate_rate']:.1%}); delta {metric['rate_delta']:+.1%}; "
        f"paired p={metric['paired_exact_test']['two_sided_p']}"
    )


def _format_usage(label: str, cost: dict[str, Any]) -> str:
    if not cost.get("usage_records"):
        return f"- {label}: provider usage not recorded"
    return (
        f"- {label}: {cost['total_tokens']} tokens "
        f"(input={cost['total_input_tokens']}, output={cost['total_output_tokens']}, "
        f"cache-read={cost['total_cache_read_tokens']}); "
        f"cost={cost['total_cost_usd']} USD; "
        f"mean/case={cost['mean_tokens_per_traced_case']}"
    )


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--min-delta", type=float, default=0.05)
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=_DEFAULT_BOOTSTRAP_ITERATIONS,
    )
    parser.add_argument(
        "--permutation-iterations",
        type=int,
        default=_DEFAULT_PERMUTATION_ITERATIONS,
    )
    parser.add_argument("--random-seed", type=int, default=_DEFAULT_RANDOM_SEED)
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help=(
            "Allow incomplete/error scorecards for exploratory comparison; "
            "error cases are excluded from the paired set."
        ),
    )
    parser.add_argument(
        "--allow-incompatible",
        action="store_true",
        help=(
            "Allow mismatched scorer provenance or non-comparable protocol "
            "fingerprints for an explicitly exploratory report."
        ),
    )
    args = parser.parse_args()

    try:
        report = build_comparison(
            args.baseline,
            args.candidate,
            min_delta=args.min_delta,
            allow_incomplete=args.allow_incomplete,
            allow_incompatible=args.allow_incompatible,
            bootstrap_iterations=args.bootstrap_iterations,
            permutation_iterations=args.permutation_iterations,
            random_seed=args.random_seed,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    candidate_dir = resolve_eval_dir(args.candidate)
    output_dir = args.output or (candidate_dir / "comparison")
    write_report(report, output_dir)
    headline = report["headline"]
    counts = report["case_status_counts"]
    safety_counts = report["safety_case_status_counts"]
    print(f"Paired cases: {report['paired_cases']}")
    print(
        "Partial-credit improved/regressed/unchanged: "
        f"{counts['improved']}/{counts['regressed']}/{counts['unchanged']}"
    )
    print(
        "Safety improved/regressed/unchanged: "
        f"{safety_counts['improved']}/{safety_counts['regressed']}/"
        f"{safety_counts['unchanged']}"
    )
    print(f"Strict pass delta: {headline['strict_pass_rate_delta']:.1%}")
    print(f"Partial-credit delta: {headline['partial_credit_delta']:.1%}")
    print(f"Paired sign-test p-value: {report['paired_sign_test']['two_sided_p']}")
    inference = report["paired_partial_credit_inference"]
    print(
        "Weak-label partial-credit significant improvement supported: "
        f"{inference['significant_improvement']['supported']}"
    )
    print(f"Output: {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
