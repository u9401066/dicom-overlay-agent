"""Persistence helpers for the desktop OpenClaw control panel."""

from __future__ import annotations

import json
import secrets
from typing import TYPE_CHECKING, Any

import yaml

from dicom_overlay.infrastructure.env_file import read_env_file
from dicom_overlay.infrastructure.openclaw_settings import (
    ProviderProfile,
    build_openclaw_config,
    merge_openclaw_config,
)

if TYPE_CHECKING:
    from pathlib import Path

    from dicom_overlay.domain.entities import TriggerMode


class DesktopSettingsStore:
    """Writes the small config surface managed by the desktop GUI."""

    def __init__(
        self,
        repo_root: Path,
        *,
        config_path: Path | None = None,
        env_path: Path | None = None,
        openclaw_config_path: Path | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._config_path = config_path or repo_root / "config.yaml"
        self._env_path = env_path or repo_root / ".env"
        self._openclaw_config_path = (
            openclaw_config_path or repo_root / "openclaw" / "openclaw.json"
        )

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def env_path(self) -> Path:
        return self._env_path

    @property
    def openclaw_config_path(self) -> Path:
        return self._openclaw_config_path

    def save_trigger_mode(self, mode: TriggerMode) -> None:
        raw = self._read_yaml(self._config_path)
        analysis = raw.setdefault("analysis", {})
        analysis["trigger_mode"] = mode.value
        self._write_yaml(self._config_path, raw)

    def save_provider_profile(
        self,
        profile: ProviderProfile,
        *,
        api_key: str,
        gateway_token: str,
    ) -> None:
        env_updates: dict[str, str] = {}
        if api_key.strip():
            env_updates[profile.api_key_env] = api_key.strip()
        if gateway_token.strip():
            env_updates["OPENCLAW_GATEWAY_TOKEN"] = gateway_token.strip()
        elif "OPENCLAW_GATEWAY_TOKEN" not in self._read_env_map():
            env_updates["OPENCLAW_GATEWAY_TOKEN"] = secrets.token_urlsafe(24)

        if env_updates:
            self._write_env_updates(env_updates)

        existing = self._read_openclaw_config()
        managed = build_openclaw_config(profile)
        merged = merge_openclaw_config(existing, managed)
        self._openclaw_config_path.parent.mkdir(parents=True, exist_ok=True)
        self._openclaw_config_path.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _read_openclaw_config(self) -> dict[str, Any]:
        if not self._openclaw_config_path.exists():
            return {}
        text = self._openclaw_config_path.read_text(encoding="utf-8").strip()
        if not text:
            return {}
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}

    def _read_env_map(self) -> dict[str, str]:
        return read_env_file(self._env_path)

    def _write_env_updates(self, updates: dict[str, str]) -> None:
        lines: list[str] = []
        seen: set[str] = set()
        if self._env_path.exists():
            for line in self._env_path.read_text(encoding="utf-8").splitlines():
                if "=" not in line or line.lstrip().startswith("#"):
                    lines.append(line)
                    continue
                key = line.split("=", 1)[0].strip()
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                    seen.add(key)
                else:
                    lines.append(line)
        for key, value in updates.items():
            if key not in seen:
                lines.append(f"{key}={value}")
        self._env_path.parent.mkdir(parents=True, exist_ok=True)
        self._env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _write_yaml(path: Path, raw: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.dump(raw, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
