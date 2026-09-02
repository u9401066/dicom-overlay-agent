from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

from dicom_overlay.infrastructure.eval_artifact_validator import (
    verify_eval_artifacts,
)


def _write_manifest(path: Path, count: int) -> None:
    image_dir = path.parent / "cxr"
    image_dir.mkdir(parents=True, exist_ok=True)
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "white").save(buffer, format="PNG")
    image_bytes = buffer.getvalue()
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
    for index in range(count):
        (image_dir / f"{index:04d}.png").write_bytes(image_bytes)


def _write_scorecard(eval_dir: Path, count: int, **overrides: object) -> None:
    manifest_path = eval_dir.parent / "manifest.json"
    image_path = manifest_path.parent / "cxr" / "0000.png"
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    image_size = image_path.stat().st_size
    protocol = {
        "source": {
            "commit": "abc123",
            "dirty": False,
            "tracked_diff_sha256": hashlib.sha256(b"").hexdigest(),
        },
        "model": {
            "id": "mock-eval-gateway",
            "openclaw": {"version": "test"},
        },
        "prompts": [{"path": "prompt.py", "sha256": "0" * 64}],
        "skills": [{"path": "skills/test/SKILL.md", "sha256": "1" * 64}],
        "flags": {"multi_pass": False},
        "manifest": {
            "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "selected_case_count": count,
            "cases": [
                {
                    "case": f"public_cxr_{index:04d}",
                    "image": f"cxr/{index:04d}.png",
                    "image_name": f"{index:04d}.png",
                    "size_bytes": image_size,
                    "sha256": image_sha256,
                }
                for index in range(count)
            ],
        },
    }
    protocol_digest = hashlib.sha256(
        json.dumps(
            protocol,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    payload = {
        "gateway_mode": "mock",
        "scorecard_kind": "full_rebuild",
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
        "missing_cases": [],
        "protocol_digest": protocol_digest,
        "protocol_comparability": {
            "status": "comparable",
            "comparable": True,
            "reasons": [],
        },
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
    (eval_dir / "protocol-fingerprint.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "protocol_scope": "entire_run",
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
                    "image": f"{i:04d}.png",
                    "protocol_digest": protocol_digest,
                    "source_image_sha256": image_sha256,
                    "findings": [],
                    "local_image_quality": {"low_signal": False},
                    "local_signal_candidates": {
                        "candidate_count": 1,
                        "candidates": [
                            {
                                "label": "local_signal",
                                "x": 0.1,
                                "y": 0.2,
                                "w": 0.7,
                                "h": 0.2,
                                "confidence": 0.5,
                            }
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
    review = eval_dir / "review"
    review.mkdir()
    (review / "index.html").write_text("<html></html>", encoding="utf-8")
    review_png = (manifest_path.parent / "cxr" / "0000.png").read_bytes()
    for index in range(count):
        (review / f"public_cxr_{index:04d}.review.png").write_bytes(review_png)
    (review / "bbox-audit.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "audit_type": "case",
                    "case": f"public_cxr_{i:04d}",
                    "bbox_count": 0,
                    "finding_count": 0,
                    "review_image": f"public_cxr_{i:04d}.review.png",
                }
            )
            for i in range(count)
        )
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


def test_verify_eval_artifacts_rejects_missed_urgent_concern(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 5)
    _write_scorecard(
        eval_dir,
        5,
        urgent_concern_missed=["public_cxr_0000: tension pneumothorax"],
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest,
        min_cases=5,
    )

    assert not verification.ok
    assert any("urgent_concern_gate" in item for item in verification.failures)


def test_verify_eval_artifacts_can_record_safety_misses_as_outcomes(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 5)
    _write_scorecard(
        eval_dir,
        5,
        cant_miss_missed=["public_cxr_0000: ventricular tachycardia"],
        urgent_concern_missed=["public_cxr_0001: STEMI"],
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest,
        min_cases=5,
        require_zero_safety_misses=False,
    )

    assert verification.ok
    assert "cant_miss_metrics_recorded" in verification.passed_checks
    assert "urgent_concern_metrics_recorded" in verification.passed_checks


def test_verify_eval_artifacts_rejects_missing_review_audit(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 5)
    _write_scorecard(eval_dir, 5)
    (eval_dir / "review" / "bbox-audit.jsonl").unlink()

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest,
        min_cases=5,
    )

    assert not verification.ok
    assert any("bbox-audit" in failure for failure in verification.failures)


def test_verify_eval_artifacts_rejects_missing_local_preflight(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 5)
    _write_scorecard(eval_dir, 5)
    (eval_dir / "results" / "public_cxr_0000.json").write_text(
        json.dumps({"case": "public_cxr_0000"}),
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest,
        min_cases=5,
    )

    assert not verification.ok
    assert any("local_image_quality" in failure for failure in verification.failures)


def test_verify_eval_artifacts_rejects_missing_local_signal_candidates(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 5)
    _write_scorecard(eval_dir, 5)
    (eval_dir / "results" / "public_cxr_0000.json").write_text(
        json.dumps(
            {
                "case": "public_cxr_0000",
                "local_image_quality": {"low_signal": False},
            }
        ),
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest,
        min_cases=5,
    )

    assert not verification.ok
    assert any(
        "local_signal_candidates" in failure for failure in verification.failures
    )


def test_verify_eval_artifacts_requires_unique_reviewed_cases(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 5)
    _write_scorecard(eval_dir, 5)
    (eval_dir / "review" / "bbox-audit.jsonl").write_text(
        "\n".join(json.dumps({"case": "public_cxr_0000"}) for _ in range(5)) + "\n",
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest,
        min_cases=5,
    )

    assert not verification.ok
    assert any(
        "bbox audit case set is not exact" in failure
        for failure in verification.failures
    )


def test_verify_eval_artifacts_cli_returns_zero_for_complete_run(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 5)
    _write_scorecard(eval_dir, 5)
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "verify-eval-artifacts.py"
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--eval-dir",
            str(eval_dir),
            "--manifest",
            str(manifest),
            "--min-cases",
            "5",
        ],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True


def test_verify_eval_artifacts_cli_can_require_multipass_trace(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 5)
    _write_scorecard(eval_dir, 5)
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "verify-eval-artifacts.py"
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--eval-dir",
            str(eval_dir),
            "--manifest",
            str(manifest),
            "--min-cases",
            "5",
            "--require-multipass-trace",
        ],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert (
        "multipass_trace_artifacts: missing multipass-trace.jsonl"
        in payload["failures"]
    )
