"""Bounded, atomic decoding of explicitly chosen regional history exports.

Imported text is untrusted review context. File paths, clinical findings and
model/tool instructions are never executed or restored from these documents.
"""

from __future__ import annotations

import json
import math
from datetime import datetime

from dicom_overlay.application.regional_conversation import (
    ArchivedConversation,
    RegionalTurn,
    validate_review_turn_id,
)
from medical_image_harness.models import RegionRect

MAX_HISTORY_BYTES = 4 * 1024 * 1024
MAX_HISTORY_THREADS = 64
MAX_HISTORY_TURNS = 512


def _object(value: object, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Unexpected regional history fields")
    return value


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise ValueError("Invalid or oversized regional history text")
    return value


def _turns(value: object) -> tuple[RegionalTurn, ...]:
    if not isinstance(value, list) or len(value) > MAX_HISTORY_TURNS:
        raise ValueError("Too many regional history turns")
    result = []
    seen = set()
    for raw in value:
        item = _object(
            raw, {"question", "answer", "created_at", "proposal", "review_turn_id"}
        )
        turn_id = _text(item["review_turn_id"], 32)
        validate_review_turn_id(turn_id)
        if turn_id in seen:
            raise ValueError("Duplicate regional history turn ID")
        seen.add(turn_id)
        timestamp = _text(item["created_at"], 64)
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            raise ValueError("Invalid regional history timestamp") from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Regional history timestamp needs a timezone")
        result.append(
            RegionalTurn(
                _text(item["question"], 8_000),
                _text(item["answer"], 64_000),
                timestamp,
                _text(item["proposal"], 16_000),
                turn_id,
            )
        )
    return tuple(result)


def _history(raw: object, digest: str) -> ArchivedConversation:
    item = _object(raw, {"finding_id", "region", "turns"})
    coords = _object(item["region"], {"x", "y", "w", "h"})
    values = [coords[key] for key in ("x", "y", "w", "h")]
    if not all(
        type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value)
        for value in values
    ):
        raise ValueError("Invalid regional history coordinates")
    x, y, w, h = values
    if not (0 <= x < x + w <= 1 + 1e-9 and 0 <= y < y + h <= 1 + 1e-9):
        raise ValueError("Regional history is outside the original ROI")
    turns = _turns(item["turns"])
    if not turns:
        raise ValueError("Regional history has no turns")
    return ArchivedConversation(
        digest, _text(item["finding_id"], 256), RegionRect(x, y, w, h), turns
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate regional history JSON key")
        result[key] = value
    return result


def decode_regional_history(
    content: bytes, *, source_image_sha256: str
) -> list[ArchivedConversation]:
    """Validate the whole file before returning any selectable conversations.

    Same encoded source-image bytes are required, not a filename, image size,
    overlapping box or perceptual similarity. Old turn IDs are retained only
    inside explicitly historical context, never as this run's evidence receipts.
    """
    if len(content) > MAX_HISTORY_BYTES:
        raise ValueError("Regional history exceeds the 4 MiB limit")
    try:
        payload = json.loads(
            content.decode("utf-8-sig"), object_pairs_hook=_unique_object
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("Invalid regional history JSON") from None
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int:
        raise ValueError("Invalid regional history version")
    version = payload["schema_version"]
    if version not in (2, 3):
        raise ValueError("Unsupported regional history version")
    keys = {
        "schema_version",
        "source_image_sha256",
        "coordinate_space",
        "content_role",
        "threads",
    }
    _object(payload, keys | ({"archived_threads"} if version == 3 else set()))
    digest = payload["source_image_sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
        or digest != source_image_sha256
    ):
        raise ValueError("History belongs to a different original image")
    if (
        payload["coordinate_space"] != "normalized_original_roi"
        or payload["content_role"] != "review_conversation_not_verified_findings"
    ):
        raise ValueError("Unsupported regional history coordinate space or role")
    live = payload["threads"]
    archived = payload.get("archived_threads", [])
    if (
        not isinstance(live, list)
        or not isinstance(archived, list)
        or len(live) + len(archived) > MAX_HISTORY_THREADS
    ):
        raise ValueError("Too many regional history conversations")
    result = [_history(raw, digest) for raw in live]
    for raw in archived:
        item = _object(raw, {"history", "turns"})
        original = _object(
            item["history"], {"source_image_sha256", "finding_id", "region", "turns"}
        )
        if original["source_image_sha256"] != digest:
            raise ValueError("Archived conversation belongs to a different image")
        history = _history(
            {
                key: value
                for key, value in original.items()
                if key != "source_image_sha256"
            },
            digest,
        )
        turns = (*history.turns, *_turns(item["turns"]))
        if len({turn.review_turn_id for turn in turns}) != len(turns):
            raise ValueError("Duplicate regional history turn ID")
        result.append(
            ArchivedConversation(digest, history.finding_id, history.region, turns)
        )
    if sum(len(history.turns) for history in result) > MAX_HISTORY_TURNS:
        raise ValueError("Too many total regional history turns")
    # Duplicate archives do not create ambiguous choices; do not conflate live
    # IDs across independent past runs (those may legitimately repeat).
    return list({history.archive_id: history for history in result}.values())
