"""Unit tests for OverlayAgent state machine."""

from __future__ import annotations

import base64

import pytest

from dicom_overlay.domain.entities import (
    AgentState,
    AnalysisResult,
    AppConfig,
    ChecklistItem,
    DisplayFrame,
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
    async def test_manual_mode_ignores_automatic_change_detection(
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
        assert not agent.pending_analysis
        assert pending_events == []
        assert agent_deps["vision_analyzer"].analyze_calls == 0

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
