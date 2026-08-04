"""Export a desktop interpretation as source, JSON, and annotated review PNG."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from dicom_overlay.infrastructure.annotation_exporter import render_annotated_result

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import (
        AnalysisResult,
        RegionRect,
        UserRegionAnnotation,
    )


def _finding_payload(result: AnalysisResult) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for finding in result.findings:
        findings.append(
            {
                "id": finding.id,
                "regions": list(finding.regions),
                "label": finding.label,
                "detail": finding.detail,
                "severity": finding.severity.value,
                "bboxes": [
                    {"x": box.x, "y": box.y, "w": box.w, "h": box.h}
                    for box in finding.bboxes
                ],
                "notes": list(finding.notes),
                "confidence": finding.confidence,
                "question": finding.question,
                "source": finding.source,
            }
        )
    return findings


def export_desktop_review(
    *,
    image_base64: str,
    result: AnalysisResult,
    output_root: Path,
    user_regions: list[RegionRect] | None = None,
    user_annotations: list[UserRegionAnnotation] | None = None,
    now: datetime | None = None,
) -> Path:
    """Write one self-contained, coordinate-auditable desktop review folder."""
    raw = base64.b64decode(image_base64, validate=True)
    captured_at = now or datetime.now(UTC)
    stamp = captured_at.strftime("%Y%m%d-%H%M%S-%f")
    case = f"desktop-{stamp}"
    folder = Path(output_root) / case
    folder.mkdir(parents=True, exist_ok=False)

    source_path = folder / "source.png"
    source_path.write_bytes(raw)
    with Image.open(source_path) as source:
        source.verify()
    with Image.open(source_path) as source:
        width, height = source.size

    findings = _finding_payload(result)
    for index, region in enumerate(user_regions or [], start=1):
        findings.append(
            {
                "id": f"user-{index}",
                "regions": ["user_selected"],
                "label": "User region",
                "detail": "Region selected manually for expert review.",
                "severity": "info",
                "bboxes": [
                    {
                        "x": region.x,
                        "y": region.y,
                        "w": region.w,
                        "h": region.h,
                    }
                ],
                "notes": [],
                "source": "user",
            }
        )
    annotation_offset = len(user_regions or [])
    for index, annotation in enumerate(user_annotations or [], start=1):
        question = annotation.question.strip()
        answer = annotation.answer.strip()
        detail_parts = []
        if question:
            detail_parts.append(f"Reviewer question/observation: {question}")
        if answer:
            detail_parts.append(f"Regional AI response: {answer}")
        findings.append(
            {
                "id": f"user-{annotation_offset + index}",
                "regions": ["user_selected"],
                "label": "Reviewer annotation" if detail_parts else "User region",
                "detail": (
                    "\n".join(detail_parts)
                    if detail_parts
                    else "Region selected manually for expert review."
                ),
                "severity": "info",
                "bboxes": [
                    {
                        "x": annotation.region.x,
                        "y": annotation.region.y,
                        "w": annotation.region.w,
                        "h": annotation.region.h,
                    }
                ],
                "notes": [],
                "question": question,
                "answer": answer,
                "source": "user",
            }
        )

    payload: dict[str, object] = {
        "case": case,
        "created_at": captured_at.isoformat(),
        "coordinate_space": "normalized_original_roi",
        "source_image": {
            "path": source_path.name,
            "width_px": width,
            "height_px": height,
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        "modality": result.modality.value,
        "summary": result.summary,
        "severity": result.severity.value,
        "findings": findings,
        "checklist": {
            key: {"value": item.value, "status": item.status.value}
            for key, item in result.checklist.items()
        },
        "analysis_time_ms": result.analysis_time_ms,
        "model_used": result.model_used,
        "image_quality": result.image_quality,
        "next_steps": list(result.next_steps),
        "incomplete": result.incomplete,
        "incomplete_reasons": list(result.incomplete_reasons),
        "validation_warnings": list(result.validation_warnings),
        "review_required": result.review_required,
        "review_reasons": list(result.review_reasons),
        "layout": result.layout,
        "analysis_trace": result.analysis_trace,
    }
    result_path = folder / "result.json"
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    review_path = folder / "review.png"
    render_annotated_result(
        image_path=source_path,
        result=payload,
        output_path=review_path,
    )
    with Image.open(review_path) as review:
        review.verify()
    return review_path
