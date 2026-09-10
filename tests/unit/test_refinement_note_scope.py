"""A crop's missing anatomy is not proof that the original ROI lacks it."""

from __future__ import annotations

import dataclasses

import pytest

from dicom_overlay.application.multi_pass import (
    RefinementAction,
    RefinementDelta,
    apply_refinement_delta,
    remap_bbox,
)
from dicom_overlay.domain.entities import Finding, RegionRect, Severity

_CROP = RegionRect(0.25, 0.5, 0.5, 0.25)
_SCOPE = "[Crop-only evidence; ROI x=0.2500 y=0.5000 w=0.5000 h=0.2500] "


def _finding(identifier: str, *, notes: list[str]) -> Finding:
    return Finding(
        id=identifier,
        regions=["lead_V4"],
        label="Visible waveform concern",
        detail="Review the marked segment.",
        severity=Severity.WARNING,
        bboxes=[RegionRect(0.1, 0.2, 0.2, 0.3)],
        notes=notes,
        confidence="low",
        question="Is the marked change reproducible?",
    )


@pytest.mark.parametrize(
    "action", [RefinementAction.ADD, RefinementAction.CONFIRM, RefinementAction.REVISE]
)
def test_crop_notes_and_rationale_keep_scope_without_changing_geometry(action):
    coarse = _finding("coarse", notes=["Original ROI includes labeled V1."])
    sibling = _finding("unrelated", notes=["Keep this finding unchanged."])
    payload = _finding("crop", notes=["V1 is absent; V2 and V6 are truncated."])
    delta = RefinementDelta(
        action,
        target_id=coarse.id if action is not RefinementAction.ADD else "",
        finding=payload,
        rationale="Limb-lead comparison is unavailable.",
    )

    result = apply_refinement_delta(
        [coarse, sibling], delta, crop_region=_CROP, expected_target_id=coarse.id
    )

    updated = result[-1] if action is RefinementAction.ADD else result[0]
    assert _SCOPE + payload.notes[0] in updated.notes
    assert _SCOPE + delta.rationale in updated.notes
    assert payload.notes[0] not in updated.notes
    assert delta.rationale not in updated.notes
    assert updated.bboxes == [remap_bbox(payload.bboxes[0], _CROP)]
    assert updated.detail == payload.detail
    assert updated.severity is Severity.WARNING
    assert result[1] is sibling
    assert coarse.notes == ["Original ROI includes labeled V1."]
    assert payload.notes == ["V1 is absent; V2 and V6 are truncated."]
    if action is not RefinementAction.ADD:
        assert updated.id == coarse.id
        assert updated.notes[0] == coarse.notes[0]


def test_confirm_without_payload_scopes_rationale_but_preserves_original():
    coarse = _finding("coarse", notes=["Whole-ROI observation."])
    result = apply_refinement_delta(
        [coarse],
        RefinementDelta(
            RefinementAction.CONFIRM,
            target_id=coarse.id,
            rationale="Only the selected segment was assessed.",
        ),
        crop_region=_CROP,
        expected_target_id=coarse.id,
    )
    assert result[0] == dataclasses.replace(
        coarse,
        notes=[*coarse.notes, _SCOPE + "Only the selected segment was assessed."],
    )


def test_identical_crop_notes_are_deduplicated_without_losing_coarse_provenance():
    coarse = _finding("coarse", notes=["V1 is absent."])
    payload = _finding("crop", notes=[" V1 is absent. ", "", "   ", "V1 is absent."])
    delta = RefinementDelta(
        RefinementAction.CONFIRM,
        target_id=coarse.id,
        finding=payload,
        rationale=" V1 is absent. ",
    )
    result = apply_refinement_delta(
        [coarse], delta, crop_region=_CROP, expected_target_id=coarse.id
    )
    repeated = apply_refinement_delta(
        result, delta, crop_region=_CROP, expected_target_id=coarse.id
    )
    assert repeated[0].notes == ["V1 is absent.", _SCOPE + "V1 is absent."]


def test_same_words_from_different_crops_retain_both_scopes():
    coarse = _finding("coarse", notes=[])
    delta = RefinementDelta(
        RefinementAction.CONFIRM,
        target_id=coarse.id,
        rationale="The selected region lacks comparison leads.",
    )
    first = apply_refinement_delta(
        [coarse], delta, crop_region=_CROP, expected_target_id=coarse.id
    )
    second = apply_refinement_delta(
        first,
        delta,
        crop_region=RegionRect(0.0, 0.0, 1.0, 0.5),
        expected_target_id=coarse.id,
    )
    assert second[0].notes == [
        _SCOPE + delta.rationale,
        "[Crop-only evidence; ROI x=0.0000 y=0.0000 w=1.0000 h=0.5000] "
        + delta.rationale,
    ]


@pytest.mark.parametrize("rationale", ["", "   "])
def test_empty_crop_text_does_not_add_an_empty_scope_annotation(rationale):
    coarse = _finding("coarse", notes=["Original observation."])
    delta = RefinementDelta(
        RefinementAction.CONFIRM,
        target_id=coarse.id,
        finding=_finding("crop", notes=["", "  "]),
        rationale=rationale,
    )
    result = apply_refinement_delta(
        [coarse], delta, crop_region=_CROP, expected_target_id=coarse.id
    )
    assert result[0].notes == coarse.notes


def test_semantic_only_addition_still_scopes_notes():
    payload = dataclasses.replace(_finding("new", notes=["No comparison lead."]), bboxes=[])
    delta = RefinementDelta(RefinementAction.ADD, finding=payload)
    result = apply_refinement_delta(
        [],
        delta,
        crop_region=_CROP,
        expected_target_id=None,
        allow_unlocalized_add=True,
    )
    assert result[0].notes == [_SCOPE + "No comparison lead."]
    assert result[0].bboxes == []


def test_out_of_boundary_rationale_does_not_leak_into_any_finding():
    coarse = _finding("coarse", notes=[])
    original = [coarse]
    result = apply_refinement_delta(
        original,
        RefinementDelta(
            RefinementAction.CONFIRM,
            target_id="other",
            rationale="Unsupported crop assertion.",
        ),
        crop_region=_CROP,
        expected_target_id=coarse.id,
    )
    assert result is original
    assert coarse.notes == []
