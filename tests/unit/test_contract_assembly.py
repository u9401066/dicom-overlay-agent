from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256

import pytest

from dicom_overlay.application.contract_assembly import (
    ContractAssemblyError,
    assemble_review_contract,
)
from medical_image_harness.models import (
    AnalysisResult,
    ChecklistItem,
    Evidence,
    Finding,
    Modality,
    Observation,
    Polarity,
    RegionRect,
    Severity,
    VerificationStatus,
)
from medical_image_harness.profiles import default_registry
from medical_image_harness.provenance import InputProvenance, TransformationRecord
from medical_image_harness.study import ImageAsset, StudyManifest


@pytest.fixture
def inputs():
    # Bytes are opaque to this host boundary; actual image decoding and the
    # capture/crop operation belong to the upstream adapter, not these fixtures.
    source = b"synthetic ROI bytes, no patient data"
    digest = sha256(source).hexdigest()
    box = RegionRect(0.1, 0.2, 0.1, 0.1, source_image_sha256=digest, verified=True)
    evidence = Evidence(
        "e1",
        "source_region",
        digest,
        "synthetic visible shape",
        bboxes=[box],
        source_ref="image-1",
    )
    observation = Observation(
        "o1",
        "visible trace",
        "synthetic waveform shape",
        Polarity.UNCERTAIN,
        VerificationStatus.POSSIBLE,
        True,
        evidence_ids=["e1"],
        question="Review source shape.",
    )
    checklist = {
        key: ChecklistItem(
            "not assessable in synthetic fixture", Severity.INFO, assessable=False
        )
        for key in default_registry().get("EKG").checklist_keys
    }
    checklist["rhythm"] = ChecklistItem("synthetic shape", Severity.INFO, evidence="o1")
    draft = AnalysisResult(
        modality=Modality.EKG,
        summary="Synthetic shape requires review.",
        severity=Severity.INFO,
        findings=[
            Finding(
                "f1",
                [],
                "Synthetic shape",
                "Unresolved synthetic shape.",
                Severity.INFO,
                bboxes=[box],
                confidence="low",
                question="Review source shape.",
                evidence_ids=["e1"],
                observation_ids=["o1"],
            )
        ],
        checklist=checklist,
        observations=[observation],
        evidence=[evidence],
        summary_observation_ids=["o1"],
        image_quality={
            "adequacy": "limited",
            "issues": ["synthetic partial source"],
            "detail": "Synthetic fixture only.",
            "views_present": [],
            "views_required": [],
        },
        incomplete=True,
        incomplete_reasons=["synthetic partial source"],
        review_required=True,
        review_reasons=["Synthetic evidence requires review."],
        model_used="synthetic",
        next_steps=["Review source."],
        analysis_trace=[{"stage": "legacy_transport", "status": "not_canonical"}],
    )
    study = StudyManifest(
        "synthetic-study",
        "EKG",
        (ImageAsset("image-1", digest, "EKG", "screenshot"),),
        False,
        limitations=("synthetic partial source",),
    )
    events = [
        {"stage": stage, "status": "completed", "detail": "Synthetic host event."}
        for stage in (
            "intake",
            "quality_gate",
            "blind_pass",
            "reconcile",
            "contract_validation",
            "human_handoff",
        )
    ]
    kwargs = {
        "provenance": InputProvenance(digest, "screenshot", True),
        "study": study,
        "assessment_scope": "single_image_observation",
        "asset_bytes": {"image-1": source},
        "transform_bytes": {},
        "trusted_evidence": [deepcopy(evidence)],
        "workflow_events": events,
    }
    return draft, kwargs


def test_assembles_public_contract_without_mutating_or_aliasing(inputs):
    draft, kwargs = inputs
    baseline = deepcopy((draft, kwargs))
    result = assemble_review_contract(draft, **kwargs)
    payload = result.to_contract_payload()
    assert (
        payload["input_provenance"]["source_image_sha256"]
        == kwargs["provenance"].source_image_sha256
    )
    assert payload["analysis_trace"] == kwargs["workflow_events"]
    assert result.analysis_trace == draft.analysis_trace
    assert (draft, kwargs) == baseline
    result.findings[0].evidence_ids.append("changed")
    result.study_manifest.metadata["changed"] = "private mutation"
    result.workflow_events[0]["detail"] = "changed"
    assert (draft, kwargs) == baseline


def test_actual_gateway_draft_parser_does_not_become_a_scientific_ledger(inputs):
    from dicom_overlay.infrastructure.openclaw_client import OpenClawClient

    _, kwargs = inputs
    client = OpenClawClient(gateway_url="ws://127.0.0.1:1")
    draft = client._parse_result(
        {
            "payload": {
                "modality": "EKG",
                "summary": "Synthetic legacy draft.",
                "severity": "info",
                "findings": [],
                "checklist": {},
                "incomplete": True,
                "incomplete_reasons": ["Synthetic partial source."],
                "observations": [{"id": "model-invented-unparsed-ledger"}],
                "input_provenance": {"source_image_sha256": "f" * 64},
                "workflow_events": [{"stage": "intake", "status": "completed"}],
            }
        },
        elapsed_ms=1,
    )
    assert draft.input_provenance is None and draft.workflow_events == []
    assert draft.observations == []
    with pytest.raises(
        ContractAssemblyError, match=r"^missing_model_observation_ledger$"
    ):
        assemble_review_contract(draft, **kwargs)


@pytest.mark.parametrize("host_event", [False, True])
def test_tool_geometry_needs_independent_source_proof_and_recorded_stage(
    inputs, host_event
):
    draft, kwargs = inputs
    tool = replace(
        draft.evidence[0],
        id="tool-1",
        kind="tool_output",
        tool_name="synthetic-localizer",
        tool_version="test-only",
    )
    draft.evidence.append(tool)
    kwargs["trusted_evidence"] = deepcopy(draft.evidence)
    if host_event:
        kwargs["workflow_events"].insert(
            3,
            {
                "stage": "independent_evidence",
                "status": "completed",
                "detail": "Synthetic host tool receipt after blind pass.",
            },
        )
        result = assemble_review_contract(draft, **kwargs)
        assert (
            result.to_contract_payload()["evidence"][1]["tool_name"]
            == "synthetic-localizer"
        )
    else:
        with pytest.raises(
            ContractAssemblyError, match=r"^tool_evidence_without_host_workflow_event$"
        ):
            assemble_review_contract(draft, **kwargs)


@pytest.mark.parametrize(
    "change,category",
    [
        ("missing_asset", "asset_inventory_mismatch"),
        ("extra_asset", "asset_inventory_mismatch"),
        ("wrong_bytes", "asset_bytes_mismatch"),
        ("mutable_bytes", "missing_immutable_input_bytes"),
        ("asset_modality", "asset_modality_mismatch"),
        ("duplicate_asset", "duplicate_asset_identity"),
        ("missing_primary", "ambiguous_or_missing_primary_asset"),
        ("source_kind", "source_kind_mismatch"),
        ("metadata", "unapproved_study_metadata"),
        ("draft_provenance", "draft_contains_host_owned_bindings"),
        ("draft_study", "draft_contains_host_owned_bindings"),
        ("draft_scope", "draft_contains_host_owned_bindings"),
        ("draft_events", "draft_contains_host_owned_bindings"),
        ("missing_ledger", "missing_model_observation_ledger"),
        ("missing_proof", "evidence_inventory_mismatch"),
        ("extra_proof", "evidence_inventory_mismatch"),
        ("duplicate_proof", "duplicate_trusted_evidence"),
        ("duplicate_prediction", "duplicate_draft_evidence"),
        ("altered_evidence", "evidence_receipt_disagreement"),
        ("false_source_ref", "evidence_asset_binding_mismatch"),
        ("tool_box", "tool_label_is_not_spatial_evidence"),
        ("foreign_finding", "finding_not_in_primary_source_coordinates"),
    ],
)
def test_host_bindings_fail_closed_without_repair(inputs, change, category):
    draft, kwargs = inputs
    if change == "missing_asset":
        kwargs["asset_bytes"] = {}
    elif change == "extra_asset":
        kwargs["asset_bytes"]["unknown"] = b"extra"
    elif change == "wrong_bytes":
        kwargs["asset_bytes"]["image-1"] = b"wrong"
    elif change == "mutable_bytes":
        kwargs["asset_bytes"]["image-1"] = bytearray(b"mutable")
    elif change == "asset_modality":
        asset = replace(kwargs["study"].assets[0], modality="CXR")
        kwargs["study"] = replace(kwargs["study"], assets=(asset,))
    elif change == "duplicate_asset":
        kwargs["study"] = replace(kwargs["study"], assets=kwargs["study"].assets * 2)
    elif change == "missing_primary":
        kwargs["provenance"] = replace(
            kwargs["provenance"], source_image_sha256="0" * 64
        )
    elif change == "source_kind":
        kwargs["provenance"] = replace(kwargs["provenance"], source_kind="dicom")
    elif change == "metadata":
        kwargs["study"].metadata["unapproved"] = "not a permitted host field"
    elif change.startswith("draft_"):
        field, value = {
            "draft_provenance": ("input_provenance", kwargs["provenance"]),
            "draft_study": ("study_manifest", kwargs["study"]),
            "draft_scope": ("assessment_scope", "complete_study"),
            "draft_events": ("workflow_events", kwargs["workflow_events"]),
        }[change]
        setattr(draft, field, value)
    elif change == "missing_ledger":
        draft.observations = []
    elif change == "missing_proof":
        kwargs["trusted_evidence"] = []
    elif change == "extra_proof":
        kwargs["trusted_evidence"].append(replace(draft.evidence[0], id="extra"))
    elif change == "duplicate_proof":
        kwargs["trusted_evidence"] *= 2
    elif change == "duplicate_prediction":
        draft.evidence *= 2
    elif change == "altered_evidence":
        draft.evidence[0] = replace(draft.evidence[0], description="altered")
    elif change in {"false_source_ref", "tool_box"}:
        changes = (
            {"source_ref": "unknown"}
            if change == "false_source_ref"
            else {"kind": "tool_output", "tool_name": "synthetic", "tool_version": "1"}
        )
        draft.evidence[0] = replace(draft.evidence[0], **changes)
        kwargs["trusted_evidence"] = deepcopy(draft.evidence)
    else:
        draft.findings[0] = replace(
            draft.findings[0],
            bboxes=[replace(draft.findings[0].bboxes[0], source_image_sha256="f" * 64)],
        )
    baseline = deepcopy(draft)
    with pytest.raises(ContractAssemblyError, match=f"^{category}$"):
        assemble_review_contract(draft, **kwargs)
    assert draft == baseline


@pytest.mark.parametrize(
    "change",
    [
        "missing_event",
        "reordered_events",
        "failed_event",
        "duplicate_event",
        "missing_axis",
        "unresolved_observation",
        "unverified_box",
        "wrong_scope",
        "normal_with_box",
        "no_review",
        "false_complete",
    ],
)
def test_public_scientific_invariants_remain_mandatory(inputs, change):
    draft, kwargs = inputs
    if change == "missing_event":
        kwargs["workflow_events"].pop(1)
    elif change == "reordered_events":
        kwargs["workflow_events"].reverse()
    elif change == "failed_event":
        kwargs["workflow_events"][1]["status"] = "failed"
    elif change == "duplicate_event":
        kwargs["workflow_events"].append(deepcopy(kwargs["workflow_events"][0]))
    elif change == "missing_axis":
        del draft.checklist["rhythm"]
    elif change == "unresolved_observation":
        draft.summary_observation_ids = ["nonexistent private prediction"]
    elif change == "unverified_box":
        draft.findings[0] = replace(
            draft.findings[0],
            bboxes=[replace(draft.findings[0].bboxes[0], verified=False)],
        )
    elif change == "wrong_scope":
        kwargs["assessment_scope"] = "complete_study"
    elif change == "normal_with_box":
        draft.findings[0] = replace(draft.findings[0], severity=Severity.NORMAL)
    elif change == "no_review":
        draft.review_required = False
    else:
        draft.incomplete = False
    with pytest.raises(
        ContractAssemblyError, match=r"^public_contract_rejected$"
    ) as failure:
        assemble_review_contract(draft, **kwargs)
    assert "private prediction" not in str(failure.value)
    assert failure.value.__suppress_context__


@pytest.mark.parametrize(
    "change",
    ["valid", "missing", "extra", "wrong_bytes", "parent", "duplicate", "cycle"],
)
def test_transform_chain_hashes_and_inventory(inputs, change):
    draft, kwargs = inputs
    output = b"synthetic transformed bytes"
    output_hash = sha256(output).hexdigest()
    source_hash = kwargs["provenance"].source_image_sha256
    transform = TransformationRecord("synthetic_test", output_hash, {}, source_hash)
    kwargs["provenance"] = replace(kwargs["provenance"], transformations=(transform,))
    kwargs["transform_bytes"] = {output_hash: output}
    if change == "missing":
        kwargs["transform_bytes"] = {}
    elif change == "extra":
        kwargs["transform_bytes"]["f" * 64] = b"extra"
    elif change == "wrong_bytes":
        kwargs["transform_bytes"][output_hash] = b"different"
    elif change == "parent":
        kwargs["provenance"] = replace(
            kwargs["provenance"],
            transformations=(replace(transform, parent_sha256="f" * 64),),
        )
    elif change == "duplicate":
        kwargs["provenance"] = replace(
            kwargs["provenance"], transformations=(transform, transform)
        )
    elif change == "cycle":
        kwargs["provenance"] = replace(
            kwargs["provenance"],
            transformations=(replace(transform, parent_sha256=output_hash),),
        )
    if change == "valid":
        result = assemble_review_contract(draft, **kwargs)
        assert (
            result.to_contract_payload()["input_provenance"]["transformations"][0][
                "output_sha256"
            ]
            == output_hash
        )
    else:
        with pytest.raises(ContractAssemblyError):
            assemble_review_contract(draft, **kwargs)
