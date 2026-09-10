from __future__ import annotations

from dicom_overlay.infrastructure.openclaw_settings import (
    ProviderAuthMode,
    build_openclaw_config,
    default_provider_profiles,
)


def test_luna_codex_subscription_profile_uses_oauth_transport_without_api_key() -> None:
    profile = next(
        item
        for item in default_provider_profiles()
        if item.key == "openai-codex-luna"
    )

    assert profile.model_ref == "openai/gpt-5.6-luna"
    assert profile.auth_mode is ProviderAuthMode.CODEX_SUBSCRIPTION
    assert profile.api == "openai-chatgpt-responses"
    assert profile.api_key_env == ""
    assert profile.input_modalities == ("text", "image")

    config = build_openclaw_config(profile)
    provider = config["models"]["providers"]["openai"]
    model = provider["models"][0]

    assert provider["api"] == "openai-chatgpt-responses"
    assert "apiKey" not in provider
    assert "baseUrl" not in provider
    assert model["id"] == "gpt-5.6-luna"
    assert model["input"] == ["text", "image"]
    assert config["agents"]["defaults"]["model"]["primary"] == (
        "openai/gpt-5.6-luna"
    )
    assert config["agents"]["defaults"]["models"]["openai/gpt-5.6-luna"][
        "agentRuntime"
    ] == {"id": "openclaw"}


def test_luna_subscription_and_api_key_profiles_remain_explicitly_distinct() -> None:
    profiles = {
        item.key: item
        for item in default_provider_profiles()
        if item.model == "gpt-5.6-luna"
    }

    assert set(profiles) == {"openai-codex-luna", "openai-luna"}
    assert profiles["openai-codex-luna"].auth_mode is (
        ProviderAuthMode.CODEX_SUBSCRIPTION
    )
    assert profiles["openai-luna"].auth_mode is ProviderAuthMode.API_KEY
