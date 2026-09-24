"""Synthetic clinical decisions; no accuracy or actual model execution claim."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256

import pytest

from dicom_overlay.infrastructure.scientific_reconciliation import decode_reconciliation
from medical_image_harness.models import Modality
from tests.unit.test_contract_assembly import inputs as inputs
from tests.unit.test_scientific_draft import decode
from tests.unit.test_scientific_draft import draft_request as draft_request


def envelope(payload):
    return {
        "agreements": ["Synthetic image observation remains possible."],
        "conflicts": [],
        "unsupported_claims": [],
        "uninspected_regions": ["Partial image."],
        "decisions": [
            {
                "action": "confirm",
                "prior_finding_id": "f1",
                "final_finding_id": "f1",
                "rationale": "Synthetic source reinspection.",
            }
        ],
        "draft": deepcopy(payload),
    }


def reconcile(wrapper, payload, host):
    return decode_reconciliation(
        json.dumps(wrapper, ensure_ascii=False).encode(),
        blind=decode(payload, host),
        modality=Modality.EKG,
        trusted_evidence=host["trusted_evidence"],
        elapsed_ms=9,
    )


def test_confirm_keeps_original_wrapper_bytes_and_does_not_mutate_blind(draft_request):
    payload, host = draft_request
    before = deepcopy(payload)
    wrapper = envelope(payload)
    result = reconcile(wrapper, payload, host)
    assert result.response_bytes == json.dumps(wrapper, ensure_ascii=False).encode()
    assert result.response_sha256 == sha256(result.response_bytes).hexdigest()
    assert payload == before
    assert result.decoded.draft.input_provenance is None
    assert not result.decoded.draft.workflow_events
    with pytest.raises(ValueError):
        result.decoded.draft.to_contract_payload()


@pytest.mark.parametrize("action", ["revise", "retract", "unevaluable", "add"])
def test_explicit_alternative_decisions(draft_request, action):
    payload, host = draft_request
    wrapper = envelope(payload)
    decision = wrapper["decisions"][0]
    if action == "add":
        added = deepcopy(wrapper["draft"]["findings"][0])
        added["id"] = "f2"
        wrapper["draft"]["findings"].append(added)
        wrapper["decisions"].append(
            {
                "action": "add",
                "prior_finding_id": "",
                "final_finding_id": "f2",
                "rationale": "New synthetic candidate.",
            }
        )
    elif action in {"retract", "unevaluable"}:
        decision.update(action=action, final_finding_id="")
        wrapper["draft"]["findings"] = []
    else:
        decision["action"] = action
        wrapper["draft"]["findings"][0]["detail"] = "Revised synthetic observation."
    assert reconcile(wrapper, payload, host).decoded.draft.observations


@pytest.mark.parametrize(
    "change,error",
    [
        ("omit", "unreviewed_blind_finding"),
        ("duplicate", "invalid_prior_finding"),
        ("prior", "invalid_prior_finding"),
        ("final", "invalid_final_finding"),
        ("keep_retracted", "removed_finding_retained"),
        ("add_existing", "invalid_added_finding"),
        ("changed_claim", "confirmation_changed_clinical_claim"),
        ("changed_observation", "confirmation_changed_observation"),
        ("new_without_decision", "unchallenged_final_finding"),
        ("rationale", "invalid_challenge_decision"),
        ("unknown_action", "invalid_challenge_decision"),
        ("extra_decision_key", "invalid_challenge_decision"),
        ("inventory", "invalid_reconciliation_inventory"),
        ("extra_envelope", "invalid_reconciliation_envelope"),
    ],
)
def test_inconsistent_challenge_rejected_without_repair(draft_request, change, error):
    payload, host = draft_request
    wrapper = envelope(payload)
    decision = wrapper["decisions"][0]
    if change == "omit":
        wrapper["decisions"] = []
    elif change == "duplicate":
        wrapper["decisions"] *= 2
    elif change in {"prior", "final"}:
        decision[f"{change}_finding_id"] = "missing"
    elif change == "keep_retracted":
        decision.update(action="retract", final_finding_id="")
    elif change == "add_existing":
        decision.update(action="add", prior_finding_id="")
    elif change == "changed_claim":
        wrapper["draft"]["findings"][0]["detail"] = "Changed claim."
    elif change == "changed_observation":
        wrapper["draft"]["observations"][0]["finding"] = "Changed observation."
    elif change == "new_without_decision":
        extra = deepcopy(wrapper["draft"]["findings"][0])
        extra["id"] = "f2"
        wrapper["draft"]["findings"].append(extra)
    elif change == "rationale":
        decision["rationale"] = " "
    elif change == "unknown_action":
        decision["action"] = "auto_accept"
    elif change == "extra_decision_key":
        decision["verified"] = "true"
    elif change == "inventory":
        wrapper["conflicts"] = "none"
    else:
        wrapper["host_provenance"] = {}
    with pytest.raises(ValueError, match=error):
        reconcile(wrapper, payload, host)


def test_does_not_repair_duplicate_keys_or_raw_fences(draft_request):
    payload, host = draft_request
    for raw in (b'{"draft":{},"draft":{}}', b"```json\n{}\n```"):
        with pytest.raises(ValueError):
            decode_reconciliation(
                raw,
                blind=decode(payload, host),
                modality=Modality.EKG,
                trusted_evidence=host["trusted_evidence"],
                elapsed_ms=0,
            )
