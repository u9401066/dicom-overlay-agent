from __future__ import annotations

from dicom_overlay.application.interpretation_harness import (
    InterpretationContext,
    build_coarse_analysis_prompt,
    build_followup_prompt,
    build_initial_analysis_prompt,
    build_minimal_control_prompt,
    summarize_result_for_followup,
)
from dicom_overlay.domain.entities import (
    AnalysisResult,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    Severity,
)


def test_initial_analysis_prompt_contains_structured_interpretation_protocol():
    prompt = build_initial_analysis_prompt(
        modality=Modality.EKG,
        valid_regions=["lead_I", "rhythm_strip"],
        skill_name="dicom-ekg-analysis",
        skill_prompt="EKG skill instructions",
    )

    assert "systematic image interpretation protocol" in prompt
    assert "image quality" in prompt
    assert "bboxes" in prompt
    assert "label" in prompt
    assert "detail" in prompt
    assert "next_steps" in prompt
    assert "lead_I, rhythm_strip" in prompt
    assert "Return a single JSON object only" in prompt
    assert "exactly match the accepted boxes" in prompt


def test_initial_prompt_binds_matched_waveform_tool_without_granting_bboxes():
    prompt = build_initial_analysis_prompt(
        modality=Modality.EKG,
        valid_regions=["lead_I"],
        skill_name="dicom-ekg-analysis",
        skill_prompt="EKG skill instructions",
        waveform_artifact_id="wf-opaque-123",
        waveform_lead_mode="12_lead",
        waveform_evidence_nonce="a" * 32,
    )

    assert "ecg_founder_analyze_waveform exactly once" in prompt
    assert "never call it again for this nonce" in prompt
    assert "duplicate attempts are suppressed" in prompt
    assert "artifact_id='wf-opaque-123'" in prompt
    assert f"evidence_nonce='{'a' * 32}'" in prompt
    assert "uncalibrated_score is neither a positive nor a negative" in prompt
    assert "normal/otherwise-normal label" in prompt
    assert "omission of a condition from top-k" in prompt
    assert "visually supported, visually unsupported, or not assessable" in prompt
    assert "ranked labels to route visual checks" in prompt
    assert "high versus low voltage" in prompt
    assert "Irregular R-R timing alone cannot diagnose atrial fibrillation" in prompt
    assert "top-three candidate is PVC/PAC/ectopy" in prompt
    assert "unrounded heart_rate_bpm_from_median_rr" in prompt
    assert "has no image localization" in prompt


def test_coarse_prompt_is_compact_triage_with_bound_tools() -> None:
    prompt = build_coarse_analysis_prompt(
        modality=Modality.EKG,
        valid_regions=["lead_I", "lead_II"],
        waveform_artifact_id="wf-opaque-123",
        waveform_lead_mode="12_lead",
        waveform_evidence_nonce="a" * 32,
        bbox_source_image_sha256="b" * 64,
        bbox_evidence_nonce="c" * 32,
    )

    assert "TRIAGE" in prompt
    assert "checklist={}" in prompt
    assert "at most three" in prompt
    assert "ecg_founder_analyze_waveform exactly once" in prompt
    assert "max_predictions=5" in prompt
    assert "top-k omission is not negative evidence" in prompt
    assert "dicom_bbox_validate exactly once" in prompt
    assert "accepted=[]" in prompt
    assert "never return a rejected coordinate" in prompt
    assert "lead_order" in prompt
    assert '"leads":[]' in prompt
    assert "do not output per-lead bboxes" in prompt
    assert "Do not call sinus from regular timing alone" in prompt
    assert "High voltage alone cannot establish definite LVH" in prompt
    assert "missing calibration pulse prevents a definite LVH claim" in prompt
    assert "standard ECG grid and appropriate labeled leads" in prompt
    assert "more than one qualifying lead group" in prompt
    assert "secondary discordant ST-T/strain, axis deviation" in prompt
    assert "do not suppress the candidate solely because" in prompt
    assert "'Possible LVH-compatible pattern'" in prompt
    assert "do not automatically force warning" in prompt
    assert "report R-wave progression independently" in prompt
    assert "classify PR qualitatively" in prompt
    assert "premature P-QRS complexes" in prompt
    assert "tall or broad T waves" in prompt
    assert "never rhythm_strip" in prompt
    assert "under 2200 characters" in prompt
    assert "Normal/WNL is valid" in prompt
    assert "never emit urgent/emergent" in prompt
    assert "full modality checklist" in prompt
    assert "three consecutive broad QRS complexes" in prompt
    assert "NSVT/VT versus artifact" in prompt
    assert "16 keys" not in prompt


def test_non_ekg_coarse_prompt_omits_lvh_balance_contract() -> None:
    prompt = build_coarse_analysis_prompt(
        modality=Modality.CXR,
        valid_regions=["left_lung", "right_lung"],
    )

    assert "Possible LVH-compatible pattern" not in prompt
    assert "calibration pulse prevents a definite LVH claim" not in prompt


def test_minimal_control_prompt_keeps_only_json_envelope_and_single_look() -> None:
    prompt = build_minimal_control_prompt(
        modality=Modality.EKG,
        valid_regions=["lead_I", "lead_II"],
    )

    assert "minimal-control" in prompt
    assert "do not call tools" in prompt
    assert "Required top-level keys" in prompt
    assert "lead_I, lead_II" in prompt
    assert "systematic image interpretation protocol" not in prompt
    assert "dicom_bbox_validate" not in prompt


def test_followup_prompt_carries_image_context_and_prior_result():
    result = AnalysisResult(
        modality=Modality.EKG,
        summary="ST elevation in anterior leads",
        severity=Severity.CRITICAL,
        findings=[
            Finding(
                id="f1",
                regions=["lead_I"],
                label="ST Elevation",
                detail="ST elevation > 2 mm",
                severity=Severity.CRITICAL,
                bboxes=[RegionRect(x=0.1, y=0.2, w=0.3, h=0.1)],
            )
        ],
        checklist={"stemi": ChecklistItem(value="present", status=Severity.CRITICAL)},
        model_used="smoke-model",
    )
    context = InterpretationContext.from_result(result)

    prompt = build_followup_prompt(
        user_question="Which area should I look at first?",
        context=context,
    )

    assert "same attached medical image" in prompt
    assert "ST elevation in anterior leads" in prompt
    assert "ST Elevation" in prompt
    assert "Which area should I look at first?" in prompt
    assert "Do not invent findings" in prompt


def test_summarize_result_for_followup_is_compact_and_label_oriented():
    result = AnalysisResult(
        modality=Modality.CXR,
        summary="Right lower lobe consolidation",
        severity=Severity.WARNING,
        findings=[
            Finding(
                id="cxr1",
                regions=["right_lower_lung"],
                label="Consolidation",
                detail="Air bronchograms present",
                severity=Severity.WARNING,
            )
        ],
        checklist={},
    )

    text = summarize_result_for_followup(result)

    assert "CXR" in text
    assert "Right lower lobe consolidation" in text
    assert "Consolidation" in text
    assert "right_lower_lung" in text
