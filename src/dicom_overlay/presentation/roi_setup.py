"""Interactive ROI setup wizard for PHI-safe crop selection."""

from __future__ import annotations

from typing import Any, cast

import structlog
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QDialog, QLabel

from dicom_overlay.application.roi import (
    compute_roi_crop_from_safe_rect,
    normalize_selection,
)
from dicom_overlay.domain.entities import ROICrop, WindowRect

logger = structlog.get_logger(__name__)


class ROISetupDialog(QDialog):
    """Fullscreen-ish ROI selector.

    User drags the safe image area. Red outside region will be cropped.
    Press Enter to confirm, R to reset, Esc to cancel.
    """

    def __init__(
        self,
        base_rect: WindowRect,
        screenshot: QPixmap,
        existing_roi: ROICrop | None = None,
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)
        self._base_rect = base_rect
        self._screenshot = screenshot
        self._selection_start: QPoint | None = None
        self._selection_end: QPoint | None = None
        self._selected_crop: ROICrop | None = None

        # Pre-populate selection from existing ROI
        if existing_roi is not None and (
            existing_roi.left > 0
            or existing_roi.top > 0
            or existing_roi.right > 0
            or existing_roi.bottom > 0
        ):
            safe_x = existing_roi.left
            safe_y = existing_roi.top
            safe_w = base_rect.width - existing_roi.left - existing_roi.right
            safe_h = base_rect.height - existing_roi.top - existing_roi.bottom
            if safe_w > 0 and safe_h > 0:
                self._selection_start = QPoint(safe_x, safe_y)
                self._selection_end = QPoint(safe_x + safe_w, safe_y + safe_h)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setModal(True)
        self.setGeometry(
            base_rect.left,
            base_rect.top,
            base_rect.width,
            base_rect.height,
        )
        self.setMouseTracking(True)

        self._hint = QLabel(self)
        self._hint.setText(
            "拖曳框選安全影像區域  |  Enter 確認  |  R 重選  |  Esc 取消"
        )
        self._hint.setStyleSheet(
            "background: rgba(20,20,20,180); color: white;"
            "padding: 8px 12px; border-radius: 6px;"
        )
        self._hint.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._hint.adjustSize()
        self._hint.move(16, 16)

        self._status = QLabel(self)
        self._status.setStyleSheet(
            "background: rgba(20,20,20,180); color: #d0d0d0;"
            "padding: 6px 10px; border-radius: 6px;"
        )
        self._status.setFont(QFont("Segoe UI", 9))
        if self._selection_start is not None:
            self._update_status_preview()
        else:
            self._status.setText("尚未選取")
        self._status.adjustSize()
        self._status.move(16, 56)

    @property
    def selected_crop(self) -> ROICrop | None:
        return self._selected_crop

    def _selection_rect(self) -> QRect | None:
        if self._selection_start is None or self._selection_end is None:
            return None
        x, y, width, height = normalize_selection(
            self._selection_start.x(),
            self._selection_start.y(),
            self._selection_end.x(),
            self._selection_end.y(),
        )
        if width <= 0 or height <= 0:
            return None
        return QRect(x, y, width, height)

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            self._selection_start = a0.position().toPoint()
            self._selection_end = self._selection_start
            self.update()
            a0.accept()

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None or self._selection_start is None:
            return
        if a0.buttons() & Qt.MouseButton.LeftButton:
            self._selection_end = a0.position().toPoint()
            self._update_status_preview()
            self.update()
            a0.accept()

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        if a0.button() == Qt.MouseButton.LeftButton and self._selection_start is not None:
            self._selection_end = a0.position().toPoint()
            self._update_status_preview()
            self.update()
            a0.accept()

    def keyPressEvent(self, a0: QKeyEvent | None) -> None:
        if a0 is None:
            return
        if a0.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm_selection()
            return
        if a0.key() == Qt.Key.Key_R:
            self._selection_start = None
            self._selection_end = None
            self._selected_crop = None
            self._status.setText("尚未選取")
            self._status.adjustSize()
            self.update()
            return
        if a0.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(a0)

    def _update_status_preview(self) -> None:
        rect = self._selection_rect()
        if rect is None:
            self._status.setText("尚未選取")
        else:
            self._status.setText(
                f"safe: x={rect.x()} y={rect.y()} w={rect.width()} h={rect.height()}"
            )
        self._status.adjustSize()

    def _confirm_selection(self) -> None:
        rect = self._selection_rect()
        if rect is None:
            self._status.setText("請先拖曳框選安全區域")
            self._status.adjustSize()
            return
        self._selected_crop = compute_roi_crop_from_safe_rect(
            self._base_rect,
            (rect.x(), rect.y(), rect.width(), rect.height()),
        )
        logger.info(
            "ROI selected: top=%d bottom=%d left=%d right=%d",
            self._selected_crop.top,
            self._selected_crop.bottom,
            self._selected_crop.left,
            self._selected_crop.right,
        )
        self.accept()

    def paintEvent(self, a0: object) -> None:
        del a0
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.drawPixmap(self.rect(), self._screenshot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

        rect = self._selection_rect()
        if rect is not None:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, QColor(0, 0, 0, 0))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            pen = QPen(QColor(0, 220, 120, 255), 3)
            painter.setPen(pen)
            painter.drawRect(rect)

        painter.end()


def run_roi_setup(
    app: QApplication,
    target_rect: WindowRect | None = None,
    existing_roi: ROICrop | None = None,
) -> ROICrop | None:
    """Launch ROI setup dialog and return selected crop margins."""
    screen = app.primaryScreen()
    if screen is None:
        return None

    if target_rect is None:
        geo = screen.geometry()
        base_rect = WindowRect(
            left=geo.left(),
            top=geo.top(),
            width=geo.width(),
            height=geo.height(),
        )
        screenshot = screen.grabWindow(cast("Any", 0))
    else:
        base_rect = target_rect
        screenshot = screen.grabWindow(
            cast("Any", 0),
            target_rect.left,
            target_rect.top,
            target_rect.width,
            target_rect.height,
        )

    dialog = ROISetupDialog(
        base_rect=base_rect,
        screenshot=screenshot,
        existing_roi=existing_roi,
    )
    result = dialog.exec()
    if result == QDialog.DialogCode.Accepted:
        return dialog.selected_crop
    return None
