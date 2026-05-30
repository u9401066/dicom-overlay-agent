"""Floating control bar for desktop overlay interaction."""

from __future__ import annotations

import structlog
from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QMouseEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from dicom_overlay.domain.entities import AgentState, TriggerMode

logger = structlog.get_logger(__name__)

_BTN_STYLE = (
    "QPushButton { color: white; background: rgba(60,60,80,230); "
    "border: 1px solid #555; border-radius: 4px; padding: 4px 12px; "
    "font-size: 12px; }"
    "QPushButton:hover { background: rgba(80,80,110,240); }"
    "QPushButton:pressed { background: rgba(40,40,60,250); }"
    "QPushButton[pending=\"true\"] { background: rgba(0,115,170,245); "
    "border: 1px solid #54c7ff; }"
)

_MODE_LABELS = {
    TriggerMode.MANUAL: "Manual",
    TriggerMode.HYBRID: "Hybrid",
    TriggerMode.AUTO: "Auto",
}


class ControlBarWindow(QWidget):
    """Floating control bar window: always on top and not click-through."""

    pause_clicked = pyqtSignal()
    resume_clicked = pyqtSignal()
    analyze_clicked = pyqtSignal()
    retrigger_clicked = pyqtSignal()
    modality_cycle = pyqtSignal()
    trigger_mode_changed = pyqtSignal(object)
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
        self.setMinimumWidth(560)
        self.setStyleSheet(
            "background-color: rgba(25, 25, 35, 240); border-radius: 8px;"
        )

        self._trigger_mode = TriggerMode.HYBRID
        self._is_paused = False
        self._drag_pos: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        self._pause_btn = self._button("Pause")
        self._pause_btn.clicked.connect(self._on_pause_toggle)
        layout.addWidget(self._pause_btn)

        self._analyze_btn = self._button("Analyze")
        self._analyze_btn.setObjectName("analyzeButton")
        self._analyze_btn.setProperty("pending", False)
        self._analyze_btn.clicked.connect(self._emit_analyze)
        layout.addWidget(self._analyze_btn)
        self._retrigger_btn = self._analyze_btn

        self._mode_btn = self._button(_MODE_LABELS[self._trigger_mode])
        self._mode_btn.setObjectName("triggerModeButton")
        self._mode_btn.clicked.connect(self._cycle_trigger_mode)
        layout.addWidget(self._mode_btn)

        self._modality_btn = self._button("EKG")
        self._modality_btn.clicked.connect(self.modality_cycle.emit)
        layout.addWidget(self._modality_btn)

        self._chat_btn = self._button("Ask AI")
        self._chat_btn.clicked.connect(self.chat_clicked.emit)
        layout.addWidget(self._chat_btn)

        self._status_label = QLabel("Waiting")
        self._status_label.setFont(QFont("Segoe UI", 10))
        self._status_label.setStyleSheet("color: #bbb; padding: 0 8px;")
        layout.addWidget(self._status_label)

        layout.addStretch()

        self._settings_btn = self._button("Settings")
        self._settings_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self._settings_btn)

        self._dismiss_btn = self._button("Quit")
        self._dismiss_btn.clicked.connect(self.dismiss_clicked.emit)
        layout.addWidget(self._dismiss_btn)

    @property
    def current_trigger_mode(self) -> TriggerMode:
        return self._trigger_mode

    def _button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setStyleSheet(_BTN_STYLE)
        return button

    def _on_pause_toggle(self) -> None:
        if self._is_paused:
            self.resume_clicked.emit()
        else:
            self.pause_clicked.emit()

    def set_paused(self, paused: bool) -> None:
        self._is_paused = paused
        self._pause_btn.setText("Resume" if paused else "Pause")

    def set_modality(self, modality: str) -> None:
        self._modality_btn.setText(modality)

    def set_trigger_mode(self, mode: TriggerMode) -> None:
        self._trigger_mode = mode
        self._mode_btn.setText(_MODE_LABELS[mode])

    def set_pending_analysis(self, pending: bool) -> None:
        self._analyze_btn.setProperty("pending", pending)
        self._analyze_btn.setText("Analyze new image" if pending else "Analyze")
        style = self._analyze_btn.style()
        if style is not None:
            style.unpolish(self._analyze_btn)
            style.polish(self._analyze_btn)
        self._analyze_btn.update()

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def update_state(self, state: AgentState) -> None:
        status_map = {
            AgentState.INIT: "Starting",
            AgentState.SETUP: "ROI setup needed",
            AgentState.WAITING: "Waiting for viewer",
            AgentState.MONITORING: "Monitoring",
            AgentState.CAPTURING: "Capturing",
            AgentState.ANALYZING: "Analyzing",
            AgentState.DISPLAYING: "Displaying result",
            AgentState.PAUSED: "Paused",
            AgentState.ERROR: "Error",
            AgentState.RECONNECTING: "Reconnecting",
        }
        self.set_status(status_map.get(state, state.name))

    def position_bottom_right(
        self,
        screen_width: int,
        screen_height: int,
        screen_left: int = 0,
        screen_top: int = 0,
    ) -> None:
        x = screen_left + screen_width - self.width() - 20
        y = screen_top + screen_height - self.height() - 60
        self.move(x, y)

    def _emit_analyze(self) -> None:
        self.analyze_clicked.emit()
        self.retrigger_clicked.emit()

    def _cycle_trigger_mode(self) -> None:
        cycle = [TriggerMode.HYBRID, TriggerMode.AUTO, TriggerMode.MANUAL]
        index = cycle.index(self._trigger_mode)
        next_mode = cycle[(index + 1) % len(cycle)]
        self.set_trigger_mode(next_mode)
        self.trigger_mode_changed.emit(next_mode)

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = a0.globalPosition().toPoint() - self.frameGeometry().topLeft()
            a0.accept()

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        if self._drag_pos is not None and a0.buttons() & Qt.MouseButton.LeftButton:
            self.move(a0.globalPosition().toPoint() - self._drag_pos)
            a0.accept()

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        self._drag_pos = None
        a0.accept()
