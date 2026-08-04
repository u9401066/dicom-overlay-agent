from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

from dicom_overlay.infrastructure.real_model_readiness import (
    ProviderProbeResult,
    assess_real_model_readiness,
    probe_provider_for_model,
)


def _write_manifest(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    images = path.parent / "images"
    images.mkdir()
    for i in range(count):
        Image.new("RGB", (20, 20), "white").save(images / f"{i:04d}.png")
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


def _write_eval_artifacts(eval_dir: Path, manifest_path: Path, count: int) -> None:
    eval_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    identities: list[dict[str, object]] = []
    image_hashes: dict[str, str] = {}
    for row in manifest["cases"]:
        label = row["label"]
        image_path = manifest_path.parent / row["image"]
        digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
        image_hashes[label] = digest
        identities.append(
            {
                "case": label,
                "image": row["image"],
                "image_name": image_path.name,
                "size_bytes": image_path.stat().st_size,
                "sha256": digest,
            }
        )
    protocol = {
        "source": {
            "commit": "readiness-fixture",
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
            "cases": identities,
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
        json.dumps(
            {
                "gateway_mode": "mock",
                "scorecard_kind": "full_rebuild",
                "total": count,
                "scored": count,
                "error_count": 0,
                "schema_pass_rate": 1.0,
                "bbox_in_bounds_rate": 1.0,
                "strict_pass_rate": 1.0,
                "cant_miss_missed": [],
                "urgent_concern_missed": [],
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
                    "image": f"images/{i:04d}.png",
                    "protocol_digest": protocol_digest,
                    "source_image_sha256": image_hashes[f"meeti_{i:04d}"],
                    "findings": [],
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
    for i in range(count):
        Image.new("RGB", (40, 20), "white").save(
            review / f"meeti_{i:04d}.review.png"
        )
    (review / "bbox-audit.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "audit_type": "case",
                    "case": f"meeti_{i:04d}",
                    "bbox_count": 0,
                    "review_image": f"meeti_{i:04d}.review.png",
                }
            )
            for i in range(count)
        )
        + "\n",
        encoding="utf-8",
    )


def test_readiness_blocks_missing_openrouter_key_without_leaking_secret(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 2)
    _write_eval_artifacts(eval_dir, manifest, 2)

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
    _write_eval_artifacts(eval_dir, manifest, 2)

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


def test_readiness_provider_probe_blocks_unreachable_openrouter_without_secret(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 2)
    _write_eval_artifacts(eval_dir, manifest, 2)

    report = assess_real_model_readiness(
        model_id="openrouter/minimax/minimax-m3",
        manifest_path=manifest,
        eval_dir=eval_dir,
        min_cases=2,
        env={"OPENROUTER_API_KEY": "sk-secret"},
        provider_probe=lambda model_id: ProviderProbeResult(
            provider="openrouter",
            model_id=model_id,
            ok=False,
            supports_image=None,
            error="read ECONNRESET",
        ),
    )

    payload = report.to_dict()
    assert payload["status"] == "blocked"
    assert {
        "code": "provider_probe_failed",
        "message": "Provider probe failed for openrouter/minimax/minimax-m3: read ECONNRESET",
        "provider": "openrouter",
    } in payload["blockers"]
    assert payload["evidence"]["provider_probe"]["ok"] is False
    assert "scripts\\check-real-model-readiness.cmd" in payload["next_commands"][0]
    assert "check-real-model-readiness.py" not in payload["next_commands"][0]
    assert "--probe-provider" in payload["next_commands"][0]
    assert "run-meeti-openclaw-experiment" not in payload["next_commands"][0]
    assert "sk-secret" not in json.dumps(payload)


def test_readiness_provider_probe_blocks_models_without_image_input(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    _write_manifest(manifest, 2)
    _write_eval_artifacts(eval_dir, manifest, 2)

    report = assess_real_model_readiness(
        model_id="openrouter/minimax/minimax-m3",
        manifest_path=manifest,
        eval_dir=eval_dir,
        min_cases=2,
        env={"OPENROUTER_API_KEY": "sk-secret"},
        provider_probe=lambda model_id: ProviderProbeResult(
            provider="openrouter",
            model_id=model_id,
            ok=True,
            supports_image=False,
            error="",
        ),
    )

    payload = report.to_dict()
    assert payload["status"] == "blocked"
    assert {
        "code": "model_lacks_image_input",
        "message": "Model openrouter/minimax/minimax-m3 does not advertise image input.",
        "provider": "openrouter",
    } in payload["blockers"]


def test_openai_gpt54_mini_probe_uses_pinned_vision_profile() -> None:
    probe = probe_provider_for_model("openai/gpt-5.4-mini")

    assert probe.ok is True
    assert probe.supports_image is True
    assert probe.provider == "openai"


def test_openai_readiness_recommends_transactional_canary(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, 1)

    report = assess_real_model_readiness(
        model_id="openai/gpt-5.4-mini",
        manifest_path=manifest,
        min_cases=1,
        env={"OPENAI_API_KEY": "sk-test"},
        provider_probe=probe_provider_for_model,
    )
    payload = report.to_dict()

    assert payload["status"] == "ready"
    assert payload["evidence"]["provider_transaction_tested"] is False
    assert any("billing/quota" in warning for warning in payload["warnings"])
    assert "--limit 1" in payload["next_commands"][0]
    assert "--require-perfect" not in payload["next_commands"][0]


def test_readiness_cli_writes_blocked_artifact_for_missing_key(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    eval_dir = tmp_path / "eval"
    output = tmp_path / "readiness.json"
    _write_manifest(manifest, 2)
    _write_eval_artifacts(eval_dir, manifest, 2)
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
    _write_eval_artifacts(eval_dir, manifest, 2)
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


def test_readiness_cli_exposes_provider_probe_flag() -> None:
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check-real-model-readiness.py"
    ).read_text(encoding="utf-8")

    assert "--probe-provider" in script
    assert "probe_provider_for_model" in script
