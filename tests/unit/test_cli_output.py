"""CLI diagnostics are UTF-8 even on legacy Windows pipe encodings."""

import io
import os
import subprocess
import sys

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
def test_real_python_cli_overrides_legacy_pipe_encoding(encoding):
    env = dict(os.environ, PYTHONIOENCODING=f"{encoding}:strict")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from dicom_overlay.__main__ import _print_cli; "
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
