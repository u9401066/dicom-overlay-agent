"""Bounded JSON-object ingestion shared by scientific drafts and host receipts."""

from __future__ import annotations

import json
import math
from typing import Any, cast

MAX_JSON_BYTES = 512 * 1024


class StrictJSONError(ValueError):
    """Only fixed failure categories; never echo input text."""


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise StrictJSONError(category)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise StrictJSONError("non_finite_number")


def read_json_object(raw: bytes) -> dict[str, Any]:
    _require(
        type(raw) is bytes and 0 < len(raw) <= MAX_JSON_BYTES, "response_size_or_type"
    )
    try:
        result = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        stack = [(result, 0)]
        nodes = 0
        while stack:
            item, depth = stack.pop()
            nodes += 1
            _require(depth <= 32 and nodes <= 50000, "response_structure_limit")
            if isinstance(item, dict):
                for key, value in item.items():
                    key.encode("utf-8")
                    stack.append((value, depth + 1))
            elif isinstance(item, list):
                stack.extend((value, depth + 1) for value in item)
            elif isinstance(item, str):
                item.encode("utf-8")
            elif isinstance(item, float):
                _require(math.isfinite(item), "non_finite_number")
    except StrictJSONError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise StrictJSONError("invalid_json_encoding_or_structure") from None
    _require(isinstance(result, dict), "json_must_be_object")
    return cast("dict[str, Any]", result)
