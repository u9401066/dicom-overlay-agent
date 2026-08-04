"""PyQt6 Overlay Window — transparent overlay with summary panel + control bar (spec §3.4)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog
from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import (
        AnalysisResult,
        ChecklistItem,
        DisplayFrame,
        RegionRect,
        WindowRect,
    )
    from dicom_overlay.infrastructure.overlay_geometry import OverlayCoordinateFrame

logger = structlog.get_logger(__name__)

# Severity color map (spec §3.4)
SEVERITY_COLORS: dict[str, QColor] = {
    "critical": QColor(220, 53, 69, 200),  # red
    "warning": QColor(255, 193, 7, 200),  # yellow
    "normal": QColor(40, 167, 69, 180),  # green
    "info": QColor(108, 117, 125, 150),  # gray
}


class _DraggableWindowMixin:
    """Mixin providing drag-to-move for frameless top-level panels."""

    _drag_pos: QPoint | None = None

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
                a0.globalPosition().toPoint() - self.frameGeometry().topLeft()  # type: ignore[attr-defined]
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
    """Draggable report panel with findings, checklist, and run provenance."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_draggable_window()
        self.setFixedWidth(430)
        self.setStyleSheet(
            "background-color: rgba(20, 20, 30, 220); border-radius: 8px; padding: 8px;"
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(4)

        drag_hint = QLabel("Drag")
        drag_hint.setFont(QFont("Segoe UI", 8))
        drag_hint.setStyleSheet("color: #666; padding: 0;")
        drag_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(drag_hint)

        self._title_label = QLabel("Clinical Review")
        self._title_label.setTextFormat(Qt.TextFormat.PlainText)
        self._title_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._title_label.setStyleSheet("color: white; padding-bottom: 4px;")
        self._layout.addWidget(self._title_label)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #444; border-radius: 4px; }"
            "QTabBar::tab { color: #bbb; background: #2b2b36; padding: 6px 12px; }"
            "QTabBar::tab:selected { color: white; background: #3d4655; }"
        )
        report_page, self._report_layout = self._scroll_page()
        checklist_page, self._checklist_layout = self._scroll_page()
        process_page, self._process_layout = self._scroll_page()
        self._content_layout = self._checklist_layout
        self._tabs.addTab(report_page, "Report")
        self._tabs.addTab(checklist_page, "Checklist")
        self._tabs.addTab(process_page, "Process")
        self._layout.addWidget(self._tabs, stretch=1)

        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        self._summary_label.setTextFormat(Qt.TextFormat.PlainText)
        self._summary_label.setFont(QFont("Segoe UI", 10))
        self._summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._summary_label.setStyleSheet("color: #ddd; padding: 4px 0 8px 0;")
        self._report_layout.addWidget(self._summary_label)

        # Degradation badge: shown when the result failed schema checks
        # (partial JSON, missing checklist keys) so the physician never reads
        # a degraded result as a clean "all normal".
        self._incomplete_label = QLabel("")
        self._incomplete_label.setWordWrap(True)
        self._incomplete_label.setTextFormat(Qt.TextFormat.PlainText)
        self._incomplete_label.setFont(QFont("Segoe UI", 9))
        self._incomplete_label.setStyleSheet("color: #ffb000; padding-top: 6px;")
        self._incomplete_label.setVisible(False)
        self._report_layout.addWidget(self._incomplete_label)

        # Manual-zoom hint: shown when a lesion is too small in the screen
        # capture to resolve further by digital crop, so the user is asked to
        # zoom in their DICOM viewer and re-capture.
        self._zoom_hint_label = QLabel("")
        self._zoom_hint_label.setWordWrap(True)
        self._zoom_hint_label.setTextFormat(Qt.TextFormat.PlainText)
        self._zoom_hint_label.setFont(QFont("Segoe UI", 9))
        self._zoom_hint_label.setStyleSheet("color: #4ea1ff; padding-top: 6px;")
        self._zoom_hint_label.setVisible(False)
        self._report_layout.addWidget(self._zoom_hint_label)

        # Clinical review flag: shown when the data-driven consistency engine
        # escalated a result whose structured read contradicts itself (e.g. ST
        # elevation described yet rated normal). Distinct, alarming styling so
        # the physician treats it as a "double-check this" prompt, not a benign
        # note. Carries the guideline citation behind the flag.
        self._review_label = QLabel("")
        self._review_label.setWordWrap(True)
        self._review_label.setTextFormat(Qt.TextFormat.PlainText)
        self._review_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._review_label.setStyleSheet("color: #ff5252; padding-top: 6px;")
        self._review_label.setVisible(False)
        self._report_layout.addWidget(self._review_label)

        findings_heading = QLabel("Findings")
        findings_heading.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        findings_heading.setStyleSheet("color: white; padding-top: 10px;")
        self._report_layout.addWidget(findings_heading)
        self._findings_layout = QVBoxLayout()
        self._findings_layout.setSpacing(8)
        self._report_layout.addLayout(self._findings_layout)

    @staticmethod
    def _scroll_page() -> tuple[QScrollArea, QVBoxLayout]:
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(body)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 7px; background: transparent; }"
            "QScrollBar::handle:vertical { background: #666; border-radius: 3px; }"
        )
        return scroll, layout

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def update_result(self, result: AnalysisResult) -> None:
        """Update panel with new analysis result."""
        from dicom_overlay.domain.entities import Severity
        from dicom_overlay.domain.modality_profile import get_active_registry

        profile = get_active_registry().resolve(result.modality.value)
        self._title_label.setText(
            f"{profile.icon} {profile.resolved_display_name()} Analysis"
        )

        self._clear_layout(self._findings_layout)
        self._clear_layout(self._checklist_layout)
        self._clear_layout(self._process_layout)

        severity_rank = {
            Severity.CRITICAL: 0,
            Severity.WARNING: 1,
            Severity.INFO: 2,
            Severity.NORMAL: 3,
        }
        checklist_rows: list[tuple[str, ChecklistItem]] = sorted(
            result.checklist.items(),
            key=lambda row: (severity_rank[row[1].status], row[0]),
        )
        for key, checklist_item in checklist_rows:
            display_key = _humanize_checklist_key(key)
            display_val = _humanize_checklist_value(checklist_item.value)
            label = QLabel(
                f"{checklist_item.status.value.upper()}  {display_key}: {display_val}"
            )
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setFont(QFont("Segoe UI", 9))
            color = SEVERITY_COLORS.get(
                checklist_item.status.value, SEVERITY_COLORS["info"]
            )
            label.setStyleSheet(
                f"color: rgb({color.red()}, {color.green()}, {color.blue()}); "
                "padding: 2px 0px;"
            )
            self._content_layout.addWidget(label)

        metadata = " | ".join(
            value
            for value in (
                result.model_used.strip(),
                f"{result.analysis_time_ms} ms" if result.analysis_time_ms else "",
            )
            if value
        )
        self._summary_label.setText(
            f"{result.severity.value.upper()}\n{result.summary}"
            + (f"\n{metadata}" if metadata else "")
        )

        if result.findings:
            for index, finding in enumerate(result.findings, start=1):
                regions = ", ".join(finding.regions) or "unlocalized"
                lines = [
                    f"{index}. {finding.label} [{finding.severity.value}]",
                    finding.detail or "No detail provided.",
                    f"Regions: {regions} | Boxes: {len(finding.bboxes)}",
                ]
                if finding.confidence:
                    lines.append(f"Confidence: {finding.confidence}")
                if finding.question:
                    lines.append(f"Question for review: {finding.question}")
                if finding.source and finding.source != "ai":
                    lines.append(
                        f"Source: {finding.source.replace('_', ' ').replace('+', ' + ')}"
                    )
                lines.extend(f"Note: {note}" for note in finding.notes)
                finding_label = QLabel("\n".join(lines))
                finding_label.setWordWrap(True)
                finding_label.setTextFormat(Qt.TextFormat.PlainText)
                finding_label.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                finding_label.setFont(QFont("Segoe UI", 9))
                color = SEVERITY_COLORS.get(
                    finding.severity.value,
                    SEVERITY_COLORS["info"],
                )
                finding_label.setStyleSheet(
                    f"color: rgb({color.red()}, {color.green()}, {color.blue()}); "
                    "padding: 3px 0; border-bottom: 1px solid #3f3f49;"
                )
                self._findings_layout.addWidget(finding_label)
        else:
            empty = QLabel("No focal findings reported.")
            empty.setStyleSheet("color: #aaa;")
            self._findings_layout.addWidget(empty)

        if result.image_quality:
            quality = (
                json.dumps(result.image_quality, ensure_ascii=False)
                if isinstance(result.image_quality, dict)
                else result.image_quality
            )
            quality_label = QLabel(f"Image quality: {quality}")
            quality_label.setWordWrap(True)
            quality_label.setTextFormat(Qt.TextFormat.PlainText)
            quality_label.setStyleSheet("color: #c8ced9; padding: 4px 0;")
            self._findings_layout.addWidget(quality_label)
        if result.next_steps:
            next_label = QLabel(
                "Next steps:\n"
                + "\n".join(
                    f"{index}. {step}"
                    for index, step in enumerate(result.next_steps, 1)
                )
            )
            next_label.setWordWrap(True)
            next_label.setTextFormat(Qt.TextFormat.PlainText)
            next_label.setStyleSheet("color: #c8ced9; padding: 4px 0;")
            self._findings_layout.addWidget(next_label)

        for index, entry in enumerate(result.analysis_trace, start=1):
            stage = str(entry.get("stage", "step")).replace("_", " ").title()
            status = str(entry.get("status", ""))
            details: list[str] = []
            tool = str(entry.get("tool", ""))
            tools = entry.get("tools", [])
            if tool:
                details.append(f"Internal: {tool}")
            if isinstance(tools, list) and tools:
                details.append(f"OpenClaw tools: {', '.join(map(str, tools))}")
            if entry.get("target_id"):
                details.append(f"Target: {entry['target_id']}")
            if entry.get("operation"):
                details.append(f"Operation: {entry['operation']}")
            if entry.get("bbox_source"):
                details.append(f"Box source: {entry['bbox_source']}")
            if entry.get("user_confirmed") is True:
                details.append("Reviewer confirmation: recorded")
            signal_audit = entry.get("local_signal_audit")
            if isinstance(signal_audit, dict):
                signal_bits = []
                if signal_audit.get("status"):
                    signal_bits.append(f"status={signal_audit['status']}")
                if isinstance(signal_audit.get("ink_pixel_ratio"), (int, float)):
                    signal_bits.append(
                        f"ink={float(signal_audit['ink_pixel_ratio']):.3%}"
                    )
                if isinstance(signal_audit.get("edge_pixel_ratio"), (int, float)):
                    signal_bits.append(
                        f"edges={float(signal_audit['edge_pixel_ratio']):.3%}"
                    )
                if isinstance(signal_audit.get("robust_dynamic_range"), (int, float)):
                    signal_bits.append(
                        f"range={float(signal_audit['robust_dynamic_range']):.0f}"
                    )
                if isinstance(signal_audit.get("low_signal"), bool):
                    signal_bits.append(f"low_signal={signal_audit['low_signal']}")
                if signal_bits:
                    details.append(f"Local signal audit: {', '.join(signal_bits)}")
            if entry.get("hypothesis"):
                details.append(f"Hypothesis: {entry['hypothesis']}")
            crop_source = str(entry.get("crop_source") or entry.get("source") or "")
            if crop_source:
                details.append(f"Source: {crop_source}")
            crop = entry.get("crop_region")
            if isinstance(crop, dict):
                details.append(
                    "Crop: "
                    + ", ".join(
                        f"{key}={float(crop.get(key, 0.0)):.4f}"
                        for key in ("x", "y", "w", "h")
                    )
                )
            probes = entry.get("probes")
            if isinstance(probes, list):
                for probe in probes:
                    if not isinstance(probe, dict):
                        continue
                    probe_id = str(probe.get("target_id", "probe"))
                    probe_crop = probe.get("crop_region")
                    probe_text = f"Probe: {probe_id}"
                    if isinstance(probe_crop, dict):
                        probe_text += (
                            " ("
                            + ", ".join(
                                f"{key}={float(probe_crop.get(key, 0.0)):.4f}"
                                for key in ("x", "y", "w", "h")
                            )
                            + ")"
                        )
                    details.append(probe_text)
            tool_audit = entry.get("tool_audit")
            if isinstance(tool_audit, list):
                for receipt in tool_audit:
                    if not isinstance(receipt, dict):
                        continue
                    receipt_tool = str(receipt.get("tool", "tool"))
                    accepted = receipt.get("accepted_count")
                    rejected = receipt.get("rejected_count")
                    counts = []
                    if isinstance(accepted, int):
                        counts.append(f"accepted={accepted}")
                    if isinstance(rejected, int):
                        counts.append(f"rejected={rejected}")
                    receipt_status = receipt.get("status")
                    if isinstance(receipt_status, str) and receipt_status:
                        counts.append(f"status={receipt_status}")
                    prediction_count = receipt.get("prediction_count")
                    if isinstance(prediction_count, int):
                        counts.append(f"predictions={prediction_count}")
                    calibration_status = receipt.get("calibration_status")
                    if isinstance(calibration_status, str) and calibration_status:
                        counts.append(f"calibration={calibration_status}")
                    details.append(
                        f"Tool receipt: {receipt_tool}"
                        + (f" ({', '.join(counts)})" if counts else "")
                    )
            decisions = entry.get("decisions")
            if isinstance(decisions, list):
                for decision in decisions:
                    if not isinstance(decision, dict):
                        continue
                    action = str(decision.get("action", "decision")).upper()
                    rationale = str(decision.get("rationale", "")).strip()
                    details.append(f"{action}: {rationale}".rstrip(": "))
            process_label = QLabel(
                f"{index}. {stage} [{status}]"
                + ("\n" + "\n".join(details) if details else "")
            )
            process_label.setWordWrap(True)
            process_label.setTextFormat(Qt.TextFormat.PlainText)
            process_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            process_label.setFont(QFont("Segoe UI", 9))
            process_label.setStyleSheet(
                "color: #ccd3df; padding: 4px 0; border-bottom: 1px solid #3f3f49;"
            )
            self._process_layout.addWidget(process_label)

        if not result.analysis_trace:
            no_trace = QLabel("No process record available.")
            no_trace.setStyleSheet("color: #aaa;")
            self._process_layout.addWidget(no_trace)

        # Incomplete / degraded badge
        if getattr(result, "incomplete", False):
            reasons = getattr(result, "incomplete_reasons", []) or []
            detail = f"（{reasons[0]}）" if reasons else ""
            self._incomplete_label.setText(f"結果不完整，請以原圖為準{detail}")
            self._incomplete_label.setVisible(True)
        else:
            self._incomplete_label.setText("")
            self._incomplete_label.setVisible(False)

        # Manual-zoom hints (region too small in the screen capture).
        zoom_hints = getattr(result, "zoom_hints", []) or []
        if zoom_hints:
            self._zoom_hint_label.setText("\n".join(zoom_hints))
            self._zoom_hint_label.setVisible(True)
        else:
            self._zoom_hint_label.setText("")
            self._zoom_hint_label.setVisible(False)

        # Clinical consistency review flag (escalated, guideline-grounded).
        if getattr(result, "review_required", False):
            reasons = getattr(result, "review_reasons", []) or []
            body = "\n".join(f"• {r}" for r in reasons)
            self._review_label.setText(f"需人工複核\n{body}".rstrip())
            self._review_label.setVisible(True)
        else:
            self._review_label.setText("")
            self._review_label.setVisible(False)

    def clear(self) -> None:
        self._clear_layout(self._findings_layout)
        self._clear_layout(self._checklist_layout)
        self._clear_layout(self._process_layout)
        self._summary_label.setText("")
        self._title_label.setText("Waiting")


class ChatPanel(_DraggableWindowMixin, QWidget):
    """Draggable panel for displaying chat Q&A."""

    proposal_accepted = pyqtSignal()
    proposal_dismissed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_draggable_window()
        self.setFixedWidth(400)
        self.setStyleSheet(
            "background-color: rgba(20, 20, 30, 230); border-radius: 8px; padding: 8px;"
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
        self._question_label.setTextFormat(Qt.TextFormat.PlainText)
        self._question_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._question_label.setStyleSheet("color: #8cb4ff; padding: 4px 0;")
        layout.addWidget(self._question_label)

        # Answer (scrollable)
        self._answer_label = QLabel("")
        self._answer_label.setWordWrap(True)
        self._answer_label.setTextFormat(Qt.TextFormat.PlainText)
        self._answer_label.setFont(QFont("Segoe UI", 10))
        self._answer_label.setStyleSheet("color: #ddd;")
        self._answer_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
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

        self._proposal_label = QLabel("")
        self._proposal_label.setWordWrap(True)
        self._proposal_label.setTextFormat(Qt.TextFormat.PlainText)
        self._proposal_label.setStyleSheet(
            "color: #f2d27a; border-top: 1px solid #555; padding: 8px 0 4px 0;"
        )
        self._proposal_label.setVisible(False)
        layout.addWidget(self._proposal_label)

        self._proposal_actions = QWidget()
        action_layout = QHBoxLayout(self._proposal_actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        self._dismiss_proposal_btn = QPushButton("Dismiss")
        self._dismiss_proposal_btn.setToolTip("Keep the current report unchanged")
        self._dismiss_proposal_btn.clicked.connect(self._dismiss_proposal)
        action_layout.addWidget(self._dismiss_proposal_btn)
        self._apply_proposal_btn = QPushButton("Apply to report")
        self._apply_proposal_btn.setToolTip(
            "Apply this AI suggestion to the current report and audit trail"
        )
        self._apply_proposal_btn.setStyleSheet(
            "QPushButton { background: #2563a6; color: white; padding: 6px 10px; "
            "border: 1px solid #4f88c6; border-radius: 4px; }"
            "QPushButton:hover { background: #2f74bd; }"
        )
        self._apply_proposal_btn.clicked.connect(self._accept_proposal)
        action_layout.addWidget(self._apply_proposal_btn)
        self._proposal_actions.setVisible(False)
        layout.addWidget(self._proposal_actions)

    def show_chat(
        self,
        question: str,
        answer: str,
        *,
        proposal_summary: str = "",
    ) -> None:
        self._question_label.setText(f"Q: {question}")
        self._answer_label.setText(answer)
        self._set_proposal(proposal_summary)
        self.setVisible(True)

    def show_waiting(self, question: str) -> None:
        self._question_label.setText(f"Q: {question}")
        self._answer_label.setText("思考中…")
        self._set_proposal("")
        self.setVisible(True)

    def _set_proposal(self, summary: str) -> None:
        summary = summary.strip()
        self._proposal_label.setText(
            f"AI-suggested report update\n{summary}" if summary else ""
        )
        self._proposal_label.setVisible(bool(summary))
        self._proposal_actions.setVisible(bool(summary))

    def clear_proposal(self) -> None:
        self._set_proposal("")

    def _accept_proposal(self) -> None:
        self._set_proposal("")
        self.proposal_accepted.emit()

    def _dismiss_proposal(self) -> None:
        self._set_proposal("")
        self.proposal_dismissed.emit()

    def clear(self) -> None:
        self._question_label.setText("")
        self._answer_label.setText("")
        self._set_proposal("")
        self.setVisible(False)


class OverlayWindow(QWidget):
    """Main transparent overlay window (spec §3.4).

    Click-through except for summary panel and control bar.
    """

    display_expired = pyqtSignal()
    highlight_selected = pyqtSignal(str, float, float, float, float)
    user_region_created = pyqtSignal(float, float, float, float)
    chat_proposal_accepted = pyqtSignal()
    chat_proposal_dismissed = pyqtSignal()

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
        self.chat_panel.proposal_accepted.connect(self.chat_proposal_accepted.emit)
        self.chat_panel.proposal_dismissed.connect(self.chat_proposal_dismissed.emit)

        # Chat answers expire independently; the report and image markers persist.
        self._chat_timer = QTimer(self)
        self._chat_timer.setSingleShot(True)
        self._chat_timer.timeout.connect(self.chat_panel.clear)

        self._display_duration_sec = 30
        self._critical_persist = True
        self._current_severity = "normal"
        self._interaction_mode = "passive"
        self._content_rect: tuple[int, int, int, int] | None = None
        self._coordinate_frame: OverlayCoordinateFrame | None = None
        self._selection_start: QPoint | None = None
        self._draft_rect: tuple[int, int, int, int] | None = None
        self._user_regions: list[tuple[float, float, float, float]] = []

        # Region highlights to draw
        self._highlights: list[
            tuple[int, int, int, int, str, str]
        ] = []  # x, y, w, h, severity, label

    def set_interaction_mode(self, mode: str) -> None:
        """Switch between click-through, AI-box inspection, and user marking."""
        if mode not in {"passive", "inspect", "annotate"}:
            raise ValueError(f"Unknown overlay interaction mode: {mode}")
        self._interaction_mode = mode
        self._selection_start = None
        self._draft_rect = None
        self.setWindowFlag(
            Qt.WindowType.WindowTransparentForInput,
            mode == "passive",
        )
        self.setCursor(
            Qt.CursorShape.CrossCursor
            if mode == "annotate"
            else Qt.CursorShape.PointingHandCursor
            if mode == "inspect"
            else Qt.CursorShape.ArrowCursor
        )
        if self.isVisible():
            self.show()
        self.update()

    @property
    def user_regions(self) -> list[tuple[float, float, float, float]]:
        return list(self._user_regions)

    def clear_user_regions(self) -> None:
        """Clear reviewer-drawn regions at a new-image boundary."""

        self._user_regions.clear()

    def consume_user_region(
        self,
        region: RegionRect,
        *,
        tolerance: float = 1e-6,
    ) -> bool:
        """Remove a manual region promoted to a reviewer-confirmed finding."""

        target = (region.x, region.y, region.w, region.h)
        for index, values in enumerate(self._user_regions):
            if all(
                abs(actual - expected) <= tolerance
                for actual, expected in zip(values, target, strict=True)
            ):
                self._user_regions.pop(index)
                return True
        return False

    def configure(
        self,
        display_duration_sec: int = 30,
        critical_persist: bool = True,
    ) -> None:
        self._display_duration_sec = display_duration_sec
        self._critical_persist = critical_persist

    @property
    def coordinate_frame(self) -> OverlayCoordinateFrame | None:
        return self._coordinate_frame

    def position_over_window(
        self,
        rect: WindowRect,
        display_frame: DisplayFrame | None = None,
    ) -> OverlayCoordinateFrame:
        """Position the overlay over the display containing the viewer.

        The overlay spans the entire target screen so that the summary panel,
        chat panel, and region highlights are not clipped by the viewer window
        boundaries. The returned frame maps Win32 physical capture pixels to
        this widget's local Qt logical coordinates.
        """
        from PyQt6.QtWidgets import QApplication

        from dicom_overlay.infrastructure.overlay_geometry import (
            OverlayCoordinateFrame,
        )
        from dicom_overlay.presentation.screen_selection import (
            coordinate_frame_for_screen,
            select_qt_screen,
        )

        app = QApplication.instance()
        screen = select_qt_screen(app, display_frame) if app is not None else None
        if screen is None:
            from dicom_overlay.infrastructure.dpi import physical_to_logical

            logical = physical_to_logical(rect)
            self.setGeometry(logical.left, logical.top, logical.width, logical.height)
            frame = OverlayCoordinateFrame(
                physical_screen=rect,
                logical_screen=logical,
            )
        else:
            frame = coordinate_frame_for_screen(screen, display_frame)
            logical = frame.logical_screen
            self.setGeometry(
                logical.left,
                logical.top,
                logical.width,
                logical.height,
            )

        self._coordinate_frame = frame
        sw, sh = logical.width, logical.height
        screen_x, screen_y = logical.left, logical.top

        # Place summary panel on right side of screen
        panel_x = screen_x + sw - self.summary_panel.width() - 10
        self.summary_panel.move(panel_x, screen_y + 10)
        self.summary_panel.setFixedHeight(sh - 70)

        # Place chat panel on left side of screen
        self.chat_panel.move(screen_x + 10, screen_y + 10)
        self.chat_panel.setFixedHeight(sh - 70)
        return frame

    def show_result(
        self,
        result: AnalysisResult,
        highlights: list[tuple[int, int, int, int, str, str]] | None = None,
        *,
        append: bool = False,
        content_rect: tuple[int, int, int, int] | None = None,
    ) -> None:
        """Show analysis result on overlay.

        When ``append`` is ``False`` (default) the highlight set is replaced,
        preserving the original single-shot behavior. When ``True`` the existing
        highlights are kept and ``highlights`` is appended; the caller (the
        application-layer accumulator) is responsible for feeding an already
        deduplicated, non-overlapping set so the overlay never decides merges.
        """
        self.summary_panel.update_result(result)
        self.summary_panel.setVisible(True)
        self._current_severity = result.severity.value
        if content_rect is not None:
            self._content_rect = content_rect
        if append:
            self._highlights = [*self._highlights, *(highlights or [])]
        else:
            self._highlights = highlights or []

        self.setWindowOpacity(1.0)
        self.show()
        self.update()

        # Results persist until dismissed or new image triggers a new analysis.
        # No auto-hide timer.

    def clear_result(self) -> None:
        self.summary_panel.clear()
        self._highlights.clear()
        self._user_regions.clear()
        self._content_rect = None
        self.clear_chat()
        self.update()

    def show_chat_waiting(self, question: str) -> None:
        """Show chat panel with 'thinking' placeholder."""
        self._chat_timer.stop()
        self.chat_panel.show_waiting(question)
        self.setWindowOpacity(1.0)
        self.show()

    def show_chat_response(
        self,
        question: str,
        answer: str,
        *,
        proposal_summary: str = "",
    ) -> None:
        """Show chat Q&A on overlay."""
        self.chat_panel.show_chat(
            question,
            answer,
            proposal_summary=proposal_summary,
        )
        self.setWindowOpacity(1.0)
        self.show()
        # A pending report update must stay available for an explicit decision.
        if proposal_summary:
            self._chat_timer.stop()
        else:
            self._chat_timer.start(self._display_duration_sec * 1000)

    def clear_chat_proposal(self, *, restart_timeout: bool = False) -> None:
        """Remove pending proposal controls after apply, dismiss, or image change."""

        self.chat_panel.clear_proposal()
        if restart_timeout and self.chat_panel.isVisible():
            self._chat_timer.start(self._display_duration_sec * 1000)

    def clear_chat(self) -> None:
        """Dismiss only chat state, preserving the current report and boxes."""

        self._chat_timer.stop()
        self.chat_panel.clear()

    def _fade_out(self) -> None:
        self._chat_timer.stop()
        self.setWindowOpacity(0.0)
        self.summary_panel.setVisible(False)
        self.chat_panel.clear()
        self._highlights.clear()
        self._user_regions.clear()
        self._content_rect = None
        self.set_interaction_mode("passive")
        self.update()
        self.display_expired.emit()

    def dismiss(self) -> None:
        self._chat_timer.stop()
        self._fade_out()

    def _point_in_content(self, point: QPoint) -> bool:
        if self._content_rect is None:
            return False
        x, y, width, height = self._content_rect
        return x <= point.x() <= x + width and y <= point.y() <= y + height

    def _normalized_rect(
        self,
        rect: tuple[int, int, int, int],
    ) -> tuple[float, float, float, float] | None:
        if self._content_rect is None:
            return None
        content_x, content_y, content_w, content_h = self._content_rect
        if content_w <= 0 or content_h <= 0:
            return None
        x, y, width, height = rect
        left = max(content_x, min(content_x + content_w, x))
        top = max(content_y, min(content_y + content_h, y))
        right = max(content_x, min(content_x + content_w, x + width))
        bottom = max(content_y, min(content_y + content_h, y + height))
        if right - left < 2 or bottom - top < 2:
            return None
        return (
            (left - content_x) / content_w,
            (top - content_y) / content_h,
            (right - left) / content_w,
            (bottom - top) / content_h,
        )

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is None or event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position().toPoint()
        if self._interaction_mode == "inspect":
            for highlight in reversed(self._highlights):
                x, y, width, height, _severity, label = highlight
                if x <= point.x() <= x + width and y <= point.y() <= y + height:
                    normalized = self._normalized_rect((x, y, width, height))
                    if normalized is not None:
                        self.highlight_selected.emit(label, *normalized)
                    event.accept()
                    return
        if self._interaction_mode == "annotate" and self._point_in_content(point):
            self._selection_start = point
            self._draft_rect = (point.x(), point.y(), 0, 0)
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is None or self._selection_start is None:
            return
        point = event.position().toPoint()
        x0 = min(self._selection_start.x(), point.x())
        y0 = min(self._selection_start.y(), point.y())
        x1 = max(self._selection_start.x(), point.x())
        y1 = max(self._selection_start.y(), point.y())
        self._draft_rect = (x0, y0, x1 - x0, y1 - y0)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event is None or self._selection_start is None:
            return
        draft = self._draft_rect
        self._selection_start = None
        self._draft_rect = None
        if draft is not None:
            normalized = self._normalized_rect(draft)
            if normalized is not None:
                content_x, content_y, content_w, content_h = self._content_rect or (
                    0,
                    0,
                    0,
                    0,
                )
                nx, ny, nw, nh = normalized
                clipped = (
                    round(content_x + nx * content_w),
                    round(content_y + ny * content_h),
                    round(nw * content_w),
                    round(nh * content_h),
                    "info",
                    "User region",
                )
                self._highlights.append(clipped)
                self._user_regions.append(normalized)
                self.user_region_created.emit(*normalized)
        self.update()
        event.accept()

    def paintEvent(self, a0: object) -> None:
        """Draw region highlights with labels (spec §3.4)."""
        del a0
        if not self._highlights and self._draft_rect is None:
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
                bg = QColor(0, 0, 0, 180)
                metrics = painter.fontMetrics()
                available = max(80, min(320, self.width() - x - 8))
                visible_label = metrics.elidedText(
                    label,
                    Qt.TextElideMode.ElideRight,
                    available,
                )
                text_rect = metrics.boundingRect(visible_label)
                text_x = max(2, min(x + 4, self.width() - text_rect.width() - 6))
                text_y = max(text_rect.height() + 2, y - 2)
                painter.fillRect(
                    text_x - 2,
                    text_y - text_rect.height(),
                    text_rect.width() + 6,
                    text_rect.height() + 4,
                    bg,
                )
                painter.setPen(QPen(color, 1))
                painter.drawText(text_x, text_y, visible_label)

        if self._draft_rect is not None:
            x, y, width, height = self._draft_rect
            draft_pen = QPen(QColor(84, 199, 255, 230), 2, Qt.PenStyle.DashLine)
            painter.setPen(draft_pen)
            painter.drawRect(x, y, width, height)

        painter.end()


# ── Checklist display helpers ──

_KEY_DISPLAY_MAP: dict[str, str] = {
    # EKG - 16-point systematic checklist
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
