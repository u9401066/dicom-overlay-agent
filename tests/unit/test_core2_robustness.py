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
import json
from pathlib import Path

import pytest
from PIL import Image

from dicom_overlay.domain.entities import (
    AnalysisResult,
    AppConfig,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.domain.hooks import AnalyzeRequest
from dicom_overlay.infrastructure.hooks.output_validator import OutputValidator
from dicom_overlay.infrastructure.openclaw_client import (
    OpenClawClient,
    _build_finalization_prompt,
    _build_refinement_prompt,
    _extract_first_json_object,
    _extract_tool_names,
    _load_gateway_token,
    _load_skill_prompt,
    _parse_refinement_result,
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
    client._base_dir = Path.cwd()
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


def test_openclaw_waveform_artifact_context_is_scoped_and_reset(tmp_path: Path) -> None:
    client = OpenClawClient(gateway_token="test", base_dir=tmp_path)

    assert client._waveform_artifact_context.get() is None
    with client.use_waveform_artifact("wf-opaque-123", lead_mode="12_lead"):
        assert client._waveform_artifact_context.get() == (
            "wf-opaque-123",
            "12_lead",
        )
    assert client._waveform_artifact_context.get() is None


def test_runtime_assets_resolve_from_bundle_base_not_process_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle = tmp_path / "bundle"
    skill = bundle / "openclaw/workspace/skills/test-skill/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: test-skill\n---\nPrompt body", encoding="utf-8")
    (bundle / ".env").write_text(
        "OPENCLAW_GATEWAY_TOKEN=bundle-token\n",
        encoding="utf-8",
    )
    foreign_cwd = tmp_path / "foreign"
    foreign_cwd.mkdir()
    monkeypatch.chdir(foreign_cwd)
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)

    assert _load_skill_prompt("test-skill", base_dir=bundle) == "Prompt body"
    assert _load_gateway_token(bundle) == "bundle-token"


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
        payload = {"message": {"content": [{"type": "text", "text": "no json at all"}]}}
        with pytest.raises(RuntimeError):
            _payload_from_chat_event(payload)


class TestHypothesisAwareRefinement:
    def test_finalization_prompt_locks_grounded_findings_and_original_coordinates(
        self,
    ):
        finding = Finding(
            id="f1",
            regions=["lead_V2"],
            label="ST depression",
            detail="confirmed on source crop",
            severity=Severity.WARNING,
            bboxes=[RegionRect(0.2, 0.3, 0.1, 0.1)],
        )
        draft = AnalysisResult(
            modality=Modality.EKG,
            summary="Coarse narrative.",
            severity=Severity.WARNING,
            findings=[finding],
            checklist={},
            layout={"format": "partial"},
        )

        prompt = _build_finalization_prompt(
            modality=Modality.EKG,
            valid_regions=["lead_V2"],
            draft=draft,
            refinement_trace=[
                {
                    "target_id": "f1",
                    "hypothesis": "ST depression",
                    "crop_source": "original_roi",
                    "decisions": [{"action": "confirm"}],
                }
            ],
        )

        assert '"id": "f1"' in prompt
        assert '"x": 0.2' in prompt
        assert "Do not add a diagnosis, finding, or bbox" in prompt
        assert "relative to the attached original image" in prompt
        assert "dicom_bbox_validate" in prompt

    def test_prompt_carries_hypothesis_and_crop_coordinate_contract(self):
        finding = Finding(
            id="f1",
            regions=["lead_V2"],
            label="ST elevation",
            detail="coarse",
            severity=Severity.WARNING,
            bboxes=[RegionRect(0.2, 0.3, 0.2, 0.1)],
        )

        prompt = _build_refinement_prompt(
            modality=Modality.EKG,
            valid_regions=["lead_V2"],
            hypothesis=finding,
            crop_region=RegionRect(0.15, 0.25, 0.3, 0.2),
        )

        assert '"id": "f1"' in prompt
        assert "confirm|revise|retract|add" in prompt
        assert "normalized to the attached crop" in prompt
        assert "dicom_bbox_validate" in prompt
        assert "modality=EKG" in prompt
        assert "w<=0.35" in prompt

    def test_ekg_safety_probe_requests_systematic_visible_lead_search(self):
        prompt = _build_refinement_prompt(
            modality=Modality.EKG,
            valid_regions=["lead_I", "lead_II", "lead_V1"],
            hypothesis=None,
            crop_region=RegionRect(0.0, 0.0, 1.0, 0.5),
        )

        assert '"probe_kind": "systematic_discovery"' in prompt
        assert "ST elevation/depression" in prompt
        assert "reciprocal change" in prompt
        assert "ask a concrete reviewer question" in prompt

    def test_refinement_parser_keeps_explicit_retract_and_revise(self):
        parsed = _parse_refinement_result(
            {
                "deltas": [
                    {
                        "action": "retract",
                        "target_id": "f1",
                        "rationale": "baseline artifact only",
                    },
                    {
                        "action": "add",
                        "target_id": "",
                        "rationale": "new visible ectopy",
                        "finding": {
                            "id": "f2",
                            "regions": ["lead_II"],
                            "label": "PVC",
                            "detail": "wide premature complex",
                            "severity": "warning",
                            "bboxes": [
                                {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.2}
                            ],
                        },
                    },
                ]
            }
        )

        assert [delta.action.value for delta in parsed.deltas] == [
            "retract",
            "add",
        ]
        assert parsed.deltas[1].finding is not None
        assert parsed.deltas[1].finding.bboxes == [
            RegionRect(0.1, 0.2, 0.3, 0.2)
        ]

    def test_refinement_parser_retracts_boxed_nonfinding_limitation(self):
        parsed = _parse_refinement_result(
            {
                "deltas": [
                    {
                        "action": "revise",
                        "target_id": "f1",
                        "rationale": "V2-V6 are outside the crop.",
                        "finding": {
                            "id": "f1",
                            "regions": ["lead_V1"],
                            "label": "R-wave progression cannot be assessed",
                            "detail": "Required leads are unavailable.",
                            "severity": "info",
                            "bboxes": [
                                {"x": 0.1, "y": 0.2, "w": 0.2, "h": 0.1}
                            ],
                        },
                    }
                ]
            }
        )

        assert len(parsed.deltas) == 1
        assert parsed.deltas[0].action.value == "retract"
        assert parsed.deltas[0].target_id == "f1"
        assert parsed.deltas[0].finding is None

    def test_tool_trace_extracts_explicit_gateway_tool_events_only(self):
        frame = {
            "payload": {
                "event": {
                    "type": "tool_call",
                    "name": "dicom_bbox_validate",
                },
                "finding": {"name": "not_a_tool"},
            }
        }

        assert _extract_tool_names(frame) == ["dicom_bbox_validate"]


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
        "heart_rate",
        "rhythm",
        "regularity",
        "axis",
        "p_wave",
        "pr_interval",
        "qrs_duration",
        "qrs_morphology",
        "st_segment",
        "t_wave",
        "qtc_interval",
        "chamber_enlargement",
        "conduction",
        "av_block",
        "stemi_pattern",
        "ischemia",
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

    def test_normal_observation_boxes_are_removed_from_overlay(self):
        validator = OutputValidator(strict=False)
        result = _make_result()
        result.findings = [
            Finding(
                id="normal-qrs",
                regions=["lead_II"],
                label="Narrow QRS",
                detail="No bundle branch block morphology.",
                severity=Severity.NORMAL,
                bboxes=[RegionRect(0.1, 0.1, 0.2, 0.2)],
            )
        ]

        validated = validator.post_analyze(_make_request(), result)

        assert validated.findings[0].bboxes == []
        assert validated.incomplete is True
        assert "normal/negative observation" in validated.validation_warnings[0]

    def test_uncertain_box_requires_low_confidence_reviewer_question(self):
        validator = OutputValidator(strict=False)
        result = _make_result()
        result.findings = [
            Finding(
                id="candidate",
                regions=["lead_II"],
                label="Possible ectopic beat",
                detail="Candidate morphology is not resolved.",
                severity=Severity.INFO,
                bboxes=[RegionRect(0.1, 0.1, 0.2, 0.2)],
                confidence="",
                question="",
            )
        ]

        validated = validator.post_analyze(_make_request(), result)

        assert validated.incomplete is True
        assert "reviewer question" in validated.validation_warnings[0]

    def test_moderate_confidence_benign_info_box_does_not_require_question(self):
        validator = OutputValidator(strict=False)
        result = _make_result()
        result.findings = [
            Finding(
                id="benign",
                regions=["lead_II"],
                label="Early repolarization",
                detail="Mild concave J-point elevation.",
                severity=Severity.INFO,
                bboxes=[RegionRect(0.1, 0.1, 0.2, 0.2)],
                confidence="moderate",
                question="",
            )
        ]

        validated = validator.post_analyze(_make_request(), result)

        assert validated.incomplete is False
        assert validated.validation_warnings == []

    def test_broad_ekg_lead_strip_box_is_not_exposed_as_a_finding(self):
        validator = OutputValidator(strict=False)
        result = _make_result()
        result.severity = Severity.WARNING
        result.findings = [
            Finding(
                id="broad",
                regions=["lead_II"],
                label="Sinus bradycardia",
                detail="Representative rhythm evidence.",
                severity=Severity.WARNING,
                bboxes=[RegionRect(0.02, 0.08, 0.96, 0.08)],
            )
        ]

        validated = validator.post_analyze(_make_request(), result)

        assert validated.findings[0].bboxes == []
        assert any("lead-strip" in item for item in validated.validation_warnings)
        assert any("no accepted tight bbox" in item for item in validated.validation_warnings)


class TestNativeToolAuditTrace:
    def test_reads_only_records_appended_during_current_turn(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        audit_path = tmp_path / "bbox-audit.jsonl"
        stale = {
            "schema_version": 1,
            "tool": "dicom_bbox_validate",
            "tool_call_id": "stale-call",
            "accepted_count": 1,
            "rejected_count": 0,
            "details_sha256": "a" * 64,
        }
        audit_path.write_text(f"{json.dumps(stale)}\n", encoding="utf-8")
        monkeypatch.setenv("DICOM_BBOX_AUDIT_PATH", str(audit_path))
        client = OpenClawClient(gateway_token="test", base_dir=tmp_path)

        client._begin_run_trace("analysis-current")
        current = stale | {
            "tool_call_id": "current-call",
            "details_sha256": "b" * 64,
        }
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{json.dumps(current)}\n")
            handle.write('{"tool":"invalid"}\n')

        trace = client.last_run_trace()

        assert trace["tools"] == ["dicom_bbox_validate"]
        assert [row["tool_call_id"] for row in trace["tool_audit"]] == [
            "current-call"
        ]

    def test_reads_phi_free_ecg_founder_receipt_from_current_turn(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        audit_path = tmp_path / "ecgfounder-audit.jsonl"
        monkeypatch.setenv("DICOM_ECGFOUNDER_AUDIT_PATH", str(audit_path))
        client = OpenClawClient(gateway_token="test", base_dir=tmp_path)

        client._begin_run_trace("analysis-ecg-founder")
        receipt = {
            "schema_version": 1,
            "tool": "ecg_founder_analyze_waveform",
            "tool_call_id": "ecg-call-1",
            "status": "ok",
            "artifact_id_sha256": "a" * 64,
            "model_revision": "04edac702b61c91face519774ddcc0cd712fef23",
            "checkpoint_sha256": "b" * 64,
            "calibration_status": "uncalibrated",
            "prediction_count": 10,
        }
        audit_path.write_text(f"{json.dumps(receipt)}\n", encoding="utf-8")

        trace = client.last_run_trace()

        assert trace["tools"] == ["ecg_founder_analyze_waveform"]
        assert trace["tool_audit"] == [receipt]
        assert "artifact_id" not in trace["tool_audit"][0]


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

    def test_uniform_full_page_signal_does_not_create_arbitrary_zoom_tiles(self):
        image = Image.new("RGB", (400, 300), "white")
        pixels = image.load()
        for y in range(5, 296, 10):
            for x in range(400):
                pixels[x, y] = (0, 0, 0)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")

        profile = ImageProcessor().local_signal_candidates(buffer.getvalue())

        assert profile["candidate_count"] == 0
        assert profile["suppressed_candidate_count"] > 0
        assert profile["selection_rule"] == "localized_density_outlier"
        assert profile["low_signal"] is False


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
