from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_compare_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "compare-eval-runs.py"
    spec = importlib.util.spec_from_file_location("compare_eval_runs_script", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scorecard(
    case_partial: float,
    *,
    strict: bool,
    latency_ms: int,
    errored_extra_case: bool = False,
) -> dict:
    cases = [
        {
            "case_label": "case_1",
            "image": "case.png",
            "modality": "EKG",
            "expected_severity": "warning",
            "actual_severity": "warning" if strict else "normal",
            "severity_match": strict,
            "severity_abnormal_match": True,
            "keyword_hits": [],
            "keyword_misses": [],
            "keyword_recall": case_partial,
            "negative_hits": [],
            "negative_misses": [],
            "negative_recall": 1.0,
            "schema_ok": True,
            "schema_issue": "",
            "bbox_in_bounds": True,
            "finding_count": 1,
            "latency_ms": latency_ms,
            "strict_pass": strict,
            "partial_credit": case_partial,
            "partial_credit_breakdown": {
                "severity_abnormal": 1.0,
                "severity_exact": 1.0 if strict else 0.0,
                "keyword_recall": case_partial,
                "negative_recall": 1.0,
            },
            "target_axes": ["st_segment"],
            "cant_miss": [],
            "cant_miss_caught": True,
            "cant_miss_missed": [],
        }
    ]
    if errored_extra_case:
        cases.append(
            {
                "case_label": "case_2",
                "image": "case2.png",
                "modality": "EKG",
                "expected_severity": "warning",
                "actual_severity": "(error)",
                "severity_match": False,
                "severity_abnormal_match": False,
                "keyword_hits": [],
                "keyword_misses": ["ischemia"],
                "keyword_recall": 0.0,
                "negative_hits": [],
                "negative_misses": [],
                "negative_recall": 0.0,
                "schema_ok": False,
                "schema_issue": "ConnectionError",
                "bbox_in_bounds": False,
                "finding_count": 0,
                "latency_ms": 0,
                "strict_pass": False,
                "partial_credit": 0.0,
                "partial_credit_breakdown": {},
                "target_axes": ["ischemia"],
                "cant_miss": [],
                "cant_miss_caught": True,
                "cant_miss_missed": [],
                "error": "ConnectionError: aborted",
            }
        )
    return {
        "gateway_mode": "real",
        "total": len(cases),
        "scored": 1,
        "error_count": 1 if errored_extra_case else 0,
        "severity_accuracy": 1.0 if strict else 0.0,
        "severity_abnormal_accuracy": 1.0,
        "mean_keyword_recall": case_partial,
        "mean_negative_recall": 1.0,
        "schema_pass_rate": 1.0,
        "bbox_in_bounds_rate": 1.0,
        "mean_latency_ms": latency_ms,
        "strict_pass_rate": 1.0 if strict else 0.0,
        "mean_partial_credit": case_partial,
        "partial_credit_breakdown": {
            "severity_abnormal": 1.0,
            "severity_exact": 1.0 if strict else 0.0,
            "keyword_recall": case_partial,
            "negative_recall": 1.0,
        },
        "cant_miss_total": 0,
        "cant_miss_caught_count": 0,
        "cant_miss_missed": [],
        "axis_coverage": {},
        "target_axis_performance": {},
        "cases": cases,
    }


def test_build_comparison_pairs_cases_and_records_improvement(tmp_path: Path) -> None:
    module = _load_compare_module()
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    baseline.mkdir()
    candidate.mkdir()
    (baseline / "scorecard.json").write_text(
        json.dumps(_scorecard(0.55, strict=False, latency_ms=1000)),
        encoding="utf-8",
    )
    (candidate / "scorecard.json").write_text(
        json.dumps(_scorecard(0.90, strict=True, latency_ms=2500)),
        encoding="utf-8",
    )
    (candidate / "multipass-trace.jsonl").write_text(
        json.dumps(
            {
                "case": "case_1",
                "openclaw_analyze_calls": 3,
                "zoom_passes": 2,
                "crop_calls": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.build_comparison(baseline, candidate, min_delta=0.05)

    assert report["paired_cases"] == 1
    assert report["headline"]["partial_credit_delta"] == 0.35
    assert report["headline"]["strict_pass_rate_delta"] == 1.0
    assert report["case_status_counts"] == {
        "improved": 1,
        "regressed": 0,
        "unchanged": 0,
    }
    assert report["candidate_cost"]["mean_openclaw_analyze_calls"] == 3.0
    assert report["cases"][0]["status"] == "improved"


def test_resolve_eval_dir_accepts_experiment_root(tmp_path: Path) -> None:
    module = _load_compare_module()
    experiment = tmp_path / "experiment"
    eval_dir = experiment / "eval"
    eval_dir.mkdir(parents=True)
    (eval_dir / "scorecard.json").write_text(
        json.dumps(_scorecard(1.0, strict=True, latency_ms=1))
    )

    assert module.resolve_eval_dir(experiment) == eval_dir


def test_build_comparison_accepts_explicit_scorecard_json_path(
    tmp_path: Path,
) -> None:
    module = _load_compare_module()
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps(_scorecard(0.60, strict=False, latency_ms=1)),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps(_scorecard(0.80, strict=False, latency_ms=1)),
        encoding="utf-8",
    )

    report = module.build_comparison(baseline, candidate, min_delta=0.05)

    assert report["paired_cases"] == 1
    assert report["headline"]["partial_credit_delta"] == 0.2


def test_build_comparison_rejects_incomplete_scorecards_by_default(
    tmp_path: Path,
) -> None:
    module = _load_compare_module()
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps(
            _scorecard(0.60, strict=False, latency_ms=1, errored_extra_case=True)
        ),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps(_scorecard(0.80, strict=False, latency_ms=1)),
        encoding="utf-8",
    )

    try:
        module.build_comparison(baseline, candidate)
    except ValueError as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("expected incomplete scorecard rejection")


def test_build_comparison_rejects_different_reference_labels(
    tmp_path: Path,
) -> None:
    module = _load_compare_module()
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline_payload = _scorecard(0.60, strict=False, latency_ms=1)
    candidate_payload = _scorecard(0.80, strict=False, latency_ms=1)
    candidate_payload["cases"][0]["expected_severity"] = "critical"
    baseline.write_text(json.dumps(baseline_payload), encoding="utf-8")
    candidate.write_text(json.dumps(candidate_payload), encoding="utf-8")

    try:
        module.build_comparison(baseline, candidate)
    except ValueError as exc:
        assert "different reference labels" in str(exc)
    else:
        raise AssertionError("expected reference-label mismatch rejection")


def test_build_comparison_allow_incomplete_filters_error_cases(
    tmp_path: Path,
) -> None:
    module = _load_compare_module()
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps(
            _scorecard(0.60, strict=False, latency_ms=1, errored_extra_case=True)
        ),
        encoding="utf-8",
    )
    candidate_payload = _scorecard(0.80, strict=False, latency_ms=1)
    candidate_payload["cases"].append(
        {
            **candidate_payload["cases"][0],
            "case_label": "case_2",
            "partial_credit": 1.0,
            "strict_pass": True,
        }
    )
    candidate.write_text(json.dumps(candidate_payload), encoding="utf-8")

    report = module.build_comparison(baseline, candidate, allow_incomplete=True)

    assert report["paired_cases"] == 1
    assert report["baseline_health"]["error_count"] == 1
    assert report["candidate_only_cases"] == ["case_2"]


def test_paired_sign_test_quantifies_improvement_signal() -> None:
    module = _load_compare_module()
    rows = [{"status": "improved"} for _ in range(5)]
    rows += [{"status": "unchanged"} for _ in range(2)]

    result = module._paired_sign_test(rows)

    assert result == {
        "improved": 5,
        "regressed": 0,
        "informative_pairs": 5,
        "two_sided_p": 0.0625,
    }
