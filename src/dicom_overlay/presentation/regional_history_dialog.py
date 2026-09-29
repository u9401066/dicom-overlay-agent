"""Explicit, local-only history selection; no inference or report writeback."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dicom_overlay.application.regional_conversation import (
    ArchivedConversation,
    RegionalThread,
)
from dicom_overlay.infrastructure.regional_history_io import load_regional_history
from dicom_overlay.presentation.capture_safety import protect_widget_from_capture


class RegionalHistoryDialog(QDialog):
    def __init__(
        self,
        *,
        image_base64: str,
        threads: list[RegionalThread],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("區域對話歷史 / Regional history")
        self.resize(720, 700)
        self.selected_history: ArchivedConversation | None = None
        raw = base64.b64decode(image_base64, validate=True)
        self._digest = hashlib.sha256(raw).hexdigest()
        self._image = QImage.fromData(raw)
        self._choices: list[tuple[ArchivedConversation, RegionalThread]] = [
            (thread.history, thread) for thread in threads if thread.history is not None
        ]
        layout = QVBoxLayout(self)
        notice = QLabel(
            "僅接受完全相同的原始 ROI 影像。歷史不是目前報告的證據。\n"
            "先載入 regional-conversations.json，再選區域；開啟不會呼叫 AI。\n"
            "續問僅供問答；要變更報告，請回到目前影像的 Inspect / Mark。"
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self._list = QListWidget()
        self._list.setObjectName("regionalHistoryList")
        self._list.currentRowChanged.connect(self._select)
        layout.addWidget(self._list)
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._preview)
        self._transcript = QPlainTextEdit()
        self._transcript.setReadOnly(True)
        self._transcript.setObjectName("regionalHistoryTranscript")
        layout.addWidget(self._transcript, 1)
        row = QHBoxLayout()
        load = QPushButton("載入歷史檔… / Load…")
        load.setObjectName("loadRegionalHistory")
        load.clicked.connect(self._load)
        row.addWidget(load)
        self._open = QPushButton("開啟並續問 / Open conversation")
        self._open.setObjectName("openRegionalHistory")
        self._open.setEnabled(False)
        self._open.clicked.connect(self._accept_selection)
        row.addWidget(self._open)
        close = QPushButton("取消 / Cancel")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        layout.addLayout(row)
        self._refresh()
        protect_widget_from_capture(self)

    def _refresh(self) -> None:
        self._list.clear()
        for index, (history, thread) in enumerate(self._choices, 1):
            region = history.region
            self._list.addItem(
                f"{index}. {'AI 標記歷史' if history.finding_id else '人工區域歷史'} · "
                f"{len(thread.all_turns)} 輪 · "
                f"ROI ({region.x:.3f}, {region.y:.3f}, {region.w:.3f}, {region.h:.3f})"
            )
        if self._choices:
            self._list.setCurrentRow(0)

    def _select(self, index: int) -> None:
        self._open.setEnabled(0 <= index < len(self._choices))
        self._transcript.clear()
        self._preview.clear()
        if not 0 <= index < len(self._choices):
            return
        history, thread = self._choices[index]
        self._transcript.setPlainText(thread.transcript())
        if self._image.isNull():
            return
        pixmap = QPixmap.fromImage(self._image).scaled(
            660,
            200,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor("#ef9b20"), 2))
        region = history.region
        painter.drawRect(
            QRectF(
                region.x * pixmap.width(),
                region.y * pixmap.height(),
                region.w * pixmap.width(),
                region.h * pixmap.height(),
            )
        )
        painter.end()
        self._preview.setPixmap(pixmap)

    def _load(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "載入區域對話歷史", "", "Regional history (*.json)"
        )
        if not filename:
            return
        try:
            histories = load_regional_history(
                Path(filename), source_image_sha256=self._digest
            )
        except (OSError, ValueError):
            # No arbitrary file contents, path or parser payload in logs/dialogs.
            QMessageBox.warning(
                self,
                "無法載入歷史",
                "檔案不相容、超過限制，或原始 ROI 影像不同。"
                "請使用同一張原始影像匯出的 regional-conversations.json。",
            )
            return
        known = {history.archive_id for history, _ in self._choices}
        combined = {history.archive_id: history for history, _ in self._choices}
        combined.update({history.archive_id: history for history in histories})
        if (
            len(combined) > 64
            or sum(len(history.turns) for history in combined.values()) > 512
            or sum(
                len(
                    json.dumps(history.to_payload(), ensure_ascii=False).encode("utf-8")
                )
                for history in combined.values()
            )
            > 4 * 1024 * 1024
        ):
            QMessageBox.warning(
                self, "歷史數量超過限制", "一次最多開啟 64 區、512 輪、4 MiB 的歷史。"
            )
            return
        for history in histories:
            if history.archive_id not in known:
                self._choices.append(
                    (history, RegionalThread(history.region, "", history=history))
                )
                known.add(history.archive_id)
        self._refresh()

    def _accept_selection(self) -> None:
        index = self._list.currentRow()
        if 0 <= index < len(self._choices):
            self.selected_history = self._choices[index][0]
            self.accept()
