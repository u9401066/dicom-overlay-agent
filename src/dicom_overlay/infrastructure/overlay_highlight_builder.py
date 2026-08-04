"""Build drift-audited overlay highlights from AI bboxes.

This module is intentionally GUI-free: it turns normalized AI bboxes into
overlay highlight tuples and keeps a PHI-free audit row for every attempted box.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dicom_overlay.domain.entities import Finding, RegionRect, Severity, WindowRect
from dicom_overlay.infrastructure.overlay_geometry import (
    BboxProjectionCalibration,
    OverlayCoordinateFrame,
    project_bbox_to_overlay_highlight,
)

HighlightTuple = tuple[int, int, int, int, str, str]


@dataclass(frozen=True)
class BboxHighlightAuditRow:
    """PHI-free evidence for one AI bbox projection decision."""

    finding_id: str
    label: str
    severity: str
    bbox_index: int
    drawn: bool
    calibration: BboxProjectionCalibration

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "label": self.label,
            "severity": self.severity,
            "bbox_index": self.bbox_index,
            "drawn": self.drawn,
            "original_bbox": _bbox_to_dict(self.calibration.original_bbox),
            "clamped_bbox": _bbox_to_dict(self.calibration.clamped_bbox),
            "back_projected_bbox": _bbox_to_dict(
                self.calibration.back_projected_bbox
            ),
            "max_edge_drift_px": self.calibration.max_edge_drift_px,
            "was_clamped": self.calibration.was_clamped,
            "ok": self.calibration.ok,
        }


@dataclass(frozen=True)
class BboxHighlightBuildResult:
    """Built overlay highlights plus one audit row per attempted AI bbox."""

    highlights: list[HighlightTuple]
    audit_rows: list[BboxHighlightAuditRow]


def build_ai_bbox_highlights(
    *,
    findings: list[Finding],
    image_rect: WindowRect,
    dpr: float | None = None,
    coordinate_frame: OverlayCoordinateFrame | None = None,
    max_roundtrip_drift_px: float | None = None,
) -> BboxHighlightBuildResult:
    highlights: list[HighlightTuple] = []
    audit_rows: list[BboxHighlightAuditRow] = []
    for finding in findings:
        if finding.severity is Severity.NORMAL:
            continue
        for bbox_index, bbox in enumerate(finding.bboxes):
            projected = project_bbox_to_overlay_highlight(
                bbox=bbox,
                image_rect=image_rect,
                dpr=dpr,
                coordinate_frame=coordinate_frame,
                severity=finding.severity.value,
                label=finding.label,
                max_roundtrip_drift_px=max_roundtrip_drift_px,
            )
            drawn = projected.calibration.ok
            audit_rows.append(
                BboxHighlightAuditRow(
                    finding_id=finding.id,
                    label=finding.label,
                    severity=finding.severity.value,
                    bbox_index=bbox_index,
                    drawn=drawn,
                    calibration=projected.calibration,
                )
            )
            if drawn:
                highlights.append(projected.highlight)
    return BboxHighlightBuildResult(highlights=highlights, audit_rows=audit_rows)


def _bbox_to_dict(bbox: RegionRect) -> dict[str, float]:
    return {"x": bbox.x, "y": bbox.y, "w": bbox.w, "h": bbox.h}
