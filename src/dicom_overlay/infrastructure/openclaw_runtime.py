"""OpenClaw runtime compatibility helpers.

The desktop app deliberately talks to OpenClaw through the Gateway protocol
surface instead of importing plugin SDK internals.  This keeps the medical
image harness portable across OpenClaw releases while still enforcing a minimum
safe runtime version.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pathlib import Path

MIN_SAFE_OPENCLAW_VERSION = "2026.4.22"
PINNED_OPENCLAW_VERSION = "2026.9.3"
DEFAULT_OPENCLAW_NPM_SPEC = "openclaw@latest"
HARNESS_NAME = "dicom-overlay-agent-harness"
MIN_GATEWAY_PROTOCOL = 3
MAX_GATEWAY_PROTOCOL = 4
_OPENCLAW_CALENDAR_VERSION = re.compile(
    r"^(?P<year>[1-9]\d{3})\."
    r"(?P<month>[1-9]|1[0-2])\."
    r"(?P<day>[1-9]|[12]\d|3[01])"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
)


class OpenClawRuntimeError(RuntimeError):
    """Raised when the local OpenClaw runtime cannot be used safely."""


def parse_gateway_hello(payload: object) -> tuple[int, str]:
    """Validate a public Gateway ``hello-ok`` payload and return its receipt.

    OpenClaw 2026.4.x negotiated protocol 3 while the pinned 2026.9.3
    runtime negotiates protocol 4.  Accept only a protocol that the client
    explicitly advertised; an arbitrary successful response is not proof that
    the configured listener is an OpenClaw Gateway.
    """

    if not isinstance(payload, dict) or payload.get("type") != "hello-ok":
        raise OpenClawRuntimeError("OpenClaw connect response is not hello-ok")
    protocol = payload.get("protocol")
    if (
        not isinstance(protocol, int)
        or isinstance(protocol, bool)
        or not MIN_GATEWAY_PROTOCOL <= protocol <= MAX_GATEWAY_PROTOCOL
    ):
        raise OpenClawRuntimeError(
            "OpenClaw negotiated an unsupported Gateway protocol"
        )
    server = payload.get("server")
    version = server.get("version") if isinstance(server, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise OpenClawRuntimeError(
            "OpenClaw hello-ok response is missing server.version"
        )
    version = version.strip()
    try:
        version_date = _calendar_version_tuple(version)
    except ValueError as exc:
        raise OpenClawRuntimeError(
            "OpenClaw hello-ok server.version is not a valid calendar version"
        ) from exc
    if version_date < _calendar_version_tuple(MIN_SAFE_OPENCLAW_VERSION):
        raise OpenClawRuntimeError(
            "OpenClaw hello-ok server.version is below the minimum safe runtime: "
            f"{version} < {MIN_SAFE_OPENCLAW_VERSION}"
        )
    # Upgrading the pin must not erase already verified protocol-4 requirements.
    if (
        version in {"2026.7.1-2", PINNED_OPENCLAW_VERSION}
        and protocol != MAX_GATEWAY_PROTOCOL
    ):
        raise OpenClawRuntimeError(
            f"OpenClaw {version} must negotiate Gateway protocol {MAX_GATEWAY_PROTOCOL}"
        )
    return protocol, version


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
    try:
        return _calendar_version_tuple(version) >= _calendar_version_tuple(
            MIN_SAFE_OPENCLAW_VERSION
        )
    except (TypeError, ValueError):
        return False


def build_harness_manifest() -> dict[str, Any]:
    """Build a plugin-like manifest for the image interpretation harness."""
    return {
        "name": HARNESS_NAME,
        "version": "1.5.8",
        "description": "Medical image co-reading harness for DICOM Overlay Agent.",
        "compatibility": {
            "minimumOpenClaw": MIN_SAFE_OPENCLAW_VERSION,
            "installDefault": DEFAULT_OPENCLAW_NPM_SPEC,
            "gatewayProtocol": {
                "minProtocol": MIN_GATEWAY_PROTOCOL,
                "maxProtocol": MAX_GATEWAY_PROTOCOL,
                "methods": ["connect", "chat.send"],
                "chatSendParameters": ["fastMode"],
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
            "imageTurnBoundBboxReceipts": True,
            "ecgFounderWaveformAssist": True,
            "externalWaveformSidecar": True,
            "noScreenshotToWaveformInference": True,
            "gatewayOnlyDesktopBoundary": True,
            "gatewayHelloProtocolReceipt": True,
            "boundedAnalysisSla": {
                "initialResponseSeconds": 60,
                "firstCropRefinementSeconds": 100,
                "totalSeconds": 180,
                "finalizationRetryReserveSeconds": 80,
            },
            "compactCoarseTriage": True,
            "compactLeadOrderLayout": True,
            "nearMissRowPeakGeometryRecovery": True,
            "epsilonSafeCropProjection": True,
            "overlapAwareSystematicFallback": True,
            "finalTurnAfterCompletedRefinement": True,
            "boundedFinalizationRetryBudget": True,
            "explicitUnassessedChecklistFallback": True,
            "finalDispositionBoundBboxReceipt": True,
            "finalFindingRetainReviseRetract": True,
            "rejectedCoarseBboxRetraction": True,
            "objectShapedLayoutGeometry": True,
            "semanticUnlocalizedEkgRouting": True,
            "geometryDeduplicatedSystematicProbes": True,
            "systematicHypothesisReconciliation": True,
            "unlocalizedActionableGroundingGuard": True,
            "unavailableRhythmRegionReconciliation": True,
            "boxedInfoUncertaintyGuard": True,
            "preFinalTightEkgBboxGuard": True,
            "benignVariantRetractionContract": True,
            "timeCriticalStElevationTriageContract": True,
            "boundedRhythmStripRefinement": True,
            "endToEndRhythmSlaReceipt": True,
            "preRefinementCoordinateNormalization": True,
            "deterministicRowStripDetection": True,
            "imageCorroboratedLayoutRecovery": True,
            "explicitRowStripDetectorInjection": True,
            "waveformAttentionCropRouting": True,
            "ekgContextualCropRouting": True,
            "partialCropRetractionGuard": True,
            "balancedWaveformCandidateVerification": True,
            "nonceIdempotentWaveformTool": True,
            "ineligibleWaveformImageFallback": True,
            "compactWaveformAgentPayload": True,
            "deterministicRhythmRegularityMeasurement": True,
            "waveformRhythmConflictGuard": True,
            "rhythmConflictFindingReconciliation": True,
            "nonUrgentDiscoveryUncertaintyContract": True,
            "negationAwareExperimentScoring": True,
            "uncertaintyAwareConceptDeduplication": True,
            "rawJsonRecoveryAudit": True,
            "perTurnFastModeRequest": True,
            "transportReceiptRequiredForServiceTierClaim": True,
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
    fast_mode: bool | Literal["auto"] | None = None,
    fast_auto_on_seconds: int | None = None,
) -> dict[str, Any]:
    """Build a Gateway ``chat.send`` request using the stable public schema."""
    if image_base64 is not None and (
        not isinstance(image_base64, str) or not image_base64.strip()
    ):
        raise ValueError("image_base64 must be a non-empty string when provided")
    if (
        fast_mode is not None
        and not isinstance(fast_mode, bool)
        and fast_mode != "auto"
    ):
        raise ValueError("fast_mode must be true, false, auto, or None")
    if fast_auto_on_seconds is not None:
        if fast_mode != "auto":
            raise ValueError("fast_auto_on_seconds requires fast_mode='auto'")
        if (
            not isinstance(fast_auto_on_seconds, int)
            or isinstance(fast_auto_on_seconds, bool)
            or fast_auto_on_seconds < 1
        ):
            raise ValueError("fast_auto_on_seconds must be an integer >= 1")
    params: dict[str, Any] = {
        "sessionKey": session_key,
        "message": message,
        "idempotencyKey": idempotency_key,
    }
    if fast_mode is not None:
        params["fastMode"] = fast_mode
    if fast_auto_on_seconds is not None:
        params["fastAutoOnSeconds"] = fast_auto_on_seconds
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


def _calendar_version_tuple(version: str) -> tuple[int, int, int]:
    """Parse an OpenClaw calendar version without accepting embedded digits."""

    if not isinstance(version, str):
        raise TypeError("OpenClaw version must be a string")
    match = _OPENCLAW_CALENDAR_VERSION.fullmatch(version.strip())
    if match is None:
        raise ValueError("invalid OpenClaw calendar version")
    year = int(match["year"])
    month = int(match["month"])
    day = int(match["day"])
    date(year, month, day)
    return (year, month, day)
