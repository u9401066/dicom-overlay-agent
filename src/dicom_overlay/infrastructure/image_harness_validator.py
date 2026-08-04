"""Artifact verifier for the image interpretation harness smoke test."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dicom_overlay.infrastructure.openclaw_runtime import MIN_SAFE_OPENCLAW_VERSION

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class HarnessVerification:
    """Codex/CI-readable verification report."""

    ok: bool
    passed_checks: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "passed_checks": self.passed_checks,
                "failures": self.failures,
            },
            indent=2,
        )


def verify_image_harness_artifacts(
    *,
    log_path: Path,
    result_path: Path,
    require_viewer: bool,
) -> HarnessVerification:
    """Verify that smoke artifacts prove the OpenClaw image harness contract."""
    failures: list[str] = []
    passed: list[str] = []

    log_text = _read_text(log_path, failures)
    result = _read_json(result_path, failures)

    if require_viewer and "viewer_displayed=True" not in log_text:
        failures.append("desktop_viewer: expected viewer_displayed=True in smoke log")
    elif "viewer_displayed=" in log_text:
        passed.append("desktop_viewer")

    if _gateway_contract_ok(log_text):
        passed.append("gateway_contract")
    else:
        failures.append(
            "gateway_contract: expected connect + chat.send with image attachment metadata"
        )

    if _image_payload_proof_ok(log_text):
        passed.append("image_payload_proof")
    else:
        failures.append(
            "image_payload_proof: missing redacted payload length/hash or found unredacted image content"
        )

    if isinstance(result, dict) and _overlay_annotation_contract_ok(result):
        passed.append("overlay_annotation_contract")
    else:
        failures.append(
            "overlay_annotation_contract: expected finding label/detail/regions and normalized bbox"
        )

    if isinstance(result, dict) and _manifest_contract_ok(result):
        passed.append("harness_manifest_contract")
    else:
        failures.append(
            "harness_manifest_contract: expected safe OpenClaw floor and Gateway method manifest"
        )

    return HarnessVerification(ok=not failures, passed_checks=passed, failures=failures)


def _read_text(path: Path, failures: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        failures.append(f"read_log: {exc}")
        return ""


def _read_json(path: Path, failures: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        failures.append(f"read_result: {exc}")
        return None


def _gateway_contract_ok(log_text: str) -> bool:
    return (
        '"method": "connect"' in log_text
        and '"method": "chat.send"' in log_text
        and '"attachments"' in log_text
        and '"mimeType": "image/png"' in log_text
    )


def _image_payload_proof_ok(log_text: str) -> bool:
    has_redaction = '"content": "<redacted>"' in log_text
    has_length = re.search(r'"contentLength":\s*[1-9]\d*', log_text) is not None
    has_hash = re.search(r'"contentSha256":\s*"[0-9a-f]{64}"', log_text) is not None
    has_unredacted_png = re.search(r'"content":\s*"iVBOR', log_text) is not None
    return has_redaction and has_length and has_hash and not has_unredacted_png


def _overlay_annotation_contract_ok(result: dict[str, Any]) -> bool:
    boundary_epsilon = 1e-9
    findings = result.get("findings")
    if not isinstance(findings, list) or not findings:
        return False
    for finding in findings:
        if not isinstance(finding, dict):
            return False
        if not all(
            isinstance(finding.get(key), str) and finding[key]
            for key in ("label", "detail")
        ):
            return False
        regions = finding.get("regions")
        if not isinstance(regions, list) or not all(
            isinstance(item, str) for item in regions
        ):
            return False
        bboxes = finding.get("bboxes")
        if not isinstance(bboxes, list) or not bboxes:
            return False
        for bbox in bboxes:
            if not isinstance(bbox, dict):
                return False
            if not all(_is_normalized_number(bbox.get(key)) for key in ("x", "y", "w", "h")):
                return False
            if not bool(
                bbox["x"] + bbox["w"] <= 1.0 + boundary_epsilon
                and bbox["y"] + bbox["h"] <= 1.0 + boundary_epsilon
            ):
                return False
    return True


def _is_normalized_number(value: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def _manifest_contract_ok(result: dict[str, Any]) -> bool:
    manifest = result.get("harness_manifest")
    if not isinstance(manifest, dict):
        return False
    compatibility = manifest.get("compatibility")
    if not isinstance(compatibility, dict):
        return False
    gateway = compatibility.get("gatewayProtocol")
    if not isinstance(gateway, dict):
        return False
    return (
        compatibility.get("minimumOpenClaw") == MIN_SAFE_OPENCLAW_VERSION
        and gateway.get("methods") == ["connect", "chat.send"]
    )
