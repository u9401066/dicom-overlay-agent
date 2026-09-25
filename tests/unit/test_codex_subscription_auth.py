from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from dicom_overlay.infrastructure import codex_subscription_auth as auth_module
from dicom_overlay.infrastructure.codex_subscription_auth import (
    CODEX_MIGRATION_PLUGIN_NAME,
    CODEX_MIGRATION_PLUGIN_VERSION,
    ensure_openclaw_subscription_auth,
    uses_codex_subscription_transport,
)
from dicom_overlay.infrastructure.gateway_manager import GatewayManager


def _write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize("phase", ["oauth_migration", "profile_check"])
@pytest.mark.parametrize(
    "outcome", ["success", "nonzero_exit", "timeout", "spawn_error"]
)
def test_auth_phase_timing_has_no_command_output_environment_or_error_secrets(
    monkeypatch, tmp_path, phase, outcome
):
    secret = "private-credential-must-not-appear"
    command = ["node", secret, "public-command"]
    environment = {"PRIVATE": secret}
    result = subprocess.CompletedProcess(
        command, 0 if outcome == "success" else 9, stdout=secret, stderr=secret
    )
    error = (
        subprocess.TimeoutExpired(command, 120, output=secret, stderr=secret)
        if outcome == "timeout"
        else OSError(secret)
    )
    events = []
    ticks = iter([10.0, 12.25])
    calls = []

    def run(observed_command, **kwargs):
        calls.append((observed_command, kwargs))
        if outcome in {"timeout", "spawn_error"}:
            raise error
        return result

    monkeypatch.setattr(auth_module.subprocess, "run", run)
    monkeypatch.setattr(auth_module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(
        auth_module,
        "logger",
        SimpleNamespace(
            info=lambda event, **fields: events.append({"event": event, **fields})
        ),
    )
    args = {
        "phase": phase,
        "working_directory": tmp_path,
        "environment": environment,
        "timeout": 120,
    }
    if outcome in {"timeout", "spawn_error"}:
        with pytest.raises(type(error)) as caught:
            auth_module._run_auth_command(command, **args)
        assert caught.value is error
    else:
        assert auth_module._run_auth_command(command, **args) is result
    assert len(calls) == 1  # Instrumentation must never retry a command.
    observed_command, kwargs = calls[0]
    assert observed_command == command
    assert kwargs["env"] == environment and kwargs["env"] is not environment
    assert kwargs["cwd"] == tmp_path and kwargs["timeout"] == 120
    assert kwargs["capture_output"] and kwargs["text"] and not kwargs["check"]
    assert events == [
        {"event": "subscription_auth_phase_started", "phase": phase},
        {
            "event": "subscription_auth_phase_finished",
            "phase": phase,
            "outcome": outcome,
            "exit_code": result.returncode
            if outcome in {"success", "nonzero_exit"}
            else None,
            "elapsed_ms": 2250.0,
        },
    ]
    assert secret not in json.dumps(events)


def test_runtime_selfcheck_uses_matching_migration_pin_and_rejects_flat_codex(tmp_path):
    modules = tmp_path / "openclaw/node_modules"
    plugin = modules / "openclaw/dist/extensions/codex"
    _write_json(
        plugin / "package.json",
        {
            "name": CODEX_MIGRATION_PLUGIN_NAME,
            "version": CODEX_MIGRATION_PLUGIN_VERSION,
        },
    )
    _write_json(
        plugin / "migration-bundle.json",
        {
            "purpose": "oauth_migration_only",
            "codex_agent_runtime_dependencies_bundled": False,
        },
    )
    (plugin / "dist").mkdir()
    (plugin / "dist/index.js").write_text("export default {};", encoding="utf-8")
    manager = GatewayManager(repo_root=tmp_path)

    def migration_ready():
        return next(
            ok
            for name, ok, _ in manager.verify_runtime()
            if name == "codex_oauth_migration_provider"
        )

    assert migration_ready() is True
    _write_json(modules / "@openai/codex/package.json", {"name": "@openai/codex"})
    assert migration_ready() is False


def _subscription_config() -> dict[str, object]:
    return {
        "models": {
            "providers": {
                "openai": {
                    "api": "openai-chatgpt-responses",
                    "models": [{"id": "gpt-5.4-mini"}],
                }
            }
        },
        "plugins": {
            "allow": ["dicom-overlay-agent-harness"],
            "load": {"paths": ["C:/app/harness"]},
            "entries": {"dicom-overlay-agent-harness": {"enabled": True}},
        },
    }


def test_subscription_transport_rejects_platform_api_fallback(tmp_path) -> None:
    config = tmp_path / "openclaw.json"
    payload = _subscription_config()
    _write_json(config, payload)
    assert uses_codex_subscription_transport(config) is True

    payload["models"]["providers"]["openai"]["apiKey"] = "secret"
    _write_json(config, payload)
    assert uses_codex_subscription_transport(config) is False


def test_auth_import_uses_plugin_only_for_migration(monkeypatch, tmp_path) -> None:
    config = tmp_path / "openclaw.json"
    source = tmp_path / "native-codex"
    state = tmp_path / "openclaw-home"
    plugin = tmp_path / "openclaw" / "dist" / "extensions" / "codex"
    audit = tmp_path / "audit.json"
    cli = tmp_path / "openclaw.mjs"
    _write_json(config, _subscription_config())
    _write_json(
        source / "auth.json",
        {
            "auth_mode": "chatgpt",
            "tokens": {"access_token": "never-log-me"},
            "OPENAI_API_KEY": "never-copy-me",
        },
    )
    _write_json(
        plugin / "package.json",
        {
            "name": CODEX_MIGRATION_PLUGIN_NAME,
            "version": CODEX_MIGRATION_PLUGIN_VERSION,
        },
    )
    _write_json(
        plugin / "openclaw.plugin.json",
        {"id": "codex", "contracts": {"migrationProviders": ["codex"]}},
    )
    _write_json(
        plugin / "migration-bundle.json",
        {
            "purpose": "oauth_migration_only",
            "codex_agent_runtime_dependencies_bundled": False,
        },
    )
    (plugin / "dist").mkdir()
    (plugin / "dist" / "index.js").write_text("export default {};", encoding="utf-8")
    cli.write_text("", encoding="utf-8")
    calls: list[tuple[list[str], dict[str, str], int]] = []

    def fake_run(command, **kwargs):
        calls.append((list(command), dict(kwargs["env"]), int(kwargs["timeout"])))
        if "migrate" in command:
            assert command[command.index("--item") + 1] == "auth:openai"
            sanitized_source = command[command.index("--from") + 1]
            disabled_runtime = Path(kwargs["env"]["OPENCLAW_CODEX_APP_SERVER_BIN"])
            assert disabled_runtime.parent == Path(sanitized_source)
            assert not disabled_runtime.exists()
            copied_auth = json.loads(
                (Path(sanitized_source) / "auth.json").read_text(encoding="utf-8")
            )
            assert set(copied_auth) == {"auth_mode", "tokens"}
            payload = json.loads(config.read_text(encoding="utf-8"))
            codex_policy = payload["plugins"]["entries"]["codex"]["config"]
            assert codex_policy["supervision"]["enabled"] is False
            assert codex_policy["sessionCatalog"]["enabled"] is False
            assert codex_policy["discovery"]["enabled"] is False
            payload["auth"] = {
                "profiles": {
                    "openai:codex-import": {
                        "provider": "openai",
                        "mode": "oauth",
                        "email": "private@example.invalid",
                    }
                }
            }
            _write_json(config, payload)
            return SimpleNamespace(returncode=0, stdout="{}", stderr="")
        profile_ready = "auth" in json.loads(config.read_text(encoding="utf-8"))
        profiles = (
            [
                {
                    "id": "openai:codex-import",
                    "provider": "openai",
                    "type": "oauth",
                }
            ]
            if profile_ready
            else []
        )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"profiles": profiles}),
            stderr="",
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    import_args = {
        "node_executable": "node",
        "openclaw_cli": cli,
        "config_path": config,
        "state_home": state,
        "source_codex_home": source,
        "plugin_path": plugin,
        "working_directory": tmp_path,
        "audit_path": audit,
        "environment": {
            "OPENAI_API_KEY": "must-not-leak",
            "CODEX_HOME": "must-not-leak",
            "PATH": "test-path",
        },
    }
    result = ensure_openclaw_subscription_auth(**import_args)

    assert result["status"] == "ready"
    commands = [command for command, _env, _timeout in calls]
    assert sum("migrate" in command for command in commands) == 1
    assert all("app-server" not in command for command in commands)
    assert all("OPENAI_API_KEY" not in env for _command, env, _timeout in calls)
    assert all("CODEX_HOME" not in env for _command, env, _timeout in calls)
    assert all(timeout > 0 for _command, _env, timeout in calls)
    final_config = json.loads(config.read_text(encoding="utf-8"))
    assert "codex" not in final_config["plugins"]["allow"]
    assert final_config["plugins"]["entries"]["codex"] == {"enabled": False}
    assert final_config["plugins"]["load"]["paths"] == ["C:/app/harness"]
    assert "email" not in final_config["auth"]["profiles"]["openai:codex-import"]
    audit_text = audit.read_text(encoding="utf-8")
    assert "never-log-me" not in audit_text
    assert "must-not-leak" not in audit_text
    assert 'codex_agent_runtime_enabled": false' in audit_text
    assert 'temporary_migration_plugin_config_removed": true' in audit_text

    # Unchanged native credentials can reuse OpenClaw's own refreshed profile.
    second = ensure_openclaw_subscription_auth(**import_args)
    assert second["reused_existing_profile"] is True
    assert sum("migrate" in command for command, _, _ in calls) == 1

    # A native rotation must re-import even when `models auth list` still sees
    # the old profile; that public command does not validate refresh-token age.
    _write_json(
        source / "auth.json",
        {"auth_mode": "chatgpt", "tokens": {"access_token": "rotated-private"}},
    )
    third = ensure_openclaw_subscription_auth(**import_args)
    assert third["reused_existing_profile"] is False
    assert third["source_auth_sha256"] != second["source_auth_sha256"]
    assert sum("migrate" in command for command, _, _ in calls) == 2
    assert "rotated-private" not in audit.read_text(encoding="utf-8")
