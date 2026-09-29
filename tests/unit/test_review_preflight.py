from copy import deepcopy

import pytest

from dicom_overlay.application.contract_assembly import (
    ContractAssemblyError,
    assemble_review_contract,
    preflight_review_contract,
    review_content_sha256,
)
from tests.unit.test_contract_assembly import inputs as inputs


def prefix(kwargs):
    kwargs = deepcopy(kwargs)
    kwargs["workflow_events"] = kwargs["workflow_events"][:-2]
    return kwargs


def test_preflight_snapshot_is_not_canonical_and_does_not_alias(inputs):
    draft, kwargs = inputs
    bindings = prefix(kwargs)
    before = deepcopy((draft, bindings))
    prepared = preflight_review_contract(draft, **bindings)
    assert (draft, bindings) == before
    assert len(prepared.result.workflow_events) == 4
    assert prepared.content_sha256 == review_content_sha256(prepared.result)
    with pytest.raises(ValueError):
        prepared.result.to_contract_payload()
    prepared.result.findings.clear()
    draft.findings.clear()
    assert prepared.result.findings


def test_real_final_events_do_not_change_review_content_fingerprint(inputs):
    draft, kwargs = inputs
    prepared = preflight_review_contract(draft, **prefix(kwargs))
    final = assemble_review_contract(draft, **kwargs)
    assert review_content_sha256(final) == prepared.content_sha256
    final.summary += " Changed content."
    assert review_content_sha256(final) != prepared.content_sha256


@pytest.mark.parametrize(
    "change", ["source", "evidence", "review", "future", "missing_axis"]
)
def test_preflight_does_not_weaken_source_content_or_event_checks(inputs, change):
    draft, kwargs = inputs
    bindings = prefix(kwargs)
    if change == "source":
        bindings["asset_bytes"]["image-1"] = b"not the supplied source"
    elif change == "evidence":
        bindings["trusted_evidence"] = []
    elif change == "review":
        draft.review_required = False
    elif change == "future":
        bindings["workflow_events"] = kwargs["workflow_events"]
    else:
        del draft.checklist["rhythm"]
    with pytest.raises(ContractAssemblyError):
        preflight_review_contract(draft, **bindings)
