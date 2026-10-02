"""Real loopback WebSocket, synthetic pixels/replies: not clinical acceptance."""

from __future__ import annotations

import base64
import json
from hashlib import sha256

import pytest
import websockets

from dicom_overlay.application.reading_contract import contract_identity
from dicom_overlay.domain.generated_clinical_rules import READING_CONTRACT
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
from dicom_overlay.infrastructure.scientific_image_session import ScientificImageSession
from medical_image_harness.models import Modality
from medical_image_harness.profiles import default_registry
from tests.scientific_delta_fixture import scripted_delta
from tests.unit.test_contract_assembly import inputs as inputs
from tests.unit.test_image_evidence_turn import SOURCE
from tests.unit.test_scientific_draft import draft_request as draft_request
from tests.unit.test_scientific_image_session import replies as replies
from tests.unit.test_scientific_reconciliation import envelope


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("modality", [Modality.EKG, Modality.CXR, Modality.CT_BRAIN])
async def test_yaml_contract_reaches_each_wire_turn_and_hash_bound_receipt(
    tmp_path, replies, modality
):
    qc, draft = replies
    draft["modality"] = modality.value
    draft["checklist"] = {
        key: {
            "value": "Synthetic unassessable axis",
            "status": "info",
            "assessable": False,
        }
        for key in default_registry().get(modality.value).checklist_keys
    }
    responses = [
        qc,
        draft,
        {"status": "unavailable", "reason": "No synthetic box."},
        envelope(draft),
        envelope(draft),
    ]
    frames = []

    async def handler(socket):
        connect = json.loads(await socket.recv())
        assert connect["method"] == "connect"
        await socket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": connect["id"],
                    "ok": True,
                    "payload": {
                        "type": "hello-ok",
                        "protocol": 4,
                        "server": {"version": "2026.9.3"},
                    },
                }
            )
        )
        async for raw in socket:
            frame = json.loads(raw)
            frames.append(frame)
            assert frame["method"] == "chat.send"
            index = len(frames) - 1
            response = scripted_delta(frame["params"]["message"], responses[index])
            run = f"synthetic-{index}"
            await socket.send(
                json.dumps(
                    {
                        "type": "res",
                        "id": frame["id"],
                        "ok": True,
                        "payload": {"status": "accepted", "runId": run},
                    }
                )
            )
            await socket.send(
                json.dumps(
                    {
                        "type": "event",
                        "event": "chat",
                        "payload": {
                            "runId": run,
                            "sessionKey": frame["params"]["sessionKey"],
                            "state": "final",
                            "message": {
                                "role": "assistant",
                                "content": [
                                    {"type": "text", "text": json.dumps(response)}
                                ],
                            },
                        },
                    }
                )
            )

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = OpenClawClient(
            gateway_url=f"ws://127.0.0.1:{port}",
            gateway_token="synthetic-loopback-only",
            base_dir=tmp_path,
            timeout_sec=5,
            collect_transport_evidence=True,
        )
        try:
            await client.connect()
            reader = ScientificImageSession(
                client,
                image_bytes=SOURCE,
                modality=modality,
                deidentified=True,
                receipt_root=tmp_path / "receipts",
            )
            await reader.read_blind()
            await reader.localize_and_reconcile()
            await reader.targeted_second_look()
        finally:
            await client.disconnect()

    stages = list(READING_CONTRACT["stages"])
    assert len(frames) == len(stages) == 5  # No extra request or automatic retry.
    saved = sorted((tmp_path / "receipts").glob("*/turn-*/receipt.json"))
    assert len(saved) == 5
    for stage, frame, path in zip(stages, frames, saved, strict=True):
        prompt = frame["params"]["message"]
        identity = contract_identity(stage)
        assert "READING CONTRACT: " + json.dumps(identity, sort_keys=True) in prompt
        for step in READING_CONTRACT["stages"][stage]:
            assert f"[{step['id']}] {step['instruction']}" in prompt
        guided = (
            stage in {"reconcile", "targeted_second_look"}
            and modality != Modality.CT_BRAIN
        )
        assert ("CONDITIONAL CLINICAL GUIDANCE:" in prompt) is guided
        for rule in READING_CONTRACT["rules"]:
            assert (rule["rule_id"] in prompt) is (
                guided and rule["modality"] == modality.value
            )
        assert base64.b64decode(frame["params"]["attachments"][0]["content"]) == SOURCE
        receipt = json.loads(path.read_text("utf-8"))
        assert receipt["reading_contract"] == identity
        assert receipt["prompt_sha256"] == sha256(prompt.encode()).hexdigest()
        assert receipt["image_sha256"] == sha256(SOURCE).hexdigest()
        assert receipt["terminal_seen"] is True
    assert (
        reader.final_result is None
    )  # No physician review or GUI acceptance fabricated.
