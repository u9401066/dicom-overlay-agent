"""Canonical filesystem paths shared by the OpenClaw client and launcher."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def resolve_bbox_tool_audit_path(
    base_dir: Path,
    explicit_path: str | Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Return one absolute bbox-receipt path for both sides of the Gateway.

    An explicit constructor argument has priority over the process environment.
    Relative paths are always anchored to ``base_dir`` so a launcher and client
    with different working directories cannot silently select different files.
    """

    root = base_dir.resolve()
    configured = str(explicit_path or "").strip()
    if not configured:
        values = os.environ if environment is None else environment
        configured = values.get("DICOM_BBOX_AUDIT_PATH", "").strip()
    path = (
        Path(configured)
        if configured
        else root / "data" / "tmp" / "bbox-tool-audit.jsonl"
    )
    if not path.is_absolute():
        path = root / path
    return path.resolve()
