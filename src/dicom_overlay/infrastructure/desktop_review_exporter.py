"""Export a desktop interpretation as source, JSON, and annotated review PNG."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from dicom_overlay.infrastructure.annotation_exporter import (
    BboxAudit,
    render_annotated_result_with_audit,
)

if TYPE_CHECKING:
    from medical_image_harness.models import (
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
    regional_conversations: dict[str, object] | None = None,
    now: datetime | None = None,
) -> Path:
    """Write one self-contained, coordinate-auditable desktop review folder."""
    raw = base64.b64decode(image_base64, validate=True)
    scientific_payload = None
    if result.workflow_events:
        try:
            scientific_payload = result.to_contract_payload()
            provenance = scientific_payload["input_provenance"]
            if (
                not isinstance(provenance, dict)
                or provenance.get("source_image_sha256")
                != hashlib.sha256(raw).hexdigest()
            ):
                raise ValueError("source_mismatch")
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ValueError("scientific_export_contract_invalid") from None
    if (
        regional_conversations is not None
        and regional_conversations.get("source_image_sha256")
        != hashlib.sha256(raw).hexdigest()
    ):
        raise ValueError("Regional conversation belongs to a different source image")
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
    review_path = folder / "review.png"
    crops_dir = folder / "crops"
    _, audit_records = render_annotated_result_with_audit(
        image_path=source_path,
        result=payload,
        output_path=review_path,
        crops_dir=crops_dir,
    )
    audit_payload = {
        "schema_version": 1,
        "case": case,
        "coordinate_space": "normalized_original_roi",
        "source_image_sha256": hashlib.sha256(raw).hexdigest(),
        "source_size_px": [width, height],
        "review_image": review_path.name,
        "records": [
            record.to_json() if isinstance(record, BboxAudit) else record
            for record in audit_records
        ],
    }
    audit_path = folder / "bbox-audit.json"
    audit_path.write_text(
        json.dumps(audit_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    payload["coordinate_audit"] = audit_path.name
    payload["crop_directory"] = crops_dir.name
    result_path = folder / "result.json"
    if scientific_payload is not None:
        contract_path = folder / "scientific-result.json"
        contract_path.write_text(
            json.dumps(
                scientific_payload, ensure_ascii=False, indent=2, allow_nan=False
            )
            + "\n",
            encoding="utf-8",
        )
        payload["scientific_contract"] = contract_path.name
        payload["scientific_contract_scope"] = (
            "analysis_ledger_only; manual annotations are separate review context"
        )
    elif result.input_provenance is not None:
        payload["scientific_contract_status"] = (
            "requires_reconciliation; not a canonical result"
        )
    if regional_conversations is not None:
        conversation_path = folder / "regional-conversations.json"
        conversation_path.write_text(
            json.dumps(regional_conversations, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        payload["regional_conversations"] = conversation_path.name
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with Image.open(review_path) as review:
        review.verify()
    return review_path
