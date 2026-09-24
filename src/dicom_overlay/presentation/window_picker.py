"""Explicit, session-local selection of an external image window."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QWidget

    from dicom_overlay.domain.entities import CaptureWindow


class WindowPickerDialog(QDialog):
    def __init__(
        self,
        load_windows: Callable[[], list[CaptureWindow]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose image window")
        self.resize(660, 420)
        self._load_windows = load_windows
        layout = QVBoxLayout(self)
        explanation = QLabel(
            "選擇瀏覽器或影像軟體視窗，再重新框選不含個資的 ROI。\n"
            "僅套用於本次啟動；視窗關閉後不會自動改抓其他視窗。"
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self._windows = QListWidget()
        self._windows.setObjectName("captureWindowChoices")
        self._windows.currentItemChanged.connect(self._selection_changed)
        layout.addWidget(self._windows)
        self._status = QLabel("")
        layout.addWidget(self._status)
        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        buttons.addWidget(refresh)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self._use = QPushButton("Use selected window")
        self._use.setObjectName("useCaptureWindow")
        self._use.clicked.connect(self.accept)
        buttons.addWidget(self._use)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self) -> None:
        self._windows.clear()
        self._use.setEnabled(False)
        try:
            windows = self._load_windows()
        except Exception:
            self._status.setText("無法列出視窗，請重試；未更改擷取目標。")
            return
        for choice in windows:
            item = QListWidgetItem(f"{choice.title}  [PID {choice.process_id}]")
            item.setData(Qt.ItemDataRole.UserRole, choice)
            self._windows.addItem(item)
        self._status.setText(
            "請先點選影像視窗。" if windows else "請先開啟影像視窗，再按 Refresh。"
        )

    def _selection_changed(self, *_args: object) -> None:
        self._use.setEnabled(self.selected_window() is not None)

    def selected_window(self) -> CaptureWindow | None:
        item = self._windows.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None
