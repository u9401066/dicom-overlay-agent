"""Desktop-facing OpenClaw provider settings helpers.

The desktop app owns a narrow, safe subset of OpenClaw configuration: model
provider credentials, the default model, and vision-readiness metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


DEFAULT_INFERENCE_TIMEOUT_SEC = 180
DEFAULT_VISION_PROFILE_KEY = "openai-vision"
DEFAULT_VISION_MODEL_REF = "openai/gpt-5.4-mini"
_PROVIDER_TIMEOUT_HEADROOM_SEC = 15
_AGENT_TIMEOUT_HEADROOM_SEC = 5


class ProviderType(Enum):
    """Provider families exposed by the desktop settings UI."""

    OPENAI = "openai"
    OPENROUTER = "openrouter"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    OPENAI_COMPATIBLE = "openai_compatible"
    GITHUB_COPILOT_BYOK = "github_copilot_byok"


class ProviderAuthMode(Enum):
    """Authentication/billing routes supported by desktop provider presets."""

    API_KEY = "api_key"
    CODEX_SUBSCRIPTION = "codex_subscription"


@dataclass(frozen=True)
class ProviderProfile:
    """A provider/model profile that can be translated into OpenClaw config."""

    key: str
    label: str
    provider_id: str
    provider_type: ProviderType
    model: str
    api_key_env: str
    auth_mode: ProviderAuthMode = ProviderAuthMode.API_KEY
    base_url: str = ""
    api: str = ""
    input_modalities: tuple[str, ...] = ()
    context_window: int = 0
    max_tokens: int = 0
    reasoning: bool = False
    agent_runtime: str = ""
    requires_vision_check: bool = True
    notes: str = ""

    @property
    def model_ref(self) -> str:
        """OpenClaw model reference in provider/model form."""
        return f"{self.provider_id}/{self.model}"


def default_provider_profiles() -> list[ProviderProfile]:
    """Return desktop presets for the providers requested by the product."""
    return [
        ProviderProfile(
            key="openai-vision",
            label="OpenAI GPT-5.4 Mini Vision",
            provider_id="openai",
            provider_type=ProviderType.OPENAI,
            model="gpt-5.4-mini",
            api_key_env="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
            api="openai-responses",
            input_modalities=("text", "image"),
            context_window=400_000,
            max_tokens=128_000,
            reasoning=True,
            agent_runtime="openclaw",
            notes="Cost-efficient OpenAI multimodal default with tool support.",
        ),
        ProviderProfile(
            key="openai-codex",
            label="OpenAI Subscription via OpenClaw",
            provider_id="openai",
            provider_type=ProviderType.OPENAI,
            model="gpt-5.4-mini",
            api_key_env="",
            auth_mode=ProviderAuthMode.CODEX_SUBSCRIPTION,
            api="openai-chatgpt-responses",
            input_modalities=("text", "image"),
            context_window=400_000,
            max_tokens=128_000,
            reasoning=True,
            agent_runtime="openclaw",
            notes=(
                "OpenClaw owns the agent loop and uses the local ChatGPT/Codex "
                "OAuth allowance for inference. Run `codex login` first; no "
                "Platform API key or Codex agent runtime is used."
            ),
        ),
        ProviderProfile(
            key="openai-luna",
            label="OpenAI GPT-5.6 Luna Vision",
            provider_id="openai",
            provider_type=ProviderType.OPENAI,
            model="gpt-5.6-luna",
            api_key_env="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
            api="openai-responses",
            input_modalities=("text", "image"),
            context_window=1_050_000,
            max_tokens=128_000,
            reasoning=True,
            agent_runtime="openclaw",
            notes="Preview high-volume OpenAI multimodal profile.",
        ),
        ProviderProfile(
            key="openrouter",
            label="OpenRouter",
            provider_id="openrouter",
            provider_type=ProviderType.OPENROUTER,
            model="minimax/minimax-m3",
            api_key_env="OPENROUTER_API_KEY",
            base_url="https://openrouter.ai/api/v1",
            notes="Default OpenRouter vision-capable profile for MiniMax M3.",
        ),
        ProviderProfile(
            key="anthropic",
            label="Anthropic Claude",
            provider_id="anthropic",
            provider_type=ProviderType.ANTHROPIC,
            model="claude-sonnet-4-6",
            api_key_env="ANTHROPIC_API_KEY",
            base_url="https://api.anthropic.com",
        ),
        ProviderProfile(
            key="azure-openai",
            label="Azure OpenAI",
            provider_id="azure",
            provider_type=ProviderType.AZURE_OPENAI,
            model="YOUR-DEPLOYMENT-NAME",
            api_key_env="AZURE_OPENAI_API_KEY",
            base_url="https://YOUR-RESOURCE.openai.azure.com/openai/deployments/YOUR-DEPLOYMENT-NAME",
        ),
        ProviderProfile(
            key="openai-compatible",
            label="OpenAI-compatible endpoint",
            provider_id="custom",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            model="YOUR-MODEL-NAME",
            api_key_env="CUSTOM_API_KEY",
            base_url="http://localhost:11434/v1",
        ),
        ProviderProfile(
            key="github-copilot-byok",
            label="GitHub Copilot CLI BYOK-compatible",
            provider_id="copilot-byok",
            provider_type=ProviderType.GITHUB_COPILOT_BYOK,
            model="YOUR-COPILOT-BYOK-MODEL",
            api_key_env="COPILOT_PROVIDER_API_KEY",
            base_url="https://api.openai.com/v1",
            notes=(
                "For official Copilot CLI BYOK/OpenAI-compatible provider flows; "
                "not a Copilot subscription token bridge."
            ),
        ),
    ]


def build_analysis_tool_policy(allowed_tools: list[str]) -> dict[str, Any]:
    """Build the bounded tool surface used by screenshot-analysis agents."""

    unique_tools = list(dict.fromkeys(allowed_tools))
    policy: dict[str, Any] = {
        "web": {
            "search": {"enabled": False},
            "fetch": {"enabled": False},
        },
    }
    if unique_tools:
        policy["allow"] = unique_tools
    else:
        # OpenClaw treats an empty allowlist as unspecified/permissive. A
        # wildcard deny is the explicit text-only control-arm policy.
        policy["deny"] = ["*"]
    return policy


def build_openclaw_config(
    profile: ProviderProfile,
    *,
    gateway_token_env: str = "OPENCLAW_GATEWAY_TOKEN",
    image_max_dimension_px: int = 1568,
    inference_timeout_sec: int = DEFAULT_INFERENCE_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Build the OpenClaw config subset managed by this desktop app.

    Secrets are represented as OpenClaw SecretRef objects so generated config
    can remain shareable while values live in the local environment/.env file.
    """
    provider_timeout_sec, agent_timeout_sec = derive_openclaw_timeout_budget(
        inference_timeout_sec
    )
    provider_configs: dict[str, Any] = {}
    if profile.auth_mode is ProviderAuthMode.CODEX_SUBSCRIPTION:
        provider_config: dict[str, Any] = {
            "timeoutSeconds": provider_timeout_sec,
        }
        if profile.base_url:
            provider_config["baseUrl"] = profile.base_url
        if profile.api:
            provider_config["api"] = profile.api
        provider_configs[profile.provider_id] = provider_config
    else:
        if not profile.api_key_env:
            raise ValueError("API-key provider profiles require api_key_env")
        provider_config = {
            "apiKey": {
                "source": "env",
                "provider": "default",
                "id": profile.api_key_env,
            },
            "timeoutSeconds": provider_timeout_sec,
        }
        if profile.base_url:
            provider_config["baseUrl"] = profile.base_url
        if profile.api:
            provider_config["api"] = profile.api
        provider_configs[profile.provider_id] = provider_config
    if profile.input_modalities:
        model_config: dict[str, Any] = {
            "id": profile.model,
            "name": profile.label,
            "input": list(profile.input_modalities),
            "reasoning": profile.reasoning,
        }
        if profile.context_window > 0:
            model_config["contextWindow"] = profile.context_window
        if profile.max_tokens > 0:
            model_config["maxTokens"] = profile.max_tokens
        if profile.agent_runtime:
            model_config["agentRuntime"] = {"id": profile.agent_runtime}
        provider_config["models"] = [model_config]

    config: dict[str, Any] = {
        "gateway": {
            "mode": "local",
            "auth": {
                "token": f"${{{gateway_token_env}}}",
            },
        },
        "models": {
            "mode": "merge",
            "providers": provider_configs,
        },
        "agents": {
            "defaults": {
                "model": {
                    "primary": profile.model_ref,
                    "fallbacks": [],
                },
                "models": {
                    profile.model_ref: {
                        "alias": profile.label,
                        **(
                            {"agentRuntime": {"id": profile.agent_runtime}}
                            if profile.agent_runtime
                            else {}
                        ),
                    },
                },
                "imageMaxDimensionPx": image_max_dimension_px,
                "timeoutSeconds": agent_timeout_sec,
            },
        },
        "tools": build_analysis_tool_policy(["dicom_bbox_validate"]),
    }
    return config


def derive_openclaw_timeout_budget(inference_timeout_sec: int) -> tuple[int, int]:
    """Keep provider and agent watchdogs below the desktop receive timeout."""
    if (
        isinstance(inference_timeout_sec, bool)
        or not isinstance(inference_timeout_sec, int)
        or inference_timeout_sec < 30
    ):
        raise ValueError("inference_timeout_sec must be an integer >= 30")
    provider_timeout_sec = inference_timeout_sec - _PROVIDER_TIMEOUT_HEADROOM_SEC
    agent_timeout_sec = inference_timeout_sec - _AGENT_TIMEOUT_HEADROOM_SEC
    return provider_timeout_sec, agent_timeout_sec


def merge_openclaw_config(
    existing: dict[str, Any], managed: dict[str, Any]
) -> dict[str, Any]:
    """Merge desktop-managed OpenClaw sections without touching channels/skills."""
    result = dict(existing)
    for key in ("gateway", "models", "agents"):
        result[key] = _deep_merge(result.get(key, {}), managed.get(key, {}))
    managed_providers = managed.get("models", {}).get("providers", {})
    if isinstance(managed_providers, dict):
        result_providers = result.setdefault("models", {}).setdefault("providers", {})
        for provider_id, provider_config in managed_providers.items():
            # Switching auth routes must not retain stale apiKey/baseUrl/model
            # transport fields from the prior provider configuration.
            result_providers[provider_id] = provider_config
    managed_plugins = managed.get("plugins")
    if isinstance(managed_plugins, dict):
        existing_plugins = result.get("plugins", {})
        existing_allow = existing_plugins.get("allow", [])
        managed_allow = managed_plugins.get("allow", [])
        result["plugins"] = _deep_merge(existing_plugins, managed_plugins)
        result["plugins"]["allow"] = list(
            dict.fromkeys([*existing_allow, *managed_allow])
        )
    if _uses_openclaw_subscription_transport(managed_providers):
        _remove_codex_runtime_plugin_config(result)
    return result


def _uses_openclaw_subscription_transport(providers: object) -> bool:
    if not isinstance(providers, dict):
        return False
    openai = providers.get("openai")
    if not isinstance(openai, dict):
        return False
    if openai.get("api") != "openai-chatgpt-responses":
        return False
    models = openai.get("models", [])
    return isinstance(models, list) and any(
        isinstance(model, dict) and model.get("agentRuntime") == {"id": "openclaw"}
        for model in models
    )


def _remove_codex_runtime_plugin_config(config: dict[str, Any]) -> None:
    plugins = config.get("plugins")
    if not isinstance(plugins, dict):
        return
    allow = plugins.get("allow")
    if isinstance(allow, list):
        plugins["allow"] = [item for item in allow if item != "codex"]
    entries = plugins.get("entries")
    if isinstance(entries, dict):
        entries.pop("codex", None)
    load = plugins.get("load")
    paths = load.get("paths") if isinstance(load, dict) else None
    if isinstance(paths, list):
        load["paths"] = [
            item for item in paths if not _is_codex_plugin_source_path(item)
        ]


def _is_codex_plugin_source_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.replace("\\", "/").rstrip("/").lower()
    return normalized.endswith("/@openclaw/codex")


def _deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def ensure_parent(path: Path) -> None:
    """Create the parent directory for a generated settings file."""
    path.parent.mkdir(parents=True, exist_ok=True)
