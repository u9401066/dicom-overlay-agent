"""Bounded, opt-in visible-output collection at the public Gateway boundary.

No prompts, auth, arbitrary tools, reasoning streams or wire transcripts are
retained. Exact decoded text bytes are not a signature or an execution journal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from dicom_overlay.infrastructure.strict_json import StrictJSONError, read_json_object

_MAX_TEXT_BYTES = 512 * 1024
_MAX_TOTAL_BYTES = 4 * 1024 * 1024
_MAX_TOOL_RESULTS = 64


@dataclass(frozen=True)
class NativeToolText:
    tool_call_id: str
    tool_name: str
    text_sha256: str
    text_bytes: bytes = field(repr=False)


@dataclass(frozen=True)
class GatewayTurnEvidence:
    request_id: str
    session_key: str = field(repr=False)
    run_id: str
    terminal_seen: bool
    failure: str
    model_text_sha256: str
    model_text_bytes: bytes | None = field(repr=False)
    native_tools: tuple[NativeToolText, ...]
    tool_event_seen: bool = False

    def require_model_text(self) -> bytes:
        if self.failure or not self.terminal_seen or self.model_text_bytes is None:
            raise ValueError(self.failure or "gateway_model_text_unavailable")
        return self.model_text_bytes

    def require_native_tool_text(self, tool_call_id: str) -> NativeToolText:
        if self.failure or not self.terminal_seen:
            raise ValueError(self.failure or "gateway_turn_not_terminal")
        for receipt in self.native_tools:
            if receipt.tool_call_id == tool_call_id:
                return receipt
        raise ValueError("gateway_native_tool_text_missing")


@dataclass(frozen=True)
class ImageEvidenceTurn:
    """Host image/request binding plus the original visible Gateway outputs.

    This is a transport receipt, not a scientific draft or a model usage receipt.
    Neither source hash nor prompt hash establishes clinical correctness.
    """

    image_sha256: str
    prompt_sha256: str
    bbox_evidence_nonce: str
    elapsed_ms: int
    gateway: GatewayTurnEvidence


class GatewayEvidenceCollector:
    """One immutable send identity, including reconnects of the same paid turn.

    A native result is only a candidate for source_evidence binding. Public tool
    events may be sanitized/truncated; the independent audit's exact text hash
    must still agree. Missing results are never reconstructed from final prose.
    """

    def __init__(self, request_id: str, session_key: str) -> None:
        self._request_id = request_id
        self._session_key = session_key
        self._run_id = ""
        self._terminal = False
        self._failure = ""
        self._model: bytes | None = None
        self._tools: dict[str, NativeToolText] = {}
        self._tool_event_seen = False
        self._bytes = 0

    def snapshot(self) -> GatewayTurnEvidence:
        return GatewayTurnEvidence(
            self._request_id,
            self._session_key,
            self._run_id,
            self._terminal,
            self._failure,
            sha256(self._model).hexdigest() if self._model is not None else "",
            self._model,
            tuple(self._tools.values()),
            self._tool_event_seen,
        )

    def _fail(self, category: str) -> None:
        if not self._failure:
            self._failure = category

    def _text(self, message: object) -> bytes | None:
        # A single explicit visible-text block preserves exact body identity.
        # Do not join blocks, strip fences/whitespace, repair JSON, serialize a
        # model object, or retain accompanying reasoning blocks.
        if not isinstance(message, dict):
            return None
        content = message.get("content")
        if not isinstance(content, list):
            return None
        blocks = [
            block
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if len(blocks) != 1 or not isinstance(blocks[0].get("text"), str):
            return None
        raw = blocks[0]["text"].encode("utf-8")
        return raw if 0 < len(raw) <= _MAX_TEXT_BYTES else None

    def _reserve(self, count: int) -> bool:
        if self._bytes + count > _MAX_TOTAL_BYTES:
            self._fail("gateway_evidence_size_limit")
            return False
        self._bytes += count
        return True

    def observe(self, raw: str) -> None:
        if self._terminal:
            return
        try:
            frame = read_json_object(raw.encode("utf-8"))
        except (StrictJSONError, UnicodeError):
            self._fail("gateway_evidence_frame_invalid")
            return
        if (
            frame.get("type") == "res"
            and frame.get("id") == self._request_id
            and frame.get("ok") is not True
        ):
            self._fail("gateway_request_failed")
            return
        payload = frame.get("payload")
        if not isinstance(payload, dict):
            return
        if frame.get("type") == "res" and frame.get("id") == self._request_id:
            if frame.get("ok") is not True or payload.get("status") == "error":
                self._fail("gateway_request_failed")
                return
            if "sessionKey" in payload and payload["sessionKey"] != self._session_key:
                self._fail("gateway_session_identity_changed")
                return
            run_id = payload.get("runId")
            if "runId" in payload and (
                not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 256
            ):
                self._fail("gateway_run_identity_invalid")
                return
            if isinstance(run_id, str) and run_id:
                if self._run_id and run_id != self._run_id:
                    self._fail("gateway_run_identity_changed")
                    return
                self._run_id = run_id
            if payload.get("status") == "accepted":
                return
            if "result" in payload:
                # Dict results have no original JSON text body to recover.
                result = payload["result"]
                model = None
                if isinstance(result, dict) and isinstance(result.get("text"), str):
                    model = self._text(
                        {"content": [{"type": "text", "text": result["text"]}]}
                    )
                self._finish(model)
            return
        if frame.get("type") != "event" or not self._run_id:
            return
        if payload.get("runId") != self._run_id:
            return
        if "sessionKey" in payload and payload["sessionKey"] != self._session_key:
            self._fail("gateway_session_identity_changed")
            return
        if frame.get("event") == "chat":
            state = payload.get("state")
            if state in {"error", "aborted"}:
                self._fail("gateway_run_failed")
            elif state == "final":
                message = payload.get("message")
                if (
                    isinstance(message, dict)
                    and message.get("role", "assistant") != "assistant"
                ):
                    self._fail("gateway_final_role_invalid")
                    return
                self._finish(self._text(message))
        elif frame.get("event") == "agent" and payload.get("stream") == "tool":
            # A stage can fail closed on any observed tool event without keeping
            # arbitrary tool names, arguments or outputs in its evidence receipt.
            self._tool_event_seen = True
            self._tool(payload.get("data"))

    def _finish(self, model: bytes | None) -> None:
        self._terminal = True
        if not self._run_id:
            self._fail("gateway_run_identity_missing")
        elif model is None:
            self._fail("gateway_original_model_text_missing")
        elif self._reserve(len(model)):
            self._model = model

    def _tool(self, data: Any) -> None:
        if self._failure:
            return
        if not isinstance(data, dict) or data.get("phase") != "result":
            return
        if data.get("name") != "dicom_bbox_validate":
            return
        call_id = data.get("toolCallId")
        if not isinstance(call_id, str) or not call_id.strip() or len(call_id) > 256:
            self._fail("gateway_native_call_identity_missing")
            return
        result = data.get("result")
        if data.get("isError") is True or (
            isinstance(result, dict) and result.get("isError") is True
        ):
            self._fail("gateway_native_tool_failed")
            return
        raw = self._text(result)
        if raw is None:
            self._fail("gateway_original_tool_text_missing")
            return
        receipt = NativeToolText(
            call_id, "dicom_bbox_validate", sha256(raw).hexdigest(), raw
        )
        previous = self._tools.get(call_id)
        if previous is not None:
            if previous != receipt:
                self._fail("gateway_native_result_conflict")
            return
        if len(self._tools) >= _MAX_TOOL_RESULTS:
            self._fail("gateway_native_result_count_limit")
            return
        if self._reserve(len(raw)):
            self._tools[call_id] = receipt
