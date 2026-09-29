"""Synthetic compact edits preserve strict original scientific validation."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from dicom_overlay.infrastructure.scientific_delta import (
    build_scientific_delta_prompt,
    decode_scientific_delta,
)
from medical_image_harness.models import Modality
from tests.unit.test_contract_assembly import inputs as inputs
from tests.unit.test_scientific_draft import decode
from tests.unit.test_scientific_draft import draft_request as draft_request
from tests.unit.test_scientific_reconciliation import envelope


def delta_for(payload, host):
    full = envelope(payload)
    return {
        **{k: v for k, v in full.items() if k != "draft"},
        "delta_version": "1",
        "base_response_sha256": decode(payload, host).response_sha256,
        "operations": [],
        "localizations": [
            {
                "evidence_id": "e1",
                "action": "use",
                "finding_ids": ["f1"],
                "rationale": "Synthetic visible match.",
            }
        ],
    }


def read_delta(delta, payload, host):
    return decode_scientific_delta(
        json.dumps(delta, ensure_ascii=False).encode(),
        prior=decode(payload, host),
        modality=Modality.EKG,
        trusted_evidence=host["trusted_evidence"],
        elapsed_ms=3,
    )


def test_unchanged_delta_preserves_full_draft_and_exact_original_bytes(draft_request):
    payload, host = draft_request
    delta = delta_for(payload, host)
    original = deepcopy((payload, host, delta))
    result = read_delta(delta, payload, host)
    assert json.loads(result.decoded.response_bytes) == payload
    assert result.response_bytes == json.dumps(delta, ensure_ascii=False).encode()
    assert len(result.response_bytes) < len(json.dumps(envelope(payload)).encode()) / 2
    assert (payload, host, delta) == original


@pytest.mark.parametrize("action", ["confirm", "revise"])
def test_explicit_observation_edit_still_requires_revise(draft_request, action):
    payload, host = draft_request
    delta = delta_for(payload, host)
    delta["operations"] = [
        {
            "op": "update",
            "target": "observations",
            "id": "o1",
            "value": {"finding": "New synthetic description"},
        }
    ]
    delta["decisions"][0]["action"] = action
    if action == "confirm":
        with pytest.raises(ValueError, match="confirmation_changed_observation"):
            read_delta(delta, payload, host)
    else:
        result = read_delta(delta, payload, host)
        assert (
            result.decoded.draft.observations[0].finding == "New synthetic description"
        )


@pytest.mark.parametrize(
    "change",
    [
        "base",
        "version",
        "duplicate",
        "unknown",
        "rename",
        "host",
        "quality",
        "full",
        "extra",
    ],
)
def test_invalid_or_ambiguous_delta_is_not_repaired(draft_request, change):
    payload, host = draft_request
    delta = delta_for(payload, host)
    operation = {
        "op": "update",
        "target": "observations",
        "id": "o1",
        "value": {"evidence_ids": ["e1"]},
    }
    if change == "base":
        delta["base_response_sha256"] = "a" * 64
    elif change == "version":
        delta["delta_version"] = "2"
    elif change == "duplicate":
        delta["operations"] = [operation, deepcopy(operation)]
    elif change == "unknown":
        delta["operations"] = [{**operation, "id": "unknown"}]
    elif change == "rename":
        delta["operations"] = [{**operation, "value": {"id": "o2"}}]
    elif change in {"host", "quality"}:
        delta["operations"] = [
            {
                "op": "update",
                "target": "report",
                "id": "",
                "value": {
                    "input_provenance" if change == "host" else "image_quality": {}
                },
            }
        ]
    elif change == "full":
        delta["draft"] = payload
    else:
        delta["operations"] = [{**operation, "verified": True}]
    original = deepcopy(delta)
    with pytest.raises(ValueError):
        read_delta(delta, payload, host)
    assert delta == original


@pytest.mark.parametrize(
    "change",
    [
        "omitted",
        "unknown",
        "duplicate",
        "unlinked",
        "reject_retained",
        "blank_reason",
        "wrong_finding",
    ],
)
def test_every_localization_needs_a_consistent_explicit_disposition(
    draft_request, change
):
    payload, host = draft_request
    delta = delta_for(payload, host)
    item = delta["localizations"][0]
    if change == "omitted":
        delta["localizations"] = []
    elif change == "unknown":
        item["evidence_id"] = "missing"
    elif change == "duplicate":
        delta["localizations"] *= 2
    elif change == "unlinked":
        delta["operations"] = [
            {
                "op": "update",
                "target": "findings",
                "id": "f1",
                "value": {"bbox_evidence_ids": []},
            }
        ]
    elif change == "reject_retained":
        item.update(action="reject", finding_ids=[])
    elif change == "blank_reason":
        item["rationale"] = " "
    else:
        item["finding_ids"] = ["unknown"]
    with pytest.raises(ValueError):
        read_delta(delta, payload, host)


def test_explicit_rejection_removes_geometry_without_forcing_a_box(draft_request):
    payload, host = draft_request
    delta = delta_for(payload, host)
    host["trusted_evidence"].append(
        replace(host["trusted_evidence"][0], id="e2", bboxes=[])
    )
    delta["operations"] = [
        {
            "op": "update",
            "target": "observations",
            "id": "o1",
            "value": {"evidence_ids": ["e2"]},
        },
        {
            "op": "update",
            "target": "findings",
            "id": "f1",
            "value": {"evidence_ids": ["e2"], "bbox_evidence_ids": []},
        },
    ]
    delta["localizations"][0].update(
        action="reject",
        finding_ids=[],
        rationale="Geometry does not match this synthetic claim.",
    )
    result = read_delta(delta, payload, host)
    assert result.decoded.draft.findings[0].bboxes == []


def test_retained_finding_and_new_finding_decisions_survive_delta(draft_request):
    payload, host = draft_request
    delta = delta_for(payload, host)
    added = deepcopy(payload["findings"][0])
    added["id"] = "f2"
    delta["operations"] = [
        {"op": "add", "target": "findings", "id": "f2", "value": added}
    ]
    delta["decisions"].append(
        {
            "action": "add",
            "prior_finding_id": "",
            "final_finding_id": "f2",
            "rationale": "Additional synthetic candidate",
        }
    )
    delta["localizations"][0]["finding_ids"].append("f2")
    assert len(read_delta(delta, payload, host).decoded.draft.findings) == 2


def test_retract_has_no_stale_localization(draft_request):
    payload, host = draft_request
    delta = delta_for(payload, host)
    delta["operations"] = [
        {"op": "remove", "target": "findings", "id": "f1", "value": {}}
    ]
    delta["decisions"][0].update(action="retract", final_finding_id="")
    delta["localizations"][0].update(action="reject", finding_ids=[])
    # The observation still refers to rejected geometry, which is not hidden.
    with pytest.raises(ValueError, match="rejected_localization_retained"):
        read_delta(delta, payload, host)


def test_prompt_does_not_request_a_full_repeated_report(draft_request):
    payload, host = draft_request
    prior = decode(payload, host)
    text = build_scientific_delta_prompt(prior, Modality.EKG, host["trusted_evidence"])
    assert prior.response_sha256 in text
    assert "NOT a full draft" in text and "EVERY supplied geometry" in text
    assert "Each decision has exactly" in text and "shared observation" in text
    assert '"draft":{...}' not in text


@pytest.mark.parametrize(
    "operations",
    [
        None,
        {},
        [None],
        [{"op": []}],
        [{"op": "update", "target": [], "id": "o1", "value": {}}],
        [
            {
                "op": "remove",
                "target": "findings",
                "id": "f1",
                "value": {"label": "not empty"},
            }
        ],
    ],
)
def test_malformed_operation_shapes_fail_with_bounded_errors(draft_request, operations):
    payload, host = draft_request
    delta = delta_for(payload, host)
    delta["operations"] = operations
    with pytest.raises(ValueError) as error:
        read_delta(delta, payload, host)
    assert len(str(error.value)) < 80


def test_delta_preserves_required_checklist_and_immutable_qc(draft_request):
    payload, host = draft_request
    delta = delta_for(payload, host)
    delta["operations"] = [
        {"op": "remove", "target": "checklist", "id": "rhythm", "value": {}}
    ]
    with pytest.raises(ValueError, match="draft_schema_rejected"):
        read_delta(delta, payload, host)


def test_second_delta_must_bind_to_materialized_previous_stage(draft_request):
    payload, host = draft_request
    first = delta_for(payload, host)
    first["operations"] = [
        {
            "op": "update",
            "target": "report",
            "id": "",
            "value": {"summary": "Revised synthetic impression"},
        }
    ]
    previous = read_delta(first, payload, host)
    stale = delta_for(payload, host)
    with pytest.raises(ValueError, match="delta_base_mismatch"):
        decode_scientific_delta(
            json.dumps(stale).encode(),
            prior=previous.decoded,
            modality=Modality.EKG,
            trusted_evidence=host["trusted_evidence"],
            elapsed_ms=1,
        )
    stale["base_response_sha256"] = previous.decoded.response_sha256
    current = decode_scientific_delta(
        json.dumps(stale).encode(),
        prior=previous.decoded,
        modality=Modality.EKG,
        trusted_evidence=host["trusted_evidence"],
        elapsed_ms=1,
    )
    assert current.decoded.draft.summary == "Revised synthetic impression"
