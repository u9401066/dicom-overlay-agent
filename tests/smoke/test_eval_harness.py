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
    is_empty_read,
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


def _result(
    severity: Severity, *, summary: str, bbox: RegionRect | None = None
) -> AnalysisResult:
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
    assert score.concept_precision == 1.0
    assert score.concept_recall == 1.0
    assert score.concept_f1 == 1.0
    assert score.concept_false_positives == []
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


def test_score_case_accepts_clinically_incomplete_but_structurally_valid_result(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, Severity.NORMAL, ())
    result = _complete_result(Severity.NORMAL, summary="Within normal limits.")
    result.incomplete = True
    result.incomplete_reasons = ["Lead V6 is cropped; QTc is not assessable."]

    score = score_case(case, result, latency_ms=12)

    assert score.schema_ok is True
    assert score.schema_issue == ""


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
        "concept_precision": 1.0,
        "concept_recall": 1.0,
        "concept_f1": 1.0,
        "false_positive_penalty": 0.0,
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
        "concept_precision": 0.0,
        "concept_recall": 0.0,
        "concept_f1": 0.0,
        "false_positive_penalty": 0.0,
        "negative_recall": 1.0,
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
    assert score.partial_credit <= 0.4


def test_extra_diagnoses_reduce_concept_precision_and_partial_credit(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.WARNING,
        name="afib_precision",
        keywords=("atrial fibrillation",),
    )
    clean = _result_with_checklist(
        Severity.WARNING,
        summary="Atrial fibrillation is present.",
        checklist={},
    )
    noisy = _result_with_checklist(
        Severity.WARNING,
        summary=(
            "Atrial fibrillation, ventricular tachycardia, and hyperkalemia "
            "are present."
        ),
        checklist={},
    )

    clean_score = score_case(case, clean, latency_ms=12)
    noisy_score = score_case(case, noisy, latency_ms=12)

    assert noisy_score.keyword_recall == 1.0
    assert noisy_score.concept_recall == 1.0
    assert noisy_score.concept_precision == 0.333
    assert noisy_score.concept_f1 == 0.5
    assert noisy_score.concept_false_positives == [
        "hyperkalemia",
        "ventricular tachycardia",
    ]
    assert noisy_score.false_positive_penalty == 0.667
    assert noisy_score.partial_credit < clean_score.partial_credit
    assert noisy_score.strict_pass is False


def test_partial_uncertain_reference_does_not_score_unlabeled_extras(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.WARNING,
        name="partial_reference",
        keywords=("atrial fibrillation",),
        label_status="partially_uncertain",
    )
    result = _result_with_checklist(
        Severity.WARNING,
        summary="Atrial fibrillation and prominent T waves are present.",
        checklist={},
    )

    score = score_case(case, result, latency_ms=12)

    assert score.false_positive_scorable is False
    assert score.concept_false_positives == []
    assert score.false_positive_penalty == 0.0
    assert score.strict_pass is True


def test_rather_than_phrase_does_not_assert_rejected_diagnosis(
    tmp_path: Path,
) -> None:
    case = _ekg_case(tmp_path, Severity.NORMAL, name="normal_variant")
    result = _result_with_checklist(
        Severity.INFO,
        summary="Early repolarization rather than acute ischemia.",
        checklist={},
    )

    score = score_case(case, result, latency_ms=12)

    assert "ischemia" not in score.concept_false_positives


def test_write_raw_result_includes_local_case_metadata(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.NORMAL, (), name="case_meta")
    result = _complete_result(
        Severity.NORMAL,
        summary="No acute finding.",
    )
    result.layout = {
        "format": "12lead_3x4_rhythm",
        "rhythm_strip_bbox": [0.0, 0.8, 1.0, 0.18],
    }
    result.analysis_time_ms = 321
    result.model_used = "openai/gpt-5.6-luna"
    result.image_quality = {"grade": "limited"}
    result.next_steps = ["Confirm calibration."]
    result.incomplete = True
    result.incomplete_reasons = ["Calibration marker is not visible."]
    result.validation_warnings = ["Synthetic validator warning"]
    result.review_required = True
    result.review_reasons = ["Low-confidence rhythm classification."]
    result.analysis_trace = [{"stage": "refine", "tool": "crop_region_base64"}]
    score = score_case(case, result, latency_ms=10)

    _write_raw_result(
        tmp_path,
        result,
        score,
        case_metadata={"local_image_quality": {"low_signal": False}},
    )

    raw = json.loads((tmp_path / "case_meta.json").read_text(encoding="utf-8"))
    assert raw["local_image_quality"] == {"low_signal": False}
    assert raw["layout"]["rhythm_strip_bbox"] == [0.0, 0.8, 1.0, 0.18]
    assert raw["analysis_time_ms"] == 321
    assert raw["model_used"] == "openai/gpt-5.6-luna"
    assert raw["image_quality"] == {"grade": "limited"}
    assert raw["next_steps"] == ["Confirm calibration."]
    assert raw["incomplete_reasons"] == ["Calibration marker is not visible."]
    assert raw["validation_warnings"] == ["Synthetic validator warning"]
    assert raw["review_required"] is True
    assert raw["review_reasons"] == ["Low-confidence rhythm classification."]
    assert raw["analysis_trace"][0]["tool"] == "crop_region_base64"


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


def test_keyword_recall_credits_clinical_synonyms(tmp_path: Path) -> None:
    """Abbreviations and equivalent phrasings must count as hits (mined from
    real MEETI runs where correct reads were scored as misses)."""
    case = _case(
        tmp_path,
        Severity.WARNING,
        (
            "flutter waves",
            "irregularly irregular",
            "right bundle branch block",
            "axis deviation",
        ),
    )
    result = _result(
        Severity.WARNING,
        summary=(
            "Sawtooth atrial activity consistent with atrial flutter; other "
            "segments show atrial fibrillation with a leftward axis and RBBB "
            "morphology."
        ),
    )
    score = score_case(case, result, latency_ms=0)
    assert score.keyword_misses == []


def test_keyword_recall_normalizes_hyphens_and_plurals(tmp_path: Path) -> None:
    """Hyphenation/spacing variants must not create false misses."""
    case = _case(
        tmp_path,
        Severity.WARNING,
        ("poor r wave progression", "first degree av block", "low voltage"),
    )
    result = _result(
        Severity.WARNING,
        summary=(
            "Poor R-wave progression across precordials with a first-degree "
            "AV block and diffuse low-voltage QRS."
        ),
    )
    score = score_case(case, result, latency_ms=0)
    assert score.keyword_misses == []


def test_keyword_recall_still_misses_genuine_disagreement(tmp_path: Path) -> None:
    """Synonyms must not credit a finding the model did not actually report:
    a model reading sinus rhythm must still miss an atrial-fibrillation label."""
    case = _case(tmp_path, Severity.WARNING, ("atrial fibrillation",))
    result = _result(
        Severity.WARNING,
        summary="Regular sinus rhythm at 80 bpm with narrow QRS complexes.",
    )
    score = score_case(case, result, latency_ms=0)
    assert score.keyword_misses == ["atrial fibrillation"]


def test_keyword_recall_honors_negation_for_synonyms(tmp_path: Path) -> None:
    """A negated equivalent phrase must not count as a positive hit."""
    case = _case(tmp_path, Severity.WARNING, ("st elevation",))
    result = _result(
        Severity.WARNING,
        summary="No convincing ST-elevation STEMI pattern is present.",
    )
    score = score_case(case, result, latency_ms=0)
    assert score.keyword_misses == ["st elevation"]


def test_is_empty_read_flags_blank_summary_and_no_findings() -> None:
    empty = _result(Severity.INFO, summary="")
    assert is_empty_read(empty) is True
    whitespace = _result(Severity.INFO, summary="   ")
    assert is_empty_read(whitespace) is True
    non_empty = _result(Severity.NORMAL, summary="Clear study, no acute finding.")
    assert is_empty_read(non_empty) is False


def test_score_case_detects_out_of_bounds_bbox(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.WARNING, ())
    result = _result(
        Severity.WARNING,
        summary="bad bbox",
        bbox=RegionRect(x=0.9, y=0.5, w=0.5, h=0.2),  # x+w = 1.4 > 1
    )
    score = score_case(case, result, latency_ms=0)
    assert score.bbox_in_bounds is False


def test_score_case_rejects_zero_area_bbox(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.WARNING, ())
    zero_width = _result(
        Severity.WARNING,
        summary="degenerate bbox",
        bbox=RegionRect(x=0.2, y=0.2, w=0.0, h=0.3),
    )
    zero_height = _result(
        Severity.WARNING,
        summary="degenerate bbox",
        bbox=RegionRect(x=0.2, y=0.2, w=0.3, h=0.0),
    )

    assert score_case(case, zero_width, latency_ms=0).bbox_in_bounds is False
    assert score_case(case, zero_height, latency_ms=0).bbox_in_bounds is False


def test_normal_and_info_receive_full_clinical_partial_credit(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.NORMAL, ())
    result = _complete_result(Severity.INFO, summary="No acute finding.")

    score = score_case(case, result, latency_ms=0)

    assert score.severity_match is False
    assert score.strict_pass is True
    assert score.partial_credit == 1.0
    assert score.partial_credit_breakdown["severity_exact"] == 1.0
    assert score.partial_credit_breakdown["negative_recall"] == 1.0


def test_ungradable_info_without_concepts_does_not_manufacture_false_positives(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, Severity.INFO, ())
    result = _complete_result(
        Severity.WARNING,
        summary="Hyperkalemia is present.",
    )

    score = score_case(case, result, latency_ms=0)

    assert score.concept_false_positives == []
    assert score.concept_precision == 1.0
    assert score.concept_recall == 1.0


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
    report = await run_evaluation(cases, analyze, output_dir=out, gateway_mode="mock")

    assert report.total == 2
    assert report.scored == 2
    assert report.severity_accuracy == 1.0
    assert report.mean_negative_recall == 1.0
    assert report.strict_pass_rate == 1.0
    assert report.mean_partial_credit == 1.0
    assert report.partial_credit_breakdown["keyword_recall"] == 1.0
    assert report.partial_credit_breakdown["negative_recall"] == 1.0
    assert (
        report.partial_credit_breakdown["negative_recall"]
        == report.mean_negative_recall
    )
    assert report.mean_concept_precision == 1.0
    assert report.mean_concept_recall == 1.0
    assert report.mean_concept_f1 == 1.0
    scorecard = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["gateway_mode"] == "mock"
    assert "mean_negative_recall" in scorecard
    assert scorecard["mean_concept_precision"] == 1.0
    assert scorecard["mean_concept_recall"] == 1.0
    assert scorecard["mean_concept_f1"] == 1.0
    assert scorecard["mean_false_positive_penalty"] == 0.0
    assert scorecard["cases"][0]["concept_false_positives"] == []
    assert scorecard["cases"][0]["concept_f1"] == 1.0
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


async def test_run_evaluation_collects_case_metadata_after_analysis(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, Severity.NORMAL, (), name="metadata_after")
    observed: dict[str, object] = {}

    async def analyze(_case: EvalCase) -> AnalysisResult:
        observed["local_image_quality"] = {"low_signal": False}
        return _complete_result(Severity.NORMAL, summary="Within normal limits.")

    await run_evaluation(
        [case],
        analyze,
        output_dir=tmp_path / "out_metadata",
        gateway_mode="mock",
        case_metadata=lambda _case: dict(observed),
    )

    raw = json.loads(
        (tmp_path / "out_metadata" / "results" / "metadata_after.json").read_text(
            encoding="utf-8"
        )
    )
    assert raw["local_image_quality"] == {"low_signal": False}


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
        cases,
        analyze,
        output_dir=tmp_path / "o",
        gateway_mode="real",
        case_metadata=lambda _case: {
            "protocol_digest": "protocol-123",
            "source_image_sha256": "image-456",
        },
    )
    assert report.error_count == 1
    assert report.scored == 0
    assert report.cases[0].error is not None
    raw = json.loads(
        (tmp_path / "o" / "results" / "x.json").read_text(encoding="utf-8")
    )
    assert raw["protocol_digest"] == "protocol-123"
    assert raw["source_image_sha256"] == "image-456"
    assert raw["incomplete"] is True


async def test_run_evaluation_throttles_partial_scorecard_for_1000_cases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cases = [
        _case(tmp_path, Severity.NORMAL, (), name=f"case_{i:04d}") for i in range(1000)
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
    keywords: tuple[str, ...] = (),
    target_axes: tuple[str, ...] = (),
    cant_miss: tuple[str, ...] = (),
    urgent_concerns: tuple[str, ...] = (),
    label_status: str = "asserted",
) -> EvalCase:
    img = tmp_path / f"{name}.png"
    img.write_bytes(b"\x89PNG\r\n")
    return EvalCase(
        image_path=img,
        modality=Modality.EKG,
        expected_severity=severity,
        expected_keywords=keywords,
        target_axes=target_axes,
        cant_miss=cant_miss,
        urgent_concerns=urgent_concerns,
        label_status=label_status,
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
    case = _ekg_case(tmp_path, Severity.CRITICAL, name="stemi", cant_miss=("STEMI",))
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
    case = _ekg_case(tmp_path, Severity.CRITICAL, name="stemi", cant_miss=("STEMI",))
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
    case = _ekg_case(tmp_path, Severity.CRITICAL, name="stemi", cant_miss=("STEMI",))
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary="Significant abnormality, refer urgently.",
        checklist={},
    )
    score = score_case(case, result, latency_ms=10)
    assert score.cant_miss_caught is False
    assert score.cant_miss_missed == ["STEMI"]


def test_stemi_cant_miss_requires_critical_severity(tmp_path: Path) -> None:
    case = _ekg_case(tmp_path, Severity.CRITICAL, name="stemi", cant_miss=("STEMI",))
    result = _result_with_checklist(
        Severity.WARNING,
        summary="Definite anterior STEMI with ST elevation.",
        checklist={
            "stemi_pattern": ChecklistItem(
                value="anterior",
                status=Severity.WARNING,
            )
        },
    )

    score = score_case(case, result, latency_ms=10)

    assert score.cant_miss_caught is False
    assert score.cant_miss_missed == ["STEMI"]


def test_early_repolarization_without_stemi_is_not_a_positive_hit(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="early_repol",
        keywords=("stemi",),
        cant_miss=("STEMI",),
    )
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary="Early repolarization pattern without STEMI.",
        checklist={
            "stemi_pattern": ChecklistItem(
                value="anterior",
                status=Severity.CRITICAL,
            )
        },
    )

    score = score_case(case, result, latency_ms=10)

    assert score.keyword_hits == []
    assert score.keyword_misses == ["stemi"]
    assert score.concept_recall == 0.0
    assert "early repolarization" in score.concept_false_positives
    assert score.cant_miss_caught is False
    assert score.cant_miss_missed == ["STEMI"]


def test_uncertain_stemi_is_not_a_positive_hit(tmp_path: Path) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="possible_stemi",
        keywords=("stemi",),
        cant_miss=("STEMI",),
    )
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary="Possible STEMI cannot be excluded.",
        checklist={},
    )

    score = score_case(case, result, latency_ms=10)

    assert score.keyword_misses == ["stemi"]
    assert score.concept_hits == []
    assert score.cant_miss_caught is False


def test_urgent_concern_accepts_critical_uncertain_stemi(tmp_path: Path) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="urgent_stemi",
        urgent_concerns=("STEMI",),
        label_status="uncertain",
    )
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary="Possible anterior STEMI cannot be excluded; urgent review.",
        checklist={},
    )

    score = score_case(case, result, latency_ms=10)

    assert score.urgent_concern_hits == ["STEMI"]
    assert score.urgent_concern_missed == []
    assert score.urgent_concern_recall == 1.0


def test_urgent_stemi_concern_accepts_critical_hyperacute_ischemia(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="urgent_hyperacute_ischemia",
        urgent_concerns=("STEMI",),
        label_status="uncertain",
    )
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary=(
            "Tall broad T waves may reflect hyperacute ischemia or benign "
            "repolarization; no definite STEMI is established."
        ),
        checklist={},
    )

    score = score_case(case, result, latency_ms=10)

    assert score.urgent_concern_hits == ["STEMI"]
    assert score.urgent_concern_missed == []
    assert score.urgent_concern_recall == 1.0


def test_urgent_concern_rejects_negation_and_unqualified_certainty(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="urgent_stemi",
        urgent_concerns=("STEMI",),
        label_status="uncertain",
    )
    no_stemi = _result_with_checklist(
        Severity.CRITICAL,
        summary="No STEMI pattern.",
        checklist={},
    )
    overconfident = _result_with_checklist(
        Severity.CRITICAL,
        summary="Definite anterior STEMI.",
        checklist={},
    )

    assert score_case(case, no_stemi, 10).urgent_concern_missed == ["STEMI"]
    assert score_case(case, overconfident, 10).urgent_concern_missed == ["STEMI"]


def test_urgent_acute_mi_is_distinct_from_stemi(tmp_path: Path) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="urgent_acute_mi",
        urgent_concerns=("acute MI",),
        label_status="uncertain",
    )
    acute_mi = _result_with_checklist(
        Severity.CRITICAL,
        summary="Possible acute myocardial infarction cannot be excluded.",
        checklist={},
    )
    stemi_only = _result_with_checklist(
        Severity.CRITICAL,
        summary="Possible STEMI cannot be excluded.",
        checklist={},
    )

    assert score_case(case, acute_mi, 10).urgent_concern_hits == ["acute MI"]
    assert score_case(case, stemi_only, 10).urgent_concern_missed == ["acute MI"]


async def test_info_ungradable_case_is_excluded_from_accuracy_denominators(
    tmp_path: Path,
) -> None:
    gradable = _ekg_case(tmp_path, Severity.NORMAL, name="normal")
    ungradable = _ekg_case(
        tmp_path,
        Severity.INFO,
        name="ungradable",
        label_status="ungradable",
    )
    answers = {
        gradable.image_path: _result_with_checklist(
            Severity.NORMAL, summary="Normal ECG.", checklist={}
        ),
        ungradable.image_path: _result_with_checklist(
            Severity.WARNING, summary="Possible abnormality.", checklist={}
        ),
    }

    async def analyze(case: EvalCase) -> AnalysisResult:
        return answers[case.image_path]

    report = await run_evaluation(
        [gradable, ungradable],
        analyze,
        output_dir=tmp_path / "ungradable-output",
        gateway_mode="mock",
    )

    assert report.clinical_scorable_count == 1
    assert report.severity_scorable_count == 1
    assert report.severity_accuracy == 1.0
    assert report.severity_abnormal_accuracy == 1.0


async def test_run_evaluation_aggregates_urgent_concern_gate(tmp_path: Path) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="urgent_stemi",
        urgent_concerns=("STEMI",),
        label_status="uncertain",
    )

    async def analyze(_case: EvalCase) -> AnalysisResult:
        return _result_with_checklist(
            Severity.CRITICAL,
            summary="Possible STEMI; urgent expert review is required.",
            checklist={},
        )

    report = await run_evaluation(
        [case],
        analyze,
        output_dir=tmp_path / "urgent-output",
        gateway_mode="mock",
    )

    assert report.urgent_concern_total == 1
    assert report.urgent_concern_caught_count == 1
    assert report.urgent_concern_missed == []
    assert report.urgent_concern_passed is True


async def test_run_evaluation_aggregates_cant_miss_and_coverage(
    tmp_path: Path,
) -> None:
    caught = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="stemi",
        cant_miss=("STEMI",),
        target_axes=("stemi_pattern",),
    )
    missed = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="vt",
        cant_miss=("ventricular tachycardia",),
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
