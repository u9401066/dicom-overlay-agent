"""Import ChatGPT OAuth into OpenClaw without enabling the Codex agent runtime."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping


CODEX_MIGRATION_PLUGIN_NAME = "@openclaw/codex"
CODEX_MIGRATION_PLUGIN_VERSION = "2026.7.1-1"
_AUTH_PROBE_TIMEOUT_SEC = 120
_AUTH_MIGRATION_TIMEOUT_SEC = 180


def uses_codex_subscription_transport(config_path: Path) -> bool:
    """Return whether the active OpenAI provider uses subscription transport."""
    config = _read_json(config_path)
    providers = config.get("models", {}).get("providers", {})
    openai = providers.get("openai") if isinstance(providers, dict) else None
    return bool(
        isinstance(openai, dict)
        and openai.get("api") == "openai-chatgpt-responses"
        and "apiKey" not in openai
        and "baseUrl" not in openai
    )


def resolve_native_codex_home(environment: Mapping[str, str]) -> Path:
    configured = environment.get("CODEX_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    native_home = (
        environment.get("USERPROFILE", "").strip()
        or environment.get("HOME", "").strip()
    )
    if not native_home:
        raise RuntimeError("Could not locate the local Codex ChatGPT sign-in")
    return (Path(native_home).expanduser() / ".codex").resolve()


def ensure_openclaw_subscription_auth(
    *,
    node_executable: str,
    openclaw_cli: Path,
    config_path: Path,
    state_home: Path,
    source_codex_home: Path,
    plugin_path: Path,
    working_directory: Path,
    audit_path: Path,
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Import only OAuth state through the pinned official migration provider."""
    if not uses_codex_subscription_transport(config_path):
        return {"status": "not_required"}
    _verify_source_auth(source_codex_home)
    _verify_migration_plugin(plugin_path)
    state_home.mkdir(parents=True, exist_ok=True)
    env = dict(environment or os.environ)
    platform_key_was_present = bool(env.pop("OPENAI_API_KEY", "").strip())
    env.pop("CODEX_HOME", None)
    env.update(
        {
            "OPENCLAW_HOME": str(state_home),
            "OPENCLAW_STATE_DIR": str(state_home),
            "OPENCLAW_CONFIG_PATH": str(config_path),
            "HOME": str(state_home),
            "USERPROFILE": str(state_home),
        }
    )
    if _auth_profile_is_ready(
        node_executable=node_executable,
        openclaw_cli=openclaw_cli,
        config_path=config_path,
        working_directory=working_directory,
        environment=env,
    ):
        audit = _auth_audit(
            status="ready",
            reused=True,
            platform_key_was_present=platform_key_was_present,
        )
        _write_json_atomic(audit_path, audit)
        return audit

    _enable_migration_plugin(config_path, plugin_path)
    migration_exit = 1
    migration_diagnostic = ""
    try:
        with tempfile.TemporaryDirectory(
            prefix="codex-auth-source-",
            dir=state_home,
        ) as source_text:
            sanitized_source = Path(source_text)
            shutil.copy2(
                source_codex_home / "auth.json", sanitized_source / "auth.json"
            )
            models_cache = source_codex_home / "models_cache.json"
            if models_cache.is_file():
                shutil.copy2(models_cache, sanitized_source / "models_cache.json")
            try:
                process = subprocess.run(
                    [
                        node_executable,
                        str(openclaw_cli),
                        "migrate",
                        "apply",
                        "codex",
                        "--from",
                        str(sanitized_source),
                        "--include-secrets",
                        "--overwrite",
                        "--yes",
                        "--no-backup",
                        "--force",
                        "--json",
                    ],
                    cwd=working_directory,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=_AUTH_MIGRATION_TIMEOUT_SEC,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    ),
                )
                migration_exit = int(process.returncode)
                if migration_exit != 0:
                    migration_diagnostic = _sanitize_diagnostic(
                        process.stderr or process.stdout
                    )
            except subprocess.TimeoutExpired:
                migration_exit = 124
                migration_diagnostic = "OAuth migration command timed out"
    finally:
        _remove_migration_plugin(config_path, plugin_path)

    ready = migration_exit == 0 and _auth_profile_is_ready(
        node_executable=node_executable,
        openclaw_cli=openclaw_cli,
        config_path=config_path,
        working_directory=working_directory,
        environment=env,
    )
    if ready:
        _remove_auth_email_metadata(config_path)
    audit = _auth_audit(
        status="ready" if ready else "failed",
        reused=False,
        platform_key_was_present=platform_key_was_present,
        migration_exit=migration_exit,
        diagnostic=migration_diagnostic,
    )
    _write_json_atomic(audit_path, audit)
    if not ready:
        raise RuntimeError(
            "OpenClaw could not import the local ChatGPT subscription sign-in"
        )
    return audit


def _verify_source_auth(source_home: Path) -> None:
    auth_path = source_home / "auth.json"
    auth = _read_json(auth_path)
    if auth.get("auth_mode") != "chatgpt" or not isinstance(auth.get("tokens"), dict):
        raise RuntimeError("Run `codex login` with ChatGPT before using subscription")


def _verify_migration_plugin(plugin_path: Path) -> None:
    package = _read_json(plugin_path / "package.json")
    manifest = _read_json(plugin_path / "openclaw.plugin.json")
    bundle = _read_json(plugin_path / "migration-bundle.json")
    bundled_valid = bool(
        not _is_bundled_migration_plugin(plugin_path)
        or (
            bundle.get("purpose") == "oauth_migration_only"
            and bundle.get("codex_agent_runtime_dependencies_bundled") is False
            and not (plugin_path / "node_modules" / "@openai" / "codex").exists()
        )
    )
    if (
        package.get("name") != CODEX_MIGRATION_PLUGIN_NAME
        or package.get("version") != CODEX_MIGRATION_PLUGIN_VERSION
        or manifest.get("id") != "codex"
        or "codex" not in manifest.get("contracts", {}).get("migrationProviders", [])
        or not (plugin_path / "dist" / "index.js").is_file()
        or not bundled_valid
    ):
        raise RuntimeError("Pinned official Codex migration provider is unavailable")


def _auth_profile_is_ready(
    *,
    node_executable: str,
    openclaw_cli: Path,
    config_path: Path,
    working_directory: Path,
    environment: Mapping[str, str],
) -> bool:
    try:
        process = subprocess.run(
            [
                node_executable,
                str(openclaw_cli),
                "models",
                "auth",
                "list",
                "--agent",
                "main",
                "--json",
            ],
            cwd=working_directory,
            env=dict(environment),
            capture_output=True,
            text=True,
            check=False,
            timeout=_AUTH_PROBE_TIMEOUT_SEC,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            ),
        )
    except subprocess.TimeoutExpired:
        return False
    if process.returncode != 0:
        return False
    try:
        store = json.loads(process.stdout)
    except json.JSONDecodeError:
        return False
    config = _read_json(config_path)
    profiles = store.get("profiles") if isinstance(store, dict) else None
    configured = config.get("auth", {}).get("profiles", {})
    if not isinstance(profiles, list) or not isinstance(configured, dict):
        return False
    return any(
        isinstance(profile, dict)
        and profile.get("type") == "oauth"
        and profile.get("provider") == "openai"
        and isinstance(configured.get(profile.get("id")), dict)
        and configured[profile["id"]].get("provider") == "openai"
        and configured[profile["id"]].get("mode") == "oauth"
        for profile in profiles
        if isinstance(profile, dict) and isinstance(profile.get("id"), str)
    )


def _enable_migration_plugin(config_path: Path, plugin_path: Path) -> None:
    config = _read_json(config_path)
    plugins = config.setdefault("plugins", {})
    if not isinstance(plugins, dict):
        plugins = {}
        config["plugins"] = plugins
    allow = plugins.setdefault("allow", [])
    if not isinstance(allow, list):
        allow = []
        plugins["allow"] = allow
    if "codex" not in allow:
        allow.append("codex")
    if not _is_bundled_migration_plugin(plugin_path):
        load = plugins.setdefault("load", {})
        if not isinstance(load, dict):
            load = {}
            plugins["load"] = load
        paths = load.setdefault("paths", [])
        if not isinstance(paths, list):
            paths = []
            load["paths"] = paths
        plugin_text = str(plugin_path.resolve())
        if plugin_text not in paths:
            paths.append(plugin_text)
    entries = plugins.setdefault("entries", {})
    if not isinstance(entries, dict):
        entries = {}
        plugins["entries"] = entries
    entries["codex"] = {"enabled": True}
    _write_json_atomic(config_path, config)


def _remove_migration_plugin(config_path: Path, plugin_path: Path) -> None:
    config = _read_json(config_path)
    plugins = config.get("plugins")
    if not isinstance(plugins, dict):
        return
    allow = plugins.get("allow")
    if isinstance(allow, list):
        plugins["allow"] = [value for value in allow if value != "codex"]
    entries = plugins.get("entries")
    if isinstance(entries, dict):
        entries.pop("codex", None)
    load = plugins.get("load")
    paths = load.get("paths") if isinstance(load, dict) else None
    if isinstance(paths, list):
        expected = plugin_path.resolve()
        retained: list[object] = []
        for value in paths:
            try:
                matches = isinstance(value, str) and Path(value).resolve() == expected
            except OSError:
                matches = False
            if not matches and not _looks_like_codex_plugin_path(value):
                retained.append(value)
        load["paths"] = retained
    _write_json_atomic(config_path, config)


def _looks_like_codex_plugin_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value.replace("\\", "/").rstrip("/").lower().endswith("/@openclaw/codex")


def _is_bundled_migration_plugin(plugin_path: Path) -> bool:
    normalized = plugin_path.resolve().as_posix().lower().rstrip("/")
    return normalized.endswith("/openclaw/dist/extensions/codex")


def _remove_auth_email_metadata(config_path: Path) -> None:
    config = _read_json(config_path)
    profiles = config.get("auth", {}).get("profiles", {})
    if not isinstance(profiles, dict):
        return
    for profile in profiles.values():
        if isinstance(profile, dict):
            profile.pop("email", None)
    _write_json_atomic(config_path, config)


def _auth_audit(
    *,
    status: str,
    reused: bool,
    platform_key_was_present: bool,
    migration_exit: int | None = None,
    diagnostic: str = "",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": status,
        "checked_at": datetime.now(UTC).isoformat(),
        "source_scope": "auth_and_model_cache_only",
        "provider": "openai",
        "auth_mode": "oauth",
        "billing_route": "chatgpt_codex_subscription",
        "agent_runtime": "openclaw",
        "codex_agent_runtime_enabled": False,
        "temporary_migration_plugin_config_removed": True,
        "platform_api_key_disabled": True,
        "platform_api_key_was_present_before_isolation": (platform_key_was_present),
        "reused_existing_profile": reused,
        "migration_exit_code": migration_exit,
        "diagnostic": diagnostic,
    }


def _sanitize_diagnostic(value: str) -> str:
    text = value[-2000:]
    text = re.sub(
        r"(?i)(access[_ -]?token|refresh[_ -]?token|authorization|bearer)"
        r"\s*[:=]\s*\S+",
        r"\1=[redacted]",
        text,
    )
    text = re.sub(r"[A-Za-z0-9_-]{40,}", "[redacted]", text)
    text = re.sub(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        "[redacted-email]",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        Path(temp_name).replace(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            Path(temp_name).unlink()
