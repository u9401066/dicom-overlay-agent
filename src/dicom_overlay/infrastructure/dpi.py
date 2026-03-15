"""DPI scaling utilities for coordinate conversion between Win32 and Qt.

Win32 `GetWindowRect` returns physical pixels (after Qt6 sets DPI awareness).
Qt widgets (`setGeometry`, `QScreen::geometry`) use logical pixels.
This module provides conversion helpers to bridge the two coordinate systems.
"""

from __future__ import annotations

import structlog
from PyQt6.QtWidgets import QApplication

from dicom_overlay.domain.entities import WindowRect

logger = structlog.get_logger(__name__)

_cached_dpr: float | None = None


def get_dpi_scale() -> float:
    """Return the primary screen's device-pixel-ratio (physical / logical).

    Returns 1.0 if no screen is available or detection fails.
    The result is cached after first successful call.
    """
    global _cached_dpr
    if _cached_dpr is not None:
        return _cached_dpr

    app = QApplication.instance()
    if app is None:
        return 1.0

    screen = QApplication.primaryScreen()
    if screen is None:
        return 1.0

    dpr = screen.devicePixelRatio()
    _cached_dpr = dpr
    if dpr != 1.0:
        logger.info("DPI scale detected: %.2f", dpr)
    return dpr


def physical_to_logical(rect: WindowRect) -> WindowRect:
    """Convert physical-pixel WindowRect to Qt logical-pixel WindowRect."""
    dpr = get_dpi_scale()
    if dpr == 1.0:
        return rect
    return WindowRect(
        left=round(rect.left / dpr),
        top=round(rect.top / dpr),
        width=round(rect.width / dpr),
        height=round(rect.height / dpr),
    )


def physical_to_logical_roi(top: int, bottom: int, left: int, right: int) -> tuple[int, int, int, int]:
    """Convert ROI crop margins from physical to logical pixels."""
    dpr = get_dpi_scale()
    if dpr == 1.0:
        return top, bottom, left, right
    return round(top / dpr), round(bottom / dpr), round(left / dpr), round(right / dpr)


def logical_to_physical_roi(top: int, bottom: int, left: int, right: int) -> tuple[int, int, int, int]:
    """Convert ROI crop margins from logical to physical pixels."""
    dpr = get_dpi_scale()
    if dpr == 1.0:
        return top, bottom, left, right
    return round(top * dpr), round(bottom * dpr), round(left * dpr), round(right * dpr)
