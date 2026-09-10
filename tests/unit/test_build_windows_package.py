from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def build_module():
    script = Path(__file__).resolve().parents[2] / "scripts/build-windows-package.py"
    spec = importlib.util.spec_from_file_location("build_windows_package", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_environment_removes_ambient_dll_and_plugin_paths(build_module, tmp_path):
    inherited = {
        "Path": "TortoiseGit;MiKTeX",
        "PATH": "other-app",
        "SystemRoot": str(tmp_path / "Windows"),
        "PYTHONPATH": "foreign-python",
        "pythonhome": "foreign-home",
        "QT_PLUGIN_PATH": "foreign-qt",
        "QT_QPA_PLATFORM_PLUGIN_PATH": "foreign-platform",
        "QML2_IMPORT_PATH": "foreign-qml",
        "QML_IMPORT_PATH": "foreign-qml2",
        "TEMP": str(tmp_path),
        "DICOM_OVERLAY_UPX_ENABLED": "1",
    }
    env = build_module.isolated_environment(
        inherited,
        executable=tmp_path / "venv/Scripts/python.exe",
        base_prefix=tmp_path / "python",
    )
    assert env["PATH"].split(os.pathsep) == [
        str(tmp_path / "venv/Scripts"),
        str(tmp_path / "python"),
        str(tmp_path / "Windows/System32"),
        str(tmp_path / "Windows"),
    ]
    assert "Path" not in env
    assert not any(
        key.upper().startswith(("QT_", "QML", "PYTHONPATH", "PYTHONHOME"))
        for key in env
    )
    assert env["TEMP"] == str(tmp_path)
    assert env["DICOM_OVERLAY_UPX_ENABLED"] == "1"
    assert inherited["PATH"] == "other-app"


@pytest.mark.parametrize("system_root", ["", "relative"])
def test_environment_rejects_unresolved_windows_root(
    build_module, tmp_path, system_root
):
    with pytest.raises(ValueError, match="absolute Windows SystemRoot"):
        build_module.isolated_environment(
            {"SystemRoot": system_root},
            executable=tmp_path / "python.exe",
            base_prefix=tmp_path,
        )


def test_native_inventory_hashes_only_approved_roots(build_module, tmp_path):
    root = tmp_path / "venv"
    root.mkdir()
    source = root / "native.dll"
    source.write_bytes(b"native-fixture")
    toc = tmp_path / "Analysis-00.toc"
    native = ("native.dll", str(source), "BINARY")
    toc.write_text(
        repr(([native, native], [("module", "not-a-file", "PYMODULE")])),
        encoding="utf-8",
    )
    receipt = build_module.inspect_native_sources(toc, {"build_environment": root})
    assert receipt["status"] == "ok"
    assert receipt["native_file_count"] == 1
    record = receipt["files"][0]
    assert record["relative_source"] == "native.dll"
    assert record["source_root"] == "build_environment"
    assert len(record["sha256"]) == 64
    assert str(tmp_path) not in str(receipt)


def test_native_inventory_rejects_sibling_prefix_escape(build_module, tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    sibling = tmp_path / "approved-unrelated"
    sibling.mkdir()
    source = sibling / "dbghelp.dll"
    source.write_bytes(b"unapproved")
    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(repr([("dbghelp.dll", str(source), "BINARY")]), encoding="utf-8")
    with pytest.raises(ValueError, match="Unapproved native dependency"):
        build_module.inspect_native_sources(toc, {"build_environment": root})


@pytest.mark.parametrize("payload", ["[]", "__import__('os').getcwd()"])
def test_native_inventory_fails_closed_on_empty_or_code(
    build_module, tmp_path, payload
):
    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        build_module.inspect_native_sources(toc, {"build_environment": tmp_path})


def test_output_boundary_rejects_root_parent_and_accepts_child(build_module, tmp_path):
    with pytest.raises(ValueError):
        build_module.child_output(tmp_path, Path(), prefix="dist")
    with pytest.raises(ValueError):
        build_module.child_output(tmp_path, Path(".."), prefix="dist")
    assert (
        build_module.child_output(tmp_path, Path("dist-comparison"), prefix="dist")
        == tmp_path / "dist-comparison"
    )


@pytest.mark.parametrize(
    "value,prefix",
    [
        ("src", "dist"),
        ("openclaw", "build"),
        ("build-cache", "dist"),
        ("dist-output", "build"),
    ],
)
def test_outputs_cannot_replace_source_or_cross_roles(
    build_module, tmp_path, value, prefix
):
    with pytest.raises(ValueError, match="Build output must use"):
        build_module.child_output(tmp_path, Path(value), prefix=prefix)
