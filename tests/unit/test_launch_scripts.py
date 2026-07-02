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
    assert '[string]$ProviderProfile = ""' in script
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


def test_meeti_experiment_script_generates_openrouter_config_before_catalog() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.ps1").read_text(
        encoding="utf-8"
    )

    assert "DICOM_OVERLAY_PROVIDER_PROFILE" in script
    assert "build_openclaw_config" in script
    assert "merge_openclaw_config" in script
    assert "openrouter" in script
    assert script.index("$env:OPENCLAW_CONFIG_PATH = $configPath") < script.index(
        "models list"
    )


def test_meeti_experiment_script_does_not_hard_block_profile_catalog_errors() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.ps1").read_text(
        encoding="utf-8"
    )

    assert "Invoke-NativeCommand" in script
    assert "model_catalog_exit_code" in script
    assert "$modelListExitCode -ne 0 -and -not $effectiveProviderProfile" in script
    assert "model_catalog_warning" in script


def test_meeti_experiment_script_captures_failed_eval_console() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.ps1").read_text(
        encoding="utf-8"
    )

    assert "evalExitCode" in script
    assert "$evalOutput = $evalResult.Output" in script
    assert "$exitCode = $evalExitCode" in script


def test_meeti_experiment_script_retries_gateway_starting_eval() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.ps1").read_text(
        encoding="utf-8"
    )

    assert "Invoke-EvalWithGatewayRetry" in script
    assert "gateway starting; retry shortly" in script
    assert "eval_attempts" in script


def test_meeti_experiment_script_marks_scorecard_errors_as_failures() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.ps1").read_text(
        encoding="utf-8"
    )

    assert "scorecard.json" in script
    assert "eval_error_count" in script
    assert "$evalErrorCount -gt 0" in script


def test_meeti_experiment_script_uses_repo_local_uv_cache() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.ps1").read_text(
        encoding="utf-8"
    )

    assert "UV_CACHE_DIR" in script
    assert ".uv-cache-codex" in script
