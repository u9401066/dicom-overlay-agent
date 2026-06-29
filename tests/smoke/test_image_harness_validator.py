from __future__ import annotations

import json

import pytest

from dicom_overlay.infrastructure.image_harness_smoke import run_image_harness_smoke
from dicom_overlay.infrastructure.image_harness_validator import (
    verify_image_harness_artifacts,
)


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
