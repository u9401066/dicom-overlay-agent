"""DICOM Overlay Agent — main entry point.

Wires together all DDD layers and starts the PyQt6 event loop.

Threading model:
  - Qt main thread: UI rendering, signal/slot delivery
  - AsyncBridge thread: asyncio event loop for all agent + OpenClaw operations
  - Agent callbacks emit pyqtSignals from the bridge thread; Qt delivers them
    to the main thread via QueuedConnection (automatic cross-thread delivery).
"""

from __future__ import annotations

import sys
from pathlib import Path

import structlog
from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QInputDialog

from dicom_overlay.application.hooked_analyzer import HookedVisionAnalyzer
from dicom_overlay.application.overlay_agent import OverlayAgent
from dicom_overlay.domain.entities import AgentState, Modality
from dicom_overlay.infrastructure.async_bridge import AsyncBridge
from dicom_overlay.infrastructure.config_loader import load_config, save_roi_config
from dicom_overlay.infrastructure.hooks.input_guard import InputGuard
from dicom_overlay.infrastructure.hooks.output_validator import OutputValidator
from dicom_overlay.infrastructure.hooks.rate_limiter import RateLimiter
from dicom_overlay.infrastructure.logging_config import setup_logging
from dicom_overlay.infrastructure.mcp_adapter import McpAdapter
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
from dicom_overlay.infrastructure.region_mapper import RegionMapper
from dicom_overlay.infrastructure.screen_monitor import ImageProcessor, ScreenMonitor
from dicom_overlay.infrastructure.tts_speaker import speak_error, speak_result
from dicom_overlay.presentation.control_bar import ControlBarWindow
from dicom_overlay.presentation.overlay_window import OverlayWindow
from dicom_overlay.presentation.roi_setup import run_roi_setup

logger = structlog.get_logger("dicom_overlay")

_MODALITY_CYCLE = [Modality.EKG, Modality.CXR, Modality.CT_BRAIN]


class _SignalBridge(QObject):
    """Thread-safe bridge: agent callbacks (background) → Qt slots (main)."""

    state_changed = pyqtSignal(object, object)
    analysis_result = pyqtSignal(object)
    error_msg = pyqtSignal(str)
    chat_done = pyqtSignal(str, str)
    chat_failed = pyqtSignal()


def main() -> None:
    # --- Load config ---
    config_path = Path("config.yaml")
    for arg in sys.argv[1:]:
        if arg.startswith("--config="):
            config_path = Path(arg.split("=", 1)[1])
        elif arg == "--config" and sys.argv.index(arg) + 1 < len(sys.argv):
            config_path = Path(sys.argv[sys.argv.index(arg) + 1])

    config = load_config(config_path)

    # --- Setup logging ---
    setup_logging(log_level=config.log_level, log_file=config.log_file)
    logger.info("DICOM Overlay Agent starting...")

    # --- Build infrastructure ---
    screen_monitor = ScreenMonitor()
    image_processor = ImageProcessor()
    region_mapper = RegionMapper(config.region_maps)
    openclaw_client = OpenClawClient(
        gateway_url=config.openclaw.gateway_url,
        timeout_sec=config.openclaw.timeout_sec,
        reconnect_interval_sec=config.openclaw.reconnect_interval_sec,
    )

    # --- Build hook pipeline (guardrails) ---
    hooks = [
        RateLimiter(),
        InputGuard(),
        OutputValidator(),
    ]
    hooked_analyzer = HookedVisionAnalyzer(inner=openclaw_client, hooks=hooks)

    # --- MCP adapter (aligned with openclaw-mcp-adapter plugin) ---
    mcp_adapter = McpAdapter()  # No servers configured yet; use register_provider()

    # --- Build application layer ---
    agent = OverlayAgent(
        config=config,
        screen_monitor=screen_monitor,
        image_processor=image_processor,
        vision_analyzer=hooked_analyzer,
        region_mapper=region_mapper,
    )

    # --- Build presentation layer ---
    app = QApplication(sys.argv)
    app.setApplicationName("DICOM Overlay Agent")
    app.setQuitOnLastWindowClosed(False)

    overlay = OverlayWindow()
    overlay.configure(
        display_duration_sec=config.overlay.display_duration_sec,
        critical_persist=config.overlay.critical_persist,
    )

    control_bar = ControlBarWindow()
    screen = app.primaryScreen()
    if screen:
        geo = screen.geometry()
        control_bar.position_bottom_right(geo.width(), geo.height())

    # --- Async bridge (background thread for all agent operations) ---
    bridge = AsyncBridge()
    bridge.start()

    signals = _SignalBridge()

    # ─── Agent callbacks (called from bridge thread → emit signals) ───
    agent.on_state_change = signals.state_changed.emit
    agent.on_analysis_result = signals.analysis_result.emit
    agent.on_error = signals.error_msg.emit

    # ─── Qt slots (run on main thread) ───
    modality_index = [0]

    def on_state_change(_old: AgentState, new: AgentState) -> None:
        control_bar.update_state(new)
        if new == AgentState.PAUSED:
            control_bar.set_paused(True)
        elif new == AgentState.MONITORING:
            control_bar.set_paused(False)

    def on_analysis_result(result):
        logger.info(
            "Result: %s severity=%s findings=%d",
            result.modality.value,
            result.severity.value,
            len(result.findings),
        )
        # Calculate highlight rects
        highlights = []
        if agent.target_window and config.overlay.region_highlights:
            for finding in result.findings:
                for region_name in finding.regions:
                    rect = region_mapper.get_region_rect(
                        region_name, result.modality
                    )
                    if rect and agent.target_window:
                        sx, sy, sw, sh = region_mapper.to_screen_rect(
                            rect, agent.target_window
                        )
                        # Convert to overlay-local coords
                        lx = sx - agent.target_window.left
                        ly = sy - agent.target_window.top
                        highlights.append(
                            (lx, ly, sw, sh, finding.severity.value, finding.label)
                        )

        if agent.target_window:
            overlay.position_over_window(agent.target_window)
        overlay.show_result(result, highlights)
        if config.overlay.tts_enabled:
            speak_result(result.modality.value, result.severity.value, result.summary)

    def on_error(msg: str):
        control_bar.set_status(f"⚠ {msg}")
        if config.overlay.tts_enabled:
            speak_error(msg)

    signals.state_changed.connect(on_state_change)
    signals.analysis_result.connect(on_analysis_result)
    signals.error_msg.connect(on_error)

    # ─── Display timeout — single source of truth (overlay timer) ───
    def _on_display_expired() -> None:
        async def _timeout():
            agent.on_display_timeout()
        bridge.submit(_timeout())

    overlay.display_expired.connect(_on_display_expired)

    # ─── Non-blocking tick ───
    _tick_busy = [False]

    def on_tick():
        if _tick_busy[0]:
            return
        _tick_busy[0] = True
        future = bridge.submit(agent.tick())

        def _done(f):
            _tick_busy[0] = False
            try:
                f.result()
            except Exception:
                logger.exception("Tick error")

        future.add_done_callback(_done)

    tick_timer = QTimer()
    tick_timer.timeout.connect(on_tick)
    tick_timer.start(config.monitor.polling_interval_ms)

    # ─── Control bar signals (state-modifying → via bridge) ───
    def on_pause():
        async def _p():
            agent.pause()
        bridge.submit(_p())

    def on_resume():
        async def _r():
            agent.resume()
        bridge.submit(_r())

    def on_retrigger():
        bridge.submit(agent.trigger_manual())

    def on_modality_cycle():
        modality_index[0] = (modality_index[0] + 1) % len(_MODALITY_CYCLE)
        mod = _MODALITY_CYCLE[modality_index[0]]

        async def _set():
            agent.set_modality(mod)
        bridge.submit(_set())
        control_bar.set_modality(mod.value)

    def on_dismiss():
        overlay.dismiss()

    def open_settings_roi_setup() -> None:
        roi = run_roi_setup(app, agent.target_window, config.phi_roi)
        if roi is None:
            control_bar.set_status("ROI 設定已取消")
            return
        save_roi_config(config_path, roi)
        config.phi_roi = roi

        async def _roi():
            agent.on_roi_setup_complete(roi)
        bridge.submit(_roi())
        control_bar.set_status(
            f"ROI 已更新 top={roi.top} bottom={roi.bottom}"
            f" left={roi.left} right={roi.right}"
        )

    control_bar.pause_clicked.connect(on_pause)
    control_bar.resume_clicked.connect(on_resume)
    control_bar.retrigger_clicked.connect(on_retrigger)
    control_bar.modality_cycle.connect(on_modality_cycle)
    control_bar.settings_clicked.connect(open_settings_roi_setup)
    control_bar.dismiss_clicked.connect(on_dismiss)

    # ─── Chat handler (non-blocking) ───
    def on_chat() -> None:
        text, ok = QInputDialog.getText(
            control_bar, "問 AI", "請輸入問題：",
        )
        if not ok or not text.strip():
            return

        question = text.strip()
        logger.info("User chat question: %s", question)

        if agent.target_window:
            overlay.position_over_window(agent.target_window)
        overlay.show_chat_waiting(question)

        future = bridge.submit(openclaw_client.chat(question))

        def _chat_done(f):
            try:
                answer = f.result()
                signals.chat_done.emit(question, answer)
            except Exception:
                logger.exception("Chat request failed")
                signals.chat_failed.emit()

        future.add_done_callback(_chat_done)

    def _show_chat_response(question: str, answer: str) -> None:
        overlay.show_chat_response(question, answer)
        control_bar.set_status("💬 回覆已顯示")

    def _on_chat_error() -> None:
        control_bar.set_status("⚠ 聊天請求失敗")
        overlay.dismiss()

    signals.chat_done.connect(_show_chat_response)
    signals.chat_failed.connect(_on_chat_error)
    control_bar.chat_clicked.connect(on_chat)

    # ─── Hotkeys (application-wide shortcuts) ───
    def _toggle_enable() -> None:
        if agent.state == AgentState.PAUSED:
            on_resume()
        else:
            on_pause()

    hk = config.hotkeys
    shortcut_trigger = QShortcut(
        QKeySequence(hk.trigger_manual), control_bar,
    )
    shortcut_trigger.setContext(Qt.ShortcutContext.ApplicationShortcut)
    shortcut_trigger.activated.connect(on_retrigger)

    shortcut_dismiss = QShortcut(
        QKeySequence(hk.dismiss_overlay), control_bar,
    )
    shortcut_dismiss.setContext(Qt.ShortcutContext.ApplicationShortcut)
    shortcut_dismiss.activated.connect(on_dismiss)

    shortcut_toggle = QShortcut(
        QKeySequence(hk.toggle_enable), control_bar,
    )
    shortcut_toggle.setContext(Qt.ShortcutContext.ApplicationShortcut)
    shortcut_toggle.activated.connect(_toggle_enable)

    # ─── Start agent + MCP adapter (blocking OK — before Qt event loop) ───
    bridge.submit(agent.start()).result(timeout=30)
    bridge.submit(mcp_adapter.start()).result(timeout=10)

    # --- Show UI ---
    control_bar.show()
    control_bar.set_modality(agent.current_modality.value)

    if agent.state == AgentState.SETUP:
        QTimer.singleShot(0, open_settings_roi_setup)

    logger.info("Agent started — state: %s", agent.state.name)

    # --- Run Qt event loop ---
    exit_code = app.exec()

    # --- Cleanup ---
    tick_timer.stop()

    try:
        bridge.submit(mcp_adapter.stop()).result(timeout=5)
    except Exception:
        logger.exception("Error during MCP adapter shutdown")

    try:
        bridge.submit(agent.stop()).result(timeout=10)
    except Exception:
        logger.exception("Error during agent shutdown")

    bridge.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
