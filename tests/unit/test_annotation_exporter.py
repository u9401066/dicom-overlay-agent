from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from dicom_overlay.infrastructure.annotation_exporter import export_eval_annotations


def test_export_eval_annotations_draws_boxes_and_description_panel(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset"
    image_dir = dataset / "ekg"
    image_dir.mkdir(parents=True)
    source = image_dir / "case.png"
    Image.new("RGB", (100, 80), "white").save(source)
    manifest = dataset / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "label": "case_1",
                        "image": "ekg/case.png",
                        "modality": "EKG",
                        "expected_severity": "warning",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    eval_dir = tmp_path / "eval"
    results = eval_dir / "results"
    results.mkdir(parents=True)
    (results / "case_1.json").write_text(
        json.dumps(
            {
                "case": "case_1",
                "image": "case.png",
                "modality": "EKG",
                "summary": "Important review finding.",
                "severity": "warning",
                "findings": [
                    {
                        "id": "f1",
                        "label": "ST depression",
                        "detail": "Inferolateral ST depression.",
                        "severity": "warning",
                        "regions": ["lead_II"],
                        "bboxes": [{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}],
                    }
                ],
                "checklist": {},
            }
        ),
        encoding="utf-8",
    )

    output_paths = export_eval_annotations(
        eval_dir=eval_dir,
        manifest_path=manifest,
        output_dir=eval_dir / "review",
    )

    assert len(output_paths) == 1
    annotated = Image.open(output_paths[0])
    assert annotated.size[0] > 100
    assert annotated.size[1] == 80
    assert annotated.getpixel((10, 16)) != (255, 255, 255)
    assert (eval_dir / "review" / "index.html").exists()


def test_export_eval_annotations_writes_bbox_audit_and_crops(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset"
    image_dir = dataset / "ekg"
    image_dir.mkdir(parents=True)
    source = image_dir / "case.png"
    image = Image.new("RGB", (100, 80), "white")
    draw = ImageDraw.Draw(image)
    draw.line((10, 20, 40, 20), fill="black", width=4)
    image.save(source)
    manifest = dataset / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "label": "case_1",
                        "image": "ekg/case.png",
                        "modality": "EKG",
                        "expected_severity": "warning",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    eval_dir = tmp_path / "eval"
    results = eval_dir / "results"
    results.mkdir(parents=True)
    (results / "case_1.json").write_text(
        json.dumps(
            {
                "case": "case_1",
                "image": "case.png",
                "modality": "EKG",
                "summary": "Two boxes, one over waveform and one blank.",
                "severity": "warning",
                "findings": [
                    {
                        "id": "f1",
                        "label": "waveform box",
                        "detail": "Over dark ECG trace.",
                        "severity": "warning",
                        "regions": ["lead_I"],
                        "bboxes": [
                            {"x": 0.08, "y": 0.18, "w": 0.35, "h": 0.15},
                            {"x": 0.70, "y": 0.70, "w": 0.20, "h": 0.20},
                        ],
                    }
                ],
                "checklist": {},
            }
        ),
        encoding="utf-8",
    )

    export_eval_annotations(
        eval_dir=eval_dir,
        manifest_path=manifest,
        output_dir=eval_dir / "review",
    )

    audit_path = eval_dir / "review" / "bbox-audit.jsonl"
    assert audit_path.exists()
    audit_rows = [
        json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(audit_rows) == 2
    assert audit_rows[0]["low_signal"] is False
    assert audit_rows[1]["low_signal"] is True
    assert audit_rows[0]["pixels"] == {"x0": 8, "y0": 14, "x1": 43, "y1": 26}
    assert Path(audit_rows[0]["crop"]).name == "case_1-f01-b01.png"
    assert (eval_dir / "review" / "crops" / "case_1-f01-b01.png").exists()
    assert (eval_dir / "review" / "crops" / "case_1-f01-b02.png").exists()


def test_export_eval_annotations_audits_clamped_overflow_bbox(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset"
    image_dir = dataset / "ekg"
    image_dir.mkdir(parents=True)
    Image.new("RGB", (100, 80), "white").save(image_dir / "case.png")
    manifest = dataset / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "label": "case_1",
                        "image": "ekg/case.png",
                        "modality": "EKG",
                        "expected_severity": "warning",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    eval_dir = tmp_path / "eval"
    results = eval_dir / "results"
    results.mkdir(parents=True)
    (results / "case_1.json").write_text(
        json.dumps(
            {
                "case": "case_1",
                "image": "case.png",
                "modality": "EKG",
                "summary": "Overflow bbox.",
                "severity": "warning",
                "findings": [
                    {
                        "id": "f1",
                        "label": "overflow",
                        "detail": "Bbox extends beyond the image.",
                        "severity": "warning",
                        "regions": ["lead_I"],
                        "bboxes": [{"x": 0.9, "y": 0.8, "w": 0.3, "h": 0.4}],
                    }
                ],
                "checklist": {},
            }
        ),
        encoding="utf-8",
    )

    export_eval_annotations(
        eval_dir=eval_dir,
        manifest_path=manifest,
        output_dir=eval_dir / "review",
    )

    audit_row = json.loads(
        (eval_dir / "review" / "bbox-audit.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert audit_row["normalized"] == {"x": 0.9, "y": 0.8, "w": 0.3, "h": 0.4}
    assert audit_row["clamped_normalized"] == {
        "x": 0.9,
        "y": 0.8,
        "w": 0.1,
        "h": 0.2,
    }
    assert audit_row["pixels"] == {"x0": 90, "y0": 64, "x1": 100, "y1": 80}
    assert audit_row["was_clamped"] is True
    assert audit_row["invalid_reason"] == "extent_out_of_bounds"


def test_export_eval_annotations_removes_stale_generated_review_artifacts(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset"
    image_dir = dataset / "ekg"
    image_dir.mkdir(parents=True)
    Image.new("RGB", (100, 80), "white").save(image_dir / "case.png")
    manifest = dataset / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "label": "case_1",
                        "image": "ekg/case.png",
                        "modality": "EKG",
                        "expected_severity": "normal",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    eval_dir = tmp_path / "eval"
    results = eval_dir / "results"
    results.mkdir(parents=True)
    (results / "case_1.json").write_text(
        json.dumps(
            {
                "case": "case_1",
                "image": "case.png",
                "modality": "EKG",
                "summary": "Normal sinus rhythm.",
                "severity": "normal",
                "findings": [],
                "checklist": {},
            }
        ),
        encoding="utf-8",
    )
    review = eval_dir / "review"
    crops = review / "crops"
    crops.mkdir(parents=True)
    stale_review = review / "stale.review.png"
    stale_crop = crops / "stale-f01-b01.png"
    stale_review.write_bytes(b"old")
    stale_crop.write_bytes(b"old")
    keep_note = review / "expert-note.txt"
    keep_note.write_text("human note", encoding="utf-8")

    output_paths = export_eval_annotations(
        eval_dir=eval_dir,
        manifest_path=manifest,
        output_dir=review,
    )

    assert len(output_paths) == 1
    assert not stale_review.exists()
    assert not stale_crop.exists()
    assert keep_note.read_text(encoding="utf-8") == "human note"

    audit_rows = [
        json.loads(line)
        for line in (review / "bbox-audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert audit_rows == [
        {
            "audit_type": "case",
            "case": "case_1",
            "bbox_count": 0,
            "finding_count": 0,
            "review_image": "case_1.review.png",
        }
    ]
