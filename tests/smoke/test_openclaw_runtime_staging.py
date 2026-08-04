from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _node_executable() -> str | None:
    bundled = _REPO_ROOT / "node" / ("node.exe" if sys.platform == "win32" else "node")
    if bundled.exists():
        return str(bundled)
    return shutil.which("node")


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows packaging smoke")
def test_stage_openclaw_runtime_is_slim_and_gateway_help_runs(tmp_path):
    node = _node_executable()
    if node is None:
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
    assert (package_root / "dist" / "extensions").exists()
    assert (package_root / "dist" / "plugin-sdk").exists()
    assert any((package_root / "skills").glob("*/SKILL.md"))
    assert (package_root / "node_modules" / "quickjs-wasi").exists()
    assert (package_root / "node_modules" / "playwright-core").exists()
    assert not [
        path
        for path in package_root.rglob("*")
        if path.is_file()
        and (path.name.casefold() == ".env" or path.name.casefold().startswith(".env."))
    ]

    total_bytes = sum(
        path.stat().st_size for path in output_root.rglob("*") if path.is_file()
    )
    assert total_bytes < 500 * 1024 * 1024

    result = subprocess.run(
        [
            node,
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
