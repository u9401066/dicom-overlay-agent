"""Unit tests for domain entities."""

from __future__ import annotations

from typing import Any, cast

import pytest

from dicom_overlay.domain.entities import (
    AgentState,
    AnalysisResult,
    AppConfig,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    ROICrop,
    Severity,
    WindowRect,
)


class TestRegionRect:
    def test_valid_creation(self):
        r = RegionRect(x=0.0, y=0.0, w=0.5, h=0.5)
        assert r.x == 0.0
        assert r.w == 0.5

    def test_boundary_values(self):
        r = RegionRect(x=0.0, y=0.0, w=1.0, h=1.0)
        assert r.w == 1.0

    def test_invalid_negative(self):
        with pytest.raises(ValueError, match="x must be in"):
            RegionRect(x=-0.1, y=0.0, w=0.5, h=0.5)

    def test_invalid_over_one(self):
        with pytest.raises(ValueError, match="w must be in"):
            RegionRect(x=0.0, y=0.0, w=1.1, h=0.5)

    def test_frozen(self):
        r = RegionRect(x=0.1, y=0.2, w=0.3, h=0.4)
        with pytest.raises(AttributeError):
            cast("Any", r).x = 0.5


class TestWindowRect:
    def test_properties(self):
        w = WindowRect(left=100, top=200, width=800, height=600)
        assert w.right == 900
        assert w.bottom == 800


class TestROICrop:
    def test_defaults(self):
        roi = ROICrop()
        assert roi.top == 0
        assert roi.bottom == 0
        assert roi.left == 0
        assert roi.right == 0
        assert roi.configured is False
        assert roi.coordinate_space == "viewer"
        assert roi.reference_width == 0
        assert roi.reference_height == 0


class TestFinding:
    def test_creation(self):
        f = Finding(
            id="f1",
            regions=["lead_V3", "lead_V4"],
            label="QTc prolonged",
            detail="Borderline QTc",
            severity=Severity.WARNING,
        )
        assert f.id == "f1"
        assert len(f.regions) == 2
        assert f.severity == Severity.WARNING


class TestAnalysisResult:
    def test_creation(self):
        result = AnalysisResult(
            modality=Modality.EKG,
            summary="Normal sinus rhythm",
            severity=Severity.NORMAL,
            findings=[],
            checklist={
                "rate": ChecklistItem(value="72 bpm", status=Severity.NORMAL),
            },
        )
        assert result.modality == Modality.EKG
        assert result.summary == "Normal sinus rhythm"
        assert "rate" in result.checklist
        assert result.analysis_time_ms == 0


class TestSeverity:
    def test_values(self):
        assert Severity.CRITICAL.value == "critical"
        assert Severity.WARNING.value == "warning"
        assert Severity.NORMAL.value == "normal"
        assert Severity.INFO.value == "info"


class TestModality:
    def test_values(self):
        assert Modality.EKG.value == "EKG"
        assert Modality.CXR.value == "CXR"
        assert Modality.CT_BRAIN.value == "CT_BRAIN"
        assert Modality.AUTO.value == "auto"


class TestAgentState:
    def test_all_states_exist(self):
        states = [
            AgentState.INIT,
            AgentState.SETUP,
            AgentState.WAITING,
            AgentState.MONITORING,
            AgentState.CAPTURING,
            AgentState.ANALYZING,
            AgentState.DISPLAYING,
            AgentState.PAUSED,
            AgentState.ERROR,
            AgentState.RECONNECTING,
        ]
        assert len(states) == 10


class TestAppConfig:
    def test_defaults(self):
        config = AppConfig()
        assert config.monitor.polling_interval_ms == 500
        assert config.phi_roi.top == 0
        assert config.phi_roi.configured is False
        assert config.openclaw.gateway_url == "ws://127.0.0.1:18789"
        assert config.overlay.display_duration_sec == 30
        assert config.hotkeys.trigger_manual == "ctrl+shift+a"
        assert config.log_level == "INFO"
