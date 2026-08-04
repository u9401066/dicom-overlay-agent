"""Tests for one-click desktop review export."""

from __future__ import annotations

import base64
import io
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from PIL import Image

from dicom_overlay.domain.entities import (
    AnalysisResult,
    Finding,
    Modality,
    RegionRect,
    Severity,
    UserRegionAnnotation,
)
from dicom_overlay.infrastructure.desktop_review_exporter import (
    export_desktop_review,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_export_writes_original_coordinate_review_bundle(tmp_path: Path) -> None:
    image = Image.new("RGB", (800, 400), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    result = AnalysisResult(
        modality=Modality.EKG,
        summary="Review V2.",
        severity=Severity.WARNING,
        findings=[
            Finding(
                id="f1",
                regions=["lead_V2"],
                label="ST-T change",
                detail="Localized change.",
                severity=Severity.WARNING,
                bboxes=[RegionRect(0.25, 0.25, 0.25, 0.25)],
                confidence="low",
                question="Is this reproducible in the source viewer?",
                source="interactive_ai_review",
            )
        ],
        checklist={},
        image_quality={
            "adequacy": "limited",
            "issues": ["screenshot"],
            "detail": "Readable",
        },
        next_steps=["Review the original study."],
        analysis_trace=[{"stage": "coarse", "tools": ["dicom_bbox_validate"]}],
    )

    review_path = export_desktop_review(
        image_base64=base64.b64encode(buffer.getvalue()).decode("ascii"),
        result=result,
        output_root=tmp_path,
        user_regions=[RegionRect(0.6, 0.5, 0.2, 0.2)],
        user_annotations=[
            UserRegionAnnotation(
                region=RegionRect(0.1, 0.6, 0.2, 0.2),
                question="Is the baseline stable here?",
                answer="The crop remains indeterminate; verify on source ECG.",
            )
        ],
        now=datetime(2026, 7, 25, 4, 5, 6, tzinfo=UTC),
    )

    assert review_path.is_file()
    payload = json.loads((review_path.parent / "result.json").read_text("utf-8"))
    assert payload["coordinate_space"] == "normalized_original_roi"
    assert payload["source_image"]["width_px"] == 800
    assert payload["findings"][0]["bboxes"][0] == {
        "x": 0.25,
        "y": 0.25,
        "w": 0.25,
        "h": 0.25,
    }
    assert payload["findings"][1]["source"] == "user"
    assert payload["findings"][2]["label"] == "Reviewer annotation"
    assert payload["findings"][2]["question"] == "Is the baseline stable here?"
    assert payload["findings"][2]["answer"].startswith("The crop remains")
    assert "Regional AI response" in payload["findings"][2]["detail"]
    assert payload["findings"][0]["confidence"] == "low"
    assert payload["findings"][0]["question"].startswith("Is this")
    assert payload["findings"][0]["source"] == "interactive_ai_review"
    assert payload["image_quality"]["adequacy"] == "limited"
    assert payload["next_steps"] == ["Review the original study."]
    with Image.open(review_path) as review:
        assert review.width > 800
