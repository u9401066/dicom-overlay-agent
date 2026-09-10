"""Credential-free public CLI preparation before OAuth-only provider relocation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/prepare-openclaw-runtime.ps1"


def test_package_preparation_precedes_provider_relocation():
    stage = (ROOT / "scripts/stage-codex-auth-migration-provider.ps1").read_text("utf-8")
    assert stage.index('"prepare-openclaw-runtime.ps1"') < stage.index("$destination =")
    preparation = SCRIPT.read_text("utf-8")
    assert '$startInfo.EnvironmentVariables.Clear()' in preparation
    assert '$startInfo.WorkingDirectory = $preparationState' in preparation
    assert '$startInfo.CreateNoWindow = $true' in preparation
    assert 'gateway --help' in preparation
    assert 'WaitForExit(60000)' in preparation
    assert 'node_modules\\openclaw\\scripts' not in preparation


@pytest.fixture
def source(tmp_path):
    if sys.platform != "win32":
        pytest.skip("Windows public package preparation helper")
    node = ROOT / "node/node.exe"
    node = str(node) if node.exists() else shutil.which("node")
    if not node:
        pytest.skip("Node.js not available")
    package = tmp_path / "openclaw/node_modules/openclaw"
    package.mkdir(parents=True)
    (tmp_path / "openclaw/package.json").write_text(
        json.dumps({"dependencies": {"openclaw": "2026.9.3"}}), encoding="utf-8")
    (package / "package.json").write_text(
        json.dumps({"name": "openclaw", "version": "2026.9.3", "type": "module"}), encoding="utf-8")
    (package / "openclaw.mjs").write_text("""
import fs from 'node:fs';
import path from 'node:path';
const forbidden = ['OPENAI_API_KEY', 'OPENCLAW_GATEWAY_TOKEN', 'CODEX_HOME',
                   'UNRELATED_SECRET', 'NODE_OPTIONS'];
fs.writeFileSync(path.join(process.env.OPENCLAW_STATE_DIR, 'probe.json'), JSON.stringify({
  args: process.argv.slice(2), cwd: process.cwd(),
  config: process.env.OPENCLAW_CONFIG_PATH,
  inherited: forbidden.filter(key => process.env[key] !== undefined),
}));
console.log('Run the WebSocket Gateway');
""", encoding="utf-8")
    return tmp_path, package, node


def invoke(source, *, explicit_node=True, env=None):
    repo, _package, node = source
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
            "-RepoRoot", str(repo)]
    if explicit_node:
        args.extend(["-NodeExecutable", node])
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=75, env=env)


def test_cli_preparation_does_not_inherit_credentials_or_state(source):
    repo, _package, _node = source
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "OPENCLAW_GATEWAY_TOKEN", "CODEX_HOME", "UNRELATED_SECRET"):
        env[key] = "synthetic-must-not-reach-child"
    env["NODE_OPTIONS"] = "--require nonexistent-synthetic-module"
    env["OPENCLAW_STATE_DIR"] = str(repo / "must-not-use-this-state")
    result = invoke(source, env=env)
    assert result.returncode == 0, result.stderr
    states = list((repo / "data/tmp").glob("openclaw-package-prepare-*"))
    assert len(states) == 1
    state = states[0]
    probe = json.loads((state / "probe.json").read_text("utf-8"))
    assert probe["args"] == ["gateway", "--help"]
    assert probe["inherited"] == []
    assert Path(probe["cwd"]) == state
    assert Path(probe["config"]) == state / "openclaw.json"
    receipt = json.loads((state / "receipt.json").read_text("utf-8-sig"))
    assert receipt["exit_code"] == 0 and receipt["expected_help_observed"] is True
    assert receipt["inherited_credentials"] is False
    assert not (repo / "must-not-use-this-state").exists()
    assert "synthetic-must-not-reach-child" not in result.stdout + result.stderr


def test_path_with_multiple_node_candidates_selects_one(source):
    _repo, _package, node = source
    env = os.environ.copy()
    env["PATH"] = str(Path(node).parent) + os.pathsep + env["PATH"]
    result = invoke(source, explicit_node=False, env=env)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("failure", ["wrong_version", "missing_entry", "nonzero_exit", "wrong_help"])
def test_package_preparation_fails_closed(source, failure):
    repo, package, _node = source
    if failure == "wrong_version":
        (package / "package.json").write_text(
            json.dumps({"name": "openclaw", "version": "2026.7.1-2"}), encoding="utf-8")
    elif failure == "missing_entry":
        (package / "openclaw.mjs").unlink()
    else:
        (package / "openclaw.mjs").write_text(
            "process.exit(7);" if failure == "nonzero_exit" else "console.log('wrong command');",
            encoding="utf-8")
    result = invoke(source)
    assert result.returncode != 0
    if failure in {"wrong_version", "missing_entry"}:
        assert not (repo / "data/tmp").exists()
    else:
        receipt_path = next((repo / "data/tmp").glob("*/receipt.json"))
        receipt = json.loads(receipt_path.read_text("utf-8-sig"))
        assert receipt["expected_help_observed"] is False
