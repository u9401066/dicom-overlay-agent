"""Select the Qt screen that represents a Win32 physical display."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from dicom_overlay.domain.entities import DisplayFrame, WindowRect
from dicom_overlay.infrastructure.overlay_geometry import OverlayCoordinateFrame

if TYPE_CHECKING:
    from PyQt6.QtGui import QScreen
    from PyQt6.QtWidgets import QApplication


def select_qt_screen(
    app: QApplication, display_frame: DisplayFrame | None
) -> QScreen | None:
    """Return the closest Qt screen for a physical Win32 display descriptor."""
    screens = list(app.screens())
    if not screens:
        return None
    primary = app.primaryScreen()
    if display_frame is None:
        return primary or screens[0]
    if display_frame.is_primary and primary is not None:
        return primary

    ranked = sorted(
        enumerate(screens),
        key=lambda item: _screen_match_score(
            screen=item[1],
            qt_index=item[0],
            primary=primary,
            display_frame=display_frame,
        ),
    )
    return ranked[0][1]


def coordinate_frame_for_screen(
    screen: QScreen,
    display_frame: DisplayFrame | None,
) -> OverlayCoordinateFrame:
    """Build exact local mapping, with a single-screen DPR fallback."""
    geometry = screen.geometry()
    logical = WindowRect(
        left=geometry.x(),
        top=geometry.y(),
        width=geometry.width(),
        height=geometry.height(),
    )
    if display_frame is not None:
        physical = display_frame.physical_rect
    else:
        dpr = float(screen.devicePixelRatio())
        physical = WindowRect(
            left=round(geometry.x() * dpr),
            top=round(geometry.y() * dpr),
            width=round(geometry.width() * dpr),
            height=round(geometry.height() * dpr),
        )
    return OverlayCoordinateFrame(
        physical_screen=physical,
        logical_screen=logical,
    )


def _screen_match_score(
    *,
    screen: QScreen,
    qt_index: int,
    primary: QScreen | None,
    display_frame: DisplayFrame,
) -> float:
    geometry = screen.geometry()
    dpr = float(screen.devicePixelRatio())
    physical_width = round(geometry.width() * dpr)
    physical_height = round(geometry.height() * dpr)
    target = display_frame.physical_rect

    score = (
        abs(physical_width - target.width) / max(1, target.width)
        + abs(physical_height - target.height) / max(1, target.height)
    ) * 100.0
    if (screen is primary) != display_frame.is_primary:
        score += 1000.0
    if qt_index != display_frame.monitor_index:
        score += 2.0
    if _origin_sign(geometry.x()) != _origin_sign(target.left):
        score += 4.0
    if _origin_sign(geometry.y()) != _origin_sign(target.top):
        score += 4.0

    qt_name = _normalize_display_name(screen.name())
    win_name = _normalize_display_name(display_frame.device_name)
    if qt_name and win_name and (qt_name == win_name or qt_name.endswith(win_name)):
        score -= 10_000.0
    return score


def _normalize_display_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _origin_sign(value: int) -> int:
    return -1 if value < 0 else 1 if value > 0 else 0
