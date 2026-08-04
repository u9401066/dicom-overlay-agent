"""Unit tests for OverlayAgent state machine."""

from __future__ import annotations

import asyncio
import base64

import pytest

from dicom_overlay.domain.entities import (
    AgentState,
    AnalysisResult,
    AppConfig,
    ChecklistItem,
    DisplayFrame,
    Finding,
    FindingDelta,
    FindingOp,
    Modality,
    RegionRect,
    ROICrop,
    Severity,
    TriggerMode,
    WindowRect,
)
from dicom_overlay.domain.services import (
    ImageProcessorService,
    RegionMapperService,
    ScreenMonitorService,
    VisionAnalyzerService,
)

# --- Mock implementations ---


class MockScreenMonitor(ScreenMonitorService):
    def __init__(self):
        self.window: WindowRect | None = None
        self.screenshot: bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF9sAAAAASUVORK5CYII="
        )
        self.hash_value: str = "0000000000000000"
        self.hash_changed: bool = False
        self.display: DisplayFrame | None = None
        self.capture_rects: list[WindowRect] = []

    def find_target_window(self, keywords: list[str]) -> WindowRect | None:
        return self.window

    def display_for_window(self, window: WindowRect) -> DisplayFrame | None:
        del window
        return self.display

    def capture_region(self, rect: WindowRect) -> bytes:
        self.capture_rects.append(rect)
        return self.screenshot

    def compute_hash(self, image_data: bytes) -> str:
        return self.hash_value

    def has_changed(self, hash1: str, hash2: str, threshold: int) -> bool:
        return self.hash_changed


class MockImageProcessor(ImageProcessorService):
    def __init__(self):
        self.size = (321, 123)

    def crop_roi(
        self, image_data: bytes, top: int, bottom: int, left: int, right: int
    ) -> bytes:
        return image_data

    def to_base64(self, image_data: bytes) -> str:
        return "ZmFrZQ=="

    def downscale_to_max_edge(self, image_data: bytes, max_edge: int) -> bytes:
        return image_data

    def image_size(self, image_data: bytes) -> tuple[int, int]:
        return self.size


class MockVisionAnalyzer(VisionAnalyzerService):
    def __init__(self):
        self._connected = False
        self.should_fail = False
        self.analyze_calls = 0
        self.result = AnalysisResult(
            modality=Modality.EKG,
            summary="Normal sinus rhythm",
            severity=Severity.NORMAL,
            findings=[],
            checklist={"rate": ChecklistItem(value="72", status=Severity.NORMAL)},
            analysis_time_ms=100,
        )

    async def connect(self) -> None:
        if self.should_fail:
            raise ConnectionError("Mock connection failed")
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    async def analyze(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        self.analyze_calls += 1
        return self.result

    async def chat(self, message: str) -> str:
        return "Mock chat response"


class MockSourceSizeAnalyzer(MockVisionAnalyzer):
    def __init__(self):
        super().__init__()
        self.source_size_px: tuple[int, int] | None = None

    async def analyze_with_source_size(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        source_size_px: tuple[int, int] | None,
    ) -> AnalysisResult:
        self.source_size_px = source_size_px
        return await self.analyze(image_base64, modality, valid_regions)


class BlockingVisionAnalyzer(MockVisionAnalyzer):
    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def analyze(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        del image_base64, modality, valid_regions
        self.analyze_calls += 1
        self.entered.set()
        await self.release.wait()
        return self.result


class MockRegionMapper(RegionMapperService):
    def get_region_rect(
        self, region_name: str, modality: Modality
    ) -> RegionRect | None:
        return RegionRect(x=0.0, y=0.0, w=0.25, h=0.27)

    def get_valid_regions(self, modality: Modality) -> list[str]:
        return ["lead_I", "lead_II"]

    def to_screen_rect(
        self,
        region: RegionRect,
        image_rect: WindowRect,
    ) -> tuple[int, int, int, int]:
        return (0, 0, 100, 100)


# --- Tests ---


class TestOverlayAgent:
    @pytest.fixture()
    def agent_deps(self):
        return {
            "screen_monitor": MockScreenMonitor(),
            "image_processor": MockImageProcessor(),
            "vision_analyzer": MockVisionAnalyzer(),
            "region_mapper": MockRegionMapper(),
        }

    @pytest.fixture()
    def agent(self, agent_deps):
        from dicom_overlay.application.overlay_agent import OverlayAgent

        config = AppConfig()
        return OverlayAgent(config=config, **agent_deps)

    @pytest.mark.asyncio
    async def test_init_state(self, agent):
        assert agent.state == AgentState.INIT

    def test_reviewer_confirmed_delta_updates_result_and_trace(self, agent):
        original = Finding(
            id="f1",
            regions=["lead_V2"],
            label="ST-T change",
            detail="Subtle morphology.",
            severity=Severity.WARNING,
            bboxes=[RegionRect(0.2, 0.2, 0.2, 0.2)],
        )
        agent._last_result = AnalysisResult(
            modality=Modality.EKG,
            summary="Abnormal ECG",
            severity=Severity.CRITICAL,
            findings=[original],
            checklist={},
        )
        agent._annotation_accumulator.reset([original])
        agent._result_revision = 4
        agent._state = AgentState.DISPLAYING
        revised = Finding(
            id="f1",
            regions=["lead_V2"],
            label="Nonspecific ST-T change",
            detail="Less specific on crop review.",
            severity=Severity.INFO,
            bboxes=original.bboxes,
            source="interactive_ai_review",
        )

        updated = agent.apply_finding_delta(
            FindingDelta(
                op=FindingOp.REVISE,
                finding=revised,
                note="Reviewer accepted regional re-check",
            ),
            expected_revision=4,
            local_signal_audit={
                "status": "ok",
                "ink_pixel_ratio": 0.12,
                "low_signal": False,
            },
        )

        assert updated.findings[0].severity is Severity.INFO
        assert updated.findings[0].source == "interactive_ai_review"
        assert updated.severity is Severity.CRITICAL
        assert updated.summary.startswith(
            "Reviewer-confirmed regional update: revised Nonspecific ST-T change."
        )
        assert "Current overlay findings: Nonspecific ST-T change [info]." in (
            updated.summary
        )
        assert "safety floor" in updated.summary
        assert updated.review_required is True
        assert any("initial checklist" in reason for reason in updated.review_reasons)
        assert any("Reconcile" in step for step in updated.next_steps)
        assert updated.analysis_trace[-1]["stage"] == "interactive_review"
        assert updated.analysis_trace[-1]["user_confirmed"] is True
        assert updated.analysis_trace[-1]["bbox_source"] == (
            "selected_finding_existing_bbox"
        )
        assert updated.analysis_trace[-1]["local_signal_audit"] == {
            "status": "ok",
            "ink_pixel_ratio": 0.12,
            "low_signal": False,
        }
        assert updated.analysis_trace[-1]["report_reconciliation"] == {
            "findings": "updated",
            "summary": "updated",
            "overall_severity": "retained_safety_floor",
            "checklist": "retained_requires_review",
            "next_steps": "retained_with_reconciliation_step",
            "summary_before": "Abnormal ECG",
            "summary_after": updated.summary,
            "severity_before": "critical",
            "structured_severity_after": "info",
            "severity_after": "critical",
        }
        assert agent.result_revision == 5

    def test_regional_no_change_is_recorded_without_mutating_findings(self, agent):
        from dicom_overlay.application.overlay_agent import ReviewSnapshot

        finding = Finding(
            id="f1",
            regions=["lead_II"],
            label="Candidate",
            detail="Initial observation.",
            severity=Severity.INFO,
        )
        original = AnalysisResult(
            modality=Modality.EKG,
            summary="Review",
            severity=Severity.INFO,
            findings=[finding],
            checklist={},
        )
        agent._last_result = original
        agent._annotation_accumulator.reset([finding])
        agent._result_revision = 8
        agent._state = AgentState.DISPLAYING
        agent._review_snapshot = ReviewSnapshot(
            image_base64="image",
            result=original,
            capture_rect=WindowRect(10, 20, 300, 200),
            revision=8,
        )

        updated = agent.record_regional_review_outcome(
            expected_revision=8,
            outcome="blocked",
            local_signal_audit={
                "status": "ok",
                "low_signal": True,
                "private_value": "drop-me",
            },
            regional_review_trace=[
                {
                    "stage": "regional_structured_review",
                    "status": "completed",
                    "run_id": "run-8",
                    "private_value": "drop-me",
                }
            ],
        )

        assert updated.findings == [finding]
        assert updated.analysis_trace[-1] == {
            "stage": "interactive_review",
            "status": "blocked",
            "tool": "openclaw_region_followup",
            "operation": "none",
            "user_confirmed": False,
            "local_signal_audit": {"status": "ok", "low_signal": True},
            "regional_turns": [
                {
                    "stage": "regional_structured_review",
                    "status": "completed",
                    "run_id": "run-8",
                }
            ],
        }
        assert agent.result_revision == 9
        assert agent.review_snapshot is not None
        assert agent.review_snapshot.result is updated
        assert agent.review_snapshot.revision == 9

    def test_reviewer_retract_records_static_region_fallback(self, agent):
        original = Finding(
            id="f-static",
            regions=["lead_V3"],
            label="Static mapped finding",
            detail="No model bbox was supplied.",
            severity=Severity.WARNING,
        )
        agent._last_result = AnalysisResult(
            modality=Modality.EKG,
            summary="Review",
            severity=Severity.WARNING,
            findings=[original],
            checklist={},
        )
        agent._annotation_accumulator.reset([original])
        agent._result_revision = 3
        agent._state = AgentState.DISPLAYING
        fallback = RegionRect(0.4, 0.3, 0.2, 0.2)

        updated = agent.apply_finding_delta(
            FindingDelta(
                op=FindingOp.RETRACT,
                finding=Finding(
                    id=original.id,
                    regions=original.regions,
                    label=original.label,
                    detail=original.detail,
                    severity=original.severity,
                    bboxes=[fallback],
                ),
            ),
            expected_revision=3,
            local_signal_audit={"status": "ok", "low_signal": False},
        )

        assert updated.findings == []
        assert "No focal overlay findings remain." in updated.summary
        assert "safety floor" in updated.summary
        assert updated.analysis_trace[-1]["bbox_source"] == (
            "selected_static_region_fallback"
        )
        assert updated.analysis_trace[-1]["bboxes"] == [
            {"x": 0.4, "y": 0.3, "w": 0.2, "h": 0.2}
        ]

    def test_reviewer_reconciliation_includes_retained_checklist_severity(
        self,
        agent,
    ):
        original = Finding(
            id="f1",
            regions=["lead_V2"],
            label="Candidate",
            detail="Regional candidate.",
            severity=Severity.WARNING,
            bboxes=[RegionRect(0.2, 0.2, 0.2, 0.2)],
        )
        agent._last_result = AnalysisResult(
            modality=Modality.EKG,
            summary="Initial report",
            severity=Severity.WARNING,
            findings=[original],
            checklist={
                "rhythm": ChecklistItem("sinus", Severity.NORMAL),
                "qt": ChecklistItem("prolonged", Severity.WARNING),
            },
        )
        agent._annotation_accumulator.reset([original])
        agent._result_revision = 5
        agent._state = AgentState.DISPLAYING

        updated = agent.apply_finding_delta(
            FindingDelta(op=FindingOp.RETRACT, finding=original),
            expected_revision=5,
            local_signal_audit={"status": "ok", "low_signal": False},
        )

        assert updated.findings == []
        assert updated.severity is Severity.WARNING
        reconciliation = updated.analysis_trace[-1]["report_reconciliation"]
        assert reconciliation["structured_severity_after"] == "warning"
        assert reconciliation["overall_severity"] == "matches_structured_report"

    def test_reviewer_delta_rejects_ambiguous_duplicate_current_ids(self, agent):
        first = Finding(
            id="same",
            regions=[],
            label="One",
            detail="First.",
            severity=Severity.INFO,
        )
        second = Finding(
            id="same",
            regions=[],
            label="Two",
            detail="Second.",
            severity=Severity.WARNING,
        )
        agent._last_result = AnalysisResult(
            modality=Modality.EKG,
            summary="Ambiguous",
            severity=Severity.WARNING,
            findings=[first, second],
            checklist={},
        )
        agent._result_revision = 1
        agent._state = AgentState.DISPLAYING

        with pytest.raises(ValueError, match="duplicate finding ids"):
            agent.apply_finding_delta(
                FindingDelta(op=FindingOp.RETRACT, finding=first),
                expected_revision=1,
                local_signal_audit={"status": "ok", "low_signal": False},
            )

    def test_reviewer_delta_rejects_stale_result_revision(self, agent):
        finding = Finding(
            id="f1",
            regions=[],
            label="Candidate",
            detail="Candidate detail",
            severity=Severity.INFO,
        )
        agent._last_result = AnalysisResult(
            modality=Modality.EKG,
            summary="Review",
            severity=Severity.INFO,
            findings=[finding],
            checklist={},
        )
        agent._annotation_accumulator.reset([finding])
        agent._result_revision = 7
        agent._state = AgentState.DISPLAYING

        with pytest.raises(RuntimeError, match="changed"):
            agent.apply_finding_delta(
                FindingDelta(op=FindingOp.RETRACT, finding=finding),
                expected_revision=6,
            )

    def test_reviewer_add_fails_closed_without_local_signal_receipt(self, agent):
        agent._last_result = AnalysisResult(
            modality=Modality.EKG,
            summary="Normal",
            severity=Severity.NORMAL,
            findings=[],
            checklist={},
        )
        agent._annotation_accumulator.reset([])
        agent._result_revision = 2
        agent._state = AgentState.DISPLAYING
        candidate = Finding(
            id="review-blank",
            regions=[],
            label="Candidate",
            detail="Candidate detail",
            severity=Severity.INFO,
            bboxes=[RegionRect(0.2, 0.2, 0.2, 0.2)],
        )

        with pytest.raises(ValueError, match="local-signal"):
            agent.apply_finding_delta(
                FindingDelta(op=FindingOp.ADD, finding=candidate),
                expected_revision=2,
                local_signal_audit={"status": "ok", "low_signal": True},
            )

    def test_reviewer_delta_rejects_while_new_image_is_analyzing(self, agent):
        finding = Finding(
            id="f1",
            regions=[],
            label="Candidate",
            detail="Candidate detail",
            severity=Severity.WARNING,
            bboxes=[RegionRect(0.2, 0.2, 0.2, 0.2)],
        )
        agent._last_result = AnalysisResult(
            modality=Modality.EKG,
            summary="Review",
            severity=Severity.WARNING,
            findings=[finding],
            checklist={},
        )
        agent._annotation_accumulator.reset([finding])
        agent._result_revision = 3
        agent._state = AgentState.ANALYZING

        with pytest.raises(RuntimeError, match="displayed"):
            agent.apply_finding_delta(
                FindingDelta(op=FindingOp.RETRACT, finding=finding),
                expected_revision=3,
                local_signal_audit={"status": "ok", "low_signal": False},
            )

    @pytest.mark.parametrize(
        "bbox",
        [
            RegionRect(0.9, 0.2, 0.2, 0.2),
            RegionRect(0.2, 0.9, 0.2, 0.2),
        ],
    )
    def test_reviewer_add_rejects_original_roi_extent_overflow(
        self,
        agent,
        bbox,
    ):
        agent._last_result = AnalysisResult(
            modality=Modality.EKG,
            summary="Normal",
            severity=Severity.NORMAL,
            findings=[],
            checklist={},
        )
        agent._annotation_accumulator.reset([])
        agent._result_revision = 2
        agent._state = AgentState.DISPLAYING
        candidate = Finding(
            id="review-outside",
            regions=[],
            label="Candidate",
            detail="Candidate detail",
            severity=Severity.INFO,
            bboxes=[bbox],
        )

        with pytest.raises(ValueError, match="outside"):
            agent.apply_finding_delta(
                FindingDelta(op=FindingOp.ADD, finding=candidate),
                expected_revision=2,
                local_signal_audit={"status": "ok", "low_signal": False},
            )

    def test_roi_rect_includes_screen_origin(self, agent):
        """Capture rect must be absolute virtual-desktop coords (multi-monitor)."""
        agent._config.phi_roi = ROICrop(top=10, bottom=20, left=30, right=40)
        agent._screen_width = 1920
        agent._screen_height = 1080
        agent._screen_left = 1920  # primary screen offset to the right
        agent._screen_top = 0
        rect = agent._get_roi_rect()
        assert rect.left == 1920 + 30  # screen origin + roi.left
        assert rect.top == 0 + 10
        assert rect.width == 1920 - 30 - 40
        assert rect.height == 1080 - 10 - 20

    def test_roi_rect_default_origin_zero(self, agent):
        """Single-monitor primary-at-origin keeps the original behavior."""
        agent._config.phi_roi = ROICrop(top=5, bottom=5, left=5, right=5)
        agent._screen_width = 800
        agent._screen_height = 600
        rect = agent._get_roi_rect()
        assert rect.left == 5
        assert rect.top == 5
        assert rect.width == 790
        assert rect.height == 590

    @pytest.mark.asyncio
    async def test_start_without_roi(self, agent):
        agent._config.phi_roi = ROICrop(top=0, bottom=0, left=0, right=0)
        await agent.start()
        assert agent.state == AgentState.SETUP

    @pytest.mark.asyncio
    async def test_start_with_roi(self, agent):
        await agent.start()
        # Should move to WAITING (OpenClaw may not connect)
        assert agent.state == AgentState.WAITING

    @pytest.mark.asyncio
    async def test_waiting_finds_window(self, agent, agent_deps):
        await agent.start()
        assert agent.state == AgentState.WAITING

        # Simulate window appearing
        agent_deps["screen_monitor"].window = WindowRect(
            left=0, top=0, width=1920, height=1080
        )
        await agent.tick()
        assert agent.state == AgentState.MONITORING

    @pytest.mark.asyncio
    async def test_waiting_no_window(self, agent):
        await agent.start()
        await agent.tick()
        assert agent.state == AgentState.WAITING

    @pytest.mark.asyncio
    async def test_pause_resume(self, agent, agent_deps):
        await agent.start()
        agent_deps["screen_monitor"].window = WindowRect(
            left=0, top=0, width=1920, height=1080
        )
        await agent.tick()
        assert agent.state == AgentState.MONITORING

        agent.pause()
        assert agent.state == AgentState.PAUSED

        agent.resume()
        assert agent.state == AgentState.MONITORING

    @pytest.mark.asyncio
    async def test_modality_change(self, agent):
        assert agent.current_modality == Modality.EKG
        agent.set_modality(Modality.CXR)
        assert agent.current_modality == Modality.CXR

    @pytest.mark.asyncio
    async def test_display_timeout(self, agent):
        agent._transition(AgentState.DISPLAYING)
        agent.on_display_timeout()
        assert agent.state == AgentState.MONITORING

    @pytest.mark.asyncio
    async def test_has_roi_config(self, agent):
        assert agent.has_roi_config()  # defaults have top=60

    @pytest.mark.asyncio
    async def test_stop(self, agent):
        await agent.start()
        await agent.stop()
        assert not agent._running

    @pytest.mark.asyncio
    async def test_default_trigger_mode_is_hybrid(self, agent):
        assert agent.trigger_mode == TriggerMode.HYBRID

    @pytest.mark.asyncio
    async def test_hybrid_mode_detects_change_without_auto_analyzing(
        self, agent, agent_deps
    ):
        pending_events: list[str] = []
        agent.on_pending_analysis = lambda reason: pending_events.append(reason)

        await agent.start()
        agent_deps["screen_monitor"].window = WindowRect(
            left=0, top=0, width=1920, height=1080
        )
        await agent.tick()
        await agent.tick()  # establish hash baseline

        agent_deps["screen_monitor"].hash_changed = True
        agent._config.monitor.debounce_stable_sec = 0
        await agent.tick()

        assert agent.state == AgentState.MONITORING
        assert agent.pending_analysis
        assert pending_events == ["image_changed"]
        assert agent_deps["vision_analyzer"].analyze_calls == 0

    @pytest.mark.asyncio
    async def test_manual_mode_marks_changed_image_pending_without_auto_analysis(
        self, agent, agent_deps
    ):
        pending_events: list[str] = []
        agent.on_pending_analysis = lambda reason: pending_events.append(reason)
        agent.set_trigger_mode(TriggerMode.MANUAL)

        await agent.start()
        agent_deps["screen_monitor"].window = WindowRect(
            left=0, top=0, width=1920, height=1080
        )
        await agent.tick()
        await agent.tick()  # establish hash baseline

        agent_deps["screen_monitor"].hash_changed = True
        agent._config.monitor.debounce_stable_sec = 0
        await agent.tick()

        assert agent.state == AgentState.MONITORING
        assert agent.pending_analysis
        assert pending_events == ["image_changed_manual"]
        assert agent_deps["vision_analyzer"].analyze_calls == 0

    @pytest.mark.asyncio
    async def test_manual_image_change_invalidates_displayed_review_snapshot(
        self, agent, agent_deps
    ):
        agent.set_trigger_mode(TriggerMode.MANUAL)
        await agent.start()
        agent_deps["screen_monitor"].window = WindowRect(
            left=0, top=0, width=1920, height=1080
        )
        await agent.tick()
        await agent.trigger_manual()
        assert agent.displayed_review_snapshot is not None

        await agent._handle_stable_image_change("new-image-hash")

        assert agent.state is AgentState.MONITORING
        assert agent.displayed_review_snapshot is None
        assert agent.pending_analysis is True

    @pytest.mark.asyncio
    async def test_auto_mode_analyzes_after_stable_change(self, agent, agent_deps):
        agent.set_trigger_mode(TriggerMode.AUTO)

        await agent.start()
        agent_deps["screen_monitor"].window = WindowRect(
            left=0, top=0, width=1920, height=1080
        )
        await agent.tick()
        await agent.tick()  # establish hash baseline

        agent_deps["screen_monitor"].hash_changed = True
        agent._config.monitor.debounce_stable_sec = 0
        await agent.tick()

        assert agent.state == AgentState.DISPLAYING
        assert not agent.pending_analysis
        assert agent_deps["vision_analyzer"].analyze_calls == 1

    @pytest.mark.asyncio
    async def test_manual_trigger_clears_hybrid_pending_analysis(
        self, agent, agent_deps
    ):
        await agent.start()
        agent_deps["screen_monitor"].window = WindowRect(
            left=0, top=0, width=1920, height=1080
        )
        await agent.tick()
        await agent.tick()  # establish hash baseline

        agent_deps["screen_monitor"].hash_changed = True
        agent._config.monitor.debounce_stable_sec = 0
        await agent.tick()

        assert agent.pending_analysis

        await agent.trigger_manual()

        assert agent.state == AgentState.DISPLAYING
        assert not agent.pending_analysis
        assert agent_deps["vision_analyzer"].analyze_calls == 1

    @pytest.mark.asyncio
    async def test_analysis_keeps_last_image_for_followup_chat(self, agent, agent_deps):
        await agent.start()
        agent_deps["screen_monitor"].window = WindowRect(
            left=0, top=0, width=1920, height=1080
        )
        await agent.tick()

        assert agent.last_image_base64 == ""

        await agent.trigger_manual()

        assert agent.state == AgentState.DISPLAYING
        assert agent.last_image_base64 == "ZmFrZQ=="
        assert agent.review_snapshot is not None
        assert agent.review_snapshot.image_base64 == agent.last_image_base64
        assert agent.review_snapshot.result is agent.last_result

    @pytest.mark.asyncio
    async def test_review_snapshot_is_published_only_after_analysis_completes(
        self, agent_deps
    ):
        from dicom_overlay.application.overlay_agent import OverlayAgent

        analyzer = BlockingVisionAnalyzer()
        agent_deps["vision_analyzer"] = analyzer
        agent = OverlayAgent(config=AppConfig(), **agent_deps)
        await agent.start()
        agent_deps["screen_monitor"].window = WindowRect(
            left=0, top=0, width=1920, height=1080
        )
        await agent.tick()

        task = asyncio.create_task(agent.trigger_manual())
        await analyzer.entered.wait()

        assert agent.state is AgentState.ANALYZING
        assert agent.review_snapshot is None
        assert agent.last_image_base64 == ""

        analyzer.release.set()
        await task

        assert agent.state is AgentState.DISPLAYING
        assert agent.review_snapshot is not None
        assert agent.review_snapshot.image_base64 == "ZmFrZQ=="

    @pytest.mark.asyncio
    async def test_analysis_passes_downscaled_source_size_when_supported(
        self, agent_deps
    ):
        from dicom_overlay.application.overlay_agent import OverlayAgent

        analyzer = MockSourceSizeAnalyzer()
        agent_deps["vision_analyzer"] = analyzer
        agent_deps["image_processor"].size = (640, 360)
        config = AppConfig()
        agent = OverlayAgent(config=config, **agent_deps)
        await agent.start()
        agent_deps["screen_monitor"].window = WindowRect(
            left=0, top=0, width=1920, height=1080
        )
        await agent.tick()

        await agent.trigger_manual()

        assert agent.state == AgentState.DISPLAYING
        assert analyzer.source_size_px == (640, 360)

    @pytest.mark.asyncio
    async def test_capture_tracks_secondary_display_and_preserves_exact_rect(
        self, agent, agent_deps
    ):
        monitor = agent_deps["screen_monitor"]
        monitor.window = WindowRect(left=-1800, top=100, width=1600, height=800)
        monitor.display = DisplayFrame(
            physical_rect=WindowRect(
                left=-1920,
                top=0,
                width=1920,
                height=1080,
            ),
            device_name=r"\\.\DISPLAY2",
            monitor_index=1,
            is_primary=False,
        )
        agent._config.phi_roi = ROICrop(top=10, bottom=20, left=30, right=40)

        await agent.start()
        await agent.tick()
        await agent.trigger_manual()

        expected = WindowRect(left=-1890, top=10, width=1850, height=1050)
        assert agent.display_frame == monitor.display
        assert agent.last_capture_rect == expected
        assert monitor.capture_rects[-1] == expected
