"""Regression tests for the Core 2 image-harness contract boundaries."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from dicom_overlay.domain.ekg_layout import STANDARD_EKG_LEADS
from dicom_overlay.domain.entities import (
    AnalysisResult,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    Severity,
    WindowRect,
)
from dicom_overlay.domain.hooks import AnalyzeRequest, HookError
from dicom_overlay.domain.modality_profile import default_registry
from dicom_overlay.infrastructure.eval_harness import EvalCase, score_case
from dicom_overlay.infrastructure.hooks.output_validator import (
    EKG_RESULT_LAYOUT_FORMATS,
    OutputValidator,
)
from dicom_overlay.infrastructure.image_harness_smoke import _HarnessScreenMonitor
from dicom_overlay.infrastructure.image_harness_validator import (
    verify_image_harness_artifacts,
)
from dicom_overlay.infrastructure.openclaw_runtime import build_openclaw_chat_frame


def _request() -> AnalyzeRequest:
    return AnalyzeRequest(
        image_base64="cHVibGljLXN5bnRoZXRpYy1pbWFnZQ==",
        modality=Modality.EKG,
        valid_regions=["lead_I"],
    )


def _valid_result() -> AnalysisResult:
    checklist = {
        key: ChecklistItem(value="assessed", status=Severity.NORMAL)
        for key in default_registry().resolve("EKG").checklist_keys
    }
    return AnalysisResult(
        modality=Modality.EKG,
        summary="Synthetic contract result.",
        severity=Severity.NORMAL,
        findings=[],
        checklist=checklist,
        image_quality="Synthetic image is readable.",
        next_steps=["Review the original synthetic image."],
        layout={
            "format": "12lead_3x4",
            "rhythm_strip_leads": [],
            "leads": [
                {
                    "name": name,
                    "label_visible": True,
                    "bbox": [
                        (index % 4) / 4,
                        (index // 4) / 3,
                        0.25,
                        1 / 3,
                    ],
                }
                for index, name in enumerate(STANDARD_EKG_LEADS)
            ],
        },
    )


def test_strict_checklist_rejects_a_seventeenth_typo_key() -> None:
    result = _valid_result()
    result.checklist["st_segmet"] = ChecklistItem(
        value="typo",
        status=Severity.INFO,
    )

    with pytest.raises(HookError, match="unexpected keys: st_segmet"):
        OutputValidator(strict=True).post_analyze(_request(), result)


def test_strict_contract_rejects_non_schema_ekg_layout_format() -> None:
    result = _valid_result()
    result.layout["format"] = "standard_4x3"

    with pytest.raises(HookError, match="unsupported format: standard_4x3"):
        OutputValidator(strict=True).post_analyze(_request(), result)


def test_output_validator_layout_formats_track_openclaw_schema() -> None:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "openclaw"
        / "workspace"
        / "skills"
        / "dicom-ekg-analysis"
        / "schema.json"
    )
    schema = json.loads(schema_path.read_text("utf-8"))
    model_formats = set(schema["properties"]["layout"]["properties"]["format"]["enum"])

    assert model_formats == EKG_RESULT_LAYOUT_FORMATS
    lead_order = schema["properties"]["layout"]["properties"]["lead_order"]
    assert set(lead_order["items"]["enum"]) >= {
        "I",
        "II",
        "III",
        "aVR",
        "aVL",
        "aVF",
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
    }


@pytest.mark.parametrize("missing_field", ["image_quality", "next_steps"])
def test_strict_contract_rejects_missing_report_fields(missing_field: str) -> None:
    result = _valid_result()
    setattr(result, missing_field, "" if missing_field == "image_quality" else [])

    with pytest.raises(HookError, match=missing_field):
        OutputValidator(strict=True).post_analyze(_request(), result)


def test_strict_contract_rejects_zero_width_bbox() -> None:
    result = _valid_result()
    result.severity = Severity.WARNING
    result.findings = [
        Finding(
            id="zero-width",
            regions=["lead_I"],
            label="Invalid marker",
            detail="A zero-width marker must never reach the overlay.",
            severity=Severity.WARNING,
            bboxes=[RegionRect(x=0.1, y=0.1, w=0.0, h=0.1)],
        )
    ]

    with pytest.raises(HookError, match="zero-area or invalid"):
        OutputValidator(strict=True).post_analyze(_request(), result)
    assert result.findings[0].bboxes == []


def test_artifact_verifier_does_not_assemble_scattered_gateway_substrings(
    tmp_path,
) -> None:
    log_path = tmp_path / "harness.log"
    frames = [
        {
            "type": "req",
            "id": "connect-1",
            "method": "connect",
            "params": {},
        },
        {
            "type": "req",
            "id": "chat-2",
            "method": "chat.send",
            "params": {
                "sessionKey": "session",
                "message": "analyze",
                "idempotencyKey": "nonce",
            },
        },
        {
            "attachments": [
                {
                    "type": "image",
                    "mimeType": "image/png",
                    "content": "<redacted>",
                    "contentLength": 12,
                    "contentSha256": "0" * 64,
                }
            ]
        },
    ]
    log_path.write_text("\n".join(json.dumps(frame) for frame in frames), "utf-8")
    result_path = tmp_path / "result.json"
    result_path.write_text("{}", "utf-8")

    verification = verify_image_harness_artifacts(
        log_path=log_path,
        result_path=result_path,
        require_viewer=False,
    )

    assert "gateway_contract" not in verification.passed_checks
    assert "image_payload_proof" not in verification.passed_checks


@pytest.mark.parametrize("empty_image", ["", "   ", "\r\n"])
def test_chat_frame_rejects_empty_image_attachment(empty_image: str) -> None:
    with pytest.raises(ValueError, match="image_base64"):
        build_openclaw_chat_frame(
            request_id="chat-1",
            session_key="session-1",
            message="analyze",
            idempotency_key="nonce-1",
            image_base64=empty_image,
        )


def test_smoke_monitor_captures_exact_requested_roi() -> None:
    source = Image.new("RGB", (900, 600), "blue")
    source.putpixel((30, 40), (255, 0, 0))
    source_bytes = io.BytesIO()
    source.save(source_bytes, format="PNG")
    monitor = _HarnessScreenMonitor(source_bytes.getvalue())
    requested = WindowRect(left=30, top=40, width=120, height=80)

    captured_bytes = monitor.capture_region(requested)

    with Image.open(io.BytesIO(captured_bytes)) as captured:
        assert captured.size == (120, 80)
        assert captured.getpixel((0, 0)) == (255, 0, 0)
    assert monitor.captured_rects == [requested]
    assert monitor.last_capture_size == (120, 80)


def test_eval_schema_gate_preserves_rejected_bbox_evidence(tmp_path) -> None:
    image_path = tmp_path / "synthetic.png"
    image_path.write_bytes(b"\x89PNG\r\n")
    case = EvalCase(
        image_path=image_path,
        modality=Modality.CXR,
        expected_severity=Severity.WARNING,
        expected_keywords=(),
        label="zero-width",
    )
    rejected = RegionRect(x=0.2, y=0.2, w=0.0, h=0.3)
    result = AnalysisResult(
        modality=Modality.CXR,
        summary="Synthetic bbox contract case.",
        severity=Severity.WARNING,
        findings=[
            Finding(
                id="zero-width",
                regions=[],
                label="Invalid marker",
                detail="A zero-width marker must fail bbox scoring.",
                severity=Severity.WARNING,
                bboxes=[rejected],
            )
        ],
        checklist={
            key: ChecklistItem(value="assessed", status=Severity.NORMAL)
            for key in default_registry().resolve("CXR").checklist_keys
        },
        image_quality="Synthetic image is readable.",
        next_steps=["Review the original synthetic image."],
    )

    score = score_case(case, result, latency_ms=0)

    assert score.bbox_in_bounds is False
    assert result.findings[0].bboxes == [rejected]
