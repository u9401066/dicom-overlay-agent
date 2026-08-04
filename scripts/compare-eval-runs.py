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
import json
import math
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
) -> dict[str, Any]:
    """Build a paired comparison report from two eval runs."""
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
    if (
        baseline_manifest is not None
        and candidate_manifest is not None
        and baseline_manifest != candidate_manifest
    ):
        raise ValueError(
            "baseline and candidate protocol fingerprints use different manifests"
        )

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
        "improved": sum(
            1 for row in rows if row["safety_status"] == "improved"
        ),
        "regressed": sum(
            1 for row in rows if row["safety_status"] == "regressed"
        ),
        "unchanged": sum(
            1 for row in rows if row["safety_status"] == "unchanged"
        ),
    }
    return {
        "baseline_eval_dir": str(baseline_dir),
        "candidate_eval_dir": str(candidate_dir),
        "paired_cases": len(rows),
        "allow_incomplete": allow_incomplete,
        "baseline_health": baseline_health,
        "candidate_health": candidate_health,
        "baseline_manifest": baseline_manifest,
        "candidate_manifest": candidate_manifest,
        "baseline_only_cases": sorted(set(baseline_cases) - set(candidate_cases)),
        "candidate_only_cases": sorted(set(candidate_cases) - set(baseline_cases)),
        "headline": _headline(baseline, candidate, rows),
        "paired_sign_test": _paired_sign_test(rows),
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
    path = eval_dir / "protocol-fingerprint.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    protocol = payload.get("protocol")
    manifest = protocol.get("manifest") if isinstance(protocol, dict) else None
    if not isinstance(manifest, dict):
        return None
    return {
        "sha256": str(manifest.get("sha256") or ""),
        "selected_case_count": _int(manifest.get("selected_case_count")),
    }


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
    if raw_result_count is not None and raw_result_count != case_count:
        incomplete_reasons.append(
            f"raw_result_count={raw_result_count} case_count={case_count}"
        )
    scorer = scorecard.get("scorer_provenance")
    scorer_digest = (
        str(scorer.get("digest") or "") if isinstance(scorer, dict) else ""
    )
    comparability = scorecard.get("protocol_comparability")
    comparability_status = (
        str(comparability.get("status") or "")
        if isinstance(comparability, dict)
        else ""
    )
    return {
        "scorecard": str(scorecard_path),
        "scorecard_kind": str(scorecard.get("scorecard_kind") or ""),
        "protocol_digest": str(scorecard.get("protocol_digest") or ""),
        "source_protocol_digest": str(
            scorecard.get("source_protocol_digest") or ""
        ),
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
        "baseline_urgent_concern_hits": list(
            baseline.get("urgent_concern_hits", [])
        ),
        "candidate_urgent_concern_hits": list(
            candidate.get("urgent_concern_hits", [])
        ),
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


def _case_safety_observations(
    row: dict[str, Any], prefix: str
) -> list[bool]:
    expected = row["baseline_expected_severity"]
    abnormal_match = bool(row[f"{prefix}_severity_abnormal_match"])
    observations: list[bool] = []
    if expected in {"normal", "info"}:
        observations.extend(
            (
                abnormal_match,
                abnormal_match
                and not bool(row[f"{prefix}_concept_false_positives"]),
            )
        )
    elif expected in {"warning", "critical"}:
        observations.append(abnormal_match)
    if expected == "critical":
        observations.append(bool(row[f"{prefix}_severity_match"]))
    urgent_hits = set(row[f"{prefix}_urgent_concern_hits"])
    observations.extend(
        concern in urgent_hits for concern in row["urgent_concerns"]
    )
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
        if row["baseline_expected_severity"] in {"normal", "info"}
    ]
    abnormal_rows = [
        row
        for row in rows
        if row["baseline_expected_severity"] in {"warning", "critical"}
    ]
    critical_rows = [
        row for row in rows if row["baseline_expected_severity"] == "critical"
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
    return {
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
    }


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
    if not path.exists():
        return {
            "traced_cases": 0,
            "mean_openclaw_analyze_calls": None,
            "mean_zoom_passes": None,
            "mean_crop_calls": None,
        }
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {
        "traced_cases": len(rows),
        "mean_openclaw_analyze_calls": _mean_field(rows, "openclaw_analyze_calls"),
        "mean_zoom_passes": _mean_field(rows, "zoom_passes"),
        "mean_crop_calls": _mean_field(rows, "crop_calls"),
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


def _markdown_report(report: dict[str, Any]) -> str:
    headline = report["headline"]
    counts = report["case_status_counts"]
    safety_counts = report["safety_case_status_counts"]
    sign_test = report["paired_sign_test"]
    safety = report["clinical_safety"]
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
        f"- Paired sign-test p-value: {sign_test['two_sided_p']}",
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
        "--allow-incomplete",
        action="store_true",
        help=(
            "Allow incomplete/error scorecards for exploratory comparison; "
            "error cases are excluded from the paired set."
        ),
    )
    args = parser.parse_args()

    try:
        report = build_comparison(
            args.baseline,
            args.candidate,
            min_delta=args.min_delta,
            allow_incomplete=args.allow_incomplete,
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
    print(f"Output: {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
