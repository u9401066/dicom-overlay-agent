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
    )
