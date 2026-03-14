"""Async-to-Qt bridge — runs asyncio coroutines in a background thread.

Eliminates UI blocking by running all async operations (agent tick, analysis,
chat) in a dedicated thread with its own asyncio event loop.  Results are
delivered back to the Qt main thread via pyqtSignal / QueuedConnection.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concurrent.futures import Future

import structlog
from PyQt6.QtCore import QThread

logger = structlog.get_logger(__name__)


class AsyncBridge(QThread):
    """Background thread running an asyncio event loop.

    Usage::

        bridge = AsyncBridge()
        bridge.start()

        future = bridge.submit(some_coroutine())
        # future is concurrent.futures.Future — non-blocking unless .result() called

        bridge.shutdown()
    """

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Return the background event loop (blocks until ready)."""
        self._ready.wait()
        assert self._loop is not None
        return self._loop

    def run(self) -> None:
        """Thread entry — create event loop and run forever."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        logger.info("AsyncBridge event loop started")
        self._loop.run_forever()

        # Drain remaining tasks
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            with contextlib.suppress(Exception):
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        self._loop.close()
        logger.info("AsyncBridge event loop stopped")

    def submit(self, coro: Any) -> Future:
        """Submit a coroutine to run in the background loop.

        Returns a ``concurrent.futures.Future``.  Call ``.result()`` only if you
        need to block (e.g. at startup); otherwise attach a done-callback or
        let it fire-and-forget.
        """
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def shutdown(self) -> None:
        """Stop the background event loop and wait for the thread to finish."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.wait(5000)
