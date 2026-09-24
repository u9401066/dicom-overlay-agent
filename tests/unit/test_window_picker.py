from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QItemSelectionModel
from PyQt6.QtWidgets import QPushButton

from dicom_overlay.domain.entities import CaptureWindow, WindowRect
from dicom_overlay.domain.services import CaptureBlockedError
from dicom_overlay.infrastructure import screen_monitor
from dicom_overlay.presentation.settings_dialog import SettingsDialog
from dicom_overlay.presentation.window_picker import WindowPickerDialog


@pytest.fixture
def window_environment(monkeypatch):
    rows = {
        1: {
            "pid": 101,
            "title": "Browser image",
            "cls": "Browser",
            "visible": True,
            "iconic": False,
        },
        2: {
            "pid": 102,
            "title": "DICOM Viewer",
            "cls": "Viewer",
            "visible": True,
            "iconic": False,
        },
        3: {
            "pid": os.getpid(),
            "title": "Own dialog",
            "cls": "Qt",
            "visible": True,
            "iconic": False,
        },
    }
    gui = SimpleNamespace(
        EnumWindows=lambda visit, context: [visit(hwnd, context) for hwnd in rows],
        IsWindow=lambda hwnd: hwnd in rows,
        GetWindow=lambda hwnd, _: rows[hwnd].get("owner", 0),
        IsWindowVisible=lambda hwnd: rows[hwnd]["visible"],
        IsIconic=lambda hwnd: rows[hwnd]["iconic"],
        GetWindowText=lambda hwnd: rows[hwnd]["title"],
        GetClassName=lambda hwnd: rows[hwnd]["cls"],
        GetWindowRect=lambda hwnd: (20, 30, 1020, 730),
    )
    monkeypatch.setattr(screen_monitor, "HAS_WIN32", True)
    monkeypatch.setattr(screen_monitor, "win32gui", gui)
    monkeypatch.setattr(
        screen_monitor,
        "win32process",
        SimpleNamespace(GetWindowThreadProcessId=lambda hwnd: (1, rows[hwnd]["pid"])),
    )
    monkeypatch.setattr(screen_monitor, "_window_is_cloaked", lambda _: False)
    return screen_monitor.ScreenMonitor(), rows


def test_explicit_browser_selection_survives_title_change_without_keyword_matching(
    window_environment,
):
    monitor, rows = window_environment
    choices = monitor.available_capture_windows()
    assert [choice.window_id for choice in choices] == [1, 2]
    expected = WindowRect(20, 30, 1000, 700)
    assert monitor.select_capture_window(choices[0]) == expected
    rows[1]["title"] = "Different tab title"
    assert monitor.find_target_window(["DICOM"]) == expected
    assert monitor._target_hwnd == 1
    assert monitor.explicit_window_selected


@pytest.mark.parametrize("change", ["closed", "pid", "cls", "iconic", "visible"])
def test_lost_selected_window_never_falls_back_to_another_viewer(
    window_environment, change
):
    monitor, rows = window_environment
    monitor.select_capture_window(monitor.available_capture_windows()[0])
    if change == "closed":
        del rows[1]
    else:
        rows[1][change] = {
            "pid": 999,
            "cls": "Different",
            "iconic": True,
            "visible": False,
        }[change]
    assert monitor.find_target_window(["DICOM"]) is None
    assert monitor._target_hwnd is None
    assert monitor.explicit_window_selected  # Failed closed; no automatic discovery.
    with pytest.raises(CaptureBlockedError):
        monitor.verify_capture_target(WindowRect(30, 40, 100, 100))


def test_failed_reselection_preserves_valid_binding(window_environment):
    monitor, _rows = window_environment
    chosen = monitor.available_capture_windows()[0]
    monitor.select_capture_window(chosen)
    with pytest.raises(CaptureBlockedError):
        monitor.select_capture_window(
            CaptureWindow(2, 999, "Viewer", "Untrusted stale row")
        )
    assert monitor._selected_window == chosen
    with pytest.raises(CaptureBlockedError):
        monitor.select_capture_window(CaptureWindow(3, os.getpid(), "Qt", "Own dialog"))


def test_detected_destroy_requires_explicit_reselection_even_if_handle_reappears(
    window_environment,
):
    monitor, rows = window_environment
    choice = monitor.available_capture_windows()[0]
    monitor.select_capture_window(choice)
    old = rows.pop(1)
    assert monitor.find_target_window(["DICOM"]) is None
    rows[1] = old
    assert monitor.find_target_window(["DICOM"]) is None
    monitor.select_capture_window(choice)
    assert monitor.find_target_window([]) == WindowRect(20, 30, 1000, 700)


@pytest.mark.parametrize(
    "window_class", ["Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"]
)
def test_shell_desktop_cannot_be_selected_as_image_window(
    window_environment, window_class
):
    monitor, rows = window_environment
    rows[1]["cls"] = window_class
    assert [choice.window_id for choice in monitor.available_capture_windows()] == [2]
    with pytest.raises(CaptureBlockedError, match="desktop_shell"):
        monitor.select_capture_window(CaptureWindow(1, 101, window_class, "Desktop"))


def test_transient_browser_popup_is_not_offered(window_environment):
    monitor, rows = window_environment
    rows[1]["owner"] = 2
    assert [choice.window_id for choice in monitor.available_capture_windows()] == [2]


def test_window_picker_requires_explicit_selection_and_refresh_clears_it(qtbot):
    chosen = CaptureWindow(1, 101, "Browser", "Synthetic image window")
    dialog = WindowPickerDialog(lambda: [chosen])
    qtbot.addWidget(dialog)
    assert not dialog._use.isEnabled()
    assert dialog.selected_window() is None
    dialog._windows.setCurrentRow(0)
    assert dialog._use.isEnabled() and dialog.selected_window() == chosen
    dialog.refresh()
    assert not dialog._use.isEnabled() and dialog.selected_window() is None


def test_window_picker_accessibility_selection_wins_over_keyboard_current_row(qtbot):
    first = CaptureWindow(1, 101, "Editor", "Unselected unrelated window")
    browser = CaptureWindow(2, 102, "Browser", "Intended image window")
    dialog = WindowPickerDialog(lambda: [first, browser])
    qtbot.addWidget(dialog)
    dialog._windows.setCurrentRow(0)
    # Windows UIA SelectionItem.Select changes selected items, not currentItem.
    dialog._windows.item(1).setSelected(True)
    assert dialog._windows.currentItem() is dialog._windows.item(0)
    assert dialog._windows.selectedItems() == [dialog._windows.item(1)]
    assert dialog._use.isEnabled()
    assert dialog.selected_window() == browser


def test_window_picker_focus_without_selection_cannot_enable_capture(qtbot):
    chosen = CaptureWindow(1, 101, "Browser", "Synthetic image window")
    dialog = WindowPickerDialog(lambda: [chosen])
    qtbot.addWidget(dialog)
    dialog._windows.setCurrentRow(0, QItemSelectionModel.SelectionFlag.NoUpdate)
    assert dialog._windows.currentItem() is not None
    assert dialog.selected_window() is None
    assert not dialog._use.isEnabled()


def test_window_picker_clear_selection_does_not_reuse_current_item(qtbot):
    chosen = CaptureWindow(1, 101, "Browser", "Synthetic image window")
    dialog = WindowPickerDialog(lambda: [chosen])
    qtbot.addWidget(dialog)
    dialog._windows.setCurrentRow(0)
    dialog._windows.clearSelection()
    assert dialog._windows.currentItem() is not None
    assert dialog.selected_window() is None
    assert not dialog._use.isEnabled()


def test_settings_closes_before_requesting_capture_window(qtbot, tmp_path):
    dialog = SettingsDialog(repo_root=tmp_path)
    qtbot.addWidget(dialog)
    observed = []
    dialog.capture_window_requested.connect(lambda: observed.append(dialog.isVisible()))
    dialog.show()
    dialog.findChild(QPushButton, "chooseCaptureWindow").click()
    assert observed == [False]


def test_settings_closes_before_roi_preview(qtbot, tmp_path):
    dialog = SettingsDialog(repo_root=tmp_path)
    qtbot.addWidget(dialog)
    observed = []
    dialog.roi_setup_requested.connect(lambda: observed.append(dialog.isVisible()))
    dialog.show()
    next(
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == "Set ROI"
    ).click()
    assert observed == [False]
