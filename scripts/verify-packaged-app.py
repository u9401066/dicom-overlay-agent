"""Verify a freshly built portable DICOM Overlay Agent bundle."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import ModuleType

MIB = 1024 * 1024
MAX_LAUNCHER_BYTES = 50 * MIB
MAX_APP_LAYER_BYTES = 100 * MIB
MAX_OPENCLAW_BYTES = 500 * MIB
MAX_TOTAL_BYTES = 650 * MIB
MIN_OPENCLAW_VERSION = (2026, 4, 22)
MIN_NODE_VERSION = (24, 15, 0)
EXPECTED_OPENCLAW_VERSION = "2026.7.1-2"
EXPECTED_NODE_VERSION = "v24.18.0"
MIN_GATEWAY_PROTOCOL = 3
MAX_GATEWAY_PROTOCOL = 4
PLUGIN_RUNTIME_INSPECT_TIMEOUT_SEC = 180
PACKAGE_BUILD_RECEIPT_SCHEMA_VERSION = 1
RELEASE_PYTHON = "3.13.12"
CLINICAL_DB_SCHEMA_VERSION = "1"

OPENCLAW_WORKSPACE_TEMPLATE_FILES = (
    "openclaw/node_modules/openclaw/src/agents/templates/HEARTBEAT.md",
    "openclaw/node_modules/openclaw/docs/reference/templates/AGENTS.md",
    "openclaw/node_modules/openclaw/docs/reference/templates/SOUL.md",
    "openclaw/node_modules/openclaw/docs/reference/templates/TOOLS.md",
    "openclaw/node_modules/openclaw/docs/reference/templates/IDENTITY.md",
    "openclaw/node_modules/openclaw/docs/reference/templates/USER.md",
    "openclaw/node_modules/openclaw/docs/reference/templates/BOOTSTRAP.md",
)

BUILD_SOURCE_ROOTS = (
    "src/dicom_overlay",
    "openclaw/workspace",
    "clinical_rules",
    "clinical_knowledge",
    "scripts",
)
BUILD_SOURCE_FILES = (
    "config.yaml",
    "dicom-overlay-agent.spec",
    "openclaw/package.json",
    "openclaw/package-lock.json",
    "pyproject.toml",
    "THIRD_PARTY_NOTICES.md",
    "package-build-receipt.json",
    "uv.lock",
)

REQUIRED_FILES = (
    "DICOMOverlayAgent.exe",
    "config.yaml",
    "THIRD_PARTY_NOTICES.md",
    "node/node.exe",
    "openclaw/node_modules/openclaw/openclaw.mjs",
    "openclaw/node_modules/openclaw/package.json",
    "openclaw/node_modules/openclaw/dist/extensions/codex/dist/index.js",
    "openclaw/node_modules/openclaw/dist/extensions/codex/package.json",
    "openclaw/node_modules/openclaw/dist/extensions/codex/openclaw.plugin.json",
    "openclaw/node_modules/openclaw/dist/extensions/codex/migration-bundle.json",
    *OPENCLAW_WORKSPACE_TEMPLATE_FILES,
    "openclaw/workspace/plugins/dicom-overlay-agent-harness/manifest.json",
    "openclaw/workspace/plugins/dicom-overlay-agent-harness/openclaw.plugin.json",
    "openclaw/workspace/plugins/dicom-overlay-agent-harness/package.json",
    "openclaw/workspace/plugins/dicom-overlay-agent-harness/index.js",
    "openclaw/workspace/skills/dicom-ekg-analysis/SKILL.md",
    "openclaw/workspace/skills/dicom-ekg-analysis/schema.json",
    "openclaw/workspace/skills/dicom-cxr-analysis/SKILL.md",
    "openclaw/workspace/skills/dicom-cxr-analysis/schema.json",
    "openclaw/workspace/skills/dicom-ct-brain-analysis/SKILL.md",
    "openclaw/workspace/skills/dicom-ct-brain-analysis/schema.json",
    "clinical_rules/ekg-cxr.rules.yaml.example",
    "clinical_knowledge/README.md",
    "clinical_knowledge/legacy-inventory.yaml",
    "clinical_knowledge/axes/ekg.axes.yaml",
    "clinical_knowledge/axes/cxr.axes.yaml",
    "clinical_knowledge/rules/core.rule.yaml",
    "clinical_knowledge/schema/rule.schema.json",
    "clinical_knowledge/generated/human-catalogue.md",
    "clinical_knowledge/generated/agent-steps.md",
    "clinical_knowledge/clinical-knowledge.sqlite",
)

_BANNED_PARTS = {
    "numpy",
    "scipy",
    "matplotlib",
    "pandas",
    "imagehash",
    "torch",
    "torchvision",
    "torchaudio",
    "sidecars",
    "meeti",
}
_BANNED_APP_LAYER_PACKAGES = {
    "markdown_it",
    "mdurl",
    "pygments",
    "rich",
}
_BANNED_PART_PREFIXES = (
    "meeti-",
    "numpy-",
    "numpy.",
    "scipy-",
    "scipy.",
    "torch-",
    "torch_",
)
_BANNED_FILENAMES = {"opengl32sw.dll"}
_BANNED_DEBUG_SYMBOL_SUFFIXES = {".pdb"}
_BANNED_MODEL_DATA_SUFFIXES = {
    ".mat",
    ".bin",
    ".ckpt",
    ".joblib",
    ".npy",
    ".npz",
    ".onnx",
    ".pt",
    ".pth",
    ".pickle",
    ".pkl",
    ".safetensors",
}
_BANNED_WORKSPACE_ARCHIVE_SUFFIXES = {".7z", ".gz", ".tar", ".zip"}
_BANNED_ENV_FILENAMES = {".env"}
_BANNED_ENV_PREFIXES = (".env.",)
_BANNED_QT_PREFIXES = (
    "qt6pdf",
    "qt6qml",
    "qt6quick",
    "qt6webengine",
    "qt6multimedia",
)


def inspect_bundle(bundle: Path, *, run_selfcheck: bool = True) -> dict[str, Any]:
    """Return a structured completeness and size report for ``bundle``."""
    bundle = bundle.resolve()
    missing = [
        relative for relative in REQUIRED_FILES if not (bundle / relative).is_file()
    ]
    totals = {"total": 0, "openclaw": 0, "node": 0, "app_layer": 0}
    file_count = 0
    banned: list[str] = []

    if bundle.is_dir():
        for dir_path, _, filenames in os.walk(bundle):
            parent = Path(dir_path)
            for filename in filenames:
                path = parent / filename
                relative = path.relative_to(bundle)
                if relative.as_posix() == "bundle-manifest.json":
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                file_count += 1
                totals["total"] += size
                top = relative.parts[0].casefold() if relative.parts else ""
                bucket = top if top in {"openclaw", "node"} else "app_layer"
                totals[bucket] += size

                folded_parts = {part.casefold() for part in relative.parts}
                folded_name = filename.casefold()
                has_banned_part_prefix = any(
                    part.startswith(_BANNED_PART_PREFIXES) for part in folded_parts
                )
                in_openclaw_workspace = tuple(
                    part.casefold() for part in relative.parts[:2]
                ) == ("openclaw", "workspace")
                if (
                    folded_parts & _BANNED_PARTS
                    or _is_dev_dependency_leak(relative)
                    or _is_pillow_avif_payload(relative)
                    or has_banned_part_prefix
                    or folded_name in _BANNED_FILENAMES
                    or path.suffix.casefold() in _BANNED_DEBUG_SYMBOL_SUFFIXES
                    or path.suffix.casefold() in _BANNED_MODEL_DATA_SUFFIXES
                    or _is_tree_sitter_bash_build_source(relative)
                    or _is_foreign_native_payload(relative)
                    or (
                        in_openclaw_workspace
                        and path.suffix.casefold() in _BANNED_WORKSPACE_ARCHIVE_SUFFIXES
                    )
                    or folded_name in _BANNED_ENV_FILENAMES
                    or folded_name.startswith(_BANNED_ENV_PREFIXES)
                    or folded_name.startswith(_BANNED_QT_PREFIXES)
                ) and len(banned) < 100:
                    banned.append(relative.as_posix())

    exe = bundle / "DICOMOverlayAgent.exe"
    launcher_bytes = exe.stat().st_size if exe.is_file() else 0
    openclaw_version = _read_openclaw_version(bundle)
    node_version = _read_version([str(bundle / "node" / "node.exe"), "--version"])
    harness_manifest = _read_json(
        bundle
        / "openclaw"
        / "workspace"
        / "plugins"
        / "dicom-overlay-agent-harness"
        / "manifest.json"
    )
    harness_root = (
        bundle / "openclaw" / "workspace" / "plugins" / "dicom-overlay-agent-harness"
    )
    native_plugin_manifest = _read_json(harness_root / "openclaw.plugin.json")
    native_plugin_package = _read_json(harness_root / "package.json")
    codex_migration_root = (
        bundle
        / "openclaw"
        / "node_modules"
        / "openclaw"
        / "dist"
        / "extensions"
        / "codex"
    )
    codex_migration_bundle = _inspect_codex_migration_bundle(codex_migration_root)
    workspace_templates = _inspect_workspace_templates(bundle)
    clinical_knowledge = _inspect_clinical_knowledge(bundle)
    package_build = _inspect_package_build(bundle)
    component_counts = _component_counts(bundle)
    selfcheck = _run_selfcheck(exe) if run_selfcheck and exe.is_file() else None
    package_runtime_smoke = (
        _run_package_runtime_smoke(exe)
        if run_selfcheck and exe.is_file()
        else None
    )
    openclaw_cli = (
        _run_process(
            [
                str(bundle / "node" / "node.exe"),
                str(bundle / "openclaw" / "node_modules" / "openclaw" / "openclaw.mjs"),
                "gateway",
                "--help",
            ],
            timeout=60,
        )
        if run_selfcheck
        and (bundle / "node" / "node.exe").is_file()
        and (
            bundle / "openclaw" / "node_modules" / "openclaw" / "openclaw.mjs"
        ).is_file()
        else None
    )
    plugin_runtime = (
        _inspect_native_plugin(bundle, harness_root)
        if run_selfcheck
        and (bundle / "node" / "node.exe").is_file()
        and (
            bundle / "openclaw" / "node_modules" / "openclaw" / "openclaw.mjs"
        ).is_file()
        else None
    )
    codex_migration_runtime = (
        _inspect_codex_migration_runtime(bundle)
        if run_selfcheck
        and (bundle / "node" / "node.exe").is_file()
        and (
            bundle / "openclaw" / "node_modules" / "openclaw" / "openclaw.mjs"
        ).is_file()
        else None
    )
    runtime_residue = _find_runtime_residue(bundle)

    failures: list[str] = []
    if missing:
        failures.append(f"missing required files: {', '.join(missing)}")
    if banned:
        failures.append(
            f"banned or secret-like components present: {', '.join(banned[:10])}"
        )
    if runtime_residue:
        failures.append(
            "fresh bundle contains runtime residue: " + ", ".join(runtime_residue)
        )
    if launcher_bytes >= MAX_LAUNCHER_BYTES:
        failures.append("launcher exceeds 50 MiB budget")
    if totals["app_layer"] >= MAX_APP_LAYER_BYTES:
        failures.append("application/Python/Qt layer exceeds 100 MiB budget")
    if totals["openclaw"] >= MAX_OPENCLAW_BYTES:
        failures.append("OpenClaw runtime exceeds 500 MiB budget")
    if totals["total"] >= MAX_TOTAL_BYTES:
        failures.append("portable bundle exceeds 650 MiB budget")
    if not openclaw_version:
        failures.append("OpenClaw package version is unreadable")
    elif _version_tuple(openclaw_version) < MIN_OPENCLAW_VERSION:
        failures.append(
            f"OpenClaw {openclaw_version} is older than "
            f"{'.'.join(map(str, MIN_OPENCLAW_VERSION))}"
        )
    elif openclaw_version != EXPECTED_OPENCLAW_VERSION:
        failures.append(
            f"OpenClaw {openclaw_version} does not match tested release "
            f"{EXPECTED_OPENCLAW_VERSION}"
        )
    if not node_version:
        failures.append("bundled Node.js version is unreadable")
    elif _version_tuple(node_version) < MIN_NODE_VERSION:
        failures.append(
            f"Node.js {node_version} is older than "
            f"{'.'.join(map(str, MIN_NODE_VERSION))}"
        )
    elif node_version != EXPECTED_NODE_VERSION:
        failures.append(
            f"Node.js {node_version} does not match tested portable runtime "
            f"{EXPECTED_NODE_VERSION}"
        )
    if not _valid_harness_manifest(harness_manifest):
        failures.append("harness plugin manifest is unreadable or incomplete")
    if not _valid_native_plugin(native_plugin_manifest, native_plugin_package):
        failures.append("native OpenClaw plugin metadata is unreadable or incomplete")
    if not codex_migration_bundle.get("ok"):
        failures.append(
            "OAuth-only Codex migration provider is incomplete: "
            + str(codex_migration_bundle.get("error") or "unknown error")
        )
    if not workspace_templates.get("ok"):
        failures.append(
            "OpenClaw workspace templates are incomplete or empty: "
            + str(workspace_templates.get("error") or "unknown error")
        )
    if not clinical_knowledge.get("ok"):
        failures.append(
            "clinical knowledge registry/SQLite projection is incomplete: "
            + str(clinical_knowledge.get("error") or "unknown error")
        )
    if not package_build.get("ok"):
        failures.append(
            "package build/toolchain receipt is invalid: "
            + str(package_build.get("error") or "unknown error")
        )
    for component, count in component_counts.items():
        if count == 0:
            failures.append(f"bundled OpenClaw component is empty: {component}")
    if selfcheck is not None and selfcheck["exit_code"] != 0:
        failures.append(f"packaged --selfcheck exited {selfcheck['exit_code']}")
    if (
        package_runtime_smoke is not None
        and package_runtime_smoke["exit_code"] != 0
    ):
        failures.append(
            "packaged codec/logging/review smoke exited "
            f"{package_runtime_smoke['exit_code']}"
        )
    if openclaw_cli is not None and openclaw_cli["exit_code"] != 0:
        failures.append(
            f"bundled OpenClaw gateway CLI exited {openclaw_cli['exit_code']}"
        )
    if plugin_runtime is not None and not plugin_runtime.get("ok"):
        failures.append(
            "bundled native harness plugin failed runtime inspection: "
            + str(plugin_runtime.get("error") or "unknown error")
        )
    if codex_migration_runtime is not None and not codex_migration_runtime.get("ok"):
        failures.append(
            "bundled Codex migration provider failed runtime inspection: "
            + str(codex_migration_runtime.get("error") or "unknown error")
        )

    return {
        "status": "ok" if not failures else "failed",
        "bundle": str(bundle),
        "required_files": list(REQUIRED_FILES),
        "missing_files": missing,
        "banned_components": banned,
        "runtime_residue": runtime_residue,
        "versions": {
            "openclaw": openclaw_version,
            "node": node_version,
        },
        "component_counts": component_counts,
        "workspace_templates": workspace_templates,
        "clinical_knowledge": clinical_knowledge,
        "package_build": package_build,
        "sizes": {
            "file_count": file_count,
            "launcher_bytes": launcher_bytes,
            "app_layer_bytes": totals["app_layer"],
            "openclaw_bytes": totals["openclaw"],
            "node_bytes": totals["node"],
            "total_bytes": totals["total"],
        },
        "integrity": {
            "launcher_sha256": _sha256_file(exe),
            "payload_tree_sha256": _bundle_tree_sha256(bundle),
        },
        "source_provenance": _source_provenance(Path(__file__).resolve().parents[1]),
        "budgets": {
            "launcher_max_bytes": MAX_LAUNCHER_BYTES,
            "app_layer_max_bytes": MAX_APP_LAYER_BYTES,
            "openclaw_max_bytes": MAX_OPENCLAW_BYTES,
            "total_max_bytes": MAX_TOTAL_BYTES,
        },
        "selfcheck": selfcheck,
        "package_runtime_smoke": package_runtime_smoke,
        "openclaw_cli_check": openclaw_cli,
        "native_plugin_runtime_check": plugin_runtime,
        "codex_migration_bundle_check": codex_migration_bundle,
        "codex_migration_runtime_check": codex_migration_runtime,
        "failures": failures,
    }


def _read_openclaw_version(bundle: Path) -> str:
    package = bundle / "openclaw" / "node_modules" / "openclaw" / "package.json"
    try:
        payload = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("version") or "")


def _is_tree_sitter_bash_build_source(relative: Path) -> bool:
    """Return whether ``relative`` is generated C/header build input.

    The staged runtime retains tree-sitter-bash's precompiled win32-x64 module,
    queries, and JSON metadata.  Parser C sources are only needed when building
    that native module and cost roughly 9.5 MiB.
    """

    parts = tuple(part.casefold() for part in relative.parts)
    vendored_prefix = (
        "openclaw",
        "node_modules",
        "openclaw",
        "node_modules",
        "tree-sitter-bash",
        "src",
    )
    return parts[: len(vendored_prefix)] == vendored_prefix and (
        relative.suffix.casefold() in {".c", ".h"}
    )


def _is_dev_dependency_leak(relative: Path) -> bool:
    """Reject build/test presentation packages from the Python app layer."""

    parts = tuple(part.casefold() for part in relative.parts)
    if not parts or parts[0] in {"node", "openclaw"}:
        return False
    for part in parts:
        if part in _BANNED_APP_LAYER_PACKAGES:
            return True
        if any(
            part.startswith(f"{package}-") or part.startswith(f"{package}.")
            for package in _BANNED_APP_LAYER_PACKAGES
        ):
            return True
    return False


def _is_pillow_avif_payload(relative: Path) -> bool:
    """Reject only Pillow's unused AVIF plugin/native codec."""

    parts = tuple(part.casefold() for part in relative.parts)
    if "pil" not in parts:
        return False
    name = parts[-1] if parts else ""
    return name in {"avifimageplugin.py", "avifimageplugin.pyc", "_avif.pyd"} or (
        name.startswith("_avif.") and name.endswith(".pyd")
    )


def _is_foreign_native_payload(relative: Path) -> bool:
    """Reject npm native payloads that cannot run on Windows x64."""

    parts = tuple(part.casefold() for part in relative.parts)
    vendored_prefix = (
        "openclaw",
        "node_modules",
        "openclaw",
        "node_modules",
    )
    if parts[: len(vendored_prefix)] != vendored_prefix:
        return False
    package_parts = parts[len(vendored_prefix) :]
    if len(package_parts) >= 2 and package_parts[0] == "@napi-rs":
        package = package_parts[1]
        return package.startswith("canvas-") and package != "canvas-win32-x64-msvc"
    if len(package_parts) >= 2 and package_parts[0] == "@lydell":
        package = package_parts[1]
        return package.startswith("node-pty-") and package != "node-pty-win32-x64"
    if len(package_parts) >= 2 and package_parts[0] == "@mariozechner":
        package = package_parts[1]
        return (
            package.startswith("clipboard-") and package != "clipboard-win32-x64-msvc"
        )
    if package_parts and package_parts[0].startswith("sqlite-vec-"):
        return package_parts[0] != "sqlite-vec-windows-x64"
    pi_tui_native = ("@earendil-works", "pi-tui", "native")
    if tuple(package_parts[:3]) == pi_tui_native and len(package_parts) >= 4:
        if package_parts[3] != "win32":
            return True
        return bool(
            len(package_parts) >= 6
            and package_parts[4] == "prebuilds"
            and package_parts[5] != "win32-x64"
        )
    return bool(
        len(package_parts) >= 3
        and package_parts[0] == "tree-sitter-bash"
        and package_parts[1] == "prebuilds"
        and package_parts[2] != "win32-x64"
    )


def _find_runtime_residue(bundle: Path) -> list[str]:
    """Return mutable runtime paths that must not ship in a fresh bundle."""

    if not bundle.is_dir():
        return []

    residue = {
        path.name
        for path in bundle.iterdir()
        if path.is_file() and path.suffix.casefold() == ".log"
    }
    for relative in (
        "openclaw-home",
        "data",
        "openclaw/openclaw.json",
        "openclaw/openclaw.json.bak",
        "openclaw/openclaw.json.last-good",
    ):
        if (bundle / relative).exists():
            residue.add(relative)
    return sorted(residue)


def _inspect_workspace_templates(bundle: Path) -> dict[str, Any]:
    """Record the exact pinned OpenClaw templates available at runtime."""

    files: list[dict[str, Any]] = []
    errors: list[str] = []
    for relative in OPENCLAW_WORKSPACE_TEMPLATE_FILES:
        path = bundle / relative
        size_bytes = 0
        digest = ""
        try:
            content = path.read_bytes()
            size_bytes = len(content)
            digest = hashlib.sha256(content).hexdigest()
            if not content.decode("utf-8-sig").strip():
                errors.append(f"empty: {relative}")
        except FileNotFoundError:
            errors.append(f"missing: {relative}")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"unreadable: {relative} ({type(exc).__name__})")
        files.append(
            {
                "path": relative,
                "size_bytes": size_bytes,
                "sha256": digest,
            }
        )
    return {
        "ok": not errors,
        "expected_count": len(OPENCLAW_WORKSPACE_TEMPLATE_FILES),
        "ready_count": sum(
            1 for item in files if item["size_bytes"] > 0 and item["sha256"]
        ),
        "files": files,
        "error": "; ".join(errors),
    }


def _inspect_clinical_knowledge(bundle: Path) -> dict[str, Any]:
    """Rebuild the canonical model from packaged inputs and verify every table."""

    root = bundle / "clinical_knowledge"
    database = root / "clinical-knowledge.sqlite"
    human_view = root / "generated" / "human-catalogue.md"
    agent_view = root / "generated" / "agent-steps.md"
    errors: list[str] = []
    metadata: dict[str, str] = {}
    database_rule_count = 0
    quick_check = ""
    table_counts: dict[str, int] = {}
    computed_digest = ""
    digest_scope = ""
    schema_id = ""
    schema_version: object = None

    try:
        validator = _load_tooling_script(
            "validate-clinical-knowledge.py", "packaged_clinical_validator"
        )
        sqlite_builder = _load_tooling_script(
            "build-clinical-knowledge-sqlite.py", "packaged_clinical_sqlite"
        )
        registry = validator.load_registry(root)
        digest_scope = str(registry.get("registry_digest_scope") or "")
        registry_errors = validator.validate_registry(
            registry,
            verify_repository_links=False,
        )
        errors.extend(f"canonical registry: {error}" for error in registry_errors)
        if not registry_errors:
            computed_digest = str(validator.registry_digest(registry))
            errors.extend(
                sqlite_builder.verify_quick_lookup_db(
                    registry,
                    database,
                    registry_digest=computed_digest,
                )
            )
            expected_human, expected_agent = validator.render_views(registry)
        else:
            expected_human = expected_agent = ""
    except (
        AttributeError,
        ImportError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        errors.append(f"clinical tooling failed ({type(exc).__name__})")
        expected_human = expected_agent = ""

    try:
        uri = f"file:{database.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            database_rule_count = int(
                connection.execute("SELECT count(*) FROM rules").fetchone()[0]
            )
            quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            table_counts["metadata"] = int(
                connection.execute("SELECT count(*) FROM metadata").fetchone()[0]
            )
            if "sqlite_builder" in locals():
                for table in sqlite_builder._TABLE_COLUMNS:
                    table_counts[table] = int(
                        connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                    )
        finally:
            connection.close()
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        errors.append(f"SQLite unreadable ({type(exc).__name__})")

    digest = metadata.get("registry_sha256", "")
    declared_count = metadata.get("rule_count", "")
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        errors.append("SQLite registry digest is missing or invalid")
    if computed_digest and digest != computed_digest:
        errors.append("SQLite registry digest does not match packaged canonical inputs")
    if metadata.get("db_schema_version") != CLINICAL_DB_SCHEMA_VERSION:
        errors.append("SQLite clinical schema version mismatch")
    if digest_scope and metadata.get("registry_digest_scope") != digest_scope:
        errors.append("SQLite registry digest scope does not match canonical tooling")
    if quick_check != "ok":
        errors.append("SQLite quick_check did not return ok")
    if declared_count != str(database_rule_count) or database_rule_count <= 0:
        errors.append("SQLite rule count metadata does not match the rules table")

    view_digests: dict[str, str] = {}
    for name, path, expected_text in (
        ("human", human_view, expected_human),
        ("agent", agent_view, expected_agent),
    ):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{name} generated view unreadable ({type(exc).__name__})")
            continue
        match = re.search(r"Registry SHA-256: `([0-9a-f]{64})`", text)
        if match is None:
            errors.append(f"{name} generated view lacks registry digest")
        else:
            view_digests[name] = match.group(1)
        if expected_text and text != expected_text:
            errors.append(f"{name} generated view diverges from packaged canonical inputs")
    if digest and set(view_digests.values()) != {digest}:
        errors.append("generated view digest does not match SQLite")

    try:
        schema = json.loads(
            (root / "schema" / "rule.schema.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"clinical rule schema unreadable ({type(exc).__name__})")
        schema = None
    if not isinstance(schema, dict) or schema.get("additionalProperties") is not False:
        errors.append("clinical rule schema is not strict")
    if isinstance(schema, dict):
        schema_id = str(schema.get("$id") or "")
        schema_properties = schema.get("properties")
        version_node = (
            schema_properties.get("schema_version", {})
            if isinstance(schema_properties, dict)
            else {}
        )
        if isinstance(version_node, dict):
            schema_version = version_node.get("const")

    return {
        "ok": not errors,
        "registry_sha256": digest,
        "computed_registry_sha256": computed_digest,
        "registry_digest_scope": digest_scope,
        "rule_count": database_rule_count,
        "sqlite_table_counts": table_counts,
        "db_schema_version": metadata.get("db_schema_version", ""),
        "canonical_schema_id": schema_id,
        "canonical_schema_version": schema_version,
        "sqlite_quick_check": quick_check,
        "generated_view_digests": view_digests,
        "error": "; ".join(errors),
    }


def _load_tooling_script(filename: str, module_name: str) -> ModuleType:
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load packaging tool: {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inspect_package_build(bundle: Path) -> dict[str, Any]:
    """Validate exact build-toolchain identity and observable UPX evidence."""

    receipt = _read_json(bundle / "package-build-receipt.json")
    errors: list[str] = []
    platform_info = receipt.get("platform")
    toolchain = receipt.get("toolchain")
    compression = receipt.get("compression")
    if receipt.get("schema_version") != PACKAGE_BUILD_RECEIPT_SCHEMA_VERSION:
        errors.append("build receipt schema version mismatch")
    if receipt.get("release_python_pin") != RELEASE_PYTHON:
        errors.append("release Python pin mismatch")
    if not isinstance(platform_info, dict):
        errors.append("platform receipt is missing")
        platform_info = {}
    if (
        platform_info.get("system") != "Windows"
        or platform_info.get("architecture_bits") != 64
        or str(platform_info.get("machine") or "").casefold()
        not in {"amd64", "x86_64"}
    ):
        errors.append("package was not built with 64-bit Windows Python")
    required_tools = (
        "python",
        "python_implementation",
        "pyinstaller",
        "pillow",
        "pyqt6",
        "pyqt6_qt6",
        "pyqt6_sip",
    )
    if not isinstance(toolchain, dict):
        errors.append("toolchain receipt is missing")
        toolchain = {}
    elif any(not str(toolchain.get(key) or "").strip() for key in required_tools):
        errors.append("toolchain receipt has missing versions")
    if toolchain.get("python") != RELEASE_PYTHON:
        errors.append("build interpreter does not match the release Python pin")

    upx_payloads = _find_upx_payloads(bundle)
    if not isinstance(compression, dict):
        errors.append("compression receipt is missing")
        compression = {}
    mode = compression.get("mode")
    enabled = compression.get("upx_enabled")
    available = compression.get("upx_available")
    version = str(compression.get("upx_version") or "")
    if mode == "no_upx_baseline":
        if enabled is not False:
            errors.append("no-UPX baseline cannot enable UPX")
        if upx_payloads:
            errors.append("UPX payload observed despite no-UPX baseline receipt")
    elif mode == "upx_requested":
        if enabled is not True or available is not True or not version:
            errors.append("UPX request lacks tool/version evidence")
        if not upx_payloads:
            errors.append("UPX was requested but no compressed PE payload was observed")
    else:
        errors.append("compression mode must be upx_requested or no_upx_baseline")

    return {
        "ok": not errors,
        "schema_version": receipt.get("schema_version"),
        "release_python_pin": receipt.get("release_python_pin"),
        "platform": platform_info,
        "toolchain": toolchain,
        "compression": {
            **compression,
            "observed_upx_payload_count": len(upx_payloads),
            "observed_upx_payloads": upx_payloads,
        },
        "error": "; ".join(errors),
    }


def _find_upx_payloads(bundle: Path) -> list[str]:
    marked: list[str] = []
    if not bundle.is_dir():
        return marked
    for path in bundle.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in {
            ".exe",
            ".dll",
            ".pyd",
        }:
            continue
        relative = path.relative_to(bundle)
        if relative.parts and relative.parts[0].casefold() in {"node", "openclaw"}:
            continue
        try:
            with path.open("rb") as handle:
                header = handle.read(64 * 1024)
        except OSError:
            continue
        if b"UPX!" in header or (b"UPX0" in header and b"UPX1" in header):
            marked.append(relative.as_posix())
    return sorted(marked)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _bundle_tree_sha256(bundle: Path) -> str:
    if not bundle.is_dir():
        return ""
    digest = hashlib.sha256()
    paths = sorted(
        (
            path
            for path in bundle.rglob("*")
            if path.is_file() and path.name != "bundle-manifest.json"
        ),
        key=lambda path: path.relative_to(bundle).as_posix(),
    )
    for path in paths:
        relative = path.relative_to(bundle).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _source_provenance(repo_root: Path) -> dict[str, Any]:
    files: list[Path] = []
    for relative in BUILD_SOURCE_ROOTS:
        root = repo_root / relative
        if root.is_dir():
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix.casefold() not in {".pyc", ".pyo"}
            )
    files.extend(
        path
        for relative in BUILD_SOURCE_FILES
        if (path := repo_root / relative).is_file()
    )
    unique_files = sorted(
        set(files),
        key=lambda path: path.relative_to(repo_root).as_posix(),
    )
    digest = hashlib.sha256()
    for path in unique_files:
        relative = path.relative_to(repo_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\n")

    source_args = [*BUILD_SOURCE_ROOTS, *BUILD_SOURCE_FILES]
    commit = _read_version(["git", "rev-parse", "HEAD"], cwd=repo_root)
    status = _read_version(
        ["git", "status", "--porcelain", "--", *source_args],
        cwd=repo_root,
    )
    return {
        "git_commit": commit,
        "git_dirty": bool(status.strip()),
        "source_tree_sha256": digest.hexdigest(),
        "source_file_count": len(unique_files),
        "included_roots": list(BUILD_SOURCE_ROOTS),
        "included_files": list(BUILD_SOURCE_FILES),
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _valid_harness_manifest(payload: dict[str, Any]) -> bool:
    capabilities = payload.get("capabilities")
    compatibility = payload.get("compatibility")
    gateway = (
        compatibility.get("gatewayProtocol")
        if isinstance(compatibility, dict)
        else None
    )
    return bool(
        payload.get("name") == "dicom-overlay-agent-harness"
        and isinstance(capabilities, dict)
        and capabilities.get("medicalImageInterpretation") is True
        and capabilities.get("multiTurnImageFollowup") is True
        and capabilities.get("bboxCropReanalysis") is True
        and capabilities.get("coordinateDriftCalibration") is True
        and capabilities.get("imageTurnBoundBboxReceipts") is True
        and capabilities.get("ecgFounderWaveformAssist") is True
        and capabilities.get("noScreenshotToWaveformInference") is True
        and capabilities.get("gatewayHelloProtocolReceipt") is True
        and isinstance(gateway, dict)
        and gateway.get("minProtocol") == MIN_GATEWAY_PROTOCOL
        and gateway.get("maxProtocol") == MAX_GATEWAY_PROTOCOL
        and gateway.get("methods") == ["connect", "chat.send"]
    )


def _valid_native_plugin(manifest: dict[str, Any], package: dict[str, Any]) -> bool:
    openclaw = package.get("openclaw")
    extensions = openclaw.get("extensions") if isinstance(openclaw, dict) else None
    contracts = manifest.get("contracts")
    tools = contracts.get("tools") if isinstance(contracts, dict) else None
    return bool(
        manifest.get("id") == "dicom-overlay-agent-harness"
        and isinstance(manifest.get("configSchema"), dict)
        and isinstance(extensions, list)
        and "./index.js" in extensions
        and package.get("type") == "module"
        and isinstance(tools, list)
        and "dicom_bbox_validate" in tools
        and "ecg_founder_analyze_waveform" in tools
    )


def _inspect_codex_migration_bundle(root: Path) -> dict[str, Any]:
    package = _read_json(root / "package.json")
    manifest = _read_json(root / "openclaw.plugin.json")
    metadata = _read_json(root / "migration-bundle.json")
    contracts = manifest.get("contracts")
    migration_providers = (
        contracts.get("migrationProviders") if isinstance(contracts, dict) else None
    )
    runtime_dependency = root / "node_modules" / "@openai" / "codex"
    platform_binaries = list(root.glob("node_modules/@openai/codex-*/**/codex.exe"))
    size_bytes = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
    ok = bool(
        package.get("name") == "@openclaw/codex"
        and package.get("version") == "2026.7.1-1"
        and manifest.get("id") == "codex"
        and isinstance(migration_providers, list)
        and "codex" in migration_providers
        and metadata.get("purpose") == "oauth_migration_only"
        and metadata.get("codex_agent_runtime_dependencies_bundled") is False
        and (root / "dist" / "index.js").is_file()
        and not runtime_dependency.exists()
        and not platform_binaries
        and size_bytes < 32 * MIB
    )
    return {
        "ok": ok,
        "package": package.get("name"),
        "version": package.get("version"),
        "purpose": metadata.get("purpose"),
        "codex_agent_runtime_dependencies_bundled": metadata.get(
            "codex_agent_runtime_dependencies_bundled"
        ),
        "size_bytes": size_bytes,
        "platform_binary_count": len(platform_binaries),
        "error": ""
        if ok
        else "identity, migration contract, or runtime exclusion failed",
    }


def _inspect_codex_migration_runtime(bundle: Path) -> dict[str, Any]:
    """Confirm the OAuth migration provider is trusted as a bundled plugin."""
    with tempfile.TemporaryDirectory(prefix="codex-migration-verify-") as temp_text:
        temp = Path(temp_text)
        state = temp / "state"
        state.mkdir()
        config = temp / "openclaw.json"
        config.write_text(
            json.dumps(
                {
                    "plugins": {
                        "allow": ["codex"],
                        "entries": {"codex": {"enabled": True}},
                    }
                }
            ),
            encoding="utf-8",
        )
        process = _run_process(
            [
                str(bundle / "node" / "node.exe"),
                str(bundle / "openclaw" / "node_modules" / "openclaw" / "openclaw.mjs"),
                "plugins",
                "inspect",
                "codex",
                "--json",
            ],
            cwd=bundle,
            timeout=PLUGIN_RUNTIME_INSPECT_TIMEOUT_SEC,
            env={
                **os.environ,
                "OPENCLAW_STATE_DIR": str(state),
                "OPENCLAW_HOME": str(state),
                "OPENCLAW_CONFIG_PATH": str(config),
                "HOME": str(state),
                "USERPROFILE": str(state),
            },
        )
        if process["exit_code"] != 0:
            return {
                "ok": False,
                "exit_code": process["exit_code"],
                "error": process["stderr"] or process["stdout"],
            }
        payload = _parse_json_output(process["stdout"])
        if not payload:
            return {"ok": False, "error": "plugin inspect did not return JSON"}
        plugin = payload.get("plugin")
        ok = bool(
            isinstance(plugin, dict)
            and plugin.get("id") == "codex"
            and plugin.get("packageName") == "@openclaw/codex"
            and plugin.get("origin") == "bundled"
            and plugin.get("status") == "loaded"
            and "codex" in plugin.get("migrationProviderIds", [])
        )
        return {
            "ok": ok,
            "exit_code": process["exit_code"],
            "origin": plugin.get("origin") if isinstance(plugin, dict) else "",
            "status": plugin.get("status") if isinstance(plugin, dict) else "",
            "error": "" if ok else "provider was not loaded with bundled trust",
        }


def _inspect_native_plugin(bundle: Path, plugin_root: Path) -> dict[str, Any]:
    """Load the bundled plugin through the bundled OpenClaw runtime."""
    with tempfile.TemporaryDirectory(prefix="dicom-overlay-verify-") as temp_text:
        temp = Path(temp_text)
        state = temp / "state"
        state.mkdir()
        config = temp / "openclaw.json"
        config.write_text(
            json.dumps(
                {
                    "gateway": {"mode": "local"},
                    "agents": {
                        "defaults": {"model": {"primary": "openai/gpt-5.4-mini"}}
                    },
                    "plugins": {
                        "allow": ["dicom-overlay-agent-harness"],
                        "load": {"paths": [str(plugin_root.resolve())]},
                        "entries": {"dicom-overlay-agent-harness": {"enabled": True}},
                    },
                }
            ),
            encoding="utf-8",
        )
        env = {
            **os.environ,
            "OPENCLAW_STATE_DIR": str(state),
            "OPENCLAW_CONFIG_PATH": str(config),
            "DICOM_ECGFOUNDER_ENDPOINT": "http://127.0.0.1:9/v1/analyze",
            "DICOM_ECGFOUNDER_TOKEN": "packaged-plugin-inspection-only",
        }
        process = _run_process(
            [
                str(bundle / "node" / "node.exe"),
                str(bundle / "openclaw" / "node_modules" / "openclaw" / "openclaw.mjs"),
                "plugins",
                "inspect",
                "dicom-overlay-agent-harness",
                "--runtime",
                "--json",
            ],
            cwd=bundle,
            timeout=PLUGIN_RUNTIME_INSPECT_TIMEOUT_SEC,
            env=env,
        )
        if process["exit_code"] != 0:
            return {
                "ok": False,
                "exit_code": process["exit_code"],
                "error": process["stderr"] or process["stdout"],
            }
        payload = _parse_json_output(process["stdout"])
        if not payload:
            return {
                "ok": False,
                "exit_code": process["exit_code"],
                "error": "plugin inspect did not return JSON",
            }
        plugin = payload.get("plugin", {})
        tool_names = plugin.get("toolNames", []) if isinstance(plugin, dict) else []
        tools = payload.get("tools", [])
        runtime_names = {
            name
            for entry in tools
            if isinstance(entry, dict)
            for name in entry.get("names", [])
            if isinstance(name, str)
        }
        ok = bool(
            isinstance(plugin, dict)
            and plugin.get("status") == "loaded"
            and "dicom_bbox_validate" in tool_names
            and "dicom_bbox_validate" in runtime_names
            and "ecg_founder_analyze_waveform" in tool_names
            and "ecg_founder_analyze_waveform" in runtime_names
            and not payload.get("diagnostics")
        )
        return {
            "ok": ok,
            "exit_code": process["exit_code"],
            "status": plugin.get("status") if isinstance(plugin, dict) else "",
            "tool_names": tool_names,
            "runtime_tool_names": sorted(runtime_names),
            "diagnostics": payload.get("diagnostics", []),
            "error": "" if ok else "plugin/tool did not load cleanly",
        }


def _component_counts(bundle: Path) -> dict[str, int]:
    package = bundle / "openclaw" / "node_modules" / "openclaw"
    return {
        "workspace_templates": sum(
            1
            for relative in OPENCLAW_WORKSPACE_TEMPLATE_FILES
            if (bundle / relative).is_file()
        ),
        "bundled_skills": len(list((package / "skills").glob("*/SKILL.md"))),
        "dist_extensions": _file_count(package / "dist" / "extensions"),
        "dist_plugins": _file_count(package / "dist" / "plugins"),
        "dist_plugin_sdk": _file_count(package / "dist" / "plugin-sdk"),
    }


def _file_count(path: Path) -> int:
    return sum(1 for item in path.rglob("*") if item.is_file()) if path.is_dir() else 0


def _version_tuple(version: str) -> tuple[int, int, int]:
    parts = [int(part) for part in re.findall(r"\d+", version)[:3]]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def _read_version(command: list[str], *, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (result.stdout or result.stderr).strip()


def _run_selfcheck(exe: Path) -> dict[str, Any]:
    return _run_process([str(exe), "--selfcheck"], cwd=exe.parent, timeout=60)


def _run_package_runtime_smoke(exe: Path) -> dict[str, Any]:
    return _run_process(
        [str(exe), "--package-runtime-smoke"],
        cwd=exe.parent,
        timeout=60,
    )


def _run_process(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=env,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout[-100_000:],
            "stderr": result.stderr[-100_000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"exit_code": -1, "stdout": "", "stderr": str(exc)}


def _parse_json_output(value: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for offset, character in enumerate(value):
        if character != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(value[offset:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--skip-selfcheck", action="store_true")
    args = parser.parse_args()

    report = inspect_bundle(args.bundle, run_selfcheck=not args.skip_selfcheck)
    output = args.output or (args.bundle / "bundle-manifest.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    sizes = report["sizes"]
    print(f"Bundle status: {report['status']}")
    print(f"OpenClaw: {report['versions']['openclaw'] or '(missing)'}")
    print(f"Node.js: {report['versions']['node'] or '(missing)'}")
    print(
        "Sizes: "
        f"launcher={sizes['launcher_bytes'] / MIB:.2f} MiB, "
        f"app={sizes['app_layer_bytes'] / MIB:.2f} MiB, "
        f"openclaw={sizes['openclaw_bytes'] / MIB:.2f} MiB, "
        f"node={sizes['node_bytes'] / MIB:.2f} MiB, "
        f"total={sizes['total_bytes'] / MIB:.2f} MiB"
    )
    print(f"Manifest: {output}")
    for failure in report["failures"]:
        print(f"ERROR: {failure}", file=sys.stderr)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
