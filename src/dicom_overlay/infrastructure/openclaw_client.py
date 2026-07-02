"""OpenClaw Gateway WebSocket client (spec §3.3, §3.6)."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import time
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog
import websockets

from dicom_overlay.application.interpretation_harness import (
    build_initial_analysis_prompt,
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

_OPENCLAW_VERSION = "2026.3.11"
_SESSION_KEY = "main"
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
    ) -> None:
        self._url = gateway_url
        self._timeout = timeout_sec
        # Split timeouts: handshake is fast, inference can be slow on big images.
        self._connect_timeout = connect_timeout_sec or timeout_sec
        self._inference_timeout = inference_timeout_sec or timeout_sec
        self._reconnect_interval = reconnect_interval_sec
        self._registry = registry or get_active_registry()
        self._ws: Any = None
        self._connected = False
        self._request_counter = 0
        self._gateway_token = (
            gateway_token.strip() if gateway_token else None
        ) or _load_gateway_token()
        if not self._gateway_token:
            logger.warning(
                "No OpenClaw gateway token configured; connect() will proceed without auth"
            )
        self._ws_lock = asyncio.Lock()  # Serialize all WebSocket send+recv sequences

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
                return await self._do_analyze(image_base64, modality, valid_regions)
            except (
                websockets.ConnectionClosed,
                websockets.exceptions.ConcurrencyError,
            ):
                logger.warning("Connection lost during analysis, reconnecting...")
                self._connected = False
                try:
                    await self.connect()
                    return await self._do_analyze(image_base64, modality, valid_regions)
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
        prompt = _build_analysis_prompt(modality, valid_regions, skill)
        request_id = self._next_request_id("chat")
        idempotency_key = str(uuid4())
        session_key = f"analysis-{idempotency_key}"

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
        async with self._ws_lock:
            try:
                return await self._do_chat_about_image(
                    message,
                    image_base64=image_base64,
                    context=context,
                )
            except (
                websockets.ConnectionClosed,
                websockets.exceptions.ConcurrencyError,
            ):
                logger.warning("Connection lost during image chat, reconnecting...")
                self._connected = False
                try:
                    await self.connect()
                    return await self._do_chat_about_image(
                        message,
                        image_base64=image_base64,
                        context=context,
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

    async def _do_chat(self, message: str) -> str:
        if not self.is_connected():
            raise ConnectionError("Not connected to OpenClaw Gateway")

        assert self._ws is not None

        request_id = self._next_request_id("chat")
        idempotency_key = str(uuid4())

        frame = build_openclaw_chat_frame(
            request_id=request_id,
            session_key=_SESSION_KEY,
            message=message,
            idempotency_key=idempotency_key,
        )

        await self._ws.send(json.dumps(frame))
        return await self._wait_for_chat_text(request_id)

    async def _do_chat_about_image(
        self,
        message: str,
        *,
        image_base64: str,
        context: str,
    ) -> str:
        if not self.is_connected():
            raise ConnectionError("Not connected to OpenClaw Gateway")
        if not image_base64.strip():
            raise ValueError("image_base64 is required for image follow-up chat")

        assert self._ws is not None

        request_id = self._next_request_id("chat")
        idempotency_key = str(uuid4())
        prompt = _build_image_followup_prompt(message=message, context=context)

        frame = build_openclaw_chat_frame(
            request_id=request_id,
            session_key=_SESSION_KEY,
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
                raw = await asyncio.wait_for(self._ws.recv(), timeout=self._timeout)
            except TimeoutError:
                raise TimeoutError(f"Chat timeout after {self._timeout}s") from None
            except websockets.ConnectionClosed as exc:
                self._connected = False
                raise ConnectionError(f"Gateway connection closed: {exc}") from exc

            frame = json.loads(raw)
            frame_type = frame.get("type")

            if frame_type == "res" and frame.get("id") == request_id:
                if not frame.get("ok"):
                    error = frame.get("error", {})
                    raise RuntimeError(
                        f"OpenClaw error: {error.get('code')} - {error.get('message')}"
                    )
                payload = frame.get("payload", {})
                if payload.get("runId"):
                    run_id = payload["runId"]
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
                if not frame.get("ok"):
                    error = frame.get("error", {})
                    raise RuntimeError(
                        f"OpenClaw error: {error.get('code')} - {error.get('message')}"
                    )

                payload = frame.get("payload", {})
                status = payload.get("status")
                if payload.get("runId"):
                    run_id = payload["runId"]
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

                state = payload.get("state")
                if state == "error":
                    raise RuntimeError(
                        payload.get("errorMessage", "OpenClaw chat event error")
                    )
                if state == "final":
                    return _payload_from_chat_event(payload)

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
        for f in payload.get("findings", []):
            # The LLM occasionally emits a bare string/number for a finding
            # instead of an object; skip anything we cannot treat as a dict.
            if not isinstance(f, dict):
                logger.warning("Dropping non-object finding: %r", f)
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
                    bboxes.append(
                        RegionRect(
                            x=float(x),
                            y=float(y),
                            w=float(w),
                            h=float(h),
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
            findings.append(
                Finding(
                    id=f.get("id", ""),
                    regions=f.get("regions", []),
                    label=f.get("label", ""),
                    detail=f.get("detail", ""),
                    severity=_parse_severity(f.get("severity", "info")),
                    bboxes=bboxes,
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

        return AnalysisResult(
            modality=modality,
            summary=payload.get("summary", ""),
            severity=_parse_severity(payload.get("severity", "info")),
            findings=findings,
            checklist=checklist,
            analysis_time_ms=payload.get("analysis_time_ms", elapsed_ms),
            model_used=payload.get("model_used", ""),
        )


def _parse_severity(s: str) -> Severity:
    try:
        return Severity(s.lower())
    except ValueError:
        return Severity.INFO


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
) -> str:
    skill_prompt = _load_skill_prompt(skill_name)
    return build_initial_analysis_prompt(
        modality=modality,
        valid_regions=valid_regions,
        skill_name=skill_name,
        skill_prompt=skill_prompt,
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


def _load_skill_prompt(skill_name: str) -> str:
    for base in _SKILL_BASE_DIRS:
        path = Path(base) / skill_name / "SKILL.md"
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


def _load_gateway_token() -> str | None:
    env_token = os.getenv("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if env_token:
        return env_token

    dotenv_token = read_env_file(Path(".env")).get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if dotenv_token:
        return dotenv_token

    candidates = [
        Path("openclaw/openclaw.json"),
        Path("openclaw/openclaw.valid.json"),
        Path("openclaw/openclaw.portable.json"),
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
            env_value = os.getenv(env_name, "").strip() or read_env_file(Path(".env")).get(
                env_name, ""
            ).strip()
            if env_value:
                return env_value
        if isinstance(token, str) and token.strip():
            return token.strip()
    return None
