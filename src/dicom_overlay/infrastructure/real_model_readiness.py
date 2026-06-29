"""Real-model benchmark readiness checks.

The 1000-case artifact gate proves the harness shape. A real-model benchmark
also needs credentials, a large manifest, and complete review artifacts. This
module records those prerequisites as a small JSON artifact without printing or
persisting secret values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dicom_overlay.infrastructure.eval_artifact_validator import (
    verify_eval_artifacts,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


_PROVIDER_ENV = {
    "openrouter/": "OPENROUTER_API_KEY",
    "openai/": "OPENAI_API_KEY",
    "anthropic/": "ANTHROPIC_API_KEY",
}


@dataclass(frozen=True)
class RealModelReadinessReport:
    """Auditable readiness result for a real model benchmark."""

    status: str
    model_id: str
    blockers: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    next_commands: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "model_id": self.model_id,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "evidence": self.evidence,
            "next_commands": self.next_commands,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


def required_env_var_for_model(model_id: str) -> str | None:
    """Return the provider API-key env var implied by an OpenClaw model id."""

    lower = model_id.lower()
    for prefix, env_var in _PROVIDER_ENV.items():
        if lower.startswith(prefix):
            return env_var
    return None


def assess_real_model_readiness(
    *,
    model_id: str,
    manifest_path: Path,
    eval_dir: Path | None = None,
    min_cases: int = 1000,
    env: Mapping[str, str | None] | None = None,
    openclaw_package_json: Path | None = None,
) -> RealModelReadinessReport:
    """Check whether a real-model benchmark can start safely.

    ``env`` is injectable for tests and should contain only names/values already
    in process memory. The resulting report never serializes the values.
    """

    env = env or {}
    blockers: list[dict[str, Any]] = []
    warnings: list[str] = []
    evidence: dict[str, Any] = {
        "manifest": str(manifest_path),
        "min_cases": min_cases,
    }

    required_env = required_env_var_for_model(model_id)
    if required_env:
        evidence["required_env_var"] = required_env
        evidence["provider_key_present"] = bool(env.get(required_env))
        if not env.get(required_env):
            blockers.append(
                {
                    "code": "missing_provider_key",
                    "message": f"{required_env} is required for model {model_id}",
                    "env_var": required_env,
                }
            )
    else:
        warnings.append(
            f"No provider env-var mapping is known for model id '{model_id}'."
        )

    case_count = _manifest_case_count(manifest_path, blockers)
    evidence["manifest_cases"] = case_count
    if case_count < min_cases:
        blockers.append(
            {
                "code": "manifest_too_small",
                "message": (
                    f"Manifest has {case_count} cases; at least {min_cases} "
                    "are required."
                ),
                "manifest": str(manifest_path),
            }
        )

    if eval_dir is not None:
        verification = verify_eval_artifacts(
            eval_dir=eval_dir,
            manifest_path=manifest_path,
            min_cases=min_cases,
        )
        evidence["eval_dir"] = str(eval_dir)
        evidence["eval_artifacts_ok"] = verification.ok
        evidence["eval_passed_checks"] = verification.passed_checks
        if not verification.ok:
            blockers.append(
                {
                    "code": "eval_artifacts_invalid",
                    "message": "1000-case artifact gate did not pass.",
                    "failures": verification.failures,
                }
            )
    else:
        warnings.append("No eval artifact directory was provided for verification.")
        evidence["eval_artifacts_ok"] = None

    package_json = openclaw_package_json or Path(
        "openclaw/node_modules/openclaw/package.json"
    )
    evidence["openclaw_package_json"] = str(package_json)
    evidence["openclaw_version"] = _read_openclaw_version(package_json, warnings)

    next_commands = _next_commands(model_id=model_id, manifest_path=manifest_path)
    return RealModelReadinessReport(
        status="ready" if not blockers else "blocked",
        model_id=model_id,
        blockers=blockers,
        warnings=warnings,
        evidence=evidence,
        next_commands=next_commands,
    )


def write_readiness_report(report: RealModelReadinessReport, path: Path) -> None:
    """Write a readiness JSON artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json() + "\n", encoding="utf-8")


def _manifest_case_count(path: Path, blockers: list[dict[str, Any]]) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        blockers.append(
            {
                "code": "manifest_missing",
                "message": f"Manifest not found: {path}",
                "manifest": str(path),
            }
        )
        return 0
    except Exception as exc:
        blockers.append(
            {
                "code": "manifest_unreadable",
                "message": f"Could not read manifest {path}: {exc}",
                "manifest": str(path),
            }
        )
        return 0
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    return len(cases) if isinstance(cases, list) else 0


def _read_openclaw_version(path: Path, warnings: list[str]) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        warnings.append(f"OpenClaw package.json not found: {path}")
        return None
    except Exception as exc:
        warnings.append(f"Could not read OpenClaw package.json {path}: {exc}")
        return None
    version = payload.get("version") if isinstance(payload, dict) else None
    return str(version) if version else None


def _next_commands(*, model_id: str, manifest_path: Path) -> list[str]:
    manifest = str(manifest_path)
    return [
        (
            "powershell -ExecutionPolicy Bypass -File "
            "scripts\\run-meeti-openclaw-experiment.ps1 "
            f"-ModelId {model_id} -ManifestPath {manifest} -TimeoutSec 90 "
            "-MultiPass -MultiPassMaxTargets 2 -RequirePerfect"
        )
    ]
