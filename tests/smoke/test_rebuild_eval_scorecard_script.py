from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from PIL import Image


def _load_rebuild_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "rebuild-eval-scorecard.py"
    spec = importlib.util.spec_from_file_location("rebuild_eval_scorecard_script", script)
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
    eval_dir = tmp_path / "eval"
    results = eval_dir / "results"
    results.mkdir(parents=True)
    (results / "case_1.json").write_text(
        json.dumps(
            {
                "case": "case_1",
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
                "score": {"latency_ms": 1234},
            }
        ),
        encoding="utf-8",
    )

    output = module.rebuild_scorecard(eval_dir=eval_dir, manifest_path=manifest)

    scorecard = json.loads(output.read_text(encoding="utf-8"))
    assert output.name == "scorecard.rebuilt.json"
    assert scorecard["manifest_total"] == 1
    assert scorecard["result_count"] == 1
    assert scorecard["missing_cases"] == []
    assert scorecard["is_partial"] is False
    assert scorecard["mean_partial_credit"] == 1.0
    assert scorecard["strict_pass_rate"] == 1.0
    assert scorecard["target_axis_performance"]["ischemia"]["case_count"] == 1
    assert scorecard["cases"][0]["partial_credit"] == 1.0
