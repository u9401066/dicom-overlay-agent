"""Run PyInstaller with an isolated DLL search path and audit native sources."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def isolated_environment(
    inherited: Mapping[str, str], *, executable: Path, base_prefix: Path
) -> dict[str, str]:
    """Keep process settings, but never search ambient application DLL folders."""
    excluded = {
        "PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QML2_IMPORT_PATH",
        "QML_IMPORT_PATH",
    }
    env = {
        key: value for key, value in inherited.items() if key.upper() not in excluded
    }
    system_root = next(
        (value for key, value in inherited.items() if key.upper() == "SYSTEMROOT"), ""
    )
    if not system_root or not Path(system_root).is_absolute():
        raise ValueError("An absolute Windows SystemRoot is required")
    directories = [
        executable.resolve().parent,
        base_prefix.resolve(),
        Path(system_root).resolve() / "System32",
        Path(system_root).resolve(),
    ]
    env["PATH"] = os.pathsep.join(dict.fromkeys(str(path) for path in directories))
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def inspect_native_sources(toc: Path, roots: Mapping[str, Path]) -> dict[str, object]:
    """Inspect data-only PyInstaller TOC; never evaluate executable Python."""
    parsed = ast.literal_eval(toc.read_text(encoding="utf-8"))
    allowed = [(label, root.resolve()) for label, root in roots.items()]
    records: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    def visit(value: object) -> None:
        if not isinstance(value, (tuple, list)):
            return
        if (
            len(value) == 3
            and all(isinstance(item, str) for item in value)
            and value[2] in {"BINARY", "EXTENSION"}
        ):
            name, source_text, kind = value
            source = Path(source_text).resolve(strict=True)
            if not source.is_file():
                raise ValueError(f"Native dependency is not a file: {name}")
            key = (name, str(source))
            if key in seen:
                return
            seen.add(key)
            for label, root in allowed:
                if source.is_relative_to(root):
                    records.append(
                        {
                            "destination": name,
                            "kind": kind,
                            "source_root": label,
                            "relative_source": source.relative_to(root).as_posix(),
                            "size_bytes": source.stat().st_size,
                            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        }
                    )
                    return
            raise ValueError(f"Unapproved native dependency source: {name}")
        for child in value:
            visit(child)

    visit(parsed)
    if not records:
        raise ValueError("Native dependency inventory is empty")
    return {
        "schema_version": 1,
        "status": "ok",
        "ambient_path_removed": True,
        "native_file_count": len(records),
        "files": sorted(records, key=lambda item: str(item["destination"])),
    }


def child_output(repo: Path, value: Path, *, prefix: str) -> Path:
    output = (repo / value).resolve()
    if output == repo or not output.is_relative_to(repo):
        raise ValueError("Build outputs must stay inside the repository")
    top = output.relative_to(repo).parts[0]
    if top != prefix and not top.startswith(prefix + "-"):
        raise ValueError(f"Build output must use a {prefix} or {prefix}-* directory")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distpath", type=Path, default=Path("dist"))
    parser.add_argument("--workpath", type=Path, default=Path("build"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    try:
        if platform.system() != "Windows" or platform.python_version() != "3.13.12":
            raise ValueError("Release packaging requires Windows Python 3.13.12")
        dist = child_output(repo, args.distpath, prefix="dist")
        work = child_output(repo, args.workpath, prefix="build")
        env = isolated_environment(
            os.environ,
            executable=Path(sys.executable),
            base_prefix=Path(sys.base_prefix),
        )
        mode = os.environ.get("DICOM_OVERLAY_UPX_ENABLED", "1")
        if mode not in {"0", "1"}:
            raise ValueError("DICOM_OVERLAY_UPX_ENABLED must be 0 or 1")
        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--distpath",
            str(dist),
            "--workpath",
            str(work),
        ]
        if mode == "1":
            upx = shutil.which("upx")
            if upx is None:
                raise ValueError(
                    "UPX requested but unavailable; use an explicit baseline receipt"
                )
            # Select only the compressor, never add its directory to DLL lookup.
            command.extend(["--upx-dir", str(Path(upx).resolve().parent)])
        command.append(str(repo / "dicom-overlay-agent.spec"))
        completed = subprocess.run(command, cwd=repo, env=env, check=False)
        if completed.returncode:
            return completed.returncode
        system_root = next(
            value for key, value in env.items() if key.upper() == "SYSTEMROOT"
        )
        receipt = inspect_native_sources(
            work / "dicom-overlay-agent/Analysis-00.toc",
            {
                "build_environment": Path(sys.prefix),
                "python_runtime": Path(sys.base_prefix),
                "staged_openclaw": repo / "build/openclaw-runtime",
                "portable_node": repo / "node",
                "windows_system": Path(system_root),
            },
        )
        target = dist / "DICOMOverlayAgent/native-dependency-receipt.json"
        target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(
            f"Native source audit: {receipt['native_file_count']} approved files; ambient PATH removed"
        )
        return 0
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
