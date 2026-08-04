"""End-to-end smoke for regional JSON proposal -> report -> annotated export."""

from __future__ import annotations

import base64
import io
import json
from datetime import UTC, datetime

from PIL import Image

from dicom_overlay.application.overlay_agent import OverlayAgent
from dicom_overlay.application.review_chat import parse_region_review_response
from dicom_overlay.domain.entities import (
    AgentState,
    AnalysisResult,
    AppConfig,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.infrastructure.desktop_review_exporter import (
    export_desktop_review,
)


class _UnusedDependency:
    """Constructor placeholder; this smoke exercises review state only."""


def test_reviewer_confirmed_crop_proposal_reaches_json_and_png(tmp_path) -> None:
    agent = OverlayAgent(
        config=AppConfig(),
        screen_monitor=_UnusedDependency(),  # type: ignore[arg-type]
        image_processor=_UnusedDependency(),  # type: ignore[arg-type]
        vision_analyzer=_UnusedDependency(),  # type: ignore[arg-type]
        region_mapper=_UnusedDependency(),  # type: ignore[arg-type]
    )
    initial = AnalysisResult(
        modality=Modality.EKG,
        summary="No focal finding in the initial report.",
        severity=Severity.NORMAL,
        findings=[],
        checklist={},
        model_used="openai/gpt-5.6-luna",
    )
    agent._last_result = initial
    agent._annotation_accumulator.reset([])
    agent._result_revision = 1
    agent._state = AgentState.DISPLAYING
    selected = RegionRect(0.2, 0.2, 0.25, 0.25)
    response = parse_region_review_response(
        json.dumps(
            {
                "answer": "The selected crop contains an unresolved ST-T change.",
                "proposal": {
                    "op": "add",
                    "label": "Unresolved ST-T change",
                    "detail": "Localized morphology warrants source-viewer review.",
                    "severity": "info",
                    "confidence": "low",
                    "question": "Is this reproducible at source resolution?",
                    "note": "Reviewer-directed crop re-read",
                },
            }
        ),
        selected_region=selected,
        selected_finding=None,
        new_finding_id="review-e2e",
        local_signal_audit={
            "status": "ok",
            "ink_pixel_ratio": 0.08,
            "low_signal": False,
        },
    )
    assert response.delta is not None
    updated = agent.apply_finding_delta(
        response.delta,
        expected_revision=1,
        local_signal_audit={
            "status": "ok",
            "ink_pixel_ratio": 0.08,
            "low_signal": False,
        },
    )

    image = Image.new("RGB", (800, 400), "white")
    image_buffer = io.BytesIO()
    image.save(image_buffer, format="PNG")
    review_path = export_desktop_review(
        image_base64=base64.b64encode(image_buffer.getvalue()).decode("ascii"),
        result=updated,
        output_root=tmp_path,
        now=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
    )

    payload = json.loads((review_path.parent / "result.json").read_text("utf-8"))
    exported = payload["findings"][0]
    assert exported["id"] == "review-e2e"
    assert exported["source"] == "interactive_ai_review"
    assert exported["bboxes"] == [{"x": 0.2, "y": 0.2, "w": 0.25, "h": 0.25}]
    assert payload["analysis_trace"][-1]["user_confirmed"] is True
    assert payload["analysis_trace"][-1]["bbox_source"] == (
        "reviewer_selected_original_roi"
    )
    assert payload["analysis_trace"][-1]["local_signal_audit"]["low_signal"] is False
    with Image.open(review_path) as review:
        assert review.size[0] > 800
        assert review.getpixel((160, 80)) != (255, 255, 255)
