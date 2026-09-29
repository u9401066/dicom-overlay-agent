"""Real sockets: unread events must not block an otherwise healthy close."""

from __future__ import annotations

import asyncio

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from dicom_overlay.infrastructure.openclaw_client import OpenClawClient


@pytest.mark.asyncio
@pytest.mark.parametrize("event_count", [0, 80])
async def test_disconnect_closes_cleanly_with_backpressured_unread_events(
    tmp_path, event_count
):
    sent = asyncio.Event()
    peer_codes = []

    async def gateway(websocket):
        for _ in range(event_count):
            await websocket.send('{"type":"event","event":"tick","payload":{}}')
        sent.set()
        await websocket.wait_closed()
        peer_codes.append(websocket.close_code)

    async with serve(gateway, "127.0.0.1", 0, ping_interval=None) as server:
        port = server.sockets[0].getsockname()[1]
        websocket = await connect(
            f"ws://127.0.0.1:{port}",
            ping_interval=None,
            close_timeout=0.4,
            proxy=None,
        )
        client = OpenClawClient(gateway_token="synthetic", base_dir=tmp_path)
        client._ws = websocket
        client._connected = True
        client._close_timeout = 0.4
        try:
            await asyncio.wait_for(sent.wait(), 2)
            # Test-only inspection establishes actual backpressure, not merely
            # a delay or an assumption that many sends filled a local queue.
            if event_count:
                async with asyncio.timeout(2):
                    while not websocket.recv_messages.paused:
                        await asyncio.sleep(0.001)
            assert (websocket.recv_messages.high, websocket.recv_messages.low) == (
                16,
                4,
            )
            await asyncio.wait_for(client.disconnect(), 1)
            assert websocket.close_code == 1000
            assert not client.is_connected()
        finally:
            # Ensure a failing regression doesn't leave the test socket alive.
            websocket.transport.abort()
            await websocket.wait_closed()
    assert peer_codes == [1000]


@pytest.mark.asyncio
async def test_disconnect_does_not_drain_an_active_turn(tmp_path):
    class ActiveTurnSocket:
        close_calls = 0
        recv_calls = 0

        async def recv(self):
            self.recv_calls += 1
            raise AssertionError("Shutdown stole an active turn's response")

        async def close(self):
            self.close_calls += 1
            await asyncio.sleep(0)

    socket = ActiveTurnSocket()
    client = OpenClawClient(gateway_token="synthetic", base_dir=tmp_path)
    client._ws, client._connected = socket, True
    async with client._ws_lock:
        await client.disconnect()
    assert socket.close_calls == 1 and socket.recv_calls == 0
    await client.disconnect()  # Idempotent; no second reader/close created.
    assert socket.close_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("flood", [False, True])
async def test_timeout_cancels_the_drain_even_for_a_flooding_peer(tmp_path, flood):
    drain_finished = asyncio.Event()
    reads = 0

    class HangingSocket:
        async def recv(self):
            nonlocal reads
            reads += 1
            if flood:
                return "synthetic event"
            try:
                await asyncio.Event().wait()
            finally:
                drain_finished.set()

        async def close(self):
            await asyncio.Event().wait()

    client = OpenClawClient(gateway_token="synthetic", base_dir=tmp_path)
    client._ws, client._connected = HangingSocket(), True
    client._close_timeout = 0.02
    await asyncio.wait_for(client.disconnect(), 1)
    assert reads > 0
    if not flood:
        assert drain_finished.is_set()
    assert not client.is_connected()
    assert not any(t.get_name() == "openclaw-close-drain" for t in asyncio.all_tasks())


@pytest.mark.asyncio
async def test_cancelling_disconnect_also_cleans_up_its_drain(tmp_path):
    drain_started = asyncio.Event()
    drain_finished = asyncio.Event()

    class HangingSocket:
        async def recv(self):
            drain_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                drain_finished.set()

        async def close(self):
            await asyncio.Event().wait()

    client = OpenClawClient(gateway_token="synthetic", base_dir=tmp_path)
    client._ws, client._connected = HangingSocket(), True
    closing = asyncio.create_task(client.disconnect())
    await asyncio.wait_for(drain_started.wait(), 1)
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert drain_finished.is_set()
    assert not client.is_connected()
    assert not any(t.get_name() == "openclaw-close-drain" for t in asyncio.all_tasks())
