"""Run a bounded MEETI OpenClaw experiment without shell wrappers."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dicom_overlay.infrastructure.gateway_manager import (
    GatewayManager,
    ecg_founder_tool_enabled,
    pid_is_running,
)
from dicom_overlay.infrastructure.openclaw_settings import (
    DEFAULT_INFERENCE_TIMEOUT_SEC,
    DEFAULT_VISION_MODEL_REF,
    ProviderProfile,
    build_analysis_tool_policy,
    build_openclaw_config,
    default_provider_profiles,
    derive_openclaw_timeout_budget,
    merge_openclaw_config,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    REPO_ROOT / "data" / "eval-datasets" / "meeti-1000-all" / "manifest.json"
)
OPENCLAW_CLI = REPO_ROOT / "openclaw" / "node_modules" / "openclaw" / "openclaw.mjs"
BASE_OPENCLAW_CONFIG = REPO_ROOT / "openclaw" / "openclaw.json"
GATEWAY_URL = "ws://127.0.0.1:18789"
OPENCLAW_GATEWAY_LOCK = REPO_ROOT / "data" / "tmp" / "openclaw-gateway.lock"
UV_TMP_RELATIVE = "data/tmp/uv"
MAX_CAPTURED_COMMAND_OUTPUT_CHARS = 200_000
DEFAULT_MIN_STRICT_PASS_RATE = 0.75
DEFAULT_MIN_MEAN_PARTIAL_CREDIT = 0.85
_PROVIDER_BLOCK_MARKERS = {
    "credit_balance_exhausted": (
        "provider_credit_exhausted",
        "Model provider credit balance is exhausted.",
    ),
    "insufficient_quota": (
        "provider_quota_exhausted",
        "Model provider quota is exhausted.",
    ),
    "invalid_api_key": (
        "provider_auth_invalid",
        "Model provider rejected the configured API key.",
    ),
    "billing_hard_limit_reached": (
        "provider_billing_limit",
        "Model provider billing hard limit was reached.",
    ),
}


@dataclass(frozen=True)
class GatewayProcess:
    process: subprocess.Popen[str]
    lock_dir: Path


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.resolve() if args.manifest else DEFAULT_MANIFEST
    experiment_dir = resolve_experiment_dir(args.experiment_dir, args.model_id)
    experiment_dir.mkdir(parents=True, exist_ok=True)
    state_home = (experiment_dir / "openclaw-state").resolve()
    env = build_child_env(REPO_ROOT, state_home=state_home)
    load_dotenv(REPO_ROOT / ".env", env)

    resume_stamp = datetime.now().strftime("%Y%m%d-%H%M%S") if args.resume else ""
    gateway_stdout_name = (
        f"gateway.resume-{resume_stamp}.stdout.log"
        if args.resume
        else "gateway.stdout.log"
    )
    gateway_stderr_name = (
        f"gateway.resume-{resume_stamp}.stderr.log"
        if args.resume
        else "gateway.stderr.log"
    )

    paths = {
        "experiment_json": experiment_dir / "experiment.json",
        "models_list": experiment_dir / "openclaw-models-list.txt",
        "config_generation": experiment_dir / "openclaw-config-generation.json",
        "gateway_stdout": experiment_dir / gateway_stdout_name,
        "gateway_stderr": experiment_dir / gateway_stderr_name,
        "eval_console": experiment_dir / "eval-console.log",
        "eval_dir": experiment_dir / "eval",
        "scorecard": experiment_dir / "eval" / "scorecard.json",
        "scorecard_rebuilt": experiment_dir / "eval" / "scorecard.rebuilt.json",
        "protocol_fingerprint": (experiment_dir / "eval" / "protocol-fingerprint.json"),
        "review_dir": experiment_dir / "eval" / "review",
        "openclaw_config": experiment_dir / "openclaw.experiment.json",
        "openclaw_state": state_home,
        "bbox_tool_audit": experiment_dir / "bbox-tool-audit.jsonl",
        "ecg_founder_tool_audit": experiment_dir / "ecgfounder-tool-audit.jsonl",
    }
    env["DICOM_BBOX_AUDIT_PATH"] = str(paths["bbox_tool_audit"])
    env["DICOM_ECGFOUNDER_AUDIT_PATH"] = str(paths["ecg_founder_tool_audit"])

    provider_profile = effective_provider_profile(
        args.model_id, args.provider_profile, env
    )
    env["DICOM_OVERLAY_PROVIDER_PROFILE"] = provider_profile

    # Keep the experiment on the same app-owned skill/plugin bytes as the
    # desktop Gateway.  openclaw-home is mutable state and may otherwise hold a
    # stale mirror from an earlier run.
    gateway_manager = GatewayManager(repo_root=REPO_ROOT)
    gateway_manager.prepare_workspace(state_home=state_home)
    node_executable = gateway_manager.node_executable()

    try:
        config_metadata = write_experiment_openclaw_config(
            base_config=BASE_OPENCLAW_CONFIG,
            target_config=paths["openclaw_config"],
            model_id=args.model_id,
            profile_key=provider_profile,
            harness_plugin_path=(
                state_home
                / ".openclaw"
                / "workspace"
                / "plugins"
                / "dicom-overlay-agent-harness"
            ),
            enable_ecg_founder_tool=ecg_founder_tool_enabled(env),
            inference_timeout_sec=args.timeout_sec,
        )
    except Exception as exc:
        write_json(
            paths["experiment_json"],
            base_record(args, provider_profile, manifest_path, experiment_dir, paths)
            | {
                "status": "blocked",
                "reason": "could not generate experiment OpenClaw config",
                "error": str(exc),
                "finished_at": now_iso(),
            },
        )
        print(f"BLOCKED: could not generate experiment OpenClaw config: {exc}")
        print(f"Experiment record: {paths['experiment_json']}")
        return 20

    write_json(paths["config_generation"], config_metadata)
    env["OPENCLAW_CONFIG_PATH"] = str(paths["openclaw_config"])

    catalog_result = run_to_file(
        [node_executable, str(OPENCLAW_CLI), "models", "list"],
        cwd=REPO_ROOT,
        env=env,
        output_path=paths["models_list"],
    )
    catalog_text = read_text_bounded(paths["models_list"])
    catalog_input = parse_model_catalog_input(catalog_text, args.model_id)
    model_catalog_warning = ""
    if catalog_input is None:
        write_json(
            paths["experiment_json"],
            base_record(args, provider_profile, manifest_path, experiment_dir, paths)
            | {
                "status": "blocked",
                "reason": (
                    "requested model id is not exposed by the effective "
                    "OpenClaw catalog"
                ),
                "suggested_models": [
                    "openai/gpt-5.4-mini",
                    "openai/gpt-5.6-luna",
                    "openai/gpt-5.6-terra",
                    "openai/gpt-5.6-sol",
                ],
                "model_catalog_exit_code": catalog_result,
                "finished_at": now_iso(),
            },
        )
        print(
            "BLOCKED: requested model is not in the effective OpenClaw catalog: "
            f"{args.model_id}"
        )
        print(f"Experiment record: {paths['experiment_json']}")
        return 20
    if catalog_result != 0:
        model_catalog_warning = (
            "OpenClaw models list exited non-zero after emitting a usable "
            "model capability row; the run will continue and retain the log."
        )
    if "image" not in catalog_input:
        write_json(
            paths["experiment_json"],
            base_record(args, provider_profile, manifest_path, experiment_dir, paths)
            | {
                "status": "blocked",
                "reason": "requested model does not advertise image input",
                "model_catalog_exit_code": catalog_result,
                "model_catalog_input": list(catalog_input),
                "finished_at": now_iso(),
            },
        )
        print(
            "BLOCKED: requested model does not advertise image input in the "
            f"effective OpenClaw catalog: {args.model_id}"
        )
        print(f"Experiment record: {paths['experiment_json']}")
        return 20

    gateway_process: GatewayProcess | None = None
    exit_code = 1
    eval_exit_code = 1
    postprocess_exit_code = 0
    artifact_verify_exit_code: int | None = None
    eval_attempts = 0
    eval_error_count = 0
    quality_gate: dict[str, object] = {
        "minimum_strict_pass_rate": args.min_strict_pass_rate,
        "minimum_mean_partial_credit": args.min_mean_partial_credit,
        "passed": False,
        "failures": ["scorecard_not_available"],
    }
    status = "failed"
    failure_reason = ""
    provider_block: dict[str, str] = {}
    gateway_ready_seconds: float | None = None

    try:
        write_json(
            paths["experiment_json"],
            base_record(args, provider_profile, manifest_path, experiment_dir, paths)
            | {
                "status": "running",
                "model_catalog_exit_code": catalog_result,
                "model_catalog_warning": model_catalog_warning,
                "model_catalog_input": list(catalog_input),
                "started_at": now_iso(),
                "updated_at": now_iso(),
            },
        )
        gateway_process = start_gateway(paths, env, node_executable=node_executable)
        gateway_ready_seconds = wait_for_gateway(
            gateway_process,
            timeout_seconds=args.gateway_wait_sec,
        )

        eval_args = [
            sys.executable,
            "scripts/run-eval.py",
            "--gateway",
            GATEWAY_URL,
            "--manifest",
            str(manifest_path),
            "--model-id",
            args.model_id,
            "--timeout-sec",
            str(args.timeout_sec),
            "--output",
            str(paths["eval_dir"]),
            "--partial-scorecard-interval",
            str(args.partial_scorecard_interval),
            "--analysis-prompt-profile",
            args.analysis_prompt_profile,
            (
                "--rhythm-strip-pass"
                if args.multi_pass
                else "--no-rhythm-strip-pass"
            ),
        ]
        if args.limit > 0:
            eval_args += ["--limit", str(args.limit)]
        if args.require_perfect:
            eval_args.append("--require-perfect")
        if args.multi_pass:
            eval_args += [
                "--multi-pass",
                "--multi-pass-max-targets",
                str(args.multi_pass_max_targets),
                "--multi-pass-max-ekg-systematic-probes",
                str(args.multi_pass_max_ekg_systematic_probes),
            ]
        if args.ecgfounder_waveform_evidence:
            eval_args.append("--ecgfounder-waveform-evidence")
        if args.resume:
            eval_args += [
                "--resume",
                "--resume-legacy-policy",
                args.resume_legacy_policy,
            ]

        eval_result = run_eval_with_gateway_retry(
            eval_args,
            cwd=REPO_ROOT,
            env=env,
            log_path=paths["eval_console"],
            max_attempts=args.gateway_retry_attempts,
            delay_seconds=args.gateway_retry_delay_sec,
        )
        eval_exit_code = eval_result["exit_code"]
        eval_attempts = eval_result["attempts"]
        exit_code = eval_exit_code

        if (paths["eval_dir"] / "results").exists():
            rebuild_exit = run_logged_command(
                [
                    sys.executable,
                    "scripts/rebuild-eval-scorecard.py",
                    "--eval-dir",
                    str(paths["eval_dir"]),
                    "--manifest",
                    str(manifest_path),
                    "--output",
                    str(paths["scorecard_rebuilt"]),
                    "--promote-canonical",
                    "--require-protocol-fingerprint",
                ],
                cwd=REPO_ROOT,
                env=env,
                log_path=paths["eval_console"],
                section="rebuild scorecard",
            )["exit_code"]
            export_exit = run_logged_command(
                [
                    sys.executable,
                    "scripts/export-eval-annotations.py",
                    "--eval-dir",
                    str(paths["eval_dir"]),
                    "--manifest",
                    str(manifest_path),
                    "--output",
                    str(paths["review_dir"]),
                ],
                cwd=REPO_ROOT,
                env=env,
                log_path=paths["eval_console"],
                section="export annotations",
            )["exit_code"]
            if rebuild_exit != 0 or export_exit != 0:
                postprocess_exit_code = 1

            if not args.skip_artifact_verify:
                verify_command = [
                    sys.executable,
                    "scripts/verify-eval-artifacts.py",
                    "--eval-dir",
                    str(paths["eval_dir"]),
                    "--manifest",
                    str(manifest_path),
                    "--min-cases",
                    str(artifact_min_cases(args)),
                    "--require-projection-audit",
                ]
                if args.multi_pass:
                    verify_command += [
                        "--require-multipass-trace",
                        "--require-multipass-refinement",
                        "--require-ekg-systematic-probes",
                    ]
                verify_command += [
                    "--min-strict-pass-rate",
                    str(args.min_strict_pass_rate),
                    "--min-mean-partial-credit",
                    str(args.min_mean_partial_credit),
                ]
                artifact_verify_exit_code = run_logged_command(
                    verify_command,
                    cwd=REPO_ROOT,
                    env=env,
                    log_path=paths["eval_console"],
                    section="verify eval artifacts",
                )["exit_code"]
                if artifact_verify_exit_code != 0:
                    postprocess_exit_code = 1

        if paths["scorecard"].exists():
            try:
                scorecard = json.loads(paths["scorecard"].read_text(encoding="utf-8"))
                eval_error_count = int(scorecard.get("error_count", 1))
                quality_gate = evaluate_quality_gate(
                    scorecard,
                    min_strict_pass_rate=args.min_strict_pass_rate,
                    min_mean_partial_credit=args.min_mean_partial_credit,
                )
                if not quality_gate["passed"]:
                    postprocess_exit_code = 1
            except Exception as exc:
                eval_error_count = 1
                postprocess_exit_code = 1
                append_log(
                    paths["eval_console"], f"\nCould not read eval error_count: {exc}\n"
                )
        elif eval_exit_code == 0:
            eval_error_count = 1
            postprocess_exit_code = 1
            append_log(
                paths["eval_console"],
                "\nMissing eval scorecard.json after successful eval exit.\n",
            )

        if eval_exit_code == 0 and eval_error_count > 0:
            exit_code = 1
        if postprocess_exit_code != 0:
            exit_code = 1
        provider_block = detect_provider_block(
            paths["gateway_stderr"],
            paths["gateway_stdout"],
            paths["eval_console"],
        )
        if provider_block:
            status = "blocked"
            failure_reason = provider_block["reason"]
            exit_code = 20
        else:
            if (
                not quality_gate["passed"]
                and eval_error_count == 0
                and artifact_verify_exit_code in {None, 0}
            ):
                status = "completed_below_target"
                failure_reason = "; ".join(
                    str(item) for item in quality_gate.get("failures", [])
                )
            else:
                status = (
                    "completed"
                    if exit_code == 0
                    and postprocess_exit_code == 0
                    and eval_error_count == 0
                    else "completed_with_failures"
                )
    except Exception as exc:
        failure_reason = f"{type(exc).__name__}: {exc}"
        append_log(paths["eval_console"], f"\nExperiment failure: {failure_reason}\n")
        status = "failed"
        exit_code = 1
    finally:
        stop_gateway(gateway_process)
        write_json(
            paths["experiment_json"],
            base_record(args, provider_profile, manifest_path, experiment_dir, paths)
            | {
                "status": status,
                "exit_code": exit_code,
                "eval_exit_code": eval_exit_code,
                "eval_error_count": eval_error_count,
                "quality_gate": quality_gate,
                "model_catalog_exit_code": catalog_result,
                "model_catalog_warning": model_catalog_warning,
                "model_catalog_input": list(catalog_input),
                "eval_attempts": eval_attempts,
                "postprocess_exit_code": postprocess_exit_code,
                "artifact_verify_exit_code": artifact_verify_exit_code,
                "gateway_ready_seconds": gateway_ready_seconds,
                "provider_block": provider_block or None,
                "failure_reason": failure_reason,
                "finished_at": now_iso(),
            },
        )
        print(f"Experiment record: {paths['experiment_json']}")

    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default=DEFAULT_VISION_MODEL_REF)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--provider-profile", default="")
    parser.add_argument(
        "--timeout-sec", type=int, default=DEFAULT_INFERENCE_TIMEOUT_SEC
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--experiment-dir", type=Path, default=None)
    parser.add_argument(
        "--analysis-prompt-profile",
        choices=("clinical", "minimal_control"),
        default="clinical",
        help=(
            "Use the app clinical prompt harness, or a single-look minimal JSON "
            "control without skills/tools."
        ),
    )
    parser.add_argument("--multi-pass", action="store_true")
    parser.add_argument("--multi-pass-max-targets", type=int, default=3)
    parser.add_argument(
        "--multi-pass-max-ekg-systematic-probes",
        type=int,
        default=2,
        help=(
            "Maximum layout-derived EKG discovery probes within the total "
            "multi-pass target budget."
        ),
    )
    parser.add_argument(
        "--ecgfounder-waveform-evidence",
        action="store_true",
        help=(
            "Run the paired MultiPass + ECGFounder arm. The sidecar endpoint, "
            "token, and per-case waveform artifacts must already be configured."
        ),
    )
    parser.add_argument("--require-perfect", action="store_true")
    parser.add_argument(
        "--min-strict-pass-rate",
        type=float,
        default=DEFAULT_MIN_STRICT_PASS_RATE,
        help="Minimum strict pass rate required for completed status (default: 0.75).",
    )
    parser.add_argument(
        "--min-mean-partial-credit",
        type=float,
        default=DEFAULT_MIN_MEAN_PARTIAL_CREDIT,
        help=(
            "Minimum mean partial-credit score required for completed status "
            "(default: 0.85)."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume only if protocol and existing result identities validate.",
    )
    parser.add_argument(
        "--resume-legacy-policy",
        choices=("reject", "mark"),
        default="reject",
        help=(
            "Reject legacy unfingerprinted results, or continue while permanently "
            "marking the experiment mixed/non-comparable."
        ),
    )
    parser.add_argument("--partial-scorecard-interval", type=int, default=50)
    parser.add_argument(
        "--artifact-min-cases",
        type=int,
        default=0,
        help=(
            "Minimum cases for post-run artifact verification. Defaults to "
            "--limit for bounded smoke runs, otherwise 1000."
        ),
    )
    parser.add_argument(
        "--skip-artifact-verify",
        action="store_true",
        help="Skip post-run verify-eval-artifacts.py artifact completeness gate.",
    )
    parser.add_argument(
        "--gateway-wait-sec",
        type=int,
        default=120,
        help="Maximum seconds to wait for the Gateway port to become ready.",
    )
    parser.add_argument("--gateway-retry-attempts", type=int, default=6)
    parser.add_argument("--gateway-retry-delay-sec", type=int, default=5)
    args = parser.parse_args()
    if args.ecgfounder_waveform_evidence and not args.multi_pass:
        parser.error("--ecgfounder-waveform-evidence requires --multi-pass")
    if args.analysis_prompt_profile == "minimal_control" and args.multi_pass:
        parser.error("minimal_control cannot be combined with --multi-pass")
    for name in ("min_strict_pass_rate", "min_mean_partial_credit"):
        value = float(getattr(args, name))
        if not 0.0 <= value <= 1.0:
            parser.error(f"--{name.replace('_', '-')} must be in [0, 1]")
    return args


def artifact_min_cases(args: argparse.Namespace) -> int:
    if args.artifact_min_cases > 0:
        return int(args.artifact_min_cases)
    if args.limit > 0:
        return int(args.limit)
    return 1000


def experiment_arm(args: argparse.Namespace) -> str:
    if args.analysis_prompt_profile == "minimal_control":
        return "minimal_control"
    if args.ecgfounder_waveform_evidence:
        return "multipass_ecgfounder"
    if args.multi_pass:
        return "multipass"
    return "single_pass"


def evaluate_quality_gate(
    scorecard: dict[str, Any],
    *,
    min_strict_pass_rate: float,
    min_mean_partial_credit: float,
) -> dict[str, object]:
    failures: list[str] = []
    rates: dict[str, float | None] = {}
    for field, minimum in (
        ("strict_pass_rate", min_strict_pass_rate),
        ("mean_partial_credit", min_mean_partial_credit),
    ):
        try:
            actual = float(scorecard.get(field))
        except (TypeError, ValueError):
            actual = None
        rates[field] = actual
        if actual is None:
            failures.append(f"{field} is missing or invalid")
        elif actual + 1e-12 < minimum:
            failures.append(f"{field}={actual:.6f} below minimum={minimum:.6f}")
    return {
        "minimum_strict_pass_rate": min_strict_pass_rate,
        "minimum_mean_partial_credit": min_mean_partial_credit,
        **rates,
        "passed": not failures,
        "failures": failures,
    }


def build_child_env(
    repo_root: Path,
    *,
    state_home: Path | None = None,
) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("UV_CACHE_DIR", str(repo_root / ".uv-cache-codex"))
    env.setdefault("UV_NO_PROGRESS", "1")
    env.setdefault("UV_PYTHON_DOWNLOADS", "never")
    uv_tmp = repo_root / Path(UV_TMP_RELATIVE)
    uv_tmp.mkdir(parents=True, exist_ok=True)
    env["TMP"] = str(uv_tmp)
    env["TEMP"] = str(uv_tmp)
    openclaw_home = (state_home or repo_root / "openclaw-home").resolve()
    env["OPENCLAW_HOME"] = str(openclaw_home)
    env["OPENCLAW_STATE_DIR"] = str(openclaw_home)
    env["HOME"] = str(openclaw_home)
    env["USERPROFILE"] = str(openclaw_home)
    return env


def load_dotenv(path: Path, env: dict[str, str]) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name:
            env[name] = value


def resolve_experiment_dir(path: Path | None, model_id: str) -> Path:
    if path is not None:
        return path.resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_model = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in model_id)
    return REPO_ROOT / "data" / "experiments" / f"meeti-{stamp}-{safe_model}"


def effective_provider_profile(
    model_id: str, explicit: str, env: dict[str, str]
) -> str:
    if explicit:
        return explicit
    from_env = env.get("DICOM_OVERLAY_PROVIDER_PROFILE", "")
    if from_env:
        return from_env
    for profile in default_provider_profiles():
        if (
            profile.model_ref.lower() == model_id.lower()
            and "image" in profile.input_modalities
        ):
            return profile.key
    if model_id.lower().startswith("openrouter/"):
        return "openrouter"
    return ""


def parse_model_catalog_input(
    catalog_text: str,
    model_id: str,
) -> tuple[str, ...] | None:
    """Read the advertised input modalities from an OpenClaw catalog row."""
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    expected = model_id.strip().lower()
    for raw_line in catalog_text.splitlines():
        parts = ansi_escape.sub("", raw_line).split()
        if len(parts) < 2 or parts[0].lower() != expected:
            continue
        modalities = tuple(
            item.strip().lower()
            for item in parts[1].split("+")
            if item.strip()
        )
        return modalities
    return None


def write_experiment_openclaw_config(
    *,
    base_config: Path,
    target_config: Path,
    model_id: str,
    profile_key: str,
    harness_plugin_path: Path | None = None,
    enable_ecg_founder_tool: bool = False,
    inference_timeout_sec: int = DEFAULT_INFERENCE_TIMEOUT_SEC,
) -> dict[str, Any]:
    existing = read_json_dict(base_config)
    metadata: dict[str, Any] = {
        "provider_profile": profile_key,
        "requested_model": model_id,
    }
    provider_timeout_sec, agent_timeout_sec = derive_openclaw_timeout_budget(
        inference_timeout_sec
    )
    metadata.update(
        {
            "client_inference_timeout_sec": inference_timeout_sec,
            "provider_timeout_sec": provider_timeout_sec,
            "agent_timeout_sec": agent_timeout_sec,
        }
    )
    if profile_key:
        profile = find_provider_profile(profile_key)
        model = model_id
        provider_prefix = f"{profile.provider_id}/"
        if model.lower().startswith(provider_prefix.lower()):
            model = model[len(provider_prefix) :]
        profile = replace(profile, model=model)
        managed = build_openclaw_config(
            profile, inference_timeout_sec=inference_timeout_sec
        )
        merged = merge_openclaw_config(existing, managed)
        metadata.update(
            {
                "provider_profile": profile.key,
                "provider_id": profile.provider_id,
                "model_ref": profile.model_ref,
                "api_key_env": profile.api_key_env,
            }
        )
    else:
        merged = existing
        defaults = merged.setdefault("agents", {}).setdefault("defaults", {})
        model_defaults = defaults.get("model")
        if not isinstance(model_defaults, dict):
            model_defaults = {}
            defaults["model"] = model_defaults
        model_defaults["primary"] = model_id
        model_defaults.setdefault("fallbacks", [])
        models = defaults.setdefault("models", {})
        models.setdefault(model_id, {"alias": model_id})
        defaults["timeoutSeconds"] = agent_timeout_sec
        provider_id = model_id.partition("/")[0]
        model_config = merged.setdefault("models", {})
        if not isinstance(model_config, dict):
            model_config = {}
            merged["models"] = model_config
        providers = model_config.setdefault("providers", {})
        provider = providers.get(provider_id)
        if isinstance(provider, dict):
            provider["timeoutSeconds"] = provider_timeout_sec
        metadata.update(
            {
                "provider_profile": "",
                "provider_id": "",
                "model_ref": model_id,
                "api_key_env": "",
            }
        )
    if harness_plugin_path is not None:
        plugin_path = str(harness_plugin_path.resolve())
        plugins = merged.setdefault("plugins", {})
        plugins["allow"] = ["dicom-overlay-agent-harness"]
        load = plugins.setdefault("load", {})
        load["paths"] = [plugin_path]
        entries = plugins.setdefault("entries", {})
        entries["dicom-overlay-agent-harness"] = {"enabled": True}
        allowed_tools = ["dicom_bbox_validate"]
        if enable_ecg_founder_tool:
            allowed_tools.append("ecg_founder_analyze_waveform")
        merged["tools"] = build_analysis_tool_policy(allowed_tools)
        metadata["harness_plugin_path"] = plugin_path
        metadata["ecg_founder_tool_enabled"] = bool(enable_ecg_founder_tool)
    write_json(target_config, merged)
    return metadata


def find_provider_profile(profile_key: str) -> ProviderProfile:
    profiles = default_provider_profiles()
    for profile in profiles:
        if profile.key == profile_key or profile.provider_id == profile_key:
            return profile
    known = sorted(
        {item.key for item in profiles} | {item.provider_id for item in profiles}
    )
    raise ValueError(
        f"Unknown provider profile '{profile_key}'. Known profiles: {', '.join(known)}"
    )


def start_gateway(
    paths: dict[str, Path],
    env: dict[str, str],
    *,
    node_executable: str,
) -> GatewayProcess:
    lock_dir = acquire_gateway_lock()
    paths["gateway_stdout"].parent.mkdir(parents=True, exist_ok=True)
    stdout = paths["gateway_stdout"].open("w", encoding="utf-8")
    stderr = paths["gateway_stderr"].open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            [node_executable, str(OPENCLAW_CLI), "gateway", "run", "--verbose"],
            cwd=REPO_ROOT,
            env=env,
            stdout=stdout,
            stderr=stderr,
            text=True,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            ),
        )
        (lock_dir / "pid").write_text(str(process.pid), encoding="utf-8")
        return GatewayProcess(process=process, lock_dir=lock_dir)
    except Exception:
        stdout.close()
        stderr.close()
        release_gateway_lock(lock_dir)
        raise


def stop_gateway(gateway: GatewayProcess | None) -> None:
    if gateway is None:
        return
    try:
        process = gateway.process
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    finally:
        release_gateway_lock(gateway.lock_dir)


def wait_for_gateway(
    gateway: GatewayProcess,
    *,
    timeout_seconds: int,
    host: str = "127.0.0.1",
    port: int = 18789,
) -> float:
    """Wait until the launched process is alive and accepting TCP connections."""
    started = time.monotonic()
    deadline = started + max(1, timeout_seconds)
    while time.monotonic() < deadline:
        return_code = gateway.process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"OpenClaw Gateway exited before readiness (exit {return_code})"
            )
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return round(time.monotonic() - started, 3)
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(
        f"OpenClaw Gateway did not listen on {host}:{port} within "
        f"{timeout_seconds} seconds"
    )


def acquire_gateway_lock() -> Path:
    OPENCLAW_GATEWAY_LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        OPENCLAW_GATEWAY_LOCK.mkdir()
    except FileExistsError:
        pid = read_lock_pid(OPENCLAW_GATEWAY_LOCK)
        if pid is not None and pid_is_running(pid):
            raise RuntimeError(
                "OpenClaw Gateway launch lock is already held by pid "
                f"{pid}: {OPENCLAW_GATEWAY_LOCK}"
            ) from None
        release_gateway_lock(OPENCLAW_GATEWAY_LOCK)
        OPENCLAW_GATEWAY_LOCK.mkdir()
    return OPENCLAW_GATEWAY_LOCK


def release_gateway_lock(lock_dir: Path) -> None:
    try:
        (lock_dir / "pid").unlink(missing_ok=True)
        lock_dir.rmdir()
    except OSError:
        pass


def read_lock_pid(lock_dir: Path) -> int | None:
    try:
        return int((lock_dir / "pid").read_text(encoding="utf-8").strip())
    except (FileNotFoundError, OSError, ValueError):
        return None


def run_eval_with_gateway_retry(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    max_attempts: int,
    delay_seconds: int,
) -> dict[str, int]:
    attempts = 0
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        attempt_command = list(command)
        if attempt > 1 and "--resume" not in attempt_command:
            attempt_command.append("--resume")
        result = run_logged_command(
            attempt_command,
            cwd=cwd,
            env=env,
            log_path=log_path,
            section=f"eval attempt {attempt}",
        )
        if result["exit_code"] == 0:
            return {"exit_code": 0, "attempts": attempts}
        gateway_not_ready = any(
            marker in result["captured"].lower()
            for marker in (
                "gateway starting; retry shortly",
                "could not reach gateway",
                "connection refused",
                "refused the network connection",
            )
        )
        if not gateway_not_ready or attempt >= max_attempts:
            return {"exit_code": result["exit_code"], "attempts": attempts}
        append_log(
            log_path, f"Gateway not ready; retrying after {delay_seconds} seconds.\n"
        )
        time.sleep(delay_seconds)
    return {"exit_code": 1, "attempts": attempts}


def run_logged_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    section: str,
) -> dict[str, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    captured = ""
    with log_path.open("a", encoding="utf-8", errors="replace") as log:
        log.write(f"\n=== {section} ===\n")
        log.write(render_command(command) + "\n")
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            captured = append_bounded(captured, line)
        exit_code = process.wait()
        log.write(f"\nexit_code={exit_code}\n")
    return {"exit_code": exit_code, "captured": captured}


def run_to_file(
    command: list[str], *, cwd: Path, env: dict[str, str], output_path: Path
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", errors="replace") as output:
        output.write(render_command(command) + "\n")
        process = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        output.write(f"\nexit_code={process.returncode}\n")
    return int(process.returncode)


def append_bounded(current: str, new_text: str) -> str:
    if len(current) + len(new_text) <= MAX_CAPTURED_COMMAND_OUTPUT_CHARS:
        return current + new_text
    combined = current + new_text
    return combined[-MAX_CAPTURED_COMMAND_OUTPUT_CHARS:]


def append_log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(text)


def base_record(
    args: argparse.Namespace,
    provider_profile: str,
    manifest_path: Path,
    experiment_dir: Path,
    paths: dict[str, Path],
) -> dict[str, Any]:
    protocol_summary = read_protocol_summary(paths["protocol_fingerprint"])
    return {
        "requested_model": args.model_id,
        "provider_profile": provider_profile,
        "timeout_sec": args.timeout_sec,
        "limit": args.limit,
        "experiment_arm": experiment_arm(args),
        "analysis_prompt_profile": args.analysis_prompt_profile,
        "rhythm_strip_pass": bool(args.multi_pass),
        "multi_pass": bool(args.multi_pass),
        "multi_pass_max_targets": args.multi_pass_max_targets,
        "multi_pass_max_ekg_systematic_probes": (
            args.multi_pass_max_ekg_systematic_probes
        ),
        "ecgfounder_waveform_evidence": bool(
            args.ecgfounder_waveform_evidence
        ),
        "require_perfect": bool(args.require_perfect),
        "minimum_strict_pass_rate": args.min_strict_pass_rate,
        "minimum_mean_partial_credit": args.min_mean_partial_credit,
        "resume": bool(args.resume),
        "resume_legacy_policy": args.resume_legacy_policy,
        "partial_scorecard_interval": args.partial_scorecard_interval,
        "artifact_verify_min_cases": artifact_min_cases(args),
        "skip_artifact_verify": bool(args.skip_artifact_verify),
        "manifest": str(manifest_path),
        "experiment_dir": str(experiment_dir),
        "openclaw_config": str(paths["openclaw_config"]),
        "openclaw_state": str(paths["openclaw_state"]),
        "bbox_tool_audit": str(paths["bbox_tool_audit"]),
        "ecg_founder_tool_audit": str(paths["ecg_founder_tool_audit"]),
        "config_generation_log": str(paths["config_generation"]),
        "model_catalog_log": str(paths["models_list"]),
        "gateway_stdout": str(paths["gateway_stdout"]),
        "gateway_stderr": str(paths["gateway_stderr"]),
        "eval_console": str(paths["eval_console"]),
        "eval_artifacts": str(paths["eval_dir"]),
        "scorecard_rebuilt": str(paths["scorecard_rebuilt"]),
        "protocol_fingerprint": str(paths["protocol_fingerprint"]),
        "protocol_digest": protocol_summary.get("protocol_digest", ""),
        "protocol_comparability": protocol_summary.get("comparability"),
        "review_artifacts": str(paths["review_dir"]),
    }


def read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    payload = json.loads(text)
    return payload if isinstance(payload, dict) else {}


def read_protocol_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "protocol_digest": payload.get("protocol_digest", ""),
        "comparability": payload.get("comparability"),
    }


def read_text_bounded(path: Path) -> str:
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(MAX_CAPTURED_COMMAND_OUTPUT_CHARS)


def detect_provider_block(*log_paths: Path) -> dict[str, str]:
    """Identify non-retryable provider billing/auth failures without secrets."""
    combined = "\n".join(read_text_bounded(path) for path in log_paths).lower()
    for marker, (code, reason) in _PROVIDER_BLOCK_MARKERS.items():
        if marker in combined:
            return {"code": code, "reason": reason}
    return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def render_command(command: list[str]) -> str:
    return " ".join(command)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
