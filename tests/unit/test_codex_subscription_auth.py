from __future__ import annotations

import json
from types import SimpleNamespace

from dicom_overlay.infrastructure.codex_subscription_auth import (
    CODEX_MIGRATION_PLUGIN_NAME,
    CODEX_MIGRATION_PLUGIN_VERSION,
    ensure_openclaw_subscription_auth,
    uses_codex_subscription_transport,
)


def _write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


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
        {"auth_mode": "chatgpt", "tokens": {"access_token": "never-log-me"}},
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
            payload = json.loads(config.read_text(encoding="utf-8"))
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

    result = ensure_openclaw_subscription_auth(
        node_executable="node",
        openclaw_cli=cli,
        config_path=config,
        state_home=state,
        source_codex_home=source,
        plugin_path=plugin,
        working_directory=tmp_path,
        audit_path=audit,
        environment={
            "OPENAI_API_KEY": "must-not-leak",
            "CODEX_HOME": "must-not-leak",
            "PATH": "test-path",
        },
    )

    assert result["status"] == "ready"
    commands = [command for command, _env, _timeout in calls]
    assert sum("migrate" in command for command in commands) == 1
    assert all("app-server" not in command for command in commands)
    assert all("OPENAI_API_KEY" not in env for _command, env, _timeout in calls)
    assert all("CODEX_HOME" not in env for _command, env, _timeout in calls)
    assert all(timeout > 0 for _command, _env, timeout in calls)
    final_config = json.loads(config.read_text(encoding="utf-8"))
    assert "codex" not in final_config["plugins"]["allow"]
    assert "codex" not in final_config["plugins"]["entries"]
    assert final_config["plugins"]["load"]["paths"] == ["C:/app/harness"]
    assert "email" not in final_config["auth"]["profiles"]["openai:codex-import"]
    audit_text = audit.read_text(encoding="utf-8")
    assert "never-log-me" not in audit_text
    assert "must-not-leak" not in audit_text
    assert 'codex_agent_runtime_enabled": false' in audit_text
    assert 'temporary_migration_plugin_config_removed": true' in audit_text
