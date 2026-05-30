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


class ProviderType(Enum):
    """Provider families exposed by the desktop settings UI."""

    OPENAI = "openai"
    OPENROUTER = "openrouter"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    OPENAI_COMPATIBLE = "openai_compatible"
    GITHUB_COPILOT_BYOK = "github_copilot_byok"


@dataclass(frozen=True)
class ProviderProfile:
    """A provider/model profile that can be translated into OpenClaw config."""

    key: str
    label: str
    provider_id: str
    provider_type: ProviderType
    model: str
    api_key_env: str
    base_url: str = ""
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
            key="openai-codex",
            label="OpenAI Codex",
            provider_id="openai",
            provider_type=ProviderType.OPENAI,
            model="gpt-5.2-codex",
            api_key_env="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
            notes="Codex-family OpenAI API model. Requires image smoke test.",
        ),
        ProviderProfile(
            key="openai-vision",
            label="OpenAI Vision",
            provider_id="openai",
            provider_type=ProviderType.OPENAI,
            model="gpt-5.4-mini",
            api_key_env="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
            notes="Lower-latency OpenAI vision-capable default.",
        ),
        ProviderProfile(
            key="openrouter",
            label="OpenRouter",
            provider_id="openrouter",
            provider_type=ProviderType.OPENROUTER,
            model="openai/gpt-5.2-codex",
            api_key_env="OPENROUTER_API_KEY",
            base_url="https://openrouter.ai/api/v1",
            notes="Uses OpenRouter model IDs. Vision support is model-specific.",
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


def build_openclaw_config(
    profile: ProviderProfile,
    *,
    gateway_token_env: str = "OPENCLAW_GATEWAY_TOKEN",
    image_max_dimension_px: int = 1200,
) -> dict[str, Any]:
    """Build the OpenClaw config subset managed by this desktop app.

    Secrets are represented as OpenClaw SecretRef objects so generated config
    can remain shareable while values live in the local environment/.env file.
    """
    provider_config: dict[str, Any] = {
        "apiKey": {
            "source": "env",
            "provider": "default",
            "id": profile.api_key_env,
        },
    }
    if profile.base_url:
        provider_config["baseUrl"] = profile.base_url

    return {
        "gateway": {
            "auth": {
                "token": f"${{{gateway_token_env}}}",
            },
        },
        "models": {
            "providers": {
                profile.provider_id: provider_config,
            },
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
                    },
                },
                "imageMaxDimensionPx": image_max_dimension_px,
            },
        },
    }


def merge_openclaw_config(
    existing: dict[str, Any], managed: dict[str, Any]
) -> dict[str, Any]:
    """Merge desktop-managed OpenClaw sections without touching channels/skills."""
    result = dict(existing)
    for key in ("gateway", "models", "agents"):
        result[key] = _deep_merge(result.get(key, {}), managed.get(key, {}))
    return result


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
