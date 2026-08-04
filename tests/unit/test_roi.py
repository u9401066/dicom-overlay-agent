from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QPixmap

from dicom_overlay.application.roi import (
    compute_roi_crop_from_safe_rect,
    compute_viewer_roi_rect,
    normalize_selection,
    scaled_roi_crop,
)
from dicom_overlay.domain.entities import ROICrop, WindowRect
from dicom_overlay.presentation.roi_setup import ROISetupDialog


def test_normalize_selection_forward() -> None:
    assert normalize_selection(10, 20, 110, 220) == (10, 20, 100, 200)


def test_normalize_selection_reverse() -> None:
    assert normalize_selection(110, 220, 10, 20) == (10, 20, 100, 200)


def test_compute_roi_crop_from_safe_rect() -> None:
    base = WindowRect(left=0, top=0, width=1000, height=800)
    crop = compute_roi_crop_from_safe_rect(base, (50, 60, 900, 700))
    assert crop == ROICrop(
        top=60,
        bottom=40,
        left=50,
        right=50,
        configured=True,
        coordinate_space="viewer",
        reference_width=1000,
        reference_height=800,
    )


def test_compute_roi_crop_rejects_out_of_bounds() -> None:
    base = WindowRect(left=0, top=0, width=1000, height=800)
    with pytest.raises(ValueError):
        compute_roi_crop_from_safe_rect(base, (50, 60, 980, 700))


def test_compute_roi_crop_rejects_empty() -> None:
    base = WindowRect(left=0, top=0, width=1000, height=800)
    with pytest.raises(ValueError):
        compute_roi_crop_from_safe_rect(base, (50, 60, 0, 700))


def test_viewer_roi_scales_and_never_leaves_current_viewer() -> None:
    roi = ROICrop(
        top=50,
        bottom=25,
        left=100,
        right=50,
        configured=True,
        reference_width=1000,
        reference_height=500,
    )
    viewer = WindowRect(left=-1800, top=200, width=1500, height=1000)

    scaled = scaled_roi_crop(roi, viewer.width, viewer.height)
    rect = compute_viewer_roi_rect(viewer, roi)

    assert scaled == ROICrop(
        top=100,
        bottom=50,
        left=150,
        right=75,
        configured=True,
        coordinate_space="viewer",
        reference_width=1500,
        reference_height=1000,
    )
    assert rect == WindowRect(left=-1650, top=300, width=1275, height=850)
    assert viewer.left <= rect.left < rect.right <= viewer.right
    assert viewer.top <= rect.top < rect.bottom <= viewer.bottom


def test_viewer_roi_rejects_unconfigured_or_legacy_screen_values() -> None:
    viewer = WindowRect(left=0, top=0, width=1200, height=800)
    with pytest.raises(ValueError, match="not configured"):
        compute_viewer_roi_rect(viewer, ROICrop(top=60, bottom=30))


def test_roi_dialog_rejects_selection_outside_detected_viewer(qtbot) -> None:
    dialog = ROISetupDialog(
        base_rect=WindowRect(left=0, top=0, width=1000, height=800),
        screenshot=QPixmap(1000, 800),
        target_rect=WindowRect(left=100, top=50, width=800, height=600),
    )
    qtbot.addWidget(dialog)
    dialog._selection_start = QPoint(50, 100)
    dialog._selection_end = QPoint(500, 500)

    dialog._confirm_selection()

    assert dialog.selected_crop is None
    assert "viewer" in dialog._status.text()


def test_roi_dialog_saves_margins_relative_to_detected_viewer(qtbot) -> None:
    dialog = ROISetupDialog(
        base_rect=WindowRect(left=0, top=0, width=1000, height=800),
        screenshot=QPixmap(1000, 800),
        target_rect=WindowRect(left=100, top=50, width=800, height=600),
    )
    qtbot.addWidget(dialog)
    dialog._selection_start = QPoint(150, 100)
    dialog._selection_end = QPoint(850, 600)

    dialog._confirm_selection()

    assert dialog.selected_crop == ROICrop(
        top=50,
        bottom=50,
        left=50,
        right=50,
        configured=True,
        coordinate_space="viewer",
        reference_width=800,
        reference_height=600,
    )


# ─── DPI conversion tests ───


class TestDpiConversion:
    def test_physical_to_logical_no_scaling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dicom_overlay.infrastructure import dpi

        monkeypatch.setattr(dpi, "_cached_dpr", 1.0)
        rect = WindowRect(left=100, top=200, width=1920, height=1080)
        result = dpi.physical_to_logical(rect)
        assert result == rect  # identity when dpr=1.0

    def test_physical_to_logical_125_scaling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dicom_overlay.infrastructure import dpi

        monkeypatch.setattr(dpi, "_cached_dpr", 1.25)
        rect = WindowRect(left=0, top=0, width=2560, height=1440)
        result = dpi.physical_to_logical(rect)
        assert result == WindowRect(left=0, top=0, width=2048, height=1152)

    def test_physical_to_logical_150_scaling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dicom_overlay.infrastructure import dpi

        monkeypatch.setattr(dpi, "_cached_dpr", 1.5)
        rect = WindowRect(left=150, top=300, width=1920, height=1080)
        result = dpi.physical_to_logical(rect)
        assert result == WindowRect(left=100, top=200, width=1280, height=720)

    def test_logical_to_physical_roi_roundtrip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dicom_overlay.infrastructure import dpi

        monkeypatch.setattr(dpi, "_cached_dpr", 1.25)
        original = (431, 279, 1279, 0)
        logical = dpi.physical_to_logical_roi(*original)
        back = dpi.logical_to_physical_roi(*logical)
        # Round-trip should be close (rounding may differ by ±1)
        for orig, rt in zip(original, back, strict=True):
            assert abs(orig - rt) <= 1

    def test_no_scaling_returns_same_roi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dicom_overlay.infrastructure import dpi

        monkeypatch.setattr(dpi, "_cached_dpr", 1.0)
        roi = (60, 30, 0, 0)
        assert dpi.physical_to_logical_roi(*roi) == roi
        assert dpi.logical_to_physical_roi(*roi) == roi
