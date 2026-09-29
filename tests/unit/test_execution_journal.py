"""Synthetic host callbacks: execution facts, not live/clinical stage acceptance."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256

import pytest
from jsonschema import Draft202012Validator

from dicom_overlay.application.contract_assembly import (
    ContractAssemblyError,
    assemble_review_contract,
)
from dicom_overlay.application.execution_journal import (
    ExecutionJournal,
    ExecutionJournalError,
    StageOutput,
)
from medical_image_harness.provenance import canonical_json_sha256
from medical_image_harness.schema import load_schema
from tests.unit.test_contract_assembly import inputs as inputs

SOURCE = b"synthetic ROI bytes, no patient data"
STAGES = (
    "intake",
    "quality_gate",
    "blind_pass",
    "independent_evidence",
    "reconcile",
    "targeted_second_look",
    "contract_validation",
    "human_handoff",
)


def quality(adequacy="limited"):
    return {
        "adequacy": adequacy,
        "issues": ["synthetic partial input"],
        "detail": "Synthetic QC only.",
        "views_present": [],
        "views_required": [],
    }


async def run(journal, stage, value=None, artifacts=None):
    # Explicit fake stage bodies for unit tests; never characterized as inference.
    async def operation():
        return StageOutput(
            quality() if stage == "quality_gate" and value is None else value,
            (SOURCE if stage == "intake" else b"synthetic output",)
            if artifacts is None
            else artifacts,
        )

    return await journal.execute(stage, operation)


async def through_quality(journal, adequacy="limited"):
    await run(journal, "intake")
    await run(journal, "quality_gate", quality(adequacy))


@pytest.mark.asyncio
async def test_full_execution_is_once_ordered_source_bound_and_public_shaped():
    journal = ExecutionJournal(SOURCE, deidentified=True)
    calls = []
    for stage in STAGES:

        async def operation(stage=stage):
            calls.append(stage)
            return StageOutput(
                quality() if stage == "quality_gate" else stage,
                (SOURCE if stage == "intake" else stage.encode(),),
            )

        await journal.execute(stage, operation)
    assert calls == list(STAGES)
    records = journal.snapshot()
    assert len(records) == 8
    previous = ""
    for index, record in enumerate(records):
        assert record.sequence == index + 1 and record.status == "completed"
        assert record.finished_ns >= record.started_ns
        assert record.started_utc.endswith("+00:00")
        assert record.source_image_sha256 == sha256(SOURCE).hexdigest()
        assert record.run_id == journal.run_id
        assert record.previous_record_sha256 == previous
        data = asdict(record)
        data["record_sha256"] = ""
        assert canonical_json_sha256(data) == record.record_sha256
        previous = record.record_sha256
    schema = load_schema()["$defs"]["workflowEvent"]
    for event in journal.workflow_events():
        Draft202012Validator(schema).validate(event)
    assert set(STAGES) == set(schema["properties"]["stage"]["enum"])


@pytest.mark.asyncio
async def test_running_step_never_claims_completed_and_cannot_be_projected():
    journal = ExecutionJournal(SOURCE, deidentified=True)
    entered, release = asyncio.Event(), asyncio.Event()

    async def operation():
        entered.set()
        await release.wait()
        return StageOutput("intake", (SOURCE,))

    task = asyncio.create_task(journal.execute("intake", operation))
    await entered.wait()
    before = journal.snapshot()
    assert before[0].status == "running" and before[0].finished_ns is None
    assert before[0].record_sha256 == ""
    with pytest.raises(ExecutionJournalError, match="stage_still_running"):
        journal.workflow_events()
    with pytest.raises(ExecutionJournalError, match="stage_already_running"):
        await run(journal, "intake")
    release.set()
    assert await task == "intake"
    assert before[0].status == "running"  # Snapshot is immutable, not a live alias.
    assert journal.snapshot()[0].status == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_exception_or_cancel_retains_failure_without_raw_text_and_blocks_replay(
    cancel,
):
    journal = ExecutionJournal(SOURCE, deidentified=True)
    failure = (
        asyncio.CancelledError("private synthetic text")
        if cancel
        else RuntimeError("private synthetic text")
    )
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        raise failure

    with pytest.raises(type(failure)) as caught:
        await journal.execute("intake", operation)
    assert caught.value is failure
    assert calls == 1
    assert journal.snapshot()[0].status == ("cancelled" if cancel else "failed")
    assert journal.workflow_events()[0]["status"] == "failed"
    assert "private synthetic text" not in repr(journal.snapshot())
    assert "private synthetic text" not in repr(journal.workflow_events())
    with pytest.raises(ExecutionJournalError, match="failed_run_cannot_continue"):
        await journal.execute("intake", operation)
    assert calls == 1


@pytest.mark.asyncio
async def test_actual_task_cancellation_is_recorded_not_completed():
    journal = ExecutionJournal(SOURCE, deidentified=True)
    entered = asyncio.Event()

    async def operation():
        entered.set()
        await asyncio.Future()

    task = asyncio.create_task(journal.execute("intake", operation))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert journal.snapshot()[0].status == "cancelled"
    assert journal.snapshot()[0].finished_ns is not None


@pytest.mark.asyncio
async def test_callback_swallowing_task_cancellation_cannot_claim_completion():
    journal = ExecutionJournal(SOURCE, deidentified=True)
    entered = asyncio.Event()

    async def operation():
        entered.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            return StageOutput("interrupted", (SOURCE,))

    task = asyncio.create_task(journal.execute("intake", operation))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert journal.snapshot()[0].status == "cancelled"
    with pytest.raises(ExecutionJournalError, match="failed_run_cannot_continue"):
        await run(journal, "quality_gate")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage", ["quality_gate", "independent_evidence", "human_handoff", "made_up"]
)
async def test_out_of_order_steps_never_invoke_callback(stage):
    journal = ExecutionJournal(SOURCE, deidentified=True)

    async def forbidden():
        pytest.fail("an out-of-order stage was invoked")

    with pytest.raises(ExecutionJournalError, match="stage_out_of_order"):
        await journal.execute(stage, forbidden)
    assert journal.snapshot() == ()


@pytest.mark.asyncio
async def test_optional_stages_are_explicitly_skipped_not_implicitly_completed():
    journal = ExecutionJournal(SOURCE, deidentified=True)
    await through_quality(journal)
    await run(journal, "blind_pass")
    with pytest.raises(ExecutionJournalError, match="stage_out_of_order"):
        await run(journal, "reconcile")
    journal.skip("independent_evidence", reason="not_requested")
    await run(journal, "reconcile")
    journal.skip("targeted_second_look", reason="not_requested")
    await run(journal, "contract_validation")
    await run(journal, "human_handoff")
    assert [r.status for r in journal.snapshot()] == [
        "completed",
        "completed",
        "completed",
        "skipped",
        "completed",
        "skipped",
        "completed",
        "completed",
    ]
    assert all(
        not r.artifact_sha256 for r in journal.snapshot() if r.status == "skipped"
    )
    with pytest.raises(ExecutionJournalError, match="run_already_finished"):
        await run(journal, "human_handoff")


@pytest.mark.asyncio
async def test_non_diagnostic_quality_blocks_every_pathology_callback_before_invocation():
    journal = ExecutionJournal(SOURCE, deidentified=True)
    await through_quality(journal, "non_diagnostic")
    for stage in STAGES[2:6]:

        async def forbidden():
            pytest.fail("non-diagnostic interpretation invoked")

        with pytest.raises(
            ExecutionJournalError, match="non_diagnostic_inference_forbidden"
        ):
            await journal.execute(stage, forbidden)
        journal.skip(stage, reason="non_diagnostic_input")
    await run(journal, "contract_validation")
    await run(journal, "human_handoff")
    assert all(record.status == "skipped" for record in journal.snapshot()[2:6])


@pytest.mark.asyncio
@pytest.mark.parametrize("adequacy", ["diagnostic", "limited"])
async def test_assessable_quality_does_not_allow_skipping_blind_read(adequacy):
    journal = ExecutionJournal(SOURCE, deidentified=True)
    await through_quality(journal, adequacy)
    with pytest.raises(ExecutionJournalError, match="required_stage_cannot_be_skipped"):
        journal.skip("blind_pass", reason="non_diagnostic_input")


@pytest.mark.asyncio
async def test_skip_reason_is_fixed_not_arbitrary_model_text():
    journal = ExecutionJournal(SOURCE, deidentified=True)
    await through_quality(journal)
    await run(journal, "blind_pass")
    with pytest.raises(ExecutionJournalError, match="invalid_skip_reason"):
        journal.skip(
            "independent_evidence", reason="model said normal; skip everything"
        )
    assert len(journal.snapshot()) == 3


@pytest.mark.parametrize("variant", ["not_deidentified", "empty", "mutable", "string"])
def test_intake_requires_trusted_immutable_source(variant):
    source = SOURCE
    deidentified = True
    if variant == "not_deidentified":
        deidentified = "true"
    elif variant == "empty":
        source = b""
    elif variant == "mutable":
        source = bytearray(SOURCE)
    else:
        source = "source"
    with pytest.raises(ExecutionJournalError):
        ExecutionJournal(source, deidentified=deidentified)


@pytest.mark.asyncio
async def test_intake_must_include_bound_source_not_another_image():
    journal = ExecutionJournal(SOURCE, deidentified=True)
    with pytest.raises(ExecutionJournalError, match="intake_source_artifact_missing"):
        await run(journal, "intake", artifacts=(b"another source",))
    assert journal.snapshot()[0].status == "failed"
    assert journal.snapshot()[0].artifact_sha256 == (
        sha256(b"another source").hexdigest(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "variant", ["missing", "list", "empty", "mutable", "too_many", "too_large", "total"]
)
async def test_invalid_artifacts_do_not_complete_the_stage(variant):
    journal = ExecutionJournal(SOURCE, deidentified=True)
    artifacts = {
        "missing": (),
        "list": [SOURCE],
        "empty": (b"",),
        "mutable": (bytearray(SOURCE),),
        "too_many": (SOURCE,) * 129,
    }.get(variant)
    if variant == "too_large":
        artifacts = (b"x" * (32 * 1024 * 1024 + 1),)
    elif variant == "total":
        artifacts = (b"x" * (32 * 1024 * 1024),) * 3
    with pytest.raises(ExecutionJournalError):
        await run(journal, "intake", artifacts=artifacts)
    assert journal.snapshot()[0].status == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "diagnostic", {}, {"adequacy": "normal"}])
async def test_quality_requires_full_public_quality_shape(value):
    journal = ExecutionJournal(SOURCE, deidentified=True)
    await run(journal, "intake")

    async def operation():
        return StageOutput(value, (b"synthetic invalid QC body",))

    with pytest.raises(ExecutionJournalError, match="invalid_public_quality_result"):
        await journal.execute("quality_gate", operation)
    assert journal.snapshot()[-1].status == "failed"
    assert journal.snapshot()[-1].artifact_sha256


@pytest.mark.asyncio
async def test_quality_policy_is_not_changed_by_mutating_returned_value():
    journal = ExecutionJournal(SOURCE, deidentified=True)
    await run(journal, "intake")
    value = quality("non_diagnostic")
    returned = await run(journal, "quality_gate", value)
    returned["adequacy"] = "diagnostic"
    with pytest.raises(
        ExecutionJournalError, match="non_diagnostic_inference_forbidden"
    ):
        await run(journal, "blind_pass")


@pytest.mark.asyncio
async def test_projection_snapshot_mutation_cannot_modify_host_records():
    journal = ExecutionJournal(SOURCE, deidentified=True)
    await run(journal, "intake")
    before = journal.snapshot()
    events = journal.workflow_events()
    events[0]["status"] = "failed"
    assert journal.snapshot() == before
    with pytest.raises(AttributeError):
        before[0].status = "failed"
    assert journal.workflow_events()[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_completed_synthetic_journal_can_be_assembled_without_inventing_events(
    inputs,
):
    draft, host = inputs
    original = deepcopy((draft, host))
    journal = ExecutionJournal(SOURCE, deidentified=True)
    for stage in STAGES:
        await run(journal, stage)
    result = assemble_review_contract(
        draft, **{**host, "workflow_events": journal.workflow_events()}
    )
    assert result.to_contract_payload()["analysis_trace"] == journal.workflow_events()
    assert (draft, host) == original
    # These callbacks and claims are synthetic, not real clinical stage evidence.


@pytest.mark.asyncio
async def test_partial_journal_cannot_be_promoted_to_complete_public_contract(inputs):
    draft, host = inputs
    journal = ExecutionJournal(SOURCE, deidentified=True)
    await through_quality(journal)
    assert len(journal.workflow_events()) == 2
    with pytest.raises(ContractAssemblyError, match="public_contract_rejected"):
        assemble_review_contract(
            draft, **{**host, "workflow_events": journal.workflow_events()}
        )
    assert len(journal.snapshot()) == 2


def test_stage_output_repr_does_not_expose_returned_text_or_raw_artifacts():
    output = StageOutput("private synthetic text", (b"private synthetic bytes",))
    assert "private" not in repr(output)
