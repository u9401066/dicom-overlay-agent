"""OpenClaw Gateway WebSocket client (spec §3.3, §3.6)."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import time
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog
import websockets

from dicom_overlay.domain.entities import (
    AnalysisResult,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.domain.services import VisionAnalyzerService

logger = structlog.get_logger(__name__)

_OPENCLAW_VERSION = "2026.3.11"
_SESSION_KEY = "main"
_DEFAULT_SCOPES = [
    "operator.admin",
    "operator.read",
    "operator.write",
    "operator.approvals",
    "operator.pairing",
]

# Skill mapping: modality → OpenClaw workspace skill name
_SKILL_MAP: dict[str, str] = {
    "EKG": "dicom-ekg-analysis",
    "CXR": "dicom-cxr-analysis",
    "CT_BRAIN": "dicom-ct-brain-analysis",
}

_SKILL_PATHS: dict[str, tuple[Path, Path]] = {
    "EKG": (
        Path("openclaw/workspace/skills/dicom-ekg-analysis/SKILL.md"),
        Path("openclaw-home/.openclaw/workspace/skills/dicom-ekg-analysis/SKILL.md"),
    ),
    "CXR": (
        Path("openclaw/workspace/skills/dicom-cxr-analysis/SKILL.md"),
        Path("openclaw-home/.openclaw/workspace/skills/dicom-cxr-analysis/SKILL.md"),
    ),
    "CT_BRAIN": (
        Path("openclaw/workspace/skills/dicom-ct-brain-analysis/SKILL.md"),
        Path("openclaw-home/.openclaw/workspace/skills/dicom-ct-brain-analysis/SKILL.md"),
    ),
}


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
    ) -> None:
        self._url = gateway_url
        self._timeout = timeout_sec
        self._reconnect_interval = reconnect_interval_sec
        self._ws: Any = None
        self._connected = False
        self._request_counter = 0
        self._gateway_token = (
            gateway_token.strip()
            if isinstance(gateway_token, str) and gateway_token.strip()
            else _load_gateway_token()
        )
        if not self._gateway_token:
            logger.warning(
                "No OpenClaw gateway token configured; connect() will proceed without auth"
            )
        self._ws_lock = asyncio.Lock()  # Serialize all WebSocket send+recv sequences

    async def connect(self) -> None:
        try:
            self._ws = await websockets.connect(
                self._url,
                ping_interval=30,
                ping_timeout=60,
            )
            await self._handshake()
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
            except (websockets.ConnectionClosed, websockets.exceptions.ConcurrencyError):
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
                    raise ConnectionError(
                        f"Reconnect failed: {exc}"
                    ) from None

    async def _do_analyze(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        if not self.is_connected():
            raise ConnectionError("Not connected to OpenClaw Gateway")

        assert self._ws is not None

        skill = _SKILL_MAP.get(modality.value, "dicom-ekg-analysis")
        prompt = _build_analysis_prompt(modality, valid_regions, skill)
        request_id = self._next_request_id("chat")
        idempotency_key = str(uuid4())

        message = {
            "type": "req",
            "id": request_id,
            "method": "chat.send",
            "params": {
                "sessionKey": _SESSION_KEY,
                "message": prompt,
                "attachments": [
                    {
                        "type": "image",
                        "mimeType": "image/png",
                        "content": image_base64,
                    }
                ],
                "idempotencyKey": idempotency_key,
            },
        }

        start = time.monotonic()
        payload_json = json.dumps(message)
        logger.info(
            "Sending analysis request: id=%s skill=%s payload_size=%dKB",
            request_id, skill, len(payload_json) // 1024,
        )
        await self._ws.send(payload_json)

        response = await self._wait_for_chat_result(request_id)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return self._parse_result(response, elapsed_ms)

    async def chat(self, message: str) -> str:
        """Send a free-text question with auto-reconnect on connection loss."""
        async with self._ws_lock:
            try:
                return await self._do_chat(message)
            except (websockets.ConnectionClosed, websockets.exceptions.ConcurrencyError):
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
                    raise ConnectionError(
                        f"Reconnect failed: {exc}"
                    ) from None

    async def _do_chat(self, message: str) -> str:
        if not self.is_connected():
            raise ConnectionError("Not connected to OpenClaw Gateway")

        assert self._ws is not None

        request_id = self._next_request_id("chat")
        idempotency_key = str(uuid4())

        frame = {
            "type": "req",
            "id": request_id,
            "method": "chat.send",
            "params": {
                "sessionKey": _SESSION_KEY,
                "message": message,
                "idempotencyKey": idempotency_key,
            },
        }

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

        connect_id = self._next_request_id("connect")
        params: dict[str, Any] = {
            "minProtocol": 3,
            "maxProtocol": 3,
            "client": {
                "id": "cli",
                "version": _OPENCLAW_VERSION,
                "platform": platform.platform(),
                "mode": "cli",
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
                raw = await asyncio.wait_for(self._ws.recv(), timeout=self._timeout)
            except TimeoutError:
                logger.error(
                    "OpenClaw analysis timed out after %ds (request_id=%s, run_id=%s)",
                    self._timeout, request_id, run_id,
                )
                raise TimeoutError(f"Analysis timeout after {self._timeout}s") from None
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
                    raise RuntimeError(payload.get("summary", "OpenClaw request failed"))

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
                    raise RuntimeError(payload.get("errorMessage", "OpenClaw chat event error"))
                if state == "final":
                    return _payload_from_chat_event(payload)

    def _next_request_id(self, prefix: str) -> str:
        self._request_counter += 1
        return f"{prefix}-{self._request_counter}"

    def _parse_result(
        self, response: dict[str, Any], elapsed_ms: int
    ) -> AnalysisResult:
        payload = response.get("payload", response)

        findings = []
        for f in payload.get("findings", []):
            # Parse AI-provided bounding boxes (normalized 0-1 coords)
            bboxes: list[RegionRect] = []
            for b in f.get("bboxes", []):
                try:
                    bboxes.append(RegionRect(
                        x=float(b.get("x", 0)),
                        y=float(b.get("y", 0)),
                        w=float(b.get("w", 0)),
                        h=float(b.get("h", 0)),
                    ))
                except (ValueError, TypeError):
                    pass  # skip malformed bbox
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
        for key, val in payload.get("checklist", {}).items():
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

        modality_str = payload.get("modality", "EKG")
        try:
            modality = Modality(modality_str)
        except ValueError:
            modality = Modality.EKG

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


def _build_analysis_prompt(
    modality: Modality,
    valid_regions: list[str],
    skill_name: str,
) -> str:
    skill_prompt = _load_skill_prompt(modality)
    return (
        f"Use the {skill_name} instructions below to analyze the attached image.\n\n"
        f"{skill_prompt}\n\n"
        "Return a single JSON object only. Do not wrap it in markdown.\n"
        f"modality must be '{modality.value}'.\n"
        "For each abnormal finding, include 'bboxes' with normalized 0-1 coordinates "
        "(x, y, w, h) tightly bounding the specific abnormal area in the image."
    )


def _load_skill_prompt(modality: Modality) -> str:
    candidates = _SKILL_PATHS.get(modality.value, _SKILL_PATHS["EKG"])
    for path in candidates:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            return _strip_frontmatter(raw).strip()
    raise FileNotFoundError(f"Skill prompt not found for modality: {modality.value}")


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
    try:
        data = json.loads(text)
    except JSONDecodeError as exc:
        raise RuntimeError(text) from exc
    return _coerce_result_payload(data)


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
        if isinstance(token, str) and token.strip():
            return token.strip()
    return None
