from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from PIL import Image


def _load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "build-eval-subset.py"
    spec = importlib.util.spec_from_file_location("build_eval_subset", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_subset_is_deterministic_stratified_and_relocatable(
    tmp_path: Path,
) -> None:
    module = _load_module()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    cases = []
    for severity in ("normal", "warning", "critical"):
        for index in range(4):
            image = source_dir / f"{severity}-{index}.png"
            Image.new("RGB", (4, 4), "white").save(image)
            cases.append(
                {
                    "label": f"{severity}-{index}",
                    "image": image.name,
                    "expected_severity": severity,
                }
            )
    manifest = source_dir / "manifest.json"
    manifest.write_text(json.dumps({"dataset": "test", "cases": cases}))
    first = tmp_path / "subsets" / "first.json"
    second = tmp_path / "subsets" / "second.json"

    first_result = module.build_subset(
        manifest_path=manifest,
        output_path=first,
        severity_counts={"normal": 2, "warning": 2, "critical": 2},
        seed=17,
    )
    second_result = module.build_subset(
        manifest_path=manifest,
        output_path=second,
        severity_counts={"normal": 2, "warning": 2, "critical": 2},
        seed=17,
    )

    assert [row["label"] for row in first_result["cases"]] == [
        row["label"] for row in second_result["cases"]
    ]
    assert first_result["counts"]["by_severity"] == {
        "critical": 2,
        "normal": 2,
        "warning": 2,
    }
    assert [row["expected_severity"] for row in first_result["cases"]] == [
        "normal",
        "warning",
        "critical",
        "normal",
        "warning",
        "critical",
    ]
    for row in first_result["cases"]:
        assert (first.parent / row["image"]).is_file()
