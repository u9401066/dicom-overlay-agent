"""Opt-in real owned Win32 minimize/restore; no model requests or desktop capture."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import uuid

import pytest
from tests.unit.test_image_publication_guard import _agent

from dicom_overlay.domain.entities import AgentState, CaptureWindow
from dicom_overlay.infrastructure.screen_monitor import ScreenMonitor


@pytest.mark.skipif(sys.platform != "win32", reason="Native Win32 identity check")
async def test_owned_viewer_minimize_restore_retains_native_identity_without_inference():
    if os.environ.get("DICOM_RUN_WINDOWS_INPUT_SMOKE") != "1":
        pytest.skip("set DICOM_RUN_WINDOWS_INPUT_SMOKE=1 on an interactive desktop")
    import win32con
    import win32gui
    import win32process

    title = "Publication Recovery Synthetic " + uuid.uuid4().hex
    code = (
        "import os; from PyQt6.QtWidgets import QApplication,QWidget; "
        "from PyQt6.QtCore import Qt; "
        "app=QApplication([]); w=QWidget(); "
        "w.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint); "
        f"w.setWindowTitle({title!r}); "
        "w.setGeometry(300,200,320,240); w.setStyleSheet('background: #ffffff'); "
        "w.show(); print(os.getpid(),flush=True); app.exec()"
    )
    env = dict(os.environ, QT_QPA_PLATFORM="windows")
    child = subprocess.Popen(
        [sys.executable, "-c", code],
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    hwnd = None
    owner_pid = None
    pending = None
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            assert child.poll() is None, "Synthetic owned viewer terminated"
            hwnd = win32gui.FindWindow(None, title)
            if hwnd:
                break
            await asyncio.sleep(0.05)
        assert hwnd and child.stdout is not None
        # uv's Windows venv redirector can own a separate interpreter process.
        # Bind the exact child stdout receipt, not the launcher's PID.
        owner_pid = int(child.stdout.readline())
        assert win32process.GetWindowThreadProcessId(hwnd)[1] == owner_pid
        monitor = ScreenMonitor()
        window = monitor.select_capture_window(
            CaptureWindow(hwnd, owner_pid, win32gui.GetClassName(hwnd), title)
        )
        identity = monitor.capture_target_identity()
        assert identity and identity[:2] == (hwnd, owner_pid)
        agent, _fake_monitor, analyzer, _processor = _agent()
        agent._monitor = monitor
        agent._running = True
        agent._transition(AgentState.ANALYZING)
        waiting = asyncio.Event()
        agent.on_publication_status = lambda _text: waiting.set()
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        assert win32gui.IsIconic(hwnd)
        assert monitor.find_target_window([title]) is None
        pending = asyncio.create_task(
            agent._publication_window(
                expected_identity=identity, deadline=time.monotonic() + 5
            )
        )
        await asyncio.wait_for(waiting.wait(), 2)
        assert not pending.done() and analyzer.analyze_calls == 0
        assert win32process.GetWindowThreadProcessId(hwnd)[1] == owner_pid
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        restored = await asyncio.wait_for(pending, 3)
        assert restored == window and not win32gui.IsIconic(hwnd)
        assert monitor.capture_target_identity() == identity
        assert analyzer.analyze_calls == 0
        assert agent.displayed_review_snapshot is None  # No fabricated publication.
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        if (
            hwnd
            and win32gui.IsWindow(hwnd)
            and win32process.GetWindowThreadProcessId(hwnd)[1] == owner_pid
        ):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.terminate()  # Only this test-created child, never another app.
            child.wait(timeout=5)
