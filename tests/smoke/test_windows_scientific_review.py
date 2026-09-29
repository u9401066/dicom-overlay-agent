"""Native review panel with synthetic content, not a live model/App acceptance."""

from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from hashlib import sha256
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication
from tests.unit.test_contract_assembly import inputs as inputs
from tests.unit.test_scientific_review_presentation import prepared as prepared
from tests.unit.test_scientific_review_presentation import pump

from dicom_overlay.infrastructure.async_bridge import AsyncBridge
from dicom_overlay.presentation.scientific_review import (
    QtReviewPresenter,
    ScientificReviewPanel,
)


@pytest.mark.skipif(
    sys.platform != "win32", reason="Native Windows review presentation"
)
def test_native_review_paints_then_closes_via_actual_mouse(prepared, tmp_path):
    if os.environ.get("DICOM_RUN_WINDOWS_REVIEW_SMOKE") != "1":
        pytest.skip("set DICOM_RUN_WINDOWS_REVIEW_SMOKE=1 for visible native review")
    app = QApplication.instance() or QApplication([])
    if app.platformName().lower() != "windows":
        pytest.skip("native Windows Qt platform is required")
    app.setQuitOnLastWindowClosed(False)
    native = ctypes.windll.user32
    native.SetThreadDpiAwarenessContext.argtypes = [wintypes.HANDLE]
    native.SetThreadDpiAwarenessContext.restype = wintypes.HANDLE
    previous = native.SetThreadDpiAwarenessContext(-4)
    native.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    native.SetForegroundWindow.argtypes = [wintypes.HWND]
    cursor = wintypes.POINT()
    assert native.GetCursorPos(ctypes.byref(cursor))
    panel = ScientificReviewPanel()
    panel.move(180, 60)
    scope = ("a" * 32, prepared.result.input_provenance.source_image_sha256)
    presenter = QtReviewPresenter(panel, lambda run, source: (run, source) == scope)
    worker = AsyncBridge()
    worker.start()
    revoked = []
    presenter.invalidated.connect(revoked.append)
    output = Path(os.environ.get("DICOM_SCIENTIFIC_REVIEW_ARTIFACTS", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    try:
        future = worker.submit(presenter(scope[0], prepared))
        pump(app, future.done)
        receipt = json.loads(future.result())
        assert receipt["available"] is True and presenter._active.painted
        panel.activateWindow()
        native.SetForegroundWindow(int(panel.winId()))
        screenshots = {}
        for index, name in ((0, "report"), (3, "observations"), (4, "evidence")):
            panel._tabs.setCurrentIndex(index)
            app.processEvents()
            path = output / f"{name}.png"
            # Only this owned synthetic widget, never the unrestricted desktop.
            assert panel.grab().save(str(path), "PNG")
            screenshots[name] = sha256(path.read_bytes()).hexdigest()
        button = panel._close_button
        rect = wintypes.RECT()
        assert native.GetWindowRect(int(panel.winId()), ctypes.byref(rect))
        center = button.mapTo(panel, button.rect().center())
        ratio = panel.devicePixelRatioF()
        native.SetCursorPos(
            rect.left + round(center.x() * ratio), rect.top + round(center.y() * ratio)
        )
        native.mouse_event(2, 0, 0, 0, 0)
        native.mouse_event(4, 0, 0, 0, 0)
        pump(app, lambda: not panel.isVisible())
        assert revoked == [scope[0]] and not panel.content_sha256
        assert (
            not panel._observations.toPlainText() and not panel._evidence.toPlainText()
        )
        (output / "receipt.json").write_text(
            json.dumps(
                {
                    "synthetic_content": True,
                    "whole_app_or_model_acceptance": False,
                    "availability": receipt,
                    "device_pixel_ratio": ratio,
                    "screenshots_sha256": screenshots,
                    "native_close_revoked": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        native.mouse_event(4, 0, 0, 0, 0)
        native.SetCursorPos(cursor.x, cursor.y)
        panel.hide()
        worker.shutdown()
        panel.close()
        app.processEvents()
        native.SetThreadDpiAwarenessContext(previous)
