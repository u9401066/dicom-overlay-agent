from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from dicom_overlay.infrastructure.real_model_readiness import (
    assess_real_model_readiness,
)


def _write_manifest(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "dataset": "meeti-1000-all",
                "cases": [
                    {
                        "image": f"images/{i:04d}.png",
                        "modality": "EKG",
                        "expected_severity": "normal",
                        "label": f"meeti_{i:04d}",
                    }
                    for i in range(count)
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_eval_artifacts(eval_dir: Path, count: int) -> None:
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / "scorecard.json").write_text(
        json.dumps(
            {
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
                        "case_label": f"meeti_{i:04d}",
                        "schema_ok": True,
                        "bbox_in_bounds": True,
                        "strict_pass": True,
                    }
                    for i in range(count)
                ],
            }
        ),
        encoding="utf-8",
    )
    results = eval_dir / "results"
    results.mkdir()
    for i in range(count):
        (results / f"meeti_{i:04d}.json").write_text(
            json.dumps(
                {
                    "case": f"meeti_{i:04d}",
                    "local_image_quality": {"low_signal": False},
                    "local_signal_candidates": {
                        "candidate_count": 1,
                        "candidates": [{"label": "local_signal"}],
                    },
                }
            ),
            encoding="utf-8",
        )
    review = eval_dir / "review"
    review.mkdir()
    (review / "index.html").write_text("<html></html>", encoding="utf-8")
    (review / "bbox-audit.jsonl").write_text(
        "\n".join(json.dumps({"case": f"meeti_{i:04d}"}) for i in range(count))
        + "\n",
        encoding="utf-8",
    )


def test_readiness_blocks_missing_openrouter_key_without_leaking_secret(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 2)
    _write_eval_artifacts(eval_dir, 2)

    report = assess_real_model_readiness(
        model_id="openrouter/minimax/minimax-m3",
        manifest_path=manifest,
        eval_dir=eval_dir,
        min_cases=2,
        env={},
    )

    payload = report.to_dict()
    assert payload["status"] == "blocked"
    assert {
        "code": "missing_provider_key",
        "message": "OPENROUTER_API_KEY is required for model openrouter/minimax/minimax-m3",
        "env_var": "OPENROUTER_API_KEY",
    } in payload["blockers"]
    assert "sk-secret" not in json.dumps(payload)


def test_readiness_accepts_complete_artifacts_and_present_provider_key(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 2)
    _write_eval_artifacts(eval_dir, 2)

    report = assess_real_model_readiness(
        model_id="openrouter/minimax/minimax-m3",
        manifest_path=manifest,
        eval_dir=eval_dir,
        min_cases=2,
        env={"OPENROUTER_API_KEY": "sk-secret"},
    )

    payload = report.to_dict()
    assert payload["status"] == "ready"
    assert payload["blockers"] == []
    assert payload["evidence"]["manifest_cases"] == 2
    assert payload["evidence"]["eval_artifacts_ok"] is True
    assert "sk-secret" not in json.dumps(payload)
    assert "scripts\\run-meeti-openclaw-experiment.cmd" in payload["next_commands"][0]
    assert "--model-id openrouter/minimax/minimax-m3" in payload["next_commands"][0]
    assert "powershell" not in payload["next_commands"][0].lower()
    assert ".ps1" not in payload["next_commands"][0].lower()


def test_readiness_cli_writes_blocked_artifact_for_missing_key(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    output = tmp_path / "readiness.json"
    _write_manifest(manifest, 2)
    _write_eval_artifacts(eval_dir, 2)
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check-real-model-readiness.py"
    )
    env = os.environ.copy()
    env.pop("OPENROUTER_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--model-id",
            "openrouter/minimax/minimax-m3",
            "--manifest",
            str(manifest),
            "--eval-dir",
            str(eval_dir),
            "--min-cases",
            "2",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 20
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["blockers"][0]["env_var"] == "OPENROUTER_API_KEY"


def test_readiness_cli_loads_dotenv_without_leaking_values(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    dotenv = tmp_path / ".env"
    output = tmp_path / "readiness.json"
    _write_manifest(manifest, 2)
    _write_eval_artifacts(eval_dir, 2)
    dotenv.write_text("OPENROUTER_API_KEY=sk-secret-dotenv\n", encoding="utf-8")
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check-real-model-readiness.py"
    )
    env = os.environ.copy()
    env.pop("OPENROUTER_API_KEY", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--model-id",
            "openrouter/minimax/minimax-m3",
            "--manifest",
            str(manifest),
            "--eval-dir",
            str(eval_dir),
            "--min-cases",
            "2",
            "--dotenv",
            str(dotenv),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0
    assert "sk-secret-dotenv" not in proc.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert "sk-secret-dotenv" not in json.dumps(payload)
