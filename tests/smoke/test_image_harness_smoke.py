from __future__ import annotations

import json

import pytest

import dicom_overlay.infrastructure.image_harness_smoke as harness_smoke
from dicom_overlay.infrastructure.image_harness_smoke import (
    run_image_harness_smoke,
)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_image_interpretation_harness_writes_log_and_result(tmp_path):
    result = await run_image_harness_smoke(output_dir=tmp_path, show_viewer=False)

    assert result.ok
    assert result.request_count == 2
    assert result.sample_image_path.exists()
    assert result.log_path.exists()
    assert result.result_path.exists()

    payload = json.loads(result.result_path.read_text(encoding="utf-8"))
    assert payload["summary"] == result.summary
    assert payload["findings"][0]["label"] == "ST elevation marker"
    assert payload["findings"][0]["bboxes"][0]["x"] == 0.014286
    assert len(payload["checklist"]) == 16
    assert payload["output_contract"] == {
        "analyzer": "HookedVisionAnalyzer",
        "validator": "OutputValidator",
        "strict": True,
    }
    assert payload["capture_contract"]["capture_rect"] == {
        "left": 30,
        "top": 30,
        "width": 840,
        "height": 540,
    }
    assert payload["capture_contract"]["captured_image_size"] == [840, 540]
    assert all(
        rect == payload["capture_contract"]["capture_rect"]
        for rect in payload["capture_contract"]["capture_rects"]
    )
    assert payload["harness_manifest"]["compatibility"]["minimumOpenClaw"] == (
        "2026.4.22"
    )

    log_text = result.log_path.read_text(encoding="utf-8")
    assert "DICOM Overlay image harness smoke" in log_text
    assert "viewer_displayed=False" in log_text
    assert "chat.send" in log_text
    assert "contentLength" in log_text
    assert "contentSha256" in log_text
    assert "<redacted>" in log_text


@pytest.mark.asyncio
@pytest.mark.integration
async def test_image_harness_strict_hook_rejects_layout_enum_drift(
    tmp_path,
    monkeypatch,
):
    payload = harness_smoke._mock_result_payload()
    payload["layout"]["format"] = "standard_4x3"
    monkeypatch.setattr(harness_smoke, "_mock_result_payload", lambda: payload)

    with pytest.raises(RuntimeError, match="Harness produced no result"):
        await run_image_harness_smoke(output_dir=tmp_path, show_viewer=False)
