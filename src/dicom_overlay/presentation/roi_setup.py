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
from dicom_overlay.infrastructure.dpi import (
    get_dpi_scale,
    logical_to_physical_roi,
    physical_to_logical,
    physical_to_logical_roi,
)

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
        target_rect: WindowRect | None = None,
        existing_roi: ROICrop | None = None,
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)
        self._base_rect = base_rect
        self._screenshot = screenshot
        self._target_rect = target_rect or base_rect
        self._selection_start: QPoint | None = None
        self._selection_end: QPoint | None = None
        self._selected_crop: ROICrop | None = None
        self._drag_origin: QPoint | None = None  # pending click, not yet a drag
        self._dragging = False
        self._has_existing = False

        # Offset from dialog origin (screen) to target window origin
        self._target_offset_x = self._target_rect.left - base_rect.left
        self._target_offset_y = self._target_rect.top - base_rect.top

        # Pre-populate selection from existing ROI (screen-relative margins)
        if existing_roi is not None and (
            existing_roi.left > 0
            or existing_roi.top > 0
            or existing_roi.right > 0
            or existing_roi.bottom > 0
        ):
            safe_x = existing_roi.left
            safe_y = existing_roi.top
            safe_w = self._base_rect.width - existing_roi.left - existing_roi.right
            safe_h = self._base_rect.height - existing_roi.top - existing_roi.bottom
            if safe_w > 0 and safe_h > 0:
                # Dialog covers full screen, so dialog-local = screen coords
                self._selection_start = QPoint(safe_x, safe_y)
                self._selection_end = QPoint(safe_x + safe_w, safe_y + safe_h)
                self._has_existing = True

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
        if self._has_existing:
            self._hint.setText(
                "Enter 保留目前設定  |  拖曳重新選取  |  R 清除  |  Esc 取消"
            )
        else:
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

    _DRAG_THRESHOLD = 5  # px — ignore jitter, only start drag after real movement

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = a0.position().toPoint()
            self._dragging = False
            a0.accept()

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None or self._drag_origin is None:
            return
        if a0.buttons() & Qt.MouseButton.LeftButton:
            pos = a0.position().toPoint()
            if not self._dragging:
                dx = abs(pos.x() - self._drag_origin.x())
                dy = abs(pos.y() - self._drag_origin.y())
                if dx < self._DRAG_THRESHOLD and dy < self._DRAG_THRESHOLD:
                    return  # not yet a real drag
                # Commit to new selection
                self._dragging = True
                self._selection_start = self._drag_origin
            self._selection_end = pos
            self._update_status_preview()
            self.update()
            a0.accept()

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            if self._dragging and self._selection_start is not None:
                self._selection_end = a0.position().toPoint()
                self._update_status_preview()
                self.update()
            self._drag_origin = None
            self._dragging = False
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
            # Show coords (screen-relative, same as dialog-local since dialog
            # covers the full screen)
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
        # Selection is in dialog-local coords (= screen coords since dialog
        # covers the full screen).  Compute ROI margins relative to the full
        # screen so they are position-independent of the viewer window.
        adj_x = max(0, rect.x())
        adj_y = max(0, rect.y())
        adj_w = min(rect.width(), self._base_rect.width - adj_x)
        adj_h = min(rect.height(), self._base_rect.height - adj_y)
        if adj_w <= 0 or adj_h <= 0:
            self._status.setText("選取區域無效，請重新選取")
            self._status.adjustSize()
            return
        self._selected_crop = compute_roi_crop_from_safe_rect(
            self._base_rect,
            (adj_x, adj_y, adj_w, adj_h),
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

        # Draw target window boundary as visual guide
        if self._target_rect != self._base_rect:
            tw_pen = QPen(QColor(100, 150, 255, 180), 2, Qt.PenStyle.DashLine)
            painter.setPen(tw_pen)
            painter.drawRect(
                self._target_offset_x,
                self._target_offset_y,
                self._target_rect.width,
                self._target_rect.height,
            )

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
    """Launch ROI setup dialog and return selected crop margins.

    ``target_rect`` is in physical pixels (from Win32).  We convert it
    to Qt logical pixels for the dialog, then convert the result back.
    ``existing_roi`` is also in physical pixels.
    """
    screen = app.primaryScreen()
    if screen is None:
        return None

    # Always use fullscreen for the dialog so user can see the full context
    geo = screen.geometry()
    base_rect = WindowRect(
        left=geo.left(),
        top=geo.top(),
        width=geo.width(),
        height=geo.height(),
    )
    screenshot = screen.grabWindow(cast("Any", 0))

    # Convert Win32 physical-pixel coords to Qt logical coords
    logical_target = physical_to_logical(target_rect) if target_rect else None

    # Convert existing ROI margins (physical) to logical for display
    logical_roi = existing_roi
    if existing_roi and get_dpi_scale() != 1.0:
        lt, lb, ll, lr = physical_to_logical_roi(
            existing_roi.top, existing_roi.bottom,
            existing_roi.left, existing_roi.right,
        )
        logical_roi = ROICrop(top=lt, bottom=lb, left=ll, right=lr)

    dialog = ROISetupDialog(
        base_rect=base_rect,
        screenshot=screenshot,
        target_rect=logical_target,
        existing_roi=logical_roi,
    )
    result = dialog.exec()
    if result == QDialog.DialogCode.Accepted and dialog.selected_crop:
        crop = dialog.selected_crop
        # Convert logical-pixel margins back to physical pixels
        pt, pb, pl, pr = logical_to_physical_roi(
            crop.top, crop.bottom, crop.left, crop.right,
        )
        return ROICrop(top=pt, bottom=pb, left=pl, right=pr)
    return None
