"""Overlay coordinate projection and drift auditing.

AI bboxes are normalized to the captured ROI image. The overlay draws in Qt
logical pixels, while the capture path often works in physical pixels. This
module keeps that conversion testable and records the round-trip drift so bbox
placement can be audited before it reaches the physician-facing overlay.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from dicom_overlay.domain.entities import RegionRect, ROICrop, WindowRect


@dataclass(frozen=True)
class LogicalRect:
    """Qt logical-pixel rectangle used by the overlay window."""

    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class OverlayCoordinateFrame:
    """Exact physical-display to overlay-local logical-pixel mapping."""

    physical_screen: WindowRect
    logical_screen: WindowRect

    def __post_init__(self) -> None:
        dimensions = (
            self.physical_screen.width,
            self.physical_screen.height,
            self.logical_screen.width,
            self.logical_screen.height,
        )
        if any(value <= 0 for value in dimensions):
            raise ValueError("screen dimensions must be positive")

    @property
    def logical_per_physical_x(self) -> float:
        return self.logical_screen.width / self.physical_screen.width

    @property
    def logical_per_physical_y(self) -> float:
        return self.logical_screen.height / self.physical_screen.height

    @property
    def max_physical_px_per_logical_px(self) -> float:
        return max(
            self.physical_screen.width / self.logical_screen.width,
            self.physical_screen.height / self.logical_screen.height,
        )

    def physical_edges_to_local_rect(
        self, edges: tuple[float, float, float, float]
    ) -> LogicalRect:
        """Map absolute physical edges to overlay-local Qt coordinates."""
        x0, y0, x1, y1 = edges
        lx0 = round(
            (x0 - self.physical_screen.left) * self.logical_per_physical_x
        )
        ly0 = round(
            (y0 - self.physical_screen.top) * self.logical_per_physical_y
        )
        lx1 = round(
            (x1 - self.physical_screen.left) * self.logical_per_physical_x
        )
        ly1 = round(
            (y1 - self.physical_screen.top) * self.logical_per_physical_y
        )
        return LogicalRect(
            x=lx0,
            y=ly0,
            w=max(1, lx1 - lx0),
            h=max(1, ly1 - ly0),
        )

    def physical_rect_to_local(self, rect: WindowRect) -> LogicalRect:
        return self.physical_edges_to_local_rect(
            (rect.left, rect.top, rect.right, rect.bottom)
        )

    def contains_physical_rect(self, rect: WindowRect) -> bool:
        """Return whether ``rect`` is fully representable on this one display."""

        return (
            rect.width > 0
            and rect.height > 0
            and rect.left >= self.physical_screen.left
            and rect.top >= self.physical_screen.top
            and rect.right <= self.physical_screen.right
            and rect.bottom <= self.physical_screen.bottom
        )

    def physical_rect_to_global_logical(self, rect: WindowRect) -> WindowRect:
        local = self.physical_rect_to_local(rect)
        return WindowRect(
            left=self.logical_screen.left + local.x,
            top=self.logical_screen.top + local.y,
            width=local.w,
            height=local.h,
        )

    def local_rect_to_physical_edges(
        self, rect: LogicalRect
    ) -> tuple[float, float, float, float]:
        physical_per_logical_x = 1.0 / self.logical_per_physical_x
        physical_per_logical_y = 1.0 / self.logical_per_physical_y
        return (
            self.physical_screen.left + rect.x * physical_per_logical_x,
            self.physical_screen.top + rect.y * physical_per_logical_y,
            self.physical_screen.left
            + (rect.x + rect.w) * physical_per_logical_x,
            self.physical_screen.top
            + (rect.y + rect.h) * physical_per_logical_y,
        )

    def physical_roi_to_logical(self, roi: ROICrop) -> ROICrop:
        """Map physical crop margins to their stable logical representation.

        Crop margins describe pixels that must stay *outside* the captured
        image.  The inverse therefore chooses the smallest logical margin whose
        fail-closed conversion back to physical pixels is at least the original
        margin.  This prevents an unchanged ROI from drifting on every
        settings round-trip while never shrinking its PHI exclusion boundary.
        """

        return ROICrop(
            top=_inverse_ceil_scaled_margin(
                roi.top,
                source_extent=self.logical_screen.height,
                target_extent=self.physical_screen.height,
            ),
            bottom=_inverse_ceil_scaled_margin(
                roi.bottom,
                source_extent=self.logical_screen.height,
                target_extent=self.physical_screen.height,
            ),
            left=_inverse_ceil_scaled_margin(
                roi.left,
                source_extent=self.logical_screen.width,
                target_extent=self.physical_screen.width,
            ),
            right=_inverse_ceil_scaled_margin(
                roi.right,
                source_extent=self.logical_screen.width,
                target_extent=self.physical_screen.width,
            ),
            configured=roi.configured,
            coordinate_space=roi.coordinate_space,
            reference_width=_scale_extent_nearest(
                roi.reference_width,
                numerator=self.logical_screen.width,
                denominator=self.physical_screen.width,
            ),
            reference_height=_scale_extent_nearest(
                roi.reference_height,
                numerator=self.logical_screen.height,
                denominator=self.physical_screen.height,
            ),
        )

    def logical_roi_to_physical(self, roi: ROICrop) -> ROICrop:
        """Map logical crop margins inward to PHI-safe physical boundaries.

        Each margin is rounded up independently.  Consequently the returned
        capture rectangle can be one physical pixel smaller than the selected
        logical rectangle, but can never include a pixel outside it.
        """

        return ROICrop(
            top=_ceil_scaled_margin(
                roi.top,
                numerator=self.physical_screen.height,
                denominator=self.logical_screen.height,
            ),
            bottom=_ceil_scaled_margin(
                roi.bottom,
                numerator=self.physical_screen.height,
                denominator=self.logical_screen.height,
            ),
            left=_ceil_scaled_margin(
                roi.left,
                numerator=self.physical_screen.width,
                denominator=self.logical_screen.width,
            ),
            right=_ceil_scaled_margin(
                roi.right,
                numerator=self.physical_screen.width,
                denominator=self.logical_screen.width,
            ),
            configured=roi.configured,
            coordinate_space=roi.coordinate_space,
            reference_width=_scale_extent_nearest(
                roi.reference_width,
                numerator=self.physical_screen.width,
                denominator=self.logical_screen.width,
            ),
            reference_height=_scale_extent_nearest(
                roi.reference_height,
                numerator=self.physical_screen.height,
                denominator=self.logical_screen.height,
            ),
        )


def _ceil_scaled_margin(value: int, *, numerator: int, denominator: int) -> int:
    """Scale one exclusion margin with exact, fail-closed ceiling division."""

    if value < 0:
        raise ValueError("ROI crop margins cannot be negative")
    return (value * numerator + denominator - 1) // denominator


def _inverse_ceil_scaled_margin(
    value: int,
    *,
    source_extent: int,
    target_extent: int,
) -> int:
    """Return the smallest source margin whose ceiling maps to ``value`` or more."""

    if value < 0:
        raise ValueError("ROI crop margins cannot be negative")
    if value == 0:
        return 0
    return ((value - 1) * source_extent) // target_extent + 1


def _scale_extent_nearest(
    value: int,
    *,
    numerator: int,
    denominator: int,
) -> int:
    """Scale a reference extent to the nearest integer without float error."""

    if value < 0:
        raise ValueError("ROI reference dimensions cannot be negative")
    quotient, remainder = divmod(value * numerator, denominator)
    return quotient + int(remainder * 2 >= denominator)


@dataclass(frozen=True)
class BboxProjectionCalibration:
    """Round-trip evidence for bbox projection back to normalized ROI space."""

    original_bbox: RegionRect
    clamped_bbox: RegionRect
    back_projected_bbox: RegionRect
    max_edge_drift_px: float
    was_clamped: bool
    within_overlay_bounds: bool
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
    dpr: float | None = None,
    coordinate_frame: OverlayCoordinateFrame | None = None,
    severity: str,
    label: str,
    max_roundtrip_drift_px: float | None = None,
) -> ProjectedHighlight:
    """Project one normalized bbox into overlay logical pixels.

    The conversion rounds physical *edges* instead of rounding width/height
    independently. That keeps the drawn rectangle's right/bottom edge aligned
    with the source bbox more reliably across non-integer DPR values.
    """

    if image_rect.width <= 0 or image_rect.height <= 0:
        raise ValueError("image_rect dimensions must be positive")
    if coordinate_frame is None and (dpr is None or dpr <= 0):
        raise ValueError("dpr must be > 0 when coordinate_frame is not provided")
    coordinates = (bbox.x, bbox.y, bbox.w, bbox.h)
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("bbox coordinates must be finite")
    if bbox.w <= 0.0 or bbox.h <= 0.0:
        raise ValueError("bbox width and height must be positive")
    clamped = _clamp_bbox_extent(bbox)
    if clamped.w <= 0.0 or clamped.h <= 0.0:
        raise ValueError("bbox must overlap the captured image")
    physical = _bbox_to_physical_edges(clamped, image_rect)
    if coordinate_frame is not None:
        logical = coordinate_frame.physical_edges_to_local_rect(physical)
        back_physical = coordinate_frame.local_rect_to_physical_edges(logical)
        default_drift_limit = coordinate_frame.max_physical_px_per_logical_px
        within_overlay_bounds = (
            coordinate_frame.contains_physical_rect(image_rect)
            and logical.x >= 0
            and logical.y >= 0
            and logical.x + logical.w <= coordinate_frame.logical_screen.width
            and logical.y + logical.h <= coordinate_frame.logical_screen.height
        )
    else:
        assert dpr is not None
        logical = _physical_edges_to_logical_rect(physical, dpr)
        back_physical = _logical_rect_to_physical_edges(logical, dpr)
        default_drift_limit = dpr
        within_overlay_bounds = True
    drift_limit = (
        max_roundtrip_drift_px
        if max_roundtrip_drift_px is not None
        else default_drift_limit
    )
    back_projected = _physical_edges_to_bbox(back_physical, image_rect)
    drift = max(abs(a - b) for a, b in zip(physical, back_physical, strict=True))
    calibration = BboxProjectionCalibration(
        original_bbox=bbox,
        clamped_bbox=clamped,
        back_projected_bbox=back_projected,
        max_edge_drift_px=drift,
        was_clamped=_bbox_changed(bbox, clamped),
        within_overlay_bounds=within_overlay_bounds,
        ok=within_overlay_bounds and drift <= drift_limit + 1e-9,
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


def _logical_rect_to_physical_edges(
    rect: LogicalRect, dpr: float
) -> tuple[float, float, float, float]:
    x0 = rect.x * dpr
    y0 = rect.y * dpr
    x1 = (rect.x + rect.w) * dpr
    y1 = (rect.y + rect.h) * dpr
    return (x0, y0, x1, y1)


def _physical_edges_to_bbox(
    edges: tuple[float, float, float, float], image_rect: WindowRect
) -> RegionRect:
    x0, y0, x1, y1 = edges
    return RegionRect(
        x=_clamp_unit((x0 - image_rect.left) / image_rect.width),
        y=_clamp_unit((y0 - image_rect.top) / image_rect.height),
        w=_clamp_unit((x1 - x0) / image_rect.width),
        h=_clamp_unit((y1 - y0) / image_rect.height),
    )


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
