"""Export the app's own rendered widgets without capturing the desktop.

Windows capture exclusion deliberately hides overlays from screen grabbers.
QWidget.grab renders only an explicitly supplied app-owned widget; it does not
disable that protection or copy any other application's pixels.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from PyQt6.QtWidgets import QWidget


def capture_review_widgets(
    folder: Path,
    *,
    summary_panel: QWidget,
    control_bar: QWidget,
    overlay_layer: QWidget,
) -> None:
    """Save current GUI renderings alongside an explicit review export."""
    records: list[dict[str, object]] = []
    for name, widget in (
        ("summary-panel", summary_panel),
        ("control-bar", control_bar),
        ("overlay-layer", overlay_layer),
    ):
        if not widget.isVisible():
            records.append({"widget": name, "status": "not_visible"})
            continue
        pixmap = widget.grab()
        if pixmap.isNull() or not pixmap.save(str(folder / f"{name}.png"), "PNG"):
            raise RuntimeError(f"Could not export app widget: {name}")
        geometry = widget.geometry()
        records.append(
            {
                "widget": name,
                "status": "rendered",
                "path": f"{name}.png",
                "geometry_logical": [
                    geometry.x(),
                    geometry.y(),
                    geometry.width(),
                    geometry.height(),
                ],
                "device_pixel_ratio": pixmap.devicePixelRatio(),
                "image_size_px": [pixmap.width(), pixmap.height()],
            }
        )
    (folder / "ui-capture.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "method": "app_owned_widget_render",
                "desktop_background_captured": False,
                "capture_exclusion_disabled": False,
                "widgets": records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
