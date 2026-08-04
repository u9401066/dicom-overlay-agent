"""Desktop report and region-interaction tests."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from dicom_overlay.domain.entities import (
    AnalysisResult,
    ChecklistItem,
    Finding,
    Modality,
    Severity,
)
from dicom_overlay.presentation.control_bar import ControlBarWindow
from dicom_overlay.presentation.overlay_window import OverlayWindow, SummaryPanel


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    return app


def _result() -> AnalysisResult:
    return AnalysisResult(
        modality=Modality.EKG,
        summary="Possible localized repolarization change; review requested.",
        severity=Severity.INFO,
        findings=[
            Finding(
                id="f1",
                regions=["lead_V2"],
                label="Uncertain ST-T change",
                detail="Subtle morphology on the screenshot.",
                severity=Severity.INFO,
                confidence="low",
                question="Can the reviewer confirm this in the source viewer?",
            )
        ],
        checklist={
            "st_segment": ChecklistItem("nonspecific", Severity.INFO),
            "rhythm": ChecklistItem("sinus", Severity.NORMAL),
        },
        model_used="openai/gpt-5.6-luna",
        image_quality="Limited screenshot; waveform remains readable.",
        next_steps=["Review V2 at source resolution."],
        analysis_trace=[
            {
                "stage": "coarse",
                "status": "completed",
                "tool": "openclaw_vision_analysis",
                "tools": ["dicom_bbox_validate"],
            },
            {
                "stage": "systematic_assist",
                "status": "planned",
                "tool": "ekg_layout_lead_group_probes",
                "probes": [
                    {
                        "target_id": "ekg_systematic_precordial_leads",
                        "crop_region": {"x": 0.0, "y": 0.5, "w": 1.0, "h": 0.5},
                    }
                ],
            },
            {
                "stage": "refine",
                "status": "completed",
                "tool": "crop_region_base64",
                "target_id": "ekg_systematic_precordial_leads",
                "crop_source": "original_roi",
                "tool_audit": [
                    {
                        "tool": "dicom_bbox_validate",
                        "accepted_count": 2,
                        "rejected_count": 0,
                    },
                    {
                        "tool": "ecg_founder_analyze_waveform",
                        "status": "ok",
                        "prediction_count": 10,
                        "calibration_status": "uncalibrated",
                    }
                ],
            },
        ],
    )


def test_report_panel_exposes_full_report_checklist_and_process(
    qt_app: QApplication,
) -> None:
    panel = SummaryPanel()
    panel.update_result(_result())

    assert panel._tabs.count() == 3
    assert panel._findings_layout.count() == 3
    finding = panel._findings_layout.itemAt(0).widget()
    assert finding is not None
    assert "Confidence: low" in finding.text()
    assert "Question for review" in finding.text()
    assert panel._checklist_layout.count() == 2
    process = panel._process_layout.itemAt(0).widget()
    assert process is not None
    assert "dicom_bbox_validate" in process.text()
    systematic = panel._process_layout.itemAt(1).widget()
    assert systematic is not None
    assert "ekg_systematic_precordial_leads" in systematic.text()
    refined = panel._process_layout.itemAt(2).widget()
    assert refined is not None
    assert "Source: original_roi" in refined.text()
    assert "accepted=2" in refined.text()
    assert "ecg_founder_analyze_waveform" in refined.text()
    assert "predictions=10" in refined.text()
    assert "calibration=uncalibrated" in refined.text()
    panel.close()


def test_overlay_maps_drawn_region_back_to_original_roi(qt_app: QApplication) -> None:
    overlay = OverlayWindow()
    overlay._content_rect = (100, 50, 800, 400)

    normalized = overlay._normalized_rect((300, 150, 200, 100))

    assert normalized == pytest.approx((0.25, 0.25, 0.25, 0.25))
    overlay.close()


def test_control_bar_modes_are_mutually_exclusive(qt_app: QApplication) -> None:
    bar = ControlBarWindow()
    modes: list[str] = []
    bar.interaction_mode_changed.connect(modes.append)

    bar._inspect_btn.setChecked(True)
    bar._annotate_btn.setChecked(True)

    assert not bar._inspect_btn.isChecked()
    assert bar._annotate_btn.isChecked()
    assert modes[-1] == "annotate"
    bar.close()
