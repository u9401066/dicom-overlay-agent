from __future__ import annotations

import importlib.util
import json
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


def test_meeti_experiment_powershell_is_only_a_canonical_argument_adapter() -> None:
    script = Path("scripts/run-meeti-openclaw-experiment.ps1").read_text(
        encoding="utf-8"
    )

    assert '[string]$ModelId = "openai/gpt-5.4-mini"' in script
    assert '[string]$ManifestPath = ""' in script
    assert '[string]$ProviderProfile = ""' in script
    assert '[string]$ExperimentDir = ""' in script
    assert "--manifest" in script
    assert "--dataset" not in script
    assert "[switch]$MultiPass" in script
    assert "--multi-pass" in script
    assert '"scripts/run-meeti-openclaw-experiment.py"' in script
    assert "function Write-ExperimentJson" not in script
    assert "meeti-1000-all" not in script
    assert "--thinking-level" in script
    assert "--no-manage-ecgfounder-sidecar" in script
    assert "--min-strict-pass-rate" in script
    assert "--min-mean-partial-credit" in script


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


def test_meeti_experiment_waits_for_subscription_provider_plugin(tmp_path) -> None:
    module = _load_meeti_experiment_module()
    log_path = tmp_path / "gateway.log"
    log_path.write_text(
        "[plugins] loading openai from C:/runtime/extensions/openai/index.js\n",
        encoding="utf-8",
    )

    elapsed = module.wait_for_gateway_log_marker(
        SimpleNamespace(process=SimpleNamespace(poll=lambda: None)),
        log_path=log_path,
        marker="[plugins] loading openai from",
        timeout_seconds=5,
    )

    assert elapsed >= 0.0


def test_meeti_resume_reuses_existing_experiment_config(tmp_path) -> None:
    module = _load_meeti_experiment_module()
    target = tmp_path / "openclaw.experiment.json"
    repo = tmp_path / "openclaw.json"
    repo.write_text("{}", encoding="utf-8")

    assert module.resolve_experiment_config_base(
        resume=True,
        target_config=target,
        repo_config=repo,
    ) == repo

    target.write_text('{"meta":{"lastTouchedAt":"original"}}', encoding="utf-8")
    assert module.resolve_experiment_config_base(
        resume=True,
        target_config=target,
        repo_config=repo,
    ) == target
    assert module.resolve_experiment_config_base(
        resume=False,
        target_config=target,
        repo_config=repo,
    ) == repo


def test_meeti_experiment_starts_gateway_in_isolated_workspace(
    monkeypatch, tmp_path
) -> None:
    module = _load_meeti_experiment_module()
    lock_dir = tmp_path / "gateway.lock"
    lock_dir.mkdir()
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 1234

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(module, "acquire_gateway_lock", lambda: lock_dir)
    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    paths = {
        "gateway_stdout": tmp_path / "gateway.stdout.log",
        "gateway_stderr": tmp_path / "gateway.stderr.log",
    }
    workspace = tmp_path / "isolated-workspace"

    gateway = module.start_gateway(
        paths,
        {},
        node_executable="node",
        workspace_dir=workspace,
    )

    assert gateway.process.pid == 1234
    assert captured["kwargs"]["cwd"] == workspace.resolve()
    assert captured["kwargs"]["cwd"] != module.REPO_ROOT


def test_meeti_experiment_config_records_bounded_openclaw_timeouts(tmp_path) -> None:
    module = _load_meeti_experiment_module()
    base_config = tmp_path / "base.json"
    target_config = tmp_path / "experiment.json"
    base_config.write_text("{}", encoding="utf-8")

    metadata = module.write_experiment_openclaw_config(
        base_config=base_config,
        target_config=target_config,
        model_id="openai/gpt-5.4-mini",
        profile_key="openai-vision",
        harness_plugin_path=tmp_path / "dicom-overlay-agent-harness",
        inference_timeout_sec=180,
        thinking_level="low",
    )

    payload = module.read_json_dict(target_config)
    assert metadata["client_inference_timeout_sec"] == 180
    assert metadata["provider_timeout_sec"] == 165
    assert metadata["agent_timeout_sec"] == 175
    assert payload["models"]["providers"]["openai"]["timeoutSeconds"] == 165
    assert payload["agents"]["defaults"]["timeoutSeconds"] == 175
    assert payload["agents"]["defaults"]["thinkingDefault"] == "low"
    assert metadata["thinking_level"] == "low"
    assert payload["tools"] == {
        "allow": ["dicom_bbox_validate"],
        "web": {
            "search": {"enabled": False},
            "fetch": {"enabled": False},
        },
    }


def test_meeti_experiment_codex_subscription_config_is_fail_closed(tmp_path) -> None:
    module = _load_meeti_experiment_module()
    base_config = tmp_path / "base.json"
    target_config = tmp_path / "experiment.json"
    base_config.write_text(
        """{
          "models": {"providers": {"openai": {
            "apiKey": {"id": "OPENAI_API_KEY"},
            "baseUrl": "https://api.openai.com/v1",
            "models": [{"id": "gpt-5.4-mini", "agentRuntime": {"id": "openclaw"}}]
          }}},
          "plugins": {
            "allow": ["dicom-overlay-agent-harness", "codex"],
            "entries": {
              "dicom-overlay-agent-harness": {"enabled": true},
              "codex": {"enabled": true}
            }
          },
          "auth": {
            "profiles": {
              "openai:test": {"provider": "openai", "mode": "oauth"}
            }
          },
          "meta": {"lastTouchedVersion": "test", "lastTouchedAt": "now"}
        }""",
        encoding="utf-8",
    )

    metadata = module.write_experiment_openclaw_config(
        base_config=base_config,
        target_config=target_config,
        model_id="openai/gpt-5.4-mini",
        profile_key="openai-codex",
        harness_plugin_path=tmp_path / "dicom-overlay-agent-harness",
        inference_timeout_sec=180,
    )

    payload = module.read_json_dict(target_config)
    provider = payload["models"]["providers"]["openai"]
    assert "apiKey" not in provider
    assert "baseUrl" not in provider
    assert provider["api"] == "openai-chatgpt-responses"
    assert provider["models"][0]["input"] == ["text", "image"]
    assert provider["models"][0]["agentRuntime"] == {"id": "openclaw"}
    assert payload["agents"]["defaults"]["models"]["openai/gpt-5.4-mini"][
        "agentRuntime"
    ] == {"id": "openclaw"}
    expected_workspace = str((tmp_path / "dicom-overlay-agent-harness").parent.parent)
    assert payload["agents"]["defaults"]["workspace"] == expected_workspace
    assert payload["plugins"]["allow"] == [
        "dicom-overlay-agent-harness",
        "openai",
    ]
    assert payload["plugins"]["entries"]["openai"] == {"enabled": True}
    assert "codex" not in payload["plugins"]["entries"]
    assert payload["auth"]["profiles"]["openai:test"]["mode"] == "oauth"
    assert payload["meta"]["lastTouchedVersion"] == "test"
    assert metadata["provider_auth_mode"] == "codex_subscription"
    assert metadata["billing_route"] == "chatgpt_codex_subscription"
    assert metadata["platform_api_key_disabled"] is True
    assert metadata["agent_runtime"] == "openclaw"
    assert metadata["agent_loop_owner"] == "openclaw"
    assert metadata["inference_transport"] == "openai-chatgpt-responses"
    assert metadata["openai_provider_plugin_enabled"] is True
    module.assert_openclaw_subscription_ownership(
        target_config,
        model_id="openai/gpt-5.4-mini",
    )

    payload["plugins"]["allow"].append("codex")
    module.write_json(target_config, payload)
    with pytest.raises(RuntimeError, match="plugin allowlist"):
        module.assert_openclaw_subscription_ownership(
            target_config,
            model_id="openai/gpt-5.4-mini",
        )


def test_meeti_minimal_control_disables_harness_skills_and_tools(tmp_path) -> None:
    module = _load_meeti_experiment_module()
    base_config = tmp_path / "base.json"
    target_config = tmp_path / "experiment.json"
    base_config.write_text("{}", encoding="utf-8")

    metadata = module.write_experiment_openclaw_config(
        base_config=base_config,
        target_config=target_config,
        model_id="openai/gpt-5.4-mini",
        profile_key="openai-codex",
        harness_plugin_path=tmp_path / "dicom-overlay-agent-harness",
        enable_harness=False,
        thinking_level="low",
    )

    payload = module.read_json_dict(target_config)
    assert payload["agents"]["defaults"]["skills"] == []
    assert payload["agents"]["defaults"]["thinkingDefault"] == "low"
    assert payload["plugins"]["allow"] == ["openai"]
    assert payload["plugins"]["load"]["paths"] == []
    assert payload["plugins"]["entries"] == {"openai": {"enabled": True}}
    assert payload["tools"] == {
        "deny": ["*"],
        "web": {
            "search": {"enabled": False},
            "fetch": {"enabled": False},
        },
    }
    assert metadata["harness_enabled"] is False
    assert metadata["openai_provider_plugin_enabled"] is True
    assert metadata["ecg_founder_tool_enabled"] is False


def test_meeti_experiment_uses_bundled_migration_only_auth_bootstrap(
    monkeypatch, tmp_path
) -> None:
    module = _load_meeti_experiment_module()
    captured: dict[str, object] = {}
    ownership: dict[str, object] = {}

    def fake_bootstrap(**kwargs):
        captured.update(kwargs)
        return {
            "status": "ready",
            "agent_runtime": "openclaw",
            "codex_agent_runtime_enabled": False,
        }

    def fake_ownership(config_path, *, model_id):
        ownership.update(config_path=config_path, model_id=model_id)

    monkeypatch.setattr(module, "ensure_openclaw_subscription_auth", fake_bootstrap)
    monkeypatch.setattr(module, "assert_openclaw_subscription_ownership", fake_ownership)
    config_path = tmp_path / "openclaw.json"
    state_home = tmp_path / "state"
    source_home = tmp_path / ".codex"
    audit_path = tmp_path / "auth-audit.json"
    env = {"PATH": "test"}

    result = module.bootstrap_openclaw_subscription_auth(
        node_executable="node",
        env=env,
        config_path=config_path,
        state_home=state_home,
        source_codex_home=source_home,
        audit_path=audit_path,
        model_id="openai/gpt-5.4-mini",
    )

    assert result["agent_runtime"] == "openclaw"
    assert result["codex_agent_runtime_enabled"] is False
    assert captured["openclaw_cli"] == module.OPENCLAW_CLI
    assert captured["plugin_path"] == (
        module.OPENCLAW_CLI.parent / "dist" / "extensions" / "codex"
    )
    assert captured["environment"] is env
    assert ownership == {
        "config_path": config_path,
        "model_id": "openai/gpt-5.4-mini",
    }
    assert not hasattr(module, "ensure_codex_plugin_installed")
    assert not hasattr(module, "remove_codex_auth_import_plugin")


def test_meeti_experiment_codex_env_requires_chatgpt_and_removes_api_key(
    tmp_path,
) -> None:
    module = _load_meeti_experiment_module()
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        '{"auth_mode":"chatgpt","OPENAI_API_KEY":null,"tokens":{"access":"x"}}',
        encoding="utf-8",
    )
    env = {
        "OPENAI_API_KEY": "must-not-survive",
        "CODEX_HOME": "must-not-leak",
    }

    metadata = module.prepare_codex_subscription_env(env, codex_home)

    assert "OPENAI_API_KEY" not in env
    assert "CODEX_HOME" not in env
    assert metadata["codex_auth_verified"] is True
    assert metadata["platform_api_key_was_present_before_isolation"] is True
    assert metadata["inherited_codex_home_removed"] is True
    assert metadata["codex_source_home"] == str(codex_home.resolve())


def test_meeti_experiment_codex_env_rejects_api_key_auth(tmp_path) -> None:
    module = _load_meeti_experiment_module()
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        '{"auth_mode":"apikey","OPENAI_API_KEY":"test"}',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="logged in with ChatGPT"):
        module.prepare_codex_subscription_env({}, codex_home)


def test_meeti_experiment_auto_selects_exact_vision_profile() -> None:
    module = _load_meeti_experiment_module()

    assert (
        module.effective_provider_profile("openai/gpt-5.4-mini", "", {})
        == "openai-codex"
    )

    profile = module.assert_subscription_experiment_profile("openai-codex")
    assert profile.auth_mode.value == "codex_subscription"
    with pytest.raises(RuntimeError, match="subscription OAuth"):
        module.assert_subscription_experiment_profile("openai-vision")
    assert (
        module.effective_provider_profile("openai/gpt-5.6-luna", "", {})
        == "openai-luna"
    )


def test_meeti_experiment_arm_and_quality_gate_are_fail_closed() -> None:
    module = _load_meeti_experiment_module()
    args = SimpleNamespace(
        multi_pass=False,
        ecgfounder_waveform_evidence=False,
        analysis_prompt_profile="clinical",
    )

    assert module.experiment_arm(args) == "single_pass"
    args.multi_pass = True
    assert module.experiment_arm(args) == "multipass"
    args.ecgfounder_waveform_evidence = True
    assert module.experiment_arm(args) == "multipass_ecgfounder"
    args.ecgfounder_waveform_evidence = False
    args.multi_pass = False
    args.analysis_prompt_profile = "minimal_control"
    assert module.experiment_arm(args) == "minimal_control"

    failed = module.evaluate_quality_gate(
        {"strict_pass_rate": 0.74, "mean_partial_credit": 0.84},
        min_strict_pass_rate=0.75,
        min_mean_partial_credit=0.85,
    )
    assert failed["passed"] is False
    assert len(failed["failures"]) == 2
    passed = module.evaluate_quality_gate(
        {"strict_pass_rate": 0.75, "mean_partial_credit": 0.85},
        min_strict_pass_rate=0.75,
        min_mean_partial_credit=0.85,
    )
    assert passed["passed"] is True

    sla_failed = module.evaluate_quality_gate(
        {
            "strict_pass_rate": 0.8,
            "mean_partial_credit": 0.9,
            "sla_metrics": {
                "initial_response": {"rate": 0.95},
                "first_crop_refinement": {"rate": 0.8},
                "total": {"rate": 1.0},
            },
        },
        min_strict_pass_rate=0.75,
        min_mean_partial_credit=0.85,
        min_initial_response_sla_rate=0.9,
        min_first_crop_sla_rate=0.9,
        min_total_sla_rate=0.95,
    )
    assert sla_failed["passed"] is False
    assert "first_crop_refinement" in sla_failed["failures"][0]


def test_meeti_experiment_rejects_ecgfounder_without_multipass(
    monkeypatch,
) -> None:
    module = _load_meeti_experiment_module()
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "run-meeti-openclaw-experiment.py",
            "--no-multi-pass",
            "--ecgfounder-waveform-evidence",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        module.parse_args()

    assert exc.value.code == 2


def test_meeti_experiment_defaults_to_full_subscription_harness(monkeypatch) -> None:
    module = _load_meeti_experiment_module()
    monkeypatch.setattr(module.sys, "argv", ["run-meeti-openclaw-experiment.py"])

    args = module.parse_args()

    assert args.provider_profile == "openai-codex"
    assert args.multi_pass is True
    assert args.ecgfounder_waveform_evidence is True
    assert args.thinking_level == "off"
    assert args.multi_pass_max_targets == 2
    assert args.multi_pass_max_ekg_systematic_probes == 1
    assert args.initial_response_sla_sec == 60
    assert args.first_refinement_sla_sec == 100
    assert args.total_analysis_sla_sec == 180


def test_meeti_minimal_control_defaults_to_tool_free_single_pass(monkeypatch) -> None:
    module = _load_meeti_experiment_module()
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "run-meeti-openclaw-experiment.py",
            "--analysis-prompt-profile",
            "minimal_control",
        ],
    )

    args = module.parse_args()

    assert args.provider_profile == "openai-codex"
    assert args.multi_pass is False
    assert args.ecgfounder_waveform_evidence is False


def test_meeti_managed_ecgfounder_validates_manifest_registry_binding(
    tmp_path: Path,
) -> None:
    module = _load_meeti_experiment_module()
    runtime = tmp_path / "runtime"
    python = runtime / ".venv" / "Scripts" / "python.exe"
    checkpoint = runtime / "checkpoints" / "12_lead_ECGFounder.pth"
    python.parent.mkdir(parents=True)
    checkpoint.parent.mkdir(parents=True)
    python.write_bytes(b"python")
    checkpoint.write_bytes(b"checkpoint")
    registry = tmp_path / "waveform-registry.json"
    registry.write_text(
        json.dumps({"artifacts": {"wf-test": {"path": "waveform.mat"}}}),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "waveform_registry": {"path": registry.name},
                "cases": [{"waveform_artifact_id": "wf-test"}],
            }
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        ecgfounder_waveform_evidence=True,
        manage_ecgfounder_sidecar=True,
        ecgfounder_runtime_dir=runtime,
        ecgfounder_registry=None,
        ecgfounder_port=18790,
    )
    env: dict[str, str] = {}

    spec = module.prepare_managed_ecgfounder(
        args,
        env=env,
        manifest_path=manifest,
    )

    assert spec["required_artifact_count"] == 1
    assert spec["registered_artifact_count"] == 1
    assert spec["registry"] == registry
    assert env["DICOM_ECGFOUNDER_ENDPOINT"].endswith(":18790/v1/analyze")
    assert len(env["DICOM_ECGFOUNDER_TOKEN"]) >= 32


def test_meeti_experiment_resume_retry_errors_requires_resume(monkeypatch) -> None:
    module = _load_meeti_experiment_module()
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["run-meeti-openclaw-experiment.py", "--resume-retry-errors"],
    )

    with pytest.raises(SystemExit) as exc:
        module.parse_args()

    assert exc.value.code == 2


def test_meeti_experiment_parses_resume_retry_errors(monkeypatch) -> None:
    module = _load_meeti_experiment_module()
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "run-meeti-openclaw-experiment.py",
            "--resume",
            "--resume-retry-errors",
        ],
    )

    args = module.parse_args()

    assert args.resume is True
    assert args.resume_retry_errors is True


def test_meeti_experiment_parses_catalog_input_even_after_cli_crash() -> None:
    module = _load_meeti_experiment_module()
    catalog = """
Model                                      Input      Ctx
openai/gpt-5.4-mini                        text+image 400k
Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)
"""

    assert module.parse_model_catalog_input(catalog, "openai/gpt-5.4-mini") == (
        "text",
        "image",
    )
    assert module.parse_model_catalog_input(catalog, "openai/missing") is None


def test_meeti_runtime_ownership_requires_embedded_subscription_route(
    tmp_path: Path,
) -> None:
    module = _load_meeti_experiment_module()
    log = tmp_path / "gateway.log"
    log.write_text(
        "[plugins] loading codex from C:/runtime/codex/dist/index.js\n"
        "[agent/embedded] embedded run start: provider=openai "
        "model=gpt-5.4-mini\n"
        "api=openai-chatgpt-responses\n"
        "baseUrl=https://chatgpt.com/backend-api/codex timeoutMs=1\n",
        encoding="utf-8",
    )

    proof = module.verify_openclaw_runtime_ownership(
        log,
        runtime_node_modules=tmp_path / "empty-node-modules",
    )

    assert proof["verified"] is True
    assert proof["missing_markers"] == []
    assert proof["codex_extension_loaded"] is True
    assert proof["codex_agent_runtime_used"] is False
    assert proof["observed_agent_routes"] == ["openai/gpt-5.4-mini"]

    log.write_text(
        "[agent/embedded] embedded run start: provider=openai model=gpt-5.4-mini\n"
        "codex app-server context-engine projection decision\n",
        encoding="utf-8",
    )
    proof = module.verify_openclaw_runtime_ownership(
        log,
        runtime_node_modules=tmp_path / "empty-node-modules",
    )
    assert proof["verified"] is False
    assert proof["missing_markers"] == [
        "subscription_transport",
        "codex_backend",
    ]
    assert proof["observed_handoff_markers"] == ["codex_app_server_turn"]
    assert proof["codex_agent_runtime_used"] is True


def test_meeti_runtime_ownership_rejects_codex_runtime_payload(
    tmp_path: Path,
) -> None:
    module = _load_meeti_experiment_module()
    log = tmp_path / "gateway.log"
    log.write_text(
        "[agent/embedded] embedded run start: provider=openai "
        "model=gpt-5.4-mini\n"
        "api=openai-chatgpt-responses\n"
        "baseUrl=https://chatgpt.com/backend-api/codex\n",
        encoding="utf-8",
    )
    node_modules = tmp_path / "node_modules"
    (node_modules / "@openai" / "codex").mkdir(parents=True)

    proof = module.verify_openclaw_runtime_ownership(
        log,
        runtime_node_modules=node_modules,
    )

    assert proof["verified"] is False
    assert proof["codex_agent_runtime_dependencies"]


def test_meeti_bounded_log_reader_keeps_tail_for_provider_failures(
    tmp_path: Path,
) -> None:
    module = _load_meeti_experiment_module()
    log = tmp_path / "large.log"
    log.write_text(
        "x" * (module.MAX_CAPTURED_COMMAND_OUTPUT_CHARS + 1000)
        + "\ninsufficient_quota\n",
        encoding="utf-8",
    )

    assert module.detect_provider_block(log)["code"] == "provider_quota_exhausted"


def test_meeti_transport_receipt_separates_fast_mode_from_service_tier(
    tmp_path: Path,
) -> None:
    module = _load_meeti_experiment_module()
    gateway_log = tmp_path / "gateway.stdout.log"
    gateway_log.write_text(
        "[openai-transport] [responses] start provider=openai "
        "api=openai-chatgpt-responses serviceTier=undefined\n"
        "[openai-transport] [responses] start provider=openai "
        "api=openai-chatgpt-responses serviceTier=undefined\n",
        encoding="utf-8",
    )
    sessions = tmp_path / "state" / "agents" / "main" / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "run.trajectory.jsonl").write_text(
        json.dumps(
            {
                "type": "trace.metadata",
                "data": {"model": {"fastMode": True}},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    receipt = module.build_transport_receipt(
        gateway_log=gateway_log,
        state_home=tmp_path / "state",
        fast_mode_requested=True,
    )

    assert receipt["fast_mode_requested"] is True
    assert receipt["gateway_fast_mode_trace"]["observed"] is True
    assert receipt["transport_request_count"] == 2
    assert receipt["service_tier_values"] == {"undefined": 2}
    assert receipt["priority_service_observed"] is False
    assert receipt["service_tier_claim"] == "priority_not_observed"


def test_meeti_validates_answer_free_paired_manifests(tmp_path: Path) -> None:
    module = _load_meeti_experiment_module()
    image = tmp_path / "case.png"
    image.write_bytes(b"same-image")
    inference = tmp_path / "manifest.inference.json"
    gold = tmp_path / "manifest.gold.json"
    inference.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "label": "case-1",
                        "image": image.name,
                        "modality": "EKG",
                        "source": "meeti",
                        "waveform_artifact_id": "wf-1",
                        "waveform_lead_mode": "12_lead",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    gold.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "label": "case-1",
                        "image": image.name,
                        "modality": "EKG",
                        "source": "meeti",
                        "waveform_artifact_id": "wf-1",
                        "waveform_lead_mode": "12_lead",
                        "expected_severity": "warning",
                        "keywords": ["atrial fibrillation"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    proof = module.validate_manifest_pair(
        inference_manifest=inference,
        scoring_manifest=gold,
    )

    assert proof["blinded_inference"] is True
    assert proof["case_count"] == 1
    assert proof["inference_manifest_sha256"] != proof["scoring_manifest_sha256"]


def test_meeti_rejects_gold_leak_in_inference_manifest(tmp_path: Path) -> None:
    module = _load_meeti_experiment_module()
    image = tmp_path / "case.png"
    image.write_bytes(b"same-image")
    inference = tmp_path / "manifest.inference.json"
    gold = tmp_path / "manifest.gold.json"
    row = {
        "label": "case-1",
        "image": image.name,
        "modality": "EKG",
        "expected_severity": "warning",
    }
    inference.write_text(json.dumps({"cases": [row]}), encoding="utf-8")
    gold.write_text(json.dumps({"cases": [row]}), encoding="utf-8")

    with pytest.raises(ValueError, match="answer fields"):
        module.validate_manifest_pair(
            inference_manifest=inference,
            scoring_manifest=gold,
        )


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
    assert "--require-ekg-systematic-probes" in script
    assert "--require-multipass-refinement" in script
    assert "--require-projection-audit" in script
    assert "--allow-safety-misses" in script
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
    assert "uv lock --check" in script
    assert 'set "DICOM_OVERLAY_BUILD_ENV=%REPO_ROOT%.venv-build"' in script
    assert 'set "UV_PROJECT_ENVIRONMENT=%DICOM_OVERLAY_BUILD_ENV%"' in script
    assert 'set "DICOM_OVERLAY_RELEASE_PYTHON=3.13.12"' in script
    assert (
        'uv sync --python "%DICOM_OVERLAY_RELEASE_PYTHON%" '
        "--frozen --no-dev --extra build"
    ) in script
    assert (
        '"%DICOM_OVERLAY_BUILD_ENV%\\Scripts\\python.exe" -m PyInstaller'
        in script
    )
    assert "uv sync --extra build" not in script
    assert "scripts\\validate-clinical-knowledge.py --check-generated" in script
    assert "scripts\\build-clinical-knowledge-sqlite.py" in script
    assert "build\\clinical-knowledge.sqlite --check" in script
    assert "scripts\\write-package-build-receipt.py" in script
    assert "no-UPX size baseline" in script
    assert "pyinstaller.exe" not in script.lower()
    assert "scripts\\verify-packaged-app.py" in script
    assert "bundle-manifest.json" in script
    assert "refusing an incomplete bundle" in script

    installer = Path("scripts/install-openclaw-local.bat").read_text(encoding="utf-8")
    assert "npm ci --prefix openclaw --omit=dev" in installer
    assert "does not match lock target" in installer
    assert '"node\\node.exe" "!NPM_CLI_JS!"' in installer
    assert "scripts\\check-openclaw-version.cjs" in installer

    migration_stage = Path(
        "scripts/stage-codex-auth-migration-provider.ps1"
    ).read_text(encoding="utf-8")
    assert "Pruned full Codex agent runtime packages" in migration_stage
    assert 'Get-ChildItem -LiteralPath $runtimeNodeModules -Recurse -File -Filter "codex.exe"' in migration_stage

    spec = Path("dicom-overlay-agent.spec").read_text(encoding="utf-8")
    assert spec.count('contents_directory="."') == 1
    assert spec.index('contents_directory="."') < spec.index("coll = COLLECT(")
    for excluded in (
        "rich",
        "pygments",
        "markdown_it",
        "mdurl",
        "PIL.AvifImagePlugin",
        "PIL._avif",
    ):
        assert f'"{excluded}"' in spec
    assert 'optional_tree("clinical_knowledge", "clinical_knowledge")' in spec
    assert (
        'optional_file("build/clinical-knowledge.sqlite", "clinical_knowledge")'
        in spec
    )
    assert 'optional_file("build/package-build-receipt.json", ".")' in spec
    assert (
        'UPX_ENABLED = os.environ.get("DICOM_OVERLAY_UPX_ENABLED", "1") == "1"'
        in spec
    )
    assert spec.count("upx=UPX_ENABLED") == 2


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
    assert '$_.Name -ieq ".env"' in script
    assert '$_.Name.StartsWith(".env."' in script


def test_portable_node_fetcher_pins_current_lts_and_updates_stale_binary() -> None:
    script = Path("scripts/fetch-node.ps1").read_text(encoding="utf-8")

    assert '[string]$Version = "24.18.0"' in script
    assert '$existing -eq "v$Version"' in script
    assert "Updating portable Node.js" in script


def test_ecgfounder_setup_isolated_runtime_and_hash_gated_download() -> None:
    script = Path("scripts/setup-ecgfounder-sidecar.ps1").read_text(encoding="utf-8")

    assert "data\\external\\ecgfounder-runtime" in script
    assert "12_lead_ECGFounder.pth?download=true" in script
    assert "huggingface.co/PKUDigitalHealth/ECGFounder" in script
    assert "hf-mirror.com:443:$MirrorAddress" in script
    assert "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997" in script
    assert "Get-FileHash" in script
    assert script.index("Get-FileHash", script.index("$DownloadedHash")) < script.index(
        "Move-Item -LiteralPath $Download"
    )
