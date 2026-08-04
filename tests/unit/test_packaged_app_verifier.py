from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "verify-packaged-app.py"
    spec = importlib.util.spec_from_file_location("verify_packaged_app", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_required_bundle(root: Path, module) -> None:
    for relative in module.REQUIRED_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"placeholder")
    package = root / "openclaw/node_modules/openclaw/package.json"
    package.write_text(json.dumps({"version": "2026.7.1-2"}), encoding="utf-8")
    manifest = (
        root / "openclaw/workspace/plugins/dicom-overlay-agent-harness/manifest.json"
    )
    manifest.write_text(
        json.dumps(
            {
                "name": "dicom-overlay-agent-harness",
                "capabilities": {
                    "medicalImageInterpretation": True,
                    "multiTurnImageFollowup": True,
                    "bboxCropReanalysis": True,
                    "coordinateDriftCalibration": True,
                    "ecgFounderWaveformAssist": True,
                    "noScreenshotToWaveformInference": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (manifest.parent / "openclaw.plugin.json").write_text(
        json.dumps(
            {
                "id": "dicom-overlay-agent-harness",
                "configSchema": {"type": "object"},
                "contracts": {
                    "tools": [
                        "dicom_bbox_validate",
                        "ecg_founder_analyze_waveform",
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    (manifest.parent / "package.json").write_text(
        json.dumps(
            {
                "type": "module",
                "openclaw": {"extensions": ["./index.js"]},
            }
        ),
        encoding="utf-8",
    )
    package_root = root / "openclaw/node_modules/openclaw"
    for relative in (
        "skills/healthcheck/SKILL.md",
        "dist/extensions/keep.js",
        "dist/plugins/keep.js",
        "dist/plugin-sdk/keep.js",
    ):
        path = package_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")


def test_inspect_bundle_reports_required_runtime_and_versions(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    monkeypatch.setattr(module, "_read_version", lambda _command: "v24.18.0")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "ok"
    assert report["missing_files"] == []
    assert report["banned_components"] == []
    assert report["versions"]["openclaw"] == "2026.7.1-2"


def test_inspect_bundle_rejects_missing_and_banned_components(tmp_path: Path) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    (tmp_path / "config.yaml").unlink()
    banned = tmp_path / "numpy" / "core.pyd"
    banned.parent.mkdir()
    banned.write_bytes(b"heavy")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert "config.yaml" in report["missing_files"]
    assert report["banned_components"] == ["numpy/core.pyd"]


def test_inspect_bundle_rejects_sidecar_runtime_and_model_artifacts(
    tmp_path: Path,
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    sidecar = tmp_path / "sidecars" / "ecgfounder" / "server.py"
    checkpoint = tmp_path / "openclaw" / "workspace" / "checkpoint.pth"
    waveform = tmp_path / "openclaw" / "workspace" / "waveform.mat"
    archived_dataset = tmp_path / "openclaw" / "workspace" / "meeti.tar"
    torch_metadata = tmp_path / "_internal" / "torch-2.9.dist-info" / "METADATA"
    for path in (sidecar, checkpoint, waveform, archived_dataset, torch_metadata):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"must remain external")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert set(report["banned_components"]) == {
        "sidecars/ecgfounder/server.py",
        "openclaw/workspace/checkpoint.pth",
        "openclaw/workspace/waveform.mat",
        "openclaw/workspace/meeti.tar",
        "_internal/torch-2.9.dist-info/METADATA",
    }


def test_inspect_bundle_rejects_environment_files(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    monkeypatch.setattr(module, "_read_version", lambda _command: "v24.18.0")
    environment_file = (
        tmp_path / "openclaw/node_modules/openclaw/node_modules/example/.env.production"
    )
    environment_file.parent.mkdir(parents=True)
    environment_file.write_text("API_KEY=must-not-ship\n", encoding="utf-8")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert (
        environment_file.relative_to(tmp_path).as_posix() in report["banned_components"]
    )
    assert "secret-like components" in " ".join(report["failures"])


def test_inspect_bundle_rejects_fresh_release_runtime_residue(tmp_path: Path) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    (tmp_path / "overlay_agent.log").write_text("local build path", encoding="utf-8")
    (tmp_path / "openclaw-home").mkdir()

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert report["runtime_residue"] == ["openclaw-home", "overlay_agent.log"]
    assert "runtime residue" in " ".join(report["failures"])


def test_inspect_bundle_excludes_its_generated_manifest_from_payload_size(
    tmp_path: Path,
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    first = module.inspect_bundle(tmp_path, run_selfcheck=False)
    (tmp_path / "bundle-manifest.json").write_text("{}", encoding="utf-8")

    second = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert second["sizes"] == first["sizes"]


def test_native_plugin_requires_bbox_validation_tool_contract(tmp_path: Path) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    manifest = (
        tmp_path
        / "openclaw/workspace/plugins/dicom-overlay-agent-harness/openclaw.plugin.json"
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["contracts"] = {"tools": []}
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert "native OpenClaw plugin metadata" in " ".join(report["failures"])


def test_packaged_plugin_runtime_inspection_has_bounded_cold_start_timeout() -> None:
    module = _load_module()

    assert module.PLUGIN_RUNTIME_INSPECT_TIMEOUT_SEC == 180
