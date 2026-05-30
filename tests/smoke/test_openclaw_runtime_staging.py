from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows packaging smoke")
def test_stage_openclaw_runtime_is_slim_and_gateway_help_runs(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("Node.js not available")
    source = Path("openclaw/node_modules/openclaw/openclaw.mjs")
    if not source.exists():
        pytest.skip("Repo-local OpenClaw runtime not installed")

    output_root = tmp_path / "openclaw-runtime"
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts/stage-openclaw-runtime.ps1",
            "-OutputRoot",
            str(output_root),
        ],
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )

    package_root = output_root / "openclaw" / "node_modules" / "openclaw"
    assert (package_root / "openclaw.mjs").exists()
    assert not (package_root / "dist" / "extensions").exists()
    assert not (package_root / "node_modules" / "@napi-rs").exists()

    total_bytes = sum(path.stat().st_size for path in output_root.rglob("*") if path.is_file())
    assert total_bytes < 150 * 1024 * 1024

    result = subprocess.run(
        [
            "node",
            str(package_root / "openclaw.mjs"),
            "gateway",
            "--help",
        ],
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    assert "Run the WebSocket Gateway" in result.stdout
