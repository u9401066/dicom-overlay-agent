"""Private host adapter for the public medical-image prompting harness.

The public package owns the scientific protocol and prompt-injection boundary.
This adapter supplies only product-specific OpenClaw tool names while preserving
the original ``dicom_overlay`` import path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from medical_image_harness.prompting import (
    InterpretationContext,
    build_followup_prompt,
    build_minimal_control_prompt,
    summarize_result_for_followup,
)
from medical_image_harness.prompting import (
    build_initial_analysis_prompt as _build_public_initial_analysis_prompt,
)

if TYPE_CHECKING:
    from medical_image_harness.models import Modality


def build_initial_analysis_prompt(
    *,
    modality: Modality,
    valid_regions: list[str],
    skill_name: str,
    skill_prompt: str,
    waveform_artifact_id: str = "",
    waveform_lead_mode: str = "",
    waveform_evidence_nonce: str = "",
    bbox_source_image_sha256: str = "",
    bbox_evidence_nonce: str = "",
    host_contract_context: dict[str, object] | None = None,
) -> str:
    """Build a public protocol prompt with private OpenClaw tool adapters."""

    localization_is_bound = bool(bbox_source_image_sha256 and bbox_evidence_nonce)
    return _build_public_initial_analysis_prompt(
        modality=modality,
        valid_regions=valid_regions,
        skill_name=skill_name,
        skill_prompt=skill_prompt,
        waveform_artifact_id=waveform_artifact_id,
        waveform_lead_mode=waveform_lead_mode,
        waveform_evidence_nonce=waveform_evidence_nonce,
        waveform_tool_name=(
            "ecg_founder_analyze_waveform" if waveform_artifact_id else ""
        ),
        bbox_source_image_sha256=bbox_source_image_sha256,
        bbox_evidence_nonce=bbox_evidence_nonce,
        localization_tool_name=("dicom_bbox_validate" if localization_is_bound else ""),
        host_contract_context=host_contract_context,
    )


__all__ = [
    "InterpretationContext",
    "build_followup_prompt",
    "build_initial_analysis_prompt",
    "build_minimal_control_prompt",
    "summarize_result_for_followup",
]
