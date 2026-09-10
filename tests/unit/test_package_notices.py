from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _module():
    script = Path(__file__).resolve().parents[2] / "scripts/stage-package-notices.py"
    spec = importlib.util.spec_from_file_location("stage_package_notices", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_notice_dependency_closure_excludes_extras_and_build_only_dependencies(
    monkeypatch,
):
    module = _module()
    requirements = {
        "dicom-overlay-agent": ["runtime", "dev-only; extra == 'dev'"],
        "runtime": ["transitive", "runtime"],
        "transitive": [],
        "pyinstaller": ["build-only"],
    }

    def distribution(name):
        return SimpleNamespace(metadata={"Name": name}, requires=requirements[name])

    monkeypatch.setattr(module.metadata, "distribution", distribution)
    assert [dist.metadata["Name"] for dist in module.runtime_distributions()] == [
        "pyinstaller",
        "runtime",
        "transitive",
    ]


def test_notice_copy_preserves_bytes_and_hash(tmp_path):
    module = _module()
    source = tmp_path / "LICENSE"
    source.write_bytes(b"upstream text\r\n")
    target = tmp_path / "build/notices"
    record = module._copy_notice(source, target, Path("runtime/LICENSE"), "1.0")
    assert (target / record["path"]).read_bytes() == source.read_bytes()
    assert record["bytes"] == 15
    assert record["version"] == "1.0"


def test_notice_copy_rejects_escape_and_empty_file(tmp_path):
    module = _module()
    source = tmp_path / "LICENSE"
    source.write_bytes(b"upstream")
    with pytest.raises(ValueError, match="escapes"):
        module._copy_notice(source, tmp_path / "output", Path("../outside/LICENSE"), "")
    assert not (tmp_path / "outside").exists()
    source.write_bytes(b"\n")
    with pytest.raises(ValueError, match="Empty"):
        module._copy_notice(source, tmp_path / "output", Path("LICENSE"), "")


@pytest.mark.parametrize("target", [".", "build", "src", "../outside"])
def test_notice_stage_rejects_non_build_child(tmp_path, target):
    module = _module()
    with pytest.raises(ValueError, match="child"):
        module.stage(tmp_path, tmp_path / target)


def test_node_fetch_preserves_license_checks_integrity_and_avoids_recursive_removal():
    script = (
        Path(__file__).resolve().parents[2] / "scripts/fetch-node.ps1"
    ).read_text()
    assert "SHASUMS256.txt" in script and "ComputeHash" in script
    assert "@('node.exe', 'LICENSE')" in script
    assert "ValidatePattern" in script and "ReparsePoint" in script
    assert "Remove-Item -LiteralPath $tmp -Recurse" not in script
