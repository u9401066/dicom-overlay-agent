from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_meeti_experiment_module():
    script = Path("scripts/run-meeti-openclaw-experiment.py").resolve()
    spec = importlib.util.spec_from_file_location("run_meeti_experiment", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def test_real_stack_batch_avoids_interactive_gateway_conhost() -> None:
    script = Path("scripts/test-real-stack.bat").read_text(encoding="utf-8")
    lowered = script.lower()

    assert "cmd /k" not in lowered
    assert 'start "openclaw gateway"' not in lowered
    assert "start /b" in lowered
    assert "gateway.log" in lowered


def test_meeti_experiment_script_records_model_and_artifacts() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.ps1").read_text(
        encoding="utf-8"
    )

    assert '[string]$ModelId = "openai/gpt-5.6-luna"' in script
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


def test_meeti_experiment_waits_for_actual_gateway_socket(monkeypatch) -> None:
    module = _load_meeti_experiment_module()
    clock = [0.0]
    attempts = [0]

    class FakeProcess:
        @staticmethod
        def poll():
            return None

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def connect(_address, timeout):
        assert timeout == 0.5
        attempts[0] += 1
        if attempts[0] == 1:
            raise ConnectionRefusedError
        return FakeConnection()

    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        module.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    monkeypatch.setattr(module.socket, "create_connection", connect)

    elapsed = module.wait_for_gateway(
        SimpleNamespace(process=FakeProcess()),
        timeout_seconds=5,
    )

    assert elapsed == 0.5


def test_meeti_experiment_config_records_bounded_openclaw_timeouts(tmp_path) -> None:
    module = _load_meeti_experiment_module()
    base_config = tmp_path / "base.json"
    target_config = tmp_path / "experiment.json"
    base_config.write_text("{}", encoding="utf-8")

    metadata = module.write_experiment_openclaw_config(
        base_config=base_config,
        target_config=target_config,
        model_id="openai/gpt-5.6-luna",
        profile_key="openai-vision",
        inference_timeout_sec=180,
    )

    payload = module.read_json_dict(target_config)
    assert metadata["client_inference_timeout_sec"] == 180
    assert metadata["provider_timeout_sec"] == 165
    assert metadata["agent_timeout_sec"] == 175
    assert payload["models"]["providers"]["openai"]["timeoutSeconds"] == 165
    assert payload["agents"]["defaults"]["timeoutSeconds"] == 175


def test_meeti_experiment_detects_hard_provider_block_without_log_details(
    tmp_path,
) -> None:
    module = _load_meeti_experiment_module()
    gateway_log = tmp_path / "gateway.log"
    gateway_log.write_text(
        "provider=openai code=credit_balance_exhausted apiKey=do-not-copy",
        encoding="utf-8",
    )

    block = module.detect_provider_block(gateway_log)

    assert block == {
        "code": "provider_credit_exhausted",
        "reason": "Model provider credit balance is exhausted.",
    }
    assert "apiKey" not in str(block)


def test_meeti_experiment_does_not_treat_transient_timeout_as_provider_block(
    tmp_path,
) -> None:
    module = _load_meeti_experiment_module()
    gateway_log = tmp_path / "gateway.log"
    gateway_log.write_text("LLM request timed out after 74 seconds", encoding="utf-8")

    assert module.detect_provider_block(gateway_log) == {}


def test_meeti_experiment_reports_gateway_early_exit() -> None:
    module = _load_meeti_experiment_module()

    class FakeProcess:
        @staticmethod
        def poll():
            return 23

    with pytest.raises(RuntimeError, match="exit 23"):
        module.wait_for_gateway(
            SimpleNamespace(process=FakeProcess()),
            timeout_seconds=5,
        )


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
    assert "UV_NO_PROGRESS" in script
    assert "UV_PYTHON_DOWNLOADS" in script
    assert "$env:TMP" in script
    assert "$env:TEMP" in script


def test_meeti_experiment_python_runner_avoids_powershell_wrapper() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.py").read_text(
        encoding="utf-8"
    )

    assert "subprocess.Popen" in script
    assert "shell=True" not in script
    assert ".ps1" not in script
    assert "powershell" not in script.lower()
    assert "sys.executable" in script
    assert "scripts/run-eval.py" in script
    assert "scripts/rebuild-eval-scorecard.py" in script
    assert "scripts/export-eval-annotations.py" in script


def test_meeti_experiment_python_runner_has_oom_safe_environment() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.py").read_text(
        encoding="utf-8"
    )

    assert "UV_CACHE_DIR" in script
    assert ".uv-cache-codex" in script
    assert "UV_NO_PROGRESS" in script
    assert "UV_PYTHON_DOWNLOADS" in script
    assert "OPENCLAW_HOME" in script
    assert "OPENCLAW_CONFIG_PATH" in script
    assert "data/tmp/uv" in script


def test_meeti_experiment_python_runner_serializes_gateway_launches() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.py").read_text(
        encoding="utf-8"
    )

    assert "OPENCLAW_GATEWAY_LOCK" in script
    assert "openclaw-gateway.lock" in script
    assert "acquire_gateway_lock" in script
    assert "release_gateway_lock" in script
    assert "GatewayProcess" in script
    assert "CREATE_NO_WINDOW" in script


def test_meeti_experiment_python_runner_records_and_limits_artifacts() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.py").read_text(
        encoding="utf-8"
    )

    assert "experiment.json" in script
    assert "openclaw-models-list.txt" in script
    assert "gateway.stdout.log" in script
    assert "gateway.stderr.log" in script
    assert "eval-console.log" in script
    assert "scorecard.rebuilt.json" in script
    assert "review_artifacts" in script
    assert "partial-scorecard-interval" in script
    assert "MAX_CAPTURED_COMMAND_OUTPUT_CHARS" in script
    assert '"--resume"' in script
    assert '"--resume-legacy-policy"' in script
    assert '"--model-id"' in script
    assert '"--promote-canonical"' in script
    assert '"--require-protocol-fingerprint"' in script
    assert "protocol-fingerprint.json" in script
    assert 'if attempt > 1 and "--resume" not in attempt_command' in script
    assert 'attempt_command.append("--resume")' in script
    assert "gateway.resume-" in script


def test_meeti_experiment_python_runner_verifies_eval_artifacts_after_export() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.py").read_text(
        encoding="utf-8"
    )

    assert "scripts/verify-eval-artifacts.py" in script
    assert "artifact_verify_exit_code" in script
    assert "skip_artifact_verify" in script
    assert "--min-cases" in script
    assert "--require-multipass-trace" in script
    assert "--require-multipass-refinement" in script
    assert "--require-projection-audit" in script
    assert "if postprocess_exit_code != 0:" in script
    assert script.index("scripts/export-eval-annotations.py") < script.index(
        "scripts/verify-eval-artifacts.py"
    )


def test_meeti_experiment_cmd_wrapper_pins_uv_without_powershell() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.cmd").read_text(
        encoding="utf-8"
    )

    assert 'set "UV_CACHE_DIR=%REPO_ROOT%\\.uv-cache-codex"' in script
    assert 'set "UV_NO_PROGRESS=1"' in script
    assert 'set "UV_PYTHON_DOWNLOADS=never"' in script
    assert 'set "TMP=%REPO_ROOT%\\data\\tmp\\uv"' in script
    assert 'set "TEMP=%REPO_ROOT%\\data\\tmp\\uv"' in script
    assert "PYTHON_EXE=%REPO_ROOT%\\.venv\\Scripts\\python.exe" in script
    assert "MEETI_RUN_LOCK=%REPO_ROOT%\\data\\tmp\\meeti-run.lock" in script
    assert 'mkdir "%MEETI_RUN_LOCK%"' in script
    assert "Another MEETI experiment command is already running" in script
    assert 'rmdir "%MEETI_RUN_LOCK%"' in script
    assert '"%PYTHON_EXE%" scripts\\run-meeti-openclaw-experiment.py %*' in script
    assert "uv run" not in script
    assert ".ps1" not in script.lower()
    assert "powershell" not in script.lower()


def test_real_model_readiness_cmd_wrapper_pins_uv_without_powershell() -> None:
    script = Path("scripts/check-real-model-readiness.cmd").read_text(encoding="utf-8")

    assert 'set "UV_CACHE_DIR=%REPO_ROOT%\\.uv-cache-codex"' in script
    assert 'set "UV_NO_PROGRESS=1"' in script
    assert 'set "UV_PYTHON_DOWNLOADS=never"' in script
    assert 'set "TMP=%REPO_ROOT%\\data\\tmp\\uv"' in script
    assert 'set "TEMP=%REPO_ROOT%\\data\\tmp\\uv"' in script
    assert "PYTHON_EXE=%REPO_ROOT%\\.venv\\Scripts\\python.exe" in script
    assert "READINESS_RUN_LOCK=%REPO_ROOT%\\data\\tmp\\readiness-run.lock" in script
    assert 'mkdir "%READINESS_RUN_LOCK%"' in script
    assert "Another readiness command is already running" in script
    assert 'rmdir "%READINESS_RUN_LOCK%"' in script
    assert '"%PYTHON_EXE%" scripts\\check-real-model-readiness.py %*' in script
    assert "uv run" not in script
    assert ".ps1" not in script.lower()
    assert "powershell" not in script.lower()


def test_build_script_forces_locked_openclaw_and_verifies_bundle() -> None:
    script = Path("scripts/build-exe.bat").read_text(encoding="utf-8")

    assert 'set "FORCE_OPENCLAW_INSTALL=1"' in script
    assert ".venv\\Scripts\\python.exe -m PyInstaller" in script
    assert "pyinstaller.exe" not in script.lower()
    assert "scripts\\verify-packaged-app.py" in script
    assert "bundle-manifest.json" in script
    assert "refusing an incomplete bundle" in script

    installer = Path("scripts/install-openclaw-local.bat").read_text(encoding="utf-8")
    assert "npm ci --prefix openclaw --omit=dev" in installer
    assert "does not match lock target" in installer
    assert '"node\\node.exe" "!NPM_CLI_JS!"' in installer
    assert "scripts\\check-openclaw-version.cjs" in installer

    spec = Path("dicom-overlay-agent.spec").read_text(encoding="utf-8")
    assert spec.count('contents_directory="."') == 1
    assert spec.index('contents_directory="."') < spec.index("coll = COLLECT(")


def test_openclaw_calendar_version_checker_accepts_packaging_revision() -> None:
    node = Path("node/node.exe")
    if not node.is_file():
        pytest.skip("portable Node is not installed")
    checker = Path("scripts/check-openclaw-version.cjs")

    supported = subprocess.run(
        [str(node), str(checker), "2026.7.1-2", "2026.4.22"],
        check=False,
        capture_output=True,
        text=True,
    )
    too_old = subprocess.run(
        [str(node), str(checker), "2026.4.21-9", "2026.4.22"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert supported.returncode == 0
    assert too_old.returncode == 1
    assert "older than safe minimum" in too_old.stderr


def test_openclaw_staging_preserves_runtime_plugin_surfaces_and_skills() -> None:
    script = Path("scripts/stage-openclaw-runtime.ps1").read_text(encoding="utf-8")

    assert '$bundledSkills = Join-Path $dest "skills"' in script
    assert "dist/extensions" in script
    assert "dist/plugins" in script
    assert "dist/plugin-sdk" in script
    assert '"quickjs-wasi"' not in script


def test_portable_node_fetcher_pins_current_lts_and_updates_stale_binary() -> None:
    script = Path("scripts/fetch-node.ps1").read_text(encoding="utf-8")

    assert '[string]$Version = "24.18.0"' in script
    assert '$existing -eq "v$Version"' in script
    assert "Updating portable Node.js" in script


def test_ecgfounder_setup_isolated_runtime_and_hash_gated_download() -> None:
    script = Path("scripts/setup-ecgfounder-sidecar.ps1").read_text(
        encoding="utf-8"
    )

    assert 'data\\external\\ecgfounder-runtime' in script
    assert '12_lead_ECGFounder.pth?download=true' in script
    assert "huggingface.co/PKUDigitalHealth/ECGFounder" in script
    assert "hf-mirror.com:443:$MirrorAddress" in script
    assert "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997" in script
    assert "Get-FileHash" in script
    assert script.index("Get-FileHash", script.index("$DownloadedHash")) < script.index(
        "Move-Item -LiteralPath $Download"
    )
