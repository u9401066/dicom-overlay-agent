from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

from dicom_overlay.infrastructure.ecg_variant_corpus import build_variant_corpus


def _load_rebuild_module():
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "rebuild-eval-scorecard.py"
    )
    spec = importlib.util.spec_from_file_location(
        "rebuild_eval_scorecard_partial_manifest_script",
        script,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_partial_corpus(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    source = tmp_path / "source.png"
    Image.new("RGB", (120, 120), "white").save(source)
    corpus = tmp_path / "corpus"
    manifest = build_variant_corpus([source], corpus)
    return corpus, manifest


def test_load_cases_accepts_verified_partial_ecg_manifest(tmp_path: Path) -> None:
    module = _load_rebuild_module()
    corpus, manifest = _build_partial_corpus(tmp_path)

    cases = module._load_cases(corpus / "manifest.json")

    assert len(cases) == manifest["case_count"]
    assert all(case.partial_input is not None for case in cases)
    assert all(case.valid_regions == () for case in cases)


def test_load_cases_rejects_partial_ecg_root_digest_tamper(tmp_path: Path) -> None:
    module = _load_rebuild_module()
    corpus, manifest = _build_partial_corpus(tmp_path)
    manifest["manifest_sha256"] = "0" * 64
    (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest digest mismatch"):
        module._load_cases(corpus / "manifest.json")


def test_load_cases_rejects_partial_ecg_unmanifested_file(tmp_path: Path) -> None:
    module = _load_rebuild_module()
    corpus, _manifest = _build_partial_corpus(tmp_path)
    (corpus / "stale.png").write_bytes(b"stale")

    with pytest.raises(ValueError, match="stale or unmanifested"):
        module._load_cases(corpus / "manifest.json")
