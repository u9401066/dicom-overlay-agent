"""Reject unbound evidence BEFORE it enters a later model prompt."""

from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy

import pytest

from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
from medical_image_harness.models import Modality, RegionRect
from tests.unit.test_eval_artifact_validator import _ecg_receipt
from tests.unit.test_image_evidence_turn import SOURCE, Gateway

ARTIFACT = "wf-synthetic-bound"


def rehash(receipt):
    receipt["response_sha256"] = hashlib.sha256(
        json.dumps(
            receipt["response_evidence"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def bound_receipt(nonce):
    receipt = _ecg_receipt()
    for target in (receipt, receipt["response_evidence"]):
        target["evidence_nonce"] = nonce
        target["artifact_id_sha256"] = hashlib.sha256(ARTIFACT.encode()).hexdigest()
    rehash(receipt)
    return receipt


@pytest.fixture
def bound_client(tmp_path, monkeypatch):
    path = tmp_path / "waveform-audit.jsonl"
    monkeypatch.setenv("DICOM_ECGFOUNDER_AUDIT_PATH", str(path))
    client = OpenClawClient(gateway_token="synthetic", base_dir=tmp_path)
    with client.use_waveform_artifact(ARTIFACT) as nonce:
        yield client, path, nonce


def write_records(path, *records):
    with path.open("a", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record) + "\n")


@pytest.mark.parametrize(
    "field,value",
    [
        ("artifact_id_sha256", "f" * 64),
        ("model_id", "unrelated-model"),
        ("model_revision", "unrelated-revision"),
        ("checkpoint_sha256", "f" * 64),
        ("lead_mode", "single_lead"),
        ("prediction_count", 2),
        ("response_sha256", "f" * 64),
        ("source_sha256", "not-a-hash"),
        ("preprocessing_revision", ""),
        ("calibration_status", "invented"),
    ],
)
def test_mismatched_receipt_is_not_forwarded(bound_client, field, value):
    client, path, nonce = bound_client
    receipt = bound_receipt(nonce)
    receipt[field] = value
    write_records(path, receipt)
    assert client._supporting_waveform_evidence() is None
    # Evidence remains inspectable; rejection is not deletion or a model retry.
    assert client.waveform_evidence_receipts(nonce) == [receipt]


@pytest.mark.parametrize("value", [True, -0.1, 1.1, float("nan"), float("inf")])
def test_invalid_scores_are_not_forwarded(bound_client, value):
    client, path, nonce = bound_client
    receipt = bound_receipt(nonce)
    receipt["predictions"][0]["probability"] = value
    rehash(receipt)
    write_records(path, receipt)
    assert client._supporting_waveform_evidence() is None


@pytest.mark.parametrize("label", ["", "   ", "x" * 257])
def test_empty_or_unbounded_label_is_not_forwarded(bound_client, label):
    client, path, nonce = bound_client
    receipt = bound_receipt(nonce)
    receipt["predictions"][0]["label"] = label
    rehash(receipt)
    write_records(path, receipt)
    assert client._supporting_waveform_evidence() is None


def test_good_receipt_and_identical_replay_are_usable_once(bound_client):
    client, path, nonce = bound_client
    receipt = bound_receipt(nonce)
    write_records(path, receipt, receipt)
    assert client._supporting_waveform_evidence()["predictions"] == [
        {"label": "NORMAL SINUS RHYTHM", "uncalibrated_score": 0.9}
    ]
    assert len(client.waveform_evidence_receipts(nonce)) == 1


@pytest.mark.parametrize("same_call", [True, False])
def test_conflicting_or_multiple_calls_remain_unusable_across_turns(
    bound_client, same_call
):
    client, path, nonce = bound_client
    receipt = bound_receipt(nonce)
    write_records(path, receipt)
    assert client._supporting_waveform_evidence() is not None
    changed = deepcopy(receipt)
    changed["predictions"][0]["probability"] = 0.1
    if not same_call:
        changed["tool_call_id"] = "call-2"
    rehash(changed)
    write_records(path, changed)
    client._begin_run_trace("next-crop")
    assert client._supporting_waveform_evidence() is None
    assert len(client.waveform_evidence_receipts(nonce)) == 2
    assert client._supporting_waveform_evidence() is None


def test_failure_plus_success_is_not_exactly_once_evidence(bound_client):
    client, path, nonce = bound_client
    receipt = bound_receipt(nonce)
    failed = {**receipt, "tool_call_id": "failed-call", "status": "error"}
    write_records(path, failed, receipt)
    assert client._supporting_waveform_evidence() is None


def test_receipt_snapshot_mutation_cannot_poison_later_prompt(bound_client):
    client, path, nonce = bound_client
    receipt = bound_receipt(nonce)
    write_records(path, receipt)
    snapshot = client.waveform_evidence_receipts(nonce)
    snapshot[0]["predictions"][0]["label"] = "synthetic-injected-label"
    assert client._supporting_waveform_evidence()["predictions"][0]["label"] == (
        "NORMAL SINUS RHYTHM"
    )


@pytest.mark.parametrize(
    "field,value", [("spatial_localization", "bbox"), ("use_policy", "diagnosis")]
)
def test_rehashed_response_cannot_claim_spatial_or_diagnostic_authority(
    bound_client, field, value
):
    client, path, nonce = bound_client
    receipt = bound_receipt(nonce)
    receipt["response_evidence"][field] = value
    rehash(receipt)
    write_records(path, receipt)
    assert client._supporting_waveform_evidence() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["valid", "wrong_artifact", "wrong_response", "cxr"])
async def test_real_refine_send_path_includes_only_eligible_support(bound_client, case):
    client, path, nonce = bound_client
    gateway = Gateway(body='{"deltas":[]}')
    client._ws, client._connected, client._gateway_protocol = gateway, True, 4
    receipt = bound_receipt(nonce)
    if case == "wrong_artifact":
        # Internally consistent, but associated with a different host binding.
        for section in (receipt, receipt["response_evidence"]):
            section["artifact_id_sha256"] = "f" * 64
        rehash(receipt)
    elif case == "wrong_response":
        receipt["response_evidence"]["model"]["revision"] = "changed"
        rehash(receipt)
    write_records(path, receipt)
    result = await client.refine(
        base64.b64encode(SOURCE).decode(),
        Modality.CXR if case == "cxr" else Modality.EKG,
        [],
        hypothesis=None,
        crop_region=RegionRect(0, 0, 1, 1),
    )
    assert result.deltas == () and len(gateway.sent) == 1
    prompt = gateway.sent[0]["params"]["message"]
    assert ("NORMAL SINUS RHYTHM" in prompt) is (case == "valid")
    assert ('"supporting_waveform_evidence"' in prompt) is (case == "valid")
    assert client.last_run_trace()["parse_retry_count"] == 0


def test_different_nonce_does_not_taint_current_binding(bound_client):
    client, path, nonce = bound_client
    foreign = bound_receipt("f" * 32)
    write_records(path, foreign, bound_receipt(nonce))
    assert client._supporting_waveform_evidence() is not None
    assert len(client.waveform_evidence_receipts(nonce)) == 1


def test_duplicate_label_list_is_rejected(bound_client):
    client, path, nonce = bound_client
    receipt = bound_receipt(nonce)
    receipt["predictions"].append(deepcopy(receipt["predictions"][0]))
    receipt["prediction_count"] = 2
    rehash(receipt)
    write_records(path, receipt)
    assert client._supporting_waveform_evidence() is None


@pytest.mark.parametrize(
    "raw",
    [None, "{}", "[]", "not-json", '{"x":1,"x":2}', "x" * (512 * 1024 + 1)],
    ids=["null", "empty", "array", "invalid-json", "duplicate-key", "oversize"],
)
def test_present_native_bytes_must_validate_without_legacy_fallback(bound_client, raw):
    client, path, nonce = bound_client
    receipt = bound_receipt(nonce)
    receipt["response_canonical_json"] = raw
    write_records(path, receipt)
    assert client._supporting_waveform_evidence() is None


def test_native_canonical_bytes_cannot_disagree_with_projected_fields(bound_client):
    client, path, nonce = bound_client
    receipt = bound_receipt(nonce)
    copied = deepcopy(receipt["response_evidence"])
    copied["predictions"][0]["probability"] = 0.8
    raw = json.dumps(copied, sort_keys=True, separators=(",", ":"))
    receipt["response_canonical_json"] = raw
    receipt["response_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    write_records(path, receipt)
    assert client._supporting_waveform_evidence() is None
