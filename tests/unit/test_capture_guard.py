"""Pure Win32-contract fakes; actual desktop evidence is a separate gate."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dicom_overlay.domain.entities import WindowRect
from dicom_overlay.domain.services import CaptureBlockedError
from dicom_overlay.infrastructure import screen_monitor


@pytest.fixture
def desktop(monkeypatch):
    windows = {
        1: {
            "visible": True,
            "iconic": False,
            "cloaked": False,
            "pid": 42,
            "rect": (-1000, 30, 500, 1130),
            "client_origin": (-990, 70),
            "client_size": (1480, 1040),
            "above": 2,
        },
        2: {
            "visible": True,
            "iconic": False,
            "cloaked": False,
            "pid": 43,
            "rect": (600, 40, 900, 300),
            "above": 0,
        },
    }
    gui = SimpleNamespace(
        IsWindowVisible=lambda h: windows[h]["visible"],
        IsIconic=lambda h: windows[h]["iconic"],
        GetWindowRect=lambda h: windows[h]["rect"],
        GetClientRect=lambda h: (0, 0, *windows[h]["client_size"]),
        ClientToScreen=lambda h, point: (
            windows[h]["client_origin"][0] + point[0],
            windows[h]["client_origin"][1] + point[1],
        ),
        GetWindow=lambda h, relationship: (
            windows[h]["above"] if relationship == 3 else None
        ),
    )
    monkeypatch.setattr(screen_monitor, "HAS_WIN32", True)
    monkeypatch.setattr(screen_monitor, "win32gui", gui)
    monkeypatch.setattr(
        screen_monitor,
        "win32process",
        SimpleNamespace(
            GetWindowThreadProcessId=lambda h: (1, windows[h]["pid"]),
        ),
    )
    monkeypatch.setattr(
        screen_monitor, "_window_is_cloaked", lambda h: windows[h]["cloaked"]
    )
    monitor = screen_monitor.ScreenMonitor()
    monitor._target_hwnd = 1
    monitor._target_pid = 42
    monitor._target_rect = WindowRect(-1000, 30, 1500, 1100)
    return monitor, windows, gui


ROI = WindowRect(-990, 70, 1480, 1040)


def test_unobstructed_negative_coordinate_viewer(desktop):
    monitor, _, _ = desktop
    monitor.verify_capture_target(ROI)


@pytest.mark.parametrize(
    "cover",
    [
        (-990, 70, 490, 1110),  # complete terminal occlusion
        (-70, 600, -69, 601),  # one-pixel sliver, not a point-grid heuristic
        (489, 1109, 600, 1200),  # bottom-right edge
    ],
)
@pytest.mark.parametrize("same_process", [False, True])
def test_any_visible_intersection_blocks_even_owned_or_transparent_windows(
    desktop, cover, same_process
):
    monitor, windows, _ = desktop
    windows[2]["rect"] = cover
    if same_process:
        windows[2]["pid"] = 42
    with pytest.raises(CaptureBlockedError, match="viewer_roi_obstructed"):
        monitor.verify_capture_target(ROI)


@pytest.mark.parametrize("state", ["hidden", "iconic", "cloaked"])
def test_confirmed_non_displayed_windows_do_not_block(desktop, state):
    monitor, windows, _ = desktop
    windows[2]["rect"] = (-990, 70, 490, 1110)
    windows[2]["visible" if state == "hidden" else state] = state != "hidden"
    monitor.verify_capture_target(ROI)


def test_touching_boundary_without_intersection_is_allowed(desktop):
    monitor, windows, _ = desktop
    windows[2]["rect"] = (ROI.right, 70, 700, 300)
    monitor.verify_capture_target(ROI)


@pytest.mark.parametrize("state", ["hidden", "iconic", "cloaked"])
def test_viewer_must_be_displayed(desktop, state):
    monitor, windows, _ = desktop
    windows[1]["visible" if state == "hidden" else state] = state != "hidden"
    with pytest.raises(CaptureBlockedError, match="viewer_not_visible"):
        monitor.verify_capture_target(ROI)


def test_geometry_change_rejects_stale_roi(desktop):
    monitor, windows, _ = desktop
    windows[1]["rect"] = (-1000, 31, 500, 1131)
    with pytest.raises(CaptureBlockedError, match="viewer_geometry_changed"):
        monitor.verify_capture_target(ROI)


def test_recycled_window_handle_rejected(desktop):
    monitor, windows, _ = desktop
    windows[1]["pid"] = 99
    with pytest.raises(CaptureBlockedError, match="viewer_identity_changed"):
        monitor.verify_capture_target(ROI)


@pytest.mark.parametrize(
    "rect",
    [
        WindowRect(-1001, 70, 100, 100),
        WindowRect(-990, 29, 100, 100),
        WindowRect(-990, 70, 1491, 100),
        WindowRect(-990, 70, 100, 1061),
        WindowRect(-990, 70, 0, 100),
    ],
)
def test_roi_cannot_extend_outside_viewer(desktop, rect):
    monitor, _, _ = desktop
    with pytest.raises(CaptureBlockedError, match="roi_outside_viewer"):
        monitor.verify_capture_target(rect)


@pytest.mark.parametrize(
    "rect",
    [
        WindowRect(-990, 69, 100, 100),  # one titlebar pixel
        WindowRect(-991, 70, 100, 100),  # one left-border pixel
        WindowRect(390, 70, 101, 100),  # one right-border pixel
        WindowRect(-990, 1010, 100, 101),  # one bottom-border pixel
    ],
)
def test_roi_inside_outer_window_must_not_capture_chrome(desktop, rect):
    monitor, _, _ = desktop
    with pytest.raises(CaptureBlockedError, match="roi_outside_viewer_client"):
        monitor.verify_capture_target(rect)


def test_downsized_viewer_roi_cannot_scale_the_titlebar_into_capture(desktop):
    from dicom_overlay.application.roi import compute_viewer_roi_rect
    from dicom_overlay.domain.entities import ROICrop

    monitor, windows, _ = desktop
    windows[1]["rect"] = (-1000, 30, 522, 947)
    windows[1]["client_origin"] = (-989, 75)
    windows[1]["client_size"] = (1500, 864)
    monitor._target_rect = WindowRect(-1000, 30, 1522, 917)
    selected = ROICrop(
        top=45, bottom=12, left=11, right=12, configured=True,
        reference_width=1522, reference_height=1137,
    )
    scaled = compute_viewer_roi_rect(monitor._target_rect, selected)
    assert scaled.top < windows[1]["client_origin"][1]
    with pytest.raises(CaptureBlockedError, match="roi_outside_viewer_client"):
        monitor.verify_capture_target(scaled)


def test_frameless_viewer_may_use_its_selected_full_client(desktop):
    monitor, windows, _ = desktop
    windows[1]["client_origin"] = (-1000, 30)
    windows[1]["client_size"] = (1500, 1100)
    monitor.verify_capture_target(monitor._target_rect)


@pytest.mark.parametrize("method", ["GetClientRect", "ClientToScreen"])
def test_client_geometry_api_failure_is_sanitized(desktop, method):
    monitor, _, gui = desktop

    def fail(*_args):
        raise RuntimeError("PRIVATE WINDOW METADATA")

    setattr(gui, method, fail)
    with pytest.raises(CaptureBlockedError, match=r"^window_verification_failed$"):
        monitor.verify_capture_target(ROI)


@pytest.mark.parametrize("client_size", [(0, 1040), (1480, 0), (1600, 1040)])
def test_empty_or_inconsistent_client_bounds_fail_closed(desktop, client_size):
    monitor, windows, _ = desktop
    windows[1]["client_size"] = client_size
    with pytest.raises(CaptureBlockedError, match="viewer_client_geometry_invalid"):
        monitor.verify_capture_target(ROI)


def test_z_order_cycle_is_bounded(desktop):
    monitor, windows, _ = desktop
    windows[2]["above"] = 1
    with pytest.raises(CaptureBlockedError, match="unstable_window_order"):
        monitor.verify_capture_target(ROI)


def test_disappearing_window_failure_does_not_expose_metadata(desktop):
    monitor, _, gui = desktop

    def fail(_hwnd):
        raise RuntimeError("PRIVATE WINDOW TITLE")

    gui.GetWindowRect = fail
    with pytest.raises(CaptureBlockedError, match=r"^window_verification_failed$"):
        monitor.verify_capture_target(ROI)


def test_no_windows_api_is_not_silently_safe(desktop, monkeypatch):
    monitor, _, _ = desktop
    monkeypatch.setattr(screen_monitor, "HAS_WIN32", False)
    with pytest.raises(CaptureBlockedError, match="window_verification_unavailable"):
        monitor.verify_capture_target(ROI)


def test_no_selected_viewer_rejected(desktop):
    monitor, _, _ = desktop
    monitor._target_hwnd = None
    with pytest.raises(CaptureBlockedError, match="viewer_not_selected"):
        monitor.verify_capture_target(ROI)
