from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path

import pytest


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "verify-packaged-app.py"
    spec = importlib.util.spec_from_file_location("verify_packaged_app", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_build_receipt_module():
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "write-package-build-receipt.py"
    )
    spec = importlib.util.spec_from_file_location("write_package_build_receipt", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_required_bundle(root: Path, module) -> str:
    for relative in module.REQUIRED_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"placeholder")
    clinical_root = root / "clinical_knowledge"
    source_clinical = Path(__file__).resolve().parents[2] / "clinical_knowledge"
    for source in source_clinical.rglob("*"):
        if not source.is_file():
            continue
        target = clinical_root / source.relative_to(source_clinical)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    validator = module._load_tooling_script(
        "validate-clinical-knowledge.py", "fixture_clinical_validator"
    )
    sqlite_builder = module._load_tooling_script(
        "build-clinical-knowledge-sqlite.py", "fixture_clinical_sqlite"
    )
    registry = validator.load_registry(clinical_root)
    assert validator.validate_registry(registry, verify_repository_links=False) == []
    clinical_digest = validator.registry_digest(registry)
    human, agent = validator.render_views(registry)
    (clinical_root / "generated" / "human-catalogue.md").write_text(
        human, encoding="utf-8"
    )
    (clinical_root / "generated" / "agent-steps.md").write_text(
        agent, encoding="utf-8"
    )
    clinical_db = clinical_root / "clinical-knowledge.sqlite"
    clinical_db.unlink(missing_ok=True)
    sqlite_builder.build_quick_lookup_db(
        registry,
        clinical_db,
        registry_digest=clinical_digest,
    )
    (root / "package-build-receipt.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "release_python_pin": module.RELEASE_PYTHON,
                "platform": {
                    "system": "Windows",
                    "machine": "AMD64",
                    "architecture_bits": 64,
                },
                "toolchain": {
                    "python": module.RELEASE_PYTHON,
                    "python_implementation": "CPython",
                    "pyinstaller": "6.19.0",
                    "pillow": "12.1.1",
                    "pyqt6": "6.10.2",
                    "pyqt6_qt6": "6.10.2",
                    "pyqt6_sip": "13.10.0",
                },
                "compression": {
                    "mode": "no_upx_baseline",
                    "upx_available": False,
                    "upx_enabled": False,
                    "upx_version": "",
                },
            }
        ),
        encoding="utf-8",
    )
    package = root / "openclaw/node_modules/openclaw/package.json"
    package.write_text(json.dumps({"version": "2026.7.1-2"}), encoding="utf-8")
    manifest = (
        root / "openclaw/workspace/plugins/dicom-overlay-agent-harness/manifest.json"
    )
    manifest.write_text(
        json.dumps(
            {
                "name": "dicom-overlay-agent-harness",
                "compatibility": {
                    "gatewayProtocol": {
                        "minProtocol": 3,
                        "maxProtocol": 4,
                        "methods": ["connect", "chat.send"],
                    }
                },
                "capabilities": {
                    "medicalImageInterpretation": True,
                    "multiTurnImageFollowup": True,
                    "bboxCropReanalysis": True,
                    "coordinateDriftCalibration": True,
                    "imageTurnBoundBboxReceipts": True,
                    "ecgFounderWaveformAssist": True,
                    "noScreenshotToWaveformInference": True,
                    "gatewayHelloProtocolReceipt": True,
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
    codex_migration = package_root / "dist/extensions/codex"
    (codex_migration / "package.json").write_text(
        json.dumps({"name": "@openclaw/codex", "version": "2026.7.1-1"}),
        encoding="utf-8",
    )
    (codex_migration / "openclaw.plugin.json").write_text(
        json.dumps(
            {
                "id": "codex",
                "contracts": {"migrationProviders": ["codex"]},
            }
        ),
        encoding="utf-8",
    )
    (codex_migration / "migration-bundle.json").write_text(
        json.dumps(
            {
                "purpose": "oauth_migration_only",
                "codex_agent_runtime_dependencies_bundled": False,
            }
        ),
        encoding="utf-8",
    )
    for relative in (
        "skills/healthcheck/SKILL.md",
        "dist/extensions/keep.js",
        "dist/plugins/keep.js",
        "dist/plugin-sdk/keep.js",
    ):
        path = package_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")
    return clinical_digest


def test_inspect_bundle_reports_required_runtime_and_versions(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    clinical_digest = _write_required_bundle(tmp_path, module)
    monkeypatch.setattr(module, "_read_version", lambda _command, **_kwargs: "v24.18.0")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "ok"
    assert report["missing_files"] == []
    assert report["banned_components"] == []
    assert report["versions"]["openclaw"] == "2026.7.1-2"
    assert len(report["integrity"]["launcher_sha256"]) == 64
    assert len(report["integrity"]["payload_tree_sha256"]) == 64
    assert len(report["source_provenance"]["source_tree_sha256"]) == 64
    assert report["codex_migration_bundle_check"]["ok"] is True
    assert report["workspace_templates"]["ok"] is True
    assert report["workspace_templates"]["ready_count"] == 7
    clinical = report["clinical_knowledge"]
    assert clinical["ok"] is True
    assert clinical["registry_sha256"] == clinical_digest
    assert clinical["computed_registry_sha256"] == clinical_digest
    assert clinical["registry_digest_scope"] == "canonical-input-documents-v1"
    assert clinical["rule_count"] == 7
    assert clinical["db_schema_version"] == "1"
    assert clinical["canonical_schema_version"] == 1
    assert clinical["sqlite_quick_check"] == "ok"
    assert clinical["generated_view_digests"] == {
        "human": clinical_digest,
        "agent": clinical_digest,
    }
    assert clinical["error"] == ""
    assert report["package_build"]["ok"] is True
    assert report["package_build"]["toolchain"]["python"] == "3.13.12"
    assert report["package_build"]["compression"]["mode"] == "no_upx_baseline"
    assert report["component_counts"]["workspace_templates"] == 7
    assert (
        report["codex_migration_bundle_check"][
            "codex_agent_runtime_dependencies_bundled"
        ]
        is False
    )


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


def test_inspect_bundle_rejects_clinical_sqlite_view_digest_drift(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    monkeypatch.setattr(module, "_read_version", lambda _command, **_kwargs: "v24.18.0")
    human = tmp_path / "clinical_knowledge/generated/human-catalogue.md"
    human.write_text(
        f"# Generated\n\nRegistry SHA-256: `{'d' * 64}`\n",
        encoding="utf-8",
    )

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert report["clinical_knowledge"]["ok"] is False
    assert any("clinical knowledge" in failure for failure in report["failures"])


def test_inspect_bundle_recomputes_packaged_yaml_and_checks_every_sqlite_table(
    tmp_path: Path,
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    rules = tmp_path / "clinical_knowledge/rules/core.rule.yaml"
    rules.write_text(
        rules.read_text(encoding="utf-8").replace(
            "ST 段抬高所見與整體分流不一致",
            "ST 段抬高所見與整體分流需再次核對",
            1,
        ),
        encoding="utf-8",
    )

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert "does not match packaged canonical inputs" in report[
        "clinical_knowledge"
    ]["error"]

    _write_required_bundle(tmp_path, module)
    database = tmp_path / "clinical_knowledge/clinical-knowledge.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agent_steps SET instruction='tampered' "
            "WHERE rowid=(SELECT min(rowid) FROM agent_steps)"
        )
    report = module.inspect_bundle(tmp_path, run_selfcheck=False)
    assert report["status"] == "failed"
    assert "quick-lookup table diverged: agent_steps" in report[
        "clinical_knowledge"
    ]["error"]


def test_inspect_bundle_rejects_empty_or_wrong_version_clinical_schema(
    tmp_path: Path,
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    schema_path = tmp_path / "clinical_knowledge/schema/rule.schema.json"
    schema_path.write_text(
        json.dumps({"type": "object", "additionalProperties": False}),
        encoding="utf-8",
    )

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert "schema id/version mismatch" in report["clinical_knowledge"]["error"]

    _write_required_bundle(tmp_path, module)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["properties"]["schema_version"]["const"] = 2
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    report = module.inspect_bundle(tmp_path, run_selfcheck=False)
    assert report["status"] == "failed"
    assert "clinical rule schema version must be 1" in report[
        "clinical_knowledge"
    ]["error"]


def test_inspect_bundle_rejects_false_upx_or_wrong_architecture_receipt(
    tmp_path: Path,
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    receipt_path = tmp_path / "package-build-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["platform"]["architecture_bits"] = 32
    receipt["compression"] = {
        "mode": "upx_requested",
        "upx_available": True,
        "upx_enabled": True,
        "upx_version": "upx 4.2.4",
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    error = report["package_build"]["error"]
    assert "64-bit Windows Python" in error
    assert "no compressed PE payload was observed" in error


def test_inspect_bundle_accepts_upx_only_with_observed_app_pe_marker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    monkeypatch.setattr(module, "_read_version", lambda _command, **_kwargs: "v24.18.0")
    exe = tmp_path / "DICOMOverlayAgent.exe"
    exe.write_bytes(b"MZ" + b"\0" * 126 + b"UPX0" + b"\0" * 32 + b"UPX1")
    receipt_path = tmp_path / "package-build-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["compression"] = {
        "mode": "upx_requested",
        "upx_available": True,
        "upx_enabled": True,
        "upx_version": "upx 4.2.4",
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "ok"
    assert report["package_build"]["compression"][
        "observed_upx_payloads"
    ] == ["DICOMOverlayAgent.exe"]


def test_build_receipt_records_explicit_no_upx_baseline(monkeypatch) -> None:
    module = _load_build_receipt_module()
    monkeypatch.setattr(module.platform, "python_version", lambda: "3.13.12")
    monkeypatch.setattr(module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(module.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(module.struct, "calcsize", lambda _value: 8)
    monkeypatch.setattr(module.shutil, "which", lambda _value: None)
    monkeypatch.setattr(
        module,
        "_package_versions",
        lambda: {
            "pyinstaller": "6.19.0",
            "pillow": "12.1.1",
            "pyqt6": "6.10.2",
            "pyqt6_qt6": "6.10.2",
            "pyqt6_sip": "13.10.0",
        },
    )

    receipt = module.build_receipt(upx_enabled=False)

    assert receipt["platform"]["architecture_bits"] == 64
    assert receipt["toolchain"]["python"] == "3.13.12"
    assert receipt["compression"] == {
        "mode": "no_upx_baseline",
        "upx_available": False,
        "upx_enabled": False,
        "upx_version": "",
    }

    with pytest.raises(RuntimeError, match="no upx executable"):
        module.build_receipt(upx_enabled=True)


def test_inspect_bundle_rejects_dev_leaks_and_only_pillow_avif(
    tmp_path: Path,
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    banned_paths = (
        tmp_path / "rich/console.py",
        tmp_path / "pygments-2.19.2.dist-info/METADATA",
        tmp_path / "markdown_it/__init__.py",
        tmp_path / "mdurl/_decode.py",
        tmp_path / "PIL/AvifImagePlugin.py",
        tmp_path / "PIL/_avif.cp313-win_amd64.pyd",
    )
    allowed_paths = (
        tmp_path / "PIL/PngImagePlugin.py",
        tmp_path / "PIL/JpegImagePlugin.py",
        tmp_path / "PIL/_imagingft.cp313-win_amd64.pyd",
        tmp_path / "openclaw/node_modules/example/rich/index.js",
    )
    for path in (*banned_paths, *allowed_paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert set(report["banned_components"]) == {
        path.relative_to(tmp_path).as_posix() for path in banned_paths
    }
    assert all(
        path.relative_to(tmp_path).as_posix() not in report["banned_components"]
        for path in allowed_paths
    )


def test_inspect_bundle_rejects_missing_or_empty_openclaw_templates(
    tmp_path: Path,
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    missing_relative = module.OPENCLAW_WORKSPACE_TEMPLATE_FILES[0]
    empty_relative = module.OPENCLAW_WORKSPACE_TEMPLATE_FILES[1]
    (tmp_path / missing_relative).unlink()
    (tmp_path / empty_relative).write_bytes(b"")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert missing_relative in report["missing_files"]
    assert report["workspace_templates"]["ok"] is False
    assert report["workspace_templates"]["ready_count"] == 5
    assert "missing:" in report["workspace_templates"]["error"]
    assert "empty:" in report["workspace_templates"]["error"]
    assert "workspace templates" in " ".join(report["failures"])


def test_inspect_bundle_rejects_debug_build_and_foreign_native_payloads(
    tmp_path: Path,
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    runtime = tmp_path / "openclaw/node_modules/openclaw/node_modules"
    banned_paths = (
        runtime / "@lydell/node-pty-win32-x64/prebuilds/win32-x64/conpty.pdb",
        runtime / "tree-sitter-bash/src/parser.c",
        runtime / "tree-sitter-bash/src/tree_sitter/parser.h",
        runtime / "@lydell/node-pty-linux-x64/prebuilds/linux-x64/pty.node",
        runtime / "tree-sitter-bash/prebuilds/darwin-arm64/tree-sitter-bash.node",
        runtime / "sqlite-vec-darwin-arm64/vec0.dylib",
        runtime / "sqlite-vec-linux-x64/vec0.so",
        runtime
        / "@earendil-works/pi-tui/native/darwin/prebuilds/darwin-x64/darwin-modifiers.node",
        runtime
        / "@earendil-works/pi-tui/native/win32/prebuilds/win32-arm64/win32-console-mode.node",
    )
    for path in banned_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"build-only")
    allowed = runtime / "tree-sitter-bash/prebuilds/win32-x64/tree-sitter-bash.node"
    allowed.parent.mkdir(parents=True, exist_ok=True)
    allowed.write_bytes(b"runtime")
    allowed_sqlite = runtime / "sqlite-vec-windows-x64/vec0.dll"
    allowed_sqlite.parent.mkdir(parents=True, exist_ok=True)
    allowed_sqlite.write_bytes(b"runtime")
    allowed_pi_tui = (
        runtime
        / "@earendil-works/pi-tui/native/win32/prebuilds/win32-x64/win32-console-mode.node"
    )
    allowed_pi_tui.parent.mkdir(parents=True, exist_ok=True)
    allowed_pi_tui.write_bytes(b"runtime")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert set(report["banned_components"]) == {
        path.relative_to(tmp_path).as_posix() for path in banned_paths
    }
    assert allowed.relative_to(tmp_path).as_posix() not in report["banned_components"]
    assert (
        allowed_sqlite.relative_to(tmp_path).as_posix()
        not in report["banned_components"]
    )
    assert (
        allowed_pi_tui.relative_to(tmp_path).as_posix()
        not in report["banned_components"]
    )


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
    monkeypatch.setattr(module, "_read_version", lambda _command, **_kwargs: "v24.18.0")
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
    (tmp_path / "gateway.log").write_text("gateway runtime", encoding="utf-8")
    (tmp_path / "openclaw-home/state").mkdir(parents=True)
    export = tmp_path / "data/exports/review.png"
    export.parent.mkdir(parents=True)
    export.write_bytes(b"runtime export")
    openclaw = tmp_path / "openclaw"
    for name in ("openclaw.json", "openclaw.json.bak", "openclaw.json.last-good"):
        (openclaw / name).write_text("{}", encoding="utf-8")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert report["runtime_residue"] == [
        "data",
        "gateway.log",
        "openclaw-home",
        "openclaw/openclaw.json",
        "openclaw/openclaw.json.bak",
        "openclaw/openclaw.json.last-good",
        "overlay_agent.log",
    ]
    assert "runtime residue" in " ".join(report["failures"])


def test_inspect_bundle_allows_product_config_site_and_static_assets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    monkeypatch.setattr(module, "_read_version", lambda _command, **_kwargs: "v24.18.0")
    site = tmp_path / "site/index.html"
    site.parent.mkdir(parents=True)
    site.write_text("<title>DICOM Overlay Agent</title>", encoding="utf-8")
    static_asset = tmp_path / "assets/product-mark.svg"
    static_asset.parent.mkdir(parents=True)
    static_asset.write_text("<svg></svg>", encoding="utf-8")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["runtime_residue"] == []
    assert report["status"] == "ok"


def test_inspect_bundle_excludes_its_generated_manifest_from_payload_size(
    tmp_path: Path,
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    first = module.inspect_bundle(tmp_path, run_selfcheck=False)
    (tmp_path / "bundle-manifest.json").write_text("{}", encoding="utf-8")

    second = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert second["sizes"] == first["sizes"]
    assert second["integrity"] == first["integrity"]


def test_source_provenance_records_scoped_git_state(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    source = tmp_path / "src" / "dicom_overlay" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('packaged')\n", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text("provider: openai\n", encoding="utf-8")
    calls: list[tuple[list[str], Path | None]] = []

    def fake_read(command: list[str], *, cwd: Path | None = None) -> str:
        calls.append((command, cwd))
        return "abc123" if command[1:3] == ["rev-parse", "HEAD"] else ""

    monkeypatch.setattr(module, "_read_version", fake_read)

    report = module._source_provenance(tmp_path)

    assert report["git_commit"] == "abc123"
    assert report["git_dirty"] is False
    assert report["source_file_count"] == 2
    assert len(report["source_tree_sha256"]) == 64
    assert calls[0][1] == tmp_path
    assert calls[1][1] == tmp_path
    assert calls[1][0][:4] == ["git", "status", "--porcelain", "--"]


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


def test_inspect_bundle_fails_closed_on_packaged_runtime_smoke(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    monkeypatch.setattr(module, "_read_version", lambda _command, **_kwargs: "v24.18.0")
    monkeypatch.setattr(
        module,
        "_run_selfcheck",
        lambda _exe: {"exit_code": 0, "stdout": "", "stderr": ""},
    )
    monkeypatch.setattr(
        module,
        "_run_package_runtime_smoke",
        lambda _exe: {"exit_code": 7, "stdout": "", "stderr": "codec missing"},
    )
    monkeypatch.setattr(
        module,
        "_run_process",
        lambda *_args, **_kwargs: {"exit_code": 0, "stdout": "", "stderr": ""},
    )
    monkeypatch.setattr(module, "_inspect_native_plugin", lambda *_args: {"ok": True})
    monkeypatch.setattr(
        module,
        "_inspect_codex_migration_runtime",
        lambda *_args: {"ok": True},
    )

    report = module.inspect_bundle(tmp_path, run_selfcheck=True)

    assert report["status"] == "failed"
    assert report["package_runtime_smoke"]["exit_code"] == 7
    assert "packaged codec/logging/review smoke exited 7" in report["failures"]


def test_inspect_bundle_rejects_codex_agent_runtime_dependency(tmp_path: Path) -> None:
    module = _load_module()
    _write_required_bundle(tmp_path, module)
    runtime = (
        tmp_path
        / "openclaw/node_modules/openclaw/dist/extensions/codex/node_modules"
        / "@openai/codex/package.json"
    )
    runtime.parent.mkdir(parents=True)
    runtime.write_text("{}", encoding="utf-8")

    report = module.inspect_bundle(tmp_path, run_selfcheck=False)

    assert report["status"] == "failed"
    assert "OAuth-only Codex migration provider" in " ".join(report["failures"])
