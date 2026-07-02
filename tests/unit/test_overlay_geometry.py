from __future__ import annotations

import pytest

from dicom_overlay.domain.entities import RegionRect, WindowRect
from dicom_overlay.infrastructure.overlay_geometry import (
    project_bbox_to_overlay_highlight,
)


def test_project_bbox_uses_edge_rounding_and_reports_small_drift() -> None:
    image_rect = WindowRect(left=101, top=53, width=777, height=503)
    bbox = RegionRect(x=0.123, y=0.234, w=0.345, h=0.222)

    projected = project_bbox_to_overlay_highlight(
        bbox=bbox,
        image_rect=image_rect,
        dpr=1.25,
        severity="warning",
        label="ST depression",
    )

    assert projected.highlight[:4] == (
        projected.logical_rect.x,
        projected.logical_rect.y,
        projected.logical_rect.w,
        projected.logical_rect.h,
    )
    assert projected.highlight[4:] == ("warning", "ST depression")
    assert projected.calibration.max_edge_drift_px <= 1.25
    assert projected.calibration.ok is True
    assert projected.logical_rect.w > 0
    assert projected.logical_rect.h > 0


def test_project_bbox_clamps_overflow_before_screen_projection() -> None:
    image_rect = WindowRect(left=10, top=20, width=200, height=100)
    bbox = RegionRect(x=0.9, y=0.8, w=0.3, h=0.4)

    projected = project_bbox_to_overlay_highlight(
        bbox=bbox,
        image_rect=image_rect,
        dpr=1.0,
        severity="critical",
        label="overflow",
    )

    assert projected.calibration.was_clamped is True
    assert projected.calibration.clamped_bbox.x == pytest.approx(0.9)
    assert projected.calibration.clamped_bbox.y == pytest.approx(0.8)
    assert projected.calibration.clamped_bbox.w == pytest.approx(0.1)
    assert projected.calibration.clamped_bbox.h == pytest.approx(0.2)
    assert projected.logical_rect.x + projected.logical_rect.w <= image_rect.right
    assert projected.logical_rect.y + projected.logical_rect.h <= image_rect.bottom


def test_project_bbox_rejects_non_positive_dpr() -> None:
    with pytest.raises(ValueError, match="dpr must be > 0"):
        project_bbox_to_overlay_highlight(
            bbox=RegionRect(x=0.1, y=0.1, w=0.2, h=0.2),
            image_rect=WindowRect(left=0, top=0, width=100, height=100),
            dpr=0,
            severity="warning",
            label="bad",
        )
