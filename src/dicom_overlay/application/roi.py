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
    """Scale a configured viewer-relative ROI to current viewer dimensions."""

    if not roi.configured or roi.coordinate_space != "viewer":
        raise ValueError("ROI is not configured in viewer coordinates")
    if width <= 0 or height <= 0:
        raise ValueError("Viewer dimensions must be positive")
    if roi.reference_width <= 0 or roi.reference_height <= 0:
        raise ValueError("ROI reference dimensions are missing")
    if min(roi.top, roi.bottom, roi.left, roi.right) < 0:
        raise ValueError("ROI crop margins cannot be negative")

    scale_x = width / roi.reference_width
    scale_y = height / roi.reference_height
    scaled = ROICrop(
        top=round(roi.top * scale_y),
        bottom=round(roi.bottom * scale_y),
        left=round(roi.left * scale_x),
        right=round(roi.right * scale_x),
        configured=True,
        coordinate_space="viewer",
        reference_width=width,
        reference_height=height,
    )
    if scaled.left + scaled.right >= width or scaled.top + scaled.bottom >= height:
        raise ValueError("ROI crop margins exceed the viewer dimensions")
    return scaled


def compute_viewer_roi_rect(target: WindowRect, roi: ROICrop) -> WindowRect:
    """Return an absolute capture rect that is always inside ``target``."""

    scaled = scaled_roi_crop(roi, target.width, target.height)
    return WindowRect(
        left=target.left + scaled.left,
        top=target.top + scaled.top,
        width=target.width - scaled.left - scaled.right,
        height=target.height - scaled.top - scaled.bottom,
    )
