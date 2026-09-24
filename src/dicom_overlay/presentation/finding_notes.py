"""Presentation-only separation of exact known technical note formats.

Never classify arbitrary prose as technical or change the underlying findings.
Crop limitations remain explicitly crop-scoped in the primary clinical view.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_CONTEXT_EXPANSION = re.compile(
    r"BBox [0-9]+ expanded to preserve interpretable waveform context\."
)
_COORDINATE = r"(?:0\.[0-9]{4}|1\.0000)"
_CROP_NOTE = re.compile(
    rf"\[Crop-only evidence; ROI x={_COORDINATE} y={_COORDINATE} "
    rf"w={_COORDINATE} h={_COORDINATE}\] (?P<body>.+)",
    re.DOTALL,
)


def report_note_views(notes: Sequence[str]) -> tuple[list[str], list[str]]:
    """Return clinical display notes and untouched relocated originals, in order."""
    clinical: list[str] = []
    technical: list[str] = []
    for note in notes:
        if _CONTEXT_EXPANSION.fullmatch(note):
            technical.append(note)
            continue
        crop = _CROP_NOTE.fullmatch(note)
        if crop is not None:
            clinical.append("[Crop-only evidence] " + crop["body"])
            technical.append(note)
        else:
            clinical.append(note)
    return clinical, technical
