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
from uuid import uuid4

import structlog
from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QInputDialog

from dicom_overlay.application.annotation_accumulator import AnnotationAccumulator
from dicom_overlay.application.hooked_analyzer import HookedVisionAnalyzer
from dicom_overlay.application.interpretation_harness import (
    summarize_result_for_followup,
)
from dicom_overlay.application.multi_pass import (
    MultiPassAnalyzer,
    MultiPassInterpreter,
)
from dicom_overlay.application.overlay_agent import OverlayAgent, ReviewSnapshot
from dicom_overlay.application.review_chat import (
    ReviewChatResponse,
    build_region_review_prompt,
    match_selected_finding,
    parse_region_review_response,
    summarize_regional_refinement,
)
from dicom_overlay.domain.entities import (
    AgentState,
    Finding,
    FindingDelta,
    FindingOp,
    Modality,
    RegionRect,
    WindowRect,
)
from dicom_overlay.domain.modality_profile import (
    build_registry,
    set_active_registry,
)
from dicom_overlay.infrastructure.app_paths import app_base_dir
from dicom_overlay.infrastructure.async_bridge import AsyncBridge
from dicom_overlay.infrastructure.bbox_signal_calibrator import calibrate_ekg_bboxes
from dicom_overlay.infrastructure.clinical_rule_loader import build_clinical_engine
from dicom_overlay.infrastructure.config_loader import load_config, save_roi_config
from dicom_overlay.infrastructure.desktop_review_exporter import export_desktop_review
from dicom_overlay.infrastructure.desktop_settings_store import DesktopSettingsStore
from dicom_overlay.infrastructure.gateway_manager import GatewayManager
from dicom_overlay.infrastructure.hooks.bbox_calibration import BboxCalibrationHook
from dicom_overlay.infrastructure.hooks.clinical_consistency import (
    ClinicalConsistencyHook,
)
from dicom_overlay.infrastructure.hooks.input_guard import InputGuard
from dicom_overlay.infrastructure.hooks.output_validator import OutputValidator
from dicom_overlay.infrastructure.hooks.rate_limiter import RateLimiter
from dicom_overlay.infrastructure.logging_config import setup_logging
from dicom_overlay.infrastructure.mcp_adapter import McpAdapter
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
from dicom_overlay.infrastructure.overlay_highlight_builder import (
    build_ai_bbox_highlights,
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
    chat_done = pyqtSignal(str, str, int, int)
    review_chat_done = pyqtSignal(str, object, int, object, object, int)
    review_apply_done = pyqtSignal(object, object)
    review_apply_failed = pyqtSignal(str)
    review_outcome_done = pyqtSignal(str)
    review_outcome_failed = pyqtSignal(str)
    chat_failed = pyqtSignal(int)
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
    required_skills = (
        "dicom-ekg-analysis",
        "dicom-cxr-analysis",
        "dicom-ct-brain-analysis",
    )
    skills_root = base_dir / "openclaw" / "workspace" / "skills"
    missing_skills = [
        name
        for name in required_skills
        if not (skills_root / name / "SKILL.md").is_file()
    ]
    rows.append(
        (
            "skills",
            not missing_skills,
            (
                str(skills_root)
                if not missing_skills
                else f"missing: {', '.join(missing_skills)}"
            ),
        )
    )
    harness_root = (
        base_dir / "openclaw" / "workspace" / "plugins" / "dicom-overlay-agent-harness"
    )
    harness_files = (
        harness_root / "manifest.json",
        harness_root / "openclaw.plugin.json",
        harness_root / "package.json",
        harness_root / "index.js",
    )
    rows.append(
        (
            "harness_plugin",
            all(path.is_file() for path in harness_files),
            str(harness_root),
        )
    )
    clinical_rules = base_dir / "clinical_rules"
    rows.append(
        (
            "clinical_rules",
            clinical_rules.is_dir() and any(clinical_rules.iterdir()),
            str(clinical_rules),
        )
    )
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

    # --- Setup logging ---
    # Diagnostic commands above must not leave runtime logs in a fresh bundle.
    setup_logging(log_level=config.log_level, log_file=config.log_file)
    logger.info("DICOM Overlay Agent starting...")

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
        base_dir=base_dir,
    )

    # --- Build hook pipeline (guardrails) ---
    # ClinicalConsistencyHook runs AFTER OutputValidator so it sees a
    # schema-validated result, then applies the data-driven, guideline-grounded
    # safety net (optional severity floor, flag-for-review). Rule packs in
    # <base>/clinical_rules/*.rules.yaml override the built-in rules, so updating
    # a diagnostic guideline is a data edit — no code change.
    clinical_engine = build_clinical_engine(app_base_dir() / "clinical_rules")

    def build_guardrail_hooks(*, include_bbox_calibration: bool):
        hooks = [
            RateLimiter(),
            InputGuard(registry=registry),
            ClinicalConsistencyHook(engine=clinical_engine),
        ]
        if include_bbox_calibration:
            hooks.append(BboxCalibrationHook())
        hooks.append(OutputValidator(registry=registry))
        return hooks

    hooked_analyzer = HookedVisionAnalyzer(
        inner=openclaw_client,
        hooks=build_guardrail_hooks(include_bbox_calibration=True),
    )

    # --- Bounded multi-pass interpretation (coarse → crop abnormal → refine) ---
    def build_multi_pass_analyzer(max_zoom_targets: int) -> HookedVisionAnalyzer:
        interpreter = MultiPassInterpreter(
            analyzer=openclaw_client,
            cropper=image_processor.crop_region_base64,
            bbox_calibrator=calibrate_ekg_bboxes,
            max_zoom_targets=max_zoom_targets,
        )
        analyzer = MultiPassAnalyzer(inner=openclaw_client, interpreter=interpreter)
        return HookedVisionAnalyzer(
            inner=analyzer,
            hooks=build_guardrail_hooks(include_bbox_calibration=False),
        )

    multi_pass_analyzer = build_multi_pass_analyzer(
        config.analysis.multi_pass_max_zoom_targets
    )
    # Guardrails wrap the complete coarse -> crop -> refine transaction once.
    # The single-pass path additionally calibrates boxes through its hook;
    # MultiPass performs the same operation internally against the source ROI.
    vision_analyzer: VisionAnalyzerService = (
        multi_pass_analyzer if config.analysis.multi_pass_enabled else hooked_analyzer
    )
    if config.analysis.multi_pass_enabled:
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
        annotation_accumulator=AnnotationAccumulator(),
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
        control_bar.position_bottom_right(geo.width(), geo.height(), geo.x(), geo.y())

    # --- Async bridge (background thread for all agent operations) ---
    bridge = AsyncBridge()
    bridge.start()

    signals = _SignalBridge()
    _pending_review: list[
        tuple[FindingDelta, int, dict[str, object], list[dict[str, object]]] | None
    ] = [None]
    _chat_request_id = [0]

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

    def _current_review_snapshot() -> ReviewSnapshot | None:
        return agent.displayed_review_snapshot

    def on_state_change(_old: AgentState, new: AgentState) -> None:
        control_bar.update_state(new)
        if new == AgentState.PAUSED:
            control_bar.set_paused(True)
        elif new == AgentState.MONITORING:
            control_bar.set_paused(False)

    def on_analysis_result(
        result,
        *,
        announce: bool = True,
        preserve_user_regions: bool = False,
    ):
        # Invalidate every in-flight follow-up before replacing the visible image.
        _chat_request_id[0] += 1
        _pending_review[0] = None
        overlay.clear_chat()
        if not preserve_user_regions:
            overlay.clear_user_regions()
        logger.info(
            "Result: %s severity=%s findings=%d",
            result.modality.value,
            result.severity.value,
            len(result.findings),
        )
        # Position first so every projected box uses the same target-display
        # coordinate frame as the screenshot that was actually analyzed.
        highlights: list[tuple[int, int, int, int, str, str, str]] = []
        overlay_content_rect: tuple[int, int, int, int] | None = None
        coordinate_frame = None
        if agent.target_window:
            coordinate_frame = overlay.position_over_window(
                agent.target_window,
                agent.display_frame,
            )

        snapshot = agent.review_snapshot
        content_rect = (
            snapshot.capture_rect
            if snapshot is not None and snapshot.result is result
            else agent.last_capture_rect
        )
        if content_rect is None and agent.target_window:
            try:
                content_rect = agent._get_roi_rect()
            except ValueError:
                logger.exception("Cannot map result: ROI exceeds target display")

        if coordinate_frame is not None and content_rect is not None:
            local_content = coordinate_frame.physical_rect_to_local(content_rect)
            overlay_content_rect = (
                local_content.x,
                local_content.y,
                local_content.w,
                local_content.h,
            )

        if (
            coordinate_frame is not None
            and content_rect is not None
            and config.overlay.region_highlights
        ):
            # Region percentages are relative to the ROI-cropped image,
            # so map them to the exact captured content area, not the window.
            from dicom_overlay.domain.entities import Severity

            for finding in result.findings:
                # Normal findings stay in the report. Info findings with boxes
                # are intentionally visible/clickable for uncertainty review.
                if finding.severity is Severity.NORMAL:
                    continue
                # Prefer AI-provided bboxes (dynamic, precise)
                if finding.bboxes:
                    built = build_ai_bbox_highlights(
                        findings=[finding],
                        image_rect=content_rect,
                        coordinate_frame=coordinate_frame,
                    )
                    highlights.extend(built.highlights)
                    for audit_row in built.audit_rows:
                        log_method = logger.info if audit_row.drawn else logger.warning
                        log_method(
                            "bbox_projection_calibrated",
                            **audit_row.to_dict(),
                        )
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
                            logical = coordinate_frame.physical_rect_to_local(
                                WindowRect(sx, sy, sw, sh)
                            )
                            highlights.append(
                                (
                                    logical.x,
                                    logical.y,
                                    logical.w,
                                    logical.h,
                                    finding.severity.value,
                                    finding.label,
                                    finding.id,
                                )
                            )
        overlay.show_result(
            result,
            highlights,
            content_rect=overlay_content_rect,
        )
        control_bar.set_pending_analysis(False)
        if announce and config.overlay.tts_enabled:
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

    def on_analysis_settings_changed(enabled: bool, max_targets: int) -> None:
        nonlocal multi_pass_analyzer
        multi_pass_analyzer = build_multi_pass_analyzer(max_targets)
        agent.set_vision_analyzer(multi_pass_analyzer if enabled else hooked_analyzer)
        config.analysis.multi_pass_enabled = enabled
        config.analysis.multi_pass_max_zoom_targets = max_targets
        settings_store.save_analysis_settings(
            multi_pass_enabled=enabled,
            max_zoom_targets=max_targets,
        )
        state = "on" if enabled else "off"
        control_bar.set_status(f"Multi-pass: {state} ({max_targets} targets)")

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
        roi = run_roi_setup(
            app,
            agent.target_window,
            config.phi_roi,
            agent.display_frame,
        )
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
            multi_pass_enabled=config.analysis.multi_pass_enabled,
            multi_pass_max_zoom_targets=(config.analysis.multi_pass_max_zoom_targets),
            config_path=config_path,
            parent=control_bar,
        )
        dialog.trigger_mode_saved.connect(on_trigger_mode_changed)
        dialog.analysis_settings_saved.connect(on_analysis_settings_changed)
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

    def on_interaction_mode_changed(mode: str) -> None:
        overlay.set_interaction_mode(mode)
        labels = {
            "passive": "Overlay click-through",
            "inspect": "Select an AI box",
            "annotate": "Draw a review region",
        }
        control_bar.set_status(labels.get(mode, mode))

    control_bar.interaction_mode_changed.connect(on_interaction_mode_changed)

    def on_export_review() -> None:
        snapshot = _current_review_snapshot()
        if snapshot is None:
            control_bar.set_status("Analyze an image before export")
            return
        try:
            user_regions = [RegionRect(*values) for values in overlay.user_regions]
            review_path = export_desktop_review(
                image_base64=snapshot.image_base64,
                result=snapshot.result,
                output_root=app_base_dir() / "data" / "exports",
                user_regions=user_regions,
            )
        except Exception:
            logger.exception("Desktop review export failed")
            control_bar.set_status("Export failed")
            return
        control_bar.set_status(f"Exported: {review_path.parent.name}")

    control_bar.export_clicked.connect(on_export_review)

    # ─── Chat handler (non-blocking) ───
    def _begin_chat_request() -> int:
        _chat_request_id[0] += 1
        _pending_review[0] = None
        overlay.clear_chat_proposal()
        return _chat_request_id[0]

    def _submit_image_chat(
        *,
        question: str,
        image_base64: str,
        context: str,
        revision: int,
    ) -> None:
        request_id = _begin_chat_request()
        if agent.target_window:
            overlay.position_over_window(agent.target_window, agent.display_frame)
        overlay.show_chat_waiting(question)
        future = bridge.submit(
            openclaw_client.chat_about_image(
                question,
                image_base64=image_base64,
                context=context,
            )
        )

        def _chat_done(f):
            try:
                answer = f.result()
                signals.chat_done.emit(question, answer, revision, request_id)
            except Exception:
                logger.exception("Chat request failed")
                signals.chat_failed.emit(request_id)

        future.add_done_callback(_chat_done)

    def _submit_region_review(
        *,
        question: str,
        crop_base64: str,
        source_crop_bytes: bytes,
        snapshot: ReviewSnapshot,
        selected_region: RegionRect,
        selected_finding: Finding | None,
        allow_add: bool,
    ) -> None:
        current_result = snapshot.result
        revision = snapshot.revision
        request_id = _begin_chat_request()
        try:
            signal_audit = {
                "status": "ok",
                **image_processor.image_quality_profile(source_crop_bytes),
            }
        except Exception:
            logger.exception("Interactive crop signal audit failed")
            signal_audit = {"status": "error", "low_signal": True}
        new_finding_id = f"review-{uuid4().hex[:12]}"
        if agent.target_window:
            overlay.position_over_window(agent.target_window, agent.display_frame)
        overlay.show_chat_waiting(question)

        async def _run_regional_review():
            turn_trace: list[dict[str, object]] = []
            refinement_evidence = ""
            if config.analysis.multi_pass_enabled:
                if signal_audit.get("low_signal") is True:
                    turn_trace.append(
                        {
                            "stage": "regional_refine",
                            "status": "skipped",
                            "reason": "low_signal_or_source_resolution",
                        }
                    )
                else:
                    try:
                        refinement = await openclaw_client.refine(
                            crop_base64,
                            current_result.modality,
                            region_mapper.get_valid_regions(current_result.modality),
                            hypothesis=selected_finding,
                            crop_region=selected_region,
                        )
                        refinement_evidence = summarize_regional_refinement(
                            refinement,
                            expected_target_id=(
                                selected_finding.id if selected_finding else None
                            ),
                            allow_add=allow_add,
                        )
                        turn_trace.append(
                            {
                                "stage": "regional_refine",
                                "status": "completed",
                                **openclaw_client.last_run_trace(),
                            }
                        )
                    except Exception as exc:
                        logger.exception("Bounded regional refinement failed")
                        turn_trace.append(
                            {
                                "stage": "regional_refine",
                                "status": "failed",
                                "error_type": type(exc).__name__,
                            }
                        )

            prompt = build_region_review_prompt(
                user_question=question,
                prior_context=summarize_result_for_followup(current_result),
                selected_region=selected_region,
                selected_finding=selected_finding,
                local_signal_audit=signal_audit,
                refinement_evidence=refinement_evidence,
                allow_add=allow_add,
            )
            (
                raw_response,
                final_trace,
            ) = await openclaw_client.review_region_about_image_with_trace(
                prompt,
                image_base64=crop_base64,
            )
            turn_trace.append(
                {
                    "stage": "regional_structured_review",
                    "status": "completed",
                    **final_trace,
                }
            )
            return raw_response, turn_trace

        future = bridge.submit(_run_regional_review())

        def _review_done(f):
            try:
                raw_response, turn_trace = f.result()
                response = parse_region_review_response(
                    raw_response,
                    selected_region=selected_region,
                    selected_finding=selected_finding,
                    new_finding_id=new_finding_id,
                    local_signal_audit=signal_audit,
                    allow_add=allow_add,
                )
                recorded_revision = revision
                if response.delta is None:
                    agent.record_regional_review_outcome(
                        expected_revision=revision,
                        outcome="blocked" if response.warning else "no_change",
                        local_signal_audit=signal_audit,
                        regional_review_trace=turn_trace,
                    )
                    recorded_revision = agent.result_revision
                signals.review_chat_done.emit(
                    question,
                    response,
                    recorded_revision,
                    signal_audit,
                    turn_trace,
                    request_id,
                )
            except Exception:
                logger.exception("Regional review request failed")
                signals.chat_failed.emit(request_id)

        future.add_done_callback(_review_done)

    def on_chat() -> None:
        text, ok = QInputDialog.getText(
            control_bar,
            "問 AI",
            "請輸入問題:",
        )
        if not ok or not text.strip():
            return

        question = text.strip()
        logger.info("User chat question: %s", question)

        snapshot = _current_review_snapshot()
        if snapshot is not None:
            context = summarize_result_for_followup(snapshot.result)
            _submit_image_chat(
                question=question,
                image_base64=snapshot.image_base64,
                context=context,
                revision=snapshot.revision,
            )
            return

        if agent.target_window:
            overlay.position_over_window(agent.target_window, agent.display_frame)
        request_id = _begin_chat_request()
        overlay.show_chat_waiting(question)
        future = bridge.submit(openclaw_client.chat(question))

        def _chat_done(f):
            try:
                answer = f.result()
                signals.chat_done.emit(question, answer, -1, request_id)
            except Exception:
                logger.exception("Chat request failed")
                signals.chat_failed.emit(request_id)

        future.add_done_callback(_chat_done)

    def _ask_about_region(
        finding_id: str,
        label: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        control_bar.set_interaction_mode("passive")
        overlay.set_interaction_mode("passive")
        snapshot = _current_review_snapshot()
        if snapshot is None:
            control_bar.set_status("Analyze an image before regional QA")
            return
        title = label.strip() or "Selected region"
        question, ok = QInputDialog.getText(
            control_bar,
            "Regional QA",
            f"{title}:",
        )
        if not ok or not question.strip():
            control_bar.set_status("Regional QA cancelled")
            return
        current_snapshot = _current_review_snapshot()
        if current_snapshot is None or current_snapshot.revision != snapshot.revision:
            control_bar.set_status("Image changed; select the region again")
            return
        region = RegionRect(x=x, y=y, w=width, h=height)
        selected_finding = match_selected_finding(
            snapshot.result.findings,
            finding_id=finding_id,
            label=title,
            selected_region=region,
        )
        crop_base64 = image_processor.crop_region_base64(
            snapshot.image_base64,
            region,
        )
        source_crop_bytes = image_processor.crop_region_bytes(
            snapshot.image_base64,
            region,
        )
        _submit_region_review(
            question=question.strip(),
            crop_base64=crop_base64,
            source_crop_bytes=source_crop_bytes,
            snapshot=snapshot,
            selected_region=region,
            selected_finding=selected_finding,
            allow_add=False,
        )

    def _ask_about_user_region(
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        control_bar.set_interaction_mode("passive")
        overlay.set_interaction_mode("passive")
        snapshot = _current_review_snapshot()
        if snapshot is None:
            control_bar.set_status("Analyze an image before regional QA")
            return
        question, ok = QInputDialog.getText(
            control_bar,
            "Reviewer annotation",
            "Question or observation for this region:",
        )
        if not ok or not question.strip():
            control_bar.set_status("Region retained for export")
            return
        current_snapshot = _current_review_snapshot()
        if current_snapshot is None or current_snapshot.revision != snapshot.revision:
            control_bar.set_status("Image changed; draw the region again")
            return
        region = RegionRect(x=x, y=y, w=width, h=height)
        crop_base64 = image_processor.crop_region_base64(
            snapshot.image_base64,
            region,
        )
        source_crop_bytes = image_processor.crop_region_bytes(
            snapshot.image_base64,
            region,
        )
        _submit_region_review(
            question=question.strip(),
            crop_base64=crop_base64,
            source_crop_bytes=source_crop_bytes,
            snapshot=snapshot,
            selected_region=region,
            selected_finding=None,
            allow_add=True,
        )

    overlay.highlight_selected.connect(_ask_about_region)
    overlay.user_region_created.connect(_ask_about_user_region)
    overlay.user_region_selected.connect(_ask_about_user_region)

    def _show_chat_response(
        question: str,
        answer: str,
        revision: int,
        request_id: int,
    ) -> None:
        if request_id != _chat_request_id[0]:
            return
        if revision >= 0 and (
            agent.state is not AgentState.DISPLAYING
            or revision != agent.result_revision
        ):
            return
        overlay.show_chat_response(question, answer)
        control_bar.set_status("💬 回覆已顯示")

    def _show_review_chat_response(
        question: str,
        response: ReviewChatResponse,
        revision: int,
        signal_audit: dict[str, object],
        review_trace: list[dict[str, object]],
        request_id: int,
    ) -> None:
        if request_id != _chat_request_id[0]:
            return
        _pending_review[0] = None
        if (
            agent.state is not AgentState.DISPLAYING
            or revision != agent.result_revision
        ):
            return
        answer = response.answer
        if response.warning:
            answer = f"{answer}\n\nReport update not available: {response.warning}"

        proposal_summary = ""
        if response.delta is not None:
            _pending_review[0] = (
                response.delta,
                revision,
                signal_audit,
                review_trace,
            )
            proposal_summary = response.proposal_summary
        else:
            recorded_snapshot = _current_review_snapshot()
            if recorded_snapshot is not None and recorded_snapshot.revision == revision:
                overlay.summary_panel.update_result(recorded_snapshot.result)
        overlay.show_chat_response(
            question,
            answer,
            proposal_summary=proposal_summary,
        )
        control_bar.set_status(
            "Review report update" if proposal_summary else "Regional QA displayed"
        )

    def _apply_review_proposal() -> None:
        pending = _pending_review[0]
        _pending_review[0] = None
        if pending is None:
            overlay.clear_chat_proposal(restart_timeout=True)
            control_bar.set_status("No current report update")
            return
        delta, revision, signal_audit, review_trace = pending
        control_bar.set_status("Applying reviewed report update...")

        async def _apply():
            return agent.apply_finding_delta(
                delta,
                expected_revision=revision,
                local_signal_audit=signal_audit,
                regional_review_trace=review_trace,
            )

        future = bridge.submit(_apply())

        def _done(f):
            try:
                signals.review_apply_done.emit(f.result(), delta)
            except (RuntimeError, ValueError) as exc:
                signals.review_apply_failed.emit(str(exc))
            except Exception as exc:
                logger.exception("Interactive review writeback failed")
                signals.review_apply_failed.emit(type(exc).__name__)

        future.add_done_callback(_done)

    def _on_review_apply_done(updated, delta: FindingDelta) -> None:
        if delta.op is FindingOp.ADD:
            for box in delta.finding.bboxes:
                overlay.consume_user_region(box)
        on_analysis_result(
            updated,
            announce=False,
            preserve_user_regions=True,
        )
        overlay.clear_chat_proposal(restart_timeout=True)
        control_bar.set_status("Report update applied and recorded")

    def _on_review_apply_failed(reason: str) -> None:
        logger.warning("Interactive review writeback rejected", reason=reason)
        overlay.clear_chat_proposal(restart_timeout=True)
        control_bar.set_status("Report changed; suggestion was not applied")

    def _dismiss_review_proposal() -> None:
        pending = _pending_review[0]
        _pending_review[0] = None
        overlay.clear_chat_proposal(restart_timeout=True)
        if pending is None:
            control_bar.set_status("Report unchanged")
            return
        delta, revision, signal_audit, review_trace = pending
        control_bar.set_status("Recording dismissed report update...")

        async def _record_dismissal():
            return agent.record_regional_review_outcome(
                expected_revision=revision,
                outcome="dismissed",
                local_signal_audit=signal_audit,
                regional_review_trace=review_trace,
                user_confirmed=True,
                proposed_operation=delta.op.value,
                target_id=delta.finding.id,
            )

        future = bridge.submit(_record_dismissal())

        def _done(f):
            try:
                f.result()
                signals.review_outcome_done.emit("Report unchanged; dismissal recorded")
            except (RuntimeError, ValueError) as exc:
                signals.review_outcome_failed.emit(str(exc))
            except Exception as exc:
                logger.exception("Interactive review dismissal audit failed")
                signals.review_outcome_failed.emit(type(exc).__name__)

        future.add_done_callback(_done)

    def _on_review_outcome_done(status: str) -> None:
        snapshot = _current_review_snapshot()
        if snapshot is not None:
            overlay.summary_panel.update_result(snapshot.result)
        control_bar.set_status(status)

    def _on_review_outcome_failed(reason: str) -> None:
        logger.warning("Interactive review outcome audit rejected", reason=reason)
        control_bar.set_status("Report unchanged")

    def _on_chat_error(request_id: int) -> None:
        if request_id != _chat_request_id[0]:
            return
        control_bar.set_status("⚠ 聊天請求失敗")
        _pending_review[0] = None
        overlay.clear_chat_proposal()
        overlay.clear_chat()

    signals.chat_done.connect(_show_chat_response)
    signals.review_chat_done.connect(_show_review_chat_response)
    signals.review_apply_done.connect(_on_review_apply_done)
    signals.review_apply_failed.connect(_on_review_apply_failed)
    signals.review_outcome_done.connect(_on_review_outcome_done)
    signals.review_outcome_failed.connect(_on_review_outcome_failed)
    signals.chat_failed.connect(_on_chat_error)
    overlay.chat_proposal_accepted.connect(_apply_review_proposal)
    overlay.chat_proposal_dismissed.connect(_dismiss_review_proposal)
    control_bar.chat_clicked.connect(on_chat)

    # ─── Hotkeys (application-wide shortcuts) ───
    def _toggle_enable() -> None:
        if agent.state == AgentState.PAUSED:
            on_resume()
        else:
            on_pause()

    hk = config.hotkeys
    shortcut_trigger = QShortcut(
        QKeySequence(hk.trigger_manual),
        control_bar,
    )
    shortcut_trigger.setContext(Qt.ShortcutContext.ApplicationShortcut)
    shortcut_trigger.activated.connect(on_retrigger)

    shortcut_dismiss = QShortcut(
        QKeySequence(hk.dismiss_overlay),
        control_bar,
    )
    shortcut_dismiss.setContext(Qt.ShortcutContext.ApplicationShortcut)
    shortcut_dismiss.activated.connect(on_dismiss)

    shortcut_toggle = QShortcut(
        QKeySequence(hk.toggle_enable),
        control_bar,
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
