"""Keep app-owned overlay windows out of medical-image screen captures."""

from __future__ import annotations

import ctypes
import platform
import sys
from ctypes import wintypes
from typing import TYPE_CHECKING

import structlog
from PyQt6.QtGui import QGuiApplication

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

logger = structlog.get_logger(__name__)

_WINDOWS_10_2004_BUILD = 19041
_WDA_EXCLUDEFROMCAPTURE = 0x00000011


def _windows_build_number(version: str | None = None) -> int:
    text = version if version is not None else platform.win32_ver()[1]
    try:
        return int(text.rsplit(".", 1)[-1])
    except (TypeError, ValueError):
        return 0


def capture_exclusion_supported(
    *,
    platform_name: str | None = None,
    windows_version: str | None = None,
    qt_platform_name: str | None = None,
) -> bool:
    """Return whether transparent exclusion is available on this Qt runtime."""

    current_platform = platform_name or sys.platform
    if current_platform != "win32":
        return False
    qt_platform = qt_platform_name or QGuiApplication.platformName()
    if qt_platform and qt_platform.lower() != "windows":
        return False
    return _windows_build_number(windows_version) >= _WINDOWS_10_2004_BUILD


def protect_widget_from_capture(widget: QWidget) -> bool:
    """Apply Windows capture exclusion to one top-level app window.

    Windows 10 versions before 2004 interpret the flag as ``WDA_MONITOR`` and
    can replace a transparent overlay with an opaque block in captures. We
    therefore enable it only where ``WDA_EXCLUDEFROMCAPTURE`` is supported.
    """

    if not capture_exclusion_supported():
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        setter = user32.SetWindowDisplayAffinity
        setter.argtypes = [wintypes.HWND, wintypes.DWORD]
        setter.restype = wintypes.BOOL
        hwnd = wintypes.HWND(int(widget.winId()))
        if not setter(hwnd, _WDA_EXCLUDEFROMCAPTURE):
            logger.warning(
                "overlay_capture_exclusion_failed",
                widget=type(widget).__name__,
                winerror=ctypes.get_last_error(),
            )
            return False
    except (AttributeError, OSError, TypeError, ValueError):
        logger.exception(
            "overlay_capture_exclusion_failed",
            widget=type(widget).__name__,
        )
        return False
    return True
