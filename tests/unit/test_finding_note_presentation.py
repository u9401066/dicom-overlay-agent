"""Presentation-only scope preservation and accessible technical-note navigation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel

from dicom_overlay.presentation.finding_notes import report_note_views
from dicom_overlay.presentation.overlay_window import SummaryPanel, _WrappingReportLabel
from medical_image_harness.models import Severity
from tests.unit.test_overlay_interaction import _result
from tests.unit.test_overlay_interaction import qt_app as qt_app

PREFIX = "[Crop-only evidence; ROI x=0.2500 y=0.5000 w=0.5000 h=0.2500] "
BODY = "V1 is absent; V2 and V6 are truncated."
EXPANSION = "BBox 1 expanded to preserve interpretable waveform context."


def _load_render_fonts():
    # Qt's Windows offscreen backend starts with no system font database.
    # Load installed fonts into this test process only; no bundled font or
    # production fallback changes, and no native window/focus changes.
    if os.name == "nt" and not QFontDatabase.families():
        font_root = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in (
            "segoeui.ttf",
            "segoeuib.ttf",
            "msjh.ttc",
            "seguiemj.ttf",
            "seguisym.ttf",
        ):
            path = font_root / name
            if path.is_file():
                assert QFontDatabase.addApplicationFont(str(path)) >= 0
    assert QFontDatabase.families(), (
        "Rendered checks need actual fonts, not tofu glyphs"
    )


@pytest.fixture(autouse=True)
def render_fonts(qt_app):
    _load_render_fonts()


def _noted_result():
    result = _result()
    result.findings = [
        replace(
            result.findings[0],
            notes=[
                "Original ROI includes labeled V1.",
                PREFIX + BODY,
                EXPANSION,
                EXPANSION.replace("1", "2"),
                EXPANSION.replace("1", "3"),
                "Compare this uncertainty with the full-resolution source.",
            ],
        )
    ]
    return result


def _process_text(panel):
    return "\n".join(
        widget.text()
        for index in range(panel._process_layout.count())
        if isinstance(widget := panel._process_layout.itemAt(index).widget(), QLabel)
    )


@pytest.mark.parametrize(
    "note",
    [
        "Clinical uncertainty remains.",
        "BBox 1 expanded to preserve interpretable waveform context. BUT assess lead V2.",
        "BBox 1 is incorrectly localized; review source.",
        "[Crop-only evidence; ROI x=unknown] V1 is absent.",
        PREFIX.replace("x=0.2500", "x=-0.2500") + BODY,
        PREFIX.replace("h=0.2500", "h=1.5000") + BODY,
        PREFIX.replace("w=0.5000", "w=0.5") + BODY,
        PREFIX.rstrip(),
        "<script>synthetic()</script>",
        "原圖導程可見；裁切影像未包含此導程。",
    ],
)
def test_unknown_mixed_or_malformed_notes_stay_in_clinical_view(note):
    assert report_note_views([note]) == ([note], [])


def test_known_crop_coordinates_relocate_without_unscoping_or_rewriting_body():
    body = BODY + "\n  No measurement is supported."
    clinical, technical = report_note_views([PREFIX + body])
    assert clinical == ["[Crop-only evidence] " + body]
    assert technical == [PREFIX + body]


def test_known_technical_notes_preserve_order_and_duplicates():
    notes = [EXPANSION, EXPANSION, PREFIX + BODY, "Unknown note"]
    original = deepcopy(notes)
    clinical, technical = report_note_views(notes)
    assert clinical == ["[Crop-only evidence] " + BODY, "Unknown note"]
    assert technical == notes[:3]
    assert notes == original


def test_report_keeps_clinical_notes_and_process_keeps_every_relocated_original(qt_app):
    result = _noted_result()
    original = deepcopy(result)
    panel = SummaryPanel()
    panel.update_result(result)
    report = panel._findings_layout.itemAt(0).widget()
    assert "ROI x=" not in report.text()
    assert "BBox 1 expanded" not in report.text()
    assert "[Crop-only evidence] " + BODY in report.text()
    assert "Original ROI includes labeled V1." in report.text()
    assert "Compare this uncertainty" in report.text()
    assert (
        "Confidence: low" in report.text() and "Question for review:" in report.text()
    )
    process = _process_text(panel)
    for note in result.findings[0].notes[1:5]:
        assert note in process
    assert "1. Uncertain ST-T change [f1]" in process
    assert not panel._technical_button.isHidden()
    assert result == original  # Includes IDs, boxes, notes, traces, summary/checklist.
    panel.close()


@pytest.mark.parametrize("keyboard", [False, True])
def test_technical_entry_navigates_to_visible_heading(qt_app, keyboard):
    panel = SummaryPanel()
    panel.resize(430, 550)
    panel.update_result(_noted_result())
    panel.show()
    qt_app.processEvents()
    assert panel._technical_button.accessibleName() == "查看標記來源與完整技術註記"
    if keyboard:
        panel._technical_button.setFocus()
        QTest.keyClick(panel._technical_button, Qt.Key.Key_Space)
    else:
        QTest.mouseClick(panel._technical_button, Qt.MouseButton.LeftButton)
    qt_app.processEvents()
    assert panel._tabs.currentIndex() == 2
    heading = panel._technical_heading
    viewport = panel._process_scroll.viewport()
    top = heading.mapTo(viewport, heading.rect().topLeft()).y()
    assert top >= 0 and top + heading.height() <= viewport.height()
    assert panel._process_scroll.verticalScrollBar().value() > 0
    panel.close()


@pytest.mark.parametrize("action", ["clear", "replace"])
def test_queued_navigation_does_not_reopen_deleted_or_stale_details(qt_app, action):
    panel = SummaryPanel()
    panel.update_result(_noted_result())
    panel._technical_button.click()
    if action == "clear":
        panel.clear()
    else:
        panel.update_result(_result())
    qt_app.processEvents()
    assert panel._technical_heading is None
    assert panel._technical_button.isHidden()
    assert "ROI x=" not in _process_text(panel)
    panel.close()


def test_primary_and_technical_priority_numbering_match_without_reordering_data(qt_app):
    result = _noted_result()
    original_finding = result.findings[0]
    result.findings.append(
        replace(
            original_finding,
            id="urgent",
            label="Urgent pattern",
            severity=Severity.CRITICAL,
            notes=[EXPANSION],
        )
    )
    panel = SummaryPanel()
    panel.update_result(result)
    assert (
        panel._findings_layout.itemAt(0).widget().text().startswith("1. Urgent pattern")
    )
    process = _process_text(panel)
    assert process.index("1. Urgent pattern [urgent]") < process.index(
        "2. Uncertain ST-T change [f1]"
    )
    assert [finding.id for finding in result.findings] == ["f1", "urgent"]
    panel.close()


def test_no_process_trace_does_not_prevent_access_to_raw_notes(qt_app):
    result = _noted_result()
    result.analysis_trace = []
    panel = SummaryPanel()
    panel.update_result(result)
    assert "No process record available." in _process_text(panel)
    assert PREFIX + BODY in _process_text(panel)
    assert not panel._technical_button.isHidden()
    panel.close()


def test_relocated_text_remains_plain_selectable_text(qt_app):
    result = _noted_result()
    result.findings[0] = replace(
        result.findings[0],
        label="<b>synthetic</b>",
        notes=[PREFIX + "<script>synthetic()</script>"],
    )
    panel = SummaryPanel()
    panel.update_result(result)
    label = panel.findChild(QLabel, "finding-technical-notes")
    assert label.textFormat() == Qt.TextFormat.PlainText
    assert label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert "<script>synthetic()</script>" in label.text()
    assert "<b>synthetic</b>" in label.text()
    panel.close()


@pytest.mark.parametrize("height", [450, 700, 1000])
def test_compact_and_technical_text_wrap_without_clipping(qt_app, height, tmp_path):
    panel = SummaryPanel()
    panel.resize(430, height)
    panel.update_result(_noted_result())
    panel.show()
    qt_app.processEvents()
    report = panel._findings_layout.itemAt(0).widget()
    assert report.height() == report.heightForWidth(report.width())
    assert panel._report_scroll.horizontalScrollBar().maximum() == 0
    assert panel.grab().save(str(tmp_path / f"report-{height}.png"))
    panel._technical_button.click()
    qt_app.processEvents()
    details = panel.findChild(QLabel, "finding-technical-notes")
    assert details.height() == details.heightForWidth(details.width())
    assert panel._process_scroll.horizontalScrollBar().maximum() == 0
    assert panel.grab().save(str(tmp_path / f"process-{height}.png"))
    panel.close()


def test_wrapped_label_releases_old_height_after_text_becomes_shorter(qt_app):
    label = _WrappingReportLabel("A long synthetic note. " * 80)
    label.setWordWrap(True)
    label.resize(340, 100)
    label.show()
    qt_app.processEvents()
    old_height = label.height()
    label.setText("Short note.")
    qt_app.processEvents()
    assert label.height() < old_height / 2
    label.close()


@pytest.mark.parametrize("scale", ["1", "1.5", "2"])
def test_isolated_scaled_render_preserves_scope_navigation_and_wrapping(
    scale, tmp_path
):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.unit.test_finding_note_presentation",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_SCALE_FACTOR": scale},
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    receipt = json.loads(completed.stdout)
    assert receipt["device_pixel_ratio"] == pytest.approx(float(scale))
    assert receipt["report_width"] == round(430 * float(scale))
    assert receipt["report_height"] == round(700 * float(scale))
    assert receipt["scope_retained"] and receipt["original_notes_retained"]
    assert receipt["horizontal_scroll"] == 0
    assert receipt["technical_selected"] and receipt["notes_height_fits"]


def test_unbroken_identifier_remains_accessible_instead_of_silently_clipping(qt_app):
    identifier = "synthetic_identifier_" * 12
    result = _noted_result()
    result.findings[0] = replace(result.findings[0], notes=[identifier])
    panel = SummaryPanel()
    panel.resize(430, 700)
    panel.update_result(result)
    panel.show()
    for _ in range(3):
        qt_app.processEvents()
    label = panel._findings_layout.itemAt(0).widget()
    assert identifier in label.text()
    assert label.width() >= label.fontMetrics().horizontalAdvance(identifier)
    assert panel._report_scroll.horizontalScrollBar().maximum() > 0
    panel._report_scroll.horizontalScrollBar().setValue(
        panel._report_scroll.horizontalScrollBar().maximum()
    )
    assert panel._report_scroll.horizontalScrollBar().value() > 0
    panel.close()


if __name__ == "__main__":
    # Child-process offscreen Qt rendering only; never a native desktop/model run.
    app = QApplication([])
    _load_render_fonts()
    panel = SummaryPanel()
    panel.resize(430, 700)
    panel.update_result(_noted_result())
    panel.show()
    for _ in range(3):
        app.processEvents()
    output = Path(sys.argv[1])
    report_image = panel.grab()
    assert report_image.save(str(output / "report.png"))
    report_text = panel._findings_layout.itemAt(0).widget().text()
    panel._technical_button.click()
    for _ in range(3):
        app.processEvents()
    assert panel.grab().save(str(output / "process.png"))
    notes = panel.findChild(QLabel, "finding-technical-notes")
    print(
        json.dumps(
            {
                "device_pixel_ratio": report_image.devicePixelRatio(),
                "report_width": report_image.width(),
                "report_height": report_image.height(),
                "scope_retained": "[Crop-only evidence] " + BODY in report_text,
                "original_notes_retained": PREFIX + BODY in _process_text(panel),
                "horizontal_scroll": panel._process_scroll.horizontalScrollBar().maximum(),
                "technical_selected": panel._tabs.currentIndex() == 2,
                "notes_height_fits": notes.height()
                == notes.heightForWidth(notes.width()),
            }
        )
    )
    panel.close()
