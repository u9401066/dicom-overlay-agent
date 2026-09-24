"""Actual adapter/client/journal operations, synthetic pixels and Gateway replies."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from hashlib import sha256

import pytest

from dicom_overlay.infrastructure.scientific_image_session import ScientificImageSession
from medical_image_harness.models import Modality
from medical_image_harness.profiles import default_registry
from tests.unit.test_contract_assembly import inputs as inputs
from tests.unit.test_image_evidence_turn import SOURCE, Gateway, connected, picture
from tests.unit.test_scientific_draft import draft_request as draft_request


@pytest.fixture
def replies(draft_request):
    payload, _ = draft_request
    payload = deepcopy(payload)
    for observation in payload["observations"]:
        observation["evidence_ids"] = ["source-frame"]
    for finding in payload["findings"]:
        finding["evidence_ids"] = ["source-frame"]
        finding["bbox_evidence_ids"] = []
    return deepcopy(payload["image_quality"]), payload


class StageGateway(Gateway):
    def __init__(self, replies, *, tool_stage=-1, unrelated=False):
        super().__init__()
        self.replies = replies
        self.tool_stage = tool_stage
        self.unrelated = unrelated

    async def send(self, raw):
        index = len(self.sent)
        response = self.replies[index]
        self.body = response if isinstance(response, str) else json.dumps(response)
        await super().send(raw)
        if index == self.tool_stage:
            # An arbitrary tool start is a violation, even with no preserved
            # tool output. No args/name are needed in the final metadata flag.
            self.frames.insert(
                1,
                {
                    "type": "event",
                    "event": "agent",
                    "payload": {
                        "runId": "unrelated" if self.unrelated else f"run-{index + 1}",
                        "sessionKey": self.sent[-1]["params"]["sessionKey"],
                        "stream": "tool",
                        "data": {
                            "phase": "start",
                            "name": "synthetic-classifier",
                            "args": "synthetic-private-tool-input",
                        },
                    },
                },
            )


def session(tmp_path, replies, **kwargs):
    gateway = StageGateway(replies, **kwargs)
    client = connected(tmp_path, gateway)
    return ScientificImageSession(
        client,
        image_bytes=SOURCE,
        modality=Modality.EKG,
        deidentified=True,
    ), gateway


@pytest.mark.asyncio
async def test_actual_intake_qc_blind_chain_keeps_raw_receipts_and_partial_scope(
    tmp_path, replies
):
    reader, gateway = session(tmp_path, replies)
    with pytest.raises(ValueError, match="intake_not_complete"):
        _ = reader.study
    result = await reader.read_blind()
    assert result is not None and len(gateway.sent) == 2
    assert [record.stage for record in reader.records] == [
        "intake",
        "quality_gate",
        "blind_pass",
    ]
    assert all(record.status == "completed" for record in reader.records)
    assert reader.records[0].artifact_sha256[0] == sha256(SOURCE).hexdigest()
    for record, turn in zip(reader.records[1:], reader.turns, strict=True):
        assert record.artifact_sha256 == (
            sha256(turn.gateway.require_model_text()).hexdigest(),
        )
        assert turn.image_sha256 == reader.provenance.source_image_sha256
    assert reader.study.complete is False and reader.study.limitations
    assert reader.study.assets[0].sha256 == sha256(SOURCE).hexdigest()
    assert reader.source_evidence[0].bboxes == []
    assert reader.source_evidence[0].source_ref == reader.study.assets[0].id
    assert result.draft.model_used == "openclaw-unverified"
    assert result.draft.observations and result.draft.findings[0].bboxes == []
    assert result.draft.incomplete and result.draft.workflow_events == []
    assert result.draft.input_provenance is None
    assert len(reader.workflow_events()) == 3
    with pytest.raises(ValueError):
        result.draft.to_contract_payload()
    first_prompt = gateway.sent[0]["params"]["message"]
    second_prompt = gateway.sent[1]["params"]["message"]
    assert "quality_gate" in first_prompt and "observations ledger" in first_prompt
    assert "blind_pass" in second_prompt and "No verified localization" in second_prompt
    assert "COMPLETE" not in repr(reader.workflow_events())


@pytest.mark.asyncio
async def test_nondiagnostic_quality_prevents_second_paid_request(tmp_path, replies):
    qc, _ = replies
    qc["adequacy"] = "non_diagnostic"
    reader, gateway = session(tmp_path, [qc])
    assert await reader.read_blind() is None
    assert len(gateway.sent) == 1 and len(reader.turns) == 1
    assert reader.quality == qc and reader.blind_draft is None
    assert reader.records[-1].stage == "blind_pass"
    assert reader.records[-1].status == "skipped"
    assert reader.records[-1].category == "non_diagnostic_input"
    assert not any(
        event["stage"] == "human_handoff" for event in reader.workflow_events()
    )
    with pytest.raises(ValueError):
        await reader.read_blind()
    assert len(gateway.sent) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        "[]",
        "```json\n{}\n```",
        '{"adequacy":"limited","adequacy":"diagnostic"}',
        '{"adequacy":"normal"}',
        '{"x":NaN}',
    ],
)
async def test_invalid_qc_is_preserved_as_failed_attempt_without_blind_read(
    tmp_path, raw
):
    reader, gateway = session(tmp_path, [raw])
    with pytest.raises(ValueError):
        await reader.read_blind()
    assert len(gateway.sent) == 1
    assert reader.turns[0].gateway.require_model_text() == raw.encode()
    assert (
        reader.records[-1].stage == "quality_gate"
        and reader.records[-1].status == "failed"
    )
    assert reader.quality is None and reader.blind_draft is None
    with pytest.raises(ValueError, match="failed_run_cannot_continue"):
        await reader.read_blind()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["qc_upgrade", "complete_study", "missing_ledger", "invented_box"]
)
async def test_blind_output_cannot_change_qc_scope_or_invent_spatial_evidence(
    tmp_path, replies, change
):
    qc, draft = replies
    if change == "qc_upgrade":
        draft["image_quality"]["adequacy"] = "diagnostic"
    elif change == "complete_study":
        draft["incomplete"] = False
    elif change == "missing_ledger":
        draft["observations"] = []
    else:
        draft["findings"][0]["bbox_evidence_ids"] = ["source-frame"]
    reader, gateway = session(tmp_path, [qc, draft])
    with pytest.raises(ValueError):
        await reader.read_blind()
    assert len(gateway.sent) == 2 and len(reader.turns) == 2
    assert (
        reader.records[-1].stage == "blind_pass"
        and reader.records[-1].status == "failed"
    )
    assert reader.quality == qc and reader.blind_draft is None


@pytest.mark.asyncio
@pytest.mark.parametrize("index", [0, 1])
async def test_observed_tools_fail_qc_or_blind_without_saving_private_tool_content(
    tmp_path, replies, index
):
    reader, gateway = session(tmp_path, replies, tool_stage=index)
    with pytest.raises(ValueError, match="tool_observed_in_quality_or_blind_stage"):
        await reader.read_blind()
    assert len(gateway.sent) == index + 1
    assert reader.records[-1].status == "failed"
    assert reader.turns[-1].gateway.tool_event_seen
    assert reader.turns[-1].gateway.native_tools == ()
    assert "synthetic-private-tool-input" not in repr(reader.turns)
    assert "synthetic-classifier" not in repr(reader.turns)


@pytest.mark.asyncio
async def test_other_run_tool_events_do_not_taint_this_blind_pass(tmp_path, replies):
    reader, _ = session(tmp_path, replies, tool_stage=0, unrelated=True)
    assert await reader.read_blind() is not None
    assert not any(turn.gateway.tool_event_seen for turn in reader.turns)


@pytest.mark.asyncio
async def test_returned_quality_draft_study_and_evidence_do_not_alias_session(
    tmp_path, replies
):
    reader, _ = session(tmp_path, replies)
    result = await reader.read_blind()
    reader.quality["adequacy"] = "non_diagnostic"
    result.draft.observations.clear()
    reader.study.metadata["unexpected"] = "not retained"
    reader.source_evidence[0].bboxes.append("not retained")
    events = reader.workflow_events()
    events[-1]["status"] = "failed"
    assert reader.quality == replies[0]
    assert reader.blind_draft.draft.observations
    assert reader.study.metadata == {} and reader.source_evidence[0].bboxes == []
    assert reader.records[-1].status == "completed"


@pytest.mark.asyncio
async def test_same_session_concurrency_cannot_duplicate_model_requests(
    tmp_path, replies
):
    reader, gateway = session(tmp_path, replies)
    outcomes = await asyncio.gather(
        reader.read_blind(), reader.read_blind(), return_exceptions=True
    )
    assert sum(isinstance(item, ValueError) for item in outcomes) == 1
    assert len(gateway.sent) == 2
    assert len(reader.records) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["corrupt", "jpeg", "animated"])
async def test_invalid_source_fails_intake_before_any_gateway_send(tmp_path, variant):
    raw = {
        "corrupt": b"not-an-image",
        "jpeg": picture("JPEG"),
        "animated": picture(animated=True),
    }[variant]
    client = connected(tmp_path)
    reader = ScientificImageSession(
        client, image_bytes=raw, modality=Modality.EKG, deidentified=True
    )
    with pytest.raises(ValueError):
        await reader.read_blind()
    assert client._ws.sent == [] and reader.turns == ()
    assert reader.records[0].stage == "intake" and reader.records[0].status == "failed"
    with pytest.raises(ValueError, match="intake_not_complete"):
        _ = reader.provenance


@pytest.mark.parametrize(
    "variant", ["deid_false", "deid_int", "mutable", "empty", "modality"]
)
def test_untrusted_input_rejected_before_a_session_can_send(tmp_path, variant):
    client = connected(tmp_path)
    raw = (
        bytearray(SOURCE)
        if variant == "mutable"
        else b""
        if variant == "empty"
        else SOURCE
    )
    deid = False if variant == "deid_false" else 1 if variant == "deid_int" else True
    with pytest.raises(ValueError):
        ScientificImageSession(
            client,
            image_bytes=raw,
            modality="unknown" if variant == "modality" else Modality.EKG,
            deidentified=deid,
        )
    assert client._ws.sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("modality", [Modality.EKG, Modality.CXR, Modality.CT_BRAIN])
async def test_each_modality_uses_public_axes_and_remains_a_partial_single_image(
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
    client = connected(tmp_path, StageGateway([qc, draft]))
    reader = ScientificImageSession(
        client, image_bytes=SOURCE, modality=modality, deidentified=True
    )
    result = await reader.read_blind()
    assert result.draft.modality is modality
    assert reader.study.modality == modality.value and not reader.study.complete
    assert "single_image_observation" in client._ws.sent[0]["params"]["message"]
    assert set(result.draft.checklist) == set(
        default_registry().get(modality.value).checklist_keys
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["observation", "finding", "confidence"])
async def test_ct_screenshot_cannot_emit_study_diagnoses_or_high_confidence(
    tmp_path, replies, violation
):
    qc, draft = replies
    draft["modality"] = "CT_BRAIN"
    draft["checklist"] = {
        key: {
            "value": "Synthetic unassessable axis",
            "status": "info",
            "assessable": False,
        }
        for key in default_registry().get("CT_BRAIN").checklist_keys
    }
    if violation == "confidence":
        draft["findings"][0]["confidence"] = "high"
    else:
        draft["observations" if violation == "observation" else "findings"][0][
            "claim_type"
        ] = "diagnostic_hypothesis"
    client = connected(tmp_path, StageGateway([qc, draft]))
    reader = ScientificImageSession(
        client, image_bytes=SOURCE, modality=Modality.CT_BRAIN, deidentified=True
    )
    with pytest.raises(ValueError, match="single_ct_image_requires_descriptive_claims"):
        await reader.read_blind()
    assert reader.records[-1].status == "failed" and reader.blind_draft is None


@pytest.mark.asyncio
async def test_cancelled_qc_stays_cancelled_with_no_blind_request(tmp_path):
    gateway = Gateway(variant="wait")
    client = connected(tmp_path, gateway)
    reader = ScientificImageSession(
        client, image_bytes=SOURCE, modality=Modality.EKG, deidentified=True
    )
    task = asyncio.create_task(reader.read_blind())
    await gateway.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        reader.records[-1].stage == "quality_gate"
        and reader.records[-1].status == "cancelled"
    )
    assert reader.quality is None and reader.blind_draft is None
    assert [frame["method"] for frame in gateway.sent] == ["chat.send", "chat.abort"]
    assert not client.transport_evidence().terminal_seen
    with pytest.raises(ValueError, match="failed_run_cannot_continue"):
        await reader.read_blind()
