from __future__ import annotations

from pathlib import Path


def test_real_stack_batch_loads_dotenv_before_gateway() -> None:
    script = Path("scripts/test-real-stack.bat").read_text(encoding="utf-8")

    assert "call scripts\\load-env.bat" in script
    assert script.index("call scripts\\load-env.bat") < script.index(
        "node .\\openclaw\\node_modules\\openclaw\\openclaw.mjs config validate"
    )


def test_load_env_batch_never_prints_values() -> None:
    script = Path("scripts/load-env.bat").read_text(encoding="utf-8")

    assert "for /f" in script.lower()
    assert "echo %" not in script.lower()


def test_meeti_experiment_script_records_model_and_artifacts() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.ps1").read_text(
        encoding="utf-8"
    )

    assert '[string]$ModelId = "openai/gpt-5.5-mini"' in script
    assert '[string]$ManifestPath = ""' in script
    assert "openclaw-models-list.txt" in script
    assert "openclaw.experiment.json" in script
    assert '[string]$ExperimentDir = ""' in script
    assert "scripts\\run-eval.py" in script
    assert "--manifest" in script
    assert "--dataset" not in script
    assert "[switch]$MultiPass" in script
    assert "--multi-pass" in script
    assert "experiment.json" in script
    assert 'status = "running"' in script
    assert "updated_at" in script
    assert "requested model id is not exposed" in script
    assert "scripts\\rebuild-eval-scorecard.py" in script
    assert "scripts\\export-eval-annotations.py" in script
    assert "scorecard_rebuilt" in script
    assert "review_artifacts" in script
