from __future__ import annotations

from dicom_overlay.domain.entities import DisplayFrame, WindowRect
from dicom_overlay.presentation.screen_selection import (
    coordinate_frame_for_screen,
    select_qt_screen,
)


class _Geometry:
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self._values = (x, y, width, height)

    def x(self) -> int:
        return self._values[0]

    def y(self) -> int:
        return self._values[1]

    def width(self) -> int:
        return self._values[2]

    def height(self) -> int:
        return self._values[3]


class _Screen:
    def __init__(
        self,
        name: str,
        geometry: _Geometry,
        dpr: float,
    ) -> None:
        self._name = name
        self._geometry = geometry
        self._dpr = dpr

    def name(self) -> str:
        return self._name

    def geometry(self) -> _Geometry:
        return self._geometry

    def devicePixelRatio(self) -> float:
        return self._dpr


class _App:
    def __init__(self, screens: list[_Screen], primary: _Screen) -> None:
        self._screens = screens
        self._primary = primary

    def screens(self) -> list[_Screen]:
        return self._screens

    def primaryScreen(self) -> _Screen:
        return self._primary


def test_select_qt_screen_matches_secondary_monitor_index_and_geometry() -> None:
    primary = _Screen("internal", _Geometry(0, 0, 2048, 1152), 1.25)
    secondary = _Screen("external", _Geometry(-1920, 0, 1920, 1080), 1.0)
    app = _App([primary, secondary], primary)
    display = DisplayFrame(
        physical_rect=WindowRect(-1920, 0, 1920, 1080),
        device_name=r"\\.\DISPLAY2",
        monitor_index=1,
        is_primary=False,
    )

    assert select_qt_screen(app, display) is secondary  # type: ignore[arg-type]


def test_coordinate_frame_uses_win32_physical_and_qt_logical_bounds() -> None:
    screen = _Screen("external", _Geometry(-1536, 0, 1536, 864), 1.25)
    display = DisplayFrame(
        physical_rect=WindowRect(-1920, 0, 1920, 1080),
        monitor_index=1,
    )

    frame = coordinate_frame_for_screen(screen, display)  # type: ignore[arg-type]

    assert frame.physical_screen == display.physical_rect
    assert frame.logical_screen == WindowRect(-1536, 0, 1536, 864)
