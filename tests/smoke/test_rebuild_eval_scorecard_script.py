from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image


def _load_rebuild_module():
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "rebuild-eval-scorecard.py"
    )
    spec = importlib.util.spec_from_file_location(
        "rebuild_eval_scorecard_script", script
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rebuild_scorecard_from_raw_results_adds_partial_credit(
    tmp_path: Path,
) -> None:
    module = _load_rebuild_module()
    dataset = tmp_path / "dataset"
    image_dir = dataset / "ekg"
    image_dir.mkdir(parents=True)
    Image.new("RGB", (10, 10), "white").save(image_dir / "case.png")
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
                        "keywords": ["ischemia"],
                        "target_axes": ["ischemia"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    image_path = image_dir / "case.png"
    protocol = {
        "manifest": {
            "sha256": module._sha256_file(manifest),
            "selected_case_count": 1,
            "cases": [
                {
                    "case": "case_1",
                    "image": "ekg/case.png",
                    "image_name": "case.png",
                    "size_bytes": image_path.stat().st_size,
                    "sha256": module._sha256_file(image_path),
                }
            ],
        }
    }
    protocol_digest = module._protocol_digest(protocol)
    eval_dir = tmp_path / "eval"
    results = eval_dir / "results"
    results.mkdir(parents=True)
    (eval_dir / "protocol-fingerprint.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "protocol_digest": protocol_digest,
                "comparability": {
                    "status": "comparable",
                    "comparable": True,
                    "reasons": [],
                },
                "protocol": protocol,
            }
        ),
        encoding="utf-8",
    )
    (results / "case_1.json").write_text(
        json.dumps(
            {
                "case": "case_1",
                "image": "case.png",
                "modality": "EKG",
                "summary": "ST depression suggesting ischemia.",
                "severity": "warning",
                "model_used": "test-model",
                "findings": [],
                "checklist": {
                    key: {"value": "normal", "status": "normal"}
                    for key in (
                        "heart_rate",
                        "rhythm",
                        "regularity",
                        "axis",
                        "p_wave",
                        "pr_interval",
                        "qrs_duration",
                        "qrs_morphology",
                        "st_segment",
                        "t_wave",
                        "qtc_interval",
                        "chamber_enlargement",
                        "conduction",
                        "av_block",
                        "stemi_pattern",
                        "ischemia",
                    )
                }
                | {"ischemia": {"value": "st_depression", "status": "warning"}},
                "score": {"latency_ms": 1234, "image": "case.png"},
                "protocol_digest": protocol_digest,
                "source_image_sha256": module._sha256_file(image_path),
            }
        ),
        encoding="utf-8",
    )

    output = module.rebuild_scorecard(
        eval_dir=eval_dir,
        manifest_path=manifest,
        promote_canonical=True,
        require_protocol_fingerprint=True,
    )

    scorecard = json.loads(output.read_text(encoding="utf-8"))
    assert output.name == "scorecard.rebuilt.json"
    assert scorecard["manifest_total"] == 1
    assert scorecard["result_count"] == 1
    assert scorecard["missing_cases"] == []
    assert scorecard["is_partial"] is False
    assert scorecard["mean_partial_credit"] == pytest.approx(0.816)
    assert scorecard["strict_pass_rate"] == 0.0
    assert scorecard["target_axis_performance"]["ischemia"]["case_count"] == 1
    assert scorecard["cases"][0]["partial_credit"] == pytest.approx(0.816)
    assert scorecard["scorecard_kind"] == "full_rebuild"
    assert scorecard["protocol_digest"] == protocol_digest
    assert json.loads((eval_dir / "scorecard.json").read_text(encoding="utf-8")) == (
        scorecard
    )


def test_promote_canonical_requires_protocol_fingerprint(tmp_path: Path) -> None:
    module = _load_rebuild_module()

    with pytest.raises(ValueError, match="missing required protocol fingerprint"):
        module.rebuild_scorecard(
            eval_dir=tmp_path / "eval",
            manifest_path=tmp_path / "manifest.json",
            promote_canonical=True,
            require_protocol_fingerprint=True,
        )


def test_analysis_result_rebuild_preserves_report_and_uncertainty_contract() -> None:
    module = _load_rebuild_module()
    raw = {
        "modality": "EKG",
        "summary": "Possible anterior T-wave inversion.",
        "severity": "warning",
        "analysis_time_ms": 321,
        "model_used": "openai/gpt-5.6-luna",
        "image_quality": {"adequacy": "limited", "issues": ["artifact"]},
        "next_steps": ["Confirm on a clean tracing."],
        "incomplete": True,
        "incomplete_reasons": ["No calibration marker."],
        "validation_warnings": [],
        "review_required": True,
        "review_reasons": ["Human confirmation required."],
        "layout": {"format": "12x1"},
        "analysis_trace": [{"stage": "refine", "crop_source": "original_roi"}],
        "zoom_hints": ["Capture V3-V4 at native resolution."],
        "findings": [
            {
                "id": "f1",
                "label": "Possible anterior T-wave inversion",
                "detail": "Subtle morphology in V3-V4.",
                "severity": "info",
                "regions": ["lead_V3", "lead_V4"],
                "bboxes": [{"x": 0.1, "y": 0.2, "w": 0.1, "h": 0.1}],
                "notes": ["Refined on source pixels."],
                "confidence": "low",
                "question": "Is this reproducible on the source ECG?",
            }
        ],
        "checklist": {},
    }

    result = module._analysis_result_from_raw(
        raw,
        fallback_modality=module.Modality.EKG,
    )

    assert result.analysis_time_ms == 321
    assert result.image_quality == raw["image_quality"]
    assert result.next_steps == raw["next_steps"]
    assert result.incomplete is True
    assert result.incomplete_reasons == raw["incomplete_reasons"]
    assert result.review_required is True
    assert result.review_reasons == raw["review_reasons"]
    assert result.layout == raw["layout"]
    assert result.analysis_trace == raw["analysis_trace"]
    assert result.zoom_hints == raw["zoom_hints"]
    assert result.findings[0].notes == ["Refined on source pixels."]
    assert result.findings[0].confidence == "low"
    assert result.findings[0].question == "Is this reproducible on the source ECG?"
