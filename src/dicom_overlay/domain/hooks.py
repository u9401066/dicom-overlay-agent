"""Domain hook interfaces for operation guardrails.

Defines the contracts for:
1. AnalyzeHook — pre/post middleware around vision analyze calls
2. OpenClaw gateway hook events — aligned with OpenClaw's type:action system
3. MCP adapter — aligned with openclaw-mcp-adapter plugin pattern

Domain layer — no external dependencies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import AnalysisResult, Modality


class HookError(Exception):
    """Raised when a hook rejects an operation."""


# ── OpenClaw Gateway Hook Events (aligned with src/hooks/internal-hooks.ts) ──


class HookEventType(Enum):
    """Event types matching OpenClaw's InternalHookEventType."""

    COMMAND = "command"
    SESSION = "session"
    AGENT = "agent"
    GATEWAY = "gateway"
    MESSAGE = "message"
    ANALYZE = "analyze"  # Extension: our DICOM-specific event type


@dataclass
class HookEvent:
    """Mirrors OpenClaw's InternalHookEvent for cross-bridge compatibility.

    OpenClaw triggers hooks via `triggerInternalHook(event)` in the
    Node.js gateway. Our Python client can subscribe to these events
    via WebSocket and also emit its own analyze-specific events.
    """

    type: HookEventType
    action: str
    session_key: str = "main"
    context: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)


class GatewayHookHandler(ABC):
    """Handler for OpenClaw gateway hook events.

    Register with OpenClawHookBridge to receive events from the gateway
    (e.g., message:received, gateway:startup) or client-side events
    (e.g., analyze:pre, analyze:post).
    """

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def handle(self, event: HookEvent) -> None:
        """Handle a hook event. Errors are caught and logged."""


# ── Analyze Pipeline Hooks (client-side middleware) ──────────────────


@dataclass
class AnalyzeRequest:
    """Immutable snapshot of an analyze request flowing through the hook pipeline."""

    image_base64: str
    modality: Modality
    valid_regions: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


class AnalyzeHook(ABC):
    """Hook that intercepts analyze operations before/after execution.

    Hooks form a pipeline:
      pre_analyze → actual analyze → post_analyze

    - pre_analyze may modify the request or raise HookError to reject.
    - post_analyze may modify the result or raise HookError to reject.
    """

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def pre_analyze(self, request: AnalyzeRequest) -> AnalyzeRequest:
        """Validate/transform before analyze. Raise HookError to reject."""

    @abstractmethod
    def post_analyze(
        self, request: AnalyzeRequest, result: AnalysisResult
    ) -> AnalysisResult:
        """Validate/transform after analyze. Raise HookError to reject."""


# ── MCP Adapter Interface (aligned with openclaw-mcp-adapter) ────────
#
# Reference: https://github.com/androidStern-personal/openclaw-mcp-adapter
#
# OpenClaw's MCP adapter runs gateway-side as a plugin:
#   - Connects to configured MCP servers (stdio / http)
#   - Discovers tools via listTools()
#   - Registers each as a native gateway tool via api.registerTool()
#   - Proxies tool calls to the MCP server
#
# Our Python-side McpAdapter mirrors this pattern:
#   - Same config schema (ServerConfig, McpAdapterConfig)
#   - Same pool semantics (connect → discover → call → reconnect)
#   - Can also invoke gateway-registered tools via WebSocket
# ─────────────────────────────────────────────────────────────────────


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server.

    Mirrors OpenClaw's ServerConfig in openclaw-mcp-adapter/config.ts:
      - stdio transport: spawns a subprocess (command + args + env)
      - http transport: connects to a running server (url + headers)
    """

    name: str
    transport: str = "stdio"  # "stdio" | "http"
    command: str | None = None  # stdio: command to spawn
    args: list[str] = field(default_factory=list)  # stdio: command arguments
    env: dict[str, str] = field(default_factory=dict)  # stdio: environment variables
    url: str | None = None  # http: server URL
    headers: dict[str, str] = field(default_factory=dict)  # http: request headers


@dataclass
class MCPAdapterConfig:
    """Top-level MCP adapter configuration.

    Mirrors OpenClaw's McpAdapterConfig:
      - servers: list of MCP servers to connect to
      - tool_prefix: whether to prefix tool names with server name
    """

    servers: list[MCPServerConfig] = field(default_factory=list)
    tool_prefix: bool = True


@dataclass(frozen=True)
class ToolDefinition:
    """Schema definition for an MCP tool (matches MCP listTools response)."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCallResult:
    """Result of an MCP tool call (matches MCP callTool response)."""

    content: list[dict[str, Any]] = field(default_factory=list)
    is_error: bool = False

    @property
    def text(self) -> str:
        """Extract concatenated text from content blocks."""
        return "\n".join(
            c.get("text", c.get("data", "")) for c in self.content
        )

    @property
    def success(self) -> bool:
        return not self.is_error


class MCPToolProvider(ABC):
    """Interface for an MCP server client (one per server).

    Maps to openclaw-mcp-adapter's McpClientPool per-entry contract:
      connect() → listTools() → callTool() → close()
    """

    @property
    @abstractmethod
    def server_name(self) -> str:
        """Unique name for this server (used as tool prefix)."""

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the server connection is active."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the MCP server."""

    @abstractmethod
    async def list_tools(self) -> list[ToolDefinition]:
        """Discover available tools from this server."""

    @abstractmethod
    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> ToolCallResult:
        """Call a tool by name with given arguments."""

    @abstractmethod
    async def close(self) -> None:
        """Close connection to the MCP server."""
