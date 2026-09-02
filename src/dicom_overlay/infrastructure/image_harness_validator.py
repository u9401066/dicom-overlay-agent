"""Artifact verifier for the image interpretation harness smoke test."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dicom_overlay.domain.ekg_layout import parse_ekg_lead_inventory
from dicom_overlay.domain.modality_profile import default_registry
from dicom_overlay.infrastructure.hooks.output_validator import (
    EKG_RESULT_LAYOUT_FORMATS,
)
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
    gateway_frames = _extract_gateway_frames(log_text)

    if require_viewer and "viewer_displayed=True" not in log_text:
        failures.append("desktop_viewer: expected viewer_displayed=True in smoke log")
    elif "viewer_displayed=" in log_text:
        passed.append("desktop_viewer")

    if _gateway_contract_ok(gateway_frames):
        passed.append("gateway_contract")
    else:
        failures.append(
            "gateway_contract: expected connect + chat.send with image attachment metadata"
        )

    if _image_payload_proof_ok(gateway_frames):
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

    if isinstance(result, dict) and _production_output_contract_ok(result):
        passed.append("production_output_contract")
    else:
        failures.append(
            "production_output_contract: expected strict HookedVisionAnalyzer evidence, "
            "exact modality checklist, image_quality, and next_steps"
        )

    if isinstance(result, dict) and _roi_capture_contract_ok(result):
        passed.append("roi_capture_contract")
    else:
        failures.append(
            "roi_capture_contract: expected a positive, bounded, non-full-viewer ROI capture"
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


def _extract_gateway_frames(log_text: str) -> list[dict[str, Any]]:
    """Parse only JSON objects/arrays explicitly recorded as Gateway frames."""

    frames: list[dict[str, Any]] = []
    marker = "gateway_frames="
    marker_index = log_text.find(marker)
    if marker_index >= 0:
        payload = log_text[marker_index + len(marker) :].lstrip()
        try:
            decoded, _end = json.JSONDecoder().raw_decode(payload)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            frames.extend(item for item in decoded if isinstance(item, dict))
        elif isinstance(decoded, dict):
            frames.append(decoded)

    # JSONL is also accepted for hand-authored/legacy smoke artifacts. Each
    # required field must still coexist in one parsed frame/attachment object.
    if not frames:
        for line in log_text.splitlines():
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                frames.append(decoded)
            elif isinstance(decoded, list):
                frames.extend(item for item in decoded if isinstance(item, dict))
    return frames


def _gateway_contract_ok(frames: list[dict[str, Any]]) -> bool:
    connect = any(_is_gateway_request(frame, method="connect") for frame in frames)
    chat = any(_valid_image_chat_attachment(frame) is not None for frame in frames)
    return connect and chat


def _image_payload_proof_ok(frames: list[dict[str, Any]]) -> bool:
    for frame in frames:
        attachment = _valid_image_chat_attachment(frame)
        if attachment is None:
            continue
        content = attachment.get("content")
        content_length = attachment.get("contentLength")
        content_hash = attachment.get("contentSha256")
        if (
            content == "<redacted>"
            and isinstance(content_length, int)
            and not isinstance(content_length, bool)
            and content_length > 0
            and isinstance(content_hash, str)
            and re.fullmatch(r"[0-9a-f]{64}", content_hash) is not None
        ):
            return True
    return False


def _is_gateway_request(frame: dict[str, Any], *, method: str) -> bool:
    return bool(
        frame.get("type") == "req"
        and isinstance(frame.get("id"), str)
        and frame["id"].strip()
        and frame.get("method") == method
        and isinstance(frame.get("params"), dict)
    )


def _valid_image_chat_attachment(
    frame: dict[str, Any],
) -> dict[str, Any] | None:
    if not _is_gateway_request(frame, method="chat.send"):
        return None
    params = frame["params"]
    if not all(
        isinstance(params.get(key), str) and params[key].strip()
        for key in ("sessionKey", "message", "idempotencyKey")
    ):
        return None
    attachments = params.get("attachments")
    if not isinstance(attachments, list) or len(attachments) != 1:
        return None
    attachment = attachments[0]
    if not isinstance(attachment, dict):
        return None
    if (
        attachment.get("type") != "image"
        or attachment.get("mimeType") != "image/png"
        or not isinstance(attachment.get("content"), str)
        or not attachment["content"]
    ):
        return None
    return attachment


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
            if not all(
                _is_normalized_number(bbox.get(key)) for key in ("x", "y", "w", "h")
            ):
                return False
            if bbox["w"] <= 0.0 or bbox["h"] <= 0.0:
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
    return compatibility.get(
        "minimumOpenClaw"
    ) == MIN_SAFE_OPENCLAW_VERSION and gateway.get("methods") == [
        "connect",
        "chat.send",
    ]


def _production_output_contract_ok(result: dict[str, Any]) -> bool:
    evidence = result.get("output_contract")
    if not isinstance(evidence, dict) or evidence != {
        "analyzer": "HookedVisionAnalyzer",
        "validator": "OutputValidator",
        "strict": True,
    }:
        return False
    modality = result.get("modality")
    if not isinstance(modality, str) or not modality.strip():
        return False
    if modality == "EKG":
        layout = result.get("layout")
        if not isinstance(layout, dict):
            return False
        if str(layout.get("format") or "").strip() not in EKG_RESULT_LAYOUT_FORMATS:
            return False
        if not parse_ekg_lead_inventory(layout).complete:
            return False
    required = default_registry().resolve(modality).checklist_keys
    checklist = result.get("checklist")
    if not required or not isinstance(checklist, dict) or set(checklist) != required:
        return False
    for item in checklist.values():
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("value"), str) or not item["value"].strip():
            return False
        if item.get("status") not in {"critical", "warning", "normal", "info"}:
            return False
    image_quality = result.get("image_quality")
    if isinstance(image_quality, str):
        quality_ok = bool(image_quality.strip())
    elif isinstance(image_quality, dict):
        quality_ok = bool(image_quality)
    else:
        quality_ok = False
    next_steps = result.get("next_steps")
    incomplete = result.get("incomplete")
    incomplete_reasons = result.get("incomplete_reasons")
    return bool(
        quality_ok
        and isinstance(result.get("model_used"), str)
        and result["model_used"].strip()
        and isinstance(next_steps, list)
        and next_steps
        and all(isinstance(step, str) and step.strip() for step in next_steps)
        and isinstance(incomplete, bool)
        and isinstance(incomplete_reasons, list)
        and all(
            isinstance(reason, str) and reason.strip() for reason in incomplete_reasons
        )
    )


def _roi_capture_contract_ok(result: dict[str, Any]) -> bool:
    proof = result.get("capture_contract")
    if not isinstance(proof, dict):
        return False
    viewer = proof.get("viewer_rect")
    capture = proof.get("capture_rect")
    capture_rects = proof.get("capture_rects")
    captured_size = proof.get("captured_image_size")
    if not (
        isinstance(viewer, dict)
        and isinstance(capture, dict)
        and isinstance(capture_rects, list)
        and capture_rects
        and isinstance(captured_size, list)
        and len(captured_size) == 2
    ):
        return False
    try:
        viewer_values = tuple(
            int(viewer[key]) for key in ("left", "top", "width", "height")
        )
        capture_values = tuple(
            int(capture[key]) for key in ("left", "top", "width", "height")
        )
        captured_width, captured_height = (int(value) for value in captured_size)
    except (KeyError, TypeError, ValueError):
        return False
    viewer_left, viewer_top, viewer_width, viewer_height = viewer_values
    capture_left, capture_top, capture_width, capture_height = capture_values
    all_captures_match = all(item == capture for item in capture_rects)
    return bool(
        viewer_width > 0
        and viewer_height > 0
        and capture_width > 0
        and capture_height > 0
        and capture_left >= viewer_left
        and capture_top >= viewer_top
        and capture_left + capture_width <= viewer_left + viewer_width
        and capture_top + capture_height <= viewer_top + viewer_height
        and (capture_width < viewer_width or capture_height < viewer_height)
        and all_captures_match
        and [capture_width, capture_height] == [captured_width, captured_height]
    )
