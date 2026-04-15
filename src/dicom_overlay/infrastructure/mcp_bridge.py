"""MCP Bridge -- registry for external MCP tool providers.

Provides a standardized interface for external agents (Claude Cowork,
OpenWork, etc.) to register their MCP servers. Tools from all registered
providers are discoverable and callable through a unified API.

Usage:
    bridge = MCPBridge()
    bridge.register(my_claude_provider)
    bridge.register(my_openwork_provider)

    tools = bridge.list_all_tools()
    result = await bridge.call_tool("provider-name", "tool-name", {"arg": "val"})
"""

from __future__ import annotations

import asyncio

import structlog

from dicom_overlay.domain.hooks import MCPToolProvider, ToolCallResult, ToolDefinition

logger = structlog.get_logger(__name__)


class MCPBridge:
    """Registry and router for external MCP tool providers."""

    def __init__(self) -> None:
        self._providers: dict[str, MCPToolProvider] = {}

    def register(self, provider: MCPToolProvider) -> None:
        name = provider.server_name
        if name in self._providers:
            logger.warning("MCP provider '%s' already registered, replacing", name)
        self._providers[name] = provider
        logger.info("MCP provider registered", provider=name)

    def unregister(self, provider_name: str) -> None:
        if provider_name in self._providers:
            del self._providers[provider_name]
            logger.info("MCP provider unregistered: %s", provider_name)

    @property
    def providers(self) -> dict[str, MCPToolProvider]:
        return dict(self._providers)

    def list_all_tools(self) -> dict[str, list[ToolDefinition]]:
        """List all tools grouped by provider name."""
        has_running_loop = False
        try:
            asyncio.get_running_loop()
            has_running_loop = True
        except RuntimeError:
            pass

        if has_running_loop:
            msg = "list_all_tools() cannot be called from a running event loop"
            raise RuntimeError(msg)

        loop = asyncio.new_event_loop()
        try:
            return {
                name: loop.run_until_complete(provider.list_tools())
                for name, provider in self._providers.items()
            }
        finally:
            loop.close()

    async def call_tool(
        self,
        provider_name: str,
        tool_name: str,
        arguments: dict,
    ) -> ToolCallResult:
        provider = self._providers.get(provider_name)
        if provider is None:
            return ToolCallResult(
                content=[
                    {
                        "type": "text",
                        "text": f"Unknown MCP provider: {provider_name}",
                    }
                ],
                is_error=True,
            )

        try:
            return await provider.call_tool(tool_name, arguments)
        except Exception as exc:
            logger.exception(
                "MCP tool call failed",
                provider=provider_name,
                tool=tool_name,
            )
            return ToolCallResult(
                content=[{"type": "text", "text": str(exc)}],
                is_error=True,
            )

    async def connect_all(self) -> None:
        for name, provider in self._providers.items():
            try:
                await provider.connect()
                logger.info("MCP provider connected: %s", name)
            except Exception:
                logger.exception("MCP provider connect failed: %s", name)

    async def disconnect_all(self) -> None:
        for name, provider in self._providers.items():
            try:
                await provider.close()
            except Exception:
                logger.exception("MCP provider disconnect failed: %s", name)
