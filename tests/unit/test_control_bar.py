from __future__ import annotations

import pytest

from dicom_overlay.domain.entities import AgentState, TriggerMode
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


def test_control_bar_exposes_separate_gateway_status(qtbot):
    bar = ControlBarWindow()
    qtbot.addWidget(bar)

    bar.set_gateway_status("ready")
    assert bar._gateway_status_label.text() == "AI ready"

    bar.set_gateway_status("offline")
    assert bar._gateway_status_label.text() == "AI offline"


@pytest.mark.parametrize("gateway_first", [True, False])
def test_analyze_requires_both_startup_completion_and_viewer_state(
    qtbot, gateway_first
):
    bar = ControlBarWindow()
    qtbot.addWidget(bar)
    calls = []
    bar.retrigger_clicked.connect(lambda: calls.append("analyze"))
    assert not bar._analyze_btn.isEnabled()
    assert bar.analysis_unavailable_reason
    bar._emit_analyze()
    assert calls == []
    if gateway_first:
        bar.set_gateway_status("ready")
    else:
        bar.update_state(AgentState.MONITORING)
    assert not bar._analyze_btn.isEnabled()
    if gateway_first:
        bar.update_state(AgentState.MONITORING)
    else:
        bar.set_gateway_status("ready")
    assert bar._analyze_btn.isEnabled()
    assert not bar.analysis_unavailable_reason
    bar._analyze_btn.click()
    assert calls == ["analyze"]


@pytest.mark.parametrize(
    "state",
    [
        AgentState.INIT,
        AgentState.WAITING,
        AgentState.SETUP,
        AgentState.CAPTURING,
        AgentState.ANALYZING,
        AgentState.RECONNECTING,
    ],
)
def test_unavailable_analysis_never_emits_or_loses_pending_label(qtbot, state):
    bar = ControlBarWindow()
    qtbot.addWidget(bar)
    bar.set_gateway_status("ready")
    bar.update_state(state)
    bar.set_pending_analysis(True)
    calls = []
    bar.retrigger_clicked.connect(lambda: calls.append("analyze"))
    bar._analyze_btn.click()
    bar._emit_analyze()
    assert calls == []
    assert not bar._analyze_btn.isEnabled()
    assert bar._analyze_btn.toolTip() == bar.analysis_unavailable_reason
    assert bar._analyze_btn.property("pending") is True
    assert bar._settings_btn.isEnabled()
    assert bar._dismiss_btn.isEnabled()
    bar.update_state(AgentState.MONITORING)
    assert bar._analyze_btn.isEnabled()


@pytest.mark.parametrize(
    "state",
    [
        AgentState.MONITORING,
        AgentState.DISPLAYING,
        AgentState.ERROR,
        AgentState.PAUSED,
    ],
)
def test_offline_after_startup_keeps_manual_recovery_available(qtbot, state):
    bar = ControlBarWindow()
    qtbot.addWidget(bar)
    bar.update_state(state)
    bar.set_gateway_status("offline")
    assert bar._analyze_btn.isEnabled()
    bar.set_gateway_status("starting")
    assert not bar._analyze_btn.isEnabled()
    bar.set_gateway_status("ready")
    assert bar._analyze_btn.isEnabled()
