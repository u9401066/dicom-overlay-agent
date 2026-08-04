"""OpenClaw Gateway WebSocket client (spec §3.3, §3.6)."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
import websockets

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

from dicom_overlay.application.interpretation_harness import (
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
_DEFAULT_SCOPES = [
    "operator.admin",
    "operator.read",
    "operator.write",
    "operator.approvals",
    "operator.pairing",
]
_WAVEFORM_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass
class _WaveformArtifactBinding:
    artifact_id: str
    lead_mode: str
    evidence_nonce: str
    audit_offset: int
    receipts: list[dict[str, object]] = field(default_factory=list)
    tool_call_ids: set[str] = field(default_factory=set)


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
    ) -> None:
        if analysis_prompt_profile not in _ANALYSIS_PROMPT_PROFILES:
            raise ValueError(
                "analysis_prompt_profile must be clinical or minimal_control"
            )
        self._url = gateway_url
        self._timeout = timeout_sec
        # Split timeouts: handshake is fast, inference can be slow on big images.
        self._connect_timeout = connect_timeout_sec or timeout_sec
        self._inference_timeout = inference_timeout_sec or timeout_sec
        self._reconnect_interval = reconnect_interval_sec
        self._registry = registry or get_active_registry()
        self._base_dir = (base_dir or Path.cwd()).resolve()
        self._analysis_prompt_profile = analysis_prompt_profile
        self._ws: Any = None
        self._connected = False
        self._request_counter = 0
        self._gateway_token = (
            gateway_token.strip() if gateway_token else None
        ) or _load_gateway_token(self._base_dir)
        if not self._gateway_token:
            logger.warning(
                "No OpenClaw gateway token configured; connect() will proceed without auth"
            )
        self._ws_lock = asyncio.Lock()  # Serialize all WebSocket send+recv sequences
        self._last_run_id = ""
        self._last_session_key = ""
        self._last_run_tools: list[str] = []
        self._last_parse_retry_count = 0
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

    async def connect(self) -> None:
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    self._url,
                    # Long medical-image inference can occupy the Gateway long
                    # enough for client-side WS keepalive to produce false
                    # failures. Use the explicit inference timeout instead.
                    ping_interval=None,
                    ping_timeout=None,
                    max_size=_MAX_WS_MESSAGE_BYTES,
                ),
                timeout=self._connect_timeout,
            )
            await asyncio.wait_for(self._handshake(), timeout=self._connect_timeout)
            self._connected = True
            logger.info("Connected to OpenClaw Gateway at %s", self._url)
        except Exception as exc:
            self._connected = False
            logger.warning("Failed to connect to OpenClaw Gateway: %s", exc)
            raise

    async def disconnect(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._connected = False
        logger.info("Disconnected from OpenClaw Gateway")

    def is_connected(self) -> bool:
        return self._connected and self._ws is not None

    async def analyze(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        """Analyze with auto-reconnect on connection loss."""
        async with self._ws_lock:
            try:
                return await self._analyze_with_parse_retry(
                    image_base64,
                    modality,
                    valid_regions,
                )
            except (
                websockets.ConnectionClosed,
                websockets.exceptions.ConcurrencyError,
            ):
                logger.warning("Connection lost during analysis, reconnecting...")
                self._connected = False
                try:
                    await self.connect()
                    return await self._analyze_with_parse_retry(
                        image_base64,
                        modality,
                        valid_regions,
                    )
                except websockets.ConnectionClosed:
                    self._connected = False
                    raise ConnectionError(
                        "Gateway connection lost after reconnect"
                    ) from None
                except ConnectionError:
                    raise
                except Exception as exc:
                    self._connected = False
                    raise ConnectionError(f"Reconnect failed: {exc}") from None

    async def refine(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        hypothesis: Finding | None,
        crop_region: RegionRect,
    ) -> RefinementResult:
        """Re-read one crop while explicitly testing the coarse hypothesis."""
        async with self._ws_lock:
            try:
                return await self._refine_with_parse_retry(
                    image_base64,
                    modality,
                    valid_regions,
                    hypothesis=hypothesis,
                    crop_region=crop_region,
                )
            except (
                websockets.ConnectionClosed,
                websockets.exceptions.ConcurrencyError,
            ):
                logger.warning("Connection lost during refinement, reconnecting...")
                self._connected = False
                try:
                    await self.connect()
                    return await self._refine_with_parse_retry(
                        image_base64,
                        modality,
                        valid_regions,
                        hypothesis=hypothesis,
                        crop_region=crop_region,
                    )
                except websockets.ConnectionClosed:
                    self._connected = False
                    raise ConnectionError(
                        "Gateway connection lost after reconnect"
                    ) from None
                except ConnectionError:
                    raise
                except Exception as exc:
                    self._connected = False
                    raise ConnectionError(f"Reconnect failed: {exc}") from None

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
            try:
                return await self._finalize_with_parse_retry(
                    image_base64,
                    modality,
                    valid_regions,
                    draft=draft,
                    refinement_trace=refinement_trace,
                )
            except (
                websockets.ConnectionClosed,
                websockets.exceptions.ConcurrencyError,
            ):
                logger.warning("Connection lost during finalization, reconnecting...")
                self._connected = False
                try:
                    await self.connect()
                    return await self._finalize_with_parse_retry(
                        image_base64,
                        modality,
                        valid_regions,
                        draft=draft,
                        refinement_trace=refinement_trace,
                    )
                except websockets.ConnectionClosed:
                    self._connected = False
                    raise ConnectionError(
                        "Gateway connection lost after reconnect"
                    ) from None
                except ConnectionError:
                    raise
                except Exception as exc:
                    self._connected = False
                    raise ConnectionError(f"Reconnect failed: {exc}") from None

    async def _analyze_with_parse_retry(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        for attempt in range(2):
            try:
                result = await self._do_analyze(image_base64, modality, valid_regions)
            except json.JSONDecodeError:
                if attempt:
                    self._last_parse_retry_count = attempt
                    raise
                logger.warning("Malformed analysis JSON; retrying once with a new turn")
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
    ) -> RefinementResult:
        for attempt in range(2):
            try:
                result = await self._do_refine(
                    image_base64,
                    modality,
                    valid_regions,
                    hypothesis=hypothesis,
                    crop_region=crop_region,
                )
            except json.JSONDecodeError:
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
            except json.JSONDecodeError:
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
        if not self.is_connected():
            raise ConnectionError("Not connected to OpenClaw Gateway")

        assert self._ws is not None

        skill = self._registry.resolve(modality.value).resolved_skill_name()
        waveform_context = self._waveform_artifact_context.get()
        prompt = _build_analysis_prompt(
            modality,
            valid_regions,
            skill,
            base_dir=self._base_dir,
            waveform_artifact_id=(
                waveform_context.artifact_id if waveform_context else ""
            ),
            waveform_lead_mode=(waveform_context.lead_mode if waveform_context else ""),
            waveform_evidence_nonce=(
                waveform_context.evidence_nonce if waveform_context else ""
            ),
            prompt_profile=self._analysis_prompt_profile,
        )
        request_id = self._next_request_id("chat")
        idempotency_key = str(uuid4())
        session_key = f"analysis-{idempotency_key}"
        self._begin_run_trace(session_key)

        message = build_openclaw_chat_frame(
            request_id=request_id,
            session_key=session_key,
            message=prompt,
            idempotency_key=idempotency_key,
            image_base64=image_base64,
        )

        start = time.monotonic()
        payload_json = json.dumps(message)
        logger.info(
            "Sending analysis request: id=%s skill=%s payload_size=%dKB",
            request_id,
            skill,
            len(payload_json) // 1024,
        )
        await self._ws.send(payload_json)

        response = await self._wait_for_chat_result(request_id)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return self._parse_result(response, elapsed_ms, modality)

    async def _do_refine(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        hypothesis: Finding | None,
        crop_region: RegionRect,
    ) -> RefinementResult:
        if not self.is_connected():
            raise ConnectionError("Not connected to OpenClaw Gateway")
        if not image_base64.strip():
            raise ValueError("image_base64 is required for refinement")

        assert self._ws is not None
        request_id = self._next_request_id("refine")
        idempotency_key = str(uuid4())
        session_key = f"refine-{idempotency_key}"
        self._begin_run_trace(session_key)
        prompt = _build_refinement_prompt(
            modality=modality,
            valid_regions=valid_regions,
            hypothesis=hypothesis,
            crop_region=crop_region,
        )
        frame = build_openclaw_chat_frame(
            request_id=request_id,
            session_key=session_key,
            message=prompt,
            idempotency_key=idempotency_key,
            image_base64=image_base64,
        )
        await self._ws.send(json.dumps(frame))
        response = await self._wait_for_chat_result(request_id)
        return _parse_refinement_result(response)

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
        self._begin_run_trace(session_key)
        prompt = _build_finalization_prompt(
            modality=modality,
            valid_regions=valid_regions,
            draft=draft,
            refinement_trace=refinement_trace,
        )
        frame = build_openclaw_chat_frame(
            request_id=request_id,
            session_key=session_key,
            message=prompt,
            idempotency_key=idempotency_key,
            image_base64=image_base64,
        )
        start = time.monotonic()
        await self._ws.send(json.dumps(frame))
        response = await self._wait_for_chat_result(request_id)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return self._parse_result(response, elapsed_ms, modality)

    def _begin_run_trace(self, session_key: str) -> None:
        self._last_session_key = session_key
        self._last_run_id = ""
        self._last_run_tools = []
        self._last_parse_retry_count = 0
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
            "parse_retry_count": self._last_parse_retry_count,
        }

    def _refresh_tool_audit(self) -> None:
        """Read native-plugin evidence appended since this model turn began."""
        self._tool_audit_offset, bbox_records = _read_new_tool_audit_records(
            self._tool_audit_path,
            self._tool_audit_offset,
            _valid_bbox_tool_audit_record,
        )
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
            binding.receipts.append(copied)
            new_records.append(copied)
        return new_records

    async def chat(self, message: str) -> str:
        """Send a free-text question with auto-reconnect on connection loss."""
        async with self._ws_lock:
            try:
                return await self._do_chat(message)
            except (
                websockets.ConnectionClosed,
                websockets.exceptions.ConcurrencyError,
            ):
                logger.warning("Connection lost during chat, reconnecting...")
                self._connected = False
                try:
                    await self.connect()
                    return await self._do_chat(message)
                except websockets.ConnectionClosed:
                    self._connected = False
                    raise ConnectionError(
                        "Gateway connection lost after reconnect"
                    ) from None
                except ConnectionError:
                    raise
                except Exception as exc:
                    self._connected = False
                    raise ConnectionError(f"Reconnect failed: {exc}") from None

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
            try:
                response = await self._do_image_chat_prompt(
                    prompt,
                    image_base64=image_base64,
                )
            except (
                websockets.ConnectionClosed,
                websockets.exceptions.ConcurrencyError,
            ):
                logger.warning("Connection lost during image chat, reconnecting...")
                self._connected = False
                try:
                    await self.connect()
                    response = await self._do_image_chat_prompt(
                        prompt,
                        image_base64=image_base64,
                    )
                except websockets.ConnectionClosed:
                    self._connected = False
                    raise ConnectionError(
                        "Gateway connection lost after reconnect"
                    ) from None
                except ConnectionError:
                    raise
                except Exception as exc:
                    self._connected = False
                    raise ConnectionError(f"Reconnect failed: {exc}") from None
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
        )

        await self._ws.send(json.dumps(frame))
        return await self._wait_for_chat_text(request_id)

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
        )

        await self._ws.send(json.dumps(frame))
        return await self._wait_for_chat_text(request_id)

    async def _wait_for_chat_text(self, request_id: str) -> str:
        """Wait for a chat response and return raw text (no JSON parsing)."""
        assert self._ws is not None

        run_id: str | None = None
        while True:
            try:
                raw = await asyncio.wait_for(
                    self._ws.recv(), timeout=self._inference_timeout
                )
            except TimeoutError:
                raise TimeoutError(
                    f"Chat timeout after {self._inference_timeout}s"
                ) from None
            except websockets.ConnectionClosed as exc:
                self._connected = False
                raise ConnectionError(f"Gateway connection closed: {exc}") from exc

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
                if payload.get("status") == "accepted":
                    continue
                # Direct text result in res frame
                result = payload.get("result")
                if isinstance(result, dict):
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
                continue
            if not response.get("ok"):
                error = response.get("error", {})
                raise ConnectionError(
                    f"OpenClaw connect failed: {error.get('code')} - {error.get('message')}"
                )
            return

    async def _wait_for_chat_result(self, request_id: str) -> dict[str, Any]:
        assert self._ws is not None

        run_id: str | None = None
        logger.debug("Waiting for chat result, request_id=%s", request_id)
        while True:
            try:
                raw = await asyncio.wait_for(
                    self._ws.recv(), timeout=self._inference_timeout
                )
            except TimeoutError:
                logger.error(
                    "OpenClaw analysis timed out after %ds (request_id=%s, run_id=%s)",
                    self._inference_timeout,
                    request_id,
                    run_id,
                )
                raise TimeoutError(
                    f"Analysis timeout after {self._inference_timeout}s"
                ) from None
            except websockets.ConnectionClosed as exc:
                self._connected = False
                raise ConnectionError(f"Gateway connection closed: {exc}") from exc

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
                if status == "accepted":
                    continue

                result = payload.get("result")
                if isinstance(result, dict):
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
                    return _payload_from_chat_event(payload)

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
        )


def _parse_severity(s: str) -> Severity:
    try:
        return Severity(s.lower())
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
        values = [raw]
    elif isinstance(raw, (list, tuple)):
        values = raw
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
) -> str:
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
    }
    return (
        "This is the final report-reconciliation turn for the attached original "
        "medical image. Crop verification has already produced the grounded draft "
        "below. Rewrite the complete report so summary, checklist, image quality, "
        "limitations, and next steps agree with the final finding set and all "
        "retractions/revisions. Return one JSON object only, with the same complete "
        "top-level shape as final_grounded_draft.\n\n"
        f"Context:\n{json.dumps(context, ensure_ascii=False)}\n\n"
        "Hard provenance rules:\n"
        "- Keep every final finding id, label, severity, confidence, question, "
        "regions, and full-image bbox exactly as supplied in final_grounded_draft. "
        "Do not add a diagnosis, finding, or bbox in this turn.\n"
        "- Do not mention a retracted hypothesis as a present abnormality. Normal "
        "and negative observations belong in summary/checklist without boxes.\n"
        "- Reconcile every checklist axis with the retained findings. Use "
        "indeterminate/not_assessable with info status when screenshot detail or "
        "lead coverage is insufficient; normal/WNL is valid when supported.\n"
        "- If a retained finding keeps a potentially time-critical differential "
        "such as hyperacute ischemia, related checklist axes must not say normal "
        "or absent. Use indeterminate/possible with warning or critical status; "
        "do not convert the differential into a confirmed diagnosis.\n"
        "- Preserve clinically honest incomplete reasons and cautious language. "
        "Do not invent precise measurements from a screenshot.\n"
        f"- Call dicom_bbox_validate with modality={modality.value} for all retained "
        "boxes and copy only accepted coordinates. These coordinates are relative "
        "to the attached original image, never a crop.\n"
        "- Output concise auditable conclusions only; never output hidden "
        "chain-of-thought or markdown."
    )


def _build_refinement_prompt(
    *,
    modality: Modality,
    valid_regions: list[str],
    hypothesis: Finding | None,
    crop_region: RegionRect,
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
        "probe_kind": (
            "hypothesis_verification"
            if hypothesis_payload is not None
            else "systematic_discovery"
        ),
    }
    ekg_safety_guidance = ""
    if hypothesis is None and modality is Modality.EKG:
        ekg_safety_guidance = (
            " For an EKG systematic-discovery crop, inspect every visible lead "
            "for rhythm, conduction, ST elevation/depression, reciprocal change, "
            "hyperacute or inverted T waves, and screenshot/lead limitations. "
            "Add only morphology visible in this crop; preserve uncertainty and "
            "ask a concrete reviewer question when an acute pattern cannot be "
            "confirmed from the screenshot. An unresolved hyperacute ischemic "
            "pattern is critical for triage even when it remains an uncertain "
            "differential; do not call it a confirmed STEMI."
        )
    return (
        "Re-examine the attached medical-image crop as a verification turn. "
        "Test the supplied coarse hypothesis against visible evidence; do not "
        "force an abnormal result. A normal or artifactual crop may retract the "
        "hypothesis. This is an auditable decision summary, not hidden reasoning.\n\n"
        f"Context:\n{json.dumps(context, ensure_ascii=False)}\n\n"
        "Return JSON only with this shape: "
        '{"deltas":[{"action":"confirm|revise|retract|add",'
        '"target_id":"coarse id or empty for add",'
        '"rationale":"brief visible-evidence explanation",'
        '"finding":{"id":"...","regions":["..."],"label":"...",'
        '"detail":"...","severity":"normal|info|warning|critical",'
        '"confidence":"high|moderate|low","question":"...",'
        '"bboxes":[{"x":0.0,"y":0.0,"w":0.1,"h":0.1}]}}]}.\n'
        "Use confirm only when label and severity remain unchanged. Use revise "
        "for a corrected label, severity, detail, or localization. Use retract "
        "when the target is not supported. Use add only for a distinct finding "
        "actually visible in this crop. For a safety probe with no hypothesis, "
        "return an empty deltas array when no abnormality is visible."
        f"{ekg_safety_guidance} "
        "If evidence is insufficient but the candidate remains useful for human "
        "review, revise it to severity info with confidence low and a concrete "
        "question; otherwise retract it. Never leave an info candidate without "
        "that uncertainty contract. A statement such as 'cannot assess' or "
        "'required leads are outside this crop' is a limitation, not a boxed "
        "finding: retract the hypothesis instead of revising it into a limitation. "
        "All finding "
        "bboxes are normalized to the attached crop, not the original image. "
        f"Call dicom_bbox_validate with modality={modality.value}. For EKG, each "
        "box must have w<=0.35, h<=0.30, and area<=0.08; use multiple local "
        "boxes instead of an entire lead row. Copy the tool's accepted "
        "attached-image coordinates verbatim. Keep rationale concise and based "
        "on observable morphology; do not output chain-of-thought."
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
                values = candidate[:4]
            else:
                continue
            x, y, w, h = (float(value) for value in values)
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
        raise RuntimeError("OpenClaw refinement response has no deltas array")
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
        raise RuntimeError("OpenClaw returned an empty final chat message")
    text = _strip_code_fence(text)
    repaired_text = _repair_common_json_glitches(text)
    try:
        data = json.loads(repaired_text)
    except JSONDecodeError as exc:
        # The model sometimes wraps JSON in prose ("Here is the result: {...}").
        # Fall back to extracting the first balanced {...} block before giving up.
        extracted = _extract_first_json_object(text)
        if extracted is None:
            raise RuntimeError(text) from exc
        repaired_extracted = _repair_common_json_glitches(extracted)
        logger.warning(
            "Recovered JSON from prose response via brace extraction (%d chars dropped)",
            len(text) - len(extracted),
        )
        data = json.loads(repaired_extracted)
    return _coerce_result_payload(data)


def _repair_common_json_glitches(text: str) -> str:
    """Repair narrow, common LLM JSON glitches without changing semantics."""

    # GPT vision responses occasionally emit numeric bbox fields like
    # {"x": 0.17", "y": 0.22}. Removing that stray quote turns it back into
    # the intended number while leaving quoted strings untouched.
    return re.sub(
        r'(:\s*-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"(?=\s*[,}\]])',
        r"\1",
        text,
    )


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
    try:
        size = path.stat().st_size
        if size < offset:
            offset = 0
        if size == offset:
            return offset, []
        with path.open("rb") as handle:
            handle.seek(offset)
            payload = handle.read()
            offset = handle.tell()
    except OSError:
        return offset, []

    records: list[dict[str, object]] = []
    for line in payload.splitlines():
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
        value.get("schema_version") == 1
        and value.get("tool") == "dicom_bbox_validate"
        and isinstance(value.get("tool_call_id"), str)
        and bool(value["tool_call_id"])
        and isinstance(accepted, int)
        and not isinstance(accepted, bool)
        and accepted >= 0
        and isinstance(rejected, int)
        and not isinstance(rejected, bool)
        and rejected >= 0
        and isinstance(digest, str)
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest.lower())
    )


def _valid_ecg_founder_tool_audit_record(value: object) -> bool:
    if not isinstance(value, dict):
        return False
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


def _is_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )


def _load_gateway_token(base_dir: Path | None = None) -> str | None:
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
