from __future__ import annotations

import asyncio

from dicom_overlay.__main__ import _start_desktop_runtime


class _Gateway:
    def __init__(
        self,
        *,
        ready: bool = True,
        missing: bool = False,
        events: list[str] | None = None,
    ) -> None:
        self.ready = ready
        self.missing = missing
        self.started = False
        self.events = events

    def start(self) -> None:
        if self.missing:
            raise FileNotFoundError("node missing")
        self.started = True
        if self.events is not None:
            self.events.append("gateway_start")

    async def wait_ready(self) -> bool:
        if self.events is not None:
            self.events.append("gateway_wait")
        return self.ready


class _Agent:
    def __init__(self, events: list[str] | None = None) -> None:
        self._gateway = None
        self.started = False
        self.events = events

    async def start(self) -> None:
        self.started = True
        if self.events is not None:
            self.events.append("agent_start")


class _Mcp:
    def __init__(self) -> None:
        self.started = False

    async def start(self) -> None:
        self.started = True


def test_desktop_runtime_waits_for_gateway_off_qt_thread() -> None:
    events: list[str] = []
    gateway = _Gateway(events=events)
    agent = _Agent(events)
    mcp = _Mcp()

    status = asyncio.run(_start_desktop_runtime(gateway, agent, mcp))

    assert status == "ready"
    assert gateway.started is True
    assert agent._gateway is gateway
    assert agent.started is True
    assert mcp.started is True
    assert events == ["gateway_start", "agent_start", "gateway_wait"]


def test_desktop_runtime_remains_available_without_gateway() -> None:
    gateway = _Gateway(missing=True)
    agent = _Agent()
    mcp = _Mcp()

    status = asyncio.run(_start_desktop_runtime(gateway, agent, mcp))

    assert status == "offline"
    assert agent._gateway is None
    assert agent.started is True
    assert mcp.started is True
