from __future__ import annotations

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
