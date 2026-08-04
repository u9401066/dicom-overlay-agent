from __future__ import annotations

import os
import sys
import time

import mss
import pytest
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget

from dicom_overlay.presentation.capture_safety import protect_widget_from_capture


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only capture API")
def test_overlay_is_absent_from_real_desktop_capture() -> None:
    if os.environ.get("DICOM_RUN_WINDOWS_CAPTURE_SMOKE") != "1":
        pytest.skip("set DICOM_RUN_WINDOWS_CAPTURE_SMOKE=1 for rendered capture smoke")

    app = QApplication.instance() or QApplication([])
    if app.platformName().lower() != "windows":
        pytest.skip("native Windows Qt platform is required")

    base = QWidget()
    base.setGeometry(240, 180, 420, 260)
    base.setStyleSheet("background: rgb(20, 180, 70);")
    overlay = QWidget()
    overlay.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.Tool
    )
    overlay.setGeometry(300, 230, 180, 120)
    overlay.setStyleSheet("background: rgb(240, 20, 180);")

    try:
        base.show()
        overlay.show()
        app.processEvents()
        assert protect_widget_from_capture(overlay)
        app.processEvents()
        time.sleep(0.25)

        with mss.mss() as capturer:
            shot = capturer.grab(
                {"left": 240, "top": 180, "width": 420, "height": 260}
            )
        captured = Image.frombytes("RGB", shot.size, shot.rgb)
        colors = captured.getcolors(maxcolors=420 * 260) or []
        magenta_pixels = sum(
            count
            for count, (red, green, blue) in colors
            if red > 220 and green < 60 and blue > 140
        )
        underlay_pixels = sum(
            count
            for count, (red, green, blue) in colors
            if green > 140 and red < 80 and blue < 110
        )

        assert magenta_pixels == 0
        assert underlay_pixels > 20_000
    finally:
        overlay.close()
        base.close()
        app.processEvents()
