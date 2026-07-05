"""Overlay coordinate projection and drift auditing.

AI bboxes are normalized to the captured ROI image. The overlay draws in Qt
logical pixels, while the capture path often works in physical pixels. This
module keeps that conversion testable and records the round-trip drift so bbox
placement can be audited before it reaches the physician-facing overlay.
"""

from __future__ import annotations

from dataclasses import dataclass

from dicom_overlay.domain.entities import RegionRect, WindowRect


@dataclass(frozen=True)
class LogicalRect:
    """Qt logical-pixel rectangle used by the overlay window."""

    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class BboxProjectionCalibration:
    """Round-trip evidence for bbox projection back to normalized ROI space."""

    original_bbox: RegionRect
    clamped_bbox: RegionRect
    back_projected_bbox: RegionRect
    max_edge_drift_px: float
    was_clamped: bool
    ok: bool


@dataclass(frozen=True)
class ProjectedHighlight:
    """Overlay highlight tuple plus coordinate calibration evidence."""

    logical_rect: LogicalRect
    calibration: BboxProjectionCalibration
    highlight: tuple[int, int, int, int, str, str]


def project_bbox_to_overlay_highlight(
    *,
    bbox: RegionRect,
    image_rect: WindowRect,
    dpr: float,
    severity: str,
    label: str,
    max_roundtrip_drift_px: float | None = None,
) -> ProjectedHighlight:
    """Project one normalized bbox into overlay logical pixels.

    The conversion rounds physical *edges* instead of rounding width/height
    independently. That keeps the drawn rectangle's right/bottom edge aligned
    with the source bbox more reliably across non-integer DPR values.
    """

    if dpr <= 0:
        raise ValueError("dpr must be > 0")
    drift_limit = max_roundtrip_drift_px if max_roundtrip_drift_px is not None else dpr
    clamped = _clamp_bbox_extent(bbox)
    physical = _bbox_to_physical_edges(clamped, image_rect)
    logical = _physical_edges_to_logical_rect(physical, dpr)
    back_projected, back_physical = _logical_rect_to_bbox(logical, image_rect, dpr)
    drift = max(abs(a - b) for a, b in zip(physical, back_physical, strict=True))
    calibration = BboxProjectionCalibration(
        original_bbox=bbox,
        clamped_bbox=clamped,
        back_projected_bbox=back_projected,
        max_edge_drift_px=drift,
        was_clamped=_bbox_changed(bbox, clamped),
        ok=drift <= drift_limit + 1e-9,
    )
    return ProjectedHighlight(
        logical_rect=logical,
        calibration=calibration,
        highlight=(logical.x, logical.y, logical.w, logical.h, severity, label),
    )


def _clamp_bbox_extent(bbox: RegionRect) -> RegionRect:
    x0 = _clamp_unit(bbox.x)
    y0 = _clamp_unit(bbox.y)
    x1 = _clamp_unit(bbox.x + bbox.w)
    y1 = _clamp_unit(bbox.y + bbox.h)
    return RegionRect(x=x0, y=y0, w=max(0.0, x1 - x0), h=max(0.0, y1 - y0))


def _bbox_to_physical_edges(
    bbox: RegionRect, image_rect: WindowRect
) -> tuple[float, float, float, float]:
    return (
        image_rect.left + bbox.x * image_rect.width,
        image_rect.top + bbox.y * image_rect.height,
        image_rect.left + (bbox.x + bbox.w) * image_rect.width,
        image_rect.top + (bbox.y + bbox.h) * image_rect.height,
    )


def _physical_edges_to_logical_rect(
    edges: tuple[float, float, float, float], dpr: float
) -> LogicalRect:
    x0, y0, x1, y1 = edges
    lx0 = round(x0 / dpr)
    ly0 = round(y0 / dpr)
    lx1 = round(x1 / dpr)
    ly1 = round(y1 / dpr)
    return LogicalRect(
        x=lx0,
        y=ly0,
        w=max(1, lx1 - lx0),
        h=max(1, ly1 - ly0),
    )


def _logical_rect_to_bbox(
    rect: LogicalRect,
    image_rect: WindowRect,
    dpr: float,
) -> tuple[RegionRect, tuple[float, float, float, float]]:
    x0 = rect.x * dpr
    y0 = rect.y * dpr
    x1 = (rect.x + rect.w) * dpr
    y1 = (rect.y + rect.h) * dpr
    bbox = RegionRect(
        x=_clamp_unit((x0 - image_rect.left) / image_rect.width),
        y=_clamp_unit((y0 - image_rect.top) / image_rect.height),
        w=_clamp_unit((x1 - x0) / image_rect.width),
        h=_clamp_unit((y1 - y0) / image_rect.height),
    )
    return bbox, (x0, y0, x1, y1)


def _clamp_unit(value: float) -> float:
    return min(1.0, max(0.0, value))


def _bbox_changed(original: RegionRect, clamped: RegionRect) -> bool:
    return any(
        abs(a - b) > 1e-9
        for a, b in (
            (original.x, clamped.x),
            (original.y, clamped.y),
            (original.w, clamped.w),
            (original.h, clamped.h),
        )
    )
