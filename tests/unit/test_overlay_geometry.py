from __future__ import annotations

import pytest

from dicom_overlay.domain.entities import RegionRect, WindowRect
from dicom_overlay.infrastructure.overlay_geometry import (
    LogicalRect,
    OverlayCoordinateFrame,
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
    assert projected.calibration.was_clamped is False
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


def test_project_bbox_does_not_report_float_precision_clamp() -> None:
    projected = project_bbox_to_overlay_highlight(
        bbox=RegionRect(x=0.08, y=0.18, w=0.35, h=0.15),
        image_rect=WindowRect(left=0, top=0, width=100, height=80),
        dpr=1.0,
        severity="warning",
        label="in bounds",
    )

    assert projected.calibration.was_clamped is False


def test_project_bbox_rejects_non_positive_dpr() -> None:
    with pytest.raises(ValueError, match="dpr must be > 0"):
        project_bbox_to_overlay_highlight(
            bbox=RegionRect(x=0.1, y=0.1, w=0.2, h=0.2),
            image_rect=WindowRect(left=0, top=0, width=100, height=100),
            dpr=0,
            severity="warning",
            label="bad",
        )


def test_secondary_display_frame_maps_absolute_physical_to_overlay_local() -> None:
    frame = OverlayCoordinateFrame(
        physical_screen=WindowRect(left=-1920, top=0, width=1920, height=1080),
        logical_screen=WindowRect(left=-1536, top=0, width=1536, height=864),
    )
    capture = WindowRect(left=-1800, top=100, width=1600, height=800)

    local = frame.physical_rect_to_local(capture)

    assert local == LogicalRect(x=96, y=80, w=1280, h=640)
    assert frame.physical_rect_to_global_logical(capture) == WindowRect(
        left=-1440,
        top=80,
        width=1280,
        height=640,
    )
    roundtrip = frame.local_rect_to_physical_edges(local)
    expected = (capture.left, capture.top, capture.right, capture.bottom)
    assert max(abs(a - b) for a, b in zip(roundtrip, expected, strict=True)) <= 1


def test_bbox_projection_uses_target_display_frame_and_local_origin() -> None:
    frame = OverlayCoordinateFrame(
        physical_screen=WindowRect(left=-1920, top=0, width=1920, height=1080),
        logical_screen=WindowRect(left=-1536, top=0, width=1536, height=864),
    )

    projected = project_bbox_to_overlay_highlight(
        bbox=RegionRect(x=0.1, y=0.2, w=0.3, h=0.4),
        image_rect=WindowRect(left=-1800, top=100, width=1600, height=800),
        coordinate_frame=frame,
        severity="warning",
        label="secondary display",
    )

    assert projected.highlight == (
        224,
        208,
        384,
        256,
        "warning",
        "secondary display",
    )
    assert projected.calibration.ok is True
