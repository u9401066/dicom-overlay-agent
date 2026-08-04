"""Prompt and context harness for medical image interpretation sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import AnalysisResult, Modality, Severity


@dataclass(frozen=True)
class InterpretationContext:
    """Compact state carried across multiple turns for the same image."""

    modality: Modality
    summary: str
    severity: Severity
    finding_summaries: list[str] = field(default_factory=list)
    model_used: str = ""

    @classmethod
    def from_result(cls, result: AnalysisResult) -> InterpretationContext:
        return cls(
            modality=result.modality,
            summary=result.summary,
            severity=result.severity,
            finding_summaries=[
                (
                    f"{finding.id}: {finding.label} "
                    f"({finding.severity.value}; regions={','.join(finding.regions)}) "
                    f"- {finding.detail}"
                )
                for finding in result.findings
            ],
            model_used=result.model_used,
        )


def build_initial_analysis_prompt(
    *,
    modality: Modality,
    valid_regions: list[str],
    skill_name: str,
    skill_prompt: str,
    waveform_artifact_id: str = "",
    waveform_lead_mode: str = "",
    waveform_evidence_nonce: str = "",
) -> str:
    """Build the initial structured analysis prompt for an attached image."""
    allowed_regions = ", ".join(valid_regions) if valid_regions else "(none provided)"
    waveform_protocol = ""
    if waveform_artifact_id:
        waveform_protocol = (
            "\nMatched raw-waveform evidence is available for this EKG case:\n"
            "- First inspect the attached image independently and form a provisional "
            "visual interpretation.\n"
            "- Then call ecg_founder_analyze_waveform exactly once with "
            f"artifact_id='{waveform_artifact_id}', "
            f"lead_mode='{waveform_lead_mode or '12_lead'}', and "
            f"evidence_nonce='{waveform_evidence_nonce}', and max_predictions=10. "
            "Do not alter or invent the artifact id or evidence nonce.\n"
            "- Treat returned probabilities only as supporting waveform evidence. "
            "An uncalibrated_score is neither a positive nor a negative diagnosis.\n"
            "- Explicitly reconcile agreement or disagreement in the summary and "
            "retain uncertainty when the image and waveform evidence differ.\n"
            "- ECGFounder has no image localization. Every finding bbox must still "
            "be grounded in the attached image and validated by dicom_bbox_validate.\n"
        )
    return (
        f"Use the {skill_name} instructions below to analyze the attached image.\n\n"
        f"{skill_prompt}\n\n"
        "Run this systematic image interpretation protocol:\n"
        "1. Confirm modality and image quality before interpreting.\n"
        "2. Inspect the image systematically using the modality checklist.\n"
        "3. Report only findings visible in the image.\n"
        "4. Put normal and negative observations in summary/checklist, not in "
        "overlay findings. For every abnormal or unresolved finding, include "
        "label, detail, severity, regions, and tight bboxes with normalized 0-1 "
        "coordinates (x, y, w, h).\n"
        "5. Before finalizing any abnormal or uncertain bbox, call the "
        "dicom_bbox_validate tool with modality set to the requested modality, "
        "and copy only its accepted full-image boxes "
        "into the corresponding finding. Never substitute crop-local coordinates.\n"
        "6. Provide next_steps that explain what the user should inspect next.\n"
        "7. A normal or within-normal-limits interpretation is valid; never invent "
        "an abnormality merely to return a finding.\n"
        "8. For a non-urgent unresolved candidate, set severity to info, confidence "
        "to low, include a tight bbox, and provide a concrete question for human "
        "review. If the unresolved differential is time-critical, severity is the "
        "triage priority rather than diagnostic certainty: use critical with "
        "cautious wording, confidence, and a concrete urgent-review question. Do "
        "not phrase an uncertain candidate as a confirmed diagnosis.\n"
        "9. Set incomplete=true and list incomplete_reasons when image quality, "
        "labels, or captured leads are insufficient.\n"
        "10. Use cautious medical language and do not overstate certainty.\n\n"
        f"{waveform_protocol}"
        "Return a single JSON object only. Do not wrap it in markdown.\n"
        f"modality must be '{modality.value}'.\n"
        f"Only reference region names from this allow-list: {allowed_regions}.\n"
        "Required top-level keys: modality, summary, severity, findings, "
        "checklist, layout, next_steps, image_quality, model_used, incomplete, "
        "incomplete_reasons.\n"
    )


def build_minimal_control_prompt(
    *,
    modality: Modality,
    valid_regions: list[str],
) -> str:
    """Build the single-look control prompt with only a parseable JSON envelope."""

    allowed_regions = ", ".join(valid_regions) if valid_regions else "(none provided)"
    return (
        "Experimental minimal-control read. Inspect the attached medical image "
        "once and do not call tools or use external files. Return one JSON object "
        "only, without markdown. Do not invent an abnormality when the image is "
        "within normal limits.\n"
        f"modality must be '{modality.value}'.\n"
        f"Allowed region names: {allowed_regions}.\n"
        "Required top-level keys: modality, summary, severity, findings, "
        "checklist, layout, next_steps, image_quality, model_used, incomplete, "
        "incomplete_reasons. Each finding should include id, label, detail, "
        "severity, regions, and normalized 0-1 bboxes when localization is "
        "available."
    )


def build_followup_prompt(
    *,
    user_question: str,
    context: InterpretationContext,
) -> str:
    """Build a multi-turn prompt for questions about the same attached image."""
    finding_lines = "\n".join(context.finding_summaries) or "(no findings recorded)"
    return (
        "Answer the user's follow-up question about the same attached medical image.\n"
        "Use the prior structured interpretation as context, but re-check the image "
        "before answering. Do not invent findings that are not visible.\n\n"
        f"Prior modality: {context.modality.value}\n"
        f"Prior severity: {context.severity.value}\n"
        f"Prior summary: {context.summary}\n"
        f"Prior findings:\n{finding_lines}\n\n"
        f"User question: {user_question}\n\n"
        "Reply with concise clinical guidance, mention the relevant labels/regions, "
        "and say when the image is insufficient for the requested conclusion."
    )


def summarize_result_for_followup(result: AnalysisResult) -> str:
    """Create compact text context for log output and follow-up chat prompts."""
    context = InterpretationContext.from_result(result)
    findings = "; ".join(context.finding_summaries) or "no findings"
    return (
        f"{context.modality.value} {context.severity.value}: "
        f"{context.summary}. Findings: {findings}"
    )
