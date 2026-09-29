"""Bind native bbox receipts and exact image/crop bytes to public source evidence.

The host must collect the tool content and local audit record independently of
the model's final JSON. This boundary verifies their agreement, not authenticity
against a hostile host, medical localization, or clinical diagnostic correctness.
"""

from __future__ import annotations

import base64
import re
from copy import deepcopy
from dataclasses import dataclass, field, replace
from hashlib import sha256
from typing import TYPE_CHECKING

from dicom_overlay.infrastructure.bbox_receipts import (
    bbox_coordinates_digest,
    canonical_bbox_coordinate,
    valid_bbox_tool_audit_record,
)
from dicom_overlay.infrastructure.screen_monitor import ImageProcessor
from dicom_overlay.infrastructure.strict_json import StrictJSONError, read_json_object
from medical_image_harness.image_ops import (
    MAX_PIXELS,
    ImageOperationError,
    decode_image,
)
from medical_image_harness.models import Evidence, Modality, RegionRect
from medical_image_harness.multipass import remap_bbox
from medical_image_harness.provenance import TransformationRecord, canonical_json_sha256

if TYPE_CHECKING:
    from collections.abc import Mapping

_MAX_IMAGE_BYTES = 32 * 1024 * 1024


class SourceEvidenceError(ValueError):
    """Fixed PHI-free failure categories; never echo images, IDs or tool text."""


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise SourceEvidenceError(category)


@dataclass(frozen=True)
class SourceEvidenceBinding:
    """Local transport/operation receipt; scientific types stay public-owned."""

    source_image_sha256: str
    tool_image_sha256: str
    source_size: tuple[int, int]
    tool_size: tuple[int, int]
    source_pixel_box: tuple[int, int, int, int]
    evidence: tuple[Evidence, ...]
    transformations: tuple[TransformationRecord, ...]
    audit_record_sha256: str
    tool_details_sha256: str
    tool_details_bytes: bytes = field(repr=False)


def _image_size(raw: bytes) -> tuple[int, int]:
    _require(
        type(raw) is bytes and 0 < len(raw) <= _MAX_IMAGE_BYTES, "invalid_image_bytes"
    )
    try:
        _, image = decode_image(base64.b64encode(raw).decode("ascii"))
        try:
            _require(
                image.format in {"PNG", "JPEG"} and getattr(image, "n_frames", 1) == 1,
                "unsupported_image_format",
            )
            return image.size
        finally:
            image.close()
    except ImageOperationError:
        raise SourceEvidenceError("invalid_image_encoding") from None


def _geometry(raw: object) -> RegionRect:
    _require(
        isinstance(raw, dict) and set(raw) == {"x", "y", "w", "h"}, "invalid_native_box"
    )
    assert isinstance(raw, dict)
    _require(
        all(type(value) in {int, float} for value in raw.values()), "invalid_native_box"
    )
    try:
        box = RegionRect(**raw)
        _require(
            box.w > 0 and box.h > 0 and box.x + box.w <= 1 and box.y + box.h <= 1,
            "invalid_native_box",
        )
        _require(
            all(
                float(canonical_bbox_coordinate(value)) == value
                for value in raw.values()
            ),
            "native_geometry_not_canonical",
        )
        return box
    except SourceEvidenceError:
        raise
    except (ValueError, TypeError, OverflowError):
        raise SourceEvidenceError("invalid_native_box") from None


def bind_native_bbox_evidence(
    *,
    source_bytes: bytes,
    tool_image_bytes: bytes,
    tool_details_json: bytes,
    audit_record: Mapping[str, object],
    evidence_nonce: str,
    tool_call_id: str,
    source_asset_id: str,
    modality: Modality,
    deidentified: bool,
    crop_region: RegionRect | None = None,
) -> SourceEvidenceBinding:
    """Verify current native producer output without copying model-owned proof.

    ``tool_details_json`` is the exact UTF-8 bytes of the native tool's text
    content, not a Python reserialization of ``details``. Its SHA is bound by the
    independently collected audit record. The host supplies the current nonce,
    observed tool-call ID, primary ROI bytes and opaque manifest asset ID.
    A crop is reproduced with the actual App cropper and compared byte-for-byte;
    remapping uses its effective integer pixel box, not the nominal float region.
    No original full-screen data or wider ROI is requested by this API.
    """
    _require(deidentified is True, "untrusted_deidentification")
    _require(
        modality in {Modality.EKG, Modality.CXR, Modality.CT_BRAIN}, "unknown_modality"
    )
    _require(
        isinstance(evidence_nonce, str)
        and bool(re.fullmatch(r"[a-f0-9]{32}", evidence_nonce)),
        "invalid_host_nonce",
    )
    _require(
        isinstance(tool_call_id, str) and bool(tool_call_id.strip()),
        "missing_host_tool_call",
    )
    _require(
        isinstance(source_asset_id, str)
        and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", source_asset_id)),
        "invalid_host_asset_id",
    )
    source_size = _image_size(source_bytes)
    tool_size = _image_size(tool_image_bytes)
    source_sha = sha256(source_bytes).hexdigest()
    tool_sha = sha256(tool_image_bytes).hexdigest()
    width, height = source_size
    pixel_box = (0, 0, width, height)
    transforms: tuple[TransformationRecord, ...] = ()
    if crop_region is None:
        _require(tool_image_bytes == source_bytes, "tool_image_not_primary_source")
    else:
        _require(
            crop_region.w > 0
            and crop_region.h > 0
            and crop_region.x + crop_region.w <= 1
            and crop_region.y + crop_region.h <= 1,
            "crop_outside_primary_source",
        )
        pixel_box = ImageProcessor.crop_region_pixel_box(width, height, crop_region)
        crop_width, crop_height = (
            pixel_box[2] - pixel_box[0],
            pixel_box[3] - pixel_box[1],
        )
        scale = max(1, ImageProcessor._MIN_CROP_EDGE_PX / min(crop_width, crop_height))
        _require(
            round(crop_width * scale) * round(crop_height * scale) <= MAX_PIXELS,
            "crop_resampling_pixel_limit",
        )
        expected = base64.b64decode(
            ImageProcessor().crop_region_base64(
                base64.b64encode(source_bytes).decode("ascii"),
                crop_region,
            ),
            validate=True,
        )
        _require(tool_image_bytes == expected, "crop_operation_bytes_mismatch")
        if tool_sha != source_sha:
            transforms = (
                TransformationRecord(
                    operation="app_pillow_crop_lanczos",
                    parent_sha256=source_sha,
                    output_sha256=tool_sha,
                    parameters={
                        "source_size": list(source_size),
                        "pixel_box": list(pixel_box),
                        "output_size": list(tool_size),
                    },
                ),
            )

    record = deepcopy(dict(audit_record))
    _require(valid_bbox_tool_audit_record(record), "invalid_native_audit_record")
    _require(
        set(record)
        == {
            "schema_version",
            "recorded_at",
            "tool",
            "tool_call_id",
            "accepted_count",
            "rejected_count",
            "source_image_sha256",
            "evidence_nonce",
            "accepted_boxes_sha256",
            "details_sha256",
        }
        and isinstance(record["recorded_at"], str)
        and bool(record["recorded_at"]),
        "invalid_native_audit_fields",
    )
    _require(
        record["source_image_sha256"] == tool_sha
        and record["evidence_nonce"] == evidence_nonce
        and record["tool_call_id"] == tool_call_id,
        "native_receipt_binding_mismatch",
    )
    try:
        details = read_json_object(tool_details_json)
    except StrictJSONError:
        raise SourceEvidenceError("invalid_native_details_json") from None
    details_sha = sha256(tool_details_json).hexdigest()
    _require(record["details_sha256"] == details_sha, "native_details_hash_mismatch")
    _require(
        set(details)
        == {
            "modality",
            "source_image_sha256",
            "evidence_nonce",
            "coordinateSpace",
            "accepted",
            "rejected",
        },
        "invalid_native_details_shape",
    )
    _require(
        details["modality"] == modality.value
        and details["source_image_sha256"] == tool_sha
        and details["evidence_nonce"] == evidence_nonce
        and details["coordinateSpace"] == "normalized_full_image",
        "native_details_binding_mismatch",
    )
    accepted, rejected = details["accepted"], details["rejected"]
    _require(
        isinstance(accepted, list) and isinstance(rejected, list),
        "invalid_native_box_inventory",
    )
    _require(
        len(accepted) == record["accepted_count"]
        and len(rejected) == record["rejected_count"]
        and len(accepted) + len(rejected) <= 12,
        "native_box_count_mismatch",
    )
    boxes = []
    for item in accepted:
        _require(
            isinstance(item, dict)
            and set(item) == {"id", "box", "reason", "clipped"}
            and isinstance(item["id"], str)
            and isinstance(item["reason"], str)
            and type(item["clipped"]) is bool,
            "invalid_native_accepted_record",
        )
        boxes.append(_geometry(item["box"]))
    for item in rejected:
        _require(
            isinstance(item, dict)
            and set(item) == {"id", "reason"}
            and isinstance(item["id"], str)
            and isinstance(item["reason"], str),
            "invalid_native_rejected_record",
        )
    _require(
        bbox_coordinates_digest(boxes) == record["accepted_boxes_sha256"],
        "native_coordinate_digest_mismatch",
    )
    effective = RegionRect(
        pixel_box[0] / width,
        pixel_box[1] / height,
        (pixel_box[2] - pixel_box[0]) / width,
        (pixel_box[3] - pixel_box[1]) / height,
    )
    evidence = []
    for index, local_box in enumerate(boxes):
        mapped = (
            remap_bbox(local_box, effective) if crop_region is not None else local_box
        )
        bound_box = replace(mapped, source_image_sha256=source_sha, verified=True)
        identifier = (
            "region-"
            + canonical_json_sha256(
                [source_sha, tool_sha, evidence_nonce, tool_call_id, details_sha, index]
            )[:32]
        )
        evidence.append(
            Evidence(
                id=identifier,
                kind="source_region",
                source_image_sha256=source_sha,
                source_ref=source_asset_id,
                bboxes=[bound_box],
                description="Native receipt-bound source geometry; clinical content not verified.",
            )
        )
    return SourceEvidenceBinding(
        source_sha,
        tool_sha,
        source_size,
        tool_size,
        pixel_box,
        tuple(evidence),
        transforms,
        canonical_json_sha256(record),
        details_sha,
        tool_details_json,
    )
