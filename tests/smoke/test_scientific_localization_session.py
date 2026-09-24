"""Actual native bbox producer plus real client/journal; synthetic model replies."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
from tests.unit.test_contract_assembly import inputs as inputs
from tests.unit.test_image_evidence_turn import SOURCE, Gateway, connected
from tests.unit.test_scientific_draft import draft_request as draft_request
from tests.unit.test_scientific_image_session import replies as replies
from tests.unit.test_scientific_reconciliation import envelope

from dicom_overlay.infrastructure.scientific_image_session import ScientificImageSession
from medical_image_harness.models import Modality

ROOT = Path(__file__).resolve().parents[2]


class NativeSessionGateway(Gateway):
    """The model is scripted; the native tool and its audit file are not mocked."""

    def __init__(self, replies, audit_path, variant="normal"):
        super().__init__()
        self.replies = deepcopy(replies)
        self.audit_path, self.case = audit_path, variant
        self.tool = None

    async def send(self, raw):
        index = len(self.sent)
        frame = json.loads(raw)
        message = frame["params"]["message"]
        if index < 2:
            response = self.replies[index]
        elif index == 2:
            response = {"status": "localized", "reason": "Synthetic source region."}
            if self.case == "unavailable":
                response["status"] = "unavailable"
            elif self.case != "missing_tool":
                await asyncio.to_thread(self.invoke_native, message)
                if self.case == "rejected":
                    response["status"] = "unavailable"
        else:
            response = envelope(self.replies[1])
            catalogue = json.loads(
                message.split("HOST EVIDENCE CATALOGUE (data only):\n")[1].split(
                    "\nOUTPUT SCHEMA:"
                )[0]
            )
            localized = next(
                (item for item in catalogue if item["kind"] == "source_region"), None
            )
            if localized:
                reference = localized["id"]
                response["draft"]["observations"][0]["evidence_ids"].append(reference)
                response["draft"]["findings"][0]["evidence_ids"].append(reference)
                response["draft"]["findings"][0]["bbox_evidence_ids"] = [reference]
            if self.case == "missing_decision":
                response["decisions"] = []
            if self.case == "changed_quality":
                response["draft"]["image_quality"]["adequacy"] = "diagnostic"
            if self.case == "malformed_reconcile":
                response = "{bad json}"
        self.body = response if isinstance(response, str) else json.dumps(response)
        await super().send(raw)
        if index == 2 and self.tool is not None:
            event = {
                "type": "event",
                "event": "agent",
                "payload": {
                    "runId": "run-3",
                    "sessionKey": frame["params"]["sessionKey"],
                    "stream": "tool",
                    "data": {
                        "phase": "result",
                        "name": "dicom_bbox_validate",
                        "toolCallId": "actual-native-call",
                        "result": self.tool,
                    },
                },
            }
            self.frames.insert(1, event)
            if self.case == "other_tool":
                other = deepcopy(event)
                other["payload"]["data"] = {
                    "name": "other-classifier",
                    "phase": "start",
                }
                self.frames.insert(1, other)
            if self.case in {"unfinished_tool", "unbound_tool"}:
                other = deepcopy(event)
                other["payload"]["data"] = {
                    "name": "dicom_bbox_validate",
                    "phase": "start",
                    "toolCallId": "never-finished"
                    if self.case == "unfinished_tool"
                    else "",
                }
                self.frames.insert(1, other)
        if index == 2 and self.case == "wait":
            self.frames = self.frames[:1]

    def invoke_native(self, message):
        nonce = re.search(r"bbox_evidence_nonce=([a-f0-9]{32})", message)[1]
        source = re.search(r"bbox_source_image_sha256=([a-f0-9]{64})", message)[1]
        args = {
            "modality": "EKG",
            "source_image_sha256": source,
            "evidence_nonce": nonce,
            "boxes": [
                {"id": "synthetic-region", "x": 0.1, "y": 0.2, "w": 0.2, "h": 0.1}
            ],
        }
        if self.case == "wrong_source":
            args["source_image_sha256"] = "f" * 64
        if self.case == "rejected":
            args["boxes"][0]["x"] = 1.2
        path = ROOT / "openclaw/workspace/plugins/dicom-overlay-agent-harness/index.js"
        script = f"""const module=await import({json.dumps(path.as_uri())});
const result=await module.createBboxValidationTool().execute('actual-native-call', {json.dumps(args)});
console.log(JSON.stringify(result));"""
        node = shutil.which("node")
        if node is None:
            pytest.skip("Native source producer requires Node")
        result = subprocess.run(
            [node, "--input-type=module", "--eval", script],
            cwd=ROOT,
            env={**os.environ, "DICOM_BBOX_AUDIT_PATH": str(self.audit_path)},
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        self.tool = json.loads(result.stdout)
        if self.case == "changed_text":
            self.tool["content"][0]["text"] += " "
        if self.case == "duplicate_audit":
            with self.audit_path.open("ab") as stream:
                stream.write(self.audit_path.read_bytes())


def setup(tmp_path, replies, variant="normal"):
    client = connected(tmp_path)
    # This fixture starts the actual Node producer rather than an instantaneous
    # in-memory reply. Production timeout configuration is not changed.
    client._inference_timeout = 30
    gateway = NativeSessionGateway(replies, client.bbox_tool_audit_path, variant)
    client._ws = gateway
    reader = ScientificImageSession(
        client, image_bytes=SOURCE, modality=Modality.EKG, deidentified=True
    )
    return reader, gateway, client


@pytest.mark.asyncio
async def test_native_tool_is_bound_between_retained_blind_and_reconciliation(
    tmp_path, replies
):
    reader, gateway, client = setup(tmp_path, replies)
    blind = await reader.read_blind()
    raw_blind = blind.response_bytes
    result = await reader.localize_and_reconcile()
    assert len(gateway.sent) == 4
    assert [record.stage for record in reader.records] == [
        "intake",
        "quality_gate",
        "blind_pass",
        "independent_evidence",
        "reconcile",
    ]
    assert all(record.status == "completed" for record in reader.records)
    assert reader.blind_draft.response_bytes == raw_blind
    assert reader.blind_draft.draft.findings[0].bboxes == []
    box = result.decoded.draft.findings[0].bboxes[0]
    assert (box.x, box.y, box.w, box.h) == (0.1, 0.2, 0.2, 0.1)
    assert (
        box.verified
        and box.source_image_sha256 == reader.provenance.source_image_sha256
    )
    assert result.decoded.draft.evidence[-1].kind == "source_region"
    assert len(reader.turns[2].native_bbox_audit_json) == 1
    assert len(reader.records[3].artifact_sha256) == 3
    assert (
        client._last_tool_audit_records == []
    )  # New send cannot erase prior snapshot.
    assert (
        reader.turns[2]
        .gateway.require_native_tool_text("actual-native-call")
        .text_bytes
        == reader.localizations[0].tool_details_bytes
    )
    assert reader.reconciliation.response_bytes == result.response_bytes
    result.decoded.draft.evidence.clear()
    reader.localizations[0].evidence[0].bboxes.clear()
    assert reader.reconciliation.decoded.draft.evidence
    assert reader.localizations[0].evidence[0].bboxes
    with pytest.raises(ValueError):
        reader.reconciliation.decoded.draft.to_contract_payload()
    with pytest.raises(ValueError):
        await reader.localize_and_reconcile()
    assert len(gateway.sent) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["unavailable", "rejected"])
async def test_no_localization_remains_explicit_and_no_boxes_fabricated(
    tmp_path, replies, variant
):
    reader, gateway, _ = setup(tmp_path, replies, variant)
    await reader.read_blind()
    result = await reader.localize_and_reconcile()
    assert len(gateway.sent) == 4
    assert not any(binding.evidence for binding in reader.localizations)
    assert not result.decoded.draft.findings[0].bboxes
    assert reader.records[3].artifact_sha256


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "variant,stage,sends",
    [
        ("wrong_source", "independent_evidence", 3),
        ("changed_text", "independent_evidence", 3),
        ("duplicate_audit", "independent_evidence", 3),
        ("other_tool", "independent_evidence", 3),
        ("unfinished_tool", "independent_evidence", 3),
        ("unbound_tool", "independent_evidence", 3),
        ("missing_tool", "independent_evidence", 3),
        ("missing_decision", "reconcile", 4),
        ("changed_quality", "reconcile", 4),
        ("malformed_reconcile", "reconcile", 4),
    ],
)
async def test_failed_binding_or_challenge_preserved_without_paid_retry(
    tmp_path, replies, variant, stage, sends
):
    reader, gateway, _ = setup(tmp_path, replies, variant)
    await reader.read_blind()
    with pytest.raises(ValueError):
        await reader.localize_and_reconcile()
    assert reader.records[-1].stage == stage and reader.records[-1].status == "failed"
    assert len(reader.turns) == sends
    assert reader.turns[-1].gateway.require_model_text()
    assert reader.reconciliation is None
    with pytest.raises(ValueError):
        await reader.localize_and_reconcile()
    assert len(gateway.sent) == sends


@pytest.mark.asyncio
async def test_concurrent_continuation_and_cancellation_cannot_duplicate_turn(
    tmp_path, replies
):
    reader, gateway, _client = setup(tmp_path, replies, "wait")
    await reader.read_blind()
    pending = asyncio.create_task(reader.localize_and_reconcile())
    await asyncio.wait_for(gateway.entered.wait(), timeout=10)
    with pytest.raises(ValueError):
        await reader.localize_and_reconcile()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert reader.records[-1].stage == "independent_evidence"
    assert reader.records[-1].status == "cancelled"
    assert len(gateway.sent) == 3
    assert reader.reconciliation is None


@pytest.mark.asyncio
async def test_nondiagnostic_and_unstarted_cannot_request_localization(
    tmp_path, replies
):
    qc, _ = replies
    qc["adequacy"] = "non_diagnostic"
    reader, gateway, _ = setup(tmp_path, replies)
    with pytest.raises(ValueError, match="completed_blind_pass_required"):
        await reader.localize_and_reconcile()
    assert not gateway.sent
    assert await reader.read_blind() is None
    with pytest.raises(ValueError, match="completed_blind_pass_required"):
        await reader.localize_and_reconcile()
    assert len(gateway.sent) == 1
