"""Exact coordinate serialization shared by native-tool receipt consumers."""

from __future__ import annotations

import json
import math
import re
from hashlib import sha256
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from medical_image_harness.models import RegionRect


def canonical_bbox_coordinate(value: float) -> str:
    """Match JavaScript Math.round(value * 10000), then toFixed(4).

    floor(scaled + 0.5) is not equivalent for the float just below 0.5:
    the addition itself rounds up to 1.0. Compare the fractional part so
    image/turn receipts do not need an epsilon or relaxed digest matching.
    """
    scaled = value * 10_000
    if not math.isfinite(scaled):
        raise ValueError("bbox receipt coordinate must be finite")
    lower = math.floor(scaled)
    rounded = (lower + int(scaled - lower >= 0.5)) / 10_000
    return f"{rounded:.4f}"


def bbox_coordinates_digest(boxes: Sequence[RegionRect]) -> str:
    """Pinned native producer's exact four-decimal coordinate multiset digest."""
    canonical = sorted(
        [canonical_bbox_coordinate(value) for value in (box.x, box.y, box.w, box.h)]
        for box in boxes
    )
    return sha256(
        json.dumps(canonical, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def valid_bbox_tool_audit_record(value: object) -> bool:
    """Validate record shape only; consumers must bind source, turn and details."""
    if not isinstance(value, dict):
        return False

    def digest(field: str) -> bool:
        raw = value.get(field)
        return isinstance(raw, str) and bool(re.fullmatch(r"[a-fA-F0-9]{64}", raw))

    return (
        value.get("schema_version") == 2
        and value.get("tool") == "dicom_bbox_validate"
        and isinstance(value.get("tool_call_id"), str)
        and bool(value["tool_call_id"])
        and type(value.get("accepted_count")) is int
        and value["accepted_count"] >= 0
        and type(value.get("rejected_count")) is int
        and value["rejected_count"] >= 0
        and digest("source_image_sha256")
        and digest("accepted_boxes_sha256")
        and digest("details_sha256")
        and isinstance(value.get("evidence_nonce"), str)
        and bool(re.fullmatch(r"[a-f0-9]{32}", value["evidence_nonce"]))
    )
