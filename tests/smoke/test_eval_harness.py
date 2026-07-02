"""Smoke tests for the recognition evaluation harness."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from dicom_overlay.domain.entities import (
    AnalysisResult,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.infrastructure.eval_harness import (
    CaseScore,
    EvalCase,
    EvalReport,
    _write_raw_result,
    run_evaluation,
    score_case,
)


def _case(
    tmp_path: Path,
    severity: Severity,
    keywords: tuple[str, ...],
    name: str = "x",
    *,
    negatives: tuple[str, ...] = (),
) -> EvalCase:
    img = tmp_path / f"{name}.png"
    img.write_bytes(b"\x89PNG\r\n")
    return EvalCase(
        image_path=img,
        modality=Modality.CXR,
        expected_severity=severity,
        expected_keywords=keywords,
        expected_negatives=negatives,
        label=name,
    )


def _result(severity: Severity, *, summary: str, bbox: RegionRect | None = None) -> AnalysisResult:
    findings = []
    if bbox is not None:
        findings.append(
            Finding(
                id="f1",
                regions=[],
                label="consolidation",
                detail="opacity right base",
                severity=severity,
                bboxes=[bbox],
            )
        )
    return AnalysisResult(
        modality=Modality.CXR,
        summary=summary,
        severity=severity,
        findings=findings,
        checklist={"x": ChecklistItem(value="ok", status=Severity.NORMAL)},
    )


def _complete_result(
    severity: Severity,
    *,
    summary: str,
    bbox: RegionRect | None = None,
) -> AnalysisResult:
    result = _result(severity, summary=summary, bbox=bbox)
    result.checklist = {
        key: ChecklistItem(value="normal", status=Severity.NORMAL)
        for key in (
            "airway",
            "lungs",
            "pleura",
            "cardiac_silhouette",
            "mediastinum",
            "hila",
            "diaphragm",
            "bones",
            "soft_tissue",
            "lines_tubes",
        )
    }
    return result


def test_score_case_exact_severity_and_keyword_recall(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.WARNING, ("consolidation", "opacity"))
    result = _complete_result(
        Severity.WARNING,
        summary="CXR: consolidation",
        bbox=RegionRect(x=0.5, y=0.5, w=0.2, h=0.2),
    )
    score = score_case(case, result, latency_ms=12)
    assert score.severity_match is True
    assert score.severity_abnormal_match is True
    assert score.keyword_recall == 1.0
    assert score.schema_ok is True
    assert score.bbox_in_bounds is True
    assert score.partial_credit == 1.0
    assert score.strict_pass is True


def test_keyword_recall_does_not_count_negated_positive(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.WARNING, ("ischemia",))
    result = _complete_result(
        Severity.WARNING,
        summary="No ischemia identified.",
        bbox=RegionRect(x=0.5, y=0.5, w=0.2, h=0.2),
    )

    score = score_case(case, result, latency_ms=12)

    assert score.keyword_hits == []
    assert score.keyword_misses == ["ischemia"]
    assert score.keyword_recall == 0.0
    assert score.strict_pass is False


def test_score_case_marks_incomplete_schema_as_not_ok(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.WARNING, ("consolidation",))
    result = _result(
        Severity.WARNING,
        summary="CXR: consolidation",
        bbox=RegionRect(x=0.5, y=0.5, w=0.2, h=0.2),
    )

    score = score_case(case, result, latency_ms=12)

    assert score.schema_ok is False
    assert "Checklist missing keys" in score.schema_issue
    assert score.strict_pass is False


def test_score_case_records_partial_credit_for_near_miss(tmp_path: Path) -> None:
    case = _case(
        tmp_path,
        Severity.CRITICAL,
        ("stemi", "anterior"),
        negatives=("no effusion",),
    )
    result = _result(
        Severity.WARNING,
        summary="Anterior STEMI pattern. No effusion.",
        bbox=RegionRect(x=0.5, y=0.5, w=0.2, h=0.2),
    )

    score = score_case(case, result, latency_ms=12)

    assert score.severity_match is False
    assert score.severity_abnormal_match is True
    assert score.keyword_recall == 1.0
    assert score.negative_recall == 1.0
    assert score.partial_credit_breakdown == {
        "severity_abnormal": 1.0,
        "severity_exact": 0.0,
        "keyword_recall": 1.0,
        "negative_recall": 1.0,
    }
    assert score.partial_credit == 0.8
    assert score.strict_pass is False


def test_partial_credit_does_not_award_empty_negative_recall(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, Severity.CRITICAL, ("stemi",))
    result = _result(Severity.NORMAL, summary="Normal ECG.")

    score = score_case(case, result, latency_ms=12)

    assert score.negative_recall == 1.0
    assert score.partial_credit_breakdown == {
        "severity_abnormal": 0.0,
        "severity_exact": 0.0,
        "keyword_recall": 0.0,
    }
    assert score.partial_credit == 0.0


def test_partial_credit_is_capped_when_cant_miss_is_missed(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="stemi",
        cant_miss=("STEMI",),
    )
    result = _result_with_checklist(
        Severity.WARNING,
        summary="Anterior infarction pattern, urgent abnormal ECG.",
        checklist={},
    )

    score = score_case(case, result, latency_ms=12)

    assert score.cant_miss_missed == ["STEMI"]
    assert score.partial_credit == 0.4


def test_write_raw_result_includes_local_case_metadata(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.NORMAL, (), name="case_meta")
    result = _complete_result(
        Severity.NORMAL,
        summary="No acute finding.",
    )
    score = score_case(case, result, latency_ms=10)

    _write_raw_result(
        tmp_path,
        result,
        score,
        case_metadata={"local_image_quality": {"low_signal": False}},
    )

    raw = json.loads((tmp_path / "case_meta.json").read_text(encoding="utf-8"))
    assert raw["local_image_quality"] == {"low_signal": False}


def test_keyword_recall_accepts_no_acute_alias(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.NORMAL, ("no acute",))
    result = _result(
        Severity.NORMAL,
        summary="Clear lungs without focal air-space opacity or acute process.",
    )
    score = score_case(case, result, latency_ms=0)
    assert score.keyword_misses == []


def test_keyword_recall_accepts_stemi_for_infarction(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.CRITICAL, ("infarction",))
    result = _result(
        Severity.CRITICAL,
        summary="Acute anterior STEMI pattern with LAD territory occlusion.",
    )
    score = score_case(case, result, latency_ms=0)
    assert score.keyword_misses == []


def test_keyword_recall_uses_checklist_values(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.WARNING, ("t wave changes",))
    result = _result(Severity.WARNING, summary="Nonspecific ECG abnormality.")
    result.checklist["t_wave"] = ChecklistItem(value="inverted", status=Severity.INFO)
    score = score_case(case, result, latency_ms=0)
    assert score.keyword_hits == ["t wave changes"]
    assert score.keyword_misses == []


def test_keyword_recall_uses_abnormal_checklist_axis(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.WARNING, ("ischemia",))
    result = _result(Severity.WARNING, summary="Downsloping ST depression.")
    result.checklist["ischemia"] = ChecklistItem(
        value="st_depression",
        status=Severity.WARNING,
    )
    score = score_case(case, result, latency_ms=0)
    assert score.keyword_hits == ["ischemia"]
    assert score.keyword_misses == []


def test_score_case_detects_out_of_bounds_bbox(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.WARNING, ())
    result = _result(
        Severity.WARNING,
        summary="bad bbox",
        bbox=RegionRect(x=0.9, y=0.5, w=0.5, h=0.2),  # x+w = 1.4 > 1
    )
    score = score_case(case, result, latency_ms=0)
    assert score.bbox_in_bounds is False


def test_score_case_abnormal_group_mismatch(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.CRITICAL, ())
    result = _result(Severity.NORMAL, summary="all clear")
    score = score_case(case, result, latency_ms=0)
    assert score.severity_match is False
    assert score.severity_abnormal_match is False


def test_eval_report_perfect_gate_reports_any_miss() -> None:
    score = CaseScore(
        case_label="ekg_stemi",
        image="ekg.png",
        modality="EKG",
        expected_severity="critical",
        actual_severity="warning",
        severity_match=False,
        severity_abnormal_match=True,
        keyword_hits=["stemi"],
        keyword_misses=["anterior"],
        keyword_recall=0.5,
        negative_hits=[],
        negative_misses=[],
        negative_recall=1.0,
        schema_ok=True,
        schema_issue="",
        bbox_in_bounds=True,
        finding_count=1,
        latency_ms=10,
        cant_miss=["STEMI"],
        cant_miss_caught=True,
    )
    report = EvalReport(
        gateway_mode="real",
        total=1,
        scored=1,
        error_count=0,
        severity_accuracy=0.0,
        severity_abnormal_accuracy=1.0,
        mean_keyword_recall=0.5,
        mean_negative_recall=1.0,
        schema_pass_rate=1.0,
        bbox_in_bounds_rate=1.0,
        mean_latency_ms=10.0,
        cases=[score],
    )

    assert report.is_perfect is False
    assert report.perfect_failures() == [
        "ekg_stemi: severity expected critical got warning",
        "ekg_stemi: missing keywords anterior",
    ]


def test_eval_report_perfect_gate_accepts_info_for_normal() -> None:
    score = CaseScore(
        case_label="ekg_normal",
        image="ekg.png",
        modality="EKG",
        expected_severity="normal",
        actual_severity="info",
        severity_match=False,
        severity_abnormal_match=True,
        keyword_hits=[],
        keyword_misses=[],
        keyword_recall=1.0,
        negative_hits=[],
        negative_misses=[],
        negative_recall=1.0,
        schema_ok=True,
        schema_issue="",
        bbox_in_bounds=True,
        finding_count=1,
        latency_ms=10,
    )
    report = EvalReport(
        gateway_mode="real",
        total=1,
        scored=1,
        error_count=0,
        severity_accuracy=0.0,
        severity_abnormal_accuracy=1.0,
        mean_keyword_recall=1.0,
        mean_negative_recall=1.0,
        schema_pass_rate=1.0,
        bbox_in_bounds_rate=1.0,
        mean_latency_ms=10.0,
        cases=[score],
    )

    assert report.is_perfect is True


_EKG_CHECKLIST_KEYS = (
    "heart_rate",
    "rhythm",
    "regularity",
    "axis",
    "p_wave",
    "pr_interval",
    "qrs_duration",
    "qrs_morphology",
    "st_segment",
    "t_wave",
    "qtc_interval",
    "chamber_enlargement",
    "conduction",
    "av_block",
    "stemi_pattern",
    "ischemia",
)


def _result_with_checklist(
    severity: Severity, *, summary: str, checklist: dict[str, ChecklistItem]
) -> AnalysisResult:
    full_checklist = {
        key: ChecklistItem(value="normal", status=Severity.NORMAL)
        for key in _EKG_CHECKLIST_KEYS
    }
    full_checklist.update(checklist)
    return AnalysisResult(
        modality=Modality.EKG,
        summary=summary,
        severity=severity,
        findings=[],
        checklist=full_checklist,
    )


def test_pertinent_negative_recall_from_free_text(tmp_path: Path) -> None:
    # A normal CXR read should explicitly rule out the dangerous conditions.
    case = _case(
        tmp_path,
        Severity.NORMAL,
        (),
        negatives=("no pneumothorax", "no effusion"),
    )
    result = _result(
        Severity.NORMAL,
        summary="Clear lungs. No pneumothorax, no effusion.",
    )
    score = score_case(case, result, latency_ms=5)
    assert score.negative_recall == 1.0
    assert set(score.negative_hits) == {"no pneumothorax", "no effusion"}
    assert score.negative_misses == []


def test_pertinent_negative_found_in_checklist(tmp_path: Path) -> None:
    # The EKG pertinent negative "stemi absent" lives in the checklist, not the
    # free-text findings -- the harness must look there too.
    case = EvalCase(
        image_path=tmp_path / "ekg.png",
        modality=Modality.EKG,
        expected_severity=Severity.NORMAL,
        expected_negatives=("stemi_pattern", "absent"),
        label="ekg_normal",
    )
    (tmp_path / "ekg.png").write_bytes(b"\x89PNG\r\n")
    result = _result_with_checklist(
        Severity.NORMAL,
        summary="Normal sinus rhythm.",
        checklist={
            "stemi_pattern": ChecklistItem(value="absent", status=Severity.NORMAL),
        },
    )
    score = score_case(case, result, latency_ms=5)
    assert score.negative_recall == 1.0


def test_pertinent_negative_miss_is_penalized(tmp_path: Path) -> None:
    case = _case(
        tmp_path,
        Severity.NORMAL,
        (),
        negatives=("no pneumothorax", "no effusion"),
    )
    # Read only ruled out one of the two pertinent negatives.
    result = _result(Severity.NORMAL, summary="No pneumothorax.")
    score = score_case(case, result, latency_ms=5)
    assert score.negative_recall == 0.5
    assert score.negative_misses == ["no effusion"]


def test_pertinent_negative_hits_shared_no_clause(tmp_path: Path) -> None:
    case = _case(
        tmp_path,
        Severity.NORMAL,
        (),
        negatives=("no pneumothorax", "no effusion", "no consolidation"),
    )
    result = _result(
        Severity.NORMAL,
        summary=(
            "No focal air-space consolidation, pleural effusion, "
            "pneumothorax, or cardiomegaly is evident."
        ),
    )
    score = score_case(case, result, latency_ms=5)
    assert score.negative_recall == 1.0
    assert score.negative_misses == []


def test_no_negatives_defaults_to_full_recall(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.NORMAL, ())
    result = _result(Severity.NORMAL, summary="clear")
    score = score_case(case, result, latency_ms=0)
    assert score.negative_recall == 1.0


async def test_run_evaluation_writes_scorecard_and_aggregates(tmp_path: Path) -> None:
    cases = [
        _case(tmp_path, Severity.WARNING, ("consolidation",), name="abnormal"),
        _case(tmp_path, Severity.NORMAL, (), name="normal"),
    ]
    answers = {
        cases[0].image_path: _complete_result(
            Severity.WARNING,
            summary="consolidation seen",
            bbox=RegionRect(x=0.1, y=0.1, w=0.2, h=0.2),
        ),
        cases[1].image_path: _complete_result(Severity.NORMAL, summary="clear"),
    }

    async def analyze(case: EvalCase) -> AnalysisResult:
        return answers[case.image_path]

    out = tmp_path / "out"
    report = await run_evaluation(
        cases, analyze, output_dir=out, gateway_mode="mock"
    )

    assert report.total == 2
    assert report.scored == 2
    assert report.severity_accuracy == 1.0
    assert report.mean_negative_recall == 1.0
    assert report.strict_pass_rate == 1.0
    assert report.mean_partial_credit == 1.0
    assert report.partial_credit_breakdown["keyword_recall"] == 1.0
    scorecard = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["gateway_mode"] == "mock"
    assert "mean_negative_recall" in scorecard
    assert scorecard["mean_partial_credit"] == 1.0
    assert scorecard["strict_pass_rate"] == 1.0
    assert scorecard["manifest_total"] == 2
    assert scorecard["result_count"] == 2
    assert scorecard["is_partial"] is False
    assert len(scorecard["cases"]) == 2
    assert (out / "results").is_dir()
    partial = json.loads((out / "scorecard.partial.json").read_text(encoding="utf-8"))
    assert partial["manifest_total"] == 2
    assert partial["result_count"] == 2
    assert partial["is_partial"] is False


async def test_run_evaluation_fail_fast_on_consecutive_gateway_errors(
    tmp_path: Path,
) -> None:
    cases = [
        _case(tmp_path, Severity.WARNING, ("consolidation",), name=f"case_{i}")
        for i in range(6)
    ]

    async def analyze(case: EvalCase) -> AnalysisResult:
        raise ConnectionError("Not connected to OpenClaw Gateway")

    out = tmp_path / "out"
    report = await run_evaluation(
        cases,
        analyze,
        output_dir=out,
        gateway_mode="real",
        max_consecutive_infra_errors=3,
    )

    assert report.total == 3
    assert report.error_count == 3
    assert report.aborted_reason == "consecutive_infrastructure_errors"
    assert len(list((out / "results").glob("*.json"))) == 3
    scorecard = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["manifest_total"] == 6
    assert scorecard["result_count"] == 3
    assert scorecard["is_partial"] is True
    assert scorecard["aborted_reason"] == "consecutive_infrastructure_errors"


async def test_run_evaluation_aggregates_target_axis_performance(
    tmp_path: Path,
) -> None:
    cases = [
        _ekg_case(
            tmp_path,
            Severity.WARNING,
            name="st_change",
            target_axes=("st_segment", "ischemia"),
        ),
        _ekg_case(
            tmp_path,
            Severity.WARNING,
            name="rhythm",
            target_axes=("rhythm",),
        ),
    ]
    answers = {
        cases[0].image_path: _result_with_checklist(
            Severity.WARNING,
            summary="ST depression with ischemia.",
            checklist={},
        ),
        cases[1].image_path: _result_with_checklist(
            Severity.NORMAL,
            summary="normal sinus rhythm.",
            checklist={},
        ),
    }

    async def analyze(case: EvalCase) -> AnalysisResult:
        return answers[case.image_path]

    report = await run_evaluation(
        cases, analyze, output_dir=tmp_path / "o", gateway_mode="mock"
    )

    assert report.target_axis_performance["st_segment"]["case_count"] == 1
    assert report.target_axis_performance["st_segment"]["strict_pass_rate"] == 1.0
    assert report.target_axis_performance["rhythm"]["case_count"] == 1
    assert report.target_axis_performance["rhythm"]["strict_pass_rate"] == 0.0


async def test_run_evaluation_records_errors_without_aborting(tmp_path: Path) -> None:
    cases = [_case(tmp_path, Severity.WARNING, ())]

    async def analyze(_case: EvalCase) -> AnalysisResult:
        raise ConnectionError("gateway down")

    report = await run_evaluation(
        cases, analyze, output_dir=tmp_path / "o", gateway_mode="real"
    )
    assert report.error_count == 1
    assert report.scored == 0
    assert report.cases[0].error is not None


async def test_run_evaluation_throttles_partial_scorecard_for_1000_cases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cases = [
        _case(tmp_path, Severity.NORMAL, (), name=f"case_{i:04d}")
        for i in range(1000)
    ]
    partial_writes: list[int] = []

    async def analyze(_case: EvalCase) -> AnalysisResult:
        return _complete_result(Severity.NORMAL, summary="clear")

    def record_partial_write(
        _path,
        _gateway_mode,
        scores,
        _cases,
        _registry,
        *,
        aborted_reason: str = "",
    ) -> None:
        assert aborted_reason == ""
        partial_writes.append(len(scores))

    monkeypatch.setattr(
        "dicom_overlay.infrastructure.eval_harness._write_scorecard",
        record_partial_write,
    )
    monkeypatch.setattr(
        "dicom_overlay.infrastructure.eval_harness._write_raw_result",
        lambda *args, **kwargs: None,
    )

    report = await run_evaluation(
        cases,
        analyze,
        output_dir=tmp_path / "o",
        gateway_mode="mock",
    )

    assert report.total == 1000
    assert partial_writes == list(range(50, 1001, 50))


# ---------------------------------------------------------------------------
# Task B: framework coverage matrix (axis x severity)
# ---------------------------------------------------------------------------

def _ekg_case(
    tmp_path: Path,
    severity: Severity,
    *,
    name: str,
    target_axes: tuple[str, ...] = (),
    cant_miss: tuple[str, ...] = (),
) -> EvalCase:
    img = tmp_path / f"{name}.png"
    img.write_bytes(b"\x89PNG\r\n")
    return EvalCase(
        image_path=img,
        modality=Modality.EKG,
        expected_severity=severity,
        target_axes=target_axes,
        cant_miss=cant_miss,
        label=name,
    )


def test_compute_axis_coverage_normal_and_abnormal(tmp_path: Path) -> None:
    from dicom_overlay.domain.modality_profile import default_registry
    from dicom_overlay.infrastructure.eval_harness import compute_axis_coverage

    cases = [
        _ekg_case(
            tmp_path,
            Severity.NORMAL,
            name="n",
            target_axes=("st_segment", "rhythm"),
        ),
        _ekg_case(
            tmp_path,
            Severity.CRITICAL,
            name="c",
            target_axes=("st_segment", "stemi_pattern"),
        ),
    ]
    cov = compute_axis_coverage(cases, default_registry())
    ekg = cov["EKG"]
    assert ekg["total_axes"] == 16
    # rhythm, st_segment, stemi_pattern were all touched.
    assert ekg["covered_axes"] == 3
    # Only st_segment got BOTH a normal and an abnormal case.
    assert ekg["fully_covered_axes"] == 1
    assert ekg["matrix"]["st_segment"] == {"normal": True, "abnormal": True}
    assert ekg["matrix"]["stemi_pattern"] == {"normal": False, "abnormal": True}
    assert "heart_rate" in ekg["missing_axes"]


# ---------------------------------------------------------------------------
# Task C: can't-miss hard gate
# ---------------------------------------------------------------------------

def test_cant_miss_caught_when_abnormal_and_named(tmp_path: Path) -> None:
    case = _ekg_case(
        tmp_path, Severity.CRITICAL, name="stemi", cant_miss=("STEMI",)
    )
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary="Anterior STEMI with ST elevation in V1-V4.",
        checklist={
            "stemi_pattern": ChecklistItem(value="anterior", status=Severity.CRITICAL),
        },
    )
    score = score_case(case, result, latency_ms=10)
    assert score.cant_miss_caught is True
    assert score.cant_miss_missed == []


def test_cant_miss_missed_when_called_normal(tmp_path: Path) -> None:
    case = _ekg_case(
        tmp_path, Severity.CRITICAL, name="stemi", cant_miss=("STEMI",)
    )
    # The read names STEMI but calls the tracing normal -> still a miss.
    result = _result_with_checklist(
        Severity.NORMAL,
        summary="Possible STEMI but overall normal.",
        checklist={},
    )
    score = score_case(case, result, latency_ms=10)
    assert score.cant_miss_caught is False
    assert score.cant_miss_missed == ["STEMI"]


def test_cant_miss_missed_when_not_named(tmp_path: Path) -> None:
    case = _ekg_case(
        tmp_path, Severity.CRITICAL, name="stemi", cant_miss=("STEMI",)
    )
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary="Significant abnormality, refer urgently.",
        checklist={},
    )
    score = score_case(case, result, latency_ms=10)
    assert score.cant_miss_caught is False
    assert score.cant_miss_missed == ["STEMI"]


async def test_run_evaluation_aggregates_cant_miss_and_coverage(
    tmp_path: Path,
) -> None:
    caught = _ekg_case(
        tmp_path, Severity.CRITICAL, name="stemi", cant_miss=("STEMI",),
        target_axes=("stemi_pattern",),
    )
    missed = _ekg_case(
        tmp_path, Severity.CRITICAL, name="vt", cant_miss=("ventricular tachycardia",),
        target_axes=("rhythm",),
    )
    answers = {
        caught.image_path: _result_with_checklist(
            Severity.CRITICAL, summary="Anterior STEMI.", checklist={}
        ),
        missed.image_path: _result_with_checklist(
            Severity.CRITICAL, summary="Wide complex tachycardia.", checklist={}
        ),
    }

    async def analyze(case: EvalCase) -> AnalysisResult:
        return answers[case.image_path]

    report = await run_evaluation(
        [caught, missed], analyze, output_dir=tmp_path / "o", gateway_mode="mock"
    )
    assert report.cant_miss_total == 2
    assert report.cant_miss_caught_count == 1
    assert report.cant_miss_missed == ["vt: ventricular tachycardia"]
    assert report.cant_miss_passed is False
    assert "EKG" in report.axis_coverage
    assert report.axis_coverage["EKG"]["covered_axes"] == 2

