"""Unit tests for the annotation accumulator (application layer).

Covers the pure geometric dedup maths (IoU, severity-max, notes merge), the
cross-turn accumulation, structured deltas (add / revise / retract), and the
explicit clear/reset boundary. All pure-function tests, no GUI.
"""

from __future__ import annotations

import pytest

from dicom_overlay.application.annotation_accumulator import (
    AnnotationAccumulator,
    apply_delta,
    dedupe_findings,
    iou,
    max_severity,
    merge_findings,
)
from dicom_overlay.domain.entities import (
    Finding,
    FindingDelta,
    FindingOp,
    RegionRect,
    Severity,
)


def _finding(
    fid: str,
    *,
    severity: Severity = Severity.WARNING,
    bbox: RegionRect | None = None,
    detail: str = "",
    label: str = "lesion",
    regions: list[str] | None = None,
    notes: list[str] | None = None,
    source: str = "ai",
) -> Finding:
    return Finding(
        id=fid,
        regions=regions or [],
        label=label,
        detail=detail,
        severity=severity,
        bboxes=[bbox] if bbox is not None else [],
        notes=notes or [],
        source=source,
    )


# --- iou -------------------------------------------------------------------


def test_iou_identical_boxes_is_one() -> None:
    box = RegionRect(x=0.1, y=0.1, w=0.2, h=0.2)
    assert iou(box, box) == pytest.approx(1.0)


def test_iou_disjoint_boxes_is_zero() -> None:
    a = RegionRect(x=0.0, y=0.0, w=0.1, h=0.1)
    b = RegionRect(x=0.5, y=0.5, w=0.1, h=0.1)
    assert iou(a, b) == 0.0


def test_iou_half_overlap() -> None:
    a = RegionRect(x=0.0, y=0.0, w=0.2, h=0.1)
    b = RegionRect(x=0.1, y=0.0, w=0.2, h=0.1)
    # intersection 0.1*0.1=0.01; union 0.02+0.02-0.01=0.03
    assert iou(a, b) == pytest.approx(1.0 / 3.0)


def test_iou_zero_area_is_zero() -> None:
    a = RegionRect(x=0.0, y=0.0, w=0.0, h=0.0)
    b = RegionRect(x=0.0, y=0.0, w=0.2, h=0.2)
    assert iou(a, b) == 0.0


# --- severity --------------------------------------------------------------


def test_max_severity_keeps_more_urgent() -> None:
    assert max_severity(Severity.WARNING, Severity.CRITICAL) is Severity.CRITICAL
    assert max_severity(Severity.NORMAL, Severity.INFO) is Severity.INFO


# --- dedupe_findings -------------------------------------------------------


def test_dedupe_overlapping_boxes_merge_into_one() -> None:
    a = _finding("a", bbox=RegionRect(x=0.1, y=0.1, w=0.2, h=0.2))
    b = _finding("b", bbox=RegionRect(x=0.11, y=0.11, w=0.2, h=0.2))
    merged = dedupe_findings([a], [b], iou_threshold=0.5)
    assert len(merged) == 1
    assert merged[0].id == "a"  # existing identity preserved


def test_dedupe_overlapping_different_diagnoses_stay_separate() -> None:
    box = RegionRect(x=0.1, y=0.1, w=0.2, h=0.2)
    elevation = _finding("st", label="ST elevation", bbox=box)
    q_wave = _finding("q", label="Pathologic Q wave", bbox=box)

    merged = dedupe_findings([elevation], [q_wave], iou_threshold=0.5)

    assert [finding.id for finding in merged] == ["st", "q"]


def test_dedupe_distinct_boxes_are_kept_separate() -> None:
    a = _finding("a", bbox=RegionRect(x=0.0, y=0.0, w=0.1, h=0.1))
    b = _finding("b", bbox=RegionRect(x=0.7, y=0.7, w=0.1, h=0.1))
    merged = dedupe_findings([a], [b], iou_threshold=0.5)
    assert {f.id for f in merged} == {"a", "b"}


def test_dedupe_never_downgrades_severity() -> None:
    existing = _finding(
        "a", severity=Severity.CRITICAL, bbox=RegionRect(0.1, 0.1, 0.2, 0.2)
    )
    incoming = _finding(
        "a2", severity=Severity.WARNING, bbox=RegionRect(0.11, 0.11, 0.2, 0.2)
    )
    merged = dedupe_findings([existing], [incoming], iou_threshold=0.5)
    assert len(merged) == 1
    assert merged[0].severity is Severity.CRITICAL


def test_dedupe_upgrades_severity_on_merge() -> None:
    existing = _finding(
        "a", severity=Severity.WARNING, bbox=RegionRect(0.1, 0.1, 0.2, 0.2)
    )
    incoming = _finding(
        "a2", severity=Severity.CRITICAL, bbox=RegionRect(0.11, 0.11, 0.2, 0.2)
    )
    merged = dedupe_findings([existing], [incoming], iou_threshold=0.5)
    assert merged[0].severity is Severity.CRITICAL


def test_dedupe_matches_by_id_without_bbox() -> None:
    a = _finding("dup", detail="first")
    b = _finding("dup", detail="second")
    merged = dedupe_findings([a], [b], iou_threshold=0.5)
    assert len(merged) == 1
    # Differing incoming detail is preserved as a note, not overwritten.
    assert merged[0].detail == "first"
    assert "second" in merged[0].notes


def test_dedupe_bboxless_distinct_ids_kept_separate() -> None:
    a = _finding("a", detail="x")
    b = _finding("b", detail="y")
    merged = dedupe_findings([a], [b], iou_threshold=0.5)
    assert len(merged) == 2


def test_dedupe_does_not_mutate_inputs() -> None:
    existing_list = [_finding("a", bbox=RegionRect(0.1, 0.1, 0.2, 0.2))]
    new_list = [_finding("b", bbox=RegionRect(0.11, 0.11, 0.2, 0.2))]
    dedupe_findings(existing_list, new_list, iou_threshold=0.5)
    assert len(existing_list) == 1
    assert len(new_list) == 1


def test_dedupe_invalid_threshold_raises() -> None:
    with pytest.raises(ValueError, match="iou_threshold"):
        dedupe_findings([], [], iou_threshold=1.5)


def test_merge_unions_boxes_and_notes() -> None:
    existing = _finding(
        "a",
        bbox=RegionRect(0.1, 0.1, 0.2, 0.2),
        notes=["n1"],
        regions=["v5"],
    )
    incoming = _finding(
        "a2",
        bbox=RegionRect(0.6, 0.6, 0.1, 0.1),
        notes=["n2"],
        regions=["v6"],
        source="interactive_ai_review",
    )
    merged = merge_findings(existing, incoming)
    assert len(merged.bboxes) == 2
    assert merged.notes == ["n1", "n2"]
    assert merged.regions == ["v5", "v6"]
    assert merged.source == "ai+interactive_ai_review"


# --- deltas: add / revise / retract ---------------------------------------


def test_apply_delta_retract_removes_by_id() -> None:
    findings = [_finding("a"), _finding("b")]
    delta = FindingDelta(op=FindingOp.RETRACT, finding=_finding("a"))
    result = apply_delta(findings, delta)
    assert {f.id for f in result} == {"b"}


def test_apply_delta_add_dedupes() -> None:
    findings = [_finding("a", bbox=RegionRect(0.1, 0.1, 0.2, 0.2))]
    delta = FindingDelta(
        op=FindingOp.ADD,
        finding=_finding("a2", bbox=RegionRect(0.11, 0.11, 0.2, 0.2)),
        note="looks like the same lesion",
    )
    result = apply_delta(findings, delta, iou_threshold=0.5)
    assert len(result) == 1
    assert "looks like the same lesion" in result[0].notes


def test_apply_delta_revise_may_downgrade_severity() -> None:
    findings = [_finding("a", severity=Severity.CRITICAL)]
    delta = FindingDelta(
        op=FindingOp.REVISE,
        finding=_finding("a", severity=Severity.NORMAL, detail="benign on review"),
        note="physician reviewed",
    )
    result = apply_delta(findings, delta)
    assert len(result) == 1
    assert result[0].severity is Severity.NORMAL
    assert "physician reviewed" in result[0].notes


def test_apply_delta_revise_missing_falls_back_to_add() -> None:
    findings = [_finding("a")]
    delta = FindingDelta(
        op=FindingOp.REVISE,
        finding=_finding("ghost", detail="new"),
    )
    result = apply_delta(findings, delta)
    assert {f.id for f in result} == {"a", "ghost"}


# --- accumulator state machine --------------------------------------------


def test_accumulator_accumulates_across_turns() -> None:
    acc = AnnotationAccumulator(iou_threshold=0.5)
    acc.add([_finding("a", bbox=RegionRect(0.1, 0.1, 0.2, 0.2))])
    acc.add([_finding("b", bbox=RegionRect(0.7, 0.7, 0.1, 0.1))])
    assert {f.id for f in acc.findings} == {"a", "b"}


def test_accumulator_merges_duplicate_across_turns() -> None:
    acc = AnnotationAccumulator(iou_threshold=0.5)
    acc.add([_finding("a", bbox=RegionRect(0.1, 0.1, 0.2, 0.2))])
    acc.add([_finding("a2", bbox=RegionRect(0.11, 0.11, 0.2, 0.2))])
    assert len(acc.findings) == 1


def test_accumulator_clear_resets() -> None:
    acc = AnnotationAccumulator()
    acc.add([_finding("a")])
    acc.clear()
    assert acc.findings == []


def test_accumulator_reset_preserves_primary_result_exactly() -> None:
    findings = [
        _finding("a", label="same", bbox=RegionRect(0.1, 0.1, 0.2, 0.2)),
        _finding("b", label="same", bbox=RegionRect(0.11, 0.11, 0.2, 0.2)),
    ]
    acc = AnnotationAccumulator()

    snapshot = acc.reset(findings)

    assert snapshot == findings
    assert [finding.id for finding in acc.findings] == ["a", "b"]


def test_accumulator_findings_returns_copy() -> None:
    acc = AnnotationAccumulator()
    acc.add([_finding("a")])
    snapshot = acc.findings
    snapshot.clear()
    assert len(acc.findings) == 1  # internal state untouched


def test_accumulator_apply_delta_retract() -> None:
    acc = AnnotationAccumulator()
    acc.add([_finding("a"), _finding("b")])
    acc.apply(FindingDelta(op=FindingOp.RETRACT, finding=_finding("a")))
    assert {f.id for f in acc.findings} == {"b"}


def test_accumulator_invalid_threshold_raises() -> None:
    with pytest.raises(ValueError, match="iou_threshold"):
        AnnotationAccumulator(iou_threshold=-0.1)


# --- PHI invariant: dedup never widens a region beyond the ROI -------------


def test_merge_keeps_all_boxes_within_unit_roi() -> None:
    existing = _finding("a", bbox=RegionRect(0.1, 0.1, 0.2, 0.2))
    incoming = _finding("a2", bbox=RegionRect(0.15, 0.15, 0.2, 0.2))
    merged = merge_findings(existing, incoming)
    for box in merged.bboxes:
        assert 0.0 <= box.x <= 1.0
        assert 0.0 <= box.y <= 1.0
        assert box.x + box.w <= 1.0 + 1e-9
        assert box.y + box.h <= 1.0 + 1e-9
