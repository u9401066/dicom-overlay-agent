"""Core 2 robustness tests — live validation, retry, prose JSON, image guard.

Covers the hardening fixes for the OpenClaw interpretation harness:
  1. Live results get marked ``incomplete`` when schema checks warn.
  2. Transient inference timeouts get one backoff retry before ERROR.
  3. Prose-wrapped JSON responses are recovered via brace extraction.
  5. Oversized ROI images are downscaled before send.
  6. Out-of-bounds bboxes are dropped (not crashed on) and degrade gracefully.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from dicom_overlay.domain.entities import (
    AnalysisResult,
    AppConfig,
    ChecklistItem,
    Modality,
    Severity,
)
from dicom_overlay.domain.hooks import AnalyzeRequest
from dicom_overlay.infrastructure.hooks.output_validator import OutputValidator
from dicom_overlay.infrastructure.openclaw_client import (
    OpenClawClient,
    _extract_first_json_object,
    _payload_from_chat_event,
)
from dicom_overlay.infrastructure.screen_monitor import ImageProcessor


def _png_bytes(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), (123, 200, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _signal_png_bytes(width: int = 300, height: int = 180) -> bytes:
    img = Image.new("RGB", (width, height), "white")
    pixels = img.load()
    for x in range(40, 240):
        y = 70 + ((x - 40) % 40) // 5
        for dy in range(-2, 3):
            pixels[x, y + dy] = (0, 0, 0)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _bare_client() -> OpenClawClient:
    client = OpenClawClient.__new__(OpenClawClient)
    client._url = "ws://test"
    client._timeout = 5
    client._inference_timeout = 5
    client._connect_timeout = 5
    client._reconnect_interval = 1
    client._ws = None
    client._connected = False
    client._request_counter = 0
    client._gateway_token = "test-token"
    return client


@pytest.mark.asyncio
async def test_openclaw_client_disables_keepalive_during_long_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeWebSocket:
        async def close(self) -> None:
            return None

    async def fake_connect(url: str, **kwargs: object) -> FakeWebSocket:
        captured["url"] = url
        captured.update(kwargs)
        return FakeWebSocket()

    async def fake_handshake(self: OpenClawClient) -> None:
        return None

    monkeypatch.setattr(
        "dicom_overlay.infrastructure.openclaw_client.websockets.connect",
        fake_connect,
    )
    monkeypatch.setattr(OpenClawClient, "_handshake", fake_handshake)
    client = OpenClawClient(
        gateway_url="ws://127.0.0.1:18789",
        timeout_sec=120,
        gateway_token="test-token",
    )

    await client.connect()

    assert captured["ping_interval"] is None
    assert captured["ping_timeout"] is None


# ── Item 3: prose JSON fallback ──────────────────────────────────────


class TestProseJsonFallback:
    def test_extract_first_json_object_plain(self):
        assert _extract_first_json_object('{"a": 1}') == '{"a": 1}'

    def test_extract_first_json_object_with_prose(self):
        text = 'Here is the result: {"a": 1, "b": {"c": 2}} hope it helps!'
        assert _extract_first_json_object(text) == '{"a": 1, "b": {"c": 2}}'

    def test_extract_handles_braces_in_strings(self):
        text = 'prefix {"note": "a } brace", "x": 1} suffix'
        assert _extract_first_json_object(text) == '{"note": "a } brace", "x": 1}'

    def test_extract_returns_none_when_absent(self):
        assert _extract_first_json_object("no json here") is None

    def test_payload_from_chat_event_recovers_prose(self):
        payload = {
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": 'Sure! {"summary": "ok", "severity": "normal"} done',
                    }
                ]
            }
        }
        data = _payload_from_chat_event(payload)
        assert data["summary"] == "ok"
        assert data["severity"] == "normal"

    def test_payload_from_chat_event_repairs_numeric_quote_suffix(self):
        payload = {
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"summary":"ok","findings":[{"bboxes":[{"x":0.17",'
                            '"y":0.2,"w":0.1,"h":0.1}]}]}'
                        ),
                    }
                ]
            }
        }
        data = _payload_from_chat_event(payload)
        assert data["findings"][0]["bboxes"][0]["x"] == 0.17

    def test_payload_from_chat_event_raises_without_json(self):
        payload = {
            "message": {"content": [{"type": "text", "text": "no json at all"}]}
        }
        with pytest.raises(RuntimeError):
            _payload_from_chat_event(payload)


# ── Item 6: out-of-bounds bbox dropped, not crashed ──────────────────


class TestBboxDropping:
    def test_out_of_bounds_bbox_dropped(self, caplog):
        import logging

        client = _bare_client()
        payload = {
            "modality": "EKG",
            "summary": "finding present",
            "severity": "warning",
            "findings": [
                {
                    "id": "f1",
                    "label": "ST Elevation",
                    "regions": ["lead_II"],
                    "severity": "warning",
                    "bboxes": [
                        {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},  # valid
                        {"x": 1.5, "y": 0.1, "w": 0.2, "h": 0.2},  # out of bounds
                    ],
                }
            ],
            "checklist": {},
        }
        with caplog.at_level(logging.WARNING):
            result = client._parse_result(payload, elapsed_ms=100)
        # Finding kept, only the valid bbox survives
        assert len(result.findings) == 1
        assert len(result.findings[0].bboxes) == 1


# ── Regression: checklist returned as a list instead of a dict ───────


class TestChecklistAsList:
    """Models (e.g. for CXR) sometimes return ``checklist`` as a list rather
    than the expected object/dict. The parser must not crash with
    ``AttributeError: 'list' object has no attribute 'items'``.
    """

    def test_list_of_dicts_with_keys(self):
        client = _bare_client()
        payload = {
            "modality": "CXR",
            "summary": "clear lungs",
            "severity": "normal",
            "findings": [],
            "checklist": [
                {"key": "lungs", "value": "clear", "status": "normal"},
                {"name": "heart", "value": "normal size", "status": "normal"},
            ],
        }
        result = client._parse_result(payload, elapsed_ms=100)
        assert result.checklist["lungs"].value == "clear"
        assert result.checklist["lungs"].status is Severity.NORMAL
        assert result.checklist["heart"].value == "normal size"

    def test_list_of_scalars_gets_positional_keys(self):
        client = _bare_client()
        payload = {
            "modality": "CXR",
            "summary": "clear lungs",
            "severity": "normal",
            "findings": [],
            "checklist": ["lungs clear", "no effusion"],
        }
        result = client._parse_result(payload, elapsed_ms=100)
        assert result.checklist["item_0"].value == "lungs clear"
        assert result.checklist["item_1"].value == "no effusion"


# ── Item 1: live results marked incomplete on schema warnings ────────


def _make_request() -> AnalyzeRequest:
    return AnalyzeRequest(
        image_base64="ZmFrZQ==",
        modality=Modality.EKG,
        valid_regions=["lead_I", "lead_II"],
    )


def _full_ekg_checklist() -> dict[str, ChecklistItem]:
    keys = [
        "heart_rate", "rhythm", "regularity", "axis", "p_wave", "pr_interval",
        "qrs_duration", "qrs_morphology", "st_segment", "t_wave", "qtc_interval",
        "chamber_enlargement", "conduction", "av_block", "stemi_pattern", "ischemia",
    ]
    return {k: ChecklistItem(value="normal", status=Severity.NORMAL) for k in keys}


def _make_result() -> AnalysisResult:
    return AnalysisResult(
        modality=Modality.EKG,
        summary="Normal sinus rhythm",
        severity=Severity.NORMAL,
        findings=[],
        checklist=_full_ekg_checklist(),
    )


class TestIncompleteFlag:
    def test_missing_keys_marks_incomplete(self):
        validator = OutputValidator(strict=False)
        result = _make_result()
        del result.checklist["ischemia"]
        del result.checklist["stemi_pattern"]
        validated = validator.post_analyze(_make_request(), result)
        assert validated.incomplete is True
        assert validated.incomplete_reasons

    def test_complete_result_not_incomplete(self):
        validator = OutputValidator(strict=False)
        result = _make_result()
        validated = validator.post_analyze(_make_request(), result)
        assert validated.incomplete is False
        assert validated.incomplete_reasons == []


# ── Item 5: image size guard ─────────────────────────────────────────


class TestImageDownscale:
    def test_large_image_shrunk(self):
        proc = ImageProcessor()
        original = _png_bytes(3000, 2000)
        out = proc.downscale_to_max_edge(original, 1568)
        img = Image.open(io.BytesIO(out))
        assert max(img.size) == 1568

    def test_small_image_untouched(self):
        proc = ImageProcessor()
        original = _png_bytes(800, 600)
        out = proc.downscale_to_max_edge(original, 1568)
        assert out == original

    def test_zero_max_edge_disables(self):
        proc = ImageProcessor()
        original = _png_bytes(3000, 2000)
        assert proc.downscale_to_max_edge(original, 0) == original

    def test_image_quality_profile_flags_blank_low_signal_image(self):
        proc = ImageProcessor()
        profile = proc.image_quality_profile(_png_bytes(200, 100))

        assert profile["width_px"] == 200
        assert profile["height_px"] == 100
        assert profile["ink_pixel_ratio"] == 0.0
        assert profile["low_signal"] is True

    def test_image_quality_profile_detects_ink(self):
        buf = io.BytesIO()
        img = Image.new("RGB", (200, 100), "white")
        import PIL.ImageDraw

        draw = PIL.ImageDraw.Draw(img)
        draw.line((10, 50, 190, 50), fill="black", width=8)
        img.save(buf, format="PNG")

        profile = ImageProcessor().image_quality_profile(buf.getvalue())

        assert profile["ink_pixel_ratio"] > 0.01
        assert profile["low_signal"] is False

    def test_local_signal_candidates_detect_waveform_bbox(self):
        proc = ImageProcessor()
        profile = proc.local_signal_candidates(_signal_png_bytes())

        assert profile["candidate_count"] == 1
        candidate = profile["candidates"][0]
        assert candidate["label"] == "local_signal"
        assert 0.10 <= candidate["x"] <= 0.20
        assert 0.30 <= candidate["y"] <= 0.45
        assert 0.60 <= candidate["w"] <= 0.75
        assert candidate["confidence"] > 0.1

    def test_local_signal_candidates_handles_blank_image(self):
        proc = ImageProcessor()
        profile = proc.local_signal_candidates(_png_bytes(200, 100))

        assert profile["candidate_count"] == 0
        assert profile["candidates"] == []
        assert profile["low_signal"] is True


# ── Multi-pass cropper (ImageCropper protocol) ───────────────────────


class TestCropRegionBase64:
    def test_crop_is_subset_and_returns_png(self):
        import base64

        from dicom_overlay.domain.entities import RegionRect

        proc = ImageProcessor()
        src_b64 = proc.to_base64(_png_bytes(1000, 800))
        region = RegionRect(x=0.25, y=0.5, w=0.5, h=0.25)

        out_b64 = proc.crop_region_base64(src_b64, region)
        img = Image.open(io.BytesIO(base64.b64decode(out_b64)))

        # Cropped region is 500x200 source px; short edge (200) upscaled to 512.
        assert img.format == "PNG"
        assert min(img.size) >= 512

    def test_crop_clamps_out_of_range_region(self):
        import base64

        from dicom_overlay.domain.entities import RegionRect

        proc = ImageProcessor()
        src_b64 = proc.to_base64(_png_bytes(640, 480))
        # Region overflowing the image must clamp, never exceed source bounds.
        region = RegionRect(x=0.9, y=0.9, w=0.5, h=0.5)

        out_b64 = proc.crop_region_base64(src_b64, region)
        img = Image.open(io.BytesIO(base64.b64decode(out_b64)))
        assert img.size[0] >= 1 and img.size[1] >= 1


# ── Item 2: transient timeout retry ──────────────────────────────────


class _FlakyAnalyzer:
    """Times out N times, then returns a result."""

    def __init__(self, fail_times: int) -> None:
        self._fail_times = fail_times
        self.calls = 0

    async def analyze(self, image_b64, modality, valid_regions):
        self.calls += 1
        if self.calls <= self._fail_times:
            raise TimeoutError("transient")
        return AnalysisResult(
            modality=Modality.EKG,
            summary="ok",
            severity=Severity.NORMAL,
            findings=[],
            checklist={},
        )


def _make_agent(analyzer):
    from dicom_overlay.application.overlay_agent import OverlayAgent

    config = AppConfig()
    config.openclaw.analyze_retry_backoff_sec = 0.0  # no real sleep
    agent = OverlayAgent.__new__(OverlayAgent)
    agent._config = config
    agent._analyzer = analyzer
    return agent


class TestRetryBackoff:
    async def test_single_timeout_retried_then_succeeds(self):
        analyzer = _FlakyAnalyzer(fail_times=1)
        agent = _make_agent(analyzer)
        result = await agent._analyze_with_retry("img", Modality.EKG, [])
        assert result.summary == "ok"
        assert analyzer.calls == 2

    async def test_exhausted_retries_raise(self):
        analyzer = _FlakyAnalyzer(fail_times=5)
        agent = _make_agent(analyzer)
        with pytest.raises(TimeoutError):
            await agent._analyze_with_retry("img", Modality.EKG, [])
        # 1 initial + analyze_retries (default 1) = 2 attempts
        assert analyzer.calls == 2
