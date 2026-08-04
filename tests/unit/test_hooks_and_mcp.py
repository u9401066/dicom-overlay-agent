"""Tests for hooks (InputGuard, OutputValidator, RateLimiter) and MCP adapter."""

from __future__ import annotations

from typing import Any

import pytest

from dicom_overlay.domain.entities import (
    AnalysisResult,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.domain.hooks import (
    AnalyzeRequest,
    HookError,
    MCPAdapterConfig,
    MCPServerConfig,
    MCPToolProvider,
    ToolCallResult,
    ToolDefinition,
)
from dicom_overlay.infrastructure.hooks.input_guard import InputGuard
from dicom_overlay.infrastructure.hooks.output_validator import OutputValidator
from dicom_overlay.infrastructure.hooks.rate_limiter import RateLimiter
from dicom_overlay.infrastructure.mcp_adapter import McpAdapter

# ── Fixtures ─────────────────────────────────────────────────────────


def _make_request(
    image_size: int = 1000,
    modality: Modality = Modality.EKG,
    regions: list[str] | None = None,
) -> AnalyzeRequest:
    return AnalyzeRequest(
        image_base64="A" * image_size,
        modality=modality,
        valid_regions=regions if regions is not None else ["lead_II", "rhythm_strip"],
    )


def _make_result(
    modality: Modality = Modality.EKG,
    summary: str = "Normal sinus rhythm",
) -> AnalysisResult:
    return AnalysisResult(
        modality=modality,
        summary=summary,
        severity=Severity.NORMAL,
        findings=[
            Finding(
                id="f1",
                regions=["lead_II"],
                label="Normal",
                detail="Normal sinus rhythm",
                severity=Severity.NORMAL,
            )
        ],
        checklist={
            "heart_rate": ChecklistItem(value="normal", status=Severity.NORMAL),
            "rhythm": ChecklistItem(value="sinus", status=Severity.NORMAL),
            "regularity": ChecklistItem(value="regular", status=Severity.NORMAL),
            "axis": ChecklistItem(value="normal", status=Severity.NORMAL),
            "p_wave": ChecklistItem(value="normal", status=Severity.NORMAL),
            "pr_interval": ChecklistItem(value="normal", status=Severity.NORMAL),
            "qrs_duration": ChecklistItem(value="narrow", status=Severity.NORMAL),
            "qrs_morphology": ChecklistItem(value="normal", status=Severity.NORMAL),
            "st_segment": ChecklistItem(value="normal", status=Severity.NORMAL),
            "t_wave": ChecklistItem(value="normal", status=Severity.NORMAL),
            "qtc_interval": ChecklistItem(value="normal", status=Severity.NORMAL),
            "chamber_enlargement": ChecklistItem(value="absent", status=Severity.NORMAL),
            "conduction": ChecklistItem(value="normal", status=Severity.NORMAL),
            "av_block": ChecklistItem(value="absent", status=Severity.NORMAL),
            "stemi_pattern": ChecklistItem(value="absent", status=Severity.NORMAL),
            "ischemia": ChecklistItem(value="absent", status=Severity.NORMAL),
        },
        analysis_time_ms=150,
        model_used="test",
    )


# ── InputGuard Tests ─────────────────────────────────────────────────


class TestInputGuard:
    def test_valid_request_passes(self):
        guard = InputGuard()
        req = _make_request()
        result = guard.pre_analyze(req)
        assert result == req

    def test_empty_image_rejected(self):
        guard = InputGuard()
        req = _make_request(image_size=0)
        with pytest.raises(HookError, match="empty"):
            guard.pre_analyze(req)

    def test_oversized_image_rejected(self):
        guard = InputGuard()
        req = _make_request(image_size=20_000_000)
        with pytest.raises(HookError, match="過大"):
            guard.pre_analyze(req)

    def test_undersized_image_rejected(self):
        guard = InputGuard()
        req = _make_request(image_size=50)
        with pytest.raises(HookError, match="太小"):
            guard.pre_analyze(req)

    def test_empty_regions_rejected(self):
        guard = InputGuard()
        req = _make_request(regions=[])
        with pytest.raises(HookError, match="區域"):
            guard.pre_analyze(req)

    def test_post_analyze_passthrough(self):
        guard = InputGuard()
        req = _make_request()
        result = _make_result()
        assert guard.post_analyze(req, result) is result


# ── OutputValidator Tests ────────────────────────────────────────────


class TestOutputValidator:
    def test_valid_result_passes(self):
        validator = OutputValidator()
        req = _make_request()
        result = _make_result()
        validated = validator.post_analyze(req, result)
        assert validated.summary == result.summary

    def test_empty_summary_rejected(self):
        validator = OutputValidator()
        req = _make_request()
        result = _make_result(summary="")
        with pytest.raises(HookError, match="summary"):
            validator.post_analyze(req, result)

    def test_pre_analyze_passthrough(self):
        validator = OutputValidator()
        req = _make_request()
        assert validator.pre_analyze(req) is req

    def test_missing_checklist_keys_warns(self, caplog):
        """Missing EKG checklist keys should generate warnings in non-strict mode."""
        import logging

        validator = OutputValidator(strict=False)
        req = _make_request()
        result = _make_result()
        # Remove some keys to simulate partial AI response
        del result.checklist["ischemia"]
        del result.checklist["stemi_pattern"]
        with caplog.at_level(logging.WARNING):
            validated = validator.post_analyze(req, result)
        # Should still pass (non-strict), but warnings logged
        assert validated.summary == result.summary

    def test_missing_checklist_keys_strict_rejected(self):
        """In strict mode, missing checklist keys should raise HookError."""
        validator = OutputValidator(strict=True)
        req = _make_request()
        result = _make_result()
        del result.checklist["av_block"]
        with pytest.raises(HookError, match="av_block"):
            validator.post_analyze(req, result)

    def test_full_16_key_checklist_passes_strict(self):
        """All 16 required EKG keys present should pass even in strict mode."""
        validator = OutputValidator(strict=True)
        req = _make_request()
        result = _make_result()
        assert len(result.checklist) == 16
        validated = validator.post_analyze(req, result)
        assert validated.summary == result.summary

    def test_low_confidence_finding_with_question_requires_review(self):
        validator = OutputValidator()
        req = _make_request()
        result = _make_result()
        result.findings = [
            Finding(
                id="uncertain-st",
                regions=["lead_II"],
                label="Possible ST-T abnormality",
                detail="The morphology remains unresolved.",
                severity=Severity.WARNING,
                bboxes=[RegionRect(0.1, 0.1, 0.2, 0.2)],
                confidence="low",
                question="Can this be reviewed on the source ECG?",
            )
        ]

        validated = validator.post_analyze(req, result)

        assert validated.review_required is True
        assert validated.review_reasons == [
            "Low-confidence finding requires review: Possible ST-T abnormality"
        ]

    def test_incomplete_result_requires_review(self):
        validator = OutputValidator()
        req = _make_request()
        result = _make_result()
        result.incomplete = True
        result.incomplete_reasons = ["Lead V6 is cropped."]

        validated = validator.post_analyze(req, result)

        assert validated.review_required is True
        assert "Incomplete analysis requires human review" in validated.review_reasons


# ── RateLimiter Tests ────────────────────────────────────────────────


class TestRateLimiter:
    def test_under_limit_passes(self):
        limiter = RateLimiter(max_per_minute=5)
        req = _make_request()
        for _ in range(5):
            limiter.pre_analyze(req)

    def test_over_limit_rejected(self):
        limiter = RateLimiter(max_per_minute=2)
        req = _make_request()
        limiter.pre_analyze(req)
        limiter.pre_analyze(req)
        with pytest.raises(HookError, match=r"[Rr]ate"):
            limiter.pre_analyze(req)


# ── MCP Adapter Tests ────────────────────────────────────────────────


class _FakeProvider(MCPToolProvider):
    """Test MCPToolProvider implementation."""

    def __init__(self, name: str, tools: list[ToolDefinition] | None = None):
        self._name = name
        self._tools = tools or [
            ToolDefinition(name="search", description="Search"),
            ToolDefinition(name="fetch", description="Fetch"),
        ]
        self._connected = False
        self._call_log: list[tuple[str, dict]] = []

    @property
    def server_name(self) -> str:
        return self._name

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def list_tools(self) -> list[ToolDefinition]:
        return self._tools

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> ToolCallResult:
        self._call_log.append((name, arguments))
        return ToolCallResult(
            content=[{"type": "text", "text": f"result from {name}"}],
            is_error=False,
        )

    async def close(self) -> None:
        self._connected = False


class TestMcpAdapter:
    @pytest.mark.asyncio
    async def test_empty_config_starts_ok(self):
        adapter = McpAdapter()
        await adapter.start()
        assert adapter.all_tools() == []
        assert adapter.get_status() == {}
        await adapter.stop()

    def test_register_provider(self):
        adapter = McpAdapter()
        provider = _FakeProvider("pubmed")
        adapter.register_provider(provider)
        assert "pubmed" in adapter.get_status()

    @pytest.mark.asyncio
    async def test_register_and_discover_tools(self):
        adapter = McpAdapter()
        provider = _FakeProvider("pubmed")
        adapter.register_provider(provider)

        await provider.connect()
        tools = await provider.list_tools()
        # Manually index tools (register_provider doesn't auto-discover)
        for tool in tools:
            adapter._tool_index[f"pubmed_{tool.name}"] = (
                "pubmed",
                tool.name,
            )

        all_tools = adapter.all_tools()
        assert len(all_tools) == 2
        names = [t.name for t in all_tools]
        assert "pubmed_search" in names
        assert "pubmed_fetch" in names

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        adapter = McpAdapter()
        provider = _FakeProvider("pubmed")
        adapter.register_provider(provider)
        await provider.connect()

        # Index tools
        adapter._tool_index["pubmed_search"] = ("pubmed", "search")

        result = await adapter.call_tool(
            "pubmed_search", {"query": "airway"}
        )
        assert result.success
        assert "result from search" in result.text
        assert provider._call_log == [("search", {"query": "airway"})]

    @pytest.mark.asyncio
    async def test_call_unknown_tool(self):
        adapter = McpAdapter()
        result = await adapter.call_tool("nonexistent", {})
        assert result.is_error
        assert "Unknown tool" in result.text

    @pytest.mark.asyncio
    async def test_call_disconnected_server(self):
        adapter = McpAdapter()
        # Register but remove provider to simulate gone server
        adapter._tool_index["gone_tool"] = ("gone_server", "tool")
        result = await adapter.call_tool("gone_tool", {})
        assert result.is_error
        assert "not connected" in result.text.lower()

    def test_unregister_provider(self):
        adapter = McpAdapter()
        provider = _FakeProvider("pubmed")
        adapter.register_provider(provider)
        adapter._tool_index["pubmed_search"] = ("pubmed", "search")

        adapter.unregister_provider("pubmed")
        assert "pubmed" not in adapter.get_status()
        assert adapter.all_tools() == []

    @pytest.mark.asyncio
    async def test_stop_closes_all(self):
        adapter = McpAdapter()
        p1 = _FakeProvider("server1")
        p2 = _FakeProvider("server2")
        adapter.register_provider(p1)
        adapter.register_provider(p2)
        await p1.connect()
        await p2.connect()

        await adapter.stop()
        assert not p1.connected
        assert not p2.connected
        assert adapter.get_status() == {}


# ── MCPServerConfig Tests ────────────────────────────────────────────


class TestMCPServerConfig:
    def test_stdio_config(self):
        config = MCPServerConfig(
            name="pubmed",
            transport="stdio",
            command="uvx",
            args=["pubmed-search-mcp"],
            env={"API_KEY": "test"},
        )
        assert config.name == "pubmed"
        assert config.transport == "stdio"
        assert config.command == "uvx"

    def test_http_config(self):
        config = MCPServerConfig(
            name="api",
            transport="http",
            url="http://localhost:3000/mcp",
            headers={"Authorization": "Bearer token"},
        )
        assert config.name == "api"
        assert config.transport == "http"
        assert config.url == "http://localhost:3000/mcp"

    def test_adapter_config(self):
        config = MCPAdapterConfig(
            servers=[
                MCPServerConfig(name="s1"),
                MCPServerConfig(name="s2"),
            ],
            tool_prefix=False,
        )
        assert len(config.servers) == 2
        assert not config.tool_prefix


# ── ToolCallResult Tests ─────────────────────────────────────────────


class TestToolCallResult:
    def test_text_extraction(self):
        result = ToolCallResult(
            content=[
                {"type": "text", "text": "line1"},
                {"type": "text", "text": "line2"},
            ],
        )
        assert result.text == "line1\nline2"
        assert result.success

    def test_error_result(self):
        result = ToolCallResult(
            content=[{"type": "text", "text": "something failed"}],
            is_error=True,
        )
        assert not result.success
        assert "failed" in result.text
