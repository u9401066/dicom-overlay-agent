"""Accumulate overlay findings across multiple turns (application layer).

A reading is not a single shot: the multi-pass orchestrator looks at an image
several times, and the physician can guide / correct the reading through the
chat panel. Both streams must converge onto *one* non-overlapping set of overlay
markers, without the same lesion being boxed twice and without a flagged
``CRITICAL`` silently disappearing.

Design split (deliberate):

- **Geometric / structural dedup** lives here as deterministic *pure functions*
  (:func:`iou`, :func:`dedupe_findings`). It is mechanical bookkeeping: testable,
  zero-token, and auditable ("why did this box merge?"). It NEVER downgrades a
  finding's severity and never drops a finding on its own.
- **Clinical / semantic judgement** stays with the agent and the human. Their
  decisions arrive as explicit :class:`FindingDelta` operations
  (``ADD`` / ``REVISE`` / ``RETRACT``); only an explicit ``REVISE`` / ``RETRACT``
  may change or remove a finding. This keeps the can't-miss safety net intact.

DDD / PHI: this module only reshuffles already-computed findings. It decodes no
images and never widens capture — every bbox is still a subset of the ROI.
"""

from __future__ import annotations

import dataclasses

from dicom_overlay.domain.entities import (
    Finding,
    FindingDelta,
    FindingOp,
    RegionRect,
    Severity,
)

# Higher rank = more clinically urgent. Used so a merge keeps the *most* severe
# label and never downgrades it by accident.
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.NORMAL: 0,
    Severity.INFO: 1,
    Severity.WARNING: 2,
    Severity.CRITICAL: 3,
}

DEFAULT_IOU_THRESHOLD = 0.5


def iou(a: RegionRect, b: RegionRect) -> float:
    """Intersection-over-union of two normalized 0-1 rectangles.

    Returns 0.0 when the boxes do not overlap (or either has zero area). Pure
    and side-effect free so the dedup heuristic is fully unit-testable.
    """
    ax0, ay0, ax1, ay1 = a.x, a.y, a.x + a.w, a.y + a.h
    bx0, by0, bx1, by1 = b.x, b.y, b.x + b.w, b.y + b.h

    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    iw = ix1 - ix0
    ih = iy1 - iy0
    if iw <= 0.0 or ih <= 0.0:
        return 0.0
    inter = iw * ih
    area_a = a.w * a.h
    area_b = b.w * b.h
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def max_severity(a: Severity, b: Severity) -> Severity:
    """Return the more clinically urgent of two severities (never downgrades)."""
    return a if _SEVERITY_RANK[a] >= _SEVERITY_RANK[b] else b


def _boxes_overlap(a: Finding, b: Finding, iou_threshold: float) -> bool:
    """True when any bbox pair of ``a`` / ``b`` overlaps beyond the threshold."""
    for ba in a.bboxes:
        for bb in b.bboxes:
            if iou(ba, bb) >= iou_threshold:
                return True
    return False


def _same_finding(a: Finding, b: Finding, iou_threshold: float) -> bool:
    """Two findings are "the same" if they share an id or overlap geometrically.

    Findings without any bbox can only be matched by id (there is no geometry to
    compare), so two distinct bbox-less findings are kept separate.
    """
    if a.id and b.id and a.id == b.id:
        return True
    if not a.bboxes or not b.bboxes:
        return False
    return _boxes_overlap(a, b, iou_threshold)


def merge_findings(existing: Finding, incoming: Finding) -> Finding:
    """Merge ``incoming`` into ``existing`` without losing severity or context.

    Keeps the existing finding's identity, takes the *higher* severity, unions
    the bounding boxes (deduping exact repeats), and concatenates any notes.
    The incoming detail is appended as a note when it differs, so the original
    detail is never overwritten. Pure: returns a new ``Finding``.
    """
    boxes: list[RegionRect] = list(existing.bboxes)
    for box in incoming.bboxes:
        if box not in boxes:
            boxes.append(box)

    notes: list[str] = list(existing.notes)
    for note in incoming.notes:
        if note and note not in notes:
            notes.append(note)
    incoming_detail = incoming.detail.strip()
    if (
        incoming_detail
        and incoming_detail != existing.detail.strip()
        and incoming_detail not in notes
    ):
        notes.append(incoming_detail)

    regions = list(existing.regions)
    for region in incoming.regions:
        if region not in regions:
            regions.append(region)

    return dataclasses.replace(
        existing,
        regions=regions,
        severity=max_severity(existing.severity, incoming.severity),
        bboxes=boxes,
        notes=notes,
    )


def dedupe_findings(
    existing: list[Finding],
    new: list[Finding],
    *,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
) -> list[Finding]:
    """Fold ``new`` findings into ``existing``, merging geometric duplicates.

    Pure function: neither input list is mutated; a fresh list is returned.
    Each new finding either merges into the first existing finding it matches
    (same id or bbox IoU ≥ ``iou_threshold``) or is appended. Severity is taken
    as the maximum on merge, so a duplicate never downgrades a marker. Order of
    existing findings is preserved; genuinely new findings keep their order.
    """
    if not 0.0 <= iou_threshold <= 1.0:
        raise ValueError(f"iou_threshold must be in [0, 1], got {iou_threshold}")

    result: list[Finding] = list(existing)
    for incoming in new:
        for i, current in enumerate(result):
            if _same_finding(current, incoming, iou_threshold):
                result[i] = merge_findings(current, incoming)
                break
        else:
            result.append(incoming)
    return result


def apply_delta(
    findings: list[Finding],
    delta: FindingDelta,
    *,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
) -> list[Finding]:
    """Apply a single ``ADD`` / ``REVISE`` / ``RETRACT`` delta to ``findings``.

    Pure function: returns a new list. ``ADD`` deduplicates like
    :func:`dedupe_findings`. ``REVISE`` replaces the matching finding's mutable
    fields (and may downgrade severity — that is an explicit decision) and
    appends ``delta.note``. ``RETRACT`` removes the finding whose id matches.
    """
    payload = delta.finding
    note = delta.note.strip()

    if delta.op is FindingOp.RETRACT:
        return [f for f in findings if f.id != payload.id]

    if delta.op is FindingOp.ADD:
        merged = dedupe_findings(findings, [payload], iou_threshold=iou_threshold)
        if note:
            merged = _append_note_to_match(
                merged, payload, note, iou_threshold=iou_threshold
            )
        return merged

    # REVISE: explicit update of an existing finding (may change severity).
    result: list[Finding] = []
    replaced = False
    for current in findings:
        if not replaced and current.id and current.id == payload.id:
            notes = list(current.notes)
            for incoming_note in payload.notes:
                if incoming_note and incoming_note not in notes:
                    notes.append(incoming_note)
            if note and note not in notes:
                notes.append(note)
            result.append(
                dataclasses.replace(
                    current,
                    label=payload.label or current.label,
                    detail=payload.detail or current.detail,
                    severity=payload.severity,
                    bboxes=payload.bboxes or current.bboxes,
                    regions=payload.regions or current.regions,
                    notes=notes,
                )
            )
            replaced = True
        else:
            result.append(current)
    if not replaced:
        # Revising a finding that is not present behaves like an add.
        result = dedupe_findings(result, [payload], iou_threshold=iou_threshold)
        if note:
            result = _append_note_to_match(
                result, payload, note, iou_threshold=iou_threshold
            )
    return result


def _append_note_to_match(
    findings: list[Finding],
    payload: Finding,
    note: str,
    *,
    iou_threshold: float,
) -> list[Finding]:
    """Append ``note`` to whichever finding ``payload`` deduplicated into.

    After an ADD, ``payload`` may have merged into an existing finding (taking
    that finding's id) or been appended under its own id, so the note target is
    resolved by the same match rule rather than by a fixed id.
    """
    result: list[Finding] = []
    attached = False
    for current in findings:
        if (
            not attached
            and _same_finding(current, payload, iou_threshold)
            and note not in current.notes
        ):
            result.append(
                dataclasses.replace(current, notes=[*current.notes, note])
            )
            attached = True
        else:
            result.append(current)
    return result


class AnnotationAccumulator:
    """Stateful, deterministic store of the current overlay marker set.

    Wraps the pure dedup/delta functions with the minimal state the overlay
    needs: the accumulated findings plus explicit reset points. The agent's
    multi-pass turns and the physician's chat-guided corrections both feed in
    here, so the overlay is always handed one already-deduplicated list.

    Reset (``clear``) is called on an explicit boundary — a new patient, a new
    image, or a user "reset" — to stop markers from piling up indefinitely.
    """

    def __init__(self, *, iou_threshold: float = DEFAULT_IOU_THRESHOLD) -> None:
        if not 0.0 <= iou_threshold <= 1.0:
            raise ValueError(
                f"iou_threshold must be in [0, 1], got {iou_threshold}"
            )
        self._iou_threshold = iou_threshold
        self._findings: list[Finding] = []

    @property
    def findings(self) -> list[Finding]:
        """A copy of the current accumulated findings (safe to hand out)."""
        return list(self._findings)

    def add(self, new: list[Finding]) -> list[Finding]:
        """Merge a turn's findings in and return the new accumulated set."""
        self._findings = dedupe_findings(
            self._findings, new, iou_threshold=self._iou_threshold
        )
        return self.findings

    def apply(self, delta: FindingDelta) -> list[Finding]:
        """Apply one structured delta (chat-guided or agent) and return the set."""
        self._findings = apply_delta(
            self._findings, delta, iou_threshold=self._iou_threshold
        )
        return self.findings

    def clear(self) -> None:
        """Drop all accumulated findings (new patient / image / user reset)."""
        self._findings = []
