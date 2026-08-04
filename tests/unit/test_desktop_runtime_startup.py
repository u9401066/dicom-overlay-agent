from __future__ import annotations

import asyncio

from dicom_overlay.__main__ import _start_desktop_runtime


class _Gateway:
    def __init__(self, *, ready: bool = True, missing: bool = False) -> None:
        self.ready = ready
        self.missing = missing
        self.started = False

    def start(self) -> None:
        if self.missing:
            raise FileNotFoundError("node missing")
        self.started = True

    async def wait_ready(self) -> bool:
        return self.ready


class _Agent:
    def __init__(self) -> None:
        self._gateway = None
        self.started = False

    async def start(self) -> None:
        self.started = True


class _Mcp:
    def __init__(self) -> None:
        self.started = False

    async def start(self) -> None:
        self.started = True


def test_desktop_runtime_waits_for_gateway_off_qt_thread() -> None:
    gateway = _Gateway()
    agent = _Agent()
    mcp = _Mcp()

    status = asyncio.run(_start_desktop_runtime(gateway, agent, mcp))

    assert status == "ready"
    assert gateway.started is True
    assert agent._gateway is gateway
    assert agent.started is True
    assert mcp.started is True


def test_desktop_runtime_remains_available_without_gateway() -> None:
    gateway = _Gateway(missing=True)
    agent = _Agent()
    mcp = _Mcp()

    status = asyncio.run(_start_desktop_runtime(gateway, agent, mcp))

    assert status == "offline"
    assert agent._gateway is None
    assert agent.started is True
    assert mcp.started is True
