from __future__ import annotations

import json

import pytest
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QLabel

from dicom_overlay.presentation.review_capture import capture_review_widgets


def test_capture_only_renders_explicit_visible_app_widgets(qtbot, tmp_path):
    panel = QLabel("Synthetic co-reading result")
    panel.setStyleSheet("background: #123456; color: white;")
    panel.resize(320, 120)
    qtbot.addWidget(panel)
    panel.show()
    hidden = QLabel("Never export a hidden panel")
    qtbot.addWidget(hidden)

    capture_review_widgets(
        tmp_path,
        summary_panel=panel,
        control_bar=panel,
        overlay_layer=hidden,
    )

    receipt = json.loads((tmp_path / "ui-capture.json").read_text())
    assert receipt["desktop_background_captured"] is False
    assert receipt["capture_exclusion_disabled"] is False
    assert receipt["widgets"][2]["status"] == "not_visible"
    assert not (tmp_path / "overlay-layer.png").exists()
    rendered = QImage(str(tmp_path / "summary-panel.png"))
    assert not rendered.isNull()
    assert rendered.pixelColor(4, 4).name() == "#123456"
    assert receipt["widgets"][0]["image_size_px"] == [
        rendered.width(),
        rendered.height(),
    ]


def test_capture_does_not_claim_success_when_destination_missing(qtbot, tmp_path):
    panel = QLabel("Synthetic result")
    qtbot.addWidget(panel)
    panel.show()

    with pytest.raises(RuntimeError, match="Could not export app widget"):
        capture_review_widgets(
            tmp_path / "missing",
            summary_panel=panel,
            control_bar=panel,
            overlay_layer=panel,
        )
