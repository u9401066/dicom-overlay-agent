"""Overlay Agent — main application use case with state machine (spec §3.5)."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import inspect
import threading
import time
from typing import TYPE_CHECKING, Any, cast

import structlog

from dicom_overlay.application.annotation_accumulator import (
    AnnotationAccumulator,
    max_severity,
)
from dicom_overlay.application.multi_pass import (
    DEFAULT_TOTAL_ANALYSIS_SLA_SEC,
    AnalysisSlaTimeout,
)
from dicom_overlay.application.roi import compute_viewer_roi_rect, scaled_roi_crop
from dicom_overlay.domain.entities import (
    AgentState,
    AnalysisResult,
    DisplayFrame,
    Finding,
    FindingDelta,
    FindingOp,
    Modality,
    RegionRect,
    Severity,
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

_LOCAL_SIGNAL_AUDIT_KEYS = frozenset(
    {
        "status",
        "width_px",
        "height_px",
        "ink_pixel_ratio",
        "bright_pixel_ratio",
        "entropy_bits",
        "robust_dynamic_range",
        "edge_pixel_ratio",
        "source_short_edge_px",
        "insufficient_source_resolution",
        "low_signal",
    }
)
_REGIONAL_TRACE_KEYS = frozenset(
    {
        "stage",
        "status",
        "reason",
        "error_type",
        "session_key",
        "run_id",
        "tools",
        "tool_audit",
        "parse_retry_count",
    }
)
_REGIONAL_REVIEW_OUTCOMES = frozenset(
    {"no_change", "blocked", "dismissed", "superseded"}
)

_REVIEW_RECONCILIATION_REASON = (
    "A reviewer-confirmed regional update changed the overlay findings. The "
    "initial checklist and management plan were retained and require reconciliation."
)
_REVIEW_RECONCILIATION_STEP = (
    "Reconcile the reviewer-confirmed regional update with the retained checklist "
    "and management plan in the source viewer."
)


def _structured_severity(
    result: AnalysisResult,
    findings: list[Finding],
) -> Severity:
    """Return the highest severity still present in structured report fields."""

    severity = Severity.NORMAL
    for finding in findings:
        severity = max_severity(severity, finding.severity)
    for item in result.checklist.values():
        severity = max_severity(severity, item.status)
    return severity


def _finding_inventory(findings: list[Finding]) -> str:
    if not findings:
        return "No focal overlay findings remain."
    visible = [
        f"{finding.label.strip() or finding.id} [{finding.severity.value}]"
        for finding in findings[:5]
    ]
    suffix = f"; plus {len(findings) - 5} more" if len(findings) > 5 else ""
    return f"Current overlay findings: {'; '.join(visible)}{suffix}."


def _review_summary(
    *,
    delta: FindingDelta,
    findings: list[Finding],
    triage_severity: Severity,
    structured_severity: Severity,
) -> str:
    if delta.op is FindingOp.ADD:
        action = f"added {delta.finding.label.strip() or delta.finding.id}"
    elif delta.op is FindingOp.REVISE:
        action = f"revised {delta.finding.label.strip() or delta.finding.id}"
    else:
        action = f"retracted {delta.finding.label.strip() or delta.finding.id}"

    severity_note = f"Overall triage severity is {triage_severity.value}."
    if triage_severity is not structured_severity:
        severity_note = (
            f"Overall triage severity remains {triage_severity.value} as a safety "
            f"floor; current structured findings/checklist peak at "
            f"{structured_severity.value}."
        )
    return (
        f"Reviewer-confirmed regional update: {action}. "
        f"{_finding_inventory(findings)} {severity_note}"
    )


def _safe_local_signal_audit(
    audit: dict[str, object] | None,
) -> dict[str, object]:
    if not isinstance(audit, dict):
        return {}
    return {
        key: value for key, value in audit.items() if key in _LOCAL_SIGNAL_AUDIT_KEYS
    }


def _safe_regional_turns(
    turns: list[dict[str, object]] | None,
) -> list[dict[str, object]]:
    if not isinstance(turns, list):
        return []
    return [
        {key: value for key, value in turn.items() if key in _REGIONAL_TRACE_KEYS}
        for turn in turns
        if isinstance(turn, dict)
    ]


@dataclasses.dataclass(frozen=True)
class ReviewSnapshot:
    """Atomically published image/result pair for UI review operations."""

    image_base64: str
    result: AnalysisResult
    capture_rect: WindowRect
    revision: int


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
        annotation_accumulator: AnnotationAccumulator | None = None,
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
        self._display_frame: DisplayFrame | None = None
        self._last_capture_rect: WindowRect | None = None

        self._review_lock = threading.RLock()
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
        self._result_revision = 0
        self._review_snapshot: ReviewSnapshot | None = None
        self._annotation_accumulator = annotation_accumulator or AnnotationAccumulator()
        self._last_image_base64 = ""
        self._running = False
        self._roi_setup_notified = False

        # Callbacks for presentation layer
        self.on_state_change: Any = None
        self.on_analysis_result: Any = None
        self.on_pending_analysis: Any = None
        self.on_error: Any = None
        self.on_roi_setup_required: Any = None

    @property
    def state(self) -> AgentState:
        with self._review_lock:
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
    def result_revision(self) -> int:
        """Monotonic guard against applying a follow-up to a newer image."""

        with self._review_lock:
            return self._result_revision

    @property
    def review_snapshot(self) -> ReviewSnapshot | None:
        """Return one immutable, internally consistent image/result revision."""

        with self._review_lock:
            return self._review_snapshot

    @property
    def displayed_review_snapshot(self) -> ReviewSnapshot | None:
        """Return the snapshot only while it is valid for user interaction."""

        with self._review_lock:
            if self._state is not AgentState.DISPLAYING:
                return None
            return self._review_snapshot

    @property
    def last_image_base64(self) -> str:
        return self._last_image_base64

    @property
    def target_window(self) -> WindowRect | None:
        return self._target_window

    @property
    def display_frame(self) -> DisplayFrame | None:
        return self._display_frame

    @property
    def last_capture_rect(self) -> WindowRect | None:
        return self._last_capture_rect

    def set_modality(self, modality: Modality) -> None:
        self._current_modality = modality
        logger.info("Modality set to %s", modality.value)

    def set_trigger_mode(self, mode: TriggerMode) -> None:
        self._trigger_mode = mode
        self._config.analysis.trigger_mode = mode
        if mode == TriggerMode.AUTO:
            self._pending_analysis = False
        logger.info("Trigger mode set to %s", mode.value)

    def set_vision_analyzer(self, analyzer: VisionAnalyzerService) -> None:
        """Use ``analyzer`` for subsequent reads without resetting app state."""
        self._analyzer = analyzer
        logger.info("Vision analyzer set to %s", type(analyzer).__name__)

    def apply_finding_delta(
        self,
        delta: FindingDelta,
        *,
        expected_revision: int,
        local_signal_audit: dict[str, object] | None = None,
        regional_review_trace: list[dict[str, object]] | None = None,
    ) -> AnalysisResult:
        """Apply a reviewer-confirmed regional proposal to the displayed result.

        The model never calls this method. The Qt layer invokes it only after an
        explicit user action. Overall triage severity is allowed to rise but is
        never lowered by a follow-up, and every accepted operation is appended
        to the reviewer-visible process trace.
        """

        with self._review_lock:
            return self._apply_finding_delta_locked(
                delta,
                expected_revision=expected_revision,
                local_signal_audit=local_signal_audit,
                regional_review_trace=regional_review_trace,
            )

    def _apply_finding_delta_locked(
        self,
        delta: FindingDelta,
        *,
        expected_revision: int,
        local_signal_audit: dict[str, object] | None,
        regional_review_trace: list[dict[str, object]] | None,
    ) -> AnalysisResult:
        """Apply one delta while ``_review_lock`` is held."""

        if self._last_result is None:
            raise RuntimeError("No analysis result is available for review writeback")
        if self._state is not AgentState.DISPLAYING:
            raise RuntimeError("Review writeback requires the displayed result")
        if expected_revision != self._result_revision:
            raise RuntimeError(
                "The image result changed before this proposal was applied"
            )

        current_id_list = [finding.id for finding in self._last_result.findings]
        current_ids = set(current_id_list)
        if len(current_ids) != len(current_id_list):
            raise ValueError("Current result contains duplicate finding ids")
        target_finding = next(
            (
                finding
                for finding in self._last_result.findings
                if finding.id == delta.finding.id
            ),
            None,
        )
        if delta.op is FindingOp.ADD and delta.finding.id in current_ids:
            raise ValueError("Review proposal add id already exists in current result")
        if delta.op in {FindingOp.REVISE, FindingOp.RETRACT} and (
            not delta.finding.id or delta.finding.id not in current_ids
        ):
            raise ValueError("Review proposal target is not in the current result")
        signal_is_accepted = (
            isinstance(local_signal_audit, dict)
            and local_signal_audit.get("status") == "ok"
            and local_signal_audit.get("low_signal") is False
        )
        if not signal_is_accepted:
            raise ValueError("Review proposal failed the local-signal writeback gate")
        if delta.op in {FindingOp.ADD, FindingOp.REVISE}:
            if (
                not delta.finding.id.strip()
                or not delta.finding.label.strip()
                or not delta.finding.detail.strip()
            ):
                raise ValueError("Review proposal finding payload is incomplete")
            if delta.finding.severity is Severity.NORMAL:
                raise ValueError("Use retract instead of a normal overlay finding")
            if not delta.finding.bboxes:
                raise ValueError("Review proposal has no app-owned bbox")
            if any(
                box.w <= 0.0
                or box.h <= 0.0
                or box.x < 0.0
                or box.y < 0.0
                or box.x + box.w > 1.0 + 1e-9
                or box.y + box.h > 1.0 + 1e-9
                for box in delta.finding.bboxes
            ):
                raise ValueError("Review proposal bbox is outside the original ROI")

        findings = self._annotation_accumulator.apply(delta)
        structured_severity = _structured_severity(self._last_result, findings)
        severity = max_severity(self._last_result.severity, structured_severity)
        summary = _review_summary(
            delta=delta,
            findings=findings,
            triage_severity=severity,
            structured_severity=structured_severity,
        )

        reason = (
            "Interactive regional AI proposal was applied by the local reviewer; "
            "confirm it in the source viewer before clinical use."
        )
        review_reasons = list(self._last_result.review_reasons)
        if reason not in review_reasons:
            review_reasons.append(reason)
        if _REVIEW_RECONCILIATION_REASON not in review_reasons:
            review_reasons.append(_REVIEW_RECONCILIATION_REASON)
        next_steps = list(self._last_result.next_steps)
        if _REVIEW_RECONCILIATION_STEP not in next_steps:
            next_steps.append(_REVIEW_RECONCILIATION_STEP)
        trace_entry: dict[str, object] = {
            "stage": "interactive_review",
            "status": "applied",
            "tool": "openclaw_region_followup",
            "operation": delta.op.value,
            "target_id": delta.finding.id,
            "bbox_source": (
                "reviewer_selected_original_roi"
                if delta.op is FindingOp.ADD
                else "selected_finding_existing_bbox"
                if target_finding is not None and target_finding.bboxes
                else "selected_static_region_fallback"
            ),
            "user_confirmed": True,
            "report_reconciliation": {
                "findings": "updated",
                "summary": "updated",
                "overall_severity": (
                    "retained_safety_floor"
                    if severity is not structured_severity
                    else "matches_structured_report"
                ),
                "checklist": "retained_requires_review",
                "next_steps": "retained_with_reconciliation_step",
                "summary_before": self._last_result.summary,
                "summary_after": summary,
                "severity_before": self._last_result.severity.value,
                "structured_severity_after": structured_severity.value,
                "severity_after": severity.value,
            },
            "bboxes": [
                {"x": box.x, "y": box.y, "w": box.w, "h": box.h}
                for box in delta.finding.bboxes
            ],
        }
        safe_signal_audit = _safe_local_signal_audit(local_signal_audit)
        if safe_signal_audit:
            trace_entry["local_signal_audit"] = safe_signal_audit
        safe_regional_turns = _safe_regional_turns(regional_review_trace)
        if safe_regional_turns:
            trace_entry["regional_turns"] = safe_regional_turns
        trace = [*self._last_result.analysis_trace, trace_entry]
        updated = dataclasses.replace(
            self._last_result,
            summary=summary,
            findings=findings,
            severity=severity,
            next_steps=next_steps,
            review_required=True,
            review_reasons=review_reasons,
            analysis_trace=trace,
        )
        self._last_result = updated
        self._result_revision += 1
        snapshot = self._review_snapshot
        if snapshot is not None:
            self._review_snapshot = dataclasses.replace(
                snapshot,
                result=updated,
                revision=self._result_revision,
            )
        logger.info(
            "interactive_review_applied",
            operation=delta.op.value,
            target_id=delta.finding.id,
            result_revision=self._result_revision,
        )
        return updated

    def record_regional_review_outcome(
        self,
        *,
        expected_revision: int,
        outcome: str,
        local_signal_audit: dict[str, object] | None = None,
        regional_review_trace: list[dict[str, object]] | None = None,
        user_confirmed: bool = False,
        proposed_operation: str = "none",
        target_id: str = "",
    ) -> AnalysisResult:
        """Persist a crop-review turn that did not mutate report findings."""

        if outcome not in _REGIONAL_REVIEW_OUTCOMES:
            raise ValueError(f"Unsupported regional review outcome: {outcome}")
        if proposed_operation not in {"none", *(op.value for op in FindingOp)}:
            raise ValueError(
                f"Unsupported regional review operation: {proposed_operation}"
            )
        with self._review_lock:
            if self._last_result is None:
                raise RuntimeError("No analysis result is available for review audit")
            if self._state is not AgentState.DISPLAYING:
                raise RuntimeError("Review audit requires the displayed result")
            if expected_revision != self._result_revision:
                raise RuntimeError(
                    "The image result changed before this review was recorded"
                )

            trace_entry: dict[str, object] = {
                "stage": "interactive_review",
                "status": outcome,
                "tool": "openclaw_region_followup",
                "operation": proposed_operation,
                "user_confirmed": bool(user_confirmed),
            }
            if target_id.strip():
                trace_entry["target_id"] = target_id.strip()
            safe_signal_audit = _safe_local_signal_audit(local_signal_audit)
            if safe_signal_audit:
                trace_entry["local_signal_audit"] = safe_signal_audit
            safe_regional_turns = _safe_regional_turns(regional_review_trace)
            if safe_regional_turns:
                trace_entry["regional_turns"] = safe_regional_turns

            updated = dataclasses.replace(
                self._last_result,
                analysis_trace=[*self._last_result.analysis_trace, trace_entry],
            )
            self._last_result = updated
            self._result_revision += 1
            snapshot = self._review_snapshot
            if snapshot is not None:
                self._review_snapshot = dataclasses.replace(
                    snapshot,
                    result=updated,
                    revision=self._result_revision,
                )
            logger.info(
                "interactive_review_recorded",
                outcome=outcome,
                user_confirmed=bool(user_confirmed),
                result_revision=self._result_revision,
            )
            return updated

    def _transition(self, new_state: AgentState) -> None:
        with self._review_lock:
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
        try:
            scaled_roi_crop(roi, roi.reference_width, roi.reference_height)
        except ValueError:
            return False
        return True

    async def start(self) -> None:
        """Start the agent loop."""
        self._running = True
        self._transition(AgentState.INIT)

        if not self.has_roi_config():
            self._roi_setup_notified = False
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
            case AgentState.SETUP:
                await self._tick_setup()
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

    async def _tick_setup(self) -> None:
        """Wait for the actual viewer before asking for a PHI-safe ROI."""

        window = self._monitor.find_target_window(
            self._config.monitor.window_title_keywords
        )
        if window is None:
            if self._target_window is not None:
                self._set_target_window(None)
                self._roi_setup_notified = False
            return
        self._set_target_window(window)
        if not self._roi_setup_notified:
            self._roi_setup_notified = True
            logger.info("Viewer found; requesting viewer-relative ROI setup")
            if self.on_roi_setup_required:
                self.on_roi_setup_required()

    async def _tick_waiting(self) -> None:
        window = self._monitor.find_target_window(
            self._config.monitor.window_title_keywords
        )
        if window:
            self._set_target_window(window)
            self._transition(AgentState.MONITORING)
            logger.info(
                "Found viewer: %dx%d at (%d, %d)",
                window.width,
                window.height,
                window.left,
                window.top,
            )

    def _get_roi_rect(self) -> WindowRect:
        """Compute an absolute capture rectangle inside the current viewer."""

        if self._target_window is None:
            raise ValueError("No target viewer is available for ROI capture")
        return compute_viewer_roi_rect(self._target_window, self._config.phi_roi)

    def _set_target_window(self, window: WindowRect | None) -> None:
        self._target_window = window
        if window is not None:
            self._sync_capture_display(window)

    def _sync_capture_display(self, window: WindowRect) -> None:
        display = self._monitor.display_for_window(window)
        if display is None:
            return
        physical = display.physical_rect
        changed = display != self._display_frame
        self._display_frame = display
        self._screen_left = physical.left
        self._screen_top = physical.top
        self._screen_width = physical.width
        self._screen_height = physical.height
        if changed:
            logger.info(
                "Capture display: %s index=%d primary=%s rect=(%d,%d,%dx%d)",
                display.device_name or "unknown",
                display.monitor_index,
                display.is_primary,
                physical.left,
                physical.top,
                physical.width,
                physical.height,
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
            self._set_target_window(None)
            self._transition(AgentState.WAITING)
            return
        self._set_target_window(window)

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
            self._set_target_window(None)
            self._transition(AgentState.WAITING)
            return
        self._set_target_window(window)

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

        self._mark_pending_analysis("image_changed_manual")
        with self._review_lock:
            self._review_snapshot = None
        if self._state == AgentState.DISPLAYING:
            self._transition(AgentState.MONITORING)
        logger.info("Image change invalidated the manual-mode review snapshot")

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
        if self._target_window is None:
            logger.warning("No target window for capture")
            self._transition(AgentState.WAITING)
            return
        self._sync_capture_display(self._target_window)
        roi = self._config.phi_roi
        try:
            capture_rect = self._get_roi_rect()
        except ValueError:
            logger.exception("ROI does not fit the target display")
            self._transition(AgentState.ERROR)
            if self.on_error:
                self.on_error("ROI 設定超出目前螢幕, 請重新設定")
            return
        logger.info(
            "ROI capture: screen=%dx%d roi=(%d,%d,%d,%d) → rect=(%d,%d,%dx%d)",
            self._screen_width,
            self._screen_height,
            roi.top,
            roi.bottom,
            roi.left,
            roi.right,
            capture_rect.left,
            capture_rect.top,
            capture_rect.width,
            capture_rect.height,
        )
        try:
            screenshot = self._monitor.capture_region(capture_rect)
        except Exception:
            logger.exception("ROI capture failed")
            self._transition(AgentState.ERROR)
            return
        logger.debug("Captured %d bytes", len(screenshot))
        source_screenshot = screenshot
        source_size_px = self._processor.image_size(source_screenshot)
        source_image_b64 = self._processor.to_base64(source_screenshot)
        local_candidate_regions = self._local_candidate_regions(source_screenshot)
        # Guard image size before sending: oversized ROI PNGs can hit gateway
        # limits and add latency. Shrink the longest edge if configured.
        max_edge = self._config.openclaw.max_image_edge_px
        screenshot = self._processor.downscale_to_max_edge(screenshot, max_edge)
        image_b64 = self._processor.to_base64(screenshot)
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
                image_b64,
                modality,
                valid_regions,
                source_size_px=source_size_px,
                source_image_base64=source_image_b64,
                local_candidate_regions=local_candidate_regions,
            )
            if self._state != AgentState.ANALYZING:
                logger.info(
                    "Analysis result discarded (state changed to %s)", self._state.name
                )
                return
            self._annotation_accumulator.reset(result.findings)
            with self._review_lock:
                self._last_capture_rect = capture_rect
                self._last_image_base64 = source_image_b64
                self._last_result = result
                self._result_revision += 1
                self._review_snapshot = ReviewSnapshot(
                    image_base64=source_image_b64,
                    result=result,
                    capture_rect=capture_rect,
                    revision=self._result_revision,
                )
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
        *,
        source_size_px: tuple[int, int] | None = None,
        source_image_base64: str | None = None,
        local_candidate_regions: list[RegionRect] | None = None,
    ) -> AnalysisResult:
        """Run analyze with a single backoff retry on transient timeout.

        Vision models occasionally time out transiently; one retry avoids
        flapping into ERROR for what is usually a recoverable hiccup.
        ConnectionError is NOT retried here — the caller handles reconnect.
        """
        retries = max(0, self._config.openclaw.analyze_retries)
        backoff = self._config.openclaw.analyze_retry_backoff_sec
        attempt = 0
        deadline = time.monotonic() + DEFAULT_TOTAL_ANALYSIS_SLA_SEC

        async def invoke() -> AnalysisResult:
            analyze_with_source_size = getattr(
                self._analyzer, "analyze_with_source_size", None
            )
            if callable(analyze_with_source_size):
                parameters = inspect.signature(
                    analyze_with_source_size
                ).parameters.values()
                names = {parameter.name for parameter in parameters}
                accepts_extra = any(
                    parameter.kind is inspect.Parameter.VAR_KEYWORD
                    for parameter in parameters
                )
                extra: dict[str, object] = {}
                if accepts_extra or "source_image_base64" in names:
                    extra["source_image_base64"] = source_image_base64
                if accepts_extra or "local_candidate_regions" in names:
                    extra["local_candidate_regions"] = local_candidate_regions
                return cast(
                    "AnalysisResult",
                    await analyze_with_source_size(
                        image_b64,
                        modality,
                        valid_regions,
                        source_size_px=source_size_px,
                        **extra,
                    ),
                )
            return await self._analyzer.analyze(image_b64, modality, valid_regions)

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                raise TimeoutError("analysis exceeded the 180s total SLA")
            try:
                return await asyncio.wait_for(invoke(), timeout=remaining)
            except AnalysisSlaTimeout:
                # Retrying a coarse turn after its 60s deadline would violate the
                # single-question 180s contract and duplicate tool calls.
                raise
            except TimeoutError:
                if attempt >= retries:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= backoff:
                    raise
                attempt += 1
                logger.warning(
                    "Analysis timed out, retrying (%d/%d) after %.1fs backoff",
                    attempt,
                    retries,
                    backoff,
                )
                await asyncio.sleep(backoff)

    def _local_candidate_regions(self, image_data: bytes) -> list[RegionRect]:
        """Convert deterministic image-assist proposals into safe ROI boxes."""
        candidate_method = getattr(self._processor, "local_signal_candidates", None)
        if not callable(candidate_method):
            return []
        try:
            payload = candidate_method(image_data)
        except Exception:
            logger.warning("Local image-assist candidate extraction failed")
            return []
        raw_candidates = (
            payload.get("candidates", []) if isinstance(payload, dict) else []
        )
        regions: list[RegionRect] = []
        for raw in raw_candidates:
            if not isinstance(raw, dict):
                continue
            try:
                region = RegionRect(
                    x=float(raw["x"]),
                    y=float(raw["y"]),
                    w=float(raw["w"]),
                    h=float(raw["h"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if region.w <= 0.0 or region.h <= 0.0:
                continue
            regions.append(region)
        logger.info(
            "Local image-assist candidates prepared",
            candidate_count=len(regions),
        )
        return regions

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
            self._set_target_window(window)
            logger.info("Error recovery: viewer found, resuming monitoring")
            self._transition(AgentState.MONITORING)
        else:
            self._set_target_window(None)
            logger.info("Error recovery: viewer lost, returning to waiting")
            self._transition(AgentState.WAITING)

    async def _tick_reconnecting(self) -> None:
        now = time.monotonic()
        if (
            now - self._last_reconnect_attempt
            < self._config.openclaw.reconnect_interval_sec
        ):
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
        self._roi_setup_notified = False
        self._transition(AgentState.WAITING)

    def on_display_timeout(self) -> None:
        """Called when overlay display times out."""
        if self._state == AgentState.DISPLAYING:
            self._transition(AgentState.MONITORING)
