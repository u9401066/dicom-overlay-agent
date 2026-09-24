"""Pixel regressions for the safe-region preview, independent of inference."""

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap

from dicom_overlay.domain.entities import ROICrop, WindowRect
from dicom_overlay.presentation.roi_setup import ROISetupDialog


def _pattern(dpr: float) -> QPixmap:
    image = QPixmap(round(640 * dpr), round(480 * dpr))
    image.setDevicePixelRatio(dpr)
    image.fill(QColor(240, 180, 100))
    painter = QPainter(image)
    painter.fillRect(250, 0, 390, 480, QColor(90, 150, 220))
    painter.end()
    return image


def _pixel(dialog: ROISetupDialog, x: int, y: int) -> QColor:
    rendered = dialog.grab()
    scale = rendered.devicePixelRatio()
    return rendered.toImage().pixelColor(round(x * scale), round(y * scale))


@pytest.mark.parametrize("dpr", [1.0, 1.25, 1.5, 2.0])
@pytest.mark.parametrize("origin", [(0, 0), (-640, -80)])
@pytest.mark.parametrize("selection", ["forward", "reverse", "existing"])
def test_roi_preview_retains_source_pixels_and_dims_only_excluded_area(
    qtbot, dpr, origin, selection
):
    existing = (
        ROICrop(
            top=180,
            bottom=120,
            left=130,
            right=130,
            configured=True,
            reference_width=640,
            reference_height=480,
        )
        if selection == "existing"
        else None
    )
    screenshot = _pattern(dpr)
    original = screenshot.toImage()
    dialog = ROISetupDialog(
        base_rect=WindowRect(*origin, 640, 480),
        screenshot=screenshot,
        existing_roi=existing,
    )
    qtbot.addWidget(dialog)
    if selection != "existing":
        points = [QPoint(130, 180), QPoint(510, 360)]
        if selection == "reverse":
            points.reverse()
        dialog._selection_start, dialog._selection_end = points

    assert _pixel(dialog, 150, 220) == QColor(240, 180, 100)
    assert _pixel(dialog, 400, 260) == QColor(90, 150, 220)
    outside = _pixel(dialog, 100, 400)
    assert 0 < outside.red() < 240
    assert outside.alpha() == 255
    assert screenshot.toImage() == original  # No mutation of frozen preview pixels.
    assert dialog.selected_crop is None  # Painting is not ROI confirmation.
    dialog._confirm_selection()
    assert dialog.selected_crop == ROICrop(
        top=180,
        bottom=120,
        left=130,
        right=130,
        configured=True,
        reference_width=640,
        reference_height=480,
    )


def test_roi_preview_reset_dims_old_selection_without_changing_source(qtbot):
    dialog = ROISetupDialog(WindowRect(0, 0, 640, 480), _pattern(1.5))
    qtbot.addWidget(dialog)
    dialog._selection_start = QPoint(130, 180)
    dialog._selection_end = QPoint(510, 360)
    assert _pixel(dialog, 150, 220) == QColor(240, 180, 100)

    qtbot.keyClick(dialog, Qt.Key.Key_R)

    assert dialog._selection_rect() is None
    assert dialog.selected_crop is None
    assert 0 < _pixel(dialog, 150, 220).red() < 240
