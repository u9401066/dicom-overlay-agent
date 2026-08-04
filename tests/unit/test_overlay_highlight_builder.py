from __future__ import annotations

from dicom_overlay.domain.entities import Finding, RegionRect, Severity, WindowRect
from dicom_overlay.infrastructure.overlay_highlight_builder import (
    build_ai_bbox_highlights,
)


def test_ai_bbox_highlight_builder_draws_calibrated_boxes_with_audit() -> None:
    finding = Finding(
        id="f1",
        regions=[],
        label="ST depression",
        detail="inferior ST depression",
        severity=Severity.WARNING,
        bboxes=[RegionRect(x=0.1, y=0.2, w=0.3, h=0.2)],
    )

    result = build_ai_bbox_highlights(
        findings=[finding],
        image_rect=WindowRect(left=0, top=0, width=1000, height=800),
        dpr=1.0,
    )

    assert result.highlights == [(100, 160, 300, 160, "warning", "ST depression")]
    assert len(result.audit_rows) == 1
    row = result.audit_rows[0]
    assert row.finding_id == "f1"
    assert row.drawn is True
    assert row.calibration.ok is True
    assert row.to_dict()["drawn"] is True
    assert row.to_dict()["label"] == "ST depression"


def test_ai_bbox_highlight_builder_does_not_draw_failed_drift_calibration() -> None:
    finding = Finding(
        id="f2",
        regions=[],
        label="borderline drift",
        detail="bbox should be withheld if projection is not calibrated",
        severity=Severity.CRITICAL,
        bboxes=[RegionRect(x=0.123, y=0.234, w=0.345, h=0.222)],
    )

    result = build_ai_bbox_highlights(
        findings=[finding],
        image_rect=WindowRect(left=101, top=53, width=777, height=503),
        dpr=1.25,
        max_roundtrip_drift_px=0.0,
    )

    assert result.highlights == []
    assert len(result.audit_rows) == 1
    row = result.audit_rows[0]
    assert row.finding_id == "f2"
    assert row.drawn is False
    assert row.calibration.ok is False
    assert row.to_dict()["drawn"] is False
    assert row.to_dict()["max_edge_drift_px"] > 0


def test_ai_bbox_highlight_builder_draws_info_box_for_uncertainty_review() -> None:
    finding = Finding(
        id="uncertain-1",
        regions=[],
        label="Review possible ST change",
        detail="Uncertain area requires reviewer confirmation",
        severity=Severity.INFO,
        bboxes=[RegionRect(x=0.2, y=0.3, w=0.2, h=0.1)],
        question="Is this true ST depression or artifact?",
    )

    result = build_ai_bbox_highlights(
        findings=[finding],
        image_rect=WindowRect(left=0, top=0, width=1000, height=800),
        dpr=1.0,
    )

    assert result.highlights == [
        (200, 240, 200, 80, "info", "Review possible ST change")
    ]
    assert result.audit_rows[0].drawn is True
