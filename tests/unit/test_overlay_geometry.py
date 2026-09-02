from __future__ import annotations

import pytest

from dicom_overlay.domain.entities import RegionRect, ROICrop, WindowRect
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


@pytest.mark.parametrize(
    "bbox, message",
    [
        (RegionRect(x=0.1, y=0.1, w=0.0, h=0.2), "width and height"),
        (RegionRect(x=0.1, y=0.1, w=0.2, h=0.0), "width and height"),
        (RegionRect(x=1.0, y=0.2, w=0.1, h=0.2), "overlap"),
    ],
)
def test_project_bbox_rejects_degenerate_or_off_image_boxes(
    bbox: RegionRect,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        project_bbox_to_overlay_highlight(
            bbox=bbox,
            image_rect=WindowRect(left=0, top=0, width=1000, height=800),
            dpr=1.5,
            severity="warning",
            label="invalid geometry",
        )


def test_real_150_percent_desktop_projection_stays_subpixel_aligned() -> None:
    """Freeze the 2560x1600 / 150%-DPI geometry from the live Luna run."""

    frame = OverlayCoordinateFrame(
        physical_screen=WindowRect(left=0, top=0, width=2560, height=1600),
        logical_screen=WindowRect(left=0, top=0, width=1707, height=1067),
    )
    capture = WindowRect(left=19, top=30, width=1522, height=1136)
    boxes = [
        RegionRect(x=0.05, y=0.51125, w=0.18, h=0.06325),
        RegionRect(x=0.18, y=0.59175, w=0.18, h=0.06325),
        RegionRect(x=0.05, y=0.839, w=0.18, h=0.06325),
        RegionRect(x=0.18, y=0.922375, w=0.18, h=0.06325),
    ]

    assert frame.physical_rect_to_local(capture) == LogicalRect(
        x=13,
        y=20,
        w=1015,
        h=758,
    )
    for bbox in boxes:
        projected = project_bbox_to_overlay_highlight(
            bbox=bbox,
            image_rect=capture,
            coordinate_frame=frame,
            severity="info",
            label="live Luna bbox",
        )

        assert projected.calibration.ok is True
        assert projected.calibration.within_overlay_bounds is True
        assert projected.calibration.was_clamped is False
        assert projected.calibration.max_edge_drift_px < 0.8
        assert projected.calibration.back_projected_bbox.x == pytest.approx(
            bbox.x,
            abs=0.001,
        )
        assert projected.calibration.back_projected_bbox.y == pytest.approx(
            bbox.y,
            abs=0.001,
        )


def test_fractional_dpi_roi_roundtrip_is_bounded_to_one_physical_pixel() -> None:
    frame = OverlayCoordinateFrame(
        physical_screen=WindowRect(left=0, top=0, width=2560, height=1600),
        logical_screen=WindowRect(left=0, top=0, width=1707, height=1067),
    )
    physical = ROICrop(
        top=37,
        bottom=83,
        left=101,
        right=47,
        configured=True,
        coordinate_space="viewer",
        reference_width=1522,
        reference_height=1136,
    )

    roundtrip = frame.logical_roi_to_physical(
        frame.physical_roi_to_logical(physical)
    )

    for field in (
        "top",
        "bottom",
        "left",
        "right",
        "reference_width",
        "reference_height",
    ):
        assert abs(getattr(roundtrip, field) - getattr(physical, field)) <= 1


def test_live_150_percent_roi_conversion_never_expands_selected_safe_area() -> None:
    """Freeze the ROI edges selected in the live 150%-DPI desktop run."""

    frame = OverlayCoordinateFrame(
        physical_screen=WindowRect(left=0, top=0, width=2560, height=1600),
        logical_screen=WindowRect(left=0, top=0, width=1707, height=1067),
    )
    logical = ROICrop(
        top=30,
        bottom=8,
        left=7,
        right=8,
        configured=True,
        coordinate_space="viewer",
        reference_width=1015,
        reference_height=758,
    )

    physical = frame.logical_roi_to_physical(logical)

    assert physical == ROICrop(
        top=45,
        bottom=12,
        left=11,
        right=12,
        configured=True,
        coordinate_space="viewer",
        reference_width=1522,
        reference_height=1137,
    )
    # Every excluded physical margin is at least the exact scaled logical
    # margin. Thus no captured edge can cross outside the selected safe area.
    assert physical.left * 1707 >= logical.left * 2560
    assert physical.right * 1707 >= logical.right * 2560
    assert physical.top * 1067 >= logical.top * 1600
    assert physical.bottom * 1067 >= logical.bottom * 1600

    viewer = WindowRect(left=19, top=30, width=1522, height=1137)
    capture = WindowRect(
        left=viewer.left + physical.left,
        top=viewer.top + physical.top,
        width=viewer.width - physical.left - physical.right,
        height=viewer.height - physical.top - physical.bottom,
    )
    assert capture == WindowRect(left=30, top=75, width=1499, height=1080)
    assert capture.left >= 30
    assert capture.top >= 75
    assert capture.right <= 1530
    assert capture.bottom <= 1155


@pytest.mark.parametrize(
    ("physical_size", "expected_reference_size"),
    [
        ((2559, 1599), (1522, 1136)),
        ((2560, 1600), (1522, 1137)),
        ((2561, 1601), (1523, 1137)),
    ],
)
def test_fractional_dpi_roi_stays_fail_closed_when_display_size_varies(
    physical_size: tuple[int, int],
    expected_reference_size: tuple[int, int],
) -> None:
    """A one-pixel display geometry change must not round any margin outward."""

    physical_width, physical_height = physical_size
    frame = OverlayCoordinateFrame(
        physical_screen=WindowRect(
            left=0,
            top=0,
            width=physical_width,
            height=physical_height,
        ),
        logical_screen=WindowRect(left=0, top=0, width=1707, height=1067),
    )
    logical = ROICrop(
        top=30,
        bottom=8,
        left=7,
        right=8,
        configured=True,
        coordinate_space="viewer",
        reference_width=1015,
        reference_height=758,
    )

    physical = frame.logical_roi_to_physical(logical)

    assert (physical.reference_width, physical.reference_height) == (
        expected_reference_size
    )
    assert physical.left * 1707 >= logical.left * physical_width
    assert physical.right * 1707 >= logical.right * physical_width
    assert physical.top * 1067 >= logical.top * physical_height
    assert physical.bottom * 1067 >= logical.bottom * physical_height
    assert frame.physical_roi_to_logical(physical) == logical


def test_fractional_dpi_roi_repeated_roundtrips_are_stable_and_fail_closed() -> None:
    frame = OverlayCoordinateFrame(
        physical_screen=WindowRect(left=0, top=0, width=2560, height=1600),
        logical_screen=WindowRect(left=0, top=0, width=1707, height=1067),
    )
    original = ROICrop(
        top=37,
        bottom=83,
        left=10,
        right=47,
        configured=True,
        coordinate_space="viewer",
        reference_width=1522,
        reference_height=1137,
    )

    logical = frame.physical_roi_to_logical(original)
    stabilized = frame.logical_roi_to_physical(logical)

    for field in ("top", "bottom", "left", "right"):
        assert getattr(stabilized, field) >= getattr(original, field)
        assert getattr(stabilized, field) - getattr(original, field) <= 1
    for _ in range(10):
        logical = frame.physical_roi_to_logical(stabilized)
        assert frame.logical_roi_to_physical(logical) == stabilized


def test_roi_coordinate_conversion_rejects_negative_privacy_margins() -> None:
    frame = OverlayCoordinateFrame(
        physical_screen=WindowRect(left=0, top=0, width=2560, height=1600),
        logical_screen=WindowRect(left=0, top=0, width=1707, height=1067),
    )
    invalid = ROICrop(
        left=-1,
        configured=True,
        coordinate_space="viewer",
        reference_width=1015,
        reference_height=758,
    )

    with pytest.raises(ValueError, match="cannot be negative"):
        frame.logical_roi_to_physical(invalid)


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


def test_roi_coordinate_conversion_preserves_viewer_binding() -> None:
    frame = OverlayCoordinateFrame(
        physical_screen=WindowRect(left=0, top=0, width=2000, height=1000),
        logical_screen=WindowRect(left=0, top=0, width=1000, height=500),
    )
    physical = ROICrop(
        top=100,
        bottom=40,
        left=60,
        right=20,
        configured=True,
        coordinate_space="viewer",
        reference_width=1600,
        reference_height=800,
    )

    logical = frame.physical_roi_to_logical(physical)

    assert logical == ROICrop(
        top=50,
        bottom=20,
        left=30,
        right=10,
        configured=True,
        coordinate_space="viewer",
        reference_width=800,
        reference_height=400,
    )
    assert frame.logical_roi_to_physical(logical) == physical
