"""Structured regional follow-up contract tests."""

from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from dicom_overlay.application.review_chat import (
    build_region_review_prompt,
    match_selected_finding,
    parse_region_review_response,
)
from dicom_overlay.domain.entities import (
    Finding,
    FindingOp,
    RegionRect,
    Severity,
)
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
from dicom_overlay.infrastructure.screen_monitor import ImageProcessor


def _finding(
    *,
    finding_id: str = "f1",
    label: str = "ST elevation",
    box: RegionRect | None = None,
) -> Finding:
    return Finding(
        id=finding_id,
        regions=["lead_V2"],
        label=label,
        detail="Visible J-point elevation.",
        severity=Severity.WARNING,
        bboxes=[box or RegionRect(0.2, 0.3, 0.1, 0.1)],
        confidence="medium",
    )


def test_reviewer_drawn_prompt_allows_only_none_or_add() -> None:
    region = RegionRect(0.1, 0.2, 0.3, 0.4)

    prompt = build_region_review_prompt(
        user_question="Is this abnormal?",
        prior_context="EKG normal",
        selected_region=region,
        selected_finding=None,
        local_signal_audit={"status": "ok", "low_signal": False},
    )

    assert "proposal.op may be 'none' or 'add'" in prompt
    assert '"coordinate_space": "normalized_original_roi"' in prompt
    assert '"low_signal": false' in prompt
    assert "Do not return coordinates" in prompt


def test_parse_add_binds_app_selected_box_and_ignores_model_coordinates() -> None:
    region = RegionRect(0.1, 0.2, 0.3, 0.4)
    raw = json.dumps(
        {
            "answer": "There is a localized waveform abnormality.",
            "proposal": {
                "op": "add",
                "label": "Localized ST-T change",
                "detail": "Subtle repolarization morphology in the selected crop.",
                "severity": "info",
                "confidence": "low",
                "question": "Can this be confirmed at source resolution?",
                "note": "Crop-scoped re-check",
                "bboxes": [{"x": 0.8, "y": 0.8, "w": 0.1, "h": 0.1}],
            },
        }
    )

    parsed = parse_region_review_response(
        raw,
        selected_region=region,
        selected_finding=None,
        new_finding_id="review-1",
        local_signal_audit={"status": "ok", "low_signal": False},
    )

    assert parsed.delta is not None
    assert parsed.delta.op is FindingOp.ADD
    assert parsed.delta.finding.id == "review-1"
    assert parsed.delta.finding.bboxes == [region]
    assert parsed.delta.finding.regions == []
    assert parsed.delta.finding.source == "interactive_ai_review"
    assert "Add: Localized ST-T change" in parsed.proposal_summary


def test_parse_revise_preserves_existing_identity_and_geometry() -> None:
    selected = _finding()
    clicked = RegionRect(0.201, 0.301, 0.1, 0.1)
    raw = json.dumps(
        {
            "answer": "The crop supports a more urgent description.",
            "proposal": {
                "op": "revise",
                "label": "Anterior ST elevation",
                "detail": "Contiguous elevation is visible.",
                "severity": "critical",
                "confidence": "high",
                "question": "",
                "note": "Re-read of selected crop",
            },
        }
    )

    parsed = parse_region_review_response(
        raw,
        selected_region=clicked,
        selected_finding=selected,
        new_finding_id="unused",
        local_signal_audit={"status": "ok", "low_signal": False},
    )

    assert parsed.delta is not None
    assert parsed.delta.op is FindingOp.REVISE
    assert parsed.delta.finding.id == selected.id
    assert parsed.delta.finding.bboxes == selected.bboxes
    assert parsed.delta.finding.regions == selected.regions
    assert parsed.delta.finding.severity is Severity.CRITICAL


def test_parse_retract_targets_existing_finding_only() -> None:
    selected = _finding()
    raw = '{"answer":"Not supported.","proposal":{"op":"retract"}}'

    parsed = parse_region_review_response(
        raw,
        selected_region=selected.bboxes[0],
        selected_finding=selected,
        new_finding_id="unused",
    )

    assert parsed.delta is not None
    assert parsed.delta.op is FindingOp.RETRACT
    assert parsed.delta.finding is selected


def test_out_of_scope_operation_keeps_answer_but_has_no_delta() -> None:
    raw = '{"answer":"No change.","proposal":{"op":"retract"}}'

    parsed = parse_region_review_response(
        raw,
        selected_region=RegionRect(0.1, 0.1, 0.2, 0.2),
        selected_finding=None,
        new_finding_id="review-1",
    )

    assert parsed.answer == "No change."
    assert parsed.delta is None
    assert "outside" in parsed.warning


def test_blank_crop_mechanical_gate_blocks_add_writeback() -> None:
    image = Image.new("RGB", (300, 120), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    audit = {
        "status": "ok",
        **ImageProcessor().image_quality_profile(buffer.getvalue()),
    }
    raw = json.dumps(
        {
            "answer": "No visible waveform evidence is present.",
            "proposal": {
                "op": "add",
                "label": "Unsupported candidate",
                "detail": "This should not be written back.",
                "severity": "info",
            },
        }
    )

    parsed = parse_region_review_response(
        raw,
        selected_region=RegionRect(0.2, 0.2, 0.2, 0.2),
        selected_finding=None,
        new_finding_id="review-blank",
        local_signal_audit=audit,
    )

    assert audit["low_signal"] is True
    assert parsed.delta is None
    assert "local-signal gate" in parsed.warning


def test_missing_signal_audit_fails_closed_for_add() -> None:
    raw = json.dumps(
        {
            "answer": "Candidate.",
            "proposal": {
                "op": "add",
                "label": "Candidate",
                "detail": "Candidate detail.",
                "severity": "info",
            },
        }
    )

    parsed = parse_region_review_response(
        raw,
        selected_region=RegionRect(0.2, 0.2, 0.2, 0.2),
        selected_finding=None,
        new_finding_id="review-no-audit",
    )

    assert parsed.delta is None
    assert "local-signal gate" in parsed.warning


def test_fenced_or_plain_response_degrades_without_writeback() -> None:
    fenced = """```json
{"answer":"Within normal range.","proposal":{"op":"none"}}
```"""
    parsed = parse_region_review_response(
        fenced,
        selected_region=RegionRect(0.1, 0.1, 0.2, 0.2),
        selected_finding=None,
        new_finding_id="review-1",
    )
    plain = parse_region_review_response(
        "Image is insufficient for this conclusion.",
        selected_region=RegionRect(0.1, 0.1, 0.2, 0.2),
        selected_finding=None,
        new_finding_id="review-2",
    )

    assert parsed.answer == "Within normal range."
    assert parsed.delta is None
    assert plain.answer.startswith("Image is insufficient")
    assert plain.delta is None


def test_match_selected_finding_uses_label_then_original_roi_iou() -> None:
    first = _finding(finding_id="f1", box=RegionRect(0.1, 0.1, 0.2, 0.2))
    second = _finding(finding_id="f2", box=RegionRect(0.6, 0.6, 0.2, 0.2))

    matched = match_selected_finding(
        [first, second],
        label="ST elevation",
        selected_region=RegionRect(0.61, 0.61, 0.18, 0.18),
    )

    assert matched is second


def test_clicked_box_with_unmatched_label_does_not_bind_another_finding() -> None:
    matched = match_selected_finding(
        [_finding(label="ST elevation")],
        label="Different visible label",
        selected_region=RegionRect(0.2, 0.3, 0.1, 0.1),
    )

    assert matched is None


def test_unmatched_clicked_box_is_read_only_not_add_scope() -> None:
    raw = json.dumps(
        {
            "answer": "Read-only answer.",
            "proposal": {
                "op": "add",
                "label": "Candidate",
                "detail": "Must not be added.",
                "severity": "info",
            },
        }
    )

    parsed = parse_region_review_response(
        raw,
        selected_region=RegionRect(0.2, 0.3, 0.1, 0.1),
        selected_finding=None,
        new_finding_id="review-read-only",
        local_signal_audit={"status": "ok", "low_signal": False},
        allow_add=False,
    )

    assert parsed.delta is None
    assert "outside" in parsed.warning


@pytest.mark.asyncio
async def test_openclaw_regional_review_uses_complete_prompt_without_prose_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = OpenClawClient(gateway_url="ws://127.0.0.1:1")
    sender = AsyncMock(return_value='{"answer":"ok","proposal":{"op":"none"}}')
    monkeypatch.setattr(client, "_chat_about_image_prompt", sender)
    prompt = "RETURN_EXACT_REVIEW_JSON"

    answer = await client.review_region_about_image(
        prompt,
        image_base64="ZmFrZQ==",
    )

    assert '"answer":"ok"' in answer
    sender.assert_awaited_once_with(prompt, image_base64="ZmFrZQ==")
