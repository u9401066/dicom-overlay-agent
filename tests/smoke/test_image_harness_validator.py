from __future__ import annotations

import json

import pytest

from dicom_overlay.domain.modality_profile import default_registry
from dicom_overlay.infrastructure.image_harness_smoke import run_image_harness_smoke
from dicom_overlay.infrastructure.image_harness_validator import (
    verify_image_harness_artifacts,
)


def _valid_output_and_capture_contract() -> dict:
    leads = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")
    return {
        "modality": "EKG",
        "model_used": "mock-openclaw-harness",
        "layout": {
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
                for index, name in enumerate(leads)
            ],
        },
        "image_quality": "Synthetic image is readable.",
        "next_steps": ["Review the original synthetic image."],
        "incomplete": False,
        "incomplete_reasons": [],
        "checklist": {
            key: {"value": "assessed", "status": "normal"}
            for key in default_registry().resolve("EKG").checklist_keys
        },
        "output_contract": {
            "analyzer": "HookedVisionAnalyzer",
            "validator": "OutputValidator",
            "strict": True,
        },
        "capture_contract": {
            "viewer_rect": {
                "left": 0,
                "top": 0,
                "width": 900,
                "height": 600,
            },
            "capture_rect": {
                "left": 30,
                "top": 30,
                "width": 840,
                "height": 540,
            },
            "capture_rects": [
                {
                    "left": 30,
                    "top": 30,
                    "width": 840,
                    "height": 540,
                }
            ],
            "captured_image_size": [840, 540],
        },
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_codex_verifier_accepts_valid_harness_artifacts(tmp_path):
    smoke = await run_image_harness_smoke(output_dir=tmp_path, show_viewer=False)

    verification = verify_image_harness_artifacts(
        log_path=smoke.log_path,
        result_path=smoke.result_path,
        require_viewer=False,
    )

    assert verification.ok
    assert "gateway_contract" in verification.passed_checks
    assert "image_payload_proof" in verification.passed_checks
    assert "overlay_annotation_contract" in verification.passed_checks


@pytest.mark.asyncio
@pytest.mark.integration
async def test_codex_verifier_rejects_unredacted_image_payload(tmp_path):
    smoke = await run_image_harness_smoke(output_dir=tmp_path, show_viewer=False)
    text = smoke.log_path.read_text(encoding="utf-8")
    smoke.log_path.write_text(
        text.replace('"content": "<redacted>"', '"content": "iVBORw0KGgoAAA"'),
        encoding="utf-8",
    )

    verification = verify_image_harness_artifacts(
        log_path=smoke.log_path,
        result_path=smoke.result_path,
        require_viewer=False,
    )

    assert not verification.ok
    assert any("unredacted" in failure for failure in verification.failures)


def test_codex_verifier_rejects_bbox_extent_overflow(tmp_path):
    log_path = tmp_path / "harness.log"
    log_path.write_text(
        "\n".join(
            [
                '{"type":"req","id":"connect-1","method":"connect","params":{}}',
                (
                    '{"type":"req","id":"chat-2","method":"chat.send",'
                    '"params":{"sessionKey":"session","message":"analyze",'
                    '"idempotencyKey":"nonce","attachments": '
                    '[{"type":"image","mimeType": "image/png", "content": "<redacted>", '
                    '"contentLength": 123, "contentSha256": '
                    '"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}]}}'
                ),
                "viewer_displayed=False",
            ]
        ),
        encoding="utf-8",
    )
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                **_valid_output_and_capture_contract(),
                "findings": [
                    {
                        "label": "overflow",
                        "detail": "bbox spills past the right edge",
                        "regions": ["lead_I"],
                        "bboxes": [{"x": 0.9, "y": 0.1, "w": 0.2, "h": 0.2}],
                    }
                ],
                "harness_manifest": {
                    "compatibility": {
                        "minimumOpenClaw": "2026.4.22",
                        "gatewayProtocol": {"methods": ["connect", "chat.send"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    verification = verify_image_harness_artifacts(
        log_path=log_path,
        result_path=result_path,
        require_viewer=False,
    )

    assert not verification.ok
    assert "overlay_annotation_contract" not in verification.passed_checks


def test_codex_verifier_accepts_near_boundary_bbox_with_float_rounding(tmp_path):
    log_path = tmp_path / "harness.log"
    log_path.write_text(
        "\n".join(
            [
                '{"type":"req","id":"connect-1","method":"connect","params":{}}',
                (
                    '{"type":"req","id":"chat-2","method":"chat.send",'
                    '"params":{"sessionKey":"session","message":"analyze",'
                    '"idempotencyKey":"nonce","attachments": '
                    '[{"type":"image","mimeType": "image/png", "content": "<redacted>", '
                    '"contentLength": 123, "contentSha256": '
                    '"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}]}}'
                ),
                "viewer_displayed=False",
            ]
        ),
        encoding="utf-8",
    )
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                **_valid_output_and_capture_contract(),
                "findings": [
                    {
                        "label": "boundary",
                        "detail": "bbox ends at the right and bottom edge",
                        "regions": ["lead_I"],
                        "bboxes": [{"x": 0.1, "y": 0.2, "w": 0.9, "h": 0.8}],
                    }
                ],
                "harness_manifest": {
                    "compatibility": {
                        "minimumOpenClaw": "2026.4.22",
                        "gatewayProtocol": {"methods": ["connect", "chat.send"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    verification = verify_image_harness_artifacts(
        log_path=log_path,
        result_path=result_path,
        require_viewer=False,
    )

    assert verification.ok
    assert "overlay_annotation_contract" in verification.passed_checks


def test_codex_verifier_checks_all_findings_not_only_first(tmp_path):
    log_path = tmp_path / "harness.log"
    log_path.write_text(
        "\n".join(
            [
                '{"method": "connect"}',
                (
                    '{"method": "chat.send", "params": {"attachments": '
                    '[{"mimeType": "image/png", "content": "<redacted>", '
                    '"contentLength": 123, "contentSha256": '
                    '"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}]}}'
                ),
                "viewer_displayed=False",
            ]
        ),
        encoding="utf-8",
    )
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "label": "valid first finding",
                        "detail": "valid first detail",
                        "regions": ["lead_I"],
                        "bboxes": [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}],
                    },
                    {
                        "label": "invalid second finding",
                        "detail": "second finding spills outside the image",
                        "regions": ["lead_II"],
                        "bboxes": [{"x": 0.9, "y": 0.1, "w": 0.2, "h": 0.2}],
                    },
                ],
                "harness_manifest": {
                    "compatibility": {
                        "minimumOpenClaw": "2026.4.22",
                        "gatewayProtocol": {"methods": ["connect", "chat.send"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    verification = verify_image_harness_artifacts(
        log_path=log_path,
        result_path=result_path,
        require_viewer=False,
    )

    assert not verification.ok
    assert "overlay_annotation_contract" not in verification.passed_checks
