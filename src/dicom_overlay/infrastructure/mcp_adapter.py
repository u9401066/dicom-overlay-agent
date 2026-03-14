"""MCP Adapter — Python-side pool for MCP server connections.

Mirrors OpenClaw's openclaw-mcp-adapter plugin pattern:
  - McpClientPool manages connections to multiple MCP servers
  - Each server is discovered (listTools) then callable (callTool)
  - Auto-reconnect on connection failure
  - Tool names optionally prefixed with server name

Reference: https://github.com/androidStern-personal/openclaw-mcp-adapter

Two modes of operation:
  1. **Gateway-proxied**: Tools already registered by the mcp-adapter plugin
     in the OpenClaw gateway. Our client invokes them via WebSocket.
  2. **Direct**: For Python-native MCP servers running locally alongside
     the overlay agent (e.g., DICOM tools, anonymization).

Usage:
    config = MCPAdapterConfig(
        servers=[
            MCPServerConfig(name="pubmed", transport="stdio",
                            command="uvx", args=["pubmed-search-mcp"]),
        ],
        tool_prefix=True,
    )
    adapter = McpAdapter(config)
    await adapter.start()

    tools = adapter.all_tools()
    result = await adapter.call_tool("pubmed_search", {"query": "airway"})

    await adapter.stop()
"""

from __future__ import annotations

from typing import Any

import structlog

from dicom_overlay.domain.hooks import (
    MCPAdapterConfig,
    MCPServerConfig,
    MCPToolProvider,
    ToolCallResult,
    ToolDefinition,
)

logger = structlog.get_logger(__name__)


class McpAdapter:
    """Pool and router for MCP server connections.

    Mirrors openclaw-mcp-adapter's lifecycle:
      - start(): connect to all configured servers, discover tools
      - stop(): close all connections
      - call_tool(): route to correct server, auto-reconnect on failure

    Aligned with OpenClaw's api.registerService({ id, start(), stop() })
    pattern from the mcp-adapter plugin.
    """

    def __init__(self, config: MCPAdapterConfig | None = None) -> None:
        self._config = config or MCPAdapterConfig()
        self._providers: dict[str, MCPToolProvider] = {}
        self._tool_index: dict[str, tuple[str, str]] = {}  # prefixed_name → (server, original_name)

    @property
    def config(self) -> MCPAdapterConfig:
        return self._config

    # ── Lifecycle (mirrors api.registerService start/stop) ───────────

    async def start(self) -> None:
        """Connect to all configured MCP servers and discover tools.

        Mirrors openclaw-mcp-adapter's start() method:
          for each server → connect → listTools → registerTool
        """
        if not self._config.servers:
            logger.info("[mcp-adapter] No servers configured")
            return

        for server_config in self._config.servers:
            await self._connect_server(server_config)

    async def stop(self) -> None:
        """Close all MCP server connections.

        Mirrors openclaw-mcp-adapter's stop() method.
        """
        logger.info("[mcp-adapter] Shutting down...")
        for name in list(self._providers.keys()):
            await self._close_server(name)
        self._tool_index.clear()
        logger.info("[mcp-adapter] All connections closed")

    # ── Server management ────────────────────────────────────────────

    async def _connect_server(self, config: MCPServerConfig) -> None:
        """Connect to a single MCP server and register its tools."""
        try:
            provider = await self._create_provider(config)
            await provider.connect()
            self._providers[config.name] = provider

            tools = await provider.list_tools()
            logger.info(
                "[mcp-adapter] %s: found %d tools",
                config.name,
                len(tools),
            )

            for tool in tools:
                prefixed = (
                    f"{config.name}_{tool.name}"
                    if self._config.tool_prefix
                    else tool.name
                )
                self._tool_index[prefixed] = (config.name, tool.name)
                logger.debug("[mcp-adapter] Registered: %s", prefixed)

        except Exception:
            logger.exception(
                "[mcp-adapter] Failed to connect to %s", config.name
            )

    async def _close_server(self, server_name: str) -> None:
        provider = self._providers.pop(server_name, None)
        if provider is None:
            return
        try:
            await provider.close()
        except Exception:
            logger.exception(
                "[mcp-adapter] Error closing %s", server_name
            )
        # Remove tool index entries for this server
        self._tool_index = {
            k: v for k, v in self._tool_index.items() if v[0] != server_name
        }

    # ── Tool discovery ───────────────────────────────────────────────

    def all_tools(self) -> list[ToolDefinition]:
        """List all tools from all connected servers (with optional prefix)."""
        result = []
        for prefixed_name, (server_name, original_name) in self._tool_index.items():
            provider = self._providers.get(server_name)
            if provider is None:
                continue
            # Return the prefixed name in the definition
            result.append(
                ToolDefinition(
                    name=prefixed_name,
                    description=f"[{server_name}] {original_name}",
                    parameters={},
                )
            )
        return result

    def tools_by_server(self, server_name: str) -> list[ToolDefinition]:
        """List tools from a specific server."""
        provider = self._providers.get(server_name)
        if provider is None:
            return []
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't await in sync context — return cached
                return [
                    ToolDefinition(name=k, description=f"[{server_name}]")
                    for k, (sn, _) in self._tool_index.items()
                    if sn == server_name
                ]
            return loop.run_until_complete(provider.list_tools())
        except Exception:
            return []

    def get_status(self) -> dict[str, bool]:
        """Connection status for each server."""
        return {
            name: provider.connected
            for name, provider in self._providers.items()
        }

    # ── Tool invocation ──────────────────────────────────────────────

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolCallResult:
        """Call a tool by its (prefixed) name.

        Mirrors openclaw-mcp-adapter's execute() pattern:
          - Resolve tool name to server + original name
          - Call the tool on the correct server
          - Auto-reconnect on connection failure
        """
        lookup = self._tool_index.get(tool_name)
        if lookup is None:
            return ToolCallResult(
                content=[{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                is_error=True,
            )

        server_name, original_name = lookup
        provider = self._providers.get(server_name)
        if provider is None:
            return ToolCallResult(
                content=[{"type": "text", "text": f"Server not connected: {server_name}"}],
                is_error=True,
            )

        try:
            return await provider.call_tool(original_name, arguments or {})
        except Exception as exc:
            if not provider.connected or _is_connection_error(exc):
                logger.warning(
                    "[mcp-adapter] Connection error on %s, reconnecting...",
                    server_name,
                )
                return await self._reconnect_and_retry(
                    server_name, original_name, arguments or {}
                )
            logger.exception(
                "[mcp-adapter] Tool call failed: %s/%s",
                server_name,
                original_name,
            )
            return ToolCallResult(
                content=[{"type": "text", "text": str(exc)}],
                is_error=True,
            )

    async def _reconnect_and_retry(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolCallResult:
        """Reconnect to server and retry the tool call (one attempt)."""
        # Find the original config
        config = next(
            (s for s in self._config.servers if s.name == server_name), None
        )
        if config is None:
            return ToolCallResult(
                content=[{"type": "text", "text": f"No config for server: {server_name}"}],
                is_error=True,
            )

        await self._close_server(server_name)
        await self._connect_server(config)

        provider = self._providers.get(server_name)
        if provider is None:
            return ToolCallResult(
                content=[{"type": "text", "text": f"Reconnect failed: {server_name}"}],
                is_error=True,
            )

        try:
            return await provider.call_tool(tool_name, arguments)
        except Exception as exc:
            return ToolCallResult(
                content=[{"type": "text", "text": f"Retry failed: {exc}"}],
                is_error=True,
            )

    # ── Provider registration (manual / external) ────────────────────

    def register_provider(self, provider: MCPToolProvider) -> None:
        """Register a pre-built MCPToolProvider (for external agents).

        Unlike config-driven servers, this accepts an already-constructed
        provider instance (e.g., from Claude Cowork, OpenWork).
        """
        name = provider.server_name
        if name in self._providers:
            logger.warning(
                "[mcp-adapter] Provider '%s' already registered, replacing",
                name,
            )
        self._providers[name] = provider
        logger.info("[mcp-adapter] External provider registered: %s", name)

    def unregister_provider(self, server_name: str) -> None:
        """Remove a provider without closing its connection."""
        if server_name in self._providers:
            del self._providers[server_name]
            self._tool_index = {
                k: v for k, v in self._tool_index.items()
                if v[0] != server_name
            }
            logger.info("[mcp-adapter] Provider unregistered: %s", server_name)

    # ── Provider factory ─────────────────────────────────────────────

    async def _create_provider(
        self, config: MCPServerConfig
    ) -> MCPToolProvider:
        """Create an MCPToolProvider for the given config.

        Currently creates a GatewayProxiedProvider that routes calls
        through the OpenClaw gateway. When direct MCP SDK support is
        added, this will branch based on config.transport.
        """
        return _StubProvider(config)


class _StubProvider(MCPToolProvider):
    """Placeholder provider until real MCP SDK integration is wired.

    This allows the adapter to be tested and used with manual
    register_provider() calls before the full MCP protocol client
    is implemented.
    """

    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self._connected = False

    @property
    def server_name(self) -> str:
        return self._config.name

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        logger.info(
            "[mcp-stub] Would connect to %s (%s)",
            self._config.name,
            self._config.transport,
        )
        self._connected = True

    async def list_tools(self) -> list[ToolDefinition]:
        return []

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> ToolCallResult:
        return ToolCallResult(
            content=[{
                "type": "text",
                "text": f"Stub: {self._config.name}/{name} not yet implemented",
            }],
            is_error=True,
        )

    async def close(self) -> None:
        self._connected = False


def _is_connection_error(err: Exception) -> bool:
    """Check if an error indicates a broken connection.

    Mirrors openclaw-mcp-adapter's isConnectionError() logic.
    """
    msg = str(err).lower()
    return any(s in msg for s in ("closed", "econnrefused", "epipe", "broken"))
