"""Synthetic public-frame replays; no live Gateway/model or execution attestation."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from hashlib import sha256

import pytest

from dicom_overlay.infrastructure.gateway_evidence import GatewayEvidenceCollector
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
from dicom_overlay.infrastructure.strict_json import StrictJSONError, read_json_object
from tests.unit.test_gateway_resilience_edges import _closed, _ScriptedWebSocket

BODY = ' \n{"draft_version":"1","summary":"合成文字", "x":1,"x":2}\n '


def acceptance(run="run-1"):
    return {
        "type": "res",
        "id": "request-1",
        "ok": True,
        "payload": {"status": "accepted", "runId": run},
    }


def final(text=BODY, run="run-1"):
    return {
        "type": "event",
        "event": "chat",
        "payload": {
            "runId": run,
            "sessionKey": "session-1",
            "state": "final",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
            },
        },
    }


def tool(text='{"accepted":[]}', call="call-1"):
    return {
        "type": "event",
        "event": "agent",
        "payload": {
            "runId": "run-1",
            "sessionKey": "session-1",
            "stream": "tool",
            "data": {
                "phase": "result",
                "name": "dicom_bbox_validate",
                "toolCallId": call,
                "result": {"content": [{"type": "text", "text": text}]},
            },
        },
    }


def observe(collector, *frames):
    for frame in frames:
        collector.observe(json.dumps(frame, ensure_ascii=False))
    return collector.snapshot()


@pytest.fixture
def collector():
    return GatewayEvidenceCollector("request-1", "session-1")


def test_exact_visible_text_no_strip_repair_or_thought_retention(collector):
    message = final()
    message["payload"]["message"]["content"].insert(
        0, {"type": "thinking", "thinking": "synthetic-private-reasoning"}
    )
    receipt = observe(collector, acceptance(), tool(), message)
    assert receipt.require_model_text() == BODY.encode()
    assert receipt.model_text_sha256 == sha256(BODY.encode()).hexdigest()
    assert receipt.native_tools[0].text_bytes == b'{"accepted":[]}'
    assert "合成文字" not in repr(receipt)
    assert "session-1" not in repr(receipt)
    assert "synthetic-private-reasoning" not in repr(vars(collector))
    assert b'"x":1,"x":2' in receipt.model_text_bytes


def test_snapshot_is_immutable_and_does_not_alias_later_collector(collector):
    first = observe(collector, acceptance(), tool())
    second = observe(collector, final())
    assert first.model_text_bytes is None and not first.terminal_seen
    assert second.terminal_seen
    with pytest.raises(AttributeError):
        first.run_id = "other"


@pytest.mark.parametrize(
    "variant",
    [
        "unknown_run",
        "unknown_request",
        "pre_acceptance",
        "wrong_event",
        "delta",
        "reasoning",
        "other_tool",
        "start",
    ],
)
def test_unrelated_or_nonterminal_content_not_promoted(collector, variant):
    frame = final("unrelated-synthetic-text")
    if variant != "pre_acceptance":
        observe(collector, acceptance())
    if variant == "unknown_run":
        frame["payload"]["runId"] = "other"
    elif variant == "unknown_request":
        frame = acceptance()
        frame["id"] = "other"
        frame["payload"]["result"] = {"text": "unrelated-synthetic-text"}
    elif variant == "wrong_event":
        frame["event"] = "other"
    elif variant == "delta":
        frame["payload"]["state"] = "delta"
    elif variant == "reasoning":
        frame = tool()
        frame["payload"]["stream"] = "reasoning"
    elif variant == "other_tool":
        frame = tool()
        frame["payload"]["data"]["name"] = "unrelated_tool"
    elif variant == "start":
        frame = tool()
        frame["payload"]["data"]["phase"] = "start"
    receipt = observe(collector, frame)
    assert not receipt.failure and not receipt.terminal_seen
    assert receipt.model_text_bytes is None and not receipt.native_tools


@pytest.mark.parametrize(
    "variant,error",
    [
        ("run_changed", "gateway_run_identity_changed"),
        ("session_changed", "gateway_session_identity_changed"),
        ("role", "gateway_final_role_invalid"),
        ("error", "gateway_run_failed"),
        ("aborted", "gateway_run_failed"),
        ("empty", "gateway_original_model_text_missing"),
        ("multiple_texts", "gateway_original_model_text_missing"),
        ("nonstring", "gateway_original_model_text_missing"),
        ("tool_missing_id", "gateway_native_call_identity_missing"),
        ("tool_error", "gateway_native_tool_failed"),
        ("tool_data_error", "gateway_native_tool_failed"),
        ("tool_summary_only", "gateway_original_tool_text_missing"),
    ],
)
def test_identity_terminal_and_tool_failures_are_explicit(collector, variant, error):
    observe(collector, acceptance())
    frame = final()
    if variant == "run_changed":
        frame = acceptance("other")
    elif variant == "session_changed":
        frame["payload"]["sessionKey"] = "other"
    elif variant == "role":
        frame["payload"]["message"]["role"] = "user"
    elif variant in {"error", "aborted"}:
        frame["payload"]["state"] = variant
    elif variant == "empty":
        frame["payload"]["message"]["content"] = []
    elif variant == "multiple_texts":
        frame["payload"]["message"]["content"] *= 2
    elif variant == "nonstring":
        frame["payload"]["message"]["content"][0]["text"] = 42
    else:
        frame = tool()
        data = frame["payload"]["data"]
        if variant == "tool_missing_id":
            data.pop("toolCallId")
        elif variant == "tool_error":
            data["result"]["isError"] = True
        elif variant == "tool_data_error":
            data["isError"] = True
        else:
            data["result"] = "sanitized summary, not exact content"
    receipt = observe(collector, frame, final())
    assert receipt.failure == error
    with pytest.raises(ValueError, match=f"^{error}$"):
        receipt.require_model_text()


def test_request_error_without_payload_is_not_left_pending(collector):
    receipt = observe(collector, {"type": "res", "id": "request-1", "ok": False})
    assert receipt.failure == "gateway_request_failed"


def test_reconnect_acceptance_and_identical_tool_replay_deduplicate(collector):
    receipt = observe(collector, acceptance(), tool(), acceptance(), tool(), final())
    assert not receipt.failure and len(receipt.native_tools) == 1
    assert receipt.require_model_text() == BODY.encode()


def test_conflicting_tool_result_fails_instead_of_overwriting(collector):
    receipt = observe(collector, acceptance(), tool("first"), tool("changed"))
    assert receipt.failure == "gateway_native_result_conflict"
    assert receipt.native_tools[0].text_bytes == b"first"


def test_late_messages_cannot_mutate_terminal_receipt(collector):
    first = observe(collector, acceptance(), final())
    second = observe(collector, final("late"), tool())
    assert first == second


@pytest.mark.parametrize("has_run", [False, True])
def test_direct_text_requires_run_identity_but_preserves_bytes(collector, has_run):
    payload = {"result": {"text": BODY}}
    if has_run:
        payload["runId"] = "run-1"
    receipt = observe(
        collector, {"type": "res", "id": "request-1", "ok": True, "payload": payload}
    )
    if has_run:
        assert receipt.require_model_text() == BODY.encode()
    else:
        assert receipt.failure == "gateway_run_identity_missing"


def test_structured_result_is_not_reserialized_as_original_model_text(collector):
    receipt = observe(
        collector,
        {
            "type": "res",
            "id": "request-1",
            "ok": True,
            "payload": {"runId": "run-1", "result": {"draft_version": "1"}},
        },
    )
    assert receipt.failure == "gateway_original_model_text_missing"


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":"\\ud800"}', "[]"])
def test_invalid_gateway_envelopes_fail_closed(collector, raw):
    collector.observe(raw)
    assert collector.snapshot().failure == "gateway_evidence_frame_invalid"


def test_native_result_count_limit(collector):
    observe(collector, acceptance())
    for index in range(65):
        observe(collector, tool(call=f"call-{index}"))
    receipt = collector.snapshot()
    assert receipt.failure == "gateway_native_result_count_limit"
    assert len(receipt.native_tools) == 64


def test_total_byte_limit_is_bounded(collector):
    observe(collector, acceptance())
    for index in range(10):
        observe(collector, tool("a" * 500_000, call=f"call-{index}"))
    receipt = collector.snapshot()
    assert receipt.failure == "gateway_evidence_size_limit"
    assert sum(len(item.text_bytes) for item in receipt.native_tools) <= 4 * 1024 * 1024


class Socket:
    def __init__(self, frames):
        self.frames = iter(json.dumps(frame, ensure_ascii=False) for frame in frames)
        self.sent = []

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        try:
            return next(self.frames)
        except StopIteration:
            await asyncio.Future()


@pytest.mark.asyncio
@pytest.mark.parametrize("text_mode", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
async def test_real_client_waiters_capture_before_legacy_parsing(
    tmp_path, enabled, text_mode
):
    client = OpenClawClient(
        base_dir=tmp_path,
        gateway_token="synthetic-token",
        collect_transport_evidence=enabled,
    )
    client._connected = True
    client._ws = Socket([acceptance(), tool(), final()])
    frame = {
        "type": "req",
        "id": "request-1",
        "method": "chat.send",
        "params": {"sessionKey": "session-1", "message": "synthetic"},
    }
    output = await client._send_chat_frame_with_recovery(frame, expect_text=text_mode)
    receipt = client.transport_evidence()
    if enabled:
        assert receipt.require_model_text() == BODY.encode()
        assert receipt.native_tools[0].tool_call_id == "call-1"
    else:
        assert receipt is None
    assert output == BODY.strip() if text_mode else output["x"] == 2
    assert len(client._ws.sent) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_handshake_declares_tool_events_only_when_implemented(tmp_path, enabled):
    client = OpenClawClient(
        base_dir=tmp_path,
        gateway_token="synthetic-token",
        collect_transport_evidence=enabled,
    )
    client._ws = Socket(
        [
            {
                "type": "res",
                "id": "connect-1",
                "ok": True,
                "payload": {
                    "type": "hello-ok",
                    "protocol": 4,
                    "server": {"version": "2026.9.3"},
                },
            }
        ]
    )
    await client._handshake()
    assert client._ws.sent[0]["params"].get("caps", []) == (
        ["tool-events"] if enabled else []
    )


@pytest.mark.asyncio
async def test_second_send_clears_current_receipt_without_mutating_prior_snapshot(
    tmp_path,
):
    client = OpenClawClient(
        base_dir=tmp_path,
        gateway_token="synthetic-token",
        collect_transport_evidence=True,
    )
    client._connected = True
    client._ws = Socket(
        [acceptance(), final(), acceptance("run-2"), final("second", "run-2")]
    )
    frame = {
        "type": "req",
        "id": "request-1",
        "method": "chat.send",
        "params": {"sessionKey": "session-1"},
    }
    await client._send_chat_text_frame(deepcopy(frame))
    previous = client.transport_evidence()
    await client._send_chat_text_frame(frame)
    assert previous.require_model_text() == BODY.encode()
    assert client.transport_evidence().require_model_text() == b"second"


def test_flag_is_strict_boolean(tmp_path):
    with pytest.raises(
        ValueError, match="collect_transport_evidence must be a boolean"
    ):
        OpenClawClient(base_dir=tmp_path, collect_transport_evidence="false")


def test_missing_tool_content_is_not_reconstructed_from_model_text(collector):
    receipt = observe(collector, acceptance(), final('{"toolCallId":"call-1"}'))
    with pytest.raises(ValueError, match=r"^gateway_native_tool_text_missing$"):
        receipt.require_native_tool_text("call-1")


def test_exact_duplicate_keys_still_rejected_after_transport_capture(collector):
    receipt = observe(collector, acceptance(), final())
    with pytest.raises(StrictJSONError, match=r"^duplicate_json_key$"):
        read_json_object(receipt.require_model_text())


@pytest.mark.parametrize("run_id", [True, 42, "", " ", "a" * 257])
def test_run_identity_is_not_coerced_or_unbounded(collector, run_id):
    receipt = observe(collector, acceptance(run_id))
    assert receipt.failure == "gateway_run_identity_invalid"


def test_native_identity_storage_is_bounded(collector):
    receipt = observe(collector, acceptance(), tool(call="a" * 257))
    assert receipt.failure == "gateway_native_call_identity_missing"


def test_acceptance_session_must_match_when_supplied(collector):
    frame = acceptance()
    frame["payload"]["sessionKey"] = "other"
    assert observe(collector, frame).failure == "gateway_session_identity_changed"


@pytest.mark.asyncio
async def test_postaccept_recovery_preserves_evidence_without_extra_send(
    tmp_path, monkeypatch
):
    client = OpenClawClient(
        base_dir=tmp_path,
        gateway_token="synthetic-token",
        collect_transport_evidence=True,
    )
    first = _ScriptedWebSocket([acceptance(), tool(), _closed()])
    resumed = _ScriptedWebSocket([tool(), final()])
    client._ws = first
    client._connected = True

    async def reconnect():
        client._ws = resumed
        client._connected = True

    monkeypatch.setattr(client, "connect", reconnect)
    frame = {
        "type": "req",
        "id": "request-1",
        "method": "chat.send",
        "params": {"sessionKey": "session-1"},
    }
    await client._send_chat_text_frame(frame)
    receipt = client.transport_evidence()
    assert receipt.require_model_text() == BODY.encode()
    assert receipt.require_native_tool_text("call-1").text_bytes == b'{"accepted":[]}'
    assert len(receipt.native_tools) == 1
    assert len(first.sent) == 1 and not resumed.sent


@pytest.mark.asyncio
async def test_preaccept_retry_uses_same_identity_and_collects_once(
    tmp_path, monkeypatch
):
    client = OpenClawClient(
        base_dir=tmp_path,
        gateway_token="synthetic-token",
        collect_transport_evidence=True,
    )
    first = _ScriptedWebSocket([_closed()])
    resumed = _ScriptedWebSocket([acceptance(), tool(), final()])
    client._ws = first
    client._connected = True

    async def reconnect():
        client._ws = resumed
        client._connected = True

    monkeypatch.setattr(client, "connect", reconnect)
    frame = {
        "type": "req",
        "id": "request-1",
        "method": "chat.send",
        "params": {"sessionKey": "session-1", "idempotencyKey": "fixed"},
    }
    await client._send_chat_text_frame(frame)
    assert first.sent == resumed.sent == [frame]
    assert client.transport_evidence().require_model_text() == BODY.encode()


def test_tool_rejection_preserves_later_model_body_but_not_as_usable_evidence(
    collector,
):
    bad = tool()
    bad["payload"]["data"]["result"] = "sanitized"
    receipt = observe(collector, acceptance(), bad, final())
    assert receipt.failure == "gateway_original_tool_text_missing"
    assert receipt.model_text_bytes == BODY.encode()
    assert receipt.model_text_sha256 == sha256(BODY.encode()).hexdigest()
    with pytest.raises(ValueError, match=r"^gateway_original_tool_text_missing$"):
        receipt.require_model_text()


@pytest.mark.asyncio
async def test_binary_event_buffered_during_handshake_is_decoded_before_collection(
    tmp_path,
):
    client = OpenClawClient(
        base_dir=tmp_path,
        gateway_token="synthetic-token",
        collect_transport_evidence=True,
    )
    client._connected = True
    client._ws = Socket([])
    client._pending_frames.extend(
        [
            json.dumps(acceptance()).encode(),
            json.dumps(final(), ensure_ascii=False).encode(),
        ]
    )
    await client._send_chat_text_frame(
        {
            "type": "req",
            "id": "request-1",
            "method": "chat.send",
            "params": {"sessionKey": "session-1"},
        }
    )
    assert client.transport_evidence().require_model_text() == BODY.encode()
