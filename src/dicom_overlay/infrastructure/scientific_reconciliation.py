"""Explicit model challenge decisions over a retained blind scientific draft.

The envelope is execution evidence, not a second clinical schema or a truth
oracle. Clinical claims still use the pinned public scientific draft decoder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from dicom_overlay.infrastructure.scientific_draft import (
    DecodedScientificDraft,
    decode_scientific_draft,
)
from dicom_overlay.infrastructure.strict_json import read_json_object

if TYPE_CHECKING:
    from collections.abc import Sequence

    from medical_image_harness.models import Evidence, Modality

_LISTS = ("agreements", "conflicts", "unsupported_claims", "uninspected_regions")
_ACTIONS = {"confirm", "revise", "retract", "add", "unevaluable"}
_DECISION_KEYS = {"action", "prior_finding_id", "final_finding_id", "rationale"}


@dataclass(frozen=True)
class ReconciledScientificDraft:
    decoded: DecodedScientificDraft = field(repr=False)
    response_bytes: bytes = field(repr=False)
    response_sha256: str


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise ValueError(category)


def reconciliation_instruction() -> str:
    return (
        'Return exactly {"agreements":[],"conflicts":[],"unsupported_claims":[], '
        '"uninspected_regions":[],"decisions":[],"draft":{...}}. The four lists '
        "contain short visible-evidence statements (at most 64 per list, 2000 "
        "characters each), not private reasoning. draft must match the scientific "
        "draft schema below. Each decision has exactly action, prior_finding_id, "
        "final_finding_id, rationale. Cover every blind finding exactly once: "
        "confirm/revise retains its ID in the final draft; retract/unevaluable "
        "has an empty final ID and removes that finding. An add has an empty "
        "prior ID and a new final ID. Every final finding needs one decision. "
        "Use confirm only if the original clinical content is unchanged; "
        "geometry/evidence linkage may be added. Use revise for any changed "
        "wording, certainty, severity, interpretation or claim. Explain each "
        "decision in a short visible-evidence rationale. Do not force a finding. "
        "Retain unresolved conflicts and limitations for a targeted second look "
        "or specialist review; geometry verification is not clinical confirmation."
    )


def decode_reconciliation(
    raw: bytes,
    *,
    blind: DecodedScientificDraft,
    modality: Modality,
    trusted_evidence: Sequence[Evidence],
    elapsed_ms: int,
) -> ReconciledScientificDraft:
    envelope = read_json_object(raw)
    _require(
        set(envelope) == {*_LISTS, "decisions", "draft"},
        "invalid_reconciliation_envelope",
    )
    for name in _LISTS:
        entries = envelope[name]
        _require(
            isinstance(entries, list)
            and len(entries) <= 64
            and all(
                isinstance(item, str) and 0 < len(item.strip()) <= 2000
                for item in entries
            ),
            "invalid_reconciliation_inventory",
        )
    decoded = decode_scientific_draft(
        json.dumps(envelope["draft"], ensure_ascii=False, allow_nan=False).encode(),
        modality=modality,
        trusted_evidence=trusted_evidence,
        model_used="openclaw-unverified",
        elapsed_ms=elapsed_ms,
    )
    decisions = envelope["decisions"]
    _require(isinstance(decisions, list) and len(decisions) <= 128, "invalid_decisions")
    before = {finding.id: finding for finding in blind.draft.findings}
    after = {finding.id: finding for finding in decoded.draft.findings}
    seen_before: set[str] = set()
    seen_after: set[str] = set()
    for decision in decisions:
        _require(
            isinstance(decision, dict)
            and set(decision) == _DECISION_KEYS
            and all(isinstance(value, str) for value in decision.values()),
            "invalid_challenge_decision",
        )
        action, prior, final = (
            decision["action"],
            decision["prior_finding_id"],
            decision["final_finding_id"],
        )
        _require(
            action in _ACTIONS and 0 < len(decision["rationale"].strip()) <= 2000,
            "invalid_challenge_decision",
        )
        if action == "add":
            _require(prior == "" and final not in before, "invalid_added_finding")
        else:
            _require(
                prior in before and prior not in seen_before, "invalid_prior_finding"
            )
            seen_before.add(prior)
        if action in {"retract", "unevaluable"}:
            _require(final == "" and prior not in after, "removed_finding_retained")
        else:
            _require(
                final in after and final not in seen_after, "invalid_final_finding"
            )
            seen_after.add(final)
            if action != "add":
                _require(final == prior, "retained_finding_identity_changed")
            if action == "confirm":
                _require(
                    all(
                        getattr(before[prior], key) == getattr(after[final], key)
                        for key in (
                            "label",
                            "detail",
                            "severity",
                            "confidence",
                            "question",
                            "claim_type",
                            "regions",
                            "notes",
                            "source",
                            "observation_ids",
                        )
                    ),
                    "confirmation_changed_clinical_claim",
                )
                previous = {o.id: o for o in blind.draft.observations}
                current = {o.id: o for o in decoded.draft.observations}
                for observation_id in before[prior].observation_ids:
                    old, new = previous[observation_id], current[observation_id]
                    # Only independently bound evidence may be added on confirm.
                    _require(
                        _observation_claim(old) == _observation_claim(new),
                        "confirmation_changed_observation",
                    )
    _require(seen_before == set(before), "unreviewed_blind_finding")
    _require(seen_after == set(after), "unchallenged_final_finding")
    return ReconciledScientificDraft(decoded, raw, sha256(raw).hexdigest())


def _observation_claim(observation: Any) -> dict[str, Any]:
    return {
        key: value for key, value in vars(observation).items() if key != "evidence_ids"
    }
