"""Overlay Agent — main application use case with state machine (spec §3.5)."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING, Any

import structlog

from dicom_overlay.domain.entities import (
    AgentState,
    AnalysisResult,
    Modality,
    TriggerMode,
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
    from dicom_overlay.infrastructure.gateway_manager import GatewayManager

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
        gateway_manager: GatewayManager | None = None,
        screen_width: int = 1920,
        screen_height: int = 1080,
        dpr: float = 1.0,
        screen_left: int = 0,
        screen_top: int = 0,
    ) -> None:
        self._config = config
        self._monitor = screen_monitor
        self._processor = image_processor
        self._analyzer = vision_analyzer
        self._mapper = region_mapper
        self._gateway: GatewayManager | None = gateway_manager
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._dpr = dpr
        # Origin of the target screen on the virtual desktop (physical pixels).
        # Non-zero on multi-monitor layouts where the primary screen is not at
        # (0, 0); mss.grab needs absolute virtual-desktop coordinates.
        self._screen_left = screen_left
        self._screen_top = screen_top

        self._state = AgentState.INIT
        self._current_modality = Modality.EKG
        self._trigger_mode = config.analysis.trigger_mode
        self._pending_analysis = False
        self._last_hash: str = ""
        self._debounce_start: float = 0.0
        self._last_reconnect_attempt: float = 0.0
        self._error_time: float = 0.0
        self._display_enter_time: float = 0.0
        self._target_window: WindowRect | None = None
        self._last_result: AnalysisResult | None = None
        self._last_image_base64 = ""
        self._running = False

        # Callbacks for presentation layer
        self.on_state_change: Any = None
        self.on_analysis_result: Any = None
        self.on_pending_analysis: Any = None
        self.on_error: Any = None

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def current_modality(self) -> Modality:
        return self._current_modality

    @property
    def trigger_mode(self) -> TriggerMode:
        return self._trigger_mode

    @property
    def pending_analysis(self) -> bool:
        return self._pending_analysis

    @property
    def last_result(self) -> AnalysisResult | None:
        return self._last_result

    @property
    def last_image_base64(self) -> str:
        return self._last_image_base64

    @property
    def target_window(self) -> WindowRect | None:
        return self._target_window

    def set_modality(self, modality: Modality) -> None:
        self._current_modality = modality
        logger.info("Modality set to %s", modality.value)

    def set_trigger_mode(self, mode: TriggerMode) -> None:
        self._trigger_mode = mode
        self._config.analysis.trigger_mode = mode
        if mode == TriggerMode.AUTO:
            self._pending_analysis = False
        logger.info("Trigger mode set to %s", mode.value)

    def _transition(self, new_state: AgentState) -> None:
        old = self._state
        self._state = new_state
        if new_state == AgentState.ERROR:
            self._error_time = time.monotonic()
        if new_state == AgentState.DISPLAYING:
            # Reset hash baseline so first tick after overlay renders
            # establishes a new baseline (with overlay visible).
            self._last_hash = ""
            self._display_enter_time = time.monotonic()
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
            case AgentState.DISPLAYING:
                await self._tick_displaying()
            case AgentState.RECONNECTING:
                await self._tick_reconnecting()
            case AgentState.ERROR:
                await self._tick_error()
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

    def _get_roi_rect(self) -> WindowRect:
        """Compute the screen-relative ROI capture rectangle.

        ``left``/``top`` include the target screen origin so the rectangle is
        expressed in absolute virtual-desktop coordinates (required by
        ``mss.grab`` on multi-monitor layouts).
        """
        roi = self._config.phi_roi
        return WindowRect(
            left=self._screen_left + roi.left,
            top=self._screen_top + roi.top,
            width=self._screen_width - roi.left - roi.right,
            height=self._screen_height - roi.top - roi.bottom,
        )

    async def _tick_displaying(self) -> None:
        """While results are shown, keep monitoring for image changes.

        When the viewer image changes (new patient/study), automatically
        dismiss the current result and start a new analysis cycle.
        If the viewer window disappears, go back to WAITING.
        """
        window = self._monitor.find_target_window(
            self._config.monitor.window_title_keywords
        )
        if not window:
            self._target_window = None
            self._transition(AgentState.WAITING)
            return
        self._target_window = window

        # Settling period: overlay needs time to render on screen.
        # Skip hash monitoring until overlay is fully visible (~2s).
        if time.monotonic() - self._display_enter_time < 2.0:
            return

        try:
            screenshot = self._monitor.capture_region(self._get_roi_rect())
            current_hash = self._monitor.compute_hash(screenshot)
        except Exception:
            logger.exception("Screenshot failed during display")
            return

        # First tick after settling: establish baseline with overlay visible.
        if not self._last_hash:
            self._last_hash = current_hash
            return

        threshold = self._config.monitor.hash_threshold
        if self._monitor.has_changed(self._last_hash, current_hash, threshold):
            if self._debounce_start == 0.0:
                self._debounce_start = time.monotonic()
                logger.debug("Image change detected while displaying")
            else:
                elapsed = time.monotonic() - self._debounce_start
                if elapsed >= self._config.monitor.debounce_stable_sec:
                    logger.info("New image detected, re-analyzing")
                    self._debounce_start = 0.0
                    await self._handle_stable_image_change(current_hash)
        else:
            self._debounce_start = 0.0
            self._last_hash = current_hash

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

        # Capture ROI area (same region used for analysis) and compute hash
        try:
            screenshot = self._monitor.capture_region(self._get_roi_rect())
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
                await self._handle_stable_image_change(current_hash)
                return
            if self._debounce_start == 0.0:
                self._debounce_start = time.monotonic()
                logger.debug("Image change detected, starting debounce")
            else:
                elapsed = time.monotonic() - self._debounce_start
                if elapsed >= self._config.monitor.debounce_stable_sec:
                    logger.info("Debounce stable, triggering capture")
                    self._debounce_start = 0.0
                    await self._handle_stable_image_change(current_hash)
        else:
            self._debounce_start = 0.0
            self._last_hash = current_hash

    async def _handle_stable_image_change(self, current_hash: str) -> None:
        self._last_hash = current_hash
        if self._trigger_mode == TriggerMode.AUTO:
            self._pending_analysis = False
            await self._do_capture_and_analyze()
            return

        if self._trigger_mode == TriggerMode.HYBRID:
            self._mark_pending_analysis("image_changed")
            if self._state == AgentState.DISPLAYING:
                self._transition(AgentState.MONITORING)
            return

        logger.info("Image change ignored in manual trigger mode")

    def _mark_pending_analysis(self, reason: str) -> None:
        if self._pending_analysis:
            return
        self._pending_analysis = True
        logger.info("Analysis pending: %s", reason)
        if self.on_pending_analysis:
            self.on_pending_analysis(reason)

    async def trigger_manual(self) -> None:
        """Manual trigger from Control Bar or hotkey."""
        if self._target_window is None:
            logger.warning("No viewer window, cannot trigger manually")
            return
        try:
            await self._do_capture_and_analyze()
        except Exception:
            logger.exception("Manual trigger failed")
            self._transition(AgentState.ERROR)

    async def _do_capture_and_analyze(self) -> None:
        self._pending_analysis = False
        self._transition(AgentState.CAPTURING)

        # Capture the screen area defined by ROI (screen-relative margins).
        # ROI margins and screen dimensions are both in physical pixels.
        roi = self._config.phi_roi
        if self._target_window is None:
            logger.warning("No target window for capture")
            self._transition(AgentState.WAITING)
            return
        capture_rect = WindowRect(
            left=self._screen_left + roi.left,
            top=self._screen_top + roi.top,
            width=self._screen_width - roi.left - roi.right,
            height=self._screen_height - roi.top - roi.bottom,
        )
        logger.info(
            "ROI capture: screen=%dx%d roi=(%d,%d,%d,%d) → rect=(%d,%d,%dx%d)",
            self._screen_width, self._screen_height,
            roi.top, roi.bottom, roi.left, roi.right,
            capture_rect.left, capture_rect.top,
            capture_rect.width, capture_rect.height,
        )
        try:
            screenshot = self._monitor.capture_region(capture_rect)
        except Exception:
            logger.exception("ROI capture failed")
            self._transition(AgentState.ERROR)
            return
        logger.debug("Captured %d bytes", len(screenshot))
        # Guard image size before sending: oversized ROI PNGs can hit gateway
        # limits and add latency. Shrink the longest edge if configured.
        max_edge = self._config.openclaw.max_image_edge_px
        screenshot = self._processor.downscale_to_max_edge(screenshot, max_edge)
        image_b64 = self._processor.to_base64(screenshot)
        self._last_image_base64 = image_b64

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
            result = await self._analyze_with_retry(
                image_b64, modality, valid_regions
            )
            if self._state != AgentState.ANALYZING:
                logger.info("Analysis result discarded (state changed to %s)", self._state.name)
                return
            self._last_result = result
            self._transition(AgentState.DISPLAYING)
            if self.on_analysis_result:
                self.on_analysis_result(result)
        except TimeoutError:
            logger.error("Analysis timed out")
            if self._state == AgentState.ANALYZING:
                self._transition(AgentState.ERROR)
                if self.on_error:
                    self.on_error("分析逾時")
        except ConnectionError:
            if self._state == AgentState.ANALYZING:
                self._transition(AgentState.RECONNECTING)
                if self.on_error:
                    self.on_error("Gateway 連線中斷")
        except Exception:
            logger.exception("Analysis failed")
            if self._state == AgentState.ANALYZING:
                self._transition(AgentState.ERROR)
                if self.on_error:
                    self.on_error("分析錯誤")

    async def _analyze_with_retry(
        self,
        image_b64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        """Run analyze with a single backoff retry on transient timeout.

        Vision models occasionally time out transiently; one retry avoids
        flapping into ERROR for what is usually a recoverable hiccup.
        ConnectionError is NOT retried here — the caller handles reconnect.
        """
        retries = max(0, self._config.openclaw.analyze_retries)
        backoff = self._config.openclaw.analyze_retry_backoff_sec
        attempt = 0
        while True:
            try:
                return await self._analyzer.analyze(
                    image_b64, modality, valid_regions
                )
            except TimeoutError:
                if attempt >= retries:
                    raise
                attempt += 1
                logger.warning(
                    "Analysis timed out, retrying (%d/%d) after %.1fs backoff",
                    attempt,
                    retries,
                    backoff,
                )
                await asyncio.sleep(backoff)

    async def _tick_error(self) -> None:
        """Auto-recover from ERROR state after a cooldown period (5 seconds)."""
        elapsed = time.monotonic() - self._error_time
        if elapsed < 5.0:
            return  # Wait before retrying

        # Check if viewer is still present
        window = self._monitor.find_target_window(
            self._config.monitor.window_title_keywords
        )
        if window:
            self._target_window = window
            logger.info("Error recovery: viewer found, resuming monitoring")
            self._transition(AgentState.MONITORING)
        else:
            self._target_window = None
            logger.info("Error recovery: viewer lost, returning to waiting")
            self._transition(AgentState.WAITING)

    async def _tick_reconnecting(self) -> None:
        now = time.monotonic()
        if now - self._last_reconnect_attempt < self._config.openclaw.reconnect_interval_sec:
            return  # Throttle: skip this tick, don't block the event loop
        self._last_reconnect_attempt = now

        # If we have a GatewayManager, ensure the process is alive first
        if self._gateway is not None:
            gw_ok = await self._gateway.ensure_running()
            if not gw_ok:
                logger.warning("Gateway restart failed, will retry next tick")
                return

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
