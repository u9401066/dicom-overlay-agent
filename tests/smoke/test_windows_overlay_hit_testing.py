"""Real Win32 hit testing: Qt-injected mouse events cannot detect alpha holes."""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

import pytest
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QApplication, QWidget

from dicom_overlay.presentation.overlay_window import OverlayWindow


@pytest.mark.skipif(sys.platform != "win32", reason="Windows layered-window behavior")
def test_native_mark_drag_starts_in_unmarked_roi_and_passive_mode_passes_through():
    if os.environ.get("DICOM_RUN_WINDOWS_INPUT_SMOKE") != "1":
        pytest.skip("set DICOM_RUN_WINDOWS_INPUT_SMOKE=1 for native mouse smoke")
    app = QApplication.instance() or QApplication([])
    if app.platformName().lower() != "windows":
        pytest.skip("native Windows Qt platform is required")
    native = ctypes.windll.user32
    native.SetThreadDpiAwarenessContext.argtypes = [wintypes.HANDLE]
    native.SetThreadDpiAwarenessContext.restype = wintypes.HANDLE
    previous_dpi_context = native.SetThreadDpiAwarenessContext(-4)
    native.WindowFromPoint.argtypes = [wintypes.POINT]
    native.WindowFromPoint.restype = wintypes.HWND
    native.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    native.SetForegroundWindow.argtypes = [wintypes.HWND]
    base = QWidget()
    base.setWindowFlags(Qt.WindowType.FramelessWindowHint)
    base.setGeometry(300, 150, 300, 200)
    base.setStyleSheet("background: #6d8678;")
    overlay = OverlayWindow()
    overlay.setGeometry(base.geometry())
    overlay._content_rect = (30, 20, 200, 120)
    created = []
    observed = []

    class MouseObserver(QObject):
        def eventFilter(self, watched, event):
            if event.type() in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonRelease,
            ):
                observed.append(
                    (type(watched).__name__, event.position().x(), event.position().y())
                )
            return False

    observer = MouseObserver()
    app.installEventFilter(observer)
    overlay.user_region_created.connect(lambda *region: created.append(region))
    cursor = wintypes.POINT()
    assert native.GetCursorPos(ctypes.byref(cursor))

    def settle():
        for _ in range(5):
            app.processEvents()
            time.sleep(0.02)

    def point(x, y):
        rect = wintypes.RECT()
        assert native.GetWindowRect(int(overlay.winId()), ctypes.byref(rect))
        ratio = overlay.devicePixelRatioF()
        return wintypes.POINT(rect.left + round(x * ratio), rect.top + round(y * ratio))

    try:
        base.show()
        base.raise_()
        base.activateWindow()
        native.SetForegroundWindow(int(base.winId()))
        settle()
        overlay.show()
        overlay.set_interaction_mode("annotate")
        overlay.raise_()
        settle()
        start, end = point(80, 50), point(160, 100)
        # No findings, no draft, no manually painted marker under this point.
        assert overlay._highlights == []
        assert native.WindowFromPoint(start) == int(overlay.winId())
        assert native.WindowFromPoint(point(5, 5)) != int(overlay.winId())
        native.SetCursorPos(start.x, start.y)
        settle()
        native.mouse_event(2, 0, 0, 0, 0)
        settle()
        actual = wintypes.POINT()
        native.GetCursorPos(ctypes.byref(actual))
        assert overlay._selection_start is not None, (
            observed,
            (start.x, start.y),
            (actual.x, actual.y),
            overlay.geometry(),
        )
        native.SetCursorPos(end.x, end.y)
        settle()
        native.mouse_event(4, 0, 0, 0, 0)
        settle()
        assert created == [pytest.approx((0.25, 0.25, 0.4, 50 / 120))]

        overlay.set_interaction_mode("passive")
        settle()
        assert native.WindowFromPoint(start) != int(overlay.winId())
        overlay.set_interaction_mode("annotate")
        settle()
        assert native.WindowFromPoint(point(210, 110)) == int(overlay.winId())
        assert overlay.user_regions == created
    finally:
        native.mouse_event(4, 0, 0, 0, 0)
        native.SetCursorPos(cursor.x, cursor.y)
        overlay.close()
        app.removeEventFilter(observer)
        overlay.summary_panel.close()
        overlay.chat_panel.close()
        base.close()
        app.processEvents()
        native.SetThreadDpiAwarenessContext(previous_dpi_context)
