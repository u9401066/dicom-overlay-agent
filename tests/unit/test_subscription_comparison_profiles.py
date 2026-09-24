from __future__ import annotations

import json

from dicom_overlay.infrastructure.desktop_settings_store import DesktopSettingsStore
from dicom_overlay.infrastructure.openclaw_settings import default_provider_profiles


def test_subscription_model_switch_persists_effort_without_api_key(tmp_path):
    store = DesktopSettingsStore(repo_root=tmp_path)
    profiles = {profile.key: profile for profile in default_provider_profiles()}
    for key, model, effort in (
        ("openai-codex-luna", "openai/gpt-5.6-luna", "high"),
        ("openai-codex-astra", "openai/gpt-6-astra", "medium"),
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


def test_astra_selection_replaces_previous_low_effort_without_changing_route(tmp_path):
    from dataclasses import replace

    store = DesktopSettingsStore(repo_root=tmp_path)
    profile = next(p for p in default_provider_profiles() if p.key == "openai-codex-astra")
    store.save_provider_profile(replace(profile, reasoning_effort="low"), api_key="", gateway_token="")
    store.save_provider_profile(profile, api_key="", gateway_token="")
    payload = json.loads(store.openclaw_config_path.read_text(encoding="utf-8"))
    defaults = payload["agents"]["defaults"]
    assert defaults["thinkingDefault"] == "medium"
    assert defaults["model"] == {"primary": "openai/gpt-6-astra", "fallbacks": []}
    assert defaults["models"]["openai/gpt-6-astra"]["agentRuntime"] == {"id": "openclaw"}
    assert payload["models"]["providers"]["openai"]["api"] == "openai-chatgpt-responses"
    assert "apiKey" not in payload["models"]["providers"]["openai"]
    assert "baseUrl" not in payload["models"]["providers"]["openai"]
