"""Smoke tests for the recognition evaluation harness."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import pytest

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
    _atomic_write_json,
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
    result.image_quality = "Synthetic evaluation image is fully readable."
    result.next_steps = ["Review the original synthetic evaluation image."]
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


def test_keyword_recall_rejects_unsupported_classifier_mention(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.WARNING,
        name="unsupported_af",
        keywords=("atrial fibrillation",),
    )
    result = _result_with_checklist(
        Severity.WARNING,
        summary=(
            "Regular sinus rhythm; automated atrial fibrillation scoring is "
            "not visually supported on this screenshot."
        ),
        checklist={},
    )

    score = score_case(case, result, latency_ms=12)

    assert score.keyword_hits == []
    assert score.keyword_misses == ["atrial fibrillation"]
    assert score.concept_hits == []


def test_normal_case_does_not_penalize_visually_unsupported_candidate_list(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.NORMAL,
        name="unsupported_candidates",
        keywords=("normal", "sinus rhythm"),
    )
    result = _result_with_checklist(
        Severity.NORMAL,
        summary=(
            "Normal sinus rhythm. Low-probability left atrial enlargement, "
            "incomplete RBBB, and RBBB candidates are visually unsupported."
        ),
        checklist={},
    )

    score = score_case(case, result, latency_ms=12)

    assert "right bundle branch block" not in score.concept_false_positives
    assert score.keyword_recall == 1.0


def test_normal_case_does_not_count_late_item_in_shared_no_clause(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.NORMAL,
        name="shared_no_clause",
        keywords=("normal", "sinus rhythm"),
    )
    result = _result_with_checklist(
        Severity.NORMAL,
        summary=(
            "Normal sinus rhythm. QRS is narrow, with no convincing conduction "
            "block, pathologic Q waves, or acute ST-segment elevation/depression."
        ),
        checklist={},
    )

    score = score_case(case, result, latency_ms=12)

    assert "st elevation" not in score.concept_false_positives
    assert score.false_positive_penalty == 0.0


def test_normal_case_does_not_count_excluded_definitive_read_as_diagnosis(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.NORMAL,
        name="excluded_ischemia_read",
        keywords=("normal", "sinus rhythm"),
    )
    result = _result_with_checklist(
        Severity.NORMAL,
        summary=(
            "Normal sinus rhythm. Screenshot-only capture limits exact interval "
            "quantification and excludes a fully definitive ischemia read."
        ),
        checklist={},
    )

    score = score_case(case, result, latency_ms=12)

    assert "ischemia" not in score.concept_false_positives
    assert score.false_positive_penalty == 0.0


def test_normal_case_does_not_score_info_review_marker_as_diagnosis(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.NORMAL,
        name="info_review_marker",
        keywords=("normal", "sinus rhythm"),
    )
    result = _result_with_checklist(
        Severity.INFO,
        summary="Normal sinus rhythm; no actionable abnormality is confirmed.",
        checklist={},
    )
    result.findings = [
        Finding(
            id="candidate",
            regions=["lead_V1"],
            label="LVH voltage candidate",
            detail="High voltage is not confirmed on a calibrated source.",
            severity=Severity.INFO,
            confidence="low",
            question="Can a reviewer confirm calibrated voltage criteria?",
            bboxes=[RegionRect(0.1, 0.1, 0.1, 0.1)],
        )
    ]

    score = score_case(case, result, latency_ms=12)

    assert score.concept_false_positives == []
    assert score.severity_abnormal_match is True


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
        "candidate_concept_recall": 0.0,
        "weighted_concept_recall": 1.0,
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
        "candidate_concept_recall": 0.0,
        "weighted_concept_recall": 0.0,
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


def test_cautious_expected_finding_label_is_not_a_new_false_positive(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.WARNING,
        name="afib_cautious_finding",
        keywords=("atrial fibrillation",),
    )
    result = _result_with_checklist(
        Severity.WARNING,
        summary="Irregularly irregular rhythm most consistent with atrial fibrillation.",
        checklist={},
    )
    result.findings = [
        Finding(
            id="f1",
            regions=["lead_II"],
            label="Irregular rhythm; atrial fibrillation possible",
            detail="Native ECG confirmation remains appropriate.",
            severity=Severity.WARNING,
            bboxes=[RegionRect(0.1, 0.1, 0.2, 0.08)],
        )
    ]

    score = score_case(case, result, latency_ms=12)

    assert score.keyword_recall == 1.0
    assert score.concept_false_positives == []
    assert score.concept_precision == 1.0


def test_specific_expected_phrase_does_not_create_broader_false_positive(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.WARNING,
        name="nonspecific_stt",
        keywords=("nonspecific st-t changes",),
    )
    result = _result_with_checklist(
        Severity.WARNING,
        summary="Inferolateral nonspecific ST-T changes are present.",
        checklist={},
    )

    score = score_case(case, result, latency_ms=12)

    assert score.keyword_recall == 1.0
    assert score.concept_false_positives == []
    assert score.concept_precision == 1.0
    assert score.strict_pass is True


def test_separate_broader_assertion_remains_a_false_positive(tmp_path: Path) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.WARNING,
        name="nonspecific_stt_with_extra",
        keywords=("nonspecific st-t changes",),
    )
    result = _result_with_checklist(
        Severity.WARNING,
        summary=(
            "Inferolateral nonspecific ST-T changes are present. "
            "Separate anterior T waves are inverted."
        ),
        checklist={},
    )

    score = score_case(case, result, latency_ms=12)

    assert score.concept_false_positives == ["t wave changes"]
    assert score.strict_pass is False


def test_partial_uncertain_reference_scores_asserted_concepts_without_precision(
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
    assert score.reference_complete is False
    assert score.clinical_scorable is True
    assert score.severity_scorable is True
    assert score.concept_false_positives == []
    assert score.false_positive_penalty == 0.0
    assert score.concept_hits == ["atrial fibrillation"]
    assert score.strict_pass is False
    assert score.partial_credit == 1.0
    assert score.partial_credit_breakdown["concept_recall"] == 1.0


def test_weak_reference_records_half_weighted_candidate_credit(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.WARNING,
        name="cautious_candidates",
        keywords=(
            "tachycardia",
            "fascicular block",
            "ventricular tachycardia",
        ),
        label_status="partially_uncertain",
    )
    result = _result_with_checklist(
        Severity.INFO,
        summary="Tachycardic ECG with possible LAFB.",
        checklist={},
    )
    result.findings = [
        Finding(
            id="wide-run",
            regions=["lead_V2", "lead_V3"],
            label="Wide-complex run",
            detail="Three broad complexes recur across the sampled leads.",
            severity=Severity.INFO,
            confidence="low",
            question="Does this represent VT versus artifact?",
        )
    ]

    score = score_case(case, result, latency_ms=12)

    assert score.concept_hits == ["tachycardia"]
    assert score.candidate_concept_hits == [
        "fascicular block",
        "ventricular tachycardia",
    ]
    assert score.candidate_concept_misses == []
    assert score.concept_recall == 0.333
    assert score.candidate_concept_recall == 0.667
    assert score.weighted_concept_recall == 0.667
    assert score.partial_credit_breakdown["concept_recall"] == 0.333
    assert score.partial_credit_breakdown["weighted_concept_recall"] == 0.667
    assert score.strict_pass is False


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


def test_keyword_recall_credits_strict_sinus_and_t_wave_phrasings(
    tmp_path: Path,
) -> None:
    case = _case(
        tmp_path,
        Severity.WARNING,
        ("sinus rhythm", "tall t wave"),
    )
    result = _result(
        Severity.WARNING,
        summary=(
            "Sinus mechanism with persistent prominent broad T waves "
            "across the anterior precordial leads."
        ),
    )

    score = score_case(case, result, latency_ms=0)

    assert score.keyword_hits == ["sinus rhythm", "tall t wave"]
    assert score.keyword_misses == []


def test_keyword_recall_does_not_credit_uncertain_sinus_or_t_waves(
    tmp_path: Path,
) -> None:
    case = _case(
        tmp_path,
        Severity.WARNING,
        ("sinus rhythm", "tall t wave"),
    )
    result = _result(
        Severity.WARNING,
        summary=(
            "Sinus mechanism is likely; prominent broad T waves are possible "
            "in the anterior precordial leads."
        ),
    )

    score = score_case(case, result, latency_ms=0)

    assert score.keyword_hits == []
    assert score.keyword_misses == ["sinus rhythm", "tall t wave"]


def test_keyword_recall_does_not_credit_negated_prominent_t_waves(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, Severity.WARNING, ("tall t wave",))
    result = _result(
        Severity.WARNING,
        summary="No prominent broad T waves are visible in the precordial leads.",
    )

    score = score_case(case, result, latency_ms=0)

    assert score.keyword_hits == []
    assert score.keyword_misses == ["tall t wave"]


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


def _full_ekg_layout() -> dict[str, object]:
    names = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")
    return {
        "format": "12lead_12x1",
        "leads": [
            {
                "name": name,
                "label_visible": True,
                "bbox": [0.0, index / 12, 1.0, 1 / 12],
            }
            for index, name in enumerate(names)
        ],
    }


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
        image_quality="Synthetic 12-lead EKG is fully readable.",
        next_steps=["Review the original synthetic tracing."],
        layout=_full_ekg_layout(),
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
    answers[cases[1].image_path].analysis_trace = [
        {
            "stage": "json_recovery",
            "status": "repaired",
            "tool": "bounded_json_delimiter_repair",
            "repair_count": 2,
        }
    ]

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
    assert report.partial_credit_component_counts == {
        "severity_abnormal": 2,
        "severity_exact": 2,
        "keyword_recall": 1,
        "concept_f1": 2,
        "negative_recall": 0,
        "concept_precision": 2,
        "concept_recall": 1,
        "candidate_concept_recall": 0,
        "weighted_concept_recall": 0,
        "false_positive_penalty": 2,
        "urgent_concern_recall": 0,
    }
    assert (
        report.partial_credit_breakdown["negative_recall"]
        == report.mean_negative_recall
    )
    assert report.mean_concept_precision == 1.0
    assert report.mean_concept_recall == 1.0
    assert report.concept_recall_scorable_count == 1
    assert report.mean_concept_f1 == 1.0
    assert report.normal_control_count == 1
    assert report.normal_control_specificity == 1.0
    assert report.diagnosis_scorable_count == 1
    assert report.single_diagnosis_exact_set_accuracy == 1.0
    scorecard = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["gateway_mode"] == "mock"
    assert "mean_negative_recall" in scorecard
    assert scorecard["mean_concept_precision"] == 1.0
    assert scorecard["mean_concept_recall"] == 1.0
    assert scorecard["concept_recall_scorable_count"] == 1
    assert scorecard["mean_concept_f1"] == 1.0
    assert scorecard["partial_credit_component_counts"]["keyword_recall"] == 1
    assert scorecard["partial_credit_component_counts"]["negative_recall"] == 0
    assert scorecard["mean_false_positive_penalty"] == 0.0
    assert scorecard["cases"][0]["concept_false_positives"] == []
    assert scorecard["cases"][0]["concept_f1"] == 1.0
    assert scorecard["mean_partial_credit"] == 1.0
    assert scorecard["strict_pass_rate"] == 1.0
    assert scorecard["sla_metrics"]["profile"] == {
        "initial_response_sec": 60.0,
        "first_crop_refinement_sec": 100.0,
        "total_sec": 180.0,
    }
    assert scorecard["sla_metrics"]["initial_response"]["rate"] == 1.0
    assert scorecard["sla_metrics"]["first_crop_refinement"]["rate"] is None
    assert scorecard["sla_metrics"]["total"]["rate"] == 1.0
    assert scorecard["json_repair_case_count"] == 1
    assert scorecard["json_repair_total_count"] == 2
    assert scorecard["raw_json_clean_rate"] == 0.5
    assert scorecard["cases"][1]["json_repair_count"] == 2
    assert scorecard["manifest_total"] == 2
    assert scorecard["result_count"] == 2
    assert scorecard["is_partial"] is False
    assert len(scorecard["cases"]) == 2
    assert (out / "results").is_dir()
    partial = json.loads((out / "scorecard.partial.json").read_text(encoding="utf-8"))
    assert partial["manifest_total"] == 2
    assert partial["result_count"] == 2
    assert partial["is_partial"] is False


async def test_run_evaluation_atomically_replaces_all_json_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case = _case(tmp_path, Severity.NORMAL, (), name="atomic")
    result = _complete_result(Severity.NORMAL, summary="Within normal limits.")
    result.review_required = True
    result.review_reasons = ["Expert review requested."]
    replacements: list[str] = []
    real_replace = os.replace

    def tracked_replace(source, destination) -> None:
        source_path = tmp_path.__class__(source)
        destination_path = tmp_path.__class__(destination)
        assert source_path.parent == destination_path.parent
        assert source_path.name.startswith(f".{destination_path.name}.")
        assert source_path.suffix == ".tmp"
        json.loads(source_path.read_text(encoding="utf-8"))
        replacements.append(destination_path.relative_to(tmp_path).as_posix())
        real_replace(source, destination)

    monkeypatch.setattr(
        "dicom_overlay.infrastructure.eval_harness.os.replace",
        tracked_replace,
    )

    async def analyze(_case: EvalCase) -> AnalysisResult:
        return result

    out = tmp_path / "atomic-output"
    await run_evaluation(
        [case],
        analyze,
        output_dir=out,
        gateway_mode="mock",
        case_metadata=lambda _case: {"review_metadata": {"arm": "candidate"}},
    )

    assert replacements == [
        "atomic-output/results/atomic.json",
        "atomic-output/scorecard.partial.json",
        "atomic-output/scorecard.json",
    ]
    raw = json.loads((out / "results" / "atomic.json").read_text(encoding="utf-8"))
    assert raw["review_required"] is True
    assert raw["review_metadata"] == {"arm": "candidate"}
    assert not list(out.rglob("*.tmp"))


def test_atomic_json_write_preserves_previous_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "scorecard.json"
    target.write_text('{"state": "previous"}', encoding="utf-8")

    def fail_replace(_source, _destination) -> None:
        raise OSError("simulated interruption before replace")

    monkeypatch.setattr(
        "dicom_overlay.infrastructure.eval_harness.os.replace",
        fail_replace,
    )

    with pytest.raises(OSError, match="simulated interruption"):
        _atomic_write_json(target, '{"state": "new"}')

    assert json.loads(target.read_text(encoding="utf-8")) == {"state": "previous"}
    assert not list(tmp_path.glob("*.tmp"))


async def test_diagnosis_metrics_separate_single_and_three_to_five_sets(
    tmp_path: Path,
) -> None:
    single = _ekg_case(
        tmp_path,
        Severity.WARNING,
        name="single_diagnosis",
        keywords=("atrial fibrillation",),
    )
    multi = _ekg_case(
        tmp_path,
        Severity.WARNING,
        name="three_diagnoses",
        keywords=(
            "atrial fibrillation",
            "right bundle branch block",
            "left ventricular hypertrophy",
        ),
    )
    answers = {
        single.image_path: _result_with_checklist(
            Severity.WARNING,
            summary="Atrial fibrillation.",
            checklist={},
        ),
        multi.image_path: _result_with_checklist(
            Severity.WARNING,
            summary="Atrial fibrillation with right bundle branch block.",
            checklist={},
        ),
    }

    async def analyze(case: EvalCase) -> AnalysisResult:
        return answers[case.image_path]

    report = await run_evaluation(
        [single, multi],
        analyze,
        output_dir=tmp_path / "diagnosis-metrics",
        gateway_mode="mock",
    )

    assert report.diagnosis_scorable_count == 2
    assert report.diagnosis_exact_set_accuracy == 0.5
    assert report.diagnosis_complete_recall_rate == 0.5
    assert report.single_diagnosis_scorable_count == 1
    assert report.single_diagnosis_exact_set_accuracy == 1.0
    assert report.multi_diagnosis_3_to_5_scorable_count == 1
    assert report.multi_diagnosis_3_to_5_exact_set_accuracy == 0.0
    assert report.multi_diagnosis_3_to_5_complete_recall_rate == 0.0


async def test_component_aggregates_exclude_unscorable_reference_dimensions(
    tmp_path: Path,
) -> None:
    asserted_normal = _case(
        tmp_path,
        Severity.NORMAL,
        (),
        negatives=("no ischemia",),
        name="asserted_normal",
    )
    unlabeled_abnormal = EvalCase(
        image_path=tmp_path / "unlabeled_abnormal.png",
        modality=Modality.EKG,
        expected_severity=Severity.WARNING,
        expected_keywords=(),
        label_status="asserted",
        label="unlabeled_abnormal",
    )
    unlabeled_abnormal.image_path.write_bytes(b"\x89PNG\r\n")
    answers = {
        asserted_normal.image_path: _complete_result(
            Severity.NORMAL,
            summary="No ischemia.",
        ),
        unlabeled_abnormal.image_path: _complete_result(
            Severity.CRITICAL,
            summary="Abnormal tracing.",
        ),
    }

    async def analyze(case: EvalCase) -> AnalysisResult:
        return answers[case.image_path]

    report = await run_evaluation(
        [asserted_normal, unlabeled_abnormal],
        analyze,
        output_dir=tmp_path / "component_counts",
        gateway_mode="mock",
    )

    abnormal_score = next(
        score for score in report.cases if score.case_label == "unlabeled_abnormal"
    )
    assert abnormal_score.false_positive_scorable is False
    assert abnormal_score.partial_credit == 0.6
    assert report.partial_credit_component_counts["concept_f1"] == 1
    assert report.partial_credit_component_counts["concept_recall"] == 0
    assert report.concept_recall_scorable_count == 0
    assert report.mean_concept_recall == 0.0
    assert report.partial_credit_component_counts["negative_recall"] == 1
    assert report.partial_credit_breakdown["negative_recall"] == 1.0


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


@pytest.mark.parametrize(
    ("message", "expected_reason"),
    [
        (
            "OpenClaw error: 401 Unauthorized - OAuth access token expired",
            "fatal_provider_authentication",
        ),
        (
            "OpenClaw error: status=403 Forbidden",
            "fatal_provider_authentication",
        ),
        (
            "Provider code=insufficient_quota; subscription usage quota exhausted",
            "fatal_provider_quota_exhausted",
        ),
        (
            "ChatGPT subscription is expired",
            "fatal_provider_subscription_unavailable",
        ),
    ],
)
async def test_run_evaluation_stops_after_fatal_provider_error(
    tmp_path: Path,
    message: str,
    expected_reason: str,
) -> None:
    cases = [
        _case(tmp_path, Severity.WARNING, (), name=f"fatal_{index}")
        for index in range(5)
    ]
    attempted: list[str] = []

    async def analyze(case: EvalCase) -> AnalysisResult:
        attempted.append(case.label)
        raise RuntimeError(message)

    out = tmp_path / expected_reason
    report = await run_evaluation(
        cases,
        analyze,
        output_dir=out,
        gateway_mode="real",
    )

    assert attempted == ["fatal_0"]
    assert report.total == 1
    assert report.error_count == 1
    assert report.aborted_reason == expected_reason
    assert len(list((out / "results").glob("*.json"))) == 1
    raw = json.loads((out / "results" / "fatal_0.json").read_text(encoding="utf-8"))
    assert raw["abort_reason"] == expected_reason
    for name in ("scorecard.partial.json", "scorecard.json"):
        scorecard = json.loads((out / name).read_text(encoding="utf-8"))
        assert scorecard["manifest_total"] == 5
        assert scorecard["result_count"] == 1
        assert scorecard["aborted_reason"] == expected_reason


async def test_run_evaluation_does_not_abort_on_clinical_parse_or_schema_error(
    tmp_path: Path,
) -> None:
    cases = [
        _case(tmp_path, Severity.NORMAL, (), name=f"parse_{index}")
        for index in range(3)
    ]
    attempted: list[str] = []

    async def analyze(case: EvalCase) -> AnalysisResult:
        attempted.append(case.label)
        if case.label == "parse_0":
            raise ValueError("Clinical response JSON schema validation failed")
        return _complete_result(Severity.NORMAL, summary="Within normal limits.")

    report = await run_evaluation(
        cases,
        analyze,
        output_dir=tmp_path / "parse-errors",
        gateway_mode="real",
    )

    assert attempted == ["parse_0", "parse_1", "parse_2"]
    assert report.total == 3
    assert report.error_count == 1
    assert report.aborted_reason == ""


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


def test_ekg_ectopy_singular_and_plural_are_one_clinical_concept(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.WARNING,
        name="pvc_plural_reference",
        keywords=("premature ventricular complexes", "sinus rhythm"),
    )
    result = _result_with_checklist(
        Severity.WARNING,
        summary="Sinus rhythm with a premature ventricular complex.",
        checklist={
            "rhythm": ChecklistItem(
                value="sinus rhythm with ventricular ectopy",
                status=Severity.WARNING,
            )
        },
    )
    result.findings = [
        Finding(
            id="pvc-1",
            regions=["lead_II"],
            label="Premature ventricular complex",
            detail="One wide premature beat with a compensatory pause.",
            severity=Severity.WARNING,
            bboxes=[RegionRect(0.2, 0.1, 0.08, 0.05)],
        )
    ]

    score = score_case(case, result, latency_ms=12)

    assert score.keyword_recall == 1.0
    assert score.concept_hits == ["premature ventricular complexes", "sinus rhythm"]
    assert score.concept_misses == []
    assert score.concept_false_positives == []
    assert score.concept_f1 == 1.0


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


def test_urgent_stemi_concern_accepts_standardized_acute_st_elevation_phrase(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="urgent_standardized_st_elevation",
        urgent_concerns=("STEMI",),
        label_status="partially_ungradable",
    )
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary="Acute ischemia is possible but not confirmed.",
        checklist={
            "stemi_pattern": ChecklistItem(
                value="possible anterior",
                status=Severity.CRITICAL,
            ),
            "ischemia": ChecklistItem(
                value="possible acute",
                status=Severity.CRITICAL,
            ),
        },
    )
    result.findings = [
        Finding(
            id="acute-pattern",
            regions=["lead_V1", "lead_V2", "lead_V3", "lead_V4"],
            label="Possible acute ST-elevation ischemic pattern",
            detail="Contiguous anterior ST-T abnormality remains visible.",
            severity=Severity.CRITICAL,
            confidence="low",
            question="Are reciprocal changes present on the native ECG?",
        )
    ]

    score = score_case(case, result, latency_ms=10)

    assert score.urgent_concern_hits == ["STEMI"]
    assert score.urgent_concern_missed == []


def test_urgent_stemi_concern_accepts_uncertain_injury_with_st_elevation(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="urgent_acute_injury",
        urgent_concerns=("STEMI",),
        label_status="partially_uncertain",
    )
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary="Anterior precordial ST-T abnormality requires urgent review.",
        checklist={
            "st_segment": ChecklistItem(
                value="ST elevation in V2-V4",
                status=Severity.WARNING,
            ),
            "stemi_pattern": ChecklistItem(
                value="absent",
                status=Severity.NORMAL,
            ),
        },
    )
    result.findings = [
        Finding(
            id="f1",
            regions=["lead_V2", "lead_V3", "lead_V4"],
            label="Anterior precordial ST-T abnormality",
            detail=(
                "Early repolarization versus acute anterior injury cannot be "
                "resolved from the screenshot alone."
            ),
            severity=Severity.WARNING,
            confidence="low",
            question="Can acute injury be excluded on the source ECG?",
        )
    ]

    score = score_case(case, result, latency_ms=10)

    assert score.urgent_concern_hits == ["STEMI"]
    assert score.urgent_concern_missed == []
    assert score.urgent_concern_recall == 1.0


def test_urgent_injury_phrase_requires_structured_st_elevation(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="urgent_injury_without_st_elevation",
        urgent_concerns=("STEMI",),
        label_status="partially_uncertain",
    )
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary="Possible acute myocardial injury requires correlation.",
        checklist={"st_segment": ChecklistItem(value="normal", status=Severity.NORMAL)},
    )

    score = score_case(case, result, latency_ms=10)

    assert score.urgent_concern_hits == []
    assert score.urgent_concern_missed == ["STEMI"]


def test_urgent_injury_phrase_rejects_negated_injury(tmp_path: Path) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="negated_urgent_injury",
        urgent_concerns=("STEMI",),
        label_status="partially_uncertain",
    )
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary="ST elevation is present with no acute myocardial injury.",
        checklist={
            "st_segment": ChecklistItem(
                value="ST elevation in V2-V4",
                status=Severity.WARNING,
            )
        },
    )

    score = score_case(case, result, latency_ms=10)

    assert score.urgent_concern_hits == []
    assert score.urgent_concern_missed == ["STEMI"]


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


def test_urgent_acute_mi_accepts_structured_critical_stemi_differential(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="urgent_acute_mi_structured",
        urgent_concerns=("acute MI",),
        label_status="partially_uncertain",
    )
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary=(
            "Possible acute anterior-lateral ischemic ST-elevation pattern; "
            "STEMI cannot be excluded."
        ),
        checklist={
            "stemi_pattern": ChecklistItem(
                value="possible; not excluded",
                status=Severity.CRITICAL,
            ),
            "ischemia": ChecklistItem(
                value="possible acute ischemic pattern",
                status=Severity.CRITICAL,
            ),
        },
    )

    score = score_case(case, result, 10)

    assert score.urgent_concern_hits == ["acute MI"]
    assert score.urgent_concern_missed == []


def test_urgent_acute_mi_rejects_stemi_without_structured_acute_ischemia(
    tmp_path: Path,
) -> None:
    case = _ekg_case(
        tmp_path,
        Severity.CRITICAL,
        name="urgent_acute_mi_unstructured",
        urgent_concerns=("acute MI",),
        label_status="partially_uncertain",
    )
    result = _result_with_checklist(
        Severity.CRITICAL,
        summary="Possible STEMI cannot be excluded.",
        checklist={
            "stemi_pattern": ChecklistItem(
                value="possible; not excluded",
                status=Severity.CRITICAL,
            ),
            "ischemia": ChecklistItem(
                value="indeterminate",
                status=Severity.INFO,
            ),
        },
    )

    assert score_case(case, result, 10).urgent_concern_missed == ["acute MI"]


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
