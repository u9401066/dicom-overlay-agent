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
from typing import TYPE_CHECKING

import structlog
from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QInputDialog

from dicom_overlay.application.hooked_analyzer import HookedVisionAnalyzer
from dicom_overlay.application.interpretation_harness import (
    summarize_result_for_followup,
)
from dicom_overlay.application.multi_pass import (
    MultiPassAnalyzer,
    MultiPassInterpreter,
)
from dicom_overlay.application.overlay_agent import OverlayAgent
from dicom_overlay.domain.entities import AgentState, Modality
from dicom_overlay.domain.modality_profile import (
    build_registry,
    set_active_registry,
)
from dicom_overlay.infrastructure.app_paths import app_base_dir
from dicom_overlay.infrastructure.async_bridge import AsyncBridge
from dicom_overlay.infrastructure.clinical_rule_loader import build_clinical_engine
from dicom_overlay.infrastructure.config_loader import load_config, save_roi_config
from dicom_overlay.infrastructure.desktop_settings_store import DesktopSettingsStore
from dicom_overlay.infrastructure.gateway_manager import GatewayManager
from dicom_overlay.infrastructure.hooks.clinical_consistency import (
    ClinicalConsistencyHook,
)
from dicom_overlay.infrastructure.hooks.input_guard import InputGuard
from dicom_overlay.infrastructure.hooks.output_validator import OutputValidator
from dicom_overlay.infrastructure.hooks.rate_limiter import RateLimiter
from dicom_overlay.infrastructure.logging_config import setup_logging
from dicom_overlay.infrastructure.mcp_adapter import McpAdapter
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
from dicom_overlay.infrastructure.overlay_geometry import (
    project_bbox_to_overlay_highlight,
)
from dicom_overlay.infrastructure.region_mapper import RegionMapper
from dicom_overlay.infrastructure.screen_monitor import ImageProcessor, ScreenMonitor
from dicom_overlay.infrastructure.tts_speaker import speak_error, speak_result
from dicom_overlay.infrastructure.vision_probe import VisionSmokeTester
from dicom_overlay.presentation.control_bar import ControlBarWindow
from dicom_overlay.presentation.overlay_window import OverlayWindow
from dicom_overlay.presentation.roi_setup import run_roi_setup
from dicom_overlay.presentation.settings_dialog import SettingsDialog

if TYPE_CHECKING:
    from dicom_overlay.domain.services import VisionAnalyzerService

logger = structlog.get_logger("dicom_overlay")


class _SignalBridge(QObject):
    """Thread-safe bridge: agent callbacks (background) → Qt slots (main)."""

    state_changed = pyqtSignal(object, object)
    analysis_result = pyqtSignal(object)
    pending_analysis = pyqtSignal(str)
    error_msg = pyqtSignal(str)
    chat_done = pyqtSignal(str, str)
    chat_failed = pyqtSignal()
    vision_test_done = pyqtSignal(object)


def _run_selfcheck(base_dir: Path, config_path: Path) -> int:
    """Verify the portable bundle can start; print a report and return exit code.

    0 = all components OK (bundle is ready to run on this machine),
    1 = at least one component missing (prints which).
    """
    rows: list[tuple[str, bool, str]] = [
        ("base_dir", True, str(base_dir)),
        ("config.yaml", config_path.exists(), str(config_path)),
    ]
    gateway = GatewayManager(repo_root=base_dir)
    rows.extend(gateway.verify_runtime())

    all_ok = all(ok for _, ok, _ in rows)
    print("DICOM Overlay Agent — self-check")
    for component, ok, detail in rows:
        mark = "OK " if ok else "FAIL"
        print(f"  [{mark}] {component}: {detail}")
    print("RESULT:", "OK" if all_ok else "FAILED")
    return 0 if all_ok else 1


def _run_explain_rules(base_dir: Path) -> int:
    """Print the active clinical-rule catalogue for human audit; exit 0.

    Surfaces the "對照文字說明" for every live rule (built-in plus any YAML
    overrides under <base>/clinical_rules) without launching the GUI or
    contacting an LLM, so a clinician can review the safety net's logic.
    """
    engine = build_clinical_engine(base_dir / "clinical_rules")
    print("DICOM Overlay Agent — 臨床一致性規則對照表（供人工審核）")
    print(engine.catalogue())
    return 0


def main() -> None:
    # --- Resolve portable base dir (USB plug-and-play) ---
    # When frozen, anchor all runtime paths to the executable's folder, not the
    # launch cwd (which may be System32). See infrastructure/app_paths.py.
    base_dir = app_base_dir()

    # --- Load config ---
    config_path = base_dir / "config.yaml"
    for arg in sys.argv[1:]:
        if arg.startswith("--config="):
            config_path = Path(arg.split("=", 1)[1])
        elif arg == "--config" and sys.argv.index(arg) + 1 < len(sys.argv):
            config_path = Path(sys.argv[sys.argv.index(arg) + 1])

    config = load_config(config_path)

    # --- Setup logging ---
    setup_logging(log_level=config.log_level, log_file=config.log_file)
    logger.info("DICOM Overlay Agent starting...")

    # --- Portable self-check (USB plug-and-play verification) ---
    # `--selfcheck` verifies the bundle can start (node + openclaw + writable
    # base + config) and exits, without launching the GUI or contacting an LLM.
    # Lets a fresh machine confirm "the installer starts correctly" in seconds.
    if "--selfcheck" in sys.argv:
        sys.exit(_run_selfcheck(base_dir, config_path))

    # --- Clinical rule audit (`--explain-rules`) ---
    # Prints the human-readable catalogue of every active clinical-consistency
    # rule and exits, so a reviewer can audit the safety net (built-in + YAML
    # overrides) without launching the GUI or contacting an LLM.
    if "--explain-rules" in sys.argv:
        sys.exit(_run_explain_rules(base_dir))

    # --- Build modality registry (single source of truth, config-extensible) ---
    registry = build_registry(config.modalities)
    set_active_registry(registry)

    # --- Build infrastructure ---
    screen_monitor = ScreenMonitor(hash_algorithm=config.monitor.hash_algorithm)
    image_processor = ImageProcessor()
    region_mapper = RegionMapper(config.region_maps)
    openclaw_client = OpenClawClient(
        gateway_url=config.openclaw.gateway_url,
        timeout_sec=config.openclaw.timeout_sec,
        reconnect_interval_sec=config.openclaw.reconnect_interval_sec,
        connect_timeout_sec=config.openclaw.connect_timeout_sec,
        inference_timeout_sec=config.openclaw.inference_timeout_sec,
        registry=registry,
    )

    # --- Build hook pipeline (guardrails) ---
    # ClinicalConsistencyHook runs AFTER OutputValidator so it sees a
    # schema-validated result, then applies the data-driven, guideline-grounded
    # safety net (escalate-only, flag-for-review). Rule packs in
    # <base>/clinical_rules/*.rules.yaml override the built-in rules, so updating
    # a diagnostic guideline is a data edit — no code change.
    clinical_engine = build_clinical_engine(app_base_dir() / "clinical_rules")
    hooks = [
        RateLimiter(),
        InputGuard(registry=registry),
        OutputValidator(registry=registry),
        ClinicalConsistencyHook(engine=clinical_engine),
    ]
    hooked_analyzer = HookedVisionAnalyzer(inner=openclaw_client, hooks=hooks)

    # --- Optional multi-pass interpretation (coarse → crop abnormal → refine) ---
    # Off by default (latency / token cost). When enabled it wraps the hooked
    # analyzer as a drop-in VisionAnalyzerService, so OverlayAgent is unchanged.
    vision_analyzer: VisionAnalyzerService = hooked_analyzer
    if config.analysis.multi_pass_enabled:
        interpreter = MultiPassInterpreter(
            analyzer=hooked_analyzer,
            cropper=image_processor.crop_region_base64,
            max_zoom_targets=config.analysis.multi_pass_max_zoom_targets,
        )
        vision_analyzer = MultiPassAnalyzer(
            inner=hooked_analyzer, interpreter=interpreter
        )
        logger.info(
            "multi_pass_enabled",
            max_zoom_targets=config.analysis.multi_pass_max_zoom_targets,
        )

    # --- MCP adapter (aligned with openclaw-mcp-adapter plugin) ---
    mcp_adapter = McpAdapter()  # No servers configured yet; use register_provider()

    # --- Build application layer ---
    agent = OverlayAgent(
        config=config,
        screen_monitor=screen_monitor,
        image_processor=image_processor,
        vision_analyzer=vision_analyzer,
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
    control_bar.set_trigger_mode(config.analysis.trigger_mode)
    screen = app.primaryScreen()
    if screen:
        geo = screen.geometry()
        # Set screen dimensions/origin for screen-based ROI capture.
        dpr = screen.devicePixelRatio()
        agent._screen_width = int(geo.width() * dpr)
        agent._screen_height = int(geo.height() * dpr)
        # Screen origin on the virtual desktop (physical px) — non-zero on
        # multi-monitor layouts; required so mss grabs the correct screen.
        agent._screen_left = int(geo.x() * dpr)
        agent._screen_top = int(geo.y() * dpr)
        agent._dpr = dpr
        control_bar.position_bottom_right(
            geo.width(), geo.height(), geo.x(), geo.y()
        )

    # --- Async bridge (background thread for all agent operations) ---
    bridge = AsyncBridge()
    bridge.start()

    signals = _SignalBridge()

    # ─── Agent callbacks (called from bridge thread → emit signals) ───
    agent.on_state_change = signals.state_changed.emit
    agent.on_analysis_result = signals.analysis_result.emit
    agent.on_pending_analysis = lambda _reason: signals.pending_analysis.emit(
        "New image ready. Click Analyze."
    )
    agent.on_error = signals.error_msg.emit

    # ─── Qt slots (run on main thread) ───
    modality_index = [0]
    # Cycle through registry-supported modalities that map to a Modality enum.
    _known_values = {m.value for m in Modality}
    modality_cycle = [
        Modality(k) for k in registry.supported_keys() if k in _known_values
    ] or [Modality.EKG]
    _unmapped = [k for k in registry.supported_keys() if k not in _known_values]
    if _unmapped:
        logger.warning(
            "Config modalities %s are registered but not in the Modality enum; "
            "they cannot be selected via the cycle button until added to the enum.",
            _unmapped,
        )

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
            # Region percentages are relative to the ROI-cropped image,
            # so map them to the cropped content area — NOT the full window.
            roi = config.phi_roi
            from dicom_overlay.domain.entities import Severity
            from dicom_overlay.domain.entities import WindowRect as WR
            from dicom_overlay.infrastructure.dpi import get_dpi_scale
            dpr = get_dpi_scale()
            # ROI is screen-relative in physical pixels;
            # content_rect = the captured area in physical pixels.
            content_rect = WR(
                left=roi.left,
                top=roi.top,
                width=agent._screen_width - roi.left - roi.right,
                height=agent._screen_height - roi.top - roi.bottom,
            )
            for finding in result.findings:
                # Only highlight abnormal findings (skip normal/info)
                if finding.severity in (Severity.NORMAL, Severity.INFO):
                    continue
                # Prefer AI-provided bboxes (dynamic, precise)
                if finding.bboxes:
                    for bbox in finding.bboxes:
                        projected = project_bbox_to_overlay_highlight(
                            bbox=bbox,
                            image_rect=content_rect,
                            dpr=dpr,
                            severity=finding.severity.value,
                            label=finding.label,
                        )
                        if (
                            projected.calibration.was_clamped
                            or not projected.calibration.ok
                        ):
                            logger.warning(
                                "bbox_projection_calibrated",
                                finding_id=finding.id,
                                label=finding.label,
                                was_clamped=projected.calibration.was_clamped,
                                max_edge_drift_px=(
                                    projected.calibration.max_edge_drift_px
                                ),
                            )
                        highlights.append(projected.highlight)
                else:
                    # Fallback: use static region maps from config
                    for region_name in finding.regions:
                        rect = region_mapper.get_region_rect(
                            region_name, result.modality
                        )
                        if rect and agent.target_window:
                            sx, sy, sw, sh = region_mapper.to_screen_rect(
                                rect, content_rect
                            )
                            lx = round(sx / dpr)
                            ly = round(sy / dpr)
                            lw = round(sw / dpr)
                            lh = round(sh / dpr)
                            highlights.append(
                                (lx, ly, lw, lh, finding.severity.value, finding.label)
                            )

        if agent.target_window:
            overlay.position_over_window(agent.target_window)
        overlay.show_result(result, highlights)
        control_bar.set_pending_analysis(False)
        if config.overlay.tts_enabled:
            speak_result(result.modality.value, result.severity.value, result.summary)

    def on_error(msg: str):
        if msg.startswith("New image ready"):
            control_bar.set_pending_analysis(True)
        control_bar.set_status(f"⚠ {msg}")
        if config.overlay.tts_enabled:
            speak_error(msg)

    def on_pending_analysis(msg: str) -> None:
        control_bar.set_pending_analysis(True)
        control_bar.set_status(msg)

    signals.state_changed.connect(on_state_change)
    signals.analysis_result.connect(on_analysis_result)
    signals.pending_analysis.connect(on_pending_analysis)
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
        control_bar.set_pending_analysis(False)
        bridge.submit(agent.trigger_manual())

    settings_store = DesktopSettingsStore(repo_root=base_dir, config_path=config_path)

    def on_trigger_mode_changed(mode) -> None:
        agent.set_trigger_mode(mode)
        settings_store.save_trigger_mode(mode)
        control_bar.set_trigger_mode(mode)
        control_bar.set_status(f"Mode: {mode.value}")

    def on_modality_cycle():
        modality_index[0] = (modality_index[0] + 1) % len(modality_cycle)
        mod = modality_cycle[modality_index[0]]

        async def _set():
            agent.set_modality(mod)
        bridge.submit(_set())
        control_bar.set_modality(mod.value)

    def on_dismiss():
        """Quit the entire application (cleanup runs after app.exec())."""
        logger.info("User dismissed — shutting down")
        overlay.dismiss()
        tick_timer.stop()
        app.quit()

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

    def open_settings_dialog() -> None:
        dialog = SettingsDialog(
            repo_root=base_dir,
            current_mode=agent.trigger_mode,
            parent=control_bar,
        )
        dialog.trigger_mode_saved.connect(on_trigger_mode_changed)
        dialog.roi_setup_requested.connect(open_settings_roi_setup)
        dialog.vision_test_requested.connect(_run_vision_test)
        dialog.exec()

    def _run_vision_test(_profile) -> None:
        control_bar.set_status("Testing image support...")
        tester = VisionSmokeTester(openclaw_client)
        future = bridge.submit(tester.probe())

        def _done(f):
            try:
                signals.vision_test_done.emit(f.result())
            except Exception as exc:
                logger.exception("Vision smoke test failed")
                signals.error_msg.emit(f"Vision test failed: {exc}")

        future.add_done_callback(_done)

    def _on_vision_test_done(result) -> None:
        if result.ok:
            control_bar.set_status(
                f"Vision OK ({result.model_used or 'configured model'})"
            )
        else:
            control_bar.set_status(f"Vision failed: {result.message}")

    control_bar.pause_clicked.connect(on_pause)
    control_bar.resume_clicked.connect(on_resume)
    control_bar.retrigger_clicked.connect(on_retrigger)
    control_bar.modality_cycle.connect(on_modality_cycle)
    control_bar.trigger_mode_changed.connect(on_trigger_mode_changed)
    control_bar.settings_clicked.connect(open_settings_dialog)
    control_bar.dismiss_clicked.connect(on_dismiss)
    signals.vision_test_done.connect(_on_vision_test_done)

    # ─── Chat handler (non-blocking) ───
    def on_chat() -> None:
        text, ok = QInputDialog.getText(
            control_bar, "問 AI", "請輸入問題:",
        )
        if not ok or not text.strip():
            return

        question = text.strip()
        logger.info("User chat question: %s", question)

        if agent.target_window:
            overlay.position_over_window(agent.target_window)
        overlay.show_chat_waiting(question)

        if agent.last_image_base64 and agent.last_result:
            context = summarize_result_for_followup(agent.last_result)
            future = bridge.submit(
                openclaw_client.chat_about_image(
                    question,
                    image_base64=agent.last_image_base64,
                    context=context,
                )
            )
        else:
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

    # ─── Start Gateway + agent + MCP adapter ───
    gateway = GatewayManager(repo_root=base_dir)
    try:
        gateway.start()
        ready = bridge.submit(gateway.wait_ready(timeout_sec=15)).result(timeout=20)
        if not ready:
            logger.error("Gateway failed to start — continuing without it")
        # Let the agent auto-restart Gateway if it crashes during runtime
        agent._gateway = gateway
    except FileNotFoundError as exc:
        logger.warning("Gateway not available: %s", exc)
        gateway = None  # type: ignore[assignment]

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

    if gateway is not None:
        try:
            gateway.stop()
        except Exception:
            logger.exception("Error during Gateway shutdown")

    bridge.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
