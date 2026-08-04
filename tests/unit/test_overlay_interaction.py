"""Desktop report and region-interaction tests."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from dicom_overlay.domain.entities import (
    AnalysisResult,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.presentation.control_bar import ControlBarWindow
from dicom_overlay.presentation.overlay_window import (
    ChatPanel,
    OverlayWindow,
    SummaryPanel,
)


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
                source="interactive_ai_review",
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
                    },
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
    assert "Source: interactive ai review" in finding.text()
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


def test_promoted_manual_region_is_consumed_without_removing_other_regions(
    qt_app: QApplication,
) -> None:
    overlay = OverlayWindow()
    promoted = (0.1, 0.2, 0.3, 0.2)
    retained = (0.6, 0.5, 0.2, 0.2)
    overlay._user_regions = [promoted, retained]

    assert overlay.consume_user_region(RegionRect(*promoted)) is True
    assert overlay.user_regions == [retained]
    assert overlay.consume_user_region(RegionRect(*promoted)) is False
    overlay.clear_user_regions()
    assert overlay.user_regions == []
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


def test_chat_proposal_requires_explicit_apply_click(qt_app: QApplication) -> None:
    panel = ChatPanel()
    accepted: list[bool] = []
    panel.proposal_accepted.connect(lambda: accepted.append(True))

    panel.show_chat(
        "Is this still concerning?",
        "The selected crop supports a revised description.",
        proposal_summary="Revise: ST-T change [warning]",
    )
    qt_app.processEvents()

    assert not panel._proposal_actions.isHidden()
    assert "Revise" in panel._proposal_label.text()
    assert panel._question_label.textFormat() is Qt.TextFormat.PlainText
    assert panel._answer_label.textFormat() is Qt.TextFormat.PlainText
    panel._apply_proposal_btn.click()
    qt_app.processEvents()
    assert accepted == [True]
    assert panel._proposal_actions.isHidden()
    panel.close()


def test_chat_timeout_hides_only_chat_and_preserves_report(
    qt_app: QApplication,
) -> None:
    overlay = OverlayWindow()
    highlights = [(10, 20, 30, 40, "warning", "ST-T change")]
    overlay.show_result(
        _result(),
        highlights,
        content_rect=(0, 0, 800, 400),
    )
    overlay.show_chat_response("Question", "Answer")
    assert overlay._chat_timer.isActive()

    overlay._chat_timer.stop()
    overlay._chat_timer.timeout.emit()
    qt_app.processEvents()

    assert not overlay.chat_panel.isVisible()
    assert overlay.summary_panel.isVisible()
    assert overlay._highlights == highlights
    assert overlay._content_rect == (0, 0, 800, 400)
    overlay.dismiss()


def test_process_tab_exposes_interactive_writeback_receipt(
    qt_app: QApplication,
) -> None:
    result = _result()
    result.analysis_trace.append(
        {
            "stage": "interactive_review",
            "status": "applied",
            "tool": "openclaw_region_followup",
            "operation": "revise",
            "target_id": "f1",
            "bbox_source": "app_selected_original_roi",
            "user_confirmed": True,
            "local_signal_audit": {
                "status": "ok",
                "ink_pixel_ratio": 0.125,
                "low_signal": False,
            },
        }
    )
    panel = SummaryPanel()

    panel.update_result(result)

    receipt = panel._process_layout.itemAt(3).widget()
    assert receipt is not None
    assert "Operation: revise" in receipt.text()
    assert "Box source: app_selected_original_roi" in receipt.text()
    assert "Reviewer confirmation: recorded" in receipt.text()
    assert "Local signal audit: status=ok, ink=12.500%, low_signal=False" in (
        receipt.text()
    )
    panel.close()
