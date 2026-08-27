from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repo_staging_output():
    output = _REPO_ROOT / "data" / "tmp" / f"pytest-openclaw-stage-{uuid4().hex}"
    try:
        yield output
    finally:
        if output.exists():
            shutil.rmtree(output)


def _node_executable() -> str | None:
    bundled = _REPO_ROOT / "node" / ("node.exe" if sys.platform == "win32" else "node")
    if bundled.exists():
        return str(bundled)
    return shutil.which("node")


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows packaging smoke")
def test_stage_openclaw_runtime_is_slim_and_gateway_help_runs(
    tmp_path, repo_staging_output
):
    node = _node_executable()
    if node is None:
        pytest.skip("Node.js not available")
    source = Path("openclaw/node_modules/openclaw/openclaw.mjs")
    if not source.exists():
        pytest.skip("Repo-local OpenClaw runtime not installed")

    output_root = repo_staging_output
    relative_output = output_root.relative_to(_REPO_ROOT)
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_REPO_ROOT / "scripts/stage-openclaw-runtime.ps1"),
            "-OutputRoot",
            str(relative_output),
        ],
        cwd=tmp_path,
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
    runtime_templates = {
        "HEARTBEAT.md": package_root / "src/agents/templates/HEARTBEAT.md",
        **{
            name: package_root / f"docs/reference/templates/{name}"
            for name in (
                "AGENTS.md",
                "SOUL.md",
                "TOOLS.md",
                "IDENTITY.md",
                "USER.md",
                "BOOTSTRAP.md",
            )
        },
    }
    assert all(
        path.is_file() and path.read_text(encoding="utf-8-sig").strip()
        for path in runtime_templates.values()
    )
    assert not [
        path
        for path in package_root.rglob("*")
        if path.is_file()
        and (path.name.casefold() == ".env" or path.name.casefold().startswith(".env."))
    ]
    assert not list(package_root.rglob("*.pdb"))
    tree_sitter_source = package_root / "node_modules/tree-sitter-bash/src"
    assert not [
        path
        for path in tree_sitter_source.rglob("*")
        if path.is_file() and path.suffix.casefold() in {".c", ".h"}
    ]
    assert [
        path.name for path in (package_root / "node_modules/@lydell").glob("node-pty-*")
    ] == ["node-pty-win32-x64"]
    assert [
        path.name
        for path in (package_root / "node_modules/tree-sitter-bash/prebuilds").iterdir()
        if path.is_dir()
    ] == ["win32-x64"]
    assert sorted(
        path.name
        for path in (package_root / "node_modules").glob("sqlite-vec-*")
        if path.is_dir()
    ) == ["sqlite-vec-windows-x64"]
    pi_tui_native = package_root / "node_modules/@earendil-works/pi-tui/native"
    assert sorted(path.name for path in pi_tui_native.iterdir() if path.is_dir()) == [
        "win32"
    ]
    assert sorted(
        path.name
        for path in (pi_tui_native / "win32/prebuilds").iterdir()
        if path.is_dir()
    ) == ["win32-x64"]

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

    # ``gateway --help`` never initializes an agent workspace and therefore
    # did not catch missing templates.  Exercise the pinned public CLI against
    # a clean, credential-free state directory and require all seven bootstrap
    # files to be materialized from the staged package.
    state = tmp_path / "openclaw-state"
    workspace = state / "workspace"
    env = os.environ.copy()
    for name in (
        "OPENAI_API_KEY",
        "OPENCLAW_GATEWAY_TOKEN",
        "CODEX_HOME",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
    ):
        env.pop(name, None)
    env.update(
        {
            "OPENCLAW_STATE_DIR": str(state),
            "OPENCLAW_HOME": str(state),
            "OPENCLAW_CONFIG_PATH": str(state / "openclaw.json"),
            "HOME": str(state),
            "USERPROFILE": str(state),
        }
    )
    bootstrap = subprocess.run(
        [
            node,
            str(package_root / "openclaw.mjs"),
            "agents",
            "add",
            "packaged-template-smoke",
            "--non-interactive",
            "--workspace",
            str(workspace),
            "--json",
        ],
        cwd=output_root,
        env=env,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=180,
    )
    assert bootstrap.returncode == 0, (
        f"staged workspace bootstrap failed:\n{bootstrap.stdout}\n{bootstrap.stderr}"
    )
    assert all((workspace / name).is_file() for name in runtime_templates)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path safety")
def test_stage_rejects_repo_prefix_sibling_as_recursive_output(tmp_path):
    sibling = _REPO_ROOT.parent / f"{_REPO_ROOT.name}-evil-{tmp_path.name}"
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_REPO_ROOT / "scripts/stage-openclaw-runtime.ps1"),
            "-OutputRoot",
            str(sibling),
        ],
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "true child of the repo root" in (result.stdout + result.stderr)
    assert not sibling.exists()
