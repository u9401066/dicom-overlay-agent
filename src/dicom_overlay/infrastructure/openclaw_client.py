"""OpenClaw Gateway WebSocket client (spec §3.3, §3.6)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import platform
import re
import time
from collections import deque
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
import websockets
from websockets.sync.client import connect as sync_websocket_connect

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

from dicom_overlay.application.interpretation_harness import (
    EKG_LVH_BALANCE_GUIDANCE,
    EKG_PRECORDIAL_REVIEW_GUIDANCE,
    build_coarse_analysis_prompt,
    build_initial_analysis_prompt,
    build_minimal_control_prompt,
)
from dicom_overlay.application.multi_pass import (
    RefinementAction,
    RefinementDelta,
    RefinementResult,
)
from dicom_overlay.domain.entities import (
    AnalysisResult,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.domain.modality_profile import (
    ModalityRegistry,
    get_active_registry,
)
from dicom_overlay.domain.services import VisionAnalyzerService
from dicom_overlay.infrastructure.env_file import read_env_file
from dicom_overlay.infrastructure.openclaw_runtime import build_openclaw_chat_frame

logger = structlog.get_logger(__name__)

_ANALYSIS_PROMPT_PROFILES = frozenset({"clinical", "minimal_control"})

_OPENCLAW_VERSION = "2026.3.11"
# The websockets default frame limit is 1 MiB. A real medical screenshot,
# even after downscaling to the configured max edge, base64-encodes to a few
# MiB, which overflows the default and closes the connection (close code 1009).
# Raise the receive limit so large image payloads round-trip cleanly.
_MAX_WS_MESSAGE_BYTES = 16 * 1024 * 1024
_WS_CLOSE_TIMEOUT_SEC = 2.0
_BBOX_AUDIT_FLUSH_GRACE_SEC = 0.5
_BBOX_AUDIT_POLL_INTERVAL_SEC = 0.01
_DEFAULT_SCOPES = [
    "operator.admin",
    "operator.read",
    "operator.write",
    "operator.approvals",
    "operator.pairing",
]
_WAVEFORM_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class BboxEvidenceError(ValueError):
    """A boxed result lacks a receipt bound to this image and model turn."""


class ModelResponseParseError(ValueError):
    """A completed model turn did not contain a parseable output contract."""


class _GatewayRunConnectionLost(ConnectionError):
    """Transport loss carrying the Gateway acceptance state of one model turn."""

    def __init__(
        self,
        message: str,
        *,
        run_id: str | None,
        accepted: bool,
        deadline: float,
    ) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.accepted = accepted
        self.deadline = deadline


@dataclass
class _WaveformArtifactBinding:
    artifact_id: str
    lead_mode: str
    evidence_nonce: str
    audit_offset: int
    receipts: list[dict[str, object]] = field(default_factory=list)
    duplicate_attempts: list[dict[str, object]] = field(default_factory=list)
    tool_call_ids: set[str] = field(default_factory=set)


def probe_openclaw_gateway(
    gateway_url: str,
    *,
    gateway_token: str | None = None,
    timeout_sec: float = 1.5,
) -> bool:
    """Verify a listener through the public Gateway ``connect`` contract.

    A successful TCP connection isn't sufficient: an unrelated service can own
    the configured port.  Startup uses this small synchronous probe because
    :meth:`GatewayManager.start` is called from an already-running async bridge
    and therefore cannot nest another event loop.
    """

    if timeout_sec <= 0:
        raise ValueError("timeout_sec must be positive")
    connect_id = f"health-{uuid4().hex}"
    params: dict[str, Any] = {
        "minProtocol": 3,
        "maxProtocol": 4,
        "client": {
            "id": "gateway-client",
            "version": _OPENCLAW_VERSION,
            "platform": platform.platform(),
            "mode": "backend",
        },
        "role": "operator",
        "scopes": _DEFAULT_SCOPES,
    }
    clean_token = gateway_token.strip() if gateway_token else ""
    if clean_token:
        params["auth"] = {"token": clean_token}
    frame = {
        "type": "req",
        "id": connect_id,
        "method": "connect",
        "params": params,
    }
    deadline = time.monotonic() + timeout_sec
    try:
        with sync_websocket_connect(
            gateway_url,
            open_timeout=timeout_sec,
            close_timeout=min(timeout_sec, 1.0),
            ping_interval=None,
            max_size=_MAX_WS_MESSAGE_BYTES,
        ) as websocket:
            websocket.send(json.dumps(frame))
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                raw = websocket.recv(timeout=remaining)
                response = json.loads(raw)
                if (
                    isinstance(response, dict)
                    and response.get("type") == "res"
                    and response.get("id") == connect_id
                ):
                    return bool(response.get("ok"))
    except (
        OSError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        websockets.WebSocketException,
    ):
        return False


# Skill resolution is driven by the modality registry (single source of truth).
# A modality's OpenClaw skill folder name comes from its ``ModalityProfile``;
# the on-disk SKILL.md is searched in the vendored workspace and the runtime
# home below.
_SKILL_BASE_DIRS: tuple[str, str] = (
    "openclaw/workspace/skills",
    "openclaw-home/.openclaw/workspace/skills",
)


class OpenClawClient(VisionAnalyzerService):
    """WebSocket client for OpenClaw Gateway (spec §3.6).

    Sends vision.analyze messages and receives vision.result responses.
    """

    def __init__(
        self,
        gateway_url: str = "ws://127.0.0.1:18789",
        timeout_sec: int = 15,
        reconnect_interval_sec: int = 5,
        gateway_token: str | None = None,
        connect_timeout_sec: int | None = None,
        inference_timeout_sec: int | None = None,
        registry: ModalityRegistry | None = None,
        base_dir: Path | None = None,
        analysis_prompt_profile: str = "clinical",
        require_bound_bbox_receipts: bool = True,
        fast_mode: bool = False,
    ) -> None:
        if analysis_prompt_profile not in _ANALYSIS_PROMPT_PROFILES:
            raise ValueError(
                "analysis_prompt_profile must be clinical or minimal_control"
            )
        if not isinstance(fast_mode, bool):
            raise ValueError("fast_mode must be a boolean")
        self._url = gateway_url
        self._timeout = timeout_sec
        # Split timeouts: handshake is fast, inference can be slow on big images.
        self._connect_timeout = connect_timeout_sec or timeout_sec
        self._inference_timeout = inference_timeout_sec or timeout_sec
        self._reconnect_interval = reconnect_interval_sec
        self._close_timeout = _WS_CLOSE_TIMEOUT_SEC
        self._registry = registry or get_active_registry()
        self._base_dir = (base_dir or Path.cwd()).resolve()
        self._analysis_prompt_profile = analysis_prompt_profile
        self._require_bbox_receipts = bool(require_bound_bbox_receipts)
        self._fast_mode = fast_mode
        self._ws: Any = None
        self._pending_frames: deque[str] = deque(maxlen=256)
        self._connected = False
        self._request_counter = 0
        self._gateway_token = (
            gateway_token.strip() if gateway_token else None
        ) or resolve_openclaw_gateway_token(self._base_dir)
        if not self._gateway_token:
            logger.warning(
                "No OpenClaw gateway token configured; connect() will proceed without auth"
            )
        self._ws_lock = asyncio.Lock()  # Serialize all WebSocket send+recv sequences
        self._last_run_id = ""
        self._last_session_key = ""
        self._last_run_tools: list[str] = []
        self._last_parse_retry_count = 0
        self._last_run_started_at = 0.0
        self._last_run_elapsed_ms = 0
        self._last_run_aborted = False
        self._bbox_evidence_nonce = ""
        self._bbox_source_image_sha256 = ""
        self._tool_audit_path = _resolve_bbox_tool_audit_path(self._base_dir)
        self._tool_audit_offset = _file_size(self._tool_audit_path)
        self._ecg_founder_tool_audit_path = _resolve_ecg_founder_tool_audit_path(
            self._base_dir
        )
        self._ecg_founder_tool_audit_offset = _file_size(
            self._ecg_founder_tool_audit_path
        )
        self._last_waveform_binding: _WaveformArtifactBinding | None = None
        self._last_tool_audit_records: list[dict[str, object]] = []
        self._waveform_artifact_context: ContextVar[_WaveformArtifactBinding | None] = (
            ContextVar(
                f"openclaw_waveform_artifact_{id(self)}",
                default=None,
            )
        )

    @contextmanager
    def use_waveform_artifact(
        self,
        artifact_id: str,
        *,
        lead_mode: str = "12_lead",
    ) -> Iterator[str]:
        """Bind one opaque waveform artifact to the current async analysis task."""

        clean_id = artifact_id.strip()
        if not _WAVEFORM_ARTIFACT_ID.fullmatch(clean_id):
            raise ValueError("invalid waveform artifact id")
        if lead_mode != "12_lead":
            raise ValueError("invalid waveform lead mode")
        binding = _WaveformArtifactBinding(
            artifact_id=clean_id,
            lead_mode=lead_mode,
            evidence_nonce=uuid4().hex,
            audit_offset=_file_size(self._ecg_founder_tool_audit_path),
        )
        token = self._waveform_artifact_context.set(binding)
        try:
            yield binding.evidence_nonce
        finally:
            self._refresh_waveform_binding(binding)
            self._last_waveform_binding = binding
            self._waveform_artifact_context.reset(token)

    def waveform_evidence_receipts(
        self,
        evidence_nonce: str,
    ) -> list[dict[str, object]]:
        """Return nonce-correlated receipts across all turns and parse retries."""

        binding = self._waveform_artifact_context.get()
        if binding is None or binding.evidence_nonce != evidence_nonce:
            binding = self._last_waveform_binding
        if binding is None or binding.evidence_nonce != evidence_nonce:
            return []
        self._refresh_waveform_binding(binding)
        return [dict(receipt) for receipt in binding.receipts]

    def waveform_duplicate_attempts(
        self,
        evidence_nonce: str,
    ) -> list[dict[str, object]]:
        """Return suppressed duplicate waveform-tool attempts for audit only."""

        binding = self._waveform_artifact_context.get()
        if binding is None or binding.evidence_nonce != evidence_nonce:
            binding = self._last_waveform_binding
        if binding is None or binding.evidence_nonce != evidence_nonce:
            return []
        self._refresh_waveform_binding(binding)
        return [dict(attempt) for attempt in binding.duplicate_attempts]

    async def connect(self) -> None:
        try:
            self._pending_frames.clear()
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    self._url,
                    # Long medical-image inference can occupy the Gateway long
                    # enough for client-side WS keepalive to produce false
                    # failures. Use the explicit inference timeout instead.
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=self._close_timeout,
                    max_size=_MAX_WS_MESSAGE_BYTES,
                ),
                timeout=self._connect_timeout,
            )
            await asyncio.wait_for(self._handshake(), timeout=self._connect_timeout)
            self._connected = True
            logger.info("Connected to OpenClaw Gateway at %s", self._url)
        except Exception as exc:
            self._connected = False
            websocket = self._ws
            self._ws = None
            if websocket is not None:
                with suppress(Exception):
                    await asyncio.wait_for(
                        websocket.close(),
                        timeout=self._close_timeout,
                    )
            logger.warning("Failed to connect to OpenClaw Gateway: %s", exc)
            raise

    async def disconnect(self) -> None:
        websocket = self._ws
        self._ws = None
        self._connected = False
        if websocket is not None:
            try:
                await asyncio.wait_for(
                    websocket.close(),
                    timeout=self._close_timeout,
                )
            except TimeoutError:
                logger.warning("Timed out closing OpenClaw WebSocket; detaching")
            except Exception as exc:
                logger.warning(
                    "OpenClaw WebSocket close failed during shutdown; detaching",
                    error_type=type(exc).__name__,
                )
        logger.info("Disconnected from OpenClaw Gateway")

    def is_connected(self) -> bool:
        return self._connected and self._ws is not None

    def set_fast_mode(self, enabled: bool) -> None:
        """Apply the explicit per-turn OpenClaw fast-mode request."""
        if not isinstance(enabled, bool):
            raise ValueError("fast_mode must be a boolean")
        self._fast_mode = enabled

    async def analyze(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        """Analyze with acceptance-aware transport recovery."""
        async with self._ws_lock:
            return await self._analyze_with_parse_retry(
                image_base64,
                modality,
                valid_regions,
            )

    async def analyze_coarse(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        """Run the compact first-look contract used by MultiPassInterpreter."""
        async with self._ws_lock:
            return await self._analyze_coarse_with_parse_retry(
                image_base64,
                modality,
                valid_regions,
            )

    async def refine(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        hypothesis: Finding | None,
        crop_region: RegionRect,
        probe_id: str = "",
        crop_lead_regions: dict[str, RegionRect] | None = None,
    ) -> RefinementResult:
        """Re-read one crop while explicitly testing the coarse hypothesis."""
        async with self._ws_lock:
            return await self._refine_with_parse_retry(
                image_base64,
                modality,
                valid_regions,
                hypothesis=hypothesis,
                crop_region=crop_region,
                probe_id=probe_id,
                crop_lead_regions=crop_lead_regions,
            )

    async def finalize(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        draft: AnalysisResult,
        refinement_trace: list[dict[str, object]],
    ) -> AnalysisResult:
        """Reconcile the complete report against final grounded findings."""
        async with self._ws_lock:
            return await self._finalize_with_parse_retry(
                image_base64,
                modality,
                valid_regions,
                draft=draft,
                refinement_trace=refinement_trace,
            )

    async def _analyze_with_parse_retry(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        for attempt in range(2):
            try:
                result = await self._do_analyze(image_base64, modality, valid_regions)
            except (json.JSONDecodeError, BboxEvidenceError):
                if attempt:
                    self._last_parse_retry_count = attempt
                    raise
                logger.warning("Malformed analysis JSON; retrying once with a new turn")
                continue
            self._last_parse_retry_count = attempt
            return result
        raise AssertionError("unreachable")

    async def _analyze_coarse_with_parse_retry(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        for attempt in range(2):
            try:
                result = await self._do_coarse_analyze(
                    image_base64,
                    modality,
                    valid_regions,
                )
            except (
                json.JSONDecodeError,
                BboxEvidenceError,
                ModelResponseParseError,
            ):
                if attempt:
                    self._last_parse_retry_count = attempt
                    raise
                logger.warning(
                    "Malformed coarse triage JSON; retrying once with a new turn"
                )
                continue
            self._last_parse_retry_count = attempt
            return result
        raise AssertionError("unreachable")

    async def _refine_with_parse_retry(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        hypothesis: Finding | None,
        crop_region: RegionRect,
        probe_id: str = "",
        crop_lead_regions: dict[str, RegionRect] | None = None,
    ) -> RefinementResult:
        for attempt in range(2):
            try:
                result = await self._do_refine(
                    image_base64,
                    modality,
                    valid_regions,
                    hypothesis=hypothesis,
                    crop_region=crop_region,
                    probe_id=probe_id,
                    crop_lead_regions=crop_lead_regions,
                )
            except (
                json.JSONDecodeError,
                BboxEvidenceError,
                ModelResponseParseError,
            ):
                if attempt:
                    self._last_parse_retry_count = attempt
                    raise
                logger.warning(
                    "Malformed refinement JSON; retrying once with a new turn"
                )
                continue
            self._last_parse_retry_count = attempt
            return result
        raise AssertionError("unreachable")

    async def _finalize_with_parse_retry(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        draft: AnalysisResult,
        refinement_trace: list[dict[str, object]],
    ) -> AnalysisResult:
        for attempt in range(2):
            try:
                result = await self._do_finalize(
                    image_base64,
                    modality,
                    valid_regions,
                    draft=draft,
                    refinement_trace=refinement_trace,
                )
            except (
                json.JSONDecodeError,
                BboxEvidenceError,
                ModelResponseParseError,
            ):
                if attempt:
                    self._last_parse_retry_count = attempt
                    raise
                logger.warning("Malformed final report JSON; retrying once")
                continue
            self._last_parse_retry_count = attempt
            return result
        raise AssertionError("unreachable")

    async def _do_analyze(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        return await self._do_analysis_turn(
            image_base64,
            modality,
            valid_regions,
            coarse_triage=False,
        )

    async def _do_coarse_analyze(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        return await self._do_analysis_turn(
            image_base64,
            modality,
            valid_regions,
            coarse_triage=True,
        )

    async def _do_analysis_turn(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        coarse_triage: bool,
    ) -> AnalysisResult:
        if not self.is_connected():
            raise ConnectionError("Not connected to OpenClaw Gateway")

        assert self._ws is not None

        skill = self._registry.resolve(modality.value).resolved_skill_name()
        waveform_context = self._waveform_artifact_context.get()
        bbox_evidence_nonce = uuid4().hex
        source_image_sha256 = _image_sha256(image_base64)
        prompt_args = {
            "waveform_artifact_id": (
                waveform_context.artifact_id if waveform_context else ""
            ),
            "waveform_lead_mode": (
                waveform_context.lead_mode if waveform_context else ""
            ),
            "waveform_evidence_nonce": (
                waveform_context.evidence_nonce if waveform_context else ""
            ),
            "bbox_source_image_sha256": source_image_sha256,
            "bbox_evidence_nonce": bbox_evidence_nonce,
        }
        prompt = (
            build_coarse_analysis_prompt(
                modality=modality,
                valid_regions=valid_regions,
                **prompt_args,
            )
            if coarse_triage and self._analysis_prompt_profile == "clinical"
            else _build_analysis_prompt(
                modality,
                valid_regions,
                skill,
                base_dir=self._base_dir,
                prompt_profile=self._analysis_prompt_profile,
                **prompt_args,
            )
        )
        request_id = self._next_request_id("chat")
        idempotency_key = str(uuid4())
        session_key = f"analysis-{idempotency_key}"
        self._begin_run_trace(
            session_key,
            bbox_evidence_nonce=bbox_evidence_nonce,
            source_image_sha256=source_image_sha256,
        )

        message = build_openclaw_chat_frame(
            request_id=request_id,
            session_key=session_key,
            message=prompt,
            idempotency_key=idempotency_key,
            image_base64=image_base64,
            fast_mode=self._fast_mode,
        )

        start = time.monotonic()
        payload_json = json.dumps(message)
        logger.info(
            "Sending analysis request: id=%s skill=%s payload_size=%dKB",
            request_id,
            skill,
            len(payload_json) // 1024,
        )
        response = await self._send_chat_result_frame(
            message, payload_json=payload_json
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        result = self._parse_result(response, elapsed_ms, modality)
        await self._await_bbox_tool_audit(result)
        if coarse_triage:
            self._retract_tool_rejected_coarse_boxes(result)
        self._require_bound_bbox_receipt(result)
        return result

    async def _do_refine(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        hypothesis: Finding | None,
        crop_region: RegionRect,
        probe_id: str = "",
        crop_lead_regions: dict[str, RegionRect] | None = None,
    ) -> RefinementResult:
        if not self.is_connected():
            raise ConnectionError("Not connected to OpenClaw Gateway")
        if not image_base64.strip():
            raise ValueError("image_base64 is required for refinement")

        assert self._ws is not None
        request_id = self._next_request_id("refine")
        idempotency_key = str(uuid4())
        session_key = f"refine-{idempotency_key}"
        bbox_evidence_nonce = uuid4().hex
        source_image_sha256 = _image_sha256(image_base64)
        self._begin_run_trace(
            session_key,
            bbox_evidence_nonce=bbox_evidence_nonce,
            source_image_sha256=source_image_sha256,
        )
        prompt = _build_refinement_prompt(
            modality=modality,
            valid_regions=valid_regions,
            hypothesis=hypothesis,
            crop_region=crop_region,
            probe_id=probe_id,
            crop_lead_regions=crop_lead_regions,
            supporting_waveform_evidence=(
                self._supporting_waveform_evidence()
                if modality is Modality.EKG
                else None
            ),
            bbox_source_image_sha256=source_image_sha256,
            bbox_evidence_nonce=bbox_evidence_nonce,
        )
        frame = build_openclaw_chat_frame(
            request_id=request_id,
            session_key=session_key,
            message=prompt,
            idempotency_key=idempotency_key,
            image_base64=image_base64,
            fast_mode=self._fast_mode,
        )
        response = await self._send_chat_result_frame(frame)
        result = _parse_refinement_result(response)
        await self._await_bbox_tool_audit(result)
        self._require_bound_bbox_receipt(result)
        return result

    async def _do_finalize(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        draft: AnalysisResult,
        refinement_trace: list[dict[str, object]],
    ) -> AnalysisResult:
        if not self.is_connected():
            raise ConnectionError("Not connected to OpenClaw Gateway")
        if not image_base64.strip():
            raise ValueError("image_base64 is required for finalization")

        assert self._ws is not None
        request_id = self._next_request_id("finalize")
        idempotency_key = str(uuid4())
        session_key = f"finalize-{idempotency_key}"
        bbox_evidence_nonce = uuid4().hex
        source_image_sha256 = _image_sha256(image_base64)
        self._begin_run_trace(
            session_key,
            bbox_evidence_nonce=bbox_evidence_nonce,
            source_image_sha256=source_image_sha256,
        )
        prompt = _build_finalization_prompt(
            modality=modality,
            valid_regions=valid_regions,
            draft=draft,
            refinement_trace=refinement_trace,
            bbox_source_image_sha256=source_image_sha256,
            bbox_evidence_nonce=bbox_evidence_nonce,
        )
        frame = build_openclaw_chat_frame(
            request_id=request_id,
            session_key=session_key,
            message=prompt,
            idempotency_key=idempotency_key,
            image_base64=image_base64,
            fast_mode=self._fast_mode,
        )
        start = time.monotonic()
        response = await self._send_chat_result_frame(frame)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        result = self._parse_result(response, elapsed_ms, modality)
        await self._await_bbox_tool_audit(result)
        return self._lock_finalization_geometry(draft, result)

    def _begin_run_trace(
        self,
        session_key: str,
        *,
        bbox_evidence_nonce: str = "",
        source_image_sha256: str = "",
    ) -> None:
        self._last_session_key = session_key
        self._last_run_id = ""
        self._last_run_tools = []
        self._last_parse_retry_count = 0
        self._last_run_started_at = time.monotonic()
        self._last_run_elapsed_ms = 0
        self._last_run_aborted = False
        self._bbox_evidence_nonce = bbox_evidence_nonce
        self._bbox_source_image_sha256 = source_image_sha256
        self._tool_audit_offset = _file_size(self._tool_audit_path)
        waveform_context = self._waveform_artifact_context.get()
        if waveform_context is None:
            self._ecg_founder_tool_audit_offset = _file_size(
                self._ecg_founder_tool_audit_path
            )
        self._last_tool_audit_records = []

    def last_run_trace(self) -> dict[str, object]:
        """Return auditable runtime facts, never hidden chain-of-thought."""
        self._refresh_tool_audit()
        return {
            "session_key": self._last_session_key,
            "run_id": self._last_run_id,
            "tools": list(self._last_run_tools),
            "tool_audit": list(self._last_tool_audit_records),
            "bbox_evidence": {
                "source_image_sha256": self._bbox_source_image_sha256,
                "evidence_nonce": self._bbox_evidence_nonce,
                "receipt_count": sum(
                    1
                    for record in self._last_tool_audit_records
                    if record.get("tool") == "dicom_bbox_validate"
                ),
            },
            "parse_retry_count": self._last_parse_retry_count,
            "turn_elapsed_ms": self._current_run_elapsed_ms(),
            "turn_timeout_sec": self._inference_timeout,
            "turn_aborted": self._last_run_aborted,
            "fast_mode_requested": self._fast_mode,
            # Fast mode is a Gateway execution request. A provider service tier
            # is a separate transport fact and must come from a transport log.
            "priority_service_observed": None,
        }

    def _current_run_elapsed_ms(self) -> int:
        if self._last_run_elapsed_ms > 0:
            return self._last_run_elapsed_ms
        if self._last_run_started_at <= 0.0:
            return 0
        return int((time.monotonic() - self._last_run_started_at) * 1000)

    def _require_bound_bbox_receipt(
        self,
        result: AnalysisResult | RefinementResult,
    ) -> None:
        """Fail closed when boxed output is not the tool-accepted box set."""

        if (
            self._analysis_prompt_profile != "clinical"
            or not self._require_bbox_receipts
        ):
            return
        boxes = _result_bbox_coordinates(result)
        if not boxes:
            return
        expected_digest = _bbox_coordinates_digest(boxes)
        self._refresh_tool_audit()
        matching = [
            record
            for record in self._last_tool_audit_records
            if record.get("tool") == "dicom_bbox_validate"
            and record.get("accepted_boxes_sha256") == expected_digest
            and record.get("accepted_count") == len(boxes)
        ]
        if not matching:
            raise BboxEvidenceError(
                "boxed output lacks a matching image/turn-bound "
                "dicom_bbox_validate receipt"
            )

    async def _await_bbox_tool_audit(
        self,
        result: AnalysisResult | RefinementResult,
    ) -> None:
        """Let a just-finished native tool append its turn-bound receipt.

        OpenClaw can publish the final Gateway event a few milliseconds before
        the native plugin's JSONL append becomes visible on Windows.  A bounded
        poll prevents that filesystem ordering race from triggering a second
        paid model turn or producing an incomplete refinement trace.  Turns
        without boxes do not pay the grace-period cost.
        """

        if (
            self._analysis_prompt_profile != "clinical"
            or not self._require_bbox_receipts
            or not _result_bbox_coordinates(result)
        ):
            return
        deadline = time.monotonic() + _BBOX_AUDIT_FLUSH_GRACE_SEC
        while True:
            self._refresh_tool_audit()
            if any(
                record.get("tool") == "dicom_bbox_validate"
                for record in self._last_tool_audit_records
            ):
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return
            await asyncio.sleep(min(_BBOX_AUDIT_POLL_INTERVAL_SEC, remaining))

    def _lock_finalization_geometry(
        self,
        draft: AnalysisResult,
        final: AnalysisResult,
    ) -> AnalysisResult:
        """Bind final dispositions to receipt-validated draft geometry.

        The final turn selects retained finding IDs; it doesn't own a second
        copy of their coordinates.  Models may shorten a decimal while
        serializing otherwise valid JSON, so receipt verification uses the
        exact draft boxes selected by those IDs and then replaces the redundant
        model coordinates deterministically.  No digest tolerance is added.
        """

        draft_ids = [finding.id for finding in draft.findings]
        if any(not finding_id for finding_id in draft_ids) or len(
            set(draft_ids)
        ) != len(draft_ids):
            raise ModelResponseParseError(
                "finalization draft findings require unique non-empty IDs"
            )
        final_ids = [finding.id for finding in final.findings]
        if any(not finding_id for finding_id in final_ids) or len(
            set(final_ids)
        ) != len(final_ids):
            raise ModelResponseParseError(
                "final report findings require unique non-empty draft IDs"
            )
        unknown_ids = sorted(set(final_ids) - set(draft_ids))
        if unknown_ids:
            raise ModelResponseParseError(
                "final report cannot add finding IDs: " + ", ".join(unknown_ids)
            )
        retained_ids = set(final_ids)
        expected_order = [
            finding_id for finding_id in draft_ids if finding_id in retained_ids
        ]
        if final_ids != expected_order:
            raise ModelResponseParseError(
                "final report finding IDs must retain draft order"
            )

        draft_by_id = {finding.id: finding for finding in draft.findings}
        locked_findings: list[Finding] = []
        exact_boxes: list[RegionRect] = []
        drifted_bbox_count = 0
        max_coordinate_drift = 0.0
        for final_finding in final.findings:
            draft_finding = draft_by_id[final_finding.id]
            if len(final_finding.bboxes) != len(draft_finding.bboxes):
                raise ModelResponseParseError(
                    "final report bbox count changed for " + final_finding.id
                )
            for draft_box, model_box in zip(
                draft_finding.bboxes,
                final_finding.bboxes,
                strict=True,
            ):
                bbox_drift = max(
                    abs(getattr(draft_box, axis) - getattr(model_box, axis))
                    for axis in ("x", "y", "w", "h")
                )
                max_coordinate_drift = max(max_coordinate_drift, bbox_drift)
                if bbox_drift > 0.0:
                    drifted_bbox_count += 1
            exact_boxes.extend(draft_finding.bboxes)
            locked_findings.append(
                replace(final_finding, bboxes=list(draft_finding.bboxes))
            )

        locked = replace(
            final,
            findings=locked_findings,
            analysis_trace=[
                *final.analysis_trace,
                {
                    "stage": "final_bbox_geometry_lock",
                    "status": "locked_to_receipt_bound_draft",
                    "tool": "dicom_bbox_validate",
                    "retained_finding_count": len(locked_findings),
                    "bbox_count": len(exact_boxes),
                    "model_bbox_drift_count": drifted_bbox_count,
                    "model_bbox_max_coordinate_drift": round(
                        max_coordinate_drift,
                        8,
                    ),
                    "digest_tolerance_applied": False,
                    "geometry_locked": True,
                },
            ],
        )
        self._require_bound_bbox_receipt(locked)
        if drifted_bbox_count:
            logger.warning(
                "Final report bbox decimals differed from receipt-bound draft; "
                "locked exact geometry",
                bbox_count=len(exact_boxes),
                drifted_bbox_count=drifted_bbox_count,
                max_coordinate_drift=round(max_coordinate_drift, 8),
            )
        return locked

    def _retract_tool_rejected_coarse_boxes(self, result: AnalysisResult) -> None:
        """Keep triage hypotheses but remove a fully rejected bbox proposal."""

        boxes = _result_bbox_coordinates(result)
        if not boxes:
            return
        self._refresh_tool_audit()
        receipts = [
            record
            for record in self._last_tool_audit_records
            if record.get("tool") == "dicom_bbox_validate"
        ]
        if len(receipts) != 1:
            return
        receipt = receipts[0]
        if receipt.get("accepted_count") != 0 or not (
            isinstance(receipt.get("rejected_count"), int)
            and int(receipt["rejected_count"]) > 0
        ):
            return

        result.findings = [
            replace(finding, bboxes=[]) if finding.bboxes else finding
            for finding in result.findings
        ]
        result.incomplete = True
        incomplete_reason = (
            "Preliminary bbox validator rejected all candidate coordinates; "
            "findings remain unlocalized pending crop refinement."
        )
        if incomplete_reason not in result.incomplete_reasons:
            result.incomplete_reasons.append(incomplete_reason)
        result.review_required = True
        review_reason = (
            "All preliminary bbox coordinates were rejected by the bound validator."
        )
        if review_reason not in result.review_reasons:
            result.review_reasons.append(review_reason)
        result.analysis_trace.append(
            {
                "stage": "bbox_receipt_reconciliation",
                "status": "retracted_rejected_coarse_boxes",
                "tool": "dicom_bbox_validate",
                "tool_call_id": str(receipt.get("tool_call_id") or ""),
                "accepted_count": 0,
                "rejected_count": int(receipt["rejected_count"]),
                "retracted_count": len(boxes),
            }
        )

    def _refresh_tool_audit(self) -> None:
        """Read native-plugin evidence appended since this model turn began."""
        self._tool_audit_offset, bbox_records = _read_new_tool_audit_records(
            self._tool_audit_path,
            self._tool_audit_offset,
            _valid_bbox_tool_audit_record,
        )
        bbox_records = [
            record
            for record in bbox_records
            if record.get("evidence_nonce") == self._bbox_evidence_nonce
            and record.get("source_image_sha256") == self._bbox_source_image_sha256
        ]
        binding = self._waveform_artifact_context.get()
        if binding is not None:
            ecg_records = self._refresh_waveform_binding(binding)
        else:
            self._ecg_founder_tool_audit_offset, _discarded = (
                _read_new_tool_audit_records(
                    self._ecg_founder_tool_audit_path,
                    self._ecg_founder_tool_audit_offset,
                    _valid_ecg_founder_tool_audit_record,
                )
            )
            ecg_records = []
        for record in [*bbox_records, *ecg_records]:
            self._last_tool_audit_records.append(record)
            tool = record["tool"]
            if isinstance(tool, str) and tool not in self._last_run_tools:
                self._last_run_tools.append(tool)

    def _refresh_waveform_binding(
        self,
        binding: _WaveformArtifactBinding,
    ) -> list[dict[str, object]]:
        binding.audit_offset, records = _read_new_tool_audit_records(
            self._ecg_founder_tool_audit_path,
            binding.audit_offset,
            _valid_ecg_founder_tool_audit_record,
        )
        new_records: list[dict[str, object]] = []
        for record in records:
            if record.get("evidence_nonce") != binding.evidence_nonce:
                continue
            tool_call_id = str(record.get("tool_call_id") or "")
            if not tool_call_id or tool_call_id in binding.tool_call_ids:
                continue
            binding.tool_call_ids.add(tool_call_id)
            copied = dict(record)
            if record.get("status") == "duplicate_suppressed":
                binding.duplicate_attempts.append(copied)
            else:
                binding.receipts.append(copied)
            new_records.append(copied)
        return new_records

    def _supporting_waveform_evidence(self) -> dict[str, object] | None:
        """Return bounded, PHI-free evidence for later image verification turns."""

        binding = self._waveform_artifact_context.get()
        if binding is None:
            return None
        self._refresh_waveform_binding(binding)
        successful = [
            receipt
            for receipt in binding.receipts
            if receipt.get("status") == "ok"
            and receipt.get("evidence_nonce") == binding.evidence_nonce
        ]
        if len(successful) != 1:
            return None
        receipt = successful[0]
        predictions = []
        raw_predictions = receipt.get("predictions")
        if isinstance(raw_predictions, list):
            for item in raw_predictions[:10]:
                if not isinstance(item, dict):
                    continue
                label = item.get("label")
                probability = item.get("probability")
                if not isinstance(label, str) or not isinstance(
                    probability, (int, float)
                ):
                    continue
                predictions.append(
                    {
                        "label": label,
                        "uncalibrated_score": round(float(probability), 6),
                    }
                )
        if not predictions:
            return None
        evidence: dict[str, object] = {
            "status": "ok",
            "use_policy": "supporting_evidence_only",
            "calibration_status": str(
                receipt.get("calibration_status") or "uncalibrated"
            ),
            "model_id": str(receipt.get("model_id") or ""),
            "model_revision": str(receipt.get("model_revision") or ""),
            "predictions": predictions,
        }
        rhythm_measurement = _supporting_rhythm_measurement(receipt)
        if rhythm_measurement is not None:
            evidence["rhythm_measurement"] = rhythm_measurement
        return evidence

    async def chat(self, message: str) -> str:
        """Send a free-text question with acceptance-aware recovery."""
        async with self._ws_lock:
            return await self._do_chat(message)

    async def chat_about_image(
        self,
        message: str,
        *,
        image_base64: str,
        context: str = "",
    ) -> str:
        """Ask a follow-up question about the same image with context attached."""
        prompt = _build_image_followup_prompt(message=message, context=context)
        return await self._chat_about_image_prompt(
            prompt,
            image_base64=image_base64,
        )

    async def review_region_about_image(
        self,
        prompt: str,
        *,
        image_base64: str,
    ) -> str:
        """Run a complete structured regional-review prompt against a crop.

        Unlike :meth:`chat_about_image`, ``prompt`` already contains its output
        contract. Keeping this as an explicit API prevents the generic prose
        wrapper from contradicting the JSON-only review-writeback schema.
        """

        if not prompt.strip():
            raise ValueError("prompt is required for regional review")
        return await self._chat_about_image_prompt(
            prompt,
            image_base64=image_base64,
        )

    async def review_region_about_image_with_trace(
        self,
        prompt: str,
        *,
        image_base64: str,
    ) -> tuple[str, dict[str, object]]:
        """Run a regional review and atomically return its public run trace."""

        if not prompt.strip():
            raise ValueError("prompt is required for regional review")
        return await self._chat_about_image_prompt_and_trace(
            prompt,
            image_base64=image_base64,
        )

    async def _chat_about_image_prompt(
        self,
        prompt: str,
        *,
        image_base64: str,
    ) -> str:
        response, _trace = await self._chat_about_image_prompt_and_trace(
            prompt,
            image_base64=image_base64,
        )
        return response

    async def _chat_about_image_prompt_and_trace(
        self,
        prompt: str,
        *,
        image_base64: str,
    ) -> tuple[str, dict[str, object]]:
        async with self._ws_lock:
            response = await self._do_image_chat_prompt(
                prompt,
                image_base64=image_base64,
            )
            return response, self.last_run_trace()

    async def _do_chat(self, message: str) -> str:
        if not self.is_connected():
            raise ConnectionError("Not connected to OpenClaw Gateway")

        assert self._ws is not None

        request_id = self._next_request_id("chat")
        idempotency_key = str(uuid4())
        session_key = f"image-followup-{idempotency_key}"
        self._begin_run_trace(session_key)

        frame = build_openclaw_chat_frame(
            request_id=request_id,
            session_key=session_key,
            message=message,
            idempotency_key=idempotency_key,
            fast_mode=self._fast_mode,
        )

        return await self._send_chat_text_frame(frame)

    async def _do_image_chat_prompt(
        self,
        prompt: str,
        *,
        image_base64: str,
    ) -> str:
        if not self.is_connected():
            raise ConnectionError("Not connected to OpenClaw Gateway")
        if not image_base64.strip():
            raise ValueError("image_base64 is required for image follow-up chat")

        assert self._ws is not None

        request_id = self._next_request_id("chat")
        idempotency_key = str(uuid4())
        session_key = f"image-followup-{idempotency_key}"
        self._begin_run_trace(session_key)

        frame = build_openclaw_chat_frame(
            request_id=request_id,
            session_key=session_key,
            message=prompt,
            idempotency_key=idempotency_key,
            image_base64=image_base64,
            fast_mode=self._fast_mode,
        )

        return await self._send_chat_text_frame(frame)

    async def _send_chat_result_frame(
        self,
        frame: dict[str, Any],
        *,
        payload_json: str | None = None,
    ) -> dict[str, Any]:
        result = await self._send_chat_frame_with_recovery(
            frame,
            expect_text=False,
            payload_json=payload_json,
        )
        if not isinstance(result, dict):
            raise TypeError("Gateway result frame returned non-object payload")
        return result

    async def _send_chat_text_frame(self, frame: dict[str, Any]) -> str:
        result = await self._send_chat_frame_with_recovery(frame, expect_text=True)
        if not isinstance(result, str):
            raise TypeError("Gateway text frame returned non-text payload")
        return result

    async def _send_chat_frame_with_recovery(
        self,
        frame: dict[str, Any],
        *,
        expect_text: bool,
        payload_json: str | None = None,
    ) -> dict[str, Any] | str:
        """Run one immutable ``chat.send`` frame with charge-safe recovery.

        Before Gateway acceptance, a single replay is allowed and uses the
        exact same request, session, and idempotency key.  Once an acceptance
        or run ID has been observed, reconnect only resumes the event stream
        for that run; it never submits another model turn.
        """

        if not self.is_connected():
            raise ConnectionError("Not connected to OpenClaw Gateway")
        request_id = str(frame.get("id") or "")
        if not request_id or frame.get("method") != "chat.send":
            raise ValueError("expected a chat.send frame with a request id")
        serialized = payload_json if payload_json is not None else json.dumps(frame)
        deadline = time.monotonic() + self._inference_timeout

        try:
            await self._send_current_transport(serialized, deadline=deadline)
            return await self._wait_for_chat_payload(
                request_id,
                expect_text=expect_text,
                deadline=deadline,
            )
        except _GatewayRunConnectionLost as interrupted:
            first_loss = interrupted

        logger.warning(
            "Gateway transport interrupted during chat turn",
            request_id=request_id,
            accepted=first_loss.accepted,
            run_id=first_loss.run_id or "",
        )
        await self._reconnect_interrupted_turn()

        if first_loss.accepted and not first_loss.run_id:
            raise ConnectionError(
                "Gateway accepted chat.send without a runId before disconnect; "
                "reconnected but did not replay the accepted model turn"
            ) from None

        try:
            if first_loss.accepted:
                logger.info(
                    "Observing accepted Gateway run after reconnect without replay",
                    request_id=request_id,
                    run_id=first_loss.run_id,
                )
                return await self._wait_for_chat_payload(
                    request_id,
                    expect_text=expect_text,
                    deadline=first_loss.deadline,
                    initial_run_id=first_loss.run_id,
                    response_accepted=True,
                )

            logger.info(
                "Replaying unaccepted Gateway frame once with the same idempotency key",
                request_id=request_id,
            )
            await self._send_current_transport(
                serialized,
                deadline=first_loss.deadline,
            )
            return await self._wait_for_chat_payload(
                request_id,
                expect_text=expect_text,
                deadline=first_loss.deadline,
            )
        except _GatewayRunConnectionLost:
            self._connected = False
            if first_loss.accepted:
                raise ConnectionError(
                    "Gateway connection lost while observing accepted run "
                    f"{first_loss.run_id}; chat.send was not replayed"
                ) from None
            raise ConnectionError(
                "Gateway connection lost after one idempotent pre-acceptance replay"
            ) from None

    async def _send_current_transport(self, payload: str, *, deadline: float) -> None:
        if self._ws is None:
            raise _GatewayRunConnectionLost(
                "Gateway transport unavailable before acceptance",
                run_id=None,
                accepted=False,
                deadline=deadline,
            )
        try:
            await self._ws.send(payload)
        except (
            websockets.ConnectionClosed,
            websockets.exceptions.ConcurrencyError,
        ) as exc:
            self._connected = False
            raise _GatewayRunConnectionLost(
                f"Gateway connection closed before acceptance: {exc}",
                run_id=None,
                accepted=False,
                deadline=deadline,
            ) from exc

    async def _reconnect_interrupted_turn(self) -> None:
        old_websocket = self._ws
        self._ws = None
        self._connected = False
        if old_websocket is not None:
            with suppress(Exception):
                await asyncio.wait_for(
                    old_websocket.close(),
                    timeout=self._close_timeout,
                )
        try:
            await self.connect()
        except Exception as exc:
            self._connected = False
            raise ConnectionError(f"Gateway reconnect failed: {exc}") from None

    async def _wait_for_chat_payload(
        self,
        request_id: str,
        *,
        expect_text: bool,
        deadline: float,
        initial_run_id: str | None = None,
        response_accepted: bool = False,
    ) -> dict[str, Any] | str:
        if expect_text:
            return await self._wait_for_chat_text(
                request_id,
                deadline=deadline,
                initial_run_id=initial_run_id,
                response_accepted=response_accepted,
            )
        return await self._wait_for_chat_result(
            request_id,
            deadline=deadline,
            initial_run_id=initial_run_id,
            response_accepted=response_accepted,
        )

    async def _wait_for_chat_text(
        self,
        request_id: str,
        *,
        deadline: float | None = None,
        initial_run_id: str | None = None,
        response_accepted: bool = False,
    ) -> str:
        """Wait for a chat response and return raw text (no JSON parsing)."""
        assert self._ws is not None

        run_id = initial_run_id
        accepted = response_accepted or run_id is not None
        deadline = deadline or (time.monotonic() + self._inference_timeout)
        while True:
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    raise TimeoutError
                raw = await self._recv_gateway_frame(remaining)
            except TimeoutError:
                await self._abort_chat_run(run_id)
                raise TimeoutError(
                    f"Chat timeout after {self._inference_timeout}s"
                ) from None
            except asyncio.CancelledError:
                self._schedule_chat_abort(run_id)
                raise
            except websockets.ConnectionClosed as exc:
                self._connected = False
                raise _GatewayRunConnectionLost(
                    f"Gateway connection closed: {exc}",
                    run_id=run_id,
                    accepted=accepted or run_id is not None,
                    deadline=deadline,
                ) from exc

            frame = json.loads(raw)
            frame_type = frame.get("type")

            if frame_type == "res" and frame.get("id") == request_id:
                self._record_tool_events(frame)
                if not frame.get("ok"):
                    error = frame.get("error", {})
                    raise RuntimeError(
                        f"OpenClaw error: {error.get('code')} - {error.get('message')}"
                    )
                payload = frame.get("payload", {})
                if payload.get("runId"):
                    run_id = payload["runId"]
                    self._last_run_id = str(run_id)
                    accepted = True
                if payload.get("status") == "accepted":
                    accepted = True
                    continue
                # Direct text result in res frame
                result = payload.get("result")
                if isinstance(result, dict):
                    self._last_run_elapsed_ms = self._current_run_elapsed_ms()
                    return _extract_text_from_payload(result)
                if payload.get("status") == "error":
                    raise RuntimeError(payload.get("summary", "Chat request failed"))
                continue

            if frame_type == "event":
                payload = frame.get("payload", {})
                # Skip events until we know our run_id (avoid stale events)
                if run_id is None:
                    continue
                if payload.get("runId") != run_id:
                    continue
                self._record_tool_events(frame)
                state = payload.get("state")
                if state == "error":
                    raise RuntimeError(payload.get("errorMessage", "Chat event error"))
                if state == "final":
                    self._last_run_elapsed_ms = self._current_run_elapsed_ms()
                    return _extract_text_from_event(payload)

    async def _handshake(self) -> None:
        assert self._ws is not None

        # Negotiate protocol 3..4. OpenClaw 2026.4.x speaks 3; 2026.5.x raised
        # the floor to 4 and made operator *write* scopes require a bound device
        # identity. The desktop app spawns the Gateway as a co-located child
        # process and talks to it over loopback, so it connects with the
        # local-backend self-pairing identity (client.id=gateway-client,
        # mode=backend). That trusted-local path grants operator scopes without
        # an interactive device-pairing flow.
        connect_id = self._next_request_id("connect")
        params: dict[str, Any] = {
            "minProtocol": 3,
            "maxProtocol": 4,
            "client": {
                "id": "gateway-client",
                "version": _OPENCLAW_VERSION,
                "platform": platform.platform(),
                "mode": "backend",
            },
            "role": "operator",
            "scopes": _DEFAULT_SCOPES,
        }
        if self._gateway_token:
            params["auth"] = {"token": self._gateway_token}
        frame = {
            "type": "req",
            "id": connect_id,
            "method": "connect",
            "params": params,
        }
        await self._ws.send(json.dumps(frame))

        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=self._timeout)
            response = json.loads(raw)
            if response.get("type") != "res" or response.get("id") != connect_id:
                self._pending_frames.append(raw)
                continue
            if not response.get("ok"):
                error = response.get("error", {})
                raise ConnectionError(
                    f"OpenClaw connect failed: {error.get('code')} - {error.get('message')}"
                )
            return

    async def _recv_gateway_frame(self, timeout: float) -> str:
        pending_frames: deque[str] | None = getattr(self, "_pending_frames", None)
        if pending_frames:
            return pending_frames.popleft()
        assert self._ws is not None
        raw: str | bytes = await asyncio.wait_for(
            self._ws.recv(),
            timeout=timeout,
        )
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    async def _wait_for_chat_result(
        self,
        request_id: str,
        *,
        deadline: float | None = None,
        initial_run_id: str | None = None,
        response_accepted: bool = False,
    ) -> dict[str, Any]:
        assert self._ws is not None

        run_id = initial_run_id
        accepted = response_accepted or run_id is not None
        deadline = deadline or (time.monotonic() + self._inference_timeout)
        logger.debug("Waiting for chat result, request_id=%s", request_id)
        while True:
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    raise TimeoutError
                raw = await self._recv_gateway_frame(remaining)
            except TimeoutError:
                await self._abort_chat_run(run_id)
                logger.error(
                    "OpenClaw analysis timed out after %ds (request_id=%s, run_id=%s)",
                    self._inference_timeout,
                    request_id,
                    run_id,
                )
                raise TimeoutError(
                    f"Analysis timeout after {self._inference_timeout}s"
                ) from None
            except asyncio.CancelledError:
                self._schedule_chat_abort(run_id)
                raise
            except websockets.ConnectionClosed as exc:
                self._connected = False
                raise _GatewayRunConnectionLost(
                    f"Gateway connection closed: {exc}",
                    run_id=run_id,
                    accepted=accepted or run_id is not None,
                    deadline=deadline,
                ) from exc

            frame = json.loads(raw)
            frame_type = frame.get("type")
            # Only log non-event frames to avoid flooding logs
            # (Gateway pushes dozens of event frames per request)
            if frame_type != "event":
                logger.debug(
                    "WS frame: type=%s id=%s method=%s",
                    frame_type,
                    frame.get("id"),
                    frame.get("method", frame.get("payload", {}).get("state", "")),
                )

            if frame_type == "res" and frame.get("id") == request_id:
                self._record_tool_events(frame)
                if not frame.get("ok"):
                    error = frame.get("error", {})
                    raise RuntimeError(
                        f"OpenClaw error: {error.get('code')} - {error.get('message')}"
                    )

                payload = frame.get("payload", {})
                status = payload.get("status")
                if payload.get("runId"):
                    run_id = payload["runId"]
                    self._last_run_id = str(run_id)
                    accepted = True
                if status == "accepted":
                    accepted = True
                    continue

                result = payload.get("result")
                if isinstance(result, dict):
                    self._last_run_elapsed_ms = self._current_run_elapsed_ms()
                    return _coerce_result_payload(result)

                if status == "error":
                    raise RuntimeError(
                        payload.get("summary", "OpenClaw request failed")
                    )

                continue

            if frame_type == "event":
                payload = frame.get("payload", {})
                # Skip events until we know our run_id (avoid stale events
                # from a previous run that are still buffered in the WS).
                if run_id is None:
                    continue
                if payload.get("runId") != run_id:
                    continue

                self._record_tool_events(frame)

                state = payload.get("state")
                if state == "error":
                    raise RuntimeError(
                        payload.get("errorMessage", "OpenClaw chat event error")
                    )
                if state == "final":
                    self._last_run_elapsed_ms = self._current_run_elapsed_ms()
                    return _payload_from_chat_event(payload)

    async def _abort_chat_run(self, run_id: str | None) -> None:
        """Ask Gateway to stop a timed-out turn without invoking another runtime."""
        if self._ws is None or not self._last_session_key:
            return
        self._last_run_aborted = True
        self._last_run_elapsed_ms = self._current_run_elapsed_ms()
        params: dict[str, object] = {"sessionKey": self._last_session_key}
        if run_id:
            params["runId"] = run_id
        frame = {
            "type": "req",
            "id": self._next_request_id("abort"),
            "method": "chat.abort",
            "params": params,
        }
        try:
            await asyncio.wait_for(self._ws.send(json.dumps(frame)), timeout=2.0)
        except Exception:
            logger.warning(
                "Could not send OpenClaw chat.abort",
                session_key=self._last_session_key,
                run_id=run_id or "",
            )

    def _schedule_chat_abort(self, run_id: str | None) -> None:
        """Schedule cancellation cleanup when an outer stage timeout cancels us."""
        try:
            task = asyncio.create_task(self._abort_chat_run(run_id))
        except RuntimeError:
            return

        def consume_result(done: asyncio.Task[None]) -> None:
            try:
                done.result()
            except (asyncio.CancelledError, Exception):
                return

        task.add_done_callback(consume_result)

    def _record_tool_events(self, frame: object) -> None:
        for tool_name in _extract_tool_names(frame):
            if tool_name not in self._last_run_tools:
                self._last_run_tools.append(tool_name)

    def _next_request_id(self, prefix: str) -> str:
        self._request_counter += 1
        return f"{prefix}-{self._request_counter}"

    def _parse_result(
        self,
        response: dict[str, Any],
        elapsed_ms: int,
        request_modality: Modality = Modality.EKG,
    ) -> AnalysisResult:
        payload = response.get("payload", response)

        findings = []
        parse_warnings: list[str] = []
        parse_trace: list[dict[str, object]] = []
        repair_count = payload.get("_harness_json_repair_count", 0)
        if (
            isinstance(repair_count, int)
            and not isinstance(repair_count, bool)
            and repair_count > 0
        ):
            # The recovery routine only inserts an unambiguous missing closer;
            # it never changes a clinical value. Keep this visible as transport
            # audit evidence without classifying a recovered result as a
            # clinical/schema degradation.
            parse_trace.append(
                {
                    "stage": "json_recovery",
                    "status": "repaired",
                    "tool": "bounded_json_delimiter_repair",
                    "repair_count": repair_count,
                }
            )
        for f in payload.get("findings", []):
            # The LLM occasionally emits a bare string/number for a finding
            # instead of an object; skip anything we cannot treat as a dict.
            if not isinstance(f, dict):
                logger.warning("Dropping non-object finding: %r", f)
                parse_warnings.append("Dropped a malformed non-object finding")
                continue
            # Parse AI-provided bounding boxes (normalized 0-1 coords)
            bboxes: list[RegionRect] = []
            for b in f.get("bboxes", []):
                try:
                    # Accept both object form {"x","y","w","h"} and the
                    # array form [x, y, w, h] that some models return.
                    if isinstance(b, dict):
                        x, y, w, h = (
                            b.get("x", 0),
                            b.get("y", 0),
                            b.get("w", 0),
                            b.get("h", 0),
                        )
                    elif isinstance(b, (list, tuple)) and len(b) >= 4:
                        x, y, w, h = b[0], b[1], b[2], b[3]
                    else:
                        raise TypeError(f"unsupported bbox shape: {type(b).__name__}")
                    x, y, w, h = (float(value) for value in (x, y, w, h))
                    if w <= 0.0 or h <= 0.0:
                        raise ValueError("bbox width and height must be positive")
                    if x < 0.0 or y < 0.0 or x + w > 1.0 or y + h > 1.0:
                        raise ValueError("bbox must fit within normalized image bounds")
                    bboxes.append(
                        RegionRect(
                            x=x,
                            y=y,
                            w=w,
                            h=h,
                        )
                    )
                except (ValueError, TypeError) as exc:
                    # Out-of-bounds or malformed bbox: drop it but make the
                    # degradation visible instead of silently swallowing it.
                    logger.warning(
                        "Dropping invalid bbox for finding %s: %s (%s)",
                        f.get("id", ""),
                        b,
                        exc,
                    )
                    parse_warnings.append(
                        f"Dropped invalid bbox for finding {f.get('id', '') or '(unnamed)'}"
                    )
            findings.append(
                Finding(
                    id=f.get("id", ""),
                    regions=f.get("regions", []),
                    label=f.get("label", ""),
                    detail=f.get("detail", ""),
                    severity=_parse_severity(f.get("severity", "info")),
                    bboxes=bboxes,
                    confidence=_parse_confidence(f.get("confidence", "")),
                    question=str(f.get("question", "") or "").strip(),
                )
            )

        checklist: dict[str, ChecklistItem] = {}
        for key, val in _iter_checklist(payload.get("checklist")):
            if isinstance(val, dict):
                checklist[key] = ChecklistItem(
                    value=val.get("value", ""),
                    status=_parse_severity(val.get("status", "normal")),
                )
            else:
                checklist[key] = ChecklistItem(
                    value=str(val),
                    status=Severity.INFO,
                )

        modality_str = payload.get("modality")
        if modality_str is None:
            modality = request_modality
        else:
            try:
                modality = Modality(modality_str)
            except ValueError:
                logger.warning(
                    "Unknown modality %r in result; using requested modality %s",
                    modality_str,
                    request_modality.value,
                )
                modality = request_modality

        layout = payload.get("layout")
        raw_image_quality = payload.get("image_quality", "")
        image_quality: str | dict[str, object]
        if isinstance(raw_image_quality, dict):
            image_quality = dict(raw_image_quality)
        elif isinstance(raw_image_quality, str):
            image_quality = raw_image_quality.strip()
        else:
            image_quality = ""
            if raw_image_quality not in (None, ""):
                parse_warnings.append("Dropped malformed image_quality metadata")

        parse_warnings = list(dict.fromkeys(parse_warnings))
        incomplete_reasons = _coerce_string_list(payload.get("incomplete_reasons", []))
        for warning in parse_warnings:
            if warning not in incomplete_reasons:
                incomplete_reasons.append(warning)
        incomplete = _coerce_bool(payload.get("incomplete", False)) or bool(
            incomplete_reasons or parse_warnings
        )
        return AnalysisResult(
            modality=modality,
            summary=payload.get("summary", ""),
            severity=_parse_severity(payload.get("severity", "info")),
            findings=findings,
            checklist=checklist,
            analysis_time_ms=payload.get("analysis_time_ms", elapsed_ms),
            model_used=str(payload.get("model_used", "") or "").strip(),
            image_quality=image_quality,
            next_steps=_coerce_string_list(payload.get("next_steps", [])),
            incomplete=incomplete,
            incomplete_reasons=incomplete_reasons,
            validation_warnings=parse_warnings,
            zoom_hints=_coerce_string_list(payload.get("zoom_hints", [])),
            review_required=_coerce_bool(payload.get("review_required", False)),
            review_reasons=_coerce_string_list(payload.get("review_reasons", [])),
            layout=layout if isinstance(layout, dict) else {},
            analysis_trace=parse_trace,
        )


def _parse_severity(s: str) -> Severity:
    normalized = str(s or "").strip().lower()
    if normalized in {"urgent", "emergent", "emergency"}:
        return Severity.CRITICAL
    try:
        return Severity(normalized)
    except ValueError:
        return Severity.INFO


def _parse_confidence(value: object) -> str:
    confidence = str(value or "").strip().lower()
    return confidence if confidence in {"high", "moderate", "low"} else ""


def _coerce_bool(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int) and raw in {0, 1}:
        return bool(raw)
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0", ""}:
            return False
    return False


def _coerce_string_list(raw: object) -> list[str]:
    if isinstance(raw, str):
        values: tuple[object, ...] = (raw,)
    elif isinstance(raw, (list, tuple)):
        values = tuple(raw)
    else:
        return []
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _iter_checklist(raw: object) -> list[tuple[str, object]]:
    """Yield (key, value) pairs from a checklist that may be a dict or a list.

    Models sometimes return ``checklist`` as a list (e.g. for CXR) instead of
    the expected object/dict shape (as EKG does). List entries may be dicts
    carrying their own key field (``key``/``name``/``label``/``item``) or be
    bare scalars; fall back to a positional key when no name is present.
    """
    if isinstance(raw, dict):
        return list(raw.items())
    if isinstance(raw, list):
        pairs: list[tuple[str, object]] = []
        for index, entry in enumerate(raw):
            if isinstance(entry, dict):
                key = (
                    entry.get("key")
                    or entry.get("name")
                    or entry.get("label")
                    or entry.get("item")
                    or f"item_{index}"
                )
                pairs.append((str(key), entry))
            else:
                pairs.append((f"item_{index}", entry))
        return pairs
    return []


def _build_analysis_prompt(
    modality: Modality,
    valid_regions: list[str],
    skill_name: str,
    *,
    base_dir: Path | None = None,
    waveform_artifact_id: str = "",
    waveform_lead_mode: str = "",
    waveform_evidence_nonce: str = "",
    bbox_source_image_sha256: str = "",
    bbox_evidence_nonce: str = "",
    prompt_profile: str = "clinical",
) -> str:
    if prompt_profile == "minimal_control":
        if waveform_artifact_id:
            raise ValueError("minimal control cannot use waveform evidence")
        return build_minimal_control_prompt(
            modality=modality,
            valid_regions=valid_regions,
        )
    if prompt_profile != "clinical":
        raise ValueError("unsupported analysis prompt profile")
    skill_prompt = _load_skill_prompt(skill_name, base_dir=base_dir)
    return build_initial_analysis_prompt(
        modality=modality,
        valid_regions=valid_regions,
        skill_name=skill_name,
        skill_prompt=skill_prompt,
        waveform_artifact_id=waveform_artifact_id,
        waveform_lead_mode=waveform_lead_mode,
        waveform_evidence_nonce=waveform_evidence_nonce,
        bbox_source_image_sha256=bbox_source_image_sha256,
        bbox_evidence_nonce=bbox_evidence_nonce,
    )


def _build_image_followup_prompt(*, message: str, context: str) -> str:
    prior_context = context.strip() or "(no prior structured result available)"
    return (
        "Answer the user's follow-up question about the same attached medical image.\n"
        "Use the prior structured interpretation as context, then re-check the "
        "attached image before answering. Do not invent findings that are not "
        "visible in the image.\n\n"
        f"Prior interpretation context:\n{prior_context}\n\n"
        f"User question: {message.strip()}\n\n"
        "Reply with concise clinical guidance. Mention relevant labels, tags, "
        "or regions when useful, and state when the image is insufficient for "
        "the requested conclusion."
    )


def _analysis_result_prompt_payload(result: AnalysisResult) -> dict[str, object]:
    return {
        "modality": result.modality.value,
        "summary": result.summary,
        "severity": result.severity.value,
        "findings": [
            {
                "id": finding.id,
                "label": finding.label,
                "detail": finding.detail,
                "severity": finding.severity.value,
                "confidence": finding.confidence,
                "question": finding.question,
                "source": finding.source,
                "regions": list(finding.regions),
                "bboxes": [
                    {"x": box.x, "y": box.y, "w": box.w, "h": box.h}
                    for box in finding.bboxes
                ],
                "notes": list(finding.notes),
            }
            for finding in result.findings
        ],
        "checklist": {
            key: {"value": item.value, "status": item.status.value}
            for key, item in result.checklist.items()
        },
        "layout": dict(result.layout),
        "image_quality": result.image_quality,
        "next_steps": list(result.next_steps),
        "model_used": result.model_used,
        "incomplete": result.incomplete,
        "incomplete_reasons": list(result.incomplete_reasons),
        "review_required": result.review_required,
        "review_reasons": list(result.review_reasons),
    }


def _build_finalization_prompt(
    *,
    modality: Modality,
    valid_regions: list[str],
    draft: AnalysisResult,
    refinement_trace: list[dict[str, object]],
    bbox_source_image_sha256: str = "",
    bbox_evidence_nonce: str = "",
) -> str:
    candidate_boxes = [
        {"x": box.x, "y": box.y, "w": box.w, "h": box.h}
        for finding in draft.findings
        for box in finding.bboxes
    ]
    safe_trace = [
        {
            "target_id": event.get("target_id", ""),
            "hypothesis": event.get("hypothesis", ""),
            "crop_source": event.get("crop_source", ""),
            "decisions": event.get("decisions", []),
        }
        for event in refinement_trace
    ]
    context = {
        "modality": modality.value,
        "allowed_regions": valid_regions,
        "final_grounded_draft": _analysis_result_prompt_payload(draft),
        "refinement_decisions": safe_trace,
        "candidate_bbox_count": len(candidate_boxes),
        "candidate_bbox_multiset": candidate_boxes,
    }
    checklist_contract = ""
    if modality is Modality.EKG:
        checklist_contract = (
            "- checklist must contain exactly these 16 axes, each as "
            "{value, status}: heart_rate, rhythm, regularity, axis, p_wave, "
            "pr_interval, qrs_duration, qrs_morphology, st_segment, t_wave, "
            "qtc_interval, chamber_enlargement, conduction, av_block, "
            "stemi_pattern, ischemia. Use indeterminate/not_assessable with info "
            "status when the image cannot support an axis.\n"
            "- Do not finalize sinus from regular timing alone. Require repeatable "
            "P waves before QRS complexes with a stable P-QRS relationship in a "
            "clear lead; AF/flutter likewise requires positive visible morphology. "
            "If neither is supported, keep rhythm indeterminate rather than force "
            "either.\n"
            "- When a clear ECG grid and lead II support visual categories, classify "
            "PR and QT qualitatively and inspect premature P-QRS complexes, coupling, "
            "and pauses across multiple beats. Do not invent milliseconds, but do "
            "not mark a visibly assessable category unassessable merely because the "
            "source is a screenshot.\n"
            f"- {EKG_LVH_BALANCE_GUIDANCE}\n"
            f"- {EKG_PRECORDIAL_REVIEW_GUIDANCE}\n"
            "- Clearly tall or broad T waves persisting across contiguous leads may "
            "be abnormal without ST elevation. Reconcile hyperkalemia, hyperacute "
            "ischemia, and benign variants; do not downgrade pathologic-looking "
            "morphology solely because reciprocal change is absent.\n"
        )
    bbox_contract = (
        f"- After choosing the retained finding IDs, call dicom_bbox_validate "
        f"exactly once with modality={modality.value}, "
        f"source_image_sha256='{bbox_source_image_sha256}', and "
        f"evidence_nonce='{bbox_evidence_nonce}'. Submit exactly the concatenated "
        "original coordinates belonging to those retained findings, in their "
        "draft order. Copy the accepted coordinates verbatim into the final "
        "findings. The final bbox multiset must exactly match that one receipt.\n"
        "- If every draft finding is retracted, return an empty findings array "
        "and do not call dicom_bbox_validate.\n"
        if candidate_boxes
        else "- There are no candidate boxes; do not call dicom_bbox_validate.\n"
    )
    return (
        "This is the final report-reconciliation turn for the attached original "
        "medical image. Crop verification has already produced the grounded draft "
        "below. Rewrite the complete report so summary, checklist, image quality, "
        "limitations, and next steps agree with the final finding set and all "
        "retractions/revisions. Return one JSON object only, with the same complete "
        "top-level shape as final_grounded_draft.\n\n"
        f"Context:\n{json.dumps(context, ensure_ascii=False)}\n\n"
        "Hard provenance rules:\n"
        "- For every draft finding, make one final disposition: RETAIN it unchanged, "
        "REVISE its label/detail/severity/confidence/question, or RETRACT it by "
        "omitting it from findings. This original-image turn may resolve an early "
        "crop candidate as a benign variant or artifact.\n"
        "- Do not retain duplicate study-level rate or rhythm findings with the "
        "same clinical meaning. Keep the best-grounded item (prefer lead II or a "
        "true rhythm strip) and RETRACT redundant IDs; never create duplicate "
        "labels merely to preserve boxes from separate crop turns.\n"
        "- Final finding IDs must be a unique subset of draft IDs and must remain "
        "in draft order. Never add, rename, split, or merge a finding.\n"
        "- For every retained or revised ID, copy source, regions, notes, and every "
        "full-image bbox exactly from that draft finding. Never move, resize, add, "
        "remove, or reassign its coordinates.\n"
        "- A revision must state only the concise final observable conclusion; do "
        "not preserve an earlier alarming label after concluding it is artifact "
        "or a benign variant. Retract it instead when no actionable or unresolved "
        "visual candidate remains.\n"
        "- Do not mention a retracted hypothesis as a present abnormality. Normal "
        "and negative observations belong in summary/checklist without boxes.\n"
        "- If findings is empty and all clinically assessable checklist axes are "
        "normal, state normal/WNL directly. Do not reintroduce names such as ST "
        "elevation, infarct, block, or ectopy from retracted candidates.\n"
        "- Reconcile every checklist axis with the retained findings. Use "
        "indeterminate/not_assessable with info status when screenshot detail or "
        "lead coverage is insufficient; normal/WNL is valid when supported.\n"
        "- If a retained finding keeps a potentially time-critical differential "
        "such as hyperacute ischemia, related checklist axes must not say normal "
        "or absent. Use indeterminate/possible with warning or critical status; "
        "do not convert the differential into a confirmed diagnosis.\n"
        "- An external waveform label such as normal/otherwise normal, or omission "
        "from its top-k list, is not negative evidence. Do not retract visually "
        "plausible time-critical contiguous ST-T morphology solely for that reason; "
        "use the attached original image and crop trace to resolve it.\n"
        "- When a retained draft documents an abrupt synchronized run of at least "
        "three broad QRS complexes across multiple leads, explicitly reconcile "
        "NSVT/VT versus artifact or conduction before finalizing. Do not relabel "
        "secondary ST-T distortion as ischemia alone. If ventricular tachycardia "
        "remains plausible, preserve it as a critical cautious differential with "
        "a concrete urgent-review question; do not call it confirmed without "
        "supporting rhythm morphology.\n"
        "- Preserve clinically honest incomplete reasons and cautious language. "
        "Do not invent precise measurements from a screenshot.\n"
        "- Top-level severity must agree with the final retained findings and "
        "checklist, with no severity floor inherited from a retracted draft "
        "candidate. Image-quality limitations do not raise clinical severity.\n"
        "- A non-urgent retained finding with a reviewer question is unresolved: "
        "keep it info/low-confidence and introduce it as possible or unresolved, "
        "not as a confirmed or 'consistent with' diagnosis. Clinical severity "
        "describes the study, not image-quality limitations.\n"
        "- Use concise clinical English for every JSON string value.\n"
        f"{checklist_contract}"
        f"{bbox_contract}"
        "- Every coordinate is relative to the attached original image, never a "
        "crop.\n"
        "- Output concise auditable conclusions only; never output hidden "
        "chain-of-thought or markdown."
    )


def _build_refinement_prompt(
    *,
    modality: Modality,
    valid_regions: list[str],
    hypothesis: Finding | None,
    crop_region: RegionRect,
    probe_id: str = "",
    crop_lead_regions: dict[str, RegionRect] | None = None,
    supporting_waveform_evidence: dict[str, object] | None = None,
    bbox_source_image_sha256: str = "",
    bbox_evidence_nonce: str = "",
) -> str:
    hypothesis_payload: dict[str, object] | None = None
    if hypothesis is not None:
        hypothesis_payload = {
            "id": hypothesis.id,
            "label": hypothesis.label,
            "detail": hypothesis.detail,
            "severity": hypothesis.severity.value,
            "regions": hypothesis.regions,
            "full_image_bboxes": [
                {"x": box.x, "y": box.y, "w": box.w, "h": box.h}
                for box in hypothesis.bboxes
            ],
        }
    context = {
        "modality": modality.value,
        "allowed_regions": valid_regions,
        "crop_in_original_image": {
            "x": crop_region.x,
            "y": crop_region.y,
            "w": crop_region.w,
            "h": crop_region.h,
        },
        "coarse_hypothesis": hypothesis_payload,
        "probe_id": probe_id,
        "probe_kind": (
            "systematic_hypothesis_verification"
            if hypothesis_payload is not None and probe_id.startswith("ekg_systematic_")
            else (
                "hypothesis_verification"
                if hypothesis_payload is not None
                else "systematic_discovery"
            )
        ),
    }
    if crop_lead_regions:
        context["crop_lead_regions"] = [
            {
                "region": name,
                "bbox_in_attached_crop": {
                    "x": round(region.x, 6),
                    "y": round(region.y, 6),
                    "w": round(region.w, 6),
                    "h": round(region.h, 6),
                },
            }
            for name, region in sorted(
                crop_lead_regions.items(),
                key=lambda item: (item[1].y, item[1].x, item[0]),
            )
        ]
    if supporting_waveform_evidence:
        context["supporting_waveform_evidence"] = supporting_waveform_evidence
    ekg_safety_guidance = ""
    if modality is Modality.EKG:
        probe_focus = ""
        if "waveform_rhythm" in probe_id:
            probe_focus = (
                " This crop was selected because the waveform-only supporting "
                "tool and whole-image read disagree about rhythm. Inspect lead II "
                "across enough consecutive beats for P-to-QRS relationships, "
                "visual PR/QT duration categories when scale is legible, "
                "prematurity/compensatory pauses, QRS morphology, and R-R pattern. "
                "AF/flutter requires positive visual rhythm evidence; irregularity "
                "or poorly resolved P waves alone is insufficient. Explicitly "
                "compare ectopy, missed peaks, pacing, and artifact before deciding."
            )
        elif "precordial_leads" in probe_id:
            probe_focus = (
                " This precordial probe must inspect V1-V6 without privileging one "
                "candidate: R/S progression, pathologic Q/QS morphology, QRS width "
                "and conduction pattern, high or low voltage, ST elevation or "
                "depression, T-wave morphology, contiguous-lead distribution, and "
                "reciprocal changes. Evaluate voltage across more than one qualifying "
                "lead group and assess supporting strain, axis, or morphology; apply "
                "the LVH balance rule below. Never let voltage displace R-wave "
                "progression. "
                "Clearly tall or broad contiguous T waves require an explicit "
                "hyperkalemia-versus-hyperacute-ischemia-versus-variant comparison "
                "even when definite ST elevation is absent. "
                "Test ranked candidates and close alternatives against their "
                "defining visible morphology. "
                f"{EKG_PRECORDIAL_REVIEW_GUIDANCE}"
            )
        elif "limb_leads" in probe_id:
            probe_focus = (
                " This limb-lead probe must inspect rate/rhythm, repeatable P-QRS "
                "relationships, premature atrial complexes/ectopy and pauses, "
                "qualitative PR/QT when the grid is legible, I/aVF axis, aVL voltage, "
                "conduction, II/III/aVF ST-T morphology, and reciprocal change."
            )
        waveform_guidance = ""
        if supporting_waveform_evidence:
            waveform_guidance = (
                " The context includes already acquired, uncalibrated waveform "
                "classifier candidates. They are not diagnoses and cannot create "
                "image boxes. Explicitly test each candidate relevant to this "
                "crop against visible morphology. Add or revise a finding only "
                "when the image supports it; reject unsupported candidates, but "
                "do not silently call the corresponding image axis normal. In "
                "each visible lead group, compare the candidate with its nearest "
                "confounders across rhythm/ectopy, QRS conduction, high versus low "
                "voltage, Q/QS or R-wave progression, and ST-T morphology. Ranked "
                "labels route inspection but never set diagnosis or severity. "
                "A normal/otherwise-normal ranked label or top-k omission is not "
                "negative evidence and cannot override visible contiguous "
                "morphology. "
                "Do not call ecg_founder_analyze_waveform again in this "
                "turn; the supplied evidence is the one permitted tool result. "
                "If rhythm_measurement is present, it is deterministic lead-II "
                "R-peak timing, independent of the uncalibrated classifier scores. "
                "Use its unrounded heart_rate_bpm_from_median_rr as supporting "
                "rate-category evidence: above 100 bpm is tachycardic even when a "
                "visual estimate rounds to about 100. It cannot identify P waves "
                "or diagnose AF. Irregularity can result "
                "from ectopy, missed peaks, pacing, or artifact. If PVC/PAC/ectopy "
                "is top-three and AF/flutter is not, explicitly test ectopy and do "
                "not infer AF solely from irregular timing or poor P-wave visibility."
            )
        ekg_safety_guidance = (
            " For an EKG crop, inspect every visible lead "
            "for rhythm, conduction, ST elevation/depression, reciprocal change, "
            "hyperacute or inverted T waves, chamber enlargement/voltage, and "
            "screenshot/lead limitations. "
            "Add only morphology visible in this crop; preserve uncertainty and "
            "ask a concrete reviewer question when an acute pattern cannot be "
            "confirmed from the screenshot. An unresolved hyperacute ischemic "
            "pattern is critical for triage even when it remains an uncertain "
            "differential; when contiguous-lead evidence remains after checking "
            "baseline, artifact, and benign variants, explicitly call it a possible "
            "acute ST-elevation ischemic pattern with STEMI not excluded rather "
            "than hiding it as nonspecific ST-T change. Do not call it confirmed. "
            "Conversely, retract a mild nonspecific or benign-variant candidate "
            "when comparison shows no reproducible morphology across at least two "
            "mapped contiguous or anatomically related leads and adjacent beats; "
            "do not keep info solely because any one-lead difference or noise is "
            "visible. Absence of acute ST elevation or reciprocal change alone is "
            "not a reason to retract a reproducible nonspecific ST-T/T-wave change. "
            f"{EKG_LVH_BALANCE_GUIDANCE} "
            "Diagnose a paced "
            "rhythm only when distinct narrow pacing spikes, separate from the "
            "QRS upstroke and grid lines, immediately precede multiple QRS "
            "complexes in at least two visible leads. Repetitive wide or tall "
            "QRS complexes alone are not pacing evidence; compare ventricular "
            "ectopy, bundle-branch conduction, high voltage, and artifact. Do not "
            "call sinus from regular timing alone: require repeatable P waves "
            "before QRS complexes with a stable P-QRS relationship in at least "
            "one clear lead. If neither sinus nor AF/flutter has positive visible "
            "morphology, keep the rhythm indeterminate rather than forcing either "
            "diagnosis. At an "
            "abrupt abnormal interval, test whether at least three consecutive "
            "broad QRS complexes recur at the same horizontal positions across "
            "multiple visible leads. If they do, evaluate NSVT/VT versus artifact "
            "or conduction before attributing secondary ST-T distortion to "
            "ischemia. A plausible ventricular run remains a critical cautious "
            "differential with an urgent-review question."
            f"{probe_focus}{waveform_guidance}"
        )
    return (
        "Re-examine the attached medical-image crop as a verification turn. "
        "Test the supplied coarse hypothesis against visible evidence; do not "
        "force an abnormal result. A normal or artifactual crop may retract the "
        "hypothesis. Finish this one bounded crop decision directly; do not inspect "
        "external files or call tools other than the required bbox validator. This "
        "is an auditable decision summary, not hidden reasoning.\n\n"
        f"Context:\n{json.dumps(context, ensure_ascii=False)}\n\n"
        "Return JSON only with this shape: "
        '{"deltas":[{"action":"confirm|revise|retract|add",'
        '"target_id":"coarse id or empty for add",'
        '"rationale":"brief visible-evidence explanation",'
        '"finding":{"id":"...","regions":["..."],"label":"...",'
        '"detail":"...","severity":"normal|info|warning|critical",'
        '"confidence":"high|moderate|low","question":"...",'
        '"bboxes":[{"x":0.0,"y":0.0,"w":0.1,"h":0.1}]}}]}.\n'
        "Use concise clinical English for every JSON string value. "
        "Use confirm only when label and severity remain unchanged. Use revise "
        "for a corrected label, severity, detail, or localization. Use retract "
        "when the target is not supported. Use add only for a distinct finding "
        "actually visible in this crop. For a safety probe with no hypothesis, "
        "return an empty deltas array when no abnormality is visible."
        " For a systematic_hypothesis_verification probe, decide the supplied "
        "target with confirm, revise, or retract before adding a distinct finding."
        f"{ekg_safety_guidance} "
        "If evidence is insufficient but the candidate remains useful for human "
        "review, revise it to severity info with confidence low and a concrete "
        "question; otherwise retract it. Never leave an info candidate without "
        "that uncertainty contract. A statement such as 'cannot assess' or "
        "'required leads are outside this crop' is a limitation, not a boxed "
        "finding: retract the hypothesis instead of revising it into a limitation. "
        "All finding "
        "bboxes are normalized to the attached crop, not the original image. "
        "For EKG, crop_lead_regions is the trusted deterministic map for this "
        "exact attached crop. The center of every returned box must fall inside "
        "one mapped lead and that lead must be included in finding.regions. Do "
        "not move a box to make it agree with a named lead. If morphology in a "
        "required lead is outside this crop, keep the limitation in rationale "
        "and do not invent a box for that lead. "
        f"Call dicom_bbox_validate with modality={modality.value}, "
        f"source_image_sha256='{bbox_source_image_sha256}', and "
        f"evidence_nonce='{bbox_evidence_nonce}'. Copy both binding values exactly. "
        "The final bbox multiset must exactly equal the accepted boxes from one "
        "validator call, not a subset or superset; validate only boxes you will "
        "retain. "
        "For EKG, each "
        "box must have w<=0.35, h<=0.30, and area<=0.08; use multiple local "
        "boxes instead of an entire lead row. Copy the tool's accepted "
        "attached-image coordinates verbatim. Keep rationale concise and based "
        "on observable morphology; do not output chain-of-thought. Before sending, "
        "perform one JSON syntax check: every bbox array has exactly four numbers "
        "and closes with ], and every object/array delimiter is balanced."
    )


def _parse_refinement_finding(raw: object) -> Finding | None:
    if not isinstance(raw, dict):
        return None
    boxes: list[RegionRect] = []
    for candidate in raw.get("bboxes", []):
        try:
            if isinstance(candidate, dict):
                values = (
                    candidate.get("x"),
                    candidate.get("y"),
                    candidate.get("w"),
                    candidate.get("h"),
                )
            elif isinstance(candidate, (list, tuple)) and len(candidate) >= 4:
                values = (candidate[0], candidate[1], candidate[2], candidate[3])
            else:
                continue
            coordinates: list[float] = []
            for value in values:
                if not isinstance(value, int | float | str):
                    raise TypeError
                coordinates.append(float(value))
            x, y, w, h = coordinates
            if w <= 0.0 or h <= 0.0:
                continue
            boxes.append(RegionRect(x=x, y=y, w=w, h=h))
        except (TypeError, ValueError):
            continue
    raw_regions = raw.get("regions", [])
    regions = (
        [str(value) for value in raw_regions] if isinstance(raw_regions, list) else []
    )
    return Finding(
        id=str(raw.get("id", "")).strip(),
        regions=regions,
        label=str(raw.get("label", "")).strip(),
        detail=str(raw.get("detail", "")).strip(),
        severity=_parse_severity(str(raw.get("severity", "info"))),
        bboxes=boxes,
        confidence=_parse_confidence(raw.get("confidence", "")),
        question=str(raw.get("question", "") or "").strip(),
    )


def _parse_refinement_result(response: dict[str, Any]) -> RefinementResult:
    payload = _coerce_result_payload(response)
    raw_deltas = payload.get("deltas", [])
    if not isinstance(raw_deltas, list):
        raise ModelResponseParseError(
            "OpenClaw refinement response has no deltas array"
        )
    deltas: list[RefinementDelta] = []
    for raw in raw_deltas:
        if not isinstance(raw, dict):
            continue
        try:
            action = RefinementAction(str(raw.get("action", "")).lower())
            target_id = str(raw.get("target_id", "")).strip()
            finding = _parse_refinement_finding(raw.get("finding"))
            rationale = str(raw.get("rationale", "")).strip()
            if finding is not None and _is_nonfinding_limitation(finding):
                if not target_id:
                    continue
                action = RefinementAction.RETRACT
                finding = None
                rationale = (
                    rationale
                    or "Crop lacks the evidence required to retain this hypothesis."
                )
            delta = RefinementDelta(
                action=action,
                target_id=target_id,
                finding=finding,
                rationale=rationale,
            )
        except ValueError:
            logger.warning("Dropping invalid refinement delta", delta=raw)
            continue
        deltas.append(delta)
    return RefinementResult(tuple(deltas))


def _is_nonfinding_limitation(finding: Finding) -> bool:
    text = f"{finding.label} {finding.detail}".lower()
    return any(
        phrase in text
        for phrase in (
            "cannot be assessed",
            "cannot be assess",
            "cannot assess",
            "not assessable",
            "unable to assess",
            "insufficient to assess",
        )
    )


def _load_skill_prompt(skill_name: str, *, base_dir: Path | None = None) -> str:
    root = (base_dir or Path.cwd()).resolve()
    for base in _SKILL_BASE_DIRS:
        path = root / base / skill_name / "SKILL.md"
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            return _strip_frontmatter(raw).strip()
    raise FileNotFoundError(f"Skill prompt not found: {skill_name}")


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text
    return parts[2]


def _strip_code_fence(text: str) -> str:
    """Strip markdown code fences (```json ... ``` or ``` ... ```)."""
    import re

    text = text.strip()
    # Use re.search for flexibility with leading/trailing content
    m = re.search(r"```(?:\w+)?\s*\r?\n(.*?)\r?\n\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def _payload_from_chat_event(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message", {})
    content = message.get("content", []) if isinstance(message, dict) else []
    text_parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(block.get("text", ""))
    text = "\n".join(part for part in text_parts if part).strip()
    if not text:
        raise ModelResponseParseError("OpenClaw returned an empty final chat message")
    text = _strip_code_fence(text)
    repaired_text = _repair_common_json_glitches(text)
    structural_repair_count = 0
    try:
        data = json.loads(repaired_text)
    except JSONDecodeError as exc:
        structurally_repaired, repair_count = _repair_missing_json_closers(
            repaired_text
        )
        if repair_count:
            try:
                data = json.loads(structurally_repaired)
            except JSONDecodeError:
                pass
            else:
                logger.warning(
                    "Recovered JSON with %d bounded structural delimiter repair(s)",
                    repair_count,
                )
                result = dict(_coerce_result_payload(data))
                result["_harness_json_repair_count"] = repair_count
                return result
        # The model sometimes wraps JSON in prose ("Here is the result: {...}").
        # Fall back to extracting the first balanced {...} block before giving up.
        extracted = _extract_first_json_object(text)
        if extracted is None:
            raise ModelResponseParseError(text) from exc
        repaired_extracted = _repair_common_json_glitches(extracted)
        logger.warning(
            "Recovered JSON from prose response via brace extraction (%d chars dropped)",
            len(text) - len(extracted),
        )
        try:
            data = json.loads(repaired_extracted)
        except JSONDecodeError:
            repaired_extracted, structural_repair_count = _repair_missing_json_closers(
                repaired_extracted
            )
            if not structural_repair_count:
                raise
            data = json.loads(repaired_extracted)
            logger.warning(
                "Recovered extracted JSON with %d bounded structural delimiter "
                "repair(s)",
                structural_repair_count,
            )
    result = dict(_coerce_result_payload(data))
    if structural_repair_count:
        result["_harness_json_repair_count"] = structural_repair_count
    return result


def _repair_common_json_glitches(text: str) -> str:
    """Repair narrow, common LLM JSON glitches without changing semantics."""

    # GPT vision responses occasionally emit numeric bbox fields like
    # {"x": 0.17", "y": 0.22}. Removing that stray quote turns it back into
    # the intended number while leaving quoted strings untouched.
    repaired = re.sub(
        r'(:\s*-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"(?=\s*[,}\]])',
        r"\1",
        text,
    )
    # A truncated array closer occasionally arrives as
    # ``...,"last item","],"next_key":...``. The quote before ``]`` cannot
    # begin a valid value because the following token is an object member.
    return re.sub(
        r',\s*"\](?=\s*,\s*"[A-Za-z_][^"]*"\s*:)',
        "]",
        repaired,
    )


def _repair_missing_json_closers(
    text: str,
    *,
    max_repairs: int = 2,
) -> tuple[str, int]:
    """Insert only unambiguous missing container closers in model JSON.

    Supported cases are an object member beginning while an immediately nested
    array is still open, and an adjacent ``}]`` pair emitted where the stack
    unambiguously requires ``]}``. This does not alter strings or scalar values,
    and callers must still pass the result through the standard JSON decoder.
    """
    if max_repairs <= 0:
        return text, 0

    output: list[str] = []
    stack: list[str] = []
    in_string = False
    escaped = False
    repair_count = 0
    skip_next = False

    for index, char in enumerate(text):
        if skip_next:
            skip_next = False
            continue
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            output.append(char)
            continue

        if (
            char == "}"
            and index + 1 < len(text)
            and text[index + 1] == "]"
            and repair_count < max_repairs
            and len(stack) >= 2
            and stack[-1] == "["
            and stack[-2] == "{"
        ):
            output.extend(("]", "}"))
            stack.pop()
            stack.pop()
            repair_count += 1
            skip_next = True
            continue

        if (
            char == ","
            and repair_count < max_repairs
            and len(stack) >= 2
            and stack[-1] == "["
            and stack[-2] == "{"
            and _next_json_token_is_object_member(text, index + 1)
        ):
            output.append("]")
            stack.pop()
            repair_count += 1

        if char in "[{":
            stack.append(char)
        elif stack and (
            (char == "]" and stack[-1] == "[") or (char == "}" and stack[-1] == "{")
        ):
            stack.pop()
        output.append(char)

    return ("".join(output), repair_count) if repair_count else (text, 0)


def _next_json_token_is_object_member(text: str, offset: int) -> bool:
    index = offset
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text) or text[index] != '"':
        return False
    index += 1
    escaped = False
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            index += 1
            break
        index += 1
    else:
        return False
    while index < len(text) and text[index].isspace():
        index += 1
    return index < len(text) and text[index] == ":"


def _extract_first_json_object(text: str) -> str | None:
    """Return the first balanced ``{...}`` substring, or ``None`` if absent.

    Brace matching is string/escape aware so braces inside JSON string values
    do not break the balance count.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _coerce_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "payload" in payload and isinstance(payload["payload"], dict):
        return payload["payload"]
    return payload


def _extract_text_from_event(payload: dict[str, Any]) -> str:
    """Extract raw text from a final chat event (no JSON parsing)."""
    message = payload.get("message", {})
    content = message.get("content", []) if isinstance(message, dict) else []
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    text = "\n".join(part for part in parts if part).strip()
    if not text:
        raise RuntimeError("OpenClaw returned an empty chat response")
    return text


def _extract_text_from_payload(payload: dict[str, Any]) -> str:
    """Extract raw text from a result payload dict."""
    if "text" in payload:
        return str(payload["text"])
    return json.dumps(payload, ensure_ascii=False)


def _extract_tool_names(value: object) -> list[str]:
    """Collect explicit tool-call names from Gateway event payloads."""
    found: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, dict):
            event_type = str(item.get("type", "")).lower().replace("_", "")
            if event_type in {
                "toolcall",
                "tooluse",
                "toolresult",
                "toolstart",
                "toolend",
            }:
                name = item.get("name") or item.get("toolName") or item.get("tool_name")
                if isinstance(name, str) and name.strip():
                    found.append(name.strip())
            for key in ("toolName", "tool_name"):
                name = item.get(key)
                if isinstance(name, str) and name.strip():
                    found.append(name.strip())
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return list(dict.fromkeys(found))


def _resolve_bbox_tool_audit_path(base_dir: Path) -> Path:
    configured = os.getenv("DICOM_BBOX_AUDIT_PATH", "").strip()
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else (base_dir / path).resolve()
    return (base_dir / "data" / "tmp" / "bbox-tool-audit.jsonl").resolve()


def _resolve_ecg_founder_tool_audit_path(base_dir: Path) -> Path:
    configured = os.getenv("DICOM_ECGFOUNDER_AUDIT_PATH", "").strip()
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else (base_dir / path).resolve()
    return (base_dir / "data" / "tmp" / "ecgfounder-tool-audit.jsonl").resolve()


def _read_new_tool_audit_records(
    path: Path,
    offset: int,
    validator: Callable[[object], bool],
) -> tuple[int, list[dict[str, object]]]:
    """Read and validate JSONL receipts appended after ``offset``."""
    start_offset = offset
    try:
        size = path.stat().st_size
        if size < offset:
            offset = 0
            start_offset = 0
        if size == offset:
            return offset, []
        with path.open("rb") as handle:
            handle.seek(offset)
            payload = handle.read()
    except OSError:
        return offset, []

    # Do not consume a record while another process is still appending it.  If
    # a reader advances past a partial JSON object, the completed receipt can
    # never be reconstructed on the next poll.  Native audit writers terminate
    # every JSONL record with a newline, so only complete lines are consumable.
    last_newline = payload.rfind(b"\n")
    if last_newline < 0:
        return start_offset, []
    complete_payload = payload[: last_newline + 1]
    offset = start_offset + len(complete_payload)
    records: list[dict[str, object]] = []
    for line in complete_payload.splitlines():
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if validator(record) and isinstance(record, dict):
            records.append(record)
    return offset, records


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _valid_bbox_tool_audit_record(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    digest = value.get("details_sha256")
    accepted = value.get("accepted_count")
    rejected = value.get("rejected_count")
    return (
        value.get("schema_version") == 2
        and value.get("tool") == "dicom_bbox_validate"
        and isinstance(value.get("tool_call_id"), str)
        and bool(value["tool_call_id"])
        and isinstance(accepted, int)
        and not isinstance(accepted, bool)
        and accepted >= 0
        and isinstance(rejected, int)
        and not isinstance(rejected, bool)
        and rejected >= 0
        and _is_sha256(value.get("source_image_sha256"))
        and isinstance(value.get("evidence_nonce"), str)
        and bool(re.fullmatch(r"[a-f0-9]{32}", value["evidence_nonce"]))
        and _is_sha256(value.get("accepted_boxes_sha256"))
        and isinstance(digest, str)
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest.lower())
    )


def _valid_ecg_founder_tool_audit_record(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("tool") == "ecg_founder_duplicate_suppressed":
        return bool(
            value.get("schema_version") == 1
            and value.get("original_tool") == "ecg_founder_analyze_waveform"
            and value.get("status") == "duplicate_suppressed"
            and isinstance(value.get("tool_call_id"), str)
            and bool(value["tool_call_id"])
            and isinstance(value.get("original_tool_call_id"), str)
            and bool(value["original_tool_call_id"])
            and value.get("original_status")
            in {"ok", "ineligible", "unavailable", "error"}
            and isinstance(value.get("evidence_nonce"), str)
            and bool(re.fullmatch(r"[a-f0-9]{32}", value["evidence_nonce"]))
            and _is_sha256(value.get("artifact_id_sha256"))
            and _is_sha256(value.get("request_sha256"))
        )
    artifact_digest = value.get("artifact_id_sha256")
    checkpoint_digest = value.get("checkpoint_sha256")
    prediction_count = value.get("prediction_count")
    status = value.get("status")
    evidence_nonce = value.get("evidence_nonce")
    return (
        value.get("schema_version") == 1
        and value.get("tool") == "ecg_founder_analyze_waveform"
        and isinstance(value.get("tool_call_id"), str)
        and bool(value["tool_call_id"])
        and status in {"ok", "ineligible", "unavailable", "error"}
        and isinstance(evidence_nonce, str)
        and bool(re.fullmatch(r"[a-f0-9]{32}", evidence_nonce))
        and isinstance(prediction_count, int)
        and not isinstance(prediction_count, bool)
        and 0 <= prediction_count <= 150
        and _is_sha256(artifact_digest)
        and (status != "ok" or _is_sha256(checkpoint_digest))
    )


def _supporting_rhythm_measurement(
    receipt: dict[str, object],
) -> dict[str, object] | None:
    response = receipt.get("response_evidence")
    if not isinstance(response, dict):
        return None
    raw = response.get("rhythm_measurement")
    if (
        not isinstance(raw, dict)
        or raw.get("method") != "lead_II_qrs_energy_v1"
        or raw.get("lead") != "II"
        or raw.get("status") != "ok"
        or raw.get("diagnostic_scope") != "rhythm_regularity_only"
        or raw.get("regularity_signal") not in {"regular", "irregular", "indeterminate"}
    ):
        return None

    interval_count = raw.get("rr_interval_count")
    intervals = raw.get("rr_intervals_ms")
    if (
        not isinstance(interval_count, int)
        or isinstance(interval_count, bool)
        or not 5 <= interval_count <= 30
        or not isinstance(intervals, list)
        or len(intervals) != interval_count
        or any(
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not 250 <= float(value) <= 3_000
            for value in intervals
        )
    ):
        return None

    numeric_ranges = {
        "median_rr_ms": (250.0, 3_000.0),
        "heart_rate_bpm_from_median_rr": (20.0, 240.0),
        "rr_cv": (0.0, 2.0),
        "rr_rmssd_ms": (0.0, 3_000.0),
        "rr_range_ms": (0.0, 3_000.0),
        "successive_rr_diff_over_80ms_fraction": (0.0, 1.0),
    }
    metrics: dict[str, float] = {}
    for key, (minimum, maximum) in numeric_ranges.items():
        value = raw.get(key)
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not minimum <= float(value) <= maximum
        ):
            return None
        metrics[key] = float(value)

    return {
        "method": "lead_II_qrs_energy_v1",
        "lead": "II",
        "status": "ok",
        "diagnostic_scope": "rhythm_regularity_only",
        "rr_interval_count": interval_count,
        "rr_intervals_ms": [round(float(value)) for value in intervals],
        **metrics,
        "regularity_signal": str(raw["regularity_signal"]),
        "limitations": [
            "R-peak timing only; it does not identify P waves or diagnose atrial fibrillation.",
            "Ectopy, missed peaks, pacing, and artifact can also cause irregular intervals.",
        ],
    }


def _is_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )


def _image_sha256(image_base64: str) -> str:
    try:
        image = base64.b64decode(image_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("image payload is not valid base64") from exc
    return hashlib.sha256(image).hexdigest()


def _result_bbox_coordinates(
    result: AnalysisResult | RefinementResult,
) -> list[RegionRect]:
    if isinstance(result, AnalysisResult):
        findings = result.findings
    else:
        findings = [
            delta.finding
            for delta in result.deltas
            if delta.finding is not None
            and delta.action
            in {
                RefinementAction.CONFIRM,
                RefinementAction.REVISE,
                RefinementAction.ADD,
            }
        ]
    return [box for finding in findings for box in finding.bboxes]


def _bbox_coordinates_digest(boxes: list[RegionRect]) -> str:
    def js_round(value: float) -> float:
        return math.floor(value * 10_000 + 0.5) / 10_000

    canonical = sorted(
        [f"{js_round(value):.4f}" for value in (box.x, box.y, box.w, box.h)]
        for box in boxes
    )
    encoded = json.dumps(canonical, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_openclaw_gateway_token(base_dir: Path | None = None) -> str | None:
    """Resolve Gateway auth without logging or returning unrelated secrets."""

    root = (base_dir or Path.cwd()).resolve()
    env_token = os.getenv("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if env_token:
        return env_token

    env_path = root / ".env"
    dotenv_token = read_env_file(env_path).get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if dotenv_token:
        return dotenv_token

    candidates = [
        root / "openclaw/openclaw.json",
        root / "openclaw/openclaw.valid.json",
        root / "openclaw/openclaw.portable.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        token = raw.get("gateway", {}).get("auth", {}).get("token", "")
        if isinstance(token, str) and token.startswith("${") and token.endswith("}"):
            env_name = token[2:-1].strip()
            env_value = (
                os.getenv(env_name, "").strip()
                or read_env_file(env_path).get(env_name, "").strip()
            )
            if env_value:
                return env_value
        if isinstance(token, str) and token.strip():
            return token.strip()
    return None


def _load_gateway_token(base_dir: Path | None = None) -> str | None:
    """Backward-compatible private alias for the public secret-safe resolver."""

    return resolve_openclaw_gateway_token(base_dir)
