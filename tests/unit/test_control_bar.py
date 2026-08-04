from __future__ import annotations

from dicom_overlay.domain.entities import TriggerMode
from dicom_overlay.presentation.control_bar import ControlBarWindow


def test_control_bar_shows_hybrid_mode_and_pending_analysis(qtbot):
    bar = ControlBarWindow()
    qtbot.addWidget(bar)

    bar.set_trigger_mode(TriggerMode.HYBRID)
    bar.set_pending_analysis(True)

    assert bar.current_trigger_mode == TriggerMode.HYBRID
    assert "Hybrid" in bar._mode_btn.text()
    assert "Analyze" in bar._analyze_btn.text()
    assert bar._analyze_btn.property("pending") is True


def test_control_bar_mode_button_cycles_modes(qtbot):
    bar = ControlBarWindow()
    qtbot.addWidget(bar)
    seen: list[TriggerMode] = []
    bar.trigger_mode_changed.connect(seen.append)

    bar.set_trigger_mode(TriggerMode.HYBRID)
    bar._mode_btn.click()
    bar._mode_btn.click()
    bar._mode_btn.click()

    assert seen == [TriggerMode.AUTO, TriggerMode.MANUAL, TriggerMode.HYBRID]
    assert bar.current_trigger_mode == TriggerMode.HYBRID


def test_control_bar_positions_inside_offset_screen(qtbot):
    bar = ControlBarWindow()
    qtbot.addWidget(bar)

    bar.position_bottom_right(1920, 1080, screen_left=-1920, screen_top=40)

    assert bar.x() == -20 - bar.width()
    assert bar.y() == 40 + 1080 - bar.height() - 60
