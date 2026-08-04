"""OpenClaw runtime compatibility helpers.

The desktop app deliberately talks to OpenClaw through the Gateway protocol
surface instead of importing plugin SDK internals.  This keeps the medical
image harness portable across OpenClaw releases while still enforcing a minimum
safe runtime version.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

MIN_SAFE_OPENCLAW_VERSION = "2026.4.22"
DEFAULT_OPENCLAW_NPM_SPEC = "openclaw@latest"
HARNESS_NAME = "dicom-overlay-agent-harness"


class OpenClawRuntimeError(RuntimeError):
    """Raised when the local OpenClaw runtime cannot be used safely."""


def read_installed_openclaw_version(repo_root: Path) -> str | None:
    """Read the installed repo-local OpenClaw package version, if present."""
    package_json = repo_root / "openclaw" / "node_modules" / "openclaw" / "package.json"
    if not package_json.exists():
        return None
    try:
        raw = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception as exc:
        raise OpenClawRuntimeError(
            f"Could not read OpenClaw package metadata: {package_json}"
        ) from exc
    version = raw.get("version")
    return version.strip() if isinstance(version, str) and version.strip() else None


def ensure_openclaw_runtime_supported(repo_root: Path) -> str:
    """Return installed version or raise if missing/older than the safety floor."""
    version = read_installed_openclaw_version(repo_root)
    if version is None:
        raise OpenClawRuntimeError(
            "OpenClaw is not installed locally. Run scripts\\install-openclaw-local.bat."
        )
    if not is_openclaw_version_supported(version):
        raise OpenClawRuntimeError(
            "Installed OpenClaw runtime is too old for this desktop app: "
            f"{version}. Install {MIN_SAFE_OPENCLAW_VERSION} or newer."
        )
    return version


def is_openclaw_version_supported(version: str) -> bool:
    """Check OpenClaw version against the minimum patched version boundary."""
    return _version_tuple(version) >= _version_tuple(MIN_SAFE_OPENCLAW_VERSION)


def build_harness_manifest() -> dict[str, Any]:
    """Build a plugin-like manifest for the image interpretation harness."""
    return {
        "name": HARNESS_NAME,
        "version": "1.1.0",
        "description": "Medical image co-reading harness for DICOM Overlay Agent.",
        "compatibility": {
            "minimumOpenClaw": MIN_SAFE_OPENCLAW_VERSION,
            "installDefault": DEFAULT_OPENCLAW_NPM_SPEC,
            "gatewayProtocol": {
                "minProtocol": 3,
                "maxProtocol": 4,
                "methods": ["connect", "chat.send"],
                "imageAttachment": {
                    "location": "params.attachments[]",
                    "requiredFields": ["type", "mimeType", "content"],
                    "mimeTypes": ["image/png"],
                },
            },
        },
        "capabilities": {
            "medicalImageInterpretation": True,
            "multiTurnImageFollowup": True,
            "bboxCropReanalysis": True,
            "coordinateDriftCalibration": True,
            "ecgFounderWaveformAssist": True,
            "externalWaveformSidecar": True,
            "noScreenshotToWaveformInference": True,
            "gatewayOnlyDesktopBoundary": True,
            "overlayAnnotations": ["bbox", "label", "tag", "text"],
            "triggerModes": ["hybrid", "manual", "auto"],
            "openClawTools": [
                "dicom_bbox_validate",
                "ecg_founder_analyze_waveform",
            ],
        },
    }


def build_openclaw_chat_frame(
    *,
    request_id: str,
    session_key: str,
    message: str,
    idempotency_key: str,
    image_base64: str | None = None,
) -> dict[str, Any]:
    """Build a Gateway ``chat.send`` request using the stable public schema."""
    params: dict[str, Any] = {
        "sessionKey": session_key,
        "message": message,
        "idempotencyKey": idempotency_key,
    }
    if image_base64 is not None:
        params["attachments"] = [
            {
                "type": "image",
                "mimeType": "image/png",
                "content": image_base64,
            }
        ]

    return {
        "type": "req",
        "id": request_id,
        "method": "chat.send",
        "params": params,
    }


def _version_tuple(version: str) -> tuple[int, int, int]:
    core = version.split("-", 1)[0]
    parts = [int(part) for part in re.findall(r"\d+", core)[:3]]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])
