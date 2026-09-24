"""Synthetic Gateway and presenter: no clinical or actual GUI acceptance claim."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from hashlib import sha256

import pytest

from dicom_overlay.application.contract_assembly import review_content_sha256
from dicom_overlay.infrastructure import scientific_image_session as session_module
from medical_image_harness.models import Modality
from medical_image_harness.profiles import default_registry
from tests.unit.test_contract_assembly import inputs as inputs
from tests.unit.test_scientific_draft import draft_request as draft_request
from tests.unit.test_scientific_image_session import replies as replies
from tests.unit.test_scientific_image_session import session
from tests.unit.test_scientific_reconciliation import envelope


def setup(tmp_path, replies, *, second=None, tool_stage=-1):
    qc, draft = deepcopy(replies)
    reconciled = envelope(draft)
    responses = [
        qc,
        draft,
        {"status": "unavailable", "reason": "No justified synthetic box."},
        reconciled,
        deepcopy(reconciled) if second is None else second,
    ]
    return session(tmp_path, responses, tool_stage=tool_stage)


async def through_second(reader):
    await reader.read_blind()
    await reader.localize_and_reconcile()
    return await reader.targeted_second_look()


def receipt(run_id, prepared):
    return {
        "run_id": run_id,
        "source_image_sha256": prepared.result.input_provenance.source_image_sha256,
        "review_content_sha256": prepared.content_sha256,
        "surface": "synthetic-test-surface",
        "available": True,
    }


@pytest.mark.asyncio
async def test_final_contract_requires_second_look_preflight_and_actual_callback(
    tmp_path, replies
):
    reader, gateway = setup(tmp_path, replies)
    second = await through_second(reader)
    assert len(gateway.sent) == 5
    assert reader.final_result is None and reader.prepared_review is None
    prompt = gateway.sent[-1]["params"]["message"]
    assert "targeted_second_look" in prompt and "SAME full source image" in prompt
    assert "PRIOR REVIEW INVENTORY" in prompt
    assert (
        reader.second_look.response_bytes
        == reader.turns[-1].gateway.require_model_text()
    )
    second.decoded.draft.summary = "Detached result"
    prepared = await reader.prepare_review()
    assert len(reader.records) == 7
    assert reader.records[-1].stage == "contract_validation"
    assert len(prepared.result.workflow_events) == 6
    with pytest.raises(ValueError):
        prepared.result.to_contract_payload()
    assert reader.final_result is None
    assert reader.records[-1].artifact_sha256 == (
        sha256(reader.review_artifacts[0]).hexdigest(),
    )
    calls = []

    async def presenter(run_id, shown):
        assert len(reader.records) == 8 and reader.records[-1].status == "running"
        assert reader.final_result is None
        assert shown.content_sha256 == prepared.content_sha256
        raw = json.dumps(receipt(run_id, shown)).encode()
        calls.append(raw)
        shown._result.findings.clear()  # Even deliberately altered callback snapshot is detached.
        return raw

    final = await reader.offer_review(presenter)
    payload = final.to_contract_payload()
    assert payload["review_required"] is True
    assert payload["result_status"] == "research_draft"
    assert len(payload["analysis_trace"]) == 8
    assert all(event["status"] == "completed" for event in payload["analysis_trace"])
    assert final.findings and final.incomplete
    assert review_content_sha256(final) == prepared.content_sha256
    assert reader.review_artifacts[-1] == calls[0]
    assert reader.records[-1].artifact_sha256 == (sha256(calls[0]).hexdigest(),)
    assert len(gateway.sent) == 5  # Validation and presentation add no model calls.
    final.findings.clear()
    assert reader.final_result.findings
    with pytest.raises(ValueError):
        await reader.offer_review(presenter)
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["new", "blind", "reconciled", "second", "prepared"])
async def test_no_premature_handoff_and_no_repeated_model_request(
    tmp_path, replies, stage
):
    reader, gateway = setup(tmp_path, replies)
    if stage != "new":
        await reader.read_blind()
    if stage in {"reconciled", "second", "prepared"}:
        await reader.localize_and_reconcile()
    if stage in {"second", "prepared"}:
        await reader.targeted_second_look()
    if stage == "prepared":
        await reader.prepare_review()
    count = len(gateway.sent)
    if stage in {"new", "blind"}:
        with pytest.raises(ValueError):
            await reader.targeted_second_look()
    if stage in {"new", "blind", "reconciled", "prepared"}:
        with pytest.raises(ValueError):
            await reader.prepare_review()
    if stage != "prepared":
        with pytest.raises(ValueError, match="prepared_review_required"):
            await reader.offer_review(None)
    else:
        with pytest.raises(ValueError, match="review_presenter_required"):
            await reader.offer_review(None)
    assert len(gateway.sent) == count and reader.final_result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "run_id",
        "source_image_sha256",
        "review_content_sha256",
        "available",
        "surface",
        "extra",
        "duplicate",
        "oversize",
        "not_bytes",
        "exception",
    ],
)
async def test_failed_or_unbound_presenter_never_publishes_or_retries(
    tmp_path, replies, change
):
    reader, gateway = setup(tmp_path, replies)
    await through_second(reader)
    await reader.prepare_review()
    calls = []

    async def presenter(run_id, prepared):
        calls.append(run_id)
        data = receipt(run_id, prepared)
        if change == "exception":
            raise RuntimeError("Synthetic unavailable surface")
        if change == "not_bytes":
            return "not immutable bytes"
        if change == "oversize":
            return b" " * 16_385
        if change == "duplicate":
            return b'{"available":true,"available":false}'
        data[change] = False if change == "available" else "mismatched or unsafe value"
        return json.dumps(data).encode()

    with pytest.raises((ValueError, RuntimeError)):
        await reader.offer_review(presenter)
    assert reader.final_result is None
    assert reader.records[-1].status == "failed"
    with pytest.raises(ValueError):
        await reader.offer_review(presenter)
    assert len(calls) == 1 and len(gateway.sent) == 5


@pytest.mark.asyncio
async def test_pending_handoff_and_cancelled_surface_cannot_publish(tmp_path, replies):
    reader, gateway = setup(tmp_path, replies)
    await through_second(reader)
    await reader.prepare_review()
    entered = asyncio.Event()
    calls = []

    async def presenter(run_id, prepared):
        calls.append(run_id)
        entered.set()
        await asyncio.Event().wait()
        return json.dumps(receipt(run_id, prepared)).encode()

    pending = asyncio.create_task(reader.offer_review(presenter))
    await asyncio.wait_for(entered.wait(), 2)
    assert reader.final_result is None
    with pytest.raises(ValueError):
        await reader.offer_review(presenter)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert reader.records[-1].status == "cancelled"
    with pytest.raises(ValueError):
        await reader.offer_review(presenter)
    assert len(calls) == 1 and len(gateway.sent) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["quality", "decision", "invalid_json", "tool"])
async def test_second_look_failures_retain_response_and_cannot_reach_preflight(
    tmp_path, replies, change
):
    second = envelope(deepcopy(replies[1]))
    if change == "quality":
        second["draft"]["image_quality"]["adequacy"] = "diagnostic"
    elif change == "decision":
        second["decisions"] = []
    elif change == "invalid_json":
        second = "invalid JSON"
    reader, gateway = setup(
        tmp_path, replies, second=second, tool_stage=4 if change == "tool" else -1
    )
    await reader.read_blind()
    await reader.localize_and_reconcile()
    with pytest.raises(ValueError):
        await reader.targeted_second_look()
    assert reader.records[-1].stage == "targeted_second_look"
    assert reader.records[-1].status == "failed"
    assert reader.turns[-1].gateway.require_model_text()
    assert reader.second_look is None and reader.final_result is None
    with pytest.raises(ValueError):
        await reader.prepare_review()
    with pytest.raises(ValueError):
        await reader.targeted_second_look()
    assert len(gateway.sent) == 5


@pytest.mark.asyncio
async def test_second_look_challenges_reconciled_not_original_findings(
    tmp_path, replies
):
    reader, gateway = setup(tmp_path, replies)
    prior = gateway.replies[3]
    old = prior["draft"]["findings"][0]["id"]
    prior["draft"]["findings"][0]["id"] = "new-after-blind"
    prior["decisions"] = [
        {
            "action": "retract",
            "prior_finding_id": old,
            "final_finding_id": "",
            "rationale": "Synthetic replacement.",
        },
        {
            "action": "add",
            "prior_finding_id": "",
            "final_finding_id": "new-after-blind",
            "rationale": "Synthetic replacement.",
        },
    ]
    gateway.replies[4] = envelope(deepcopy(prior["draft"]))
    gateway.replies[4]["decisions"][0].update(
        prior_finding_id="new-after-blind", final_finding_id="new-after-blind"
    )
    await through_second(reader)
    assert reader.blind_draft.draft.findings[0].id == old
    assert reader.second_look.decoded.draft.findings[0].id == "new-after-blind"


@pytest.mark.asyncio
async def test_nondiagnostic_input_is_not_filled_with_invented_clinical_ledger(
    tmp_path, replies
):
    replies[0]["adequacy"] = "non_diagnostic"
    reader, gateway = setup(tmp_path, replies)
    assert await reader.read_blind() is None
    for method in (reader.targeted_second_look, reader.prepare_review):
        with pytest.raises(ValueError):
            await method()
    assert len(gateway.sent) == 1 and reader.final_result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("modality", [Modality.EKG, Modality.CXR, Modality.CT_BRAIN])
async def test_all_modalities_complete_only_as_review_required_single_images(
    tmp_path, replies, modality
):
    reader, gateway = setup(tmp_path, replies)
    reader._modality = modality
    for draft in (
        gateway.replies[1],
        gateway.replies[3]["draft"],
        gateway.replies[4]["draft"],
    ):
        draft["modality"] = modality.value
        draft["checklist"] = {
            key: {
                "value": "Synthetic unassessable axis",
                "status": "info",
                "assessable": False,
            }
            for key in default_registry().get(modality.value).checklist_keys
        }
    await through_second(reader)
    await reader.prepare_review()

    async def presenter(run_id, prepared):
        return json.dumps(receipt(run_id, prepared)).encode()

    payload = (await reader.offer_review(presenter)).to_contract_payload()
    assert payload["modality"] == modality.value
    assert payload["assessment_scope"] == "single_image_observation"
    assert payload["incomplete"] and payload["review_required"]


@pytest.mark.asyncio
async def test_preflight_failure_blocks_handoff_without_future_completed_events(
    tmp_path, replies, monkeypatch
):
    reader, gateway = setup(tmp_path, replies)
    await through_second(reader)

    def reject(*args, **kwargs):
        raise ValueError("synthetic_preflight_rejection")

    monkeypatch.setattr(session_module, "preflight_review_contract", reject)
    with pytest.raises(ValueError, match="synthetic_preflight_rejection"):
        await reader.prepare_review()
    assert reader.records[-1].stage == "contract_validation"
    assert reader.records[-1].status == "failed"
    assert reader.prepared_review is None
    with pytest.raises(ValueError, match="prepared_review_required"):
        await reader.offer_review(None)
    assert len(gateway.sent) == 5


@pytest.mark.asyncio
async def test_final_gate_failure_does_not_rewrite_handoff_or_publish(
    tmp_path, replies, monkeypatch
):
    reader, _gateway = setup(tmp_path, replies)
    await through_second(reader)
    await reader.prepare_review()

    def reject(*args, **kwargs):
        raise ValueError("synthetic_final_rejection")

    async def presenter(run_id, prepared):
        return json.dumps(receipt(run_id, prepared)).encode()

    monkeypatch.setattr(session_module, "assemble_review_contract", reject)
    with pytest.raises(ValueError, match="synthetic_final_rejection"):
        await reader.offer_review(presenter)
    assert reader.records[-1].stage == "human_handoff"
    assert reader.records[-1].status == "completed"  # Availability really returned.
    assert reader.final_result is None  # No canonical export may follow.
    with pytest.raises(ValueError):
        await reader.offer_review(presenter)
