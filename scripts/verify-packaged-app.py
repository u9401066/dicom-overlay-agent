"""Verify a freshly built portable DICOM Overlay Agent bundle."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

MIB = 1024 * 1024
MAX_LAUNCHER_BYTES = 50 * MIB
MAX_APP_LAYER_BYTES = 100 * MIB
MAX_OPENCLAW_BYTES = 500 * MIB
MAX_TOTAL_BYTES = 650 * MIB
MIN_OPENCLAW_VERSION = (2026, 4, 22)
MIN_NODE_VERSION = (24, 15, 0)
EXPECTED_OPENCLAW_VERSION = "2026.7.1-2"
EXPECTED_NODE_VERSION = "v24.18.0"
PLUGIN_RUNTIME_INSPECT_TIMEOUT_SEC = 180

REQUIRED_FILES = (
    "DICOMOverlayAgent.exe",
    "config.yaml",
    "THIRD_PARTY_NOTICES.md",
    "node/node.exe",
    "openclaw/node_modules/openclaw/openclaw.mjs",
    "openclaw/node_modules/openclaw/package.json",
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
                    or has_banned_part_prefix
                    or folded_name in _BANNED_FILENAMES
                    or path.suffix.casefold() in _BANNED_MODEL_DATA_SUFFIXES
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
    component_counts = _component_counts(bundle)
    selfcheck = _run_selfcheck(exe) if run_selfcheck and exe.is_file() else None
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

    failures: list[str] = []
    if missing:
        failures.append(f"missing required files: {', '.join(missing)}")
    if banned:
        failures.append(
            f"banned or secret-like components present: {', '.join(banned[:10])}"
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
    for component, count in component_counts.items():
        if count == 0:
            failures.append(f"bundled OpenClaw component is empty: {component}")
    if selfcheck is not None and selfcheck["exit_code"] != 0:
        failures.append(f"packaged --selfcheck exited {selfcheck['exit_code']}")
    if openclaw_cli is not None and openclaw_cli["exit_code"] != 0:
        failures.append(
            f"bundled OpenClaw gateway CLI exited {openclaw_cli['exit_code']}"
        )
    if plugin_runtime is not None and not plugin_runtime.get("ok"):
        failures.append(
            "bundled native harness plugin failed runtime inspection: "
            + str(plugin_runtime.get("error") or "unknown error")
        )

    return {
        "status": "ok" if not failures else "failed",
        "bundle": str(bundle),
        "required_files": list(REQUIRED_FILES),
        "missing_files": missing,
        "banned_components": banned,
        "versions": {
            "openclaw": openclaw_version,
            "node": node_version,
        },
        "component_counts": component_counts,
        "sizes": {
            "file_count": file_count,
            "launcher_bytes": launcher_bytes,
            "app_layer_bytes": totals["app_layer"],
            "openclaw_bytes": totals["openclaw"],
            "node_bytes": totals["node"],
            "total_bytes": totals["total"],
        },
        "budgets": {
            "launcher_max_bytes": MAX_LAUNCHER_BYTES,
            "app_layer_max_bytes": MAX_APP_LAYER_BYTES,
            "openclaw_max_bytes": MAX_OPENCLAW_BYTES,
            "total_max_bytes": MAX_TOTAL_BYTES,
        },
        "selfcheck": selfcheck,
        "openclaw_cli_check": openclaw_cli,
        "native_plugin_runtime_check": plugin_runtime,
        "failures": failures,
    }


def _read_openclaw_version(bundle: Path) -> str:
    package = bundle / "openclaw" / "node_modules" / "openclaw" / "package.json"
    try:
        payload = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("version") or "")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _valid_harness_manifest(payload: dict[str, Any]) -> bool:
    capabilities = payload.get("capabilities")
    return bool(
        payload.get("name") == "dicom-overlay-agent-harness"
        and isinstance(capabilities, dict)
        and capabilities.get("medicalImageInterpretation") is True
        and capabilities.get("multiTurnImageFollowup") is True
        and capabilities.get("bboxCropReanalysis") is True
        and capabilities.get("coordinateDriftCalibration") is True
        and capabilities.get("ecgFounderWaveformAssist") is True
        and capabilities.get("noScreenshotToWaveformInference") is True
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
                        "defaults": {"model": {"primary": "openai/gpt-5.6-luna"}}
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
        try:
            payload = json.loads(process["stdout"])
        except json.JSONDecodeError:
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


def _read_version(command: list[str]) -> str:
    if not Path(command[0]).is_file():
        return ""
    try:
        result = subprocess.run(
            command,
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
            "stdout": result.stdout[-20_000:],
            "stderr": result.stderr[-20_000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"exit_code": -1, "stdout": "", "stderr": str(exc)}


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
