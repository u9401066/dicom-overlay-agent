from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from PIL import Image


def _load_module():
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "relabel-meeti-manifest.py"
    )
    spec = importlib.util.spec_from_file_location("relabel_meeti_manifest", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_relabel_preserves_source_and_writes_auditable_v2_manifest(
    tmp_path: Path,
) -> None:
    module = _load_module()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    Image.new("RGB", (8, 8), "white").save(source_dir / "case.png")
    source_manifest = source_dir / "manifest.json"
    source_manifest.write_text(
        json.dumps(
            {
                "dataset": "MEETI",
                "cases": [
                    {
                        "label": "case",
                        "image": "case.png",
                        "modality": "EKG",
                        "report": "ST elevation suggests early repolarization.",
                        "expected_severity": "critical",
                        "keywords": ["stemi"],
                        "cant_miss": ["STEMI"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "v2" / "manifest.json"

    result = module.relabel_manifest(
        manifest_path=source_manifest,
        output_path=output,
    )

    assert source_manifest.exists()
    assert result["labeling"]["schema_version"] == 2
    assert result["labeling"]["source_manifest_sha256"]
    assert result["labeling"]["classifier_sha256"]
    assert result["labeling"]["changed_cases"] == 1
    assert result["labeling"]["enriched_cases"] == 1
    case = result["cases"][0]
    assert case["expected_severity"] == "info"
    assert case["cant_miss"] == []
    assert "st_elevation" in case["uncertain_concepts"]
    assert "partially_uncertain" not in result["counts"]["by_concept"]
    assert result["counts"]["by_uncertain_concept"]["st_elevation"] == 1
    assert (output.parent / case["image"]).is_file()


def test_relabel_refuses_to_overwrite_source_manifest(tmp_path: Path) -> None:
    module = _load_module()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cases": []}), encoding="utf-8")

    try:
        module.relabel_manifest(manifest_path=manifest, output_path=manifest)
    except ValueError as exc:
        assert "differ" in str(exc)
    else:
        raise AssertionError("source overwrite should fail closed")
