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
            "urgent_concerns": [],
            "urgent_concern_hits": [],
            "urgent_concern_missed": [],
            "concept_false_positives": [],
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
        "scorecard_kind": "full_rebuild",
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
        "protocol_comparability": {
            "status": "comparable",
            "comparable": True,
            "reasons": [],
        },
        "scorer_provenance": {"digest": "a" * 64},
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


def _write_protocol_identity(*paths: Path, manifest_sha: str = "b" * 64) -> None:
    for path in paths:
        eval_dir = path.parent if path.suffix == ".json" else path
        (eval_dir / "protocol-fingerprint.json").write_text(
            json.dumps(
                {
                    "protocol": {
                        "source": {
                            "available": True,
                            "commit": "c" * 40,
                            "dirty": False,
                            "worktree_status_sha256": "d" * 64,
                            "tracked_diff_sha256": "e" * 64,
                        },
                        "model": {
                            "id": "openai/gpt-5.4-mini",
                            "gateway_mode": "real",
                            "openclaw": {
                                "version": "2026.7.1-2",
                                "package_sha256": "f" * 64,
                                "cli_sha256": "1" * 64,
                            },
                        },
                        "prompts": [
                            {"path": "prompt.py", "sha256": "2" * 64}
                        ],
                        "skills": [
                            {"path": "SKILL.md", "sha256": "3" * 64}
                        ],
                        "clinical_rules": [
                            {"path": "rules.yaml", "sha256": "4" * 64}
                        ],
                        "manifest": {
                            "sha256": manifest_sha,
                            "selected_case_count": 1,
                            "cases": [
                                {
                                    "case": "case_1",
                                    "image": "case.png",
                                    "sha256": "5" * 64,
                                }
                            ],
                        },
                        "flags": {
                            "analysis_prompt_profile": "clinical",
                            "max_image_edge_px": 1568,
                            "multi_pass": False,
                            "timeout_sec": 90,
                        },
                    }
                }
            ),
            encoding="utf-8",
        )


def test_build_comparison_pairs_cases_and_records_improvement(tmp_path: Path) -> None:
    module = _load_compare_module()
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    baseline.mkdir()
    candidate.mkdir()
    _write_protocol_identity(baseline, candidate)
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
    assert report["safety_case_status_counts"] == {
        "improved": 0,
        "regressed": 0,
        "unchanged": 1,
    }
    assert report["candidate_cost"]["mean_openclaw_analyze_calls"] == 3.0
    assert report["cases"][0]["status"] == "improved"
    assert report["cases"][0]["safety_status"] == "unchanged"
    assert report["clinical_safety"]["abnormal_detection"] == {
        "pairs": 1,
        "baseline_hits": 1,
        "candidate_hits": 1,
        "baseline_rate": 1.0,
        "candidate_rate": 1.0,
        "rate_delta": 0.0,
        "paired_exact_test": {
            "improved": 0,
            "regressed": 0,
            "informative_pairs": 0,
            "two_sided_p": 1.0,
        },
    }


def test_resolve_eval_dir_accepts_experiment_root(tmp_path: Path) -> None:
    module = _load_compare_module()
    experiment = tmp_path / "experiment"
    eval_dir = experiment / "eval"
    eval_dir.mkdir(parents=True)
    (eval_dir / "scorecard.json").write_text(
        json.dumps(_scorecard(1.0, strict=True, latency_ms=1))
    )

    assert module.resolve_eval_dir(experiment) == eval_dir


def test_trace_cost_includes_openclaw_token_and_cost_usage(tmp_path: Path) -> None:
    module = _load_compare_module()
    experiment = tmp_path / "experiment"
    eval_dir = experiment / "eval"
    sessions = experiment / "openclaw-state" / "agents" / "main" / "sessions"
    eval_dir.mkdir(parents=True)
    sessions.mkdir(parents=True)
    (eval_dir / "multipass-trace.jsonl").write_text(
        json.dumps(
            {
                "case": "case_1",
                "openclaw_analyze_calls": 2,
                "zoom_passes": 1,
                "crop_calls": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (sessions / "turn.jsonl").write_text(
        json.dumps(
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "usage": {
                        "input": 1200,
                        "output": 300,
                        "cacheRead": 400,
                        "cacheWrite": 0,
                        "totalTokens": 1900,
                        "cost": {"total": 0.0125},
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (sessions / "turn.trajectory.jsonl").write_text(
        (sessions / "turn.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    cost = module._trace_cost(eval_dir)

    assert cost["usage_records"] == 1
    assert cost["total_input_tokens"] == 1200
    assert cost["total_output_tokens"] == 300
    assert cost["total_cache_read_tokens"] == 400
    assert cost["total_tokens"] == 1900
    assert cost["mean_tokens_per_traced_case"] == 1900.0
    assert cost["total_cost_usd"] == 0.0125


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
    _write_protocol_identity(baseline, candidate)

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

    _write_protocol_identity(baseline, candidate)
    report = module.build_comparison(baseline, candidate, allow_incomplete=True)

    assert report["paired_cases"] == 1
    assert report["baseline_health"]["error_count"] == 1
    assert report["candidate_only_cases"] == ["case_2"]


def test_build_comparison_rejects_mismatched_scorer_provenance(
    tmp_path: Path,
) -> None:
    module = _load_compare_module()
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    baseline.mkdir()
    candidate.mkdir()
    baseline_payload = _scorecard(0.60, strict=False, latency_ms=1)
    candidate_payload = _scorecard(0.80, strict=False, latency_ms=1)
    candidate_payload["scorer_provenance"]["digest"] = "c" * 64
    (baseline / "scorecard.json").write_text(json.dumps(baseline_payload))
    (candidate / "scorecard.json").write_text(json.dumps(candidate_payload))
    _write_protocol_identity(baseline, candidate)

    try:
        module.build_comparison(baseline, candidate)
    except ValueError as exc:
        assert "different scorer digests" in str(exc)
    else:
        raise AssertionError("expected scorer-provenance mismatch rejection")


def test_build_comparison_allows_incompatible_only_when_explicit(
    tmp_path: Path,
) -> None:
    module = _load_compare_module()
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    baseline.mkdir()
    candidate.mkdir()
    baseline_payload = _scorecard(0.60, strict=False, latency_ms=1)
    candidate_payload = _scorecard(0.80, strict=False, latency_ms=1)
    candidate_payload["scorer_provenance"]["digest"] = "c" * 64
    (baseline / "scorecard.json").write_text(json.dumps(baseline_payload))
    (candidate / "scorecard.json").write_text(json.dumps(candidate_payload))
    _write_protocol_identity(baseline, candidate)

    report = module.build_comparison(
        baseline,
        candidate,
        allow_incompatible=True,
    )

    assert report["protocol_compatible"] is False
    assert any(
        "different scorer digests" in issue
        for issue in report["protocol_compatibility_issues"]
    )


def test_build_comparison_rejects_different_model_runtime(tmp_path: Path) -> None:
    module = _load_compare_module()
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    baseline.mkdir()
    candidate.mkdir()
    (baseline / "scorecard.json").write_text(
        json.dumps(_scorecard(0.6, strict=False, latency_ms=1))
    )
    (candidate / "scorecard.json").write_text(
        json.dumps(_scorecard(0.8, strict=False, latency_ms=1))
    )
    _write_protocol_identity(baseline, candidate)
    fingerprint_path = candidate / "protocol-fingerprint.json"
    fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    fingerprint["protocol"]["model"]["id"] = "openai/a-different-model"
    fingerprint_path.write_text(json.dumps(fingerprint), encoding="utf-8")

    try:
        module.build_comparison(baseline, candidate)
    except ValueError as exc:
        assert "shared protocol invariants differ" in str(exc)
        assert "model_runtime" in str(exc)
    else:
        raise AssertionError("expected model-runtime mismatch rejection")


def test_build_comparison_allows_declared_arm_flag_differences(
    tmp_path: Path,
) -> None:
    module = _load_compare_module()
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    baseline.mkdir()
    candidate.mkdir()
    (baseline / "scorecard.json").write_text(
        json.dumps(_scorecard(0.6, strict=False, latency_ms=1))
    )
    (candidate / "scorecard.json").write_text(
        json.dumps(_scorecard(0.8, strict=False, latency_ms=1))
    )
    _write_protocol_identity(baseline, candidate)
    fingerprint_path = candidate / "protocol-fingerprint.json"
    fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    fingerprint["protocol"]["flags"].update(
        {
            "analysis_prompt_profile": "clinical",
            "multi_pass": True,
            "multi_pass_max_targets": 3,
            "rhythm_strip_pass": True,
        }
    )
    fingerprint_path.write_text(json.dumps(fingerprint), encoding="utf-8")

    report = module.build_comparison(baseline, candidate)

    assert report["protocol_compatible"] is True
    assert report["candidate_shared_invariants"]["arm"]["multi_pass"] is True


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


def test_clinical_safety_reports_normal_false_positives_and_urgent_regression(
    tmp_path: Path,
) -> None:
    module = _load_compare_module()
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline_payload = _scorecard(1.0, strict=True, latency_ms=1)
    candidate_payload = _scorecard(1.0, strict=True, latency_ms=1)

    baseline_case = baseline_payload["cases"][0]
    candidate_case = candidate_payload["cases"][0]
    for case in (baseline_case, candidate_case):
        case["expected_severity"] = "normal"
        case["actual_severity"] = "normal"
        case["severity_match"] = True
        case["severity_abnormal_match"] = True
    candidate_case["concept_false_positives"] = ["atrial fibrillation"]

    urgent_baseline = {
        **baseline_case,
        "case_label": "urgent",
        "expected_severity": "critical",
        "actual_severity": "critical",
        "severity_match": True,
        "severity_abnormal_match": True,
        "urgent_concerns": ["STEMI"],
        "urgent_concern_hits": ["STEMI"],
        "urgent_concern_missed": [],
    }
    urgent_candidate = {
        **urgent_baseline,
        "actual_severity": "warning",
        "severity_match": False,
        "urgent_concern_hits": [],
        "urgent_concern_missed": ["STEMI"],
    }
    baseline_payload["cases"].append(urgent_baseline)
    candidate_payload["cases"].append(urgent_candidate)
    for payload in (baseline_payload, candidate_payload):
        payload["total"] = 2
        payload["scored"] = 2

    baseline.write_text(json.dumps(baseline_payload), encoding="utf-8")
    candidate.write_text(json.dumps(candidate_payload), encoding="utf-8")
    _write_protocol_identity(baseline, candidate)
    report = module.build_comparison(baseline, candidate)
    safety = report["clinical_safety"]

    assert safety["normal_without_false_positive"]["baseline_false_positive_rate"] == 0.0
    assert safety["normal_without_false_positive"]["candidate_false_positive_rate"] == 1.0
    assert safety["critical_exact_recall"]["rate_delta"] == -1.0
    assert safety["urgent_concern_recall"]["baseline_hits"] == 1
    assert safety["urgent_concern_recall"]["candidate_hits"] == 0
    assert safety["urgent_concern_recall"]["paired_exact_test"]["two_sided_p"] == 1.0
    assert report["safety_case_status_counts"] == {
        "improved": 0,
        "regressed": 2,
        "unchanged": 0,
    }
    urgent_row = next(row for row in report["cases"] if row["case"] == "urgent")
    assert urgent_row["safety_status"] == "regressed"
    assert urgent_row["safety_hit_delta"] == -2
