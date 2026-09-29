"""Window identity contains no title; visibility and pixel checks remain separate."""

from types import SimpleNamespace

import pytest

from dicom_overlay.infrastructure import screen_monitor


@pytest.mark.parametrize(
    "mode",
    ["valid", "missing", "destroyed", "pid_changed", "empty_class", "native_error"],
)
def test_capture_identity_uses_existing_window_process_and_class_only(
    monkeypatch, mode
):
    def native_class(_hwnd):
        if mode == "native_error":
            raise RuntimeError("private native text")
        return "" if mode == "empty_class" else "SyntheticClass"

    monkeypatch.setattr(screen_monitor, "HAS_WIN32", True)
    monkeypatch.setattr(
        screen_monitor,
        "win32gui",
        SimpleNamespace(
            IsWindow=lambda _hwnd: mode != "destroyed", GetClassName=native_class
        ),
    )
    monkeypatch.setattr(
        screen_monitor,
        "win32process",
        SimpleNamespace(
            GetWindowThreadProcessId=lambda _hwnd: (
                1,
                99 if mode == "pid_changed" else 42,
            )
        ),
    )
    monitor = screen_monitor.ScreenMonitor()
    monitor._target_hwnd = None if mode == "missing" else 1
    monitor._target_pid = 42
    assert monitor.capture_target_identity() == (
        (1, 42, "SyntheticClass") if mode == "valid" else None
    )


def test_non_windows_monitor_has_no_recovery_identity(monkeypatch):
    monkeypatch.setattr(screen_monitor, "HAS_WIN32", False)
    assert screen_monitor.ScreenMonitor().capture_target_identity() is None
