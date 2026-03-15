"""PyQt6 Overlay Window — transparent overlay with summary panel + control bar (spec §3.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import (
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import (
        AnalysisResult,
        WindowRect,
    )

logger = structlog.get_logger(__name__)

# Severity color map (spec §3.4)
SEVERITY_COLORS: dict[str, QColor] = {
    "critical": QColor(220, 53, 69, 200),   # red
    "warning": QColor(255, 193, 7, 200),     # yellow
    "normal": QColor(40, 167, 69, 180),      # green
    "info": QColor(108, 117, 125, 150),      # gray
}


class _DraggableWindowMixin:
    """Mixin providing drag-to-move for frameless top-level panels."""

    _drag_pos: object = None

    def _init_draggable_window(self) -> None:
        """Call from __init__ to set up top-level window flags."""
        self.setWindowFlags(  # type: ignore[attr-defined]
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # type: ignore[attr-defined]
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # type: ignore[attr-defined]

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                a0.globalPosition().toPoint()
                - self.frameGeometry().topLeft()  # type: ignore[attr-defined]
            )
            a0.accept()

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        if self._drag_pos is not None and a0.buttons() & Qt.MouseButton.LeftButton:
            self.move(a0.globalPosition().toPoint() - self._drag_pos)  # type: ignore[attr-defined]
            a0.accept()

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        self._drag_pos = None
        a0.accept()


class SummaryPanel(_DraggableWindowMixin, QWidget):
    """Draggable side panel showing analysis checklist (spec §3.4 Element B)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_draggable_window()
        self.setFixedWidth(320)
        self.setStyleSheet(
            "background-color: rgba(20, 20, 30, 220); "
            "border-radius: 8px; "
            "padding: 8px;"
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(4)

        # Drag handle hint
        drag_hint = QLabel("⠿ 拖曳移動")
        drag_hint.setFont(QFont("Segoe UI", 8))
        drag_hint.setStyleSheet("color: #666; padding: 0;")
        drag_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(drag_hint)

        self._title_label = QLabel("📊 Analysis")
        self._title_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._title_label.setStyleSheet("color: white; padding-bottom: 4px;")
        self._layout.addWidget(self._title_label)

        self._separator = QLabel("─" * 30)
        self._separator.setStyleSheet("color: #555;")
        self._layout.addWidget(self._separator)

        self._content_layout = QVBoxLayout()
        self._content_layout.setSpacing(2)
        self._layout.addLayout(self._content_layout)

        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        self._summary_label.setFont(QFont("Segoe UI", 10))
        self._summary_label.setStyleSheet("color: #ccc; padding-top: 8px;")
        self._layout.addWidget(self._summary_label)

        self._layout.addStretch()

    def update_result(self, result: AnalysisResult) -> None:
        """Update panel with new analysis result."""
        from dicom_overlay.domain.entities import Severity

        modality_icons = {"EKG": "🫀", "CXR": "🫁", "CT_BRAIN": "🧠"}
        icon = modality_icons.get(result.modality.value, "📊")
        self._title_label.setText(f"{icon} {result.modality.value} Analysis")

        # Clear old content
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        # Partition checklist: abnormal items first, then normal summary
        abnormal_items: list[tuple[str, object]] = []
        normal_count = 0
        for key, item in result.checklist.items():
            if item.status in (Severity.CRITICAL, Severity.WARNING):
                abnormal_items.append((key, item))
            else:
                normal_count += 1

        # Show abnormal items prominently
        for key, item in abnormal_items:
            status_icon = {
                Severity.WARNING: "⚠️",
                Severity.CRITICAL: "🔴",
            }.get(item.status, "⚠️")

            display_key = _humanize_checklist_key(key)
            display_val = _humanize_checklist_value(item.value)
            label = QLabel(f"{status_icon} {display_key}: {display_val}")
            label.setWordWrap(True)
            label.setFont(QFont("Segoe UI", 10))
            color = SEVERITY_COLORS.get(item.status.value, SEVERITY_COLORS["info"])
            label.setStyleSheet(
                f"color: rgb({color.red()}, {color.green()}, {color.blue()}); "
                "padding: 2px 0px;"
            )
            self._content_layout.addWidget(label)

        # Collapse normal items into a single summary line
        if normal_count > 0:
            normal_label = QLabel(f"✅ {normal_count} items normal")
            normal_label.setFont(QFont("Segoe UI", 9))
            normal_label.setStyleSheet(
                f"color: rgb({SEVERITY_COLORS['normal'].red()}, "
                f"{SEVERITY_COLORS['normal'].green()}, "
                f"{SEVERITY_COLORS['normal'].blue()}); "
                "padding: 2px 0px;"
            )
            self._content_layout.addWidget(normal_label)

        # Summary
        sev_icon = {"critical": "🔴", "warning": "⚠️", "normal": "🟢"}.get(
            result.severity.value, "[i]"
        )
        self._summary_label.setText(f"{sev_icon} {result.summary}")

    def clear(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._summary_label.setText("")
        self._title_label.setText("📊 Waiting...")


class ChatPanel(_DraggableWindowMixin, QWidget):
    """Draggable panel for displaying chat Q&A."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_draggable_window()
        self.setFixedWidth(400)
        self.setStyleSheet(
            "background-color: rgba(20, 20, 30, 230); "
            "border-radius: 8px; "
            "padding: 8px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Drag handle hint
        drag_hint = QLabel("⠿ 拖曳移動")
        drag_hint.setFont(QFont("Segoe UI", 8))
        drag_hint.setStyleSheet("color: #666; padding: 0;")
        drag_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(drag_hint)

        self._title_label = QLabel("💬 AI 對話")
        self._title_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._title_label.setStyleSheet("color: white; padding-bottom: 4px;")
        layout.addWidget(self._title_label)

        sep = QLabel("─" * 36)
        sep.setStyleSheet("color: #555;")
        layout.addWidget(sep)

        # Question
        self._question_label = QLabel("")
        self._question_label.setWordWrap(True)
        self._question_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._question_label.setStyleSheet("color: #8cb4ff; padding: 4px 0;")
        layout.addWidget(self._question_label)

        # Answer (scrollable)
        self._answer_label = QLabel("")
        self._answer_label.setWordWrap(True)
        self._answer_label.setFont(QFont("Segoe UI", 10))
        self._answer_label.setStyleSheet("color: #ddd;")
        self._answer_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        scroll = QScrollArea()
        scroll.setWidget(self._answer_label)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: #555; border-radius: 3px; }"
        )
        layout.addWidget(scroll, stretch=1)

    def show_chat(self, question: str, answer: str) -> None:
        self._question_label.setText(f"Q: {question}")
        self._answer_label.setText(answer)
        self.setVisible(True)

    def show_waiting(self, question: str) -> None:
        self._question_label.setText(f"Q: {question}")
        self._answer_label.setText("思考中…")
        self.setVisible(True)

    def clear(self) -> None:
        self._question_label.setText("")
        self._answer_label.setText("")
        self.setVisible(False)


class OverlayWindow(QWidget):
    """Main transparent overlay window (spec §3.4).

    Click-through except for summary panel and control bar.
    """

    display_expired = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()

        # Window flags: frameless, always on top, transparent, tool window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Summary panel — independent draggable window (right side)
        self.summary_panel = SummaryPanel()
        self.summary_panel.setVisible(False)

        # Chat panel — independent draggable window (left side)
        self.chat_panel = ChatPanel()
        self.chat_panel.setVisible(False)

        # Fade timer
        self._display_timer = QTimer(self)
        self._display_timer.setSingleShot(True)
        self._display_timer.timeout.connect(self._fade_out)

        self._display_duration_sec = 30
        self._critical_persist = True
        self._current_severity = "normal"

        # Region highlights to draw
        self._highlights: list[tuple[int, int, int, int, str, str]] = []  # x, y, w, h, severity, label

    def configure(
        self,
        display_duration_sec: int = 30,
        critical_persist: bool = True,
    ) -> None:
        self._display_duration_sec = display_duration_sec
        self._critical_persist = critical_persist

    def position_over_window(self, rect: WindowRect) -> None:
        """Position overlay to cover the full screen.

        The overlay spans the entire primary screen so that the summary panel,
        chat panel, and region highlights are not clipped by the viewer window
        boundaries.  ``rect`` is kept for reference but no longer constrains
        the overlay size.
        """
        from PyQt6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if screen is None:
            # Fallback: use viewer window bounds (should not happen)
            from dicom_overlay.infrastructure.dpi import physical_to_logical

            logical = physical_to_logical(rect)
            self.setGeometry(logical.left, logical.top, logical.width, logical.height)
            sw, sh = logical.width, logical.height
        else:
            geo = screen.geometry()
            self.setGeometry(geo.x(), geo.y(), geo.width(), geo.height())
            sw, sh = geo.width(), geo.height()

        # Place summary panel on right side of screen
        panel_x = sw - self.summary_panel.width() - 10
        self.summary_panel.move(panel_x, 10)
        self.summary_panel.setFixedHeight(sh - 70)

        # Place chat panel on left side of screen
        self.chat_panel.move(10, 10)
        self.chat_panel.setFixedHeight(sh - 70)

    def show_result(
        self,
        result: AnalysisResult,
        highlights: list[tuple[int, int, int, int, str, str]] | None = None,
    ) -> None:
        """Show analysis result on overlay."""
        self.summary_panel.update_result(result)
        self.summary_panel.setVisible(True)
        self._current_severity = result.severity.value
        self._highlights = highlights or []

        self.setWindowOpacity(1.0)
        self.show()
        self.update()

        # Results persist until dismissed or new image triggers a new analysis.
        # No auto-hide timer.

    def clear_result(self) -> None:
        self.summary_panel.clear()
        self._highlights.clear()
        self.update()

    def show_chat_waiting(self, question: str) -> None:
        """Show chat panel with 'thinking' placeholder."""
        self.chat_panel.show_waiting(question)
        self.setWindowOpacity(1.0)
        self.show()

    def show_chat_response(self, question: str, answer: str) -> None:
        """Show chat Q&A on overlay."""
        self.chat_panel.show_chat(question, answer)
        self.setWindowOpacity(1.0)
        self.show()
        # Auto-hide after display duration
        self._display_timer.start(self._display_duration_sec * 1000)

    def _fade_out(self) -> None:
        self.setWindowOpacity(0.0)
        self.summary_panel.setVisible(False)
        self.chat_panel.clear()
        self._highlights.clear()
        self.update()
        self.display_expired.emit()

    def dismiss(self) -> None:
        self._display_timer.stop()
        self._fade_out()

    def paintEvent(self, a0: object) -> None:
        """Draw region highlights with labels (spec §3.4)."""
        del a0
        if not self._highlights:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for x, y, w, h, severity, label in self._highlights:
            color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["info"])
            # Semi-transparent fill
            fill_color = QColor(color.red(), color.green(), color.blue(), 40)
            painter.fillRect(x, y, w, h, fill_color)
            # Border
            pen = QPen(color, 2)
            painter.setPen(pen)
            painter.drawRect(x, y, w, h)

            # Text label (spec §3.4 — 定性描述標籤)
            if label:
                font = QFont("Segoe UI", 9, QFont.Weight.Bold)
                painter.setFont(font)
                # Background for readability
                bg = QColor(0, 0, 0, 180)
                text_x = x + 4
                text_y = y - 2
                metrics = painter.fontMetrics()
                text_rect = metrics.boundingRect(label)
                painter.fillRect(
                    text_x - 2, text_y - text_rect.height(),
                    text_rect.width() + 6, text_rect.height() + 4,
                    bg,
                )
                painter.setPen(QPen(color, 1))
                painter.drawText(text_x, text_y, label)

        painter.end()


# ── Checklist display helpers ──

_KEY_DISPLAY_MAP: dict[str, str] = {
    # EKG – 16-point systematic checklist
    "heart_rate": "Heart Rate",
    "rhythm": "Rhythm",
    "regularity": "Regularity",
    "axis": "Axis",
    "p_wave": "P Wave",
    "pr_interval": "PR Interval",
    "qrs_duration": "QRS Duration",
    "qrs_morphology": "QRS Morph.",
    "st_segment": "ST Segment",
    "t_wave": "T Wave",
    "qtc_interval": "QTc",
    "chamber_enlargement": "Chamber Enlg.",
    "conduction": "Conduction",
    "av_block": "AV Block",
    "stemi_pattern": "STEMI",
    "ischemia": "Ischemia",
    # CXR
    "cardiomegaly": "Cardiomegaly",
    "pneumothorax": "Pneumothorax",
    "pleural_effusion": "Pleural Eff.",
    "consolidation": "Consolidation",
    # CT Brain
    "midline_shift": "Midline Shift",
    "hemorrhage": "Hemorrhage",
}


def _humanize_checklist_key(key: str) -> str:
    """Convert underscore keys to readable display names."""
    if key in _KEY_DISPLAY_MAP:
        return _KEY_DISPLAY_MAP[key]
    return key.replace("_", " ").title()


def _humanize_checklist_value(value: str) -> str:
    """Clean up verbose underscore-separated GPT values."""
    if not value:
        return "—"
    # Replace underscores with spaces, collapse multiple spaces
    cleaned = value.replace("_", " ").strip()
    # Capitalize first letter
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned
