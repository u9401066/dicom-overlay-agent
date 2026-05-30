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
) -> str:
    """Build the initial structured analysis prompt for an attached image."""
    allowed_regions = ", ".join(valid_regions) if valid_regions else "(none provided)"
    return (
        f"Use the {skill_name} instructions below to analyze the attached image.\n\n"
        f"{skill_prompt}\n\n"
        "Run this systematic image interpretation protocol:\n"
        "1. Confirm modality and image quality before interpreting.\n"
        "2. Inspect the image systematically using the modality checklist.\n"
        "3. Report only findings visible in the image.\n"
        "4. For every abnormal finding, include label, detail, severity, regions, "
        "and bboxes with normalized 0-1 coordinates (x, y, w, h).\n"
        "5. Provide next_steps that explain what the user should inspect next.\n"
        "6. Use cautious medical language and do not overstate certainty.\n\n"
        "Return a single JSON object only. Do not wrap it in markdown.\n"
        f"modality must be '{modality.value}'.\n"
        f"Only reference region names from this allow-list: {allowed_regions}.\n"
        "Required top-level keys: modality, summary, severity, findings, "
        "checklist, next_steps, image_quality, model_used.\n"
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
