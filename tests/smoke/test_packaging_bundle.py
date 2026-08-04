"""Packaging / portability smoke tests.

These verify the "USB plug-and-play" goal: the bundle can self-check that it
finds everything it needs to start (Node.js runtime, OpenClaw gateway script,
config, writable base) anchored to the executable folder — without launching
the GUI or contacting an LLM.

Two layers:
- ``test_selfcheck_reports_all_components`` runs the in-process self-check
  against the dev tree (fast, always runs). It proves the self-check wiring
  works and the config resolves; node/openclaw may legitimately be unstaged in
  CI, so those rows are reported but not hard-required here.
- ``test_built_bundle_selfcheck_exits_zero`` runs the *real built executable*
  with ``--selfcheck`` and requires exit code 0. It is **opt-in** via
  ``RUN_BUNDLE_SMOKE=1`` because (a) the ``dist/`` build may be stale relative
  to the source and (b) it spawns a windowed PyInstaller exe — neither belongs
  in the fast default suite. A release pipeline runs ``scripts/build-exe.bat``
  then sets ``RUN_BUNDLE_SMOKE=1`` to validate the freshly packaged bundle.
"""

from __future__ import annotations

import io
import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _assert_clean_roi_seed(config_path: Path) -> None:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    roi = config["phi_roi"]
    assert roi["configured"] is False
    assert roi["coordinate_space"] == "viewer"
    assert roi["reference_width"] == 0
    assert roi["reference_height"] == 0
    assert all(roi[edge] == 0 for edge in ("top", "bottom", "left", "right"))


def test_shipped_config_requires_per_workstation_roi_setup():
    _assert_clean_roi_seed(_REPO_ROOT / "config.yaml")


def test_selfcheck_reports_all_components():
    from dicom_overlay.__main__ import _run_selfcheck

    config_path = _REPO_ROOT / "config.yaml"
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = _run_selfcheck(_REPO_ROOT, config_path)
    out = buffer.getvalue()

    # Every component the bundle needs is reported on.
    for component in (
        "base_dir",
        "config.yaml",
        "skills",
        "harness_plugin",
        "clinical_rules",
        "node",
        "openclaw",
        "openclaw_bundled_skills",
        "openclaw_plugin_surfaces",
        "harness_native_plugin",
        "writable_base",
    ):
        assert component in out, f"self-check did not report {component}\n{out}"

    # Config + writable base must be OK in the dev tree (they ship in the repo);
    # node/openclaw may be unstaged in CI, so the overall code can be 0 or 1.
    assert "RESULT:" in out
    assert config_path.exists()
    assert code in (0, 1)


def _built_exe() -> Path | None:
    if sys.platform != "win32":
        return None
    exe = _REPO_ROOT / "dist" / "DICOMOverlayAgent" / "DICOMOverlayAgent.exe"
    return exe if exe.exists() else None


@pytest.mark.skipif(
    os.environ.get("RUN_BUNDLE_SMOKE") != "1" or _built_exe() is None,
    reason=(
        "Opt-in: set RUN_BUNDLE_SMOKE=1 after scripts/build-exe.bat to validate "
        "the freshly built dist/ bundle"
    ),
)
def test_built_bundle_selfcheck_exits_zero():
    exe = _built_exe()
    assert exe is not None
    bundle = exe.parent
    _assert_clean_roi_seed(bundle / "config.yaml")
    assert not (bundle / "overlay_agent.log").exists()
    assert not (bundle / "openclaw-home").exists()
    result = subprocess.run(
        [str(exe), "--selfcheck"],
        cwd=str(exe.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    # A complete portable bundle finds node + openclaw + config + writable base.
    assert result.returncode == 0, (
        f"bundle self-check failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert not (bundle / "overlay_agent.log").exists()
    assert not (bundle / "openclaw-home").exists()


@pytest.mark.skipif(
    os.environ.get("RUN_GATEWAY_BUNDLE_SMOKE") != "1" or _built_exe() is None,
    reason=(
        "Opt-in: set RUN_GATEWAY_BUNDLE_SMOKE=1 after scripts/build-exe.bat "
        "to start and authenticate to the packaged Gateway"
    ),
)
def test_built_bundle_gateway_smoke_isolated(tmp_path: Path):
    exe = _built_exe()
    assert exe is not None
    assert not _port_open(18789)
    isolated = shutil.copytree(exe.parent, tmp_path / "DICOMOverlayAgent")
    isolated_exe = isolated / exe.name
    env = os.environ.copy()
    env.pop("OPENCLAW_GATEWAY_TOKEN", None)
    env["OPENAI_API_KEY"] = "packaged-runtime-smoke-invalid-key"

    result = subprocess.run(
        [str(isolated_exe), "--gateway-smoke"],
        cwd=isolated,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )

    gateway_log = (isolated / "gateway.log").read_text(
        encoding="utf-8", errors="replace"
    )
    assert result.returncode == 0, (
        f"packaged Gateway smoke failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}\n{gateway_log}"
    )
    assert "OPENCLAW_GATEWAY_TOKEN=" in (isolated / ".env").read_text(
        encoding="utf-8"
    )
    assert "[gateway] ready" in gateway_log
    deadline = time.monotonic() + 15
    while _port_open(18789) and time.monotonic() < deadline:
        time.sleep(0.25)
    assert not _port_open(18789), "packaged Gateway process remained after smoke exit"


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False
