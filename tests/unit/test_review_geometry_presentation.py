"""Offscreen real-Qt projection and exact App callbacks; no desktop/model claim."""

from __future__ import annotations

import ast
import asyncio
import base64
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

from dicom_overlay.application.overlay_agent import ReviewSnapshot
from dicom_overlay.application.regional_conversation import RegionalConversations
from dicom_overlay.domain.entities import DisplayFrame, WindowRect
from dicom_overlay.infrastructure.overlay_geometry import OverlayCoordinateFrame
from dicom_overlay.infrastructure.overlay_highlight_builder import (
    build_ai_bbox_highlights,
)
from dicom_overlay.presentation.overlay_window import OverlayWindow
from medical_image_harness.models import (
    AnalysisResult,
    Finding,
    Modality,
    RegionRect,
    Severity,
)


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def _compile_callbacks(names, env):
    path = Path(__file__).resolve().parents[2] / "src/dicom_overlay/__main__.py"
    nodes = [
        node
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), env)


def _snapshot():
    finding = Finding(
        id="f1",
        regions=["synthetic"],
        label="Synthetic finding",
        detail="Test only",
        severity=Severity.INFO,
        bboxes=[RegionRect(0.1, 0.2, 0.3, 0.4)],
    )
    result = AnalysisResult(
        modality=Modality.EKG,
        summary="Synthetic",
        severity=Severity.INFO,
        findings=[finding, replace(finding, id="fallback", bboxes=[])],
        checklist={},
    )
    return ReviewSnapshot(
        image_base64=base64.b64encode(b"synthetic pixels").decode(),
        result=result,
        capture_rect=WindowRect(100, 100, 400, 200),
        revision=1,
        display_rect=WindowRect(300, 200, 400, 200),
        display_window=WindowRect(280, 170, 500, 280),
        display_frame=DisplayFrame(WindowRect(0, 0, 1920, 1080)),
    )


def test_projection_moves_ai_fallback_and_manual_boxes_without_resetting_review(
    qt_app, monkeypatch
):
    snapshot = _snapshot()
    overlay = OverlayWindow()
    overlay.setGeometry(0, 0, 1536, 864)
    frame = OverlayCoordinateFrame(
        WindowRect(0, 0, 1920, 1080), WindowRect(0, 0, 1536, 864)
    )
    position = Mock(return_value=frame)
    monkeypatch.setattr(overlay, "position_over_window", position)
    overlay.show_result(snapshot.result, [], content_rect=(80, 80, 320, 160))
    region = RegionRect(0.1, 0.2, 0.3, 0.4)
    overlay._user_regions = [(region.x, region.y, region.w, region.h)]
    overlay.show_chat_response(
        "Question",
        "Answer",
        proposal_summary="Keep proposal",
        regional_history="Keep history",
    )
    overlay.chat_panel._followup_input.setText("Unsent follow-up")
    overlay.set_interaction_mode("annotate")
    overlay._selection_start = QPoint(10, 10)
    overlay._draft_rect = (10, 10, 30, 20)
    store = RegionalConversations()
    store.bind(snapshot.image_base64)
    store.append(store.thread(region), question="Question", answer="Answer")
    before = store.export()
    pending = [object()]
    active = [(region, "", True)]
    threads = {7: store.thread(region)}
    request_id = [7]
    mapper = Mock()
    mapper.get_region_rect.return_value = region
    mapper.to_screen_rect.side_effect = lambda box, rect: (
        int(rect.left + box.x * rect.width),
        int(rect.top + box.y * rect.height),
        int(box.w * rect.width),
        int(box.h * rect.height),
    )
    env = {
        "_current_review_snapshot": lambda: snapshot,
        "agent": Mock(),
        "_chat_request_id": request_id,
        "_pending_review": pending,
        "_active_region": active,
        "_pending_regional_threads": threads,
        "regional_conversations": store,
        "overlay": overlay,
        "logger": Mock(),
        "config": SimpleNamespace(
            overlay=SimpleNamespace(region_highlights=True, tts_enabled=True)
        ),
        "build_ai_bbox_highlights": build_ai_bbox_highlights,
        "region_mapper": mapper,
        "WindowRect": WindowRect,
        "control_bar": Mock(),
        "speak_result": Mock(),
        "auto_export_on_result": True,
        "on_export_review": Mock(),
    }
    try:
        _compile_callbacks({"on_analysis_result"}, env)
        env["on_analysis_result"](snapshot.result, projection_only=True)
        assert overlay._content_rect == (240, 160, 320, 160)
        assert len(overlay._highlights) == 3
        assert overlay._highlights[0][:4] == (272, 192, 96, 64)
        assert overlay._highlights[1][:4] == (272, 192, 96, 64)
        assert overlay.user_regions == [(0.1, 0.2, 0.3, 0.4)]
        assert overlay._highlights[2][:4] == (272, 192, 96, 64)
        assert overlay._selection_start is None and overlay._draft_rect is None
        assert overlay.chat_panel._followup_input.text() == "Unsent follow-up"
        assert "Keep proposal" in overlay.chat_panel._proposal_label.text()
        assert overlay.chat_panel._history.toPlainText() == "Keep history"
        assert store.export() == before and request_id == [7]
        assert pending[0] is not None and active[0] is not None and 7 in threads
        env["speak_result"].assert_not_called()
        env["on_export_review"].assert_not_called()
        assert not env["control_bar"].mock_calls
        position.assert_called_once_with(
            snapshot.display_window,
            snapshot.display_frame,
            preserve_panel_positions=True,
        )
        # A late initial result must not clear the current review either.
        env["on_analysis_result"](replace(snapshot.result, summary="Stale"))
        assert store.export() == before and request_id == [7]
    finally:
        overlay.invalidate_review()
        overlay.close()


@pytest.mark.parametrize("state", ["missing", "different_image", "newer_report"])
def test_queued_geometry_event_uses_only_current_same_image_snapshot(state):
    old = _snapshot()
    current = (
        None
        if state == "missing"
        else replace(
            old,
            image_base64="other" if state == "different_image" else old.image_base64,
            result=replace(old.result, summary="New report"),
            revision=2,
        )
    )
    env = {"_current_review_snapshot": lambda: current, "on_analysis_result": Mock()}
    _compile_callbacks({"on_review_geometry_changed"}, env)
    env["on_review_geometry_changed"](old)
    if state == "newer_report":
        env["on_analysis_result"].assert_called_once_with(
            current.result,
            announce=False,
            preserve_user_regions=True,
            projection_only=True,
        )
    else:
        env["on_analysis_result"].assert_not_called()


def test_same_screen_translation_retains_dragged_panel_positions(qt_app):
    overlay = OverlayWindow()
    try:
        overlay.position_over_window(WindowRect(0, 0, 500, 400))
        overlay.summary_panel.move(77, 88)
        overlay.chat_panel.move(99, 111)
        overlay.position_over_window(
            WindowRect(100, 100, 500, 400), preserve_panel_positions=True
        )
        assert overlay.summary_panel.pos() == QPoint(77, 88)
        assert overlay.chat_panel.pos() == QPoint(99, 111)
    finally:
        overlay.close()


def test_qt_display_signals_dispatch_invalidation_through_bridge(qt_app):
    screen = qt_app.primaryScreen()
    agent = Mock()
    overlay = Mock()
    env = {
        "agent": agent,
        "bridge": SimpleNamespace(submit=asyncio.run),
        "overlay": overlay,
    }
    _compile_callbacks({"_watch_display", "_display_configuration_changed"}, env)
    env["_watch_display"](screen)
    try:
        # Emit signals only; do not change the OS monitor or DPI configuration.
        screen.logicalDotsPerInchChanged.emit(144.0)
        screen.geometryChanged.emit(screen.geometry())
        assert agent.invalidate_display_geometry.call_count == 2
        assert overlay.invalidate_review.call_count == 2
    finally:
        screen.logicalDotsPerInchChanged.disconnect(
            env["_display_configuration_changed"]
        )
        screen.geometryChanged.disconnect(env["_display_configuration_changed"])
