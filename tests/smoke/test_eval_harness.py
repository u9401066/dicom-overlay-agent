"""Smoke tests for the recognition evaluation harness."""

from __future__ import annotations

import json
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
    EvalCase,
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


def test_score_case_exact_severity_and_keyword_recall(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.WARNING, ("consolidation", "opacity"))
    result = _result(
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


def _result_with_checklist(
    severity: Severity, *, summary: str, checklist: dict[str, ChecklistItem]
) -> AnalysisResult:
    return AnalysisResult(
        modality=Modality.EKG,
        summary=summary,
        severity=severity,
        findings=[],
        checklist=checklist,
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
        cases[0].image_path: _result(
            Severity.WARNING,
            summary="consolidation seen",
            bbox=RegionRect(x=0.1, y=0.1, w=0.2, h=0.2),
        ),
        cases[1].image_path: _result(Severity.NORMAL, summary="clear"),
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
    scorecard = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["gateway_mode"] == "mock"
    assert "mean_negative_recall" in scorecard
    assert len(scorecard["cases"]) == 2
    assert (out / "results").is_dir()


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

