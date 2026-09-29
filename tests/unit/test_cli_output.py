"""CLI diagnostics are UTF-8 even on legacy Windows pipe encodings."""

import io
import os
import subprocess
import sys
from unittest.mock import Mock

import pytest

from dicom_overlay.__main__ import _print_cli


@pytest.mark.parametrize("encoding", ["cp1252", "cp950", "ascii", "utf-8"])
def test_cli_writes_lossless_utf8_to_redirected_stream(monkeypatch, encoding):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding=encoding, errors="replace")
    monkeypatch.setattr("sys.stdout", stream)

    _print_cli("DICOM Overlay Agent — self-check")
    _print_cli("臨床一致性規則", "供人工審核")
    stream.flush()

    assert raw.getvalue().decode("utf-8").splitlines() == [
        "DICOM Overlay Agent — self-check",
        "臨床一致性規則 供人工審核",
    ]


def test_cli_preserves_string_capture(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr("sys.stdout", stream)
    _print_cli("臨床規則", 7)
    assert stream.getvalue() == "臨床規則 7\n"


def test_cli_windowed_without_stdout(monkeypatch):
    monkeypatch.setattr("sys.stdout", None)
    _print_cli("臨床規則")


@pytest.mark.parametrize("encoding", ["cp1252", "cp950", "ascii"])
@pytest.mark.parametrize("missing_win32", [False, True], ids=["native", "no-win32"])
def test_real_python_cli_overrides_legacy_pipe_encoding(encoding, missing_win32):
    env = dict(os.environ, PYTHONIOENCODING=f"{encoding}:strict")
    prelude = "import sys; sys.modules['win32api'] = None; " if missing_win32 else ""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            prelude + "from dicom_overlay.__main__ import _print_cli; "
            "_print_cli('DICOM Overlay Agent \\u2014 self-check'); "
            "_print_cli('\\u81e8\\u5e8a\\u898f\\u5247')",
        ],
        capture_output=True,
        env=env,
        timeout=30,
        check=True,
    )
    assert result.stdout.decode("utf-8").splitlines() == [
        "DICOM Overlay Agent — self-check",
        "臨床規則",
    ]
    assert result.stderr == b""


def test_missing_win32_warning_is_retained_when_monitor_is_constructed(monkeypatch):
    from dicom_overlay.infrastructure import screen_monitor

    logger = Mock()
    monkeypatch.setattr(screen_monitor, "HAS_WIN32", False)
    monkeypatch.setattr(screen_monitor, "logger", logger)

    monitor = screen_monitor.ScreenMonitor()

    logger.warning.assert_called_once_with(
        "pywin32 not available — window detection disabled"
    )
    assert monitor.find_target_window(["synthetic viewer"]) is None
