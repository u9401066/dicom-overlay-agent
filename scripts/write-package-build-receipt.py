"""Write a fail-closed, machine-readable Windows package build receipt."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import shutil
import struct
import subprocess
from pathlib import Path

RELEASE_PYTHON = "3.13.12"
RECEIPT_SCHEMA_VERSION = 1
_TOOLCHAIN_PACKAGES = {
    "pyinstaller": "PyInstaller",
    "pillow": "Pillow",
    "pyqt6": "PyQt6",
    "pyqt6_qt6": "PyQt6-Qt6",
    "pyqt6_sip": "PyQt6-sip",
}


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for key, distribution in _TOOLCHAIN_PACKAGES.items():
        versions[key] = importlib.metadata.version(distribution)
    return versions


def _upx_version(executable: str) -> str:
    try:
        result = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0].strip() if result.returncode == 0 and output else ""


def build_receipt(*, upx_enabled: bool) -> dict[str, object]:
    """Describe the exact interpreter/toolchain and honest compression mode."""

    python_version = platform.python_version()
    architecture_bits = struct.calcsize("P") * 8
    system = platform.system()
    machine = platform.machine()
    if python_version != RELEASE_PYTHON:
        raise RuntimeError(
            f"release build requires Python {RELEASE_PYTHON}, got {python_version}"
        )
    if system != "Windows" or architecture_bits != 64:
        raise RuntimeError(
            "release build requires 64-bit Windows Python "
            f"(got {system} {machine} {architecture_bits}-bit)"
        )

    upx_path = shutil.which("upx")
    if upx_enabled and upx_path is None:
        raise RuntimeError("UPX was enabled but no upx executable is available")
    upx_version = _upx_version(upx_path) if upx_path else ""
    if upx_enabled and not upx_version:
        raise RuntimeError("UPX was enabled but its version could not be read")

    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "release_python_pin": RELEASE_PYTHON,
        "platform": {
            "system": system,
            "machine": machine,
            "architecture_bits": architecture_bits,
        },
        "toolchain": {
            "python": python_version,
            "python_implementation": platform.python_implementation(),
            **_package_versions(),
        },
        "compression": {
            "mode": "upx_requested" if upx_enabled else "no_upx_baseline",
            "upx_available": upx_path is not None,
            "upx_enabled": upx_enabled,
            "upx_version": upx_version,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--upx-enabled", choices=("0", "1"), required=True)
    args = parser.parse_args()

    try:
        receipt = build_receipt(upx_enabled=args.upx_enabled == "1")
    except (RuntimeError, importlib.metadata.PackageNotFoundError) as exc:
        print(f"ERROR: {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Package build receipt: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
