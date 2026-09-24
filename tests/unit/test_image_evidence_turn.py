"""Real client receive paths with synthetic Gateway frames; no paid model calls."""

from __future__ import annotations

import asyncio
import base64
import io
import json
from hashlib import sha256

import pytest
from PIL import Image

from dicom_overlay.application.execution_journal import ExecutionJournal, StageOutput
from dicom_overlay.infrastructure import openclaw_client as client_module
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
from dicom_overlay.infrastructure.scientific_draft import (
    ScientificDraftError,
    build_scientific_draft_prompt,
    decode_scientific_draft,
)
from dicom_overlay.infrastructure.strict_json import read_json_object
from medical_image_harness.models import Modality
from tests.unit.test_contract_assembly import inputs as inputs
from tests.unit.test_gateway_resilience_edges import _closed
from tests.unit.test_scientific_draft import draft_request as draft_request


def picture(kind="PNG", *, animated=False):
    buffer = io.BytesIO()
    image = Image.new("RGB", (32, 24), "white")
    other = Image.new("RGB", image.size, "black")
    image.save(
        buffer,
        format=kind,
        **({"save_all": True, "append_images": [other]} if animated else {}),
    )
    image.close()
    other.close()
    return buffer.getvalue()


SOURCE = picture()
BODY = ' \n{"draft_version":"1","summary":"合成", "x":1,"x":2}\n '


class Gateway:
    def __init__(self, body=BODY, variant="normal"):
        self.body, self.variant = body, variant
        self.sent, self.frames = [], []
        self.entered = asyncio.Event()

    async def send(self, raw):
        frame = json.loads(raw)
        self.sent.append(frame)
        if frame["method"] != "chat.send":
            return
        run = f"run-{len(self.sent)}"
        accepted = {
            "type": "res",
            "id": frame["id"],
            "ok": True,
            "payload": {"status": "accepted", "runId": run},
        }
        final = {
            "type": "event",
            "event": "chat",
            "payload": {
                "runId": run,
                "sessionKey": frame["params"]["sessionKey"],
                "state": "final",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": self.body}],
                },
            },
        }
        if self.variant == "wrong_session":
            final["payload"]["sessionKey"] = "another-session"
        elif self.variant == "canonical_session":
            key = frame["params"]["sessionKey"]
            final["payload"]["sessionKey"] = (
                key if key.startswith("agent:main:") else f"agent:main:{key}"
            )
        elif self.variant == "multiple_text":
            final["payload"]["message"]["content"] *= 2
        elif self.variant == "dict_only":
            final = {
                "type": "res",
                "id": frame["id"],
                "ok": True,
                "payload": {"runId": run, "result": {"summary": "not raw text"}},
            }
        elif self.variant == "thinking":
            final["payload"]["message"]["content"].insert(
                0, {"type": "thinking", "thinking": "private synthetic thought"}
            )
        if self.variant == "preaccept_loss":
            self.frames.append(_closed())
        elif self.variant == "postaccept_loss":
            self.frames.extend([accepted, _closed()])
        elif self.variant == "wait":
            self.frames.append(accepted)
        else:
            self.frames.extend([accepted, final])

    async def recv(self):
        await asyncio.sleep(0)
        if not self.frames:
            self.entered.set()
            await asyncio.Future()
        frame = self.frames.pop(0)
        if isinstance(frame, BaseException):
            raise frame
        return json.dumps(frame, ensure_ascii=False)

    async def close(self):
        pass


def connected(tmp_path, gateway=None, *, enabled=True):
    client = OpenClawClient(
        base_dir=tmp_path,
        gateway_token="synthetic-token",
        inference_timeout_sec=1,
        collect_transport_evidence=enabled,
    )
    client._ws = gateway or Gateway()
    client._connected = True
    client._gateway_protocol = 4
    return client


async def request(client, prompt="Synthetic stage schema"):
    return await client.request_image_evidence(
        prompt, image_bytes=SOURCE, deidentified=True
    )


async def test_scientific_request_names_main_agent_explicitly_before_strict_receipt(
    tmp_path,
):
    gateway = Gateway(variant="canonical_session")
    result = await request(connected(tmp_path, gateway))
    sent = gateway.sent[0]["params"]["sessionKey"]
    assert sent.startswith("agent:main:image-evidence-")
    assert result.gateway.session_key == sent
    assert result.gateway.require_model_text() == BODY.encode()


@pytest.mark.parametrize("agent", ["other", "MAIN", "main "])
async def test_scientific_receipt_never_accepts_another_agent_namespace(
    tmp_path, agent
):
    class WrongAgentGateway(Gateway):
        async def send(self, raw):
            await super().send(raw)
            requested = self.sent[-1]["params"]["sessionKey"]
            short = requested.removeprefix("agent:main:")
            self.frames[-1]["payload"]["sessionKey"] = f"agent:{agent}:{short}"

    with pytest.raises(ValueError, match="gateway_session_identity_changed"):
        await request(connected(tmp_path, WrongAgentGateway()))


@pytest.mark.asyncio
async def test_exact_bytes_source_prompt_and_fresh_session_binding(
    tmp_path, monkeypatch
):
    gateway = Gateway(variant="thinking")
    client = connected(tmp_path, gateway)

    def forbidden(*args, **kwargs):
        pytest.fail("legacy result parser must not consume a scientific response")

    monkeypatch.setattr(client, "_parse_result", forbidden)
    first = await request(client)
    frame = gateway.sent[0]
    assert frame["method"] == "chat.send"
    attachment = frame["params"]["attachments"][0]
    assert attachment["mimeType"] == "image/png"
    assert base64.b64decode(attachment["content"]) == SOURCE
    assert first.image_sha256 == sha256(SOURCE).hexdigest()
    assert (
        first.prompt_sha256 == sha256(frame["params"]["message"].encode()).hexdigest()
    )
    assert first.image_sha256 in frame["params"]["message"]
    assert first.bbox_evidence_nonce in frame["params"]["message"]
    assert len(first.bbox_evidence_nonce) == 32 and first.elapsed_ms >= 0
    assert first.gateway.require_model_text() == BODY.encode()
    assert "private synthetic thought" not in repr(first)
    assert "合成" not in repr(first)
    second = await request(client, "Another synthetic stage")
    assert first.gateway.require_model_text() == BODY.encode()
    assert first.gateway.request_id != second.gateway.request_id
    assert first.gateway.session_key != second.gateway.session_key
    assert first.bbox_evidence_nonce != second.bbox_evidence_nonce
    assert client.transport_evidence() == second.gateway
    assert client.last_run_trace()["parse_retry_count"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "variant",
    [
        "disabled",
        "deid_false",
        "deid_int",
        "mutable",
        "empty",
        "too_large",
        "not_image",
        "jpeg",
        "animated",
        "empty_prompt",
        "nontext_prompt",
        "surrogate_prompt",
        "long_prompt",
        "disconnected",
        "unverified_protocol",
        "request_limit",
    ],
)
async def test_invalid_request_never_sends_model_turn(tmp_path, monkeypatch, variant):
    client = connected(tmp_path, enabled=variant != "disabled")
    raw, prompt, deid = SOURCE, "stage", True
    if variant == "deid_false":
        deid = False
    elif variant == "deid_int":
        deid = 1
    elif variant == "mutable":
        raw = bytearray(SOURCE)
    elif variant == "empty":
        raw = b""
    elif variant == "too_large":
        raw = b"x" * (32 * 1024 * 1024 + 1)
    elif variant == "not_image":
        raw = b"not-an-image"
    elif variant == "jpeg":
        raw = picture("JPEG")
    elif variant == "animated":
        raw = picture(animated=True)
    elif variant == "empty_prompt":
        prompt = " \n"
    elif variant == "nontext_prompt":
        prompt = None
    elif variant == "surrogate_prompt":
        prompt = "\ud800"
    elif variant == "long_prompt":
        prompt = "x" * (512 * 1024 + 1)
    elif variant == "disconnected":
        client._connected = False
    elif variant == "unverified_protocol":
        client._gateway_protocol = None
    elif variant == "request_limit":
        monkeypatch.setattr(client_module, "_MAX_WS_MESSAGE_BYTES", 10)
    with pytest.raises((ValueError, ConnectionError)):
        await client.request_image_evidence(prompt, image_bytes=raw, deidentified=deid)
    assert client._ws.sent == []
    assert client.transport_evidence() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["wrong_session", "multiple_text", "dict_only"])
async def test_missing_exact_output_or_wrong_identity_fails_without_retry(
    tmp_path, variant
):
    gateway = Gateway(variant=variant)
    client = connected(tmp_path, gateway)
    with pytest.raises(ValueError):
        await request(client)
    assert len(gateway.sent) == 1
    assert client.transport_evidence().failure


@pytest.mark.asyncio
async def test_concurrent_callers_receive_their_own_snapshot(tmp_path):
    client = connected(tmp_path)
    first, second = await asyncio.gather(
        request(client, "first"), request(client, "second")
    )
    assert first.gateway.request_id != second.gateway.request_id
    assert first.gateway.session_key != second.gateway.session_key
    assert first.prompt_sha256 != second.prompt_sha256
    assert first.gateway.terminal_seen and second.gateway.terminal_seen
    assert len(client._ws.sent) == 2


@pytest.mark.asyncio
async def test_cancel_aborts_accepted_turn_and_retains_nonterminal_snapshot(tmp_path):
    gateway = Gateway(variant="wait")
    client = connected(tmp_path, gateway)
    task = asyncio.create_task(request(client))
    await gateway.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [frame["method"] for frame in gateway.sent] == ["chat.send", "chat.abort"]
    assert not client.transport_evidence().terminal_seen
    assert client.last_run_trace()["turn_aborted"]


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted", [False, True])
async def test_recovery_preserves_paid_turn_identity(tmp_path, monkeypatch, accepted):
    first = Gateway(variant="postaccept_loss" if accepted else "preaccept_loss")
    second = Gateway()
    client = connected(tmp_path, first)

    async def reconnect():
        client._ws, client._connected = second, True
        if accepted:
            # The resumed stream supplies only final output, not another send.
            sent = first.sent[0]
            second.frames.append(
                {
                    "type": "event",
                    "event": "chat",
                    "payload": {
                        "runId": "run-1",
                        "sessionKey": sent["params"]["sessionKey"],
                        "state": "final",
                        "message": {"content": [{"type": "text", "text": BODY}]},
                    },
                }
            )

    monkeypatch.setattr(client, "_reconnect_interrupted_turn", reconnect)
    receipt = await request(client)
    assert receipt.gateway.require_model_text() == BODY.encode()
    assert len(first.sent) == 1
    assert second.sent == ([] if accepted else first.sent)


@pytest.mark.asyncio
async def test_journal_uses_original_qc_response_and_stops_non_diagnostic_inference(
    tmp_path,
):
    qc = {
        "adequacy": "non_diagnostic",
        "issues": ["synthetic incomplete input"],
        "detail": "Synthetic quality response",
        "views_present": [],
        "views_required": [],
    }
    raw = json.dumps(qc)
    client = connected(tmp_path, Gateway(raw))
    journal = ExecutionJournal(SOURCE, deidentified=True)

    async def intake():
        return StageOutput(None, (SOURCE,))

    async def check_quality():
        turn = await request(client, "Synthetic QC schema")
        body = turn.gateway.require_model_text()
        return StageOutput(read_json_object(body), (body,))

    await journal.execute("intake", intake)
    await journal.execute("quality_gate", check_quality)
    assert journal.snapshot()[-1].artifact_sha256 == (sha256(raw.encode()).hexdigest(),)
    with pytest.raises(ValueError, match="non_diagnostic_inference_forbidden"):
        await journal.execute("blind_pass", check_quality)
    assert len(client._ws.sent) == 1


@pytest.mark.asyncio
async def test_scientific_decoder_consumes_original_reply_without_legacy_coercion(
    tmp_path, draft_request
):
    payload, host = draft_request
    raw = " \n" + json.dumps(payload, ensure_ascii=False) + "\n "
    client = connected(tmp_path, Gateway(raw))
    turn = await request(
        client, build_scientific_draft_prompt(Modality.EKG, host["trusted_evidence"])
    )
    decoded = decode_scientific_draft(
        turn.gateway.require_model_text(),
        modality=Modality.EKG,
        trusted_evidence=host["trusted_evidence"],
        model_used="synthetic",
        elapsed_ms=turn.elapsed_ms,
    )
    assert decoded.response_bytes == raw.encode()
    assert decoded.draft.observations
    assert not decoded.draft.workflow_events and decoded.draft.input_provenance is None
    client._ws.body = BODY  # Duplicate keys must survive transport, then fail decoding.
    malformed = await request(client)
    with pytest.raises(ScientificDraftError):
        decode_scientific_draft(
            malformed.gateway.require_model_text(),
            modality=Modality.EKG,
            trusted_evidence=host["trusted_evidence"],
            model_used="synthetic",
            elapsed_ms=0,
        )
    assert len(client._ws.sent) == 2  # No paid parse retry was added.
