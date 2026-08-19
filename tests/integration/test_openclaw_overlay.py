"""Integration tests for the full OpenClaw → Overlay operation pipeline.

Tests cover:
  1. OpenClaw result parsing (_parse_result, _payload_from_chat_event, _coerce_result_payload)
  2. Chat text extraction (_extract_text_from_event, _extract_text_from_payload)
  3. HookedVisionAnalyzer pipeline (pre/post hooks + delegation)
  4. End-to-end: mock WS → OpenClawClient → Agent → highlights construction
  5. Chat flow: mock WS → OpenClawClient.chat → raw text response
  6. Error paths: empty response, malformed JSON, connection loss
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest
import websockets

from dicom_overlay.application.hooked_analyzer import HookedVisionAnalyzer
from dicom_overlay.application.multi_pass import RefinementResult
from dicom_overlay.application.overlay_agent import OverlayAgent
from dicom_overlay.domain.entities import (
    AgentState,
    AnalysisResult,
    AppConfig,
    ChecklistItem,
    ClaimType,
    Finding,
    Modality,
    Polarity,
    RegionRect,
    ROICrop,
    Severity,
    TriggerMode,
    VerificationStatus,
    WindowRect,
)
from dicom_overlay.domain.hooks import AnalyzeHook, AnalyzeRequest, HookError
from dicom_overlay.domain.services import VisionAnalyzerService
from dicom_overlay.infrastructure.hooks.output_validator import OutputValidator
from dicom_overlay.infrastructure.openclaw_client import (
    OpenClawClient,
    _coerce_result_payload,
    _extract_text_from_event,
    _extract_text_from_payload,
    _load_gateway_token,
    _parse_severity,
    _payload_from_chat_event,
    _strip_code_fence,
)
from dicom_overlay.infrastructure.region_mapper import RegionMapper
from dicom_overlay.infrastructure.screen_monitor import ImageProcessor
from tests.unit.test_agent import MockScreenMonitor

# ═══════════════════════════════════════════════════════════════════════
# 1. Unit tests: OpenClaw parsing helpers
# ═══════════════════════════════════════════════════════════════════════


class TestParseResult:
    """Test OpenClawClient._parse_result() correctness."""

    def _make_client(self) -> OpenClawClient:
        """Create a client without calling __init__ (avoids _load_gateway_token)."""
        client = OpenClawClient.__new__(OpenClawClient)
        client._url = "ws://test"
        client._timeout = 5
        client._reconnect_interval = 1
        client._ws = None
        client._connected = False
        client._request_counter = 0
        client._gateway_token = "test-token"
        client._analysis_prompt_profile = "clinical"
        return client

    @pytest.mark.asyncio
    async def test_analysis_retries_one_malformed_json_turn(self):
        client = self._make_client()
        client._last_parse_retry_count = 0
        calls = 0
        expected = AnalysisResult(
            modality=Modality.EKG,
            summary="Sinus rhythm.",
            severity=Severity.NORMAL,
            findings=[],
            checklist={},
        )

        async def fake_analyze(*_args: object) -> AnalysisResult:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise json.JSONDecodeError("missing bracket", "{", 1)
            return expected

        client._do_analyze = fake_analyze  # type: ignore[method-assign]

        result = await client._analyze_with_parse_retry(
            "image",
            Modality.EKG,
            ["lead_I"],
        )

        assert result is expected
        assert calls == 2
        assert client._last_parse_retry_count == 1

    @pytest.mark.asyncio
    async def test_refinement_retries_one_malformed_json_turn(self):
        client = self._make_client()
        client._last_parse_retry_count = 0
        calls = 0
        expected = RefinementResult()

        async def fake_refine(*_args: object, **_kwargs: object) -> RefinementResult:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise json.JSONDecodeError("missing bracket", "{", 1)
            return expected

        client._do_refine = fake_refine  # type: ignore[method-assign]

        result = await client._refine_with_parse_retry(
            "image",
            Modality.EKG,
            ["lead_I"],
            hypothesis=None,
            crop_region=RegionRect(0.1, 0.2, 0.3, 0.2),
        )

        assert result is expected
        assert calls == 2
        assert client._last_parse_retry_count == 1

    @pytest.mark.asyncio
    async def test_finalization_retries_one_malformed_json_turn(self):
        client = self._make_client()
        client._last_parse_retry_count = 0
        calls = 0
        draft = AnalysisResult(
            modality=Modality.EKG,
            summary="Draft.",
            severity=Severity.NORMAL,
            findings=[],
            checklist={},
        )
        expected = AnalysisResult(
            modality=Modality.EKG,
            summary="Final.",
            severity=Severity.NORMAL,
            findings=[],
            checklist={},
        )

        async def fake_finalize(
            *_args: object,
            **_kwargs: object,
        ) -> AnalysisResult:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise json.JSONDecodeError("missing bracket", "{", 1)
            return expected

        client._do_finalize = fake_finalize  # type: ignore[method-assign]

        result = await client._finalize_with_parse_retry(
            "image",
            Modality.EKG,
            ["lead_I"],
            draft=draft,
            refinement_trace=[],
        )

        assert result is expected
        assert calls == 2
        assert client._last_parse_retry_count == 1

    def test_full_result_parsing(self):
        client = self._make_client()
        payload = {
            "modality": "EKG",
            "summary": "Normal sinus rhythm",
            "severity": "normal",
            "model_used": "gpt-5-mini",
            "analysis_time_ms": 123,
            "image_quality": {
                "adequacy": "limited",
                "issues": ["compression"],
                "detail": "Waveforms remain readable.",
            },
            "next_steps": ["Review lead II at source resolution."],
            "incomplete": True,
            "incomplete_reasons": ["Lead V6 label is cropped."],
            "zoom_hints": ["Zoom lead II at source resolution."],
            "review_required": True,
            "review_reasons": ["Lead II morphology remains uncertain."],
            "findings": [
                {
                    "id": "f1",
                    "regions": ["lead_I", "lead_II"],
                    "label": "ST Elevation",
                    "detail": "Mild elevation in leads I, II",
                    "severity": "warning",
                    "confidence": "low",
                    "question": "Is the lead II baseline stable in the source?",
                }
            ],
            "checklist": {
                "rate": {"value": "72 bpm", "status": "normal"},
                "rhythm": {"value": "sinus", "status": "normal"},
                "stemi_pattern": {"value": "absent", "status": "normal"},
            },
        }
        result = client._parse_result(payload, elapsed_ms=500)

        assert result.modality == Modality.EKG
        assert result.summary == "Normal sinus rhythm"
        assert result.severity == Severity.NORMAL
        assert result.model_used == "gpt-5-mini"
        assert result.analysis_time_ms == 123  # from payload, not elapsed
        assert result.image_quality["adequacy"] == "limited"
        assert result.next_steps == ["Review lead II at source resolution."]
        assert result.incomplete is True
        assert result.incomplete_reasons == [
            "Lead V6 label is cropped.",
            "Trusted host canonical assembly is not available",
        ]
        assert result.zoom_hints == ["Zoom lead II at source resolution."]
        assert result.review_required is True
        assert result.review_reasons == [
            "Lead II morphology remains uncertain.",
            "Medical-image analyzer draft requires authorized human review",
        ]
        assert len(result.findings) == 1

        f = result.findings[0]
        assert f.id == "f1"
        assert f.regions == ["lead_I", "lead_II"]
        assert f.label == "ST Elevation"
        assert f.severity == Severity.WARNING
        assert f.confidence == "low"
        assert f.question.startswith("Is the lead II")

        assert len(result.checklist) == 3
        assert result.checklist["rate"].value == "72 bpm"
        assert result.checklist["rate"].status == Severity.NORMAL

    def test_scientific_ledger_and_links_survive_adapter_parsing(self):
        client = self._make_client()
        result = client._parse_result(
            {
                "modality": "CXR",
                "summary": "Focal right basal opacity.",
                "summary_observation_ids": ["obs-1"],
                "observations": [
                    {
                        "id": "obs-1",
                        "anatomy": "right lower lung",
                        "finding": "focal opacity",
                        "polarity": "present",
                        "status": "supported",
                        "assessable": True,
                        "evidence_ids": ["ev-1"],
                        "claim_type": "descriptive_observation",
                    }
                ],
                "evidence": [
                    {
                        "id": "ev-1",
                        "kind": "source_image",
                        "source_image_sha256": "model-must-not-bind-this",
                        "description": "Visible focal opacity.",
                        "bboxes": [{"x": 0.2, "y": 0.6, "w": 0.1, "h": 0.1}],
                    }
                ],
                "findings": [
                    {
                        "id": "f1",
                        "regions": ["right_lower_lung"],
                        "label": "Focal opacity",
                        "detail": "Visible focal opacity.",
                        "severity": "warning",
                        "claim_type": "descriptive_observation",
                        "observation_ids": ["obs-1"],
                        "evidence_ids": ["ev-1"],
                        "bboxes": [{"x": 0.2, "y": 0.6, "w": 0.1, "h": 0.1}],
                    }
                ],
                "checklist": {
                    "projection_quality": {
                        "value": "limited AP",
                        "status": "info",
                        "assessable": False,
                        "evidence": "single screenshot",
                    }
                },
            },
            elapsed_ms=20,
            request_modality=Modality.CXR,
        )

        assert result.summary_observation_ids == ["obs-1"]
        assert result.observations[0].polarity is Polarity.PRESENT
        assert result.observations[0].status is VerificationStatus.SUPPORTED
        assert result.observations[0].claim_type is ClaimType.DESCRIPTIVE_OBSERVATION
        assert result.evidence[0].source_image_sha256 == ""
        assert result.evidence[0].kind == "source_region"
        assert result.evidence[0].source_ref == ""
        assert result.incomplete is True
        assert "Evidence attestations require trusted host assembly" in (
            result.validation_warnings
        )
        assert result.findings[0].observation_ids == ["obs-1"]
        assert result.findings[0].evidence_ids == ["ev-1"]
        assert result.checklist["projection_quality"].assessable is False
        assert result.checklist["projection_quality"].evidence == "single screenshot"

    def test_missing_fields_default(self):
        client = self._make_client()
        result = client._parse_result({}, elapsed_ms=200)
        assert result.modality == Modality.EKG
        assert result.summary == ""
        assert result.severity == Severity.INFO
        assert result.findings == []
        assert result.checklist == {}
        assert result.analysis_time_ms == 200  # fallback to elapsed

    def test_string_false_does_not_enable_incomplete_or_review_flags(self):
        client = self._make_client()
        client._analysis_prompt_profile = "minimal_control"
        result = client._parse_result(
            {
                "incomplete": "false",
                "review_required": "false",
            },
            elapsed_ms=0,
        )

        assert result.incomplete is False
        assert result.review_required is False

    def test_clinical_draft_without_ledger_fails_closed_through_validator(self):
        client = self._make_client()
        checklist_keys = (
            "projection_quality",
            "airway",
            "lungs",
            "pleura",
            "cardiac_silhouette",
            "mediastinum",
            "hila",
            "diaphragm",
            "bones",
            "soft_tissue",
            "lines_tubes",
        )
        result = client._parse_result(
            {
                "modality": "CXR",
                "summary": "No focal airspace opacity.",
                "severity": "normal",
                "findings": [],
                "checklist": {
                    key: {"value": "reviewed", "status": "normal"}
                    for key in checklist_keys
                },
                "incomplete": False,
                "review_required": False,
            },
            elapsed_ms=1,
            request_modality=Modality.CXR,
        )

        validated = OutputValidator(strict=False).post_analyze(
            AnalyzeRequest(
                image_base64="ZmFrZQ==",
                modality=Modality.CXR,
                valid_regions=["full_image"],
            ),
            result,
        )

        assert validated.incomplete is True
        assert "Trusted host canonical assembly is not available" in (
            validated.incomplete_reasons
        )
        assert validated.review_required is True
        assert "authorized human review" in " ".join(validated.review_reasons)

    def test_invalid_bbox_is_dropped_and_marks_result_incomplete(self):
        client = self._make_client()
        result = client._parse_result(
            {
                "findings": [
                    {
                        "id": "f1",
                        "label": "Candidate",
                        "regions": ["lead_II"],
                        "severity": "info",
                        "bboxes": [
                            {"x": 0.9, "y": 0.2, "w": 0.2, "h": 0.2},
                            {"x": 0.2, "y": 0.2, "w": 0.0, "h": 0.2},
                        ],
                    }
                ]
            },
            elapsed_ms=0,
        )

        assert result.findings[0].bboxes == []
        assert result.incomplete is True
        assert result.incomplete_reasons == [
            "Dropped invalid bbox for finding f1",
            "Trusted host canonical assembly is not available",
        ]
        assert result.validation_warnings == ["Dropped invalid bbox for finding f1"]

    def test_unknown_modality_defaults_ekg(self):
        client = self._make_client()
        result = client._parse_result({"modality": "UNKNOWN_XYZ"}, elapsed_ms=0)
        assert result.modality == Modality.EKG

    def test_unknown_modality_falls_back_to_requested(self):
        client = self._make_client()
        result = client._parse_result(
            {"modality": "UNKNOWN_XYZ"},
            elapsed_ms=0,
            request_modality=Modality.CXR,
        )
        assert result.modality == Modality.CXR

    def test_missing_modality_uses_requested(self):
        client = self._make_client()
        result = client._parse_result(
            {}, elapsed_ms=0, request_modality=Modality.CT_BRAIN
        )
        assert result.modality == Modality.CT_BRAIN

    def test_checklist_plain_value(self):
        """Checklist values that are plain strings (not dicts) are wrapped."""
        client = self._make_client()
        result = client._parse_result({"checklist": {"rate": "72"}}, elapsed_ms=0)
        assert result.checklist["rate"].value == "72"
        assert result.checklist["rate"].status == Severity.INFO

    def test_cxr_modality(self):
        client = self._make_client()
        result = client._parse_result(
            {"modality": "CXR", "summary": "Clear lungs", "severity": "normal"},
            elapsed_ms=100,
        )
        assert result.modality == Modality.CXR

    def test_ct_brain_modality(self):
        client = self._make_client()
        result = client._parse_result(
            {"modality": "CT_BRAIN", "summary": "No bleed", "severity": "normal"},
            elapsed_ms=50,
        )
        assert result.modality == Modality.CT_BRAIN

    def test_multiple_findings(self):
        client = self._make_client()
        result = client._parse_result(
            {
                "findings": [
                    {
                        "id": "f1",
                        "label": "A",
                        "severity": "warning",
                        "regions": ["r1"],
                    },
                    {
                        "id": "f2",
                        "label": "B",
                        "severity": "critical",
                        "regions": ["r2"],
                    },
                    {"id": "f3", "label": "C", "severity": "normal", "regions": []},
                ]
            },
            elapsed_ms=0,
        )
        assert len(result.findings) == 3
        assert result.findings[1].severity == Severity.CRITICAL
        assert result.findings[2].regions == []

    def test_nested_payload_key(self):
        """{ payload: { ... } } wrapper unwrapped by _coerce_result_payload."""
        wrapped = {"payload": {"summary": "Inner data", "severity": "warning"}}
        unwrapped = _coerce_result_payload(wrapped)
        assert unwrapped == {"summary": "Inner data", "severity": "warning"}

    def test_flat_payload(self):
        flat = {"summary": "Direct data", "severity": "normal"}
        assert _coerce_result_payload(flat) is flat


class TestParseSeverity:
    def test_all_valid_severities(self):
        assert _parse_severity("critical") == Severity.CRITICAL
        assert _parse_severity("warning") == Severity.WARNING
        assert _parse_severity("normal") == Severity.NORMAL
        assert _parse_severity("info") == Severity.INFO

    def test_case_insensitive(self):
        assert _parse_severity("CRITICAL") == Severity.CRITICAL
        assert _parse_severity("Warning") == Severity.WARNING

    def test_unknown_severity_defaults_info(self):
        assert _parse_severity("banana") == Severity.INFO
        assert _parse_severity("") == Severity.INFO


class TestPayloadFromChatEvent:
    def test_valid_json_payload(self):
        payload = {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"summary": "Test result", "severity": "normal"}
                        ),
                    }
                ],
            }
        }
        result = _payload_from_chat_event(payload)
        assert result["summary"] == "Test result"

    def test_code_fenced_json(self):
        """JSON wrapped in markdown code fences should be extracted."""
        payload = {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": '```json\n{"summary": "Fenced", "severity": "warning"}\n```',
                    }
                ],
            }
        }
        result = _payload_from_chat_event(payload)
        assert result["summary"] == "Fenced"

    def test_empty_message_raises(self):
        with pytest.raises(RuntimeError):
            _payload_from_chat_event({"message": {"content": []}})

    def test_non_json_text_raises(self):
        payload = {
            "message": {
                "content": [{"type": "text", "text": "I cannot analyze this image."}]
            }
        }
        with pytest.raises((RuntimeError, json.JSONDecodeError)):
            _payload_from_chat_event(payload)

    def test_multi_block_content(self):
        """Multiple text blocks joined together."""
        payload = {
            "message": {
                "content": [
                    {"type": "text", "text": '{"summary":'},
                    {"type": "text", "text": '"Multi-block"}'},
                ]
            }
        }
        result = _payload_from_chat_event(payload)
        assert result["summary"] == "Multi-block"

    def test_non_text_blocks_ignored(self):
        """Image blocks in content should be skipped."""
        payload = {
            "message": {
                "content": [
                    {"type": "image", "data": "base64stuff"},
                    {"type": "text", "text": '{"summary": "Only text"}'},
                ]
            }
        }
        result = _payload_from_chat_event(payload)
        assert result["summary"] == "Only text"


class TestLoadGatewayToken:
    def test_loads_token_from_environment(self, monkeypatch):
        monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "env-token")
        assert _load_gateway_token() == "env-token"

    def test_loads_token_from_file(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
        config_dir = tmp_path / "openclaw"
        config_dir.mkdir()
        (config_dir / "openclaw.json").write_text(
            json.dumps({"gateway": {"auth": {"token": "file-token"}}}),
            encoding="utf-8",
        )

        assert _load_gateway_token() == "file-token"

    def test_loads_token_from_repo_env_file(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
        (tmp_path / ".env").write_text(
            "OPENCLAW_GATEWAY_TOKEN=dotenv-token\n",
            encoding="utf-8",
        )

        assert _load_gateway_token() == "dotenv-token"

    def test_missing_token_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
        assert _load_gateway_token() is None


class TestExtractTextFromEvent:
    def test_extracts_text(self):
        payload = {
            "message": {
                "content": [
                    {"type": "text", "text": "The EKG shows normal sinus rhythm."}
                ]
            }
        }
        text = _extract_text_from_event(payload)
        assert text == "The EKG shows normal sinus rhythm."

    def test_empty_raises(self):
        with pytest.raises(RuntimeError):
            _extract_text_from_event({"message": {"content": []}})

    def test_multi_blocks_joined(self):
        payload = {
            "message": {
                "content": [
                    {"type": "text", "text": "Part 1."},
                    {"type": "text", "text": "Part 2."},
                ]
            }
        }
        text = _extract_text_from_event(payload)
        assert "Part 1." in text
        assert "Part 2." in text


@pytest.mark.asyncio
@pytest.mark.integration
async def test_chat_about_image_sends_context_and_image_attachment():
    received_messages: list[dict[str, Any]] = []

    async def handler(websocket):
        connect_raw = await websocket.recv()
        connect_request = json.loads(connect_raw)
        received_messages.append(connect_request)
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": connect_request["id"],
                    "ok": True,
                    "payload": {"status": "connected"},
                }
            )
        )

        chat_raw = await websocket.recv()
        chat_request = json.loads(chat_raw)
        received_messages.append(chat_request)
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": chat_request["id"],
                    "ok": True,
                    "payload": {"status": "accepted", "runId": "followup-1"},
                }
            )
        )
        await websocket.send(
            json.dumps(
                {
                    "type": "event",
                    "payload": {
                        "runId": "followup-1",
                        "state": "final",
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Inspect lead I first.",
                                }
                            ]
                        },
                    },
                }
            )
        )

    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        client = OpenClawClient(gateway_url=f"ws://127.0.0.1:{port}")
        await client.connect()

        answer = await client.chat_about_image(
            "Which area should I inspect first?",
            image_base64="ZmFrZS1pbWFnZQ==",
            context="EKG critical: ST elevation. Findings: f1 ST Elevation lead_I.",
        )

        assert answer == "Inspect lead I first."
        chat = received_messages[1]
        assert chat["method"] == "chat.send"
        assert "ST elevation" in chat["params"]["message"]
        assert "Which area should I inspect first?" in chat["params"]["message"]
        assert chat["params"]["attachments"][0]["type"] == "image"
    finally:
        server.close()
        await server.wait_closed()


class TestExtractTextFromPayload:
    def test_text_key_present(self):
        assert _extract_text_from_payload({"text": "Hello"}) == "Hello"

    def test_no_text_key_json_dumps(self):
        result = _extract_text_from_payload({"key": "value"})
        assert json.loads(result) == {"key": "value"}


class TestStripCodeFence:
    def test_json_fence(self):
        text = '```json\n{"a": 1}\n```'
        assert _strip_code_fence(text) == '{"a": 1}'

    def test_plain_fence(self):
        text = '```\n{"a": 1}\n```'
        assert _strip_code_fence(text) == '{"a": 1}'

    def test_no_fence(self):
        text = '{"a": 1}'
        assert _strip_code_fence(text) == '{"a": 1}'

    def test_fence_with_trailing_whitespace(self):
        text = '  ```json\n{"b": 2}\n```  '
        result = _strip_code_fence(text.strip())
        assert '{"b": 2}' in result


# ═══════════════════════════════════════════════════════════════════════
# 2. HookedVisionAnalyzer integration tests
# ═══════════════════════════════════════════════════════════════════════


class MockInnerAnalyzer(VisionAnalyzerService):
    def __init__(self):
        self._connected = True
        self.analyze_calls: list[tuple[str, Modality]] = []
        self.chat_calls: list[str] = []

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    async def analyze(
        self, image_base64: str, modality: Modality, valid_regions: list[str]
    ) -> AnalysisResult:
        self.analyze_calls.append((image_base64, modality))
        return AnalysisResult(
            modality=modality,
            summary="Mock analysis",
            severity=Severity.NORMAL,
            findings=[
                Finding(
                    id="mock-f1",
                    regions=["lead_I"],
                    label="Mock finding",
                    detail="Detail",
                    severity=Severity.WARNING,
                )
            ],
            checklist={"rate": ChecklistItem(value="72", status=Severity.NORMAL)},
            analysis_time_ms=50,
        )

    async def chat(self, message: str) -> str:
        self.chat_calls.append(message)
        return f"Answer to: {message}"


class FailingConnectAnalyzer(VisionAnalyzerService):
    """Mock that always fails on connect — for testing RECONNECTING state."""

    def __init__(self):
        self._connected = False

    async def connect(self) -> None:
        raise ConnectionError("Mock connection refused")

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    async def analyze(
        self, image_base64: str, modality: Modality, valid_regions: list[str]
    ) -> AnalysisResult:
        raise ConnectionError("Not connected")

    async def chat(self, message: str) -> str:
        raise ConnectionError("Not connected")


class CountingHook(AnalyzeHook):
    def __init__(self):
        self.pre_count = 0
        self.post_count = 0

    @property
    def name(self) -> str:
        return "counting"

    def pre_analyze(self, request: AnalyzeRequest) -> AnalyzeRequest:
        self.pre_count += 1
        return request

    def post_analyze(
        self, request: AnalyzeRequest, result: AnalysisResult
    ) -> AnalysisResult:
        self.post_count += 1
        return result


class RejectingPreHook(AnalyzeHook):
    @property
    def name(self) -> str:
        return "rejecting-pre"

    def pre_analyze(self, request: AnalyzeRequest) -> AnalyzeRequest:
        raise HookError("Pre-hook rejection")

    def post_analyze(
        self, request: AnalyzeRequest, result: AnalysisResult
    ) -> AnalysisResult:
        return result


class RejectingPostHook(AnalyzeHook):
    @property
    def name(self) -> str:
        return "rejecting-post"

    def pre_analyze(self, request: AnalyzeRequest) -> AnalyzeRequest:
        return request

    def post_analyze(
        self, request: AnalyzeRequest, result: AnalysisResult
    ) -> AnalysisResult:
        raise HookError("Post-hook rejection")


class TestHookedVisionAnalyzer:
    @pytest.mark.asyncio
    async def test_hooks_called_in_order(self):
        inner = MockInnerAnalyzer()
        hook = CountingHook()
        hooked = HookedVisionAnalyzer(inner=inner, hooks=[hook])

        result = await hooked.analyze("img_data", Modality.EKG, ["lead_I"])

        assert hook.pre_count == 1
        assert hook.post_count == 1
        assert result.summary == "Mock analysis"
        assert len(inner.analyze_calls) == 1

    @pytest.mark.asyncio
    async def test_multiple_hooks(self):
        inner = MockInnerAnalyzer()
        hook1 = CountingHook()
        hook2 = CountingHook()
        hooked = HookedVisionAnalyzer(inner=inner, hooks=[hook1, hook2])

        await hooked.analyze("img", Modality.CXR, [])

        assert hook1.pre_count == 1
        assert hook2.pre_count == 1
        assert hook1.post_count == 1
        assert hook2.post_count == 1

    @pytest.mark.asyncio
    async def test_source_aware_analysis_is_delegated_and_final_hooks_run(self):
        class SourceAwareInner(MockInnerAnalyzer):
            def __init__(self):
                super().__init__()
                self.source_call = None

            async def analyze_with_source_size(
                self,
                image_base64,
                modality,
                valid_regions,
                *,
                source_size_px,
                source_image_base64=None,
                local_candidate_regions=None,
            ):
                self.source_call = {
                    "source_size_px": source_size_px,
                    "source_image_base64": source_image_base64,
                    "local_candidate_regions": local_candidate_regions,
                }
                return await self.analyze(image_base64, modality, valid_regions)

        inner = SourceAwareInner()

        class SourceRecordingHook(CountingHook):
            source_image_base64 = None

            def post_analyze(self, request, result):
                self.source_image_base64 = request.metadata.get("source_image_base64")
                return super().post_analyze(request, result)

        hook = SourceRecordingHook()
        hooked = HookedVisionAnalyzer(inner=inner, hooks=[hook])
        candidate = RegionRect(0.1, 0.2, 0.3, 0.4)

        result = await hooked.analyze_with_source_size(
            "coarse",
            Modality.EKG,
            ["lead_I"],
            source_size_px=(2000, 1200),
            source_image_base64="source",
            local_candidate_regions=[candidate],
        )

        assert result.summary == "Mock analysis"
        assert inner.source_call == {
            "source_size_px": (2000, 1200),
            "source_image_base64": "source",
            "local_candidate_regions": [candidate],
        }
        assert hook.pre_count == 1
        assert hook.post_count == 1
        assert hook.source_image_base64 == "source"

    @pytest.mark.asyncio
    async def test_pre_hook_rejection_blocks_analyze(self):
        inner = MockInnerAnalyzer()
        hooked = HookedVisionAnalyzer(inner=inner, hooks=[RejectingPreHook()])

        with pytest.raises(HookError, match="Pre-hook"):
            await hooked.analyze("img", Modality.EKG, ["lead_I"])

        assert len(inner.analyze_calls) == 0  # Never reached inner

    @pytest.mark.asyncio
    async def test_post_hook_rejection_raises(self):
        inner = MockInnerAnalyzer()
        hooked = HookedVisionAnalyzer(inner=inner, hooks=[RejectingPostHook()])

        with pytest.raises(HookError, match="Post-hook"):
            await hooked.analyze("img", Modality.EKG, ["lead_I"])

        assert len(inner.analyze_calls) == 1  # Inner was called

    @pytest.mark.asyncio
    async def test_chat_delegates_without_hooks(self):
        inner = MockInnerAnalyzer()
        hook = CountingHook()
        hooked = HookedVisionAnalyzer(inner=inner, hooks=[hook])

        answer = await hooked.chat("What is this?")

        assert answer == "Answer to: What is this?"
        assert hook.pre_count == 0  # Hooks not involved in chat
        assert inner.chat_calls == ["What is this?"]

    @pytest.mark.asyncio
    async def test_connect_disconnect_delegates(self):
        inner = MockInnerAnalyzer()
        hooked = HookedVisionAnalyzer(inner=inner)

        assert hooked.is_connected()
        await hooked.disconnect()
        assert not hooked.is_connected()
        await hooked.connect()
        assert hooked.is_connected()

    @pytest.mark.asyncio
    async def test_add_hook_dynamically(self):
        inner = MockInnerAnalyzer()
        hooked = HookedVisionAnalyzer(inner=inner)
        hook = CountingHook()
        hooked.add_hook(hook)

        await hooked.analyze("x", Modality.EKG, [])
        assert hook.pre_count == 1


# ═══════════════════════════════════════════════════════════════════════
# 3. End-to-end: mock WS → OpenClaw → Agent → highlights
# ═══════════════════════════════════════════════════════════════════════


def _make_ws_handler(
    analysis_json: dict[str, Any],
    *,
    analysis_delay_ms: int = 0,
):
    """Create a mock WS handler that echoes an analysis result."""

    async def handler(websocket):
        # 1. Handle connect handshake
        connect_raw = await websocket.recv()
        connect_req = json.loads(connect_raw)
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": connect_req["id"],
                    "ok": True,
                    "payload": {"status": "ok"},
                }
            )
        )

        # 2. Handle chat.send (analysis request)
        chat_raw = await websocket.recv()
        chat_req = json.loads(chat_raw)
        run_id = str(uuid4())

        # Send accepted response
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": chat_req["id"],
                    "ok": True,
                    "payload": {"status": "accepted", "runId": run_id},
                }
            )
        )

        if analysis_delay_ms > 0:
            await asyncio.sleep(analysis_delay_ms / 1000)

        # Send final event with analysis JSON
        await websocket.send(
            json.dumps(
                {
                    "type": "event",
                    "event": "chat",
                    "payload": {
                        "runId": run_id,
                        "sessionKey": "main",
                        "seq": 1,
                        "state": "final",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": json.dumps(analysis_json)},
                            ],
                        },
                    },
                }
            )
        )

    return handler


def _make_chat_ws_handler(analysis_json: dict[str, Any], chat_response: str):
    """Create a WS handler that supports both analyze and chat operations."""

    async def handler(websocket):
        # 1. Handshake
        connect_raw = await websocket.recv()
        connect_req = json.loads(connect_raw)
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": connect_req["id"],
                    "ok": True,
                    "payload": {"status": "ok"},
                }
            )
        )

        # Handle multiple requests
        while True:
            try:
                raw = await asyncio.wait_for(websocket.recv(), timeout=5)
            except (TimeoutError, websockets.ConnectionClosed):
                break

            req = json.loads(raw)
            run_id = str(uuid4())

            # Check if this has attachments (analysis) or not (chat)
            has_attachments = bool(req.get("params", {}).get("attachments"))

            await websocket.send(
                json.dumps(
                    {
                        "type": "res",
                        "id": req["id"],
                        "ok": True,
                        "payload": {"status": "accepted", "runId": run_id},
                    }
                )
            )

            if has_attachments:
                content_text = json.dumps(analysis_json)
            else:
                content_text = chat_response

            await websocket.send(
                json.dumps(
                    {
                        "type": "event",
                        "event": "chat",
                        "payload": {
                            "runId": run_id,
                            "sessionKey": "main",
                            "seq": 1,
                            "state": "final",
                            "message": {
                                "role": "assistant",
                                "content": [{"type": "text", "text": content_text}],
                            },
                        },
                    }
                )
            )

    return handler


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_analysis_with_highlights():
    """Full pipeline: mock WS → OpenClaw → Agent → highlights list."""
    analysis_json = {
        "modality": "EKG",
        "summary": "ST elevation in anterior leads",
        "severity": "critical",
        "model_used": "gpt-5-mini",
        "analysis_time_ms": 150,
        "findings": [
            {
                "id": "f1",
                "regions": ["lead_I"],
                "label": "ST Elevation",
                "detail": "ST elevation > 2mm",
                "severity": "critical",
            },
            {
                "id": "f2",
                "regions": ["lead_I", "rhythm_strip"],
                "label": "Tachycardia",
                "detail": "Rate 120 bpm",
                "severity": "warning",
            },
        ],
        "checklist": {
            "rate": {"value": "120 bpm", "status": "warning"},
            "stemi_pattern": {"value": "STEMI anterior", "status": "critical"},
        },
    }

    handler = _make_ws_handler(analysis_json)
    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        config = AppConfig()
        config.phi_roi = ROICrop(
            configured=True,
            reference_width=1,
            reference_height=1,
        )
        config.analysis.trigger_mode = TriggerMode.AUTO
        config.openclaw.gateway_url = f"ws://127.0.0.1:{port}"
        config.monitor.debounce_stable_sec = 0.0
        config.region_maps = {
            "EKG": {
                "regions": {
                    "lead_I": {"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.27},
                    "rhythm_strip": {"x": 0.0, "y": 0.81, "w": 1.0, "h": 0.19},
                },
            }
        }

        screen_monitor = MockScreenMonitor()
        screen_monitor.window = WindowRect(left=100, top=50, width=1920, height=1080)
        screen_monitor.hash_value = "aaaa"

        region_mapper = RegionMapper(config.region_maps)
        client = OpenClawClient(gateway_url=config.openclaw.gateway_url)

        agent = OverlayAgent(
            config=config,
            screen_monitor=screen_monitor,
            image_processor=ImageProcessor(),
            vision_analyzer=client,
            region_mapper=region_mapper,
        )

        results: list[AnalysisResult] = []
        errors: list[str] = []
        agent.on_analysis_result = results.append
        agent.on_error = errors.append

        await agent.start()
        assert agent.state == AgentState.WAITING

        # Tick 1: find window → MONITORING
        await agent.tick()
        assert agent.state == AgentState.MONITORING

        # Tick 2: detect hash change → capture → analyze
        screen_monitor.hash_changed = True
        await agent.tick()
        # May need extra tick for debounce=0
        if not results:
            await agent.tick()

        assert len(results) == 1
        assert not errors

        result = results[0]
        assert result.modality == Modality.EKG
        assert result.summary == "ST elevation in anterior leads"
        assert result.severity == Severity.CRITICAL
        assert len(result.findings) == 2
        assert result.findings[0].label == "ST Elevation"
        assert result.findings[0].severity == Severity.CRITICAL
        assert result.findings[1].label == "Tachycardia"
        assert "stemi_pattern" in result.checklist
        assert result.checklist["rate"].value == "120 bpm"

        # Verify highlight construction (mimics __main__.py logic)
        highlights = []
        for finding in result.findings:
            for region_name in finding.regions:
                rect = region_mapper.get_region_rect(region_name, result.modality)
                if rect and agent.target_window:
                    sx, sy, sw, sh = region_mapper.to_screen_rect(
                        rect, agent.target_window
                    )
                    lx = sx - agent.target_window.left
                    ly = sy - agent.target_window.top
                    highlights.append(
                        (lx, ly, sw, sh, finding.severity.value, finding.label)
                    )

        # f1 → lead_I (1 region), f2 → lead_I + rhythm_strip (2 regions)
        assert len(highlights) == 3

        # First highlight: lead_I for f1
        h0 = highlights[0]
        assert h0[4] == "critical"
        assert h0[5] == "ST Elevation"
        assert h0[0] == 0  # x: 0.0 * 1920
        assert h0[1] == 0  # y: 0.0 * 1080

        # Third highlight: rhythm_strip for f2
        h2 = highlights[2]
        assert h2[4] == "warning"
        assert h2[5] == "Tachycardia"
        assert h2[0] == 0  # x: 0.0 * 1920
        assert h2[1] == int(0.81 * 1080)  # y: 874

        await agent.stop()
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_chat_response():
    """Full pipeline: mock WS → OpenClaw.chat → raw text response."""
    analysis_json = {
        "modality": "EKG",
        "summary": "Normal",
        "severity": "normal",
        "findings": [],
        "checklist": {},
    }
    chat_answer = "The EKG shows normal sinus rhythm at 72 bpm with no ST changes."

    handler = _make_chat_ws_handler(analysis_json, chat_answer)
    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        client = OpenClawClient(gateway_url=f"ws://127.0.0.1:{port}", timeout_sec=10)
        await client.connect()

        response = await client.chat("What does this EKG show?")
        assert response == chat_answer
        assert "72 bpm" in response

        await client.disconnect()
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_hooked_analysis_pipeline():
    """Full: mock WS → HookedVisionAnalyzer(hooks) → result passes through hooks."""
    analysis_json = {
        "modality": "EKG",
        "summary": "Hooked pipeline test",
        "severity": "warning",
        "findings": [
            {
                "id": "hf1",
                "regions": ["lead_I"],
                "label": "Test",
                "detail": "D",
                "severity": "warning",
            }
        ],
        "checklist": {"rate": {"value": "88", "status": "normal"}},
    }

    handler = _make_ws_handler(analysis_json)
    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        client = OpenClawClient(gateway_url=f"ws://127.0.0.1:{port}", timeout_sec=10)

        counting = CountingHook()
        hooked = HookedVisionAnalyzer(inner=client, hooks=[counting])

        await hooked.connect()
        result = await hooked.analyze("aW1n", Modality.EKG, ["lead_I"])

        assert counting.pre_count == 1
        assert counting.post_count == 1
        assert result.summary == "Hooked pipeline test"
        assert result.findings[0].label == "Test"

        await hooked.disconnect()
    finally:
        server.close()
        await server.wait_closed()


# ═══════════════════════════════════════════════════════════════════════
# 4. Error path tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ws_error_response():
    """Gateway returns error in res frame."""

    async def handler(websocket):
        # Handshake
        raw = await websocket.recv()
        req = json.loads(raw)
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": req["id"],
                    "ok": True,
                    "payload": {"status": "ok"},
                }
            )
        )
        # Chat send → error
        raw = await websocket.recv()
        req = json.loads(raw)
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": req["id"],
                    "ok": False,
                    "error": {"code": "RATE_LIMITED", "message": "Too many requests"},
                }
            )
        )

    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        client = OpenClawClient(gateway_url=f"ws://127.0.0.1:{port}", timeout_sec=5)
        await client.connect()

        with pytest.raises(RuntimeError):
            await client.chat("test")

        await client.disconnect()
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ws_event_error_state():
    """Gateway sends event with state='error'."""

    async def handler(websocket):
        raw = await websocket.recv()
        req = json.loads(raw)
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": req["id"],
                    "ok": True,
                    "payload": {"status": "ok"},
                }
            )
        )
        raw = await websocket.recv()
        req = json.loads(raw)
        run_id = str(uuid4())
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": req["id"],
                    "ok": True,
                    "payload": {"status": "accepted", "runId": run_id},
                }
            )
        )
        await websocket.send(
            json.dumps(
                {
                    "type": "event",
                    "event": "chat",
                    "payload": {
                        "runId": run_id,
                        "state": "error",
                        "errorMessage": "Model overloaded",
                    },
                }
            )
        )

    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        client = OpenClawClient(gateway_url=f"ws://127.0.0.1:{port}", timeout_sec=5)
        await client.connect()

        with pytest.raises(RuntimeError, match="Model overloaded"):
            await client.chat("test")
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ws_connection_close_during_chat():
    """Gateway drops connection mid-chat."""

    async def handler(websocket):
        raw = await websocket.recv()
        req = json.loads(raw)
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": req["id"],
                    "ok": True,
                    "payload": {"status": "ok"},
                }
            )
        )
        raw = await websocket.recv()
        # Close without responding
        await websocket.close()

    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        client = OpenClawClient(gateway_url=f"ws://127.0.0.1:{port}", timeout_sec=3)
        await client.connect()

        with pytest.raises((ConnectionError, websockets.ConnectionClosed)):
            await client.chat("test")

        assert not client.is_connected()
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_agent_reconnect_on_connection_loss():
    """Agent transitions to RECONNECTING when analyzer connect fails."""
    from tests.unit.test_agent import MockImageProcessor

    config = AppConfig()
    config.phi_roi = ROICrop(
        configured=True,
        reference_width=1,
        reference_height=1,
    )
    config.analysis.trigger_mode = TriggerMode.AUTO
    config.openclaw.reconnect_interval_sec = 0
    config.monitor.debounce_stable_sec = 0.0

    screen_monitor = MockScreenMonitor()
    screen_monitor.window = WindowRect(left=0, top=0, width=100, height=100)

    inner = FailingConnectAnalyzer()

    agent = OverlayAgent(
        config=config,
        screen_monitor=screen_monitor,
        image_processor=MockImageProcessor(),
        vision_analyzer=inner,
        region_mapper=RegionMapper({"EKG": {"regions": {}}}),
    )

    errors: list[str] = []
    agent.on_error = errors.append

    await agent.start()
    await agent.tick()  # find window → MONITORING

    # First monitoring tick just records initial hash
    await agent.tick()

    # Now trigger capture with disconnected analyzer
    screen_monitor.hash_changed = True
    await agent.tick()

    # Agent should be in RECONNECTING state (connect() fails)
    assert agent.state == AgentState.RECONNECTING
    assert any("離線" in e or "Gateway" in e for e in errors)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_cxr_modality():
    """CXR modality end-to-end test."""
    analysis_json = {
        "modality": "CXR",
        "summary": "Right lower lobe consolidation",
        "severity": "warning",
        "findings": [
            {
                "id": "cxr1",
                "regions": ["right_lower_lung"],
                "label": "Consolidation",
                "detail": "Air bronchograms present",
                "severity": "warning",
            }
        ],
        "checklist": {
            "consolidation": {"value": "RLL opacity", "status": "warning"},
            "pneumothorax": {"value": "absent", "status": "normal"},
        },
    }

    handler = _make_ws_handler(analysis_json)
    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        config = AppConfig()
        config.phi_roi = ROICrop(
            configured=True,
            reference_width=1,
            reference_height=1,
        )
        config.analysis.trigger_mode = TriggerMode.AUTO
        config.openclaw.gateway_url = f"ws://127.0.0.1:{port}"
        config.monitor.debounce_stable_sec = 0.0
        config.region_maps = {
            "CXR": {
                "regions": {
                    "right_lower_lung": {"x": 0.55, "y": 0.55, "w": 0.30, "h": 0.30},
                },
            }
        }

        screen_monitor = MockScreenMonitor()
        screen_monitor.window = WindowRect(left=0, top=0, width=1000, height=800)
        screen_monitor.hash_value = "bbbb"

        client = OpenClawClient(gateway_url=config.openclaw.gateway_url)
        agent = OverlayAgent(
            config=config,
            screen_monitor=screen_monitor,
            image_processor=ImageProcessor(),
            vision_analyzer=client,
            region_mapper=RegionMapper(config.region_maps),
        )
        agent.set_modality(Modality.CXR)

        results: list[AnalysisResult] = []
        agent.on_analysis_result = results.append

        await agent.start()
        await agent.tick()
        screen_monitor.hash_changed = True
        await agent.tick()
        if not results:
            await agent.tick()

        assert len(results) == 1
        assert results[0].modality == Modality.CXR
        assert results[0].findings[0].label == "Consolidation"
        assert "consolidation" in results[0].checklist

        await agent.stop()
    finally:
        server.close()
        await server.wait_closed()
