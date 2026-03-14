"""Overlay Agent — main application use case with state machine (spec §3.5)."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Any

import structlog

from dicom_overlay.domain.entities import (
    AgentState,
    AnalysisResult,
    Modality,
    WindowRect,
)

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import AppConfig, ROICrop
    from dicom_overlay.domain.services import (
        ImageProcessorService,
        RegionMapperService,
        ScreenMonitorService,
        VisionAnalyzerService,
    )

logger = structlog.get_logger(__name__)


class OverlayAgent:
    """Main orchestrator — state machine driving the analysis pipeline.

    Transitions (spec §3.5):
      INIT → SETUP (if no ROI) or WAITING
      WAITING → MONITORING (viewer found)
      MONITORING → CAPTURING (hash changed + debounce stable)
      CAPTURING → ANALYZING (screenshot + ROI done)
      ANALYZING → DISPLAYING (result received)
      DISPLAYING → MONITORING (after timeout)
      Any → PAUSED (user pause) → MONITORING (resume)
      Any + WS disconnect → RECONNECTING → MONITORING
      Any + viewer closed → WAITING
    """

    def __init__(
        self,
        config: AppConfig,
        screen_monitor: ScreenMonitorService,
        image_processor: ImageProcessorService,
        vision_analyzer: VisionAnalyzerService,
        region_mapper: RegionMapperService,
    ) -> None:
        self._config = config
        self._monitor = screen_monitor
        self._processor = image_processor
        self._analyzer = vision_analyzer
        self._mapper = region_mapper

        self._state = AgentState.INIT
        self._current_modality = Modality.EKG
        self._last_hash: str = ""
        self._debounce_start: float = 0.0
        self._last_reconnect_attempt: float = 0.0
        self._target_window: WindowRect | None = None
        self._last_result: AnalysisResult | None = None
        self._running = False

        # Callbacks for presentation layer
        self.on_state_change: Any = None
        self.on_analysis_result: Any = None
        self.on_error: Any = None

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def current_modality(self) -> Modality:
        return self._current_modality

    @property
    def last_result(self) -> AnalysisResult | None:
        return self._last_result

    @property
    def target_window(self) -> WindowRect | None:
        return self._target_window

    def set_modality(self, modality: Modality) -> None:
        self._current_modality = modality
        logger.info("Modality set to %s", modality.value)

    def _transition(self, new_state: AgentState) -> None:
        old = self._state
        self._state = new_state
        logger.info("State: %s → %s", old.name, new_state.name)
        if self.on_state_change:
            self.on_state_change(old, new_state)

    def has_roi_config(self) -> bool:
        roi = self._config.phi_roi
        return roi.top > 0 or roi.bottom > 0 or roi.left > 0 or roi.right > 0

    async def start(self) -> None:
        """Start the agent loop."""
        self._running = True
        self._transition(AgentState.INIT)

        if not self.has_roi_config():
            self._transition(AgentState.SETUP)
            return  # Wait for ROI setup from UI

        # Try connecting to OpenClaw
        try:
            await self._analyzer.connect()
        except Exception:
            logger.warning("OpenClaw not available, will retry")

        self._transition(AgentState.WAITING)

    async def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        with contextlib.suppress(Exception):
            await self._analyzer.disconnect()

    def pause(self) -> None:
        if self._state not in (AgentState.PAUSED, AgentState.INIT, AgentState.SETUP):
            self._transition(AgentState.PAUSED)

    def resume(self) -> None:
        if self._state == AgentState.PAUSED:
            self._transition(AgentState.MONITORING)

    async def tick(self) -> None:
        """One iteration of the main loop. Called by the event loop timer."""
        if not self._running:
            return

        match self._state:
            case AgentState.WAITING:
                await self._tick_waiting()
            case AgentState.MONITORING:
                await self._tick_monitoring()
            case AgentState.RECONNECTING:
                await self._tick_reconnecting()
            case _:
                pass

    async def _tick_waiting(self) -> None:
        window = self._monitor.find_target_window(
            self._config.monitor.window_title_keywords
        )
        if window:
            self._target_window = window
            self._transition(AgentState.MONITORING)
            logger.info(
                "Found viewer: %dx%d at (%d, %d)",
                window.width,
                window.height,
                window.left,
                window.top,
            )

    async def _tick_monitoring(self) -> None:
        # Re-check window
        window = self._monitor.find_target_window(
            self._config.monitor.window_title_keywords
        )
        if not window:
            self._target_window = None
            self._transition(AgentState.WAITING)
            return
        self._target_window = window

        # Capture and compute hash
        try:
            screenshot = self._monitor.capture_region(window)
            current_hash = self._monitor.compute_hash(screenshot)
        except Exception:
            logger.exception("Screenshot failed")
            return

        if not self._last_hash:
            self._last_hash = current_hash
            return

        # Check if image changed
        threshold = self._config.monitor.hash_threshold
        if self._monitor.has_changed(self._last_hash, current_hash, threshold):
            if self._config.monitor.debounce_stable_sec <= 0:
                logger.info("Immediate trigger (debounce disabled)")
                self._debounce_start = 0.0
                self._last_hash = current_hash
                await self._do_capture_and_analyze(screenshot)
                return
            if self._debounce_start == 0.0:
                self._debounce_start = time.monotonic()
                logger.debug("Image change detected, starting debounce")
            else:
                elapsed = time.monotonic() - self._debounce_start
                if elapsed >= self._config.monitor.debounce_stable_sec:
                    logger.info("Debounce stable, triggering capture")
                    self._debounce_start = 0.0
                    self._last_hash = current_hash
                    await self._do_capture_and_analyze(screenshot)
        else:
            self._debounce_start = 0.0
            self._last_hash = current_hash

    async def trigger_manual(self) -> None:
        """Manual trigger from Control Bar or hotkey."""
        if self._target_window is None:
            logger.warning("No viewer window, cannot trigger manually")
            return
        try:
            screenshot = self._monitor.capture_region(self._target_window)
            await self._do_capture_and_analyze(screenshot)
        except Exception:
            logger.exception("Manual trigger failed")
            self._transition(AgentState.ERROR)

    async def _do_capture_and_analyze(self, screenshot: bytes) -> None:
        self._transition(AgentState.CAPTURING)

        # ROI crop
        roi = self._config.phi_roi
        cropped = self._processor.crop_roi(
            screenshot, roi.top, roi.bottom, roi.left, roi.right
        )
        image_b64 = self._processor.to_base64(cropped)

        # Analyze
        self._transition(AgentState.ANALYZING)

        if not self._analyzer.is_connected():
            try:
                await self._analyzer.connect()
            except Exception:
                self._transition(AgentState.RECONNECTING)
                if self.on_error:
                    self.on_error("OpenClaw Gateway 離線中...")
                return

        modality = self._current_modality
        valid_regions = self._mapper.get_valid_regions(modality)

        try:
            result = await self._analyzer.analyze(image_b64, modality, valid_regions)
            self._last_result = result
            self._transition(AgentState.DISPLAYING)
            if self.on_analysis_result:
                self.on_analysis_result(result)
        except TimeoutError:
            logger.error("Analysis timed out")
            self._transition(AgentState.ERROR)
            if self.on_error:
                self.on_error("分析逾時")
        except ConnectionError:
            self._transition(AgentState.RECONNECTING)
            if self.on_error:
                self.on_error("Gateway 連線中斷")
        except Exception:
            logger.exception("Analysis failed")
            self._transition(AgentState.ERROR)
            if self.on_error:
                self.on_error("分析錯誤")

    async def _tick_reconnecting(self) -> None:
        now = time.monotonic()
        if now - self._last_reconnect_attempt < self._config.openclaw.reconnect_interval_sec:
            return  # Throttle: skip this tick, don't block the event loop
        self._last_reconnect_attempt = now
        try:
            await self._analyzer.connect()
            self._transition(AgentState.MONITORING)
        except Exception:
            logger.debug("Reconnect attempt failed, will retry")

    def on_roi_setup_complete(self, roi: ROICrop) -> None:
        """Called when user completes ROI setup wizard."""
        self._config.phi_roi = roi
        self._transition(AgentState.WAITING)

    def on_display_timeout(self) -> None:
        """Called when overlay display times out."""
        if self._state == AgentState.DISPLAYING:
            self._transition(AgentState.MONITORING)
