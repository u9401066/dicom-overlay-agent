from __future__ import annotations

from dicom_overlay.presentation.capture_safety import (
    _windows_build_number,
    capture_exclusion_supported,
)


def test_windows_build_number_is_fail_closed() -> None:
    assert _windows_build_number("10.0.26100") == 26100
    assert _windows_build_number("not-a-version") == 0


def test_capture_exclusion_requires_windows_10_2004_and_native_qt() -> None:
    assert capture_exclusion_supported(
        platform_name="win32",
        windows_version="10.0.19041",
        qt_platform_name="windows",
    )
    assert not capture_exclusion_supported(
        platform_name="win32",
        windows_version="10.0.18363",
        qt_platform_name="windows",
    )
    assert not capture_exclusion_supported(
        platform_name="win32",
        windows_version="10.0.26100",
        qt_platform_name="offscreen",
    )
    assert not capture_exclusion_supported(
        platform_name="linux",
        windows_version="10.0.26100",
        qt_platform_name="xcb",
    )
