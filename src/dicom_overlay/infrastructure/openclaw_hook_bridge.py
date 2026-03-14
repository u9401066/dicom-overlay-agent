"""OpenClaw Hook Bridge -- Python-side subscriber for gateway hook events.

Maps OpenClaw's Node.js `triggerInternalHook(event)` to Python handlers
via the existing WebSocket connection. Also emits client-side analyze
events back to the gateway so workspace hooks can observe them.

Aligned with: openclaw/src/hooks/internal-hooks.ts
Event format: type:action (e.g., "message:received", "analyze:pre")
"""

from __future__ import annotations

from typing import Any

import structlog

from dicom_overlay.domain.hooks import (
    GatewayHookHandler,
    HookEvent,
    HookEventType,
)

logger = structlog.get_logger(__name__)


class OpenClawHookBridge:
    """Registry for gateway hook event handlers (Python side).

    Mirrors OpenClaw's registerInternalHook / triggerInternalHook pattern:
      - register(event_key, handler)   -> listen for "type:action"
      - trigger(event)                 -> fire all matching handlers
      - emit_to_gateway(event)         -> send event back to gateway via WS

    Event keys:
      - "analyze"           -> all analyze events
      - "analyze:pre"       -> before analyze
      - "analyze:post"      -> after analyze
      - "analyze:error"     -> analyze failure
      - "message:received"  -> forwarded from gateway
      - "gateway:startup"   -> gateway started
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[GatewayHookHandler]] = {}
        self._ws_send: Any = None  # Will be set to ws.send for emit_to_gateway

    def set_ws_sender(self, send_fn: Any) -> None:
        """Set the WebSocket send function for emitting events to gateway."""
        self._ws_send = send_fn

    def register(self, event_key: str, handler: GatewayHookHandler) -> None:
        if event_key not in self._handlers:
            self._handlers[event_key] = []
        self._handlers[event_key].append(handler)
        logger.info(
            "Hook handler registered",
            event_key=event_key,
            handler=handler.name,
        )

    def unregister(self, event_key: str, handler: GatewayHookHandler) -> None:
        handlers = self._handlers.get(event_key)
        if handlers and handler in handlers:
            handlers.remove(handler)
            if not handlers:
                del self._handlers[event_key]

    async def trigger(self, event: HookEvent) -> None:
        """Trigger all handlers for an event (type handlers + type:action handlers)."""
        type_key = event.type.value
        action_key = f"{type_key}:{event.action}"

        all_handlers = [
            *self._handlers.get(type_key, []),
            *self._handlers.get(action_key, []),
        ]

        if not all_handlers:
            return

        for handler in all_handlers:
            try:
                await handler.handle(event)
            except Exception:
                logger.exception(
                    "Hook handler error",
                    handler=handler.name,
                    event=action_key,
                )

    def create_event(
        self,
        event_type: HookEventType,
        action: str,
        context: dict[str, Any] | None = None,
        session_key: str = "main",
    ) -> HookEvent:
        """Create a HookEvent (mirrors OpenClaw's createInternalHookEvent)."""
        return HookEvent(
            type=event_type,
            action=action,
            session_key=session_key,
            context=context or {},
        )

    @property
    def registered_event_keys(self) -> list[str]:
        return list(self._handlers.keys())

    def parse_gateway_event(self, payload: dict[str, Any]) -> HookEvent | None:
        """Parse a gateway WebSocket event frame into a HookEvent.

        Expected frame format from gateway:
          {"type": "event", "payload": {"hookType": "message", "hookAction": "received", ...}}
        """
        hook_type_str = payload.get("hookType", "")
        hook_action = payload.get("hookAction", "")
        if not hook_type_str or not hook_action:
            return None

        try:
            hook_type = HookEventType(hook_type_str)
        except ValueError:
            logger.debug("Unknown hook event type: %s", hook_type_str)
            return None

        return HookEvent(
            type=hook_type,
            action=hook_action,
            session_key=payload.get("sessionKey", "main"),
            context=payload.get("context", {}),
            messages=payload.get("messages", []),
        )
