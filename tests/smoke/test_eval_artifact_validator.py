from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from dicom_overlay.infrastructure.eval_artifact_validator import (
    verify_eval_artifacts,
)


def _write_manifest(path: Path, count: int) -> None:
    cases = [
        {
            "image": f"cxr/{i:04d}.png",
            "modality": "CXR",
            "expected_severity": "normal",
            "label": f"public_cxr_{i:04d}",
        }
        for i in range(count)
    ]
    path.write_text(
        json.dumps(
            {
                "dataset": "public-cxr",
                "source": {
                    "type": "huggingface",
                    "dataset_id": "hf-vision/chest-xray-pneumonia",
                },
                "cases": cases,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_scorecard(eval_dir: Path, count: int, **overrides: object) -> None:
    payload = {
        "gateway_mode": "mock",
        "total": count,
        "scored": count,
        "error_count": 0,
        "schema_pass_rate": 1.0,
        "bbox_in_bounds_rate": 1.0,
        "strict_pass_rate": 1.0,
        "cant_miss_missed": [],
        "manifest_total": count,
        "result_count": count,
        "is_partial": False,
        "cases": [
            {
                "case_label": f"public_cxr_{i:04d}",
                "schema_ok": True,
                "bbox_in_bounds": True,
                "strict_pass": True,
            }
            for i in range(count)
        ],
    }
    payload.update(overrides)
    eval_dir.mkdir(parents=True)
    (eval_dir / "scorecard.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    results = eval_dir / "results"
    results.mkdir()
    for i in range(count):
        (results / f"public_cxr_{i:04d}.json").write_text(
            json.dumps(
                {
                    "case": f"public_cxr_{i:04d}",
                    "local_image_quality": {"low_signal": False},
                }
            ),
            encoding="utf-8",
        )
    review = eval_dir / "review"
    review.mkdir()
    (review / "index.html").write_text("<html></html>", encoding="utf-8")
    (review / "bbox-audit.jsonl").write_text(
        "\n".join(json.dumps({"case": f"public_cxr_{i:04d}"}) for i in range(count))
        + "\n",
        encoding="utf-8",
    )


def test_verify_eval_artifacts_accepts_complete_1000_case_run(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 1000)
    _write_scorecard(eval_dir, 1000)

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest,
        min_cases=1000,
    )

    assert verification.ok
    assert "min_cases" in verification.passed_checks
    assert "scorecard_complete" in verification.passed_checks
    assert "review_artifacts" in verification.passed_checks


def test_verify_eval_artifacts_rejects_partial_large_run(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 1000)
    _write_scorecard(
        eval_dir,
        800,
        manifest_total=1000,
        result_count=800,
        is_partial=True,
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest,
        min_cases=1000,
    )

    assert not verification.ok
    assert any("partial" in failure for failure in verification.failures)
    assert any("result_count" in failure for failure in verification.failures)


def test_verify_eval_artifacts_rejects_missing_review_audit(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 1000)
    _write_scorecard(eval_dir, 1000)
    (eval_dir / "review" / "bbox-audit.jsonl").unlink()

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest,
        min_cases=1000,
    )

    assert not verification.ok
    assert any("bbox-audit" in failure for failure in verification.failures)


def test_verify_eval_artifacts_rejects_missing_local_preflight(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 1000)
    _write_scorecard(eval_dir, 1000)
    (eval_dir / "results" / "public_cxr_0000.json").write_text(
        json.dumps({"case": "public_cxr_0000"}),
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest,
        min_cases=1000,
    )

    assert not verification.ok
    assert any("local_image_quality" in failure for failure in verification.failures)


def test_verify_eval_artifacts_requires_unique_reviewed_cases(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 1000)
    _write_scorecard(eval_dir, 1000)
    (eval_dir / "review" / "bbox-audit.jsonl").write_text(
        "\n".join(json.dumps({"case": "public_cxr_0000"}) for _ in range(1000))
        + "\n",
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest,
        min_cases=1000,
    )

    assert not verification.ok
    assert any("unique reviewed cases" in failure for failure in verification.failures)


def test_verify_eval_artifacts_cli_returns_zero_for_complete_run(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 1000)
    _write_scorecard(eval_dir, 1000)
    script = Path(__file__).resolve().parents[2] / "scripts" / "verify-eval-artifacts.py"

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--eval-dir",
            str(eval_dir),
            "--manifest",
            str(manifest),
            "--min-cases",
            "1000",
        ],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
