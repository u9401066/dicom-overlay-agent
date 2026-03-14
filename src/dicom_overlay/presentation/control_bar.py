"""Control Bar — separate non-transparent window for user interaction (spec §3.4 Element C).

This is a separate top-level window so it can receive mouse events
while the overlay window remains click-through.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QMouseEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import AgentState

logger = structlog.get_logger(__name__)

_BTN_STYLE = (
    "QPushButton { color: white; background: rgba(60,60,80,230); "
    "border: 1px solid #555; border-radius: 4px; padding: 4px 12px; "
    "font-size: 12px; }"
    "QPushButton:hover { background: rgba(80,80,110,240); }"
    "QPushButton:pressed { background: rgba(40,40,60,250); }"
)


class ControlBarWindow(QWidget):
    """Floating control bar window — always on top, not click-through."""

    pause_clicked = pyqtSignal()
    resume_clicked = pyqtSignal()
    retrigger_clicked = pyqtSignal()
    modality_cycle = pyqtSignal()
    settings_clicked = pyqtSignal()
    dismiss_clicked = pyqtSignal()
    chat_clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedHeight(44)
        self.setMinimumWidth(420)
        self.setStyleSheet(
            "background-color: rgba(25, 25, 35, 240); border-radius: 8px;"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        # Pause/Resume
        self._pause_btn = QPushButton("⏸ 暫停")
        self._pause_btn.setStyleSheet(_BTN_STYLE)
        self._pause_btn.clicked.connect(self._on_pause_toggle)
        layout.addWidget(self._pause_btn)

        # Retrigger
        self._retrigger_btn = QPushButton("🔄 重分析")
        self._retrigger_btn.setStyleSheet(_BTN_STYLE)
        self._retrigger_btn.clicked.connect(self.retrigger_clicked.emit)
        layout.addWidget(self._retrigger_btn)

        # Modality
        self._modality_btn = QPushButton("EKG")
        self._modality_btn.setStyleSheet(_BTN_STYLE)
        self._modality_btn.clicked.connect(self.modality_cycle.emit)
        layout.addWidget(self._modality_btn)

        # Chat
        self._chat_btn = QPushButton("💬 問AI")
        self._chat_btn.setStyleSheet(_BTN_STYLE)
        self._chat_btn.clicked.connect(self.chat_clicked.emit)
        layout.addWidget(self._chat_btn)

        # Status
        self._status_label = QLabel("等待中")
        self._status_label.setFont(QFont("Segoe UI", 10))
        self._status_label.setStyleSheet("color: #999; padding: 0 8px;")
        layout.addWidget(self._status_label)

        layout.addStretch()

        # Dismiss overlay
        self._settings_btn = QPushButton("⚙")
        self._settings_btn.setStyleSheet(_BTN_STYLE)
        self._settings_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self._settings_btn)

        self._dismiss_btn = QPushButton("✕")
        self._dismiss_btn.setStyleSheet(_BTN_STYLE)
        self._dismiss_btn.clicked.connect(self.dismiss_clicked.emit)
        layout.addWidget(self._dismiss_btn)

        self._is_paused = False

        # Dragging support
        self._drag_pos = None

    def _on_pause_toggle(self) -> None:
        if self._is_paused:
            self.resume_clicked.emit()
        else:
            self.pause_clicked.emit()

    def set_paused(self, paused: bool) -> None:
        self._is_paused = paused
        self._pause_btn.setText("▶ 恢復" if paused else "⏸ 暫停")

    def set_modality(self, modality: str) -> None:
        self._modality_btn.setText(modality)

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def update_state(self, state: AgentState) -> None:
        from dicom_overlay.domain.entities import AgentState as AS

        status_map = {
            AS.INIT: "初始化...",
            AS.SETUP: "ROI 設定中",
            AS.WAITING: "等待 DICOM viewer...",
            AS.MONITORING: "監控中",
            AS.CAPTURING: "截圖中...",
            AS.ANALYZING: "分析中...",
            AS.DISPLAYING: "顯示結果",
            AS.PAUSED: "已暫停",
            AS.ERROR: "錯誤",
            AS.RECONNECTING: "重新連線中...",
        }
        self.set_status(status_map.get(state, str(state)))

    def position_bottom_right(self, screen_width: int, screen_height: int) -> None:
        x = screen_width - self.width() - 20
        y = screen_height - self.height() - 60
        self.move(x, y)

    # --- Drag support ---
    def mousePressEvent(self, a0: QMouseEvent | None):
        if a0 is None:
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                a0.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            a0.accept()

    def mouseMoveEvent(self, a0: QMouseEvent | None):
        if a0 is None:
            return
        if self._drag_pos is not None and a0.buttons() & Qt.MouseButton.LeftButton:
            self.move(a0.globalPosition().toPoint() - self._drag_pos)
            a0.accept()

    def mouseReleaseEvent(self, a0: QMouseEvent | None):
        if a0 is None:
            return
        self._drag_pos = None
        a0.accept()
