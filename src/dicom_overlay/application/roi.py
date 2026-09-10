"""ROI selection helpers for setup wizard."""

from __future__ import annotations

from dicom_overlay.domain.entities import ROICrop, WindowRect


def normalize_selection(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
) -> tuple[int, int, int, int]:
    """Normalize drag coordinates into (x, y, width, height)."""
    x = min(start_x, end_x)
    y = min(start_y, end_y)
    width = abs(end_x - start_x)
    height = abs(end_y - start_y)
    return (x, y, width, height)


def compute_roi_crop_from_safe_rect(
    base_rect: WindowRect,
    safe_rect: tuple[int, int, int, int],
) -> ROICrop:
    """Convert a safe rectangle into crop margins relative to a base rect."""
    x, y, width, height = safe_rect
    if width <= 0 or height <= 0:
        raise ValueError("Safe rectangle must have positive width and height")
    if x < 0 or y < 0:
        raise ValueError("Safe rectangle must stay within base rect")
    if x + width > base_rect.width or y + height > base_rect.height:
        raise ValueError("Safe rectangle exceeds base rect bounds")

    return ROICrop(
        top=y,
        bottom=base_rect.height - (y + height),
        left=x,
        right=base_rect.width - (x + width),
        configured=True,
        coordinate_space="viewer",
        reference_width=base_rect.width,
        reference_height=base_rect.height,
    )


def scaled_roi_crop(roi: ROICrop, width: int, height: int) -> ROICrop:
    """Scale a configured viewer-relative ROI to current viewer dimensions.

    Exclusion margins use ceiling division so a resize can only make the safe
    capture area smaller; it must never reveal pixels outside the reviewer-
    selected ROI.
    """

    if not roi.configured or roi.coordinate_space != "viewer":
        raise ValueError("ROI is not configured in viewer coordinates")
    if width <= 0 or height <= 0:
        raise ValueError("Viewer dimensions must be positive")
    if roi.reference_width <= 0 or roi.reference_height <= 0:
        raise ValueError("ROI reference dimensions are missing")
    if min(roi.top, roi.bottom, roi.left, roi.right) < 0:
        raise ValueError("ROI crop margins cannot be negative")

    scaled = ROICrop(
        top=_scale_exclusion_margin(roi.top, height, roi.reference_height),
        bottom=_scale_exclusion_margin(roi.bottom, height, roi.reference_height),
        left=_scale_exclusion_margin(roi.left, width, roi.reference_width),
        right=_scale_exclusion_margin(roi.right, width, roi.reference_width),
        configured=True,
        coordinate_space="viewer",
        reference_width=width,
        reference_height=height,
    )
    if scaled.left + scaled.right >= width or scaled.top + scaled.bottom >= height:
        raise ValueError("ROI crop margins exceed the viewer dimensions")
    return scaled


def _scale_exclusion_margin(value: int, extent: int, reference_extent: int) -> int:
    """Scale a privacy exclusion margin inward using exact ceiling division."""

    return (value * extent + reference_extent - 1) // reference_extent


def compute_viewer_roi_rect(target: WindowRect, roi: ROICrop) -> WindowRect:
    """Return an absolute capture rect that is always inside ``target``."""

    scaled = scaled_roi_crop(roi, target.width, target.height)
    return WindowRect(
        left=target.left + scaled.left,
        top=target.top + scaled.top,
        width=target.width - scaled.left - scaled.right,
        height=target.height - scaled.top - scaled.bottom,
    )
