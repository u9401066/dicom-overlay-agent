"""Read only the file explicitly selected by the reviewer, with a byte limit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dicom_overlay.application.regional_history import (
    MAX_HISTORY_BYTES,
    decode_regional_history,
)

if TYPE_CHECKING:
    from pathlib import Path

    from dicom_overlay.application.regional_conversation import ArchivedConversation


def load_regional_history(
    path: Path, *, source_image_sha256: str
) -> list[ArchivedConversation]:
    if not path.is_file() or path.stat().st_size > MAX_HISTORY_BYTES:
        raise ValueError("Choose a regional history JSON file smaller than 4 MiB")
    with path.open("rb") as stream:
        content = stream.read(MAX_HISTORY_BYTES + 1)
    return decode_regional_history(content, source_image_sha256=source_image_sha256)
