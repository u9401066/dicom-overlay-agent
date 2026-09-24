"""Host-owned assembly boundary for the public scientific contract.

Not wired into desktop inference yet. The host must supply real stage records,
validated evidence and the exact input/transform bytes. This is not a converter
from legacy 16-key predictions, a workflow-event generator, or clinical approval.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
from typing import TYPE_CHECKING

from medical_image_harness.provenance import canonical_json_sha256
from medical_image_harness.schema import preflight_validation_errors

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from medical_image_harness.models import AnalysisResult, Evidence
    from medical_image_harness.provenance import InputProvenance
    from medical_image_harness.study import StudyManifest


class ContractAssemblyError(ValueError):
    """A fixed, PHI-free failure category; never echo predictions or source data."""


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise ContractAssemblyError(category)


def _hash(data: bytes) -> str:
    _require(type(data) is bytes and bool(data), "missing_immutable_input_bytes")
    return sha256(data).hexdigest()


def _bind_review_contract(
    draft: AnalysisResult,
    *,
    provenance: InputProvenance,
    study: StudyManifest,
    assessment_scope: str,
    asset_bytes: Mapping[str, bytes],
    transform_bytes: Mapping[str, bytes],
    trusted_evidence: Sequence[Evidence],
    workflow_events: Sequence[Mapping[str, str]],
) -> AnalysisResult:
    """Bind independently checked host inputs without altering the draft.

    Public content/final validation is performed by the calling boundary below.

    ``asset_bytes`` is keyed by host manifest asset ID; ``transform_bytes`` by
    exact output SHA-256. Neither includes paths, window titles or patient IDs.
    ``trusted_evidence`` must come from the host's source/tool receipt validation,
    never be copied from model output just to satisfy this boundary. It must match
    the model-led ledger exactly; disagreement is rejected, not repaired silently.
    ``workflow_events`` is the host journal in execution order, not sorted or
    backfilled from a final report. The caller owns collecting those facts before
    this function is called. Passing its own invented records cannot attest to
    real execution; public-contract validation is not an independent observer.
    Hash/chain checks do not decode images or prove that a transform operation
    produced those bytes; the capture/crop adapter must supply that proof.

    Review-required state, observations, references, quality and claim certainty
    must already be truthful. No normal entries, observations, verified boxes,
    study completeness, review flags or completed events are manufactured here.
    """
    # Public dataclasses contain mutable collections; take private snapshots before
    # checking any cross-object equality. The returned object shares no lists.
    result = deepcopy(draft)
    provenance = deepcopy(provenance)
    study = deepcopy(study)
    evidence = deepcopy(list(trusted_evidence))
    events: list[dict[str, object]] = [
        deepcopy(dict(event)) for event in workflow_events
    ]
    assets = dict(asset_bytes)
    transforms = dict(transform_bytes)

    _require(provenance.deidentified is True, "untrusted_deidentification")
    _require(bool(study.assets), "missing_study_assets")
    asset_ids = [asset.id for asset in study.assets]
    _require(len(set(asset_ids)) == len(asset_ids), "duplicate_asset_identity")
    _require(set(assets) == set(asset_ids), "asset_inventory_mismatch")
    known_hashes = set()
    for asset in study.assets:
        _require(asset.deidentified is True, "untrusted_deidentification")
        _require(
            asset.modality == study.modality == result.modality.value,
            "asset_modality_mismatch",
        )
        _require(_hash(assets[asset.id]) == asset.sha256, "asset_bytes_mismatch")
        known_hashes.add(asset.sha256)
    primary = [a for a in study.assets if a.sha256 == provenance.source_image_sha256]
    _require(len(primary) == 1, "ambiguous_or_missing_primary_asset")
    _require(primary[0].source_kind == provenance.source_kind, "source_kind_mismatch")
    _require(not study.metadata, "unapproved_study_metadata")

    outputs = [t.output_sha256 for t in provenance.transformations]
    _require(len(set(outputs)) == len(outputs), "duplicate_transform_identity")
    _require(set(transforms) == set(outputs), "transform_inventory_mismatch")
    for transform in provenance.transformations:
        _require(transform.parent_sha256 in known_hashes, "unbound_transform_parent")
        _require(
            transform.output_sha256 not in known_hashes, "ambiguous_transform_output"
        )
        _require(
            _hash(transforms[transform.output_sha256]) == transform.output_sha256,
            "transform_bytes_mismatch",
        )
        known_hashes.add(transform.output_sha256)

    # Host-owned fields must not arrive as model assertions, or as an old run's
    # already-assembled state. Callers must retain raw drafts separately.
    _require(
        result.input_provenance is None
        and result.study_manifest is None
        and not result.assessment_scope
        and not result.workflow_events,
        "draft_contains_host_owned_bindings",
    )
    _require(bool(result.observations), "missing_model_observation_ledger")
    evidence_ids = [item.id for item in evidence]
    _require(len(set(evidence_ids)) == len(evidence_ids), "duplicate_trusted_evidence")
    predicted_ids = [item.id for item in result.evidence]
    _require(len(set(predicted_ids)) == len(predicted_ids), "duplicate_draft_evidence")
    _require(set(predicted_ids) == set(evidence_ids), "evidence_inventory_mismatch")
    trusted_by_id = {item.id: item for item in evidence}
    source_boxes = {
        box
        for item in evidence
        if item.kind in {"source_region", "source_frame"}
        for box in item.bboxes
        if box.verified
    }
    for item in result.evidence:
        _require(item == trusted_by_id[item.id], "evidence_receipt_disagreement")
        _require(item.source_image_sha256 in known_hashes, "unbound_evidence_source")
        if item.kind in {"source_region", "source_frame"}:
            referenced = [a for a in study.assets if a.id == item.source_ref]
            _require(
                len(referenced) == 1
                and referenced[0].sha256 == item.source_image_sha256,
                "evidence_asset_binding_mismatch",
            )
        if item.kind == "tool_output":
            _require(
                all(box in source_boxes for box in item.bboxes),
                "tool_label_is_not_spatial_evidence",
            )
            _require(
                any(
                    event.get("stage") == "independent_evidence"
                    and event.get("status") == "completed"
                    for event in events
                ),
                "tool_evidence_without_host_workflow_event",
            )

    # A screenshot source is the immutable ROI, never a crop-local overlay plane.
    for finding in result.findings:
        for box in finding.bboxes:
            _require(
                box.source_image_sha256 == provenance.source_image_sha256,
                "finding_not_in_primary_source_coordinates",
            )

    result.input_provenance = provenance
    result.study_manifest = study
    result.assessment_scope = assessment_scope
    result.workflow_events = events
    return result


@dataclass(frozen=True)
class PreparedReview:
    """Content-checked intermediate snapshot; not a complete canonical result."""

    _result: AnalysisResult = field(repr=False)
    content_sha256: str

    @property
    def result(self) -> AnalysisResult:
        return deepcopy(self._result)


def review_content_sha256(result: AnalysisResult) -> str:
    """Bind review content independently of later execution-event completion."""
    payload = result.to_contract_payload(validate=False)
    del payload["analysis_trace"]
    return canonical_json_sha256(payload)


def preflight_review_contract(
    draft: AnalysisResult,
    *,
    provenance: InputProvenance,
    study: StudyManifest,
    assessment_scope: str,
    asset_bytes: Mapping[str, bytes],
    transform_bytes: Mapping[str, bytes],
    trusted_evidence: Sequence[Evidence],
    workflow_events: Sequence[Mapping[str, str]],
) -> PreparedReview:
    """Verify content/source/executed prefix without claiming future handoff."""
    result = _bind_review_contract(
        draft,
        provenance=provenance,
        study=study,
        assessment_scope=assessment_scope,
        asset_bytes=asset_bytes,
        transform_bytes=transform_bytes,
        trusted_evidence=trusted_evidence,
        workflow_events=workflow_events,
    )
    try:
        errors = preflight_validation_errors(result.to_contract_payload(validate=False))
        _require(not errors, "public_preflight_rejected")
        content_sha = review_content_sha256(result)
    except (ValueError, TypeError, AttributeError, KeyError):
        raise ContractAssemblyError("public_preflight_rejected") from None
    return PreparedReview(result, content_sha)


def assemble_review_contract(
    draft: AnalysisResult,
    *,
    provenance: InputProvenance,
    study: StudyManifest,
    assessment_scope: str,
    asset_bytes: Mapping[str, bytes],
    transform_bytes: Mapping[str, bytes],
    trusted_evidence: Sequence[Evidence],
    workflow_events: Sequence[Mapping[str, str]],
) -> AnalysisResult:
    """Bind host inputs and require the unchanged full public contract gate."""
    result = _bind_review_contract(
        draft,
        provenance=provenance,
        study=study,
        assessment_scope=assessment_scope,
        asset_bytes=asset_bytes,
        transform_bytes=transform_bytes,
        trusted_evidence=trusted_evidence,
        workflow_events=workflow_events,
    )
    try:
        result.to_contract_payload()
    except (ValueError, TypeError, AttributeError, KeyError):
        # Public errors can include model-generated clinical text; do not log or
        # propagate it through an application exception/telemetry path.
        raise ContractAssemblyError("public_contract_rejected") from None
    return result
