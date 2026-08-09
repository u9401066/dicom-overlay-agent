"""Core 2 robustness tests — live validation, retry, prose JSON, image guard.

Covers the hardening fixes for the OpenClaw interpretation harness:
  1. Live results get marked ``incomplete`` when schema checks warn.
  2. Transient inference timeouts get one backoff retry before ERROR.
  3. Prose-wrapped JSON responses are recovered via brace extraction.
  5. Oversized ROI images are downscaled before send.
  6. Out-of-bounds bboxes are dropped (not crashed on) and degrade gracefully.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

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
    BboxEvidenceError,
    ModelResponseParseError,
    OpenClawClient,
    _bbox_coordinates_digest,
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
    with client.use_waveform_artifact(
        "wf-opaque-123", lead_mode="12_lead"
    ) as evidence_nonce:
        binding = client._waveform_artifact_context.get()
        assert binding is not None
        assert binding.artifact_id == "wf-opaque-123"
        assert binding.lead_mode == "12_lead"
        assert binding.evidence_nonce == evidence_nonce
        assert len(evidence_nonce) == 32
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

    def test_payload_repairs_missing_nested_array_closer_without_retry(self):
        payload = {
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"modality":"EKG","layout":{"leads":['
                            '{"name":"I","bbox":[0,0,1,0.1]},'
                            '"notes":"visible labels"},"summary":"LVH strain",'
                            '"findings":[]}'
                        ),
                    }
                ]
            }
        }

        data = _payload_from_chat_event(payload)

        assert data["layout"]["leads"][0]["name"] == "I"
        assert data["layout"]["notes"] == "visible labels"
        assert data["summary"] == "LVH strain"
        assert data["_harness_json_repair_count"] == 1

    def test_payload_repairs_reversed_closer_then_missing_parent_closer(self):
        payload = {
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"modality":"EKG","layout":{"leads":['
                            '{"name":"I","bbox":[0,0,1,0.1]},'
                            '{"name":"II","bbox":[0,0.1,1,0.1]},'
                            '{"name":"V6","bbox":[0,0.9,1,0.075]},'
                            '"notes":"visible labels"},"summary":"LVH strain",'
                            '"findings":[]}'
                        ).replace("0.075]}", "0.075}]"),
                    }
                ]
            }
        }

        data = _payload_from_chat_event(payload)

        assert [lead["name"] for lead in data["layout"]["leads"]] == [
            "I",
            "II",
            "V6",
        ]
        assert data["layout"]["notes"] == "visible labels"
        assert data["_harness_json_repair_count"] == 2

    def test_payload_from_chat_event_raises_without_json(self):
        payload = {"message": {"content": [{"type": "text", "text": "no json at all"}]}}
        with pytest.raises(ModelResponseParseError):
            _payload_from_chat_event(payload)

    def test_payload_repairs_stray_quote_before_array_closer(self):
        payload = {
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"summary":"Abnormal ECG","severity":"urgent",'
                            '"findings":[],"next_steps":["Refine rhythm.",'
                            '"Check ST-T morphology.","],'
                            '"image_quality":"Adequate"}'
                        ),
                    }
                ]
            }
        }

        data = _payload_from_chat_event(payload)

        assert data["next_steps"] == ["Refine rhythm.", "Check ST-T morphology."]
        assert data["image_quality"] == "Adequate"

    @pytest.mark.asyncio
    async def test_coarse_model_parse_error_retries_once(self):
        client = _bare_client()
        calls = 0

        async def coarse_turn(*_args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ModelResponseParseError("malformed model JSON")
            return AnalysisResult(
                modality=Modality.EKG,
                summary="Sinus rhythm.",
                severity=Severity.NORMAL,
                findings=[],
                checklist={},
            )

        client._do_coarse_analyze = coarse_turn

        result = await client._analyze_coarse_with_parse_retry(
            "image",
            Modality.EKG,
            [],
        )

        assert result.severity is Severity.NORMAL
        assert calls == 2
        assert client._last_parse_retry_count == 1


class TestHypothesisAwareRefinement:
    def test_finalization_prompt_allows_disposition_but_locks_original_coordinates(
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
        assert '"candidate_bbox_count": 1' in prompt
        assert "RETAIN it unchanged" in prompt
        assert "REVISE its label/detail/severity/confidence/question" in prompt
        assert "RETRACT it by omitting it" in prompt
        assert "unique subset of draft IDs" in prompt
        assert "duplicate study-level rate or rhythm findings" in prompt
        assert "Never move, resize, add" in prompt
        assert "normal/otherwise normal" in prompt
        assert "omission from its top-k list" in prompt
        assert "three broad QRS complexes across multiple leads" in prompt
        assert "NSVT/VT versus artifact" in prompt
        assert "final bbox multiset must exactly match that one receipt" in prompt
        assert "checklist must contain exactly these 16 axes" in prompt
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
            crop_lead_regions={
                "lead_V2": RegionRect(0.0, 0.1, 1.0, 0.4),
                "lead_V3": RegionRect(0.0, 0.5, 1.0, 0.4),
            },
        )

        assert '"id": "f1"' in prompt
        assert "confirm|revise|retract|add" in prompt
        assert "normalized to the attached crop" in prompt
        assert "dicom_bbox_validate" in prompt
        assert "modality=EKG" in prompt
        assert "w<=0.35" in prompt
        assert '"crop_lead_regions"' in prompt
        assert '"region": "lead_V2"' in prompt
        assert "center of every returned box must fall inside" in prompt
        assert "Do not move a box" in prompt

    def test_ekg_safety_probe_requests_systematic_visible_lead_search(self):
        prompt = _build_refinement_prompt(
            modality=Modality.EKG,
            valid_regions=["lead_I", "lead_II", "lead_V1"],
            hypothesis=None,
            crop_region=RegionRect(0.0, 0.0, 1.0, 0.5),
            probe_id="ekg_systematic_precordial_leads",
            supporting_waveform_evidence={
                "status": "ok",
                "calibration_status": "uncalibrated",
                "predictions": [
                    {
                        "label": "LEFT VENTRICULAR HYPERTROPHY",
                        "uncalibrated_score": 0.42,
                    }
                ],
            },
        )

        assert '"probe_kind": "systematic_discovery"' in prompt
        assert "ST elevation/depression" in prompt
        assert "reciprocal change" in prompt
        assert "ask a concrete reviewer question" in prompt
        assert "distinct narrow pacing spikes" in prompt
        assert "Repetitive wide or tall QRS complexes alone" in prompt
        assert "heart_rate_bpm_from_median_rr" in prompt
        assert "three consecutive broad QRS complexes" in prompt
        assert "NSVT/VT versus artifact" in prompt
        assert '"probe_id": "ekg_systematic_precordial_leads"' in prompt
        assert "inspect V1-V6 without privileging one candidate" in prompt
        assert "pathologic Q/QS morphology" in prompt
        assert "high or low voltage" in prompt
        assert "uncalibrated waveform classifier candidates" in prompt
        assert "Ranked labels route inspection but never set diagnosis" in prompt
        assert "normal/otherwise-normal ranked label" in prompt
        assert "top-k omission is not negative evidence" in prompt
        assert "If PVC/PAC/ectopy is top-three" in prompt
        assert "LVH finding with warning severity" not in prompt
        assert "Do not call ecg_founder_analyze_waveform again" in prompt
        assert "exactly equal the accepted boxes" in prompt

    def test_systematic_probe_can_verify_an_untargeted_hypothesis(self):
        finding = Finding(
            id="st-t",
            regions=["lead_V2", "lead_V3"],
            label="Anterior ST-T abnormality",
            detail="Unlocalized coarse concern",
            severity=Severity.CRITICAL,
        )

        prompt = _build_refinement_prompt(
            modality=Modality.EKG,
            valid_regions=["lead_V2", "lead_V3"],
            hypothesis=finding,
            crop_region=RegionRect(0.0, 0.5, 1.0, 0.5),
            probe_id="ekg_systematic_precordial_leads",
        )

        assert '"probe_kind": "systematic_hypothesis_verification"' in prompt
        assert '"id": "st-t"' in prompt
        assert "decide the supplied target" in prompt

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
                            "bboxes": [{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.2}],
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
        assert parsed.deltas[1].finding.bboxes == [RegionRect(0.1, 0.2, 0.3, 0.2)]

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
                            "bboxes": [{"x": 0.1, "y": 0.2, "w": 0.2, "h": 0.1}],
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


@pytest.mark.asyncio
async def test_image_followup_uses_unique_session_and_ignores_stale_tool_events(
    tmp_path: Path,
) -> None:
    client = OpenClawClient(
        gateway_token="test",
        base_dir=tmp_path,
        fast_mode=True,
    )

    class FakeWebSocket:
        def __init__(self) -> None:
            self.sent: dict[str, object] = {}
            self.index = 0

        async def send(self, raw: str) -> None:
            self.sent = json.loads(raw)

        async def recv(self) -> str:
            request_id = str(self.sent["id"])
            frames = [
                {
                    "type": "event",
                    "payload": {
                        "runId": "stale-run",
                        "event": {"type": "tool_call", "name": "stale_tool"},
                    },
                },
                {
                    "type": "res",
                    "id": request_id,
                    "ok": True,
                    "payload": {"status": "accepted", "runId": "current-run"},
                },
                {
                    "type": "event",
                    "payload": {
                        "runId": "stale-run",
                        "event": {"type": "tool_call", "name": "stale_tool_2"},
                    },
                },
                {
                    "type": "event",
                    "payload": {
                        "runId": "current-run",
                        "state": "working",
                        "event": {
                            "type": "tool_call",
                            "name": "dicom_bbox_validate",
                        },
                    },
                },
                {
                    "type": "event",
                    "payload": {
                        "runId": "current-run",
                        "state": "final",
                        "message": {"content": [{"type": "text", "text": "done"}]},
                    },
                },
            ]
            frame = frames[self.index]
            self.index += 1
            return json.dumps(frame)

    websocket = FakeWebSocket()
    client._ws = websocket
    client._connected = True

    response = await client._do_image_chat_prompt("review", image_base64="image")

    assert response == "done"
    session_key = websocket.sent["params"]["sessionKey"]  # type: ignore[index]
    assert str(session_key).startswith("image-followup-")
    assert session_key != "main"
    assert websocket.sent["params"]["fastMode"] is True  # type: ignore[index]
    trace = client.last_run_trace()
    assert trace["run_id"] == "current-run"
    assert trace["tools"] == ["dicom_bbox_validate"]
    assert trace["fast_mode_requested"] is True
    assert trace["priority_service_observed"] is None
    assert "priority_service_requested" not in trace


@pytest.mark.asyncio
async def test_openclaw_stream_events_do_not_reset_absolute_turn_timeout(
    tmp_path: Path,
) -> None:
    client = OpenClawClient(
        gateway_token="test",
        base_dir=tmp_path,
        inference_timeout_sec=1,
    )
    client._inference_timeout = 0.04

    class BusyWebSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, object]] = []
            self.recv_count = 0

        async def send(self, raw: str) -> None:
            self.sent.append(json.loads(raw))

        async def recv(self) -> str:
            await asyncio.sleep(0.015)
            self.recv_count += 1
            if self.recv_count == 1:
                return json.dumps(
                    {
                        "type": "res",
                        "id": "request-1",
                        "ok": True,
                        "payload": {"status": "accepted", "runId": "run-1"},
                    }
                )
            return json.dumps(
                {
                    "type": "event",
                    "payload": {"runId": "run-1", "state": "working"},
                }
            )

    websocket = BusyWebSocket()
    client._ws = websocket
    client._connected = True
    client._begin_run_trace("analysis-sla-test")

    with pytest.raises(TimeoutError, match="Analysis timeout"):
        await client._wait_for_chat_result("request-1")

    abort = websocket.sent[-1]
    assert abort["method"] == "chat.abort"
    assert abort["params"] == {
        "sessionKey": "analysis-sla-test",
        "runId": "run-1",
    }
    assert client.last_run_trace()["turn_aborted"] is True


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

    def test_bounded_json_repair_is_audited_without_clinical_degradation(self):
        client = _bare_client()
        payload = {
            "modality": "EKG",
            "summary": "Sinus rhythm within normal limits.",
            "severity": "normal",
            "findings": [],
            "checklist": {},
            "_harness_json_repair_count": 2,
        }

        result = client._parse_result(payload, elapsed_ms=100)

        assert result.incomplete is False
        assert result.validation_warnings == []
        assert result.analysis_trace == [
            {
                "stage": "json_recovery",
                "status": "repaired",
                "tool": "bounded_json_delimiter_repair",
                "repair_count": 2,
            }
        ]

    @pytest.mark.parametrize("value", ["urgent", "emergent", "emergency"])
    def test_urgent_severity_aliases_fail_safe_to_critical(self, value):
        result = _bare_client()._parse_result(
            {
                "modality": "EKG",
                "summary": "Urgent review is required.",
                "severity": value,
                "findings": [],
                "checklist": {},
            },
            elapsed_ms=100,
        )

        assert result.severity is Severity.CRITICAL


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
    result = AnalysisResult(
        modality=Modality.EKG,
        summary="Normal sinus rhythm",
        severity=Severity.NORMAL,
        findings=[],
        checklist=_full_ekg_checklist(),
    )
    result.layout = {
        "format": "12lead_rows",
        "leads": [
            {
                "name": name,
                "label_visible": True,
                "bbox": [0.0, index / 12, 1.0, 1 / 12],
            }
            for index, name in enumerate(
                [
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
                ]
            )
        ],
    }
    return result


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

    def test_empty_layout_marks_ekg_result_incomplete(self):
        validator = OutputValidator(strict=False)
        result = _make_result()
        result.layout = {}

        validated = validator.post_analyze(_make_request(), result)

        assert validated.incomplete is True
        assert "EKG layout is missing a lead inventory" in (
            validated.validation_warnings
        )

    def test_finding_cannot_claim_a_lead_absent_from_visible_inventory(self):
        validator = OutputValidator()
        request = AnalyzeRequest(
            image_base64="image",
            modality=Modality.EKG,
            valid_regions=["lead_II", "lead_V2"],
        )
        result = _make_result()
        result.layout["leads"] = [
            lead for lead in result.layout["leads"] if lead["name"] != "V2"
        ]
        result.findings = [
            Finding(
                id="missing-lead",
                regions=["lead_II", "lead_V2"],
                label="Localized change",
                detail="Candidate change",
                severity=Severity.WARNING,
                bboxes=[RegionRect(x=0.1, y=0.1, w=0.1, h=0.1)],
            )
        ]

        validated = validator.post_analyze(request, result)

        assert validated.findings[0].regions == ["lead_II"]
        assert any(
            "absent from the visible inventory: lead_V2" in warning
            for warning in validated.validation_warnings
        )
        assert validated.incomplete is True

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
        assert validated.findings[0].bboxes == []
        assert "boxes removed" in validated.validation_warnings[0]

    def test_low_confidence_box_gets_a_bounded_reviewer_question(self):
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
                confidence="low",
                question="",
            )
        ]

        validated = validator.post_analyze(_make_request(), result)

        finding = validated.findings[0]
        assert finding.bboxes
        assert "Possible ectopic beat" in finding.question
        assert "highlighted source-image region" in finding.question
        assert validated.incomplete is True
        assert validated.review_required is True

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
        assert any(
            "no accepted tight bbox" in item for item in validated.validation_warnings
        )


class TestNativeToolAuditTrace:
    def test_reads_only_records_appended_during_current_turn(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        audit_path = tmp_path / "bbox-audit.jsonl"
        source_sha = "c" * 64
        evidence_nonce = "d" * 32
        stale = {
            "schema_version": 2,
            "tool": "dicom_bbox_validate",
            "tool_call_id": "stale-call",
            "accepted_count": 1,
            "rejected_count": 0,
            "source_image_sha256": source_sha,
            "evidence_nonce": evidence_nonce,
            "accepted_boxes_sha256": "e" * 64,
            "details_sha256": "a" * 64,
        }
        audit_path.write_text(f"{json.dumps(stale)}\n", encoding="utf-8")
        monkeypatch.setenv("DICOM_BBOX_AUDIT_PATH", str(audit_path))
        client = OpenClawClient(gateway_token="test", base_dir=tmp_path)

        client._begin_run_trace(
            "analysis-current",
            bbox_evidence_nonce=evidence_nonce,
            source_image_sha256=source_sha,
        )
        current = stale | {
            "tool_call_id": "current-call",
            "details_sha256": "b" * 64,
        }
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{json.dumps(current)}\n")
            handle.write('{"tool":"invalid"}\n')

        trace = client.last_run_trace()

        assert trace["tools"] == ["dicom_bbox_validate"]
        assert [row["tool_call_id"] for row in trace["tool_audit"]] == ["current-call"]

    def test_boxed_result_requires_exact_bound_coordinate_receipt(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        audit_path = tmp_path / "bbox-audit.jsonl"
        monkeypatch.setenv("DICOM_BBOX_AUDIT_PATH", str(audit_path))
        client = OpenClawClient(gateway_token="test", base_dir=tmp_path)
        source_sha = "a" * 64
        evidence_nonce = "b" * 32
        box = RegionRect(0.1, 0.2, 0.3, 0.1)
        result = _make_result()
        result.findings = [
            Finding(
                id="f1",
                regions=["lead_II"],
                label="Candidate",
                detail="Visible candidate",
                severity=Severity.WARNING,
                bboxes=[box],
            )
        ]
        client._begin_run_trace(
            "analysis-bound",
            bbox_evidence_nonce=evidence_nonce,
            source_image_sha256=source_sha,
        )
        receipt = {
            "schema_version": 2,
            "tool": "dicom_bbox_validate",
            "tool_call_id": "bound-call",
            "accepted_count": 1,
            "rejected_count": 0,
            "source_image_sha256": source_sha,
            "evidence_nonce": evidence_nonce,
            "accepted_boxes_sha256": _bbox_coordinates_digest([box]),
            "details_sha256": "c" * 64,
        }
        audit_path.write_text(f"{json.dumps(receipt)}\n", encoding="utf-8")

        client._require_bound_bbox_receipt(result)

        result.findings[0] = Finding(
            id="f1",
            regions=["lead_II"],
            label="Candidate",
            detail="Visible candidate",
            severity=Severity.WARNING,
            bboxes=[RegionRect(0.2, 0.2, 0.3, 0.1)],
        )
        with pytest.raises(BboxEvidenceError):
            client._require_bound_bbox_receipt(result)

    def test_coarse_result_retracts_boxes_when_bound_tool_rejects_all(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        audit_path = tmp_path / "bbox-audit.jsonl"
        monkeypatch.setenv("DICOM_BBOX_AUDIT_PATH", str(audit_path))
        client = OpenClawClient(gateway_token="test", base_dir=tmp_path)
        source_sha = "a" * 64
        evidence_nonce = "b" * 32
        result = _make_result()
        result.findings = [
            Finding(
                id="f1",
                regions=["lead_II"],
                label="Candidate",
                detail="Unlocalized candidate",
                severity=Severity.WARNING,
                bboxes=[RegionRect(0.0, 0.0, 1.0, 1.0)],
            )
        ]
        client._begin_run_trace(
            "analysis-rejected",
            bbox_evidence_nonce=evidence_nonce,
            source_image_sha256=source_sha,
        )
        receipt = {
            "schema_version": 2,
            "tool": "dicom_bbox_validate",
            "tool_call_id": "rejected-call",
            "accepted_count": 0,
            "rejected_count": 1,
            "source_image_sha256": source_sha,
            "evidence_nonce": evidence_nonce,
            "accepted_boxes_sha256": _bbox_coordinates_digest([]),
            "details_sha256": "c" * 64,
        }
        audit_path.write_text(f"{json.dumps(receipt)}\n", encoding="utf-8")

        client._retract_tool_rejected_coarse_boxes(result)
        client._require_bound_bbox_receipt(result)

        assert result.findings[0].bboxes == []
        assert result.incomplete is True
        assert result.review_required is True
        assert result.analysis_trace[-1]["status"] == (
            "retracted_rejected_coarse_boxes"
        )
        assert result.analysis_trace[-1]["retracted_count"] == 1

    def test_reads_phi_free_ecg_founder_receipt_from_current_turn(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        audit_path = tmp_path / "ecgfounder-audit.jsonl"
        monkeypatch.setenv("DICOM_ECGFOUNDER_AUDIT_PATH", str(audit_path))
        client = OpenClawClient(gateway_token="test", base_dir=tmp_path)

        with client.use_waveform_artifact("wf-opaque-123") as evidence_nonce:
            client._begin_run_trace("analysis-ecg-founder")
            receipt = {
                "schema_version": 1,
                "tool": "ecg_founder_analyze_waveform",
                "tool_call_id": "ecg-call-1",
                "status": "ok",
                "evidence_nonce": evidence_nonce,
                "artifact_id_sha256": "a" * 64,
                "model_revision": "04edac702b61c91face519774ddcc0cd712fef23",
                "model_id": "PKUDigitalHealth/ECGFounder",
                "checkpoint_sha256": "b" * 64,
                "calibration_status": "uncalibrated",
                "prediction_count": 10,
                "predictions": [
                    {
                        "label": "LEFT VENTRICULAR HYPERTROPHY",
                        "probability": 0.42,
                    }
                ],
                "response_evidence": {
                    "rhythm_measurement": {
                        "method": "lead_II_qrs_energy_v1",
                        "lead": "II",
                        "status": "ok",
                        "diagnostic_scope": "rhythm_regularity_only",
                        "rr_interval_count": 6,
                        "rr_intervals_ms": [860, 720, 650, 810, 690, 840],
                        "median_rr_ms": 765.0,
                        "heart_rate_bpm_from_median_rr": 78.4,
                        "rr_cv": 0.11,
                        "rr_rmssd_ms": 130.0,
                        "rr_range_ms": 210.0,
                        "successive_rr_diff_over_80ms_fraction": 0.8,
                        "regularity_signal": "irregular",
                    }
                },
            }
            foreign_receipt = {
                **receipt,
                "tool_call_id": "foreign-call",
                "evidence_nonce": "f" * 32,
            }
            audit_path.write_text(
                f"{json.dumps(foreign_receipt)}\n{json.dumps(receipt)}\n",
                encoding="utf-8",
            )

            trace = client.last_run_trace()
            supporting = client._supporting_waveform_evidence()

        assert trace["tools"] == ["ecg_founder_analyze_waveform"]
        assert trace["tool_audit"] == [receipt]
        assert "artifact_id" not in trace["tool_audit"][0]
        assert supporting == {
            "status": "ok",
            "use_policy": "supporting_evidence_only",
            "calibration_status": "uncalibrated",
            "model_id": "PKUDigitalHealth/ECGFounder",
            "model_revision": "04edac702b61c91face519774ddcc0cd712fef23",
            "predictions": [
                {
                    "label": "LEFT VENTRICULAR HYPERTROPHY",
                    "uncalibrated_score": 0.42,
                }
            ],
            "rhythm_measurement": {
                "method": "lead_II_qrs_energy_v1",
                "lead": "II",
                "status": "ok",
                "diagnostic_scope": "rhythm_regularity_only",
                "rr_interval_count": 6,
                "rr_intervals_ms": [860, 720, 650, 810, 690, 840],
                "median_rr_ms": 765.0,
                "heart_rate_bpm_from_median_rr": 78.4,
                "rr_cv": 0.11,
                "rr_rmssd_ms": 130.0,
                "rr_range_ms": 210.0,
                "successive_rr_diff_over_80ms_fraction": 0.8,
                "regularity_signal": "irregular",
                "limitations": [
                    "R-peak timing only; it does not identify P waves or diagnose atrial fibrillation.",
                    "Ectopy, missed peaks, pacing, and artifact can also cause irregular intervals.",
                ],
            },
        }

    def test_waveform_binding_accumulates_receipts_across_turn_resets(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        audit_path = tmp_path / "ecgfounder-audit.jsonl"
        monkeypatch.setenv("DICOM_ECGFOUNDER_AUDIT_PATH", str(audit_path))
        client = OpenClawClient(gateway_token="test", base_dir=tmp_path)

        with client.use_waveform_artifact("wf-opaque-123") as evidence_nonce:
            for index in (1, 2):
                client._begin_run_trace(f"analysis-turn-{index}")
                receipt = {
                    "schema_version": 1,
                    "tool": "ecg_founder_analyze_waveform",
                    "tool_call_id": f"ecg-call-{index}",
                    "status": "ok",
                    "evidence_nonce": evidence_nonce,
                    "artifact_id_sha256": "a" * 64,
                    "checkpoint_sha256": "b" * 64,
                    "prediction_count": 1,
                }
                with audit_path.open("a", encoding="utf-8") as handle:
                    handle.write(f"{json.dumps(receipt)}\n")

        receipts = client.waveform_evidence_receipts(evidence_nonce)

        assert [row["tool_call_id"] for row in receipts] == [
            "ecg-call-1",
            "ecg-call-2",
        ]

    def test_waveform_binding_separates_suppressed_duplicate_attempts(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        audit_path = tmp_path / "ecgfounder-audit.jsonl"
        monkeypatch.setenv("DICOM_ECGFOUNDER_AUDIT_PATH", str(audit_path))
        client = OpenClawClient(gateway_token="test", base_dir=tmp_path)

        with client.use_waveform_artifact("wf-opaque-123") as evidence_nonce:
            receipt = {
                "schema_version": 1,
                "tool": "ecg_founder_analyze_waveform",
                "tool_call_id": "ecg-call-1",
                "status": "ok",
                "evidence_nonce": evidence_nonce,
                "artifact_id_sha256": "a" * 64,
                "checkpoint_sha256": "b" * 64,
                "prediction_count": 1,
            }
            duplicate = {
                "schema_version": 1,
                "tool": "ecg_founder_duplicate_suppressed",
                "original_tool": "ecg_founder_analyze_waveform",
                "tool_call_id": "ecg-call-2",
                "original_tool_call_id": "ecg-call-1",
                "status": "duplicate_suppressed",
                "original_status": "ok",
                "evidence_nonce": evidence_nonce,
                "artifact_id_sha256": "a" * 64,
                "request_sha256": "c" * 64,
            }
            audit_path.write_text(
                f"{json.dumps(receipt)}\n{json.dumps(duplicate)}\n",
                encoding="utf-8",
            )

        receipts = client.waveform_evidence_receipts(evidence_nonce)
        attempts = client.waveform_duplicate_attempts(evidence_nonce)

        assert [row["tool_call_id"] for row in receipts] == ["ecg-call-1"]
        assert [row["tool_call_id"] for row in attempts] == ["ecg-call-2"]


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
        assert profile["edge_pixel_ratio"] > 0.001
        assert profile["low_signal"] is False

    @pytest.mark.parametrize("fill", ["black", "gray"])
    def test_image_quality_profile_flags_uniform_dark_or_gray_crop(self, fill):
        buffer = io.BytesIO()
        Image.new("RGB", (200, 100), fill).save(buffer, format="PNG")

        profile = ImageProcessor().image_quality_profile(buffer.getvalue())

        assert profile["robust_dynamic_range"] == 0
        assert profile["edge_pixel_ratio"] == 0.0
        assert profile["low_signal"] is True

    def test_image_quality_profile_accepts_structured_dark_modality_crop(self):
        import PIL.ImageDraw

        buffer = io.BytesIO()
        image = Image.new("RGB", (240, 160), "black")
        draw = PIL.ImageDraw.Draw(image)
        draw.ellipse((35, 20, 205, 145), fill=(105, 105, 105))
        draw.ellipse((80, 55, 160, 120), fill=(205, 205, 205))
        image.save(buffer, format="PNG")

        profile = ImageProcessor().image_quality_profile(buffer.getvalue())

        assert profile["robust_dynamic_range"] > 8
        assert profile["edge_pixel_ratio"] > 0.001
        assert profile["low_signal"] is False

    def test_source_crop_audit_is_not_run_on_upscaled_model_pixels(self):
        image = Image.new("RGB", (320, 320), "white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        region = RegionRect(0.1, 0.1, 0.1, 0.1)
        processor = ImageProcessor()

        source_crop = processor.crop_region_bytes(encoded, region)
        model_crop = base64.b64decode(processor.crop_region_base64(encoded, region))

        assert Image.open(io.BytesIO(source_crop)).size == (32, 32)
        assert Image.open(io.BytesIO(model_crop)).size == (512, 512)
        profile = processor.image_quality_profile(source_crop)
        assert profile["source_short_edge_px"] == 32
        assert profile["insufficient_source_resolution"] is True
        assert profile["low_signal"] is True

    def test_source_crop_at_bottom_right_uses_last_real_pixel(self):
        image = Image.new("RGB", (10, 10), "white")
        image.putpixel((9, 9), (1, 2, 3))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

        cropped = Image.open(
            io.BytesIO(
                ImageProcessor().crop_region_bytes(
                    encoded,
                    RegionRect(0.99, 0.99, 0.01, 0.01),
                )
            )
        )

        assert cropped.size == (1, 1)
        assert cropped.getpixel((0, 0)) == (1, 2, 3)

    def test_thin_high_contrast_waveform_is_not_treated_as_blank(self):
        image = Image.new("RGB", (200, 100), "white")
        for x in range(10, 190):
            image.putpixel((x, 50), (0, 0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")

        profile = ImageProcessor().image_quality_profile(buffer.getvalue())

        assert profile["ink_pixel_ratio"] < 0.01
        assert profile["edge_pixel_ratio"] > 0.005
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

    @pytest.mark.parametrize(
        ("row_count", "expected"),
        [(12, True), (3, False), (8, False)],
    )
    def test_ekg_row_strip_evidence_requires_twelve_periodic_full_width_rows(
        self,
        row_count: int,
        expected: bool,
    ):
        width, height = 600, 480
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        for y in range(0, height, 10):
            draw.line((0, y, width - 1, y), fill=(255, 80, 80), width=1)
        for index in range(row_count):
            y = round((index + 0.5) * height / row_count)
            draw.line((30, y, width - 1, y), fill="black", width=3)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

        evidence = ImageProcessor().ekg_row_strip_evidence(encoded)

        assert evidence["is_12_row_strip"] is expected
        assert evidence["detected_row_count"] == row_count
        assert evidence["method"] == "local_black_ink_row_periodicity_v1"


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
