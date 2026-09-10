from __future__ import annotations

import json

from dicom_overlay.infrastructure.desktop_settings_store import DesktopSettingsStore
from dicom_overlay.infrastructure.openclaw_settings import default_provider_profiles


def test_subscription_model_switch_persists_effort_without_api_key(tmp_path):
    store = DesktopSettingsStore(repo_root=tmp_path)
    profiles = {profile.key: profile for profile in default_provider_profiles()}
    for key, model, effort in (
        ("openai-codex-luna", "openai/gpt-5.6-luna", "high"),
        ("openai-codex-astra", "openai/gpt-6-astra", "low"),
        ("openai-codex-luna", "openai/gpt-5.6-luna", "high"),
    ):
        store.save_provider_profile(profiles[key], api_key="", gateway_token="")
        payload = json.loads(store.openclaw_config_path.read_text(encoding="utf-8"))
        defaults = payload["agents"]["defaults"]
        assert defaults["model"]["primary"] == model
        assert defaults["model"]["fallbacks"] == []
        assert defaults["thinkingDefault"] == effort
        provider = payload["models"]["providers"]["openai"]
        assert provider["api"] == "openai-chatgpt-responses"
        assert "apiKey" not in provider
        assert "baseUrl" not in provider
    store.save_provider_profile(profiles["openai-vision"], api_key="", gateway_token="")
    payload = json.loads(store.openclaw_config_path.read_text(encoding="utf-8"))
    assert "thinkingDefault" not in payload["agents"]["defaults"]
