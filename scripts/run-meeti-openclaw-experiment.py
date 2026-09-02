"""Run a bounded MEETI OpenClaw experiment without shell wrappers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dicom_overlay.application.multi_pass import (
    DEFAULT_FIRST_REFINEMENT_SLA_SEC,
    DEFAULT_INITIAL_RESPONSE_SLA_SEC,
    DEFAULT_TOTAL_ANALYSIS_SLA_SEC,
)
from dicom_overlay.infrastructure.codex_subscription_auth import (
    ensure_openclaw_subscription_auth,
)
from dicom_overlay.infrastructure.gateway_manager import (
    GatewayManager,
    ecg_founder_tool_enabled,
    pid_is_running,
)
from dicom_overlay.infrastructure.openclaw_settings import (
    DEFAULT_INFERENCE_TIMEOUT_SEC,
    DEFAULT_VISION_MODEL_REF,
    ProviderAuthMode,
    ProviderProfile,
    build_analysis_tool_policy,
    build_openclaw_config,
    default_provider_profiles,
    derive_openclaw_timeout_budget,
    merge_openclaw_config,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    REPO_ROOT / "data" / "eval-datasets" / "meeti-full-all" / "manifest.json"
)
OPENCLAW_CLI = REPO_ROOT / "openclaw" / "node_modules" / "openclaw" / "openclaw.mjs"
BASE_OPENCLAW_CONFIG = REPO_ROOT / "openclaw" / "openclaw.json"
GATEWAY_URL = "ws://127.0.0.1:18789"
OPENCLAW_GATEWAY_LOCK = REPO_ROOT / "data" / "tmp" / "openclaw-gateway.lock"
UV_TMP_RELATIVE = "data/tmp/uv"
MAX_CAPTURED_COMMAND_OUTPUT_CHARS = 200_000
DEFAULT_CODEX_PROVIDER_PROFILE = "openai-codex"
DEFAULT_MIN_STRICT_PASS_RATE = 0.75
DEFAULT_MIN_MEAN_PARTIAL_CREDIT = 0.85
DEFAULT_MIN_INITIAL_RESPONSE_SLA_RATE = 0.90
DEFAULT_MIN_FIRST_CROP_SLA_RATE = 0.90
DEFAULT_MIN_TOTAL_SLA_RATE = 0.95
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
_OPENCLAW_RUNTIME_MARKERS = {
    "embedded_agent": "[agent/embedded] embedded run start",
    "subscription_transport": "api=openai-chatgpt-responses",
    "codex_backend": "baseurl=https://chatgpt.com/backend-api/codex",
}
_CODEX_AGENT_HANDOFF_MARKERS = {
    "codex_provider_route": "provider=codex",
    "codex_app_server_api": "api=codex-app-server",
    "codex_app_server_startup": "codex app-server pre-dynamic startup",
    "codex_app_server_turn": "codex app-server context-engine projection decision",
    "codex_exec_server": "codex sandbox exec-server started",
}
_OPENAI_PROVIDER_PLUGIN = "openai"
_OPENAI_PROVIDER_READY_MARKER = "[plugins] loading openai from"
_BLINDED_CASE_FIELDS = frozenset(
    {
        "image",
        "modality",
        "label",
        "regions",
        "source",
        "valid_regions",
        "waveform_artifact_id",
        "waveform_lead_mode",
    }
)


@dataclass(frozen=True)
class GatewayProcess:
    process: subprocess.Popen[str]
    lock_dir: Path


@dataclass(frozen=True)
class EcgFounderProcess:
    process: subprocess.Popen[str]


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.resolve() if args.manifest else DEFAULT_MANIFEST
    scoring_manifest_path = (
        args.scoring_manifest.resolve() if args.scoring_manifest else manifest_path
    )
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
    sidecar_stdout_name = (
        f"ecgfounder-sidecar.resume-{resume_stamp}.stdout.log"
        if args.resume
        else "ecgfounder-sidecar.stdout.log"
    )
    sidecar_stderr_name = (
        f"ecgfounder-sidecar.resume-{resume_stamp}.stderr.log"
        if args.resume
        else "ecgfounder-sidecar.stderr.log"
    )

    paths = {
        "experiment_json": experiment_dir / "experiment.json",
        "models_list": experiment_dir / "openclaw-models-list.txt",
        "config_generation": experiment_dir / "openclaw-config-generation.json",
        "codex_auth_import": experiment_dir / "codex-auth-import.json",
        "gateway_stdout": experiment_dir / gateway_stdout_name,
        "gateway_stderr": experiment_dir / gateway_stderr_name,
        "transport_receipt": experiment_dir / "transport-receipt.json",
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
        "ecgfounder_sidecar_stdout": experiment_dir / sidecar_stdout_name,
        "ecgfounder_sidecar_stderr": experiment_dir / sidecar_stderr_name,
    }
    env["DICOM_BBOX_AUDIT_PATH"] = str(paths["bbox_tool_audit"])
    env["DICOM_ECGFOUNDER_AUDIT_PATH"] = str(paths["ecg_founder_tool_audit"])

    try:
        manifest_pair = validate_manifest_pair(
            inference_manifest=manifest_path,
            scoring_manifest=scoring_manifest_path,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        write_json(
            paths["experiment_json"],
            base_record(args, "", manifest_path, experiment_dir, paths)
            | {
                "status": "blocked",
                "reason": "inference/scoring manifest pair is invalid",
                "error": str(exc),
                "finished_at": now_iso(),
            },
        )
        print(f"BLOCKED: inference/scoring manifest pair is invalid: {exc}")
        print(f"Experiment record: {paths['experiment_json']}")
        return 20

    try:
        managed_sidecar = prepare_managed_ecgfounder(
            args,
            env=env,
            manifest_path=manifest_path,
        )
    except (OSError, ValueError) as exc:
        write_json(
            paths["experiment_json"],
            base_record(args, "", manifest_path, experiment_dir, paths)
            | {
                "status": "blocked",
                "reason": "managed ECGFounder sidecar is not ready",
                "error": str(exc),
                "finished_at": now_iso(),
            },
        )
        print(f"BLOCKED: managed ECGFounder sidecar is not ready: {exc}")
        print(f"Experiment record: {paths['experiment_json']}")
        return 20

    provider_profile = effective_provider_profile(
        args.model_id, args.provider_profile, env
    )
    try:
        assert_subscription_experiment_profile(provider_profile)
    except (RuntimeError, ValueError) as exc:
        write_json(
            paths["experiment_json"],
            base_record(args, provider_profile, manifest_path, experiment_dir, paths)
            | {
                "status": "blocked",
                "reason": "MEETI runner requires OpenClaw with Codex subscription",
                "error": str(exc),
                "finished_at": now_iso(),
            },
        )
        print(f"BLOCKED: {exc}")
        print(f"Experiment record: {paths['experiment_json']}")
        return 20
    env["DICOM_OVERLAY_PROVIDER_PROFILE"] = provider_profile

    codex_auth_metadata: dict[str, Any] = {}
    try:
        selected_profile = (
            find_provider_profile(provider_profile) if provider_profile else None
        )
        if (
            selected_profile is not None
            and selected_profile.auth_mode is ProviderAuthMode.CODEX_SUBSCRIPTION
        ):
            codex_auth_metadata = prepare_codex_subscription_env(
                env,
                resolve_native_codex_home(args.codex_home),
            )
            codex_command, codex_version = resolve_native_codex_command(
                args.codex_command
            )
            codex_auth_metadata.update(
                {
                    "codex_command": str(codex_command),
                    "codex_cli_version": codex_version,
                }
            )
    except Exception as exc:
        write_json(
            paths["experiment_json"],
            base_record(args, provider_profile, manifest_path, experiment_dir, paths)
            | {
                "status": "blocked",
                "reason": "Codex subscription authentication is not ready",
                "error": str(exc),
                "finished_at": now_iso(),
            },
        )
        print(f"BLOCKED: Codex subscription authentication is not ready: {exc}")
        print(f"Experiment record: {paths['experiment_json']}")
        return 20

    # Keep the experiment on the same app-owned skill/plugin bytes as the
    # desktop Gateway.  openclaw-home is mutable state and may otherwise hold a
    # stale mirror from an earlier run.
    gateway_manager = GatewayManager(repo_root=REPO_ROOT)
    gateway_manager.prepare_workspace(state_home=state_home)
    node_executable = gateway_manager.node_executable()

    try:
        config_base_path = resolve_experiment_config_base(
            resume=args.resume,
            target_config=paths["openclaw_config"],
        )
        config_metadata = write_experiment_openclaw_config(
            base_config=config_base_path,
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
            enable_harness=args.analysis_prompt_profile == "clinical",
            enable_ecg_founder_tool=ecg_founder_tool_enabled(env),
            inference_timeout_sec=args.timeout_sec,
            thinking_level=args.thinking_level,
        )
        config_metadata["base_config_source"] = (
            "existing_experiment" if config_base_path == paths["openclaw_config"] else "repo"
        )
        config_metadata.update(managed_ecgfounder_metadata(managed_sidecar))
        config_metadata.update(codex_auth_metadata)
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

    if codex_auth_metadata:
        try:
            auth_audit = bootstrap_openclaw_subscription_auth(
                node_executable=node_executable,
                env=env,
                config_path=paths["openclaw_config"],
                state_home=state_home,
                source_codex_home=Path(
                    str(codex_auth_metadata["codex_source_home"])
                ),
                audit_path=paths["codex_auth_import"],
                model_id=args.model_id,
            )
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            write_json(
                paths["experiment_json"],
                base_record(
                    args, provider_profile, manifest_path, experiment_dir, paths
                )
                | {
                    "status": "blocked",
                    "reason": "isolated ChatGPT subscription auth import failed",
                    "error": str(exc),
                    "finished_at": now_iso(),
                },
            )
            print(f"BLOCKED: isolated ChatGPT subscription auth import failed: {exc}")
            print(f"Experiment record: {paths['experiment_json']}")
            return 20
        config_metadata = write_experiment_openclaw_config(
            base_config=paths["openclaw_config"],
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
            enable_harness=args.analysis_prompt_profile == "clinical",
            enable_ecg_founder_tool=ecg_founder_tool_enabled(env),
            inference_timeout_sec=args.timeout_sec,
            thinking_level=args.thinking_level,
        )
        config_metadata.update(managed_ecgfounder_metadata(managed_sidecar))
        config_metadata.update(codex_auth_metadata)
        config_metadata["subscription_auth_audit"] = auth_audit
        config_metadata["oauth_import_plugin_scope"] = (
            "authentication_only_config_removed_before_gateway"
        )
        config_metadata["codex_extension_configured"] = False
        config_metadata["codex_agent_runtime_configured"] = False
        config_metadata["codex_extension_may_be_auto_discovered"] = True
        assert_openclaw_subscription_ownership(
            paths["openclaw_config"], model_id=args.model_id
        )
        write_json(paths["config_generation"], config_metadata)

    catalog_command = [node_executable, str(OPENCLAW_CLI), "models", "list"]
    if codex_auth_metadata:
        catalog_command += ["--all", "--provider", "openai"]
    catalog_result = run_to_file(
        catalog_command,
        cwd=REPO_ROOT,
        env=env,
        output_path=paths["models_list"],
    )
    if codex_auth_metadata:
        try:
            assert_openclaw_subscription_ownership(
                paths["openclaw_config"], model_id=args.model_id
            )
        except RuntimeError as exc:
            write_json(
                paths["experiment_json"],
                base_record(
                    args, provider_profile, manifest_path, experiment_dir, paths
                )
                | {
                    "status": "blocked",
                    "reason": "OpenClaw ownership guard failed after model discovery",
                    "error": str(exc),
                    "model_catalog_exit_code": catalog_result,
                    "finished_at": now_iso(),
                },
            )
            print(f"BLOCKED: OpenClaw ownership guard failed: {exc}")
            print(f"Experiment record: {paths['experiment_json']}")
            return 20
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
    ecgfounder_process: EcgFounderProcess | None = None
    exit_code = 1
    eval_exit_code = 1
    postprocess_exit_code = 0
    artifact_verify_exit_code: int | None = None
    eval_attempts = 0
    eval_error_count = 0
    quality_gate: dict[str, object] = {
        "minimum_strict_pass_rate": args.min_strict_pass_rate,
        "minimum_mean_partial_credit": args.min_mean_partial_credit,
        "minimum_initial_response_sla_rate": args.min_initial_response_sla_rate,
        "minimum_first_crop_sla_rate": args.min_first_crop_sla_rate,
        "minimum_total_sla_rate": args.min_total_sla_rate,
        "passed": False,
        "failures": ["scorecard_not_available"],
    }
    status = "failed"
    failure_reason = ""
    provider_block: dict[str, str] = {}
    runtime_ownership: dict[str, object] = {
        "verified": False,
        "required_markers": list(_OPENCLAW_RUNTIME_MARKERS),
        "forbidden_handoff_markers": list(_CODEX_AGENT_HANDOFF_MARKERS),
        "observed_markers": [],
        "observed_handoff_markers": [],
    }
    gateway_ready_seconds: float | None = None
    provider_plugin_ready_seconds: float | None = None
    ecgfounder_ready_seconds: float | None = None

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
        if managed_sidecar:
            ecgfounder_process, ecgfounder_ready_seconds = start_ecgfounder_sidecar(
                managed_sidecar,
                env=env,
                stdout_path=paths["ecgfounder_sidecar_stdout"],
                stderr_path=paths["ecgfounder_sidecar_stderr"],
                timeout_seconds=args.ecgfounder_ready_wait_sec,
            )
        gateway_process = start_gateway(
            paths,
            env,
            node_executable=node_executable,
            workspace_dir=Path(str(config_metadata["agent_workspace_path"])),
        )
        gateway_ready_seconds = wait_for_gateway(
            gateway_process,
            timeout_seconds=args.gateway_wait_sec,
        )
        if codex_auth_metadata:
            provider_plugin_ready_seconds = wait_for_gateway_log_marker(
                gateway_process,
                log_path=paths["gateway_stdout"],
                marker=_OPENAI_PROVIDER_READY_MARKER,
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
            "--openclaw-thinking-level",
            args.thinking_level,
            ("--fast-mode" if args.fast_mode else "--no-fast-mode"),
            "--initial-response-sla-sec",
            str(args.initial_response_sla_sec),
            "--first-refinement-sla-sec",
            str(args.first_refinement_sla_sec),
            "--total-analysis-sla-sec",
            str(args.total_analysis_sla_sec),
            ("--rhythm-strip-pass" if args.multi_pass else "--no-rhythm-strip-pass"),
        ]
        if manifest_pair["blinded_inference"]:
            eval_args.append("--defer-scoring")
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
            if args.resume_retry_errors:
                eval_args.append("--resume-retry-errors")

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

        if codex_auth_metadata:
            runtime_ownership = verify_openclaw_runtime_ownership(
                paths["gateway_stdout"],
                expected_model=args.model_id,
            )
            if not runtime_ownership["verified"]:
                postprocess_exit_code = 1
                ownership_issues = [
                    *runtime_ownership.get("missing_markers", []),
                    *runtime_ownership.get("observed_handoff_markers", []),
                ]
                append_log(
                    paths["eval_console"],
                    "\nOpenClaw runtime ownership proof failed: "
                    + ", ".join(ownership_issues)
                    + "\n",
                )

        if (paths["eval_dir"] / "results").exists():
            rebuild_exit = run_logged_command(
                [
                    sys.executable,
                    "scripts/rebuild-eval-scorecard.py",
                    "--eval-dir",
                    str(paths["eval_dir"]),
                    "--manifest",
                    str(scoring_manifest_path),
                    "--output",
                    str(paths["scorecard_rebuilt"]),
                    "--promote-canonical",
                    "--require-protocol-fingerprint",
                    *(
                        ["--allow-paired-gold-manifest"]
                        if manifest_pair["blinded_inference"]
                        else []
                    ),
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
                    str(scoring_manifest_path),
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
                    str(scoring_manifest_path),
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
                if not args.require_perfect:
                    verify_command.append("--allow-safety-misses")
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
                    min_initial_response_sla_rate=(
                        args.min_initial_response_sla_rate if args.multi_pass else 0.0
                    ),
                    min_first_crop_sla_rate=(
                        args.min_first_crop_sla_rate if args.multi_pass else 0.0
                    ),
                    min_total_sla_rate=(
                        args.min_total_sla_rate if args.multi_pass else 0.0
                    ),
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
        stop_ecgfounder_sidecar(ecgfounder_process)
        try:
            transport_receipt = build_transport_receipt(
                gateway_log=paths["gateway_stdout"],
                state_home=paths["openclaw_state"],
                fast_mode_requested=bool(args.fast_mode),
            )
        except Exception as exc:  # Keep the primary experiment result recoverable.
            transport_receipt = {
                "schema_version": 1,
                "generated_at": now_iso(),
                "fast_mode_requested": bool(args.fast_mode),
                "priority_service_observed": None,
                "service_tier_claim": "receipt_generation_failed",
                "error_type": type(exc).__name__,
            }
            append_log(
                paths["eval_console"],
                f"\nTransport receipt generation failed: {type(exc).__name__}\n",
            )
        write_json(paths["transport_receipt"], transport_receipt)
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
                "provider_plugin_ready_seconds": provider_plugin_ready_seconds,
                "ecgfounder_ready_seconds": ecgfounder_ready_seconds,
                "provider_block": provider_block or None,
                "runtime_ownership": runtime_ownership,
                "transport_receipt_summary": transport_receipt,
                "manifest_pair": manifest_pair,
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
    parser.add_argument(
        "--scoring-manifest",
        type=Path,
        default=None,
        help=(
            "Gold manifest used only after inference to rebuild scores. When it "
            "differs from --manifest, the inference manifest must omit labels."
        ),
    )
    parser.add_argument("--provider-profile", default=DEFAULT_CODEX_PROVIDER_PROFILE)
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=None,
        help=(
            "Native Codex home containing a ChatGPT login. Defaults to "
            "$CODEX_HOME or the original user profile's .codex directory."
        ),
    )
    parser.add_argument(
        "--codex-command",
        type=Path,
        default=None,
        help=(
            "Codex CLI associated with the source ChatGPT login. It is probed "
            "for auth provenance only and is never used as the agent runtime."
        ),
    )
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
    parser.add_argument(
        "--thinking-level",
        choices=("off", "minimal", "low", "medium", "high"),
        default="off",
        help=(
            "OpenClaw embedded-agent thinking default. It is written into the "
            "isolated config and experiment protocol (default: off for SLA)."
        ),
    )
    parser.add_argument(
        "--fast-mode",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Request OpenClaw fast mode for every model turn. Enabled by "
            "default for the 60/100/180-second SLA and may consume priority "
            "subscription capacity."
        ),
    )
    parser.add_argument(
        "--multi-pass",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Use the app crop/refine loop. Defaults to enabled for the clinical "
            "profile and disabled for minimal_control."
        ),
    )
    parser.add_argument("--multi-pass-max-targets", type=int, default=2)
    parser.add_argument(
        "--multi-pass-max-ekg-systematic-probes",
        type=int,
        default=1,
        help=(
            "Maximum layout-derived EKG discovery probes within the total "
            "multi-pass target budget."
        ),
    )
    parser.add_argument(
        "--ecgfounder-waveform-evidence",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Run the paired MultiPass + ECGFounder arm. The sidecar endpoint, "
            "token, and per-case waveform artifacts must already be configured."
        ),
    )
    parser.add_argument(
        "--manage-ecgfounder-sidecar",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Start, health-check, log, and stop the pinned local ECGFounder "
            "sidecar for waveform-evidence runs (default: enabled)."
        ),
    )
    parser.add_argument(
        "--ecgfounder-runtime-dir",
        type=Path,
        default=REPO_ROOT / "data" / "external" / "ecgfounder-runtime",
    )
    parser.add_argument("--ecgfounder-registry", type=Path, default=None)
    parser.add_argument("--ecgfounder-port", type=int, default=18790)
    parser.add_argument("--ecgfounder-ready-wait-sec", type=int, default=180)
    parser.add_argument(
        "--initial-response-sla-sec",
        type=float,
        default=DEFAULT_INITIAL_RESPONSE_SLA_SEC,
    )
    parser.add_argument(
        "--first-refinement-sla-sec",
        type=float,
        default=DEFAULT_FIRST_REFINEMENT_SLA_SEC,
    )
    parser.add_argument(
        "--total-analysis-sla-sec",
        type=float,
        default=DEFAULT_TOTAL_ANALYSIS_SLA_SEC,
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
        "--min-initial-response-sla-rate",
        type=float,
        default=DEFAULT_MIN_INITIAL_RESPONSE_SLA_RATE,
    )
    parser.add_argument(
        "--min-first-crop-sla-rate",
        type=float,
        default=DEFAULT_MIN_FIRST_CROP_SLA_RATE,
    )
    parser.add_argument(
        "--min-total-sla-rate",
        type=float,
        default=DEFAULT_MIN_TOTAL_SLA_RATE,
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume only if protocol and existing result identities validate.",
    )
    parser.add_argument(
        "--resume-retry-errors",
        action="store_true",
        help="Retry persisted error cases during a protocol-compatible resume.",
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
    if args.multi_pass is None:
        args.multi_pass = args.analysis_prompt_profile == "clinical"
    if args.ecgfounder_waveform_evidence is None:
        args.ecgfounder_waveform_evidence = bool(args.multi_pass)
    if args.ecgfounder_waveform_evidence and not args.multi_pass:
        parser.error("--ecgfounder-waveform-evidence requires --multi-pass")
    if args.analysis_prompt_profile == "minimal_control" and args.multi_pass:
        parser.error("minimal_control cannot be combined with --multi-pass")
    if not 1024 <= args.ecgfounder_port <= 65535:
        parser.error("--ecgfounder-port must be in [1024, 65535]")
    if args.ecgfounder_ready_wait_sec < 10:
        parser.error("--ecgfounder-ready-wait-sec must be at least 10")
    if not (
        0.0
        < args.initial_response_sla_sec
        < args.first_refinement_sla_sec
        < args.total_analysis_sla_sec
    ):
        parser.error(
            "SLA values must satisfy 0 < initial response < first refinement < total"
        )
    if args.resume_retry_errors and not args.resume:
        parser.error("--resume-retry-errors requires --resume")
    for name in (
        "min_strict_pass_rate",
        "min_mean_partial_credit",
        "min_initial_response_sla_rate",
        "min_first_crop_sla_rate",
        "min_total_sla_rate",
    ):
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
    min_initial_response_sla_rate: float = 0.0,
    min_first_crop_sla_rate: float = 0.0,
    min_total_sla_rate: float = 0.0,
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
    sla_metrics = scorecard.get("sla_metrics")
    sla_metrics = sla_metrics if isinstance(sla_metrics, dict) else {}
    sla_rates: dict[str, float | None] = {}
    for stage, minimum in (
        ("initial_response", min_initial_response_sla_rate),
        ("first_crop_refinement", min_first_crop_sla_rate),
        ("total", min_total_sla_rate),
    ):
        stage_metrics = sla_metrics.get(stage)
        stage_metrics = stage_metrics if isinstance(stage_metrics, dict) else {}
        try:
            actual = float(stage_metrics.get("rate"))
        except (TypeError, ValueError):
            actual = None
        sla_rates[stage] = actual
        if minimum <= 0.0:
            continue
        if actual is None:
            failures.append(f"sla_metrics.{stage}.rate is missing or invalid")
        elif actual + 1e-12 < minimum:
            failures.append(
                f"sla_metrics.{stage}.rate={actual:.6f} below minimum={minimum:.6f}"
            )
    return {
        "minimum_strict_pass_rate": min_strict_pass_rate,
        "minimum_mean_partial_credit": min_mean_partial_credit,
        "minimum_initial_response_sla_rate": min_initial_response_sla_rate,
        "minimum_first_crop_sla_rate": min_first_crop_sla_rate,
        "minimum_total_sla_rate": min_total_sla_rate,
        "sla_rates": sla_rates,
        **rates,
        "passed": not failures,
        "failures": failures,
    }


def validate_manifest_pair(
    *, inference_manifest: Path, scoring_manifest: Path
) -> dict[str, object]:
    """Validate paired identities and prove gold labels are absent at inference."""
    inference = read_json_dict(inference_manifest)
    scoring = read_json_dict(scoring_manifest)
    inference_cases = inference.get("cases")
    scoring_cases = scoring.get("cases")
    if not isinstance(inference_cases, list) or not isinstance(scoring_cases, list):
        raise ValueError("both manifests must contain a cases array")
    if len(inference_cases) != len(scoring_cases):
        raise ValueError("inference and scoring manifests have different case counts")

    blinded = inference_manifest.resolve() != scoring_manifest.resolve()
    identities: list[str] = []
    for index, (inference_case, scoring_case) in enumerate(
        zip(inference_cases, scoring_cases, strict=True)
    ):
        if not isinstance(inference_case, dict) or not isinstance(scoring_case, dict):
            raise ValueError(f"manifest case {index} is not an object")
        inference_label = str(
            inference_case.get("label") or inference_case.get("image") or ""
        )
        scoring_label = str(scoring_case.get("label") or scoring_case.get("image") or "")
        if not inference_label or inference_label != scoring_label:
            raise ValueError(f"manifest case identity mismatch at index {index}")
        if blinded:
            leaked = sorted(set(inference_case) - _BLINDED_CASE_FIELDS)
            if leaked:
                raise ValueError(
                    f"blinded inference case {inference_label} contains answer fields: "
                    + ", ".join(leaked)
                )
            if "expected_severity" not in scoring_case:
                raise ValueError(
                    f"gold scoring case {scoring_label} lacks expected_severity"
                )

        inference_image = (
            inference_manifest.parent / str(inference_case.get("image") or "")
        ).resolve()
        scoring_image = (
            scoring_manifest.parent / str(scoring_case.get("image") or "")
        ).resolve()
        if not inference_image.is_file() or not scoring_image.is_file():
            raise ValueError(f"paired image is missing for case {inference_label}")
        if inference_image != scoring_image and _sha256_file(
            inference_image
        ) != _sha256_file(scoring_image):
            raise ValueError(f"paired image bytes differ for case {inference_label}")
        for field in ("modality", "waveform_artifact_id", "waveform_lead_mode"):
            if str(inference_case.get(field) or "") != str(
                scoring_case.get(field) or ""
            ):
                raise ValueError(
                    f"paired {field} differs for case {inference_label}"
                )
        identities.append(inference_label)

    return {
        "blinded_inference": blinded,
        "case_count": len(identities),
        "identity_order_sha256": hashlib.sha256(
            "\n".join(identities).encode("utf-8")
        ).hexdigest(),
        "inference_manifest": str(inference_manifest),
        "inference_manifest_sha256": _sha256_file(inference_manifest),
        "scoring_manifest": str(scoring_manifest),
        "scoring_manifest_sha256": _sha256_file(scoring_manifest),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_managed_ecgfounder(
    args: argparse.Namespace,
    *,
    env: dict[str, str],
    manifest_path: Path,
) -> dict[str, Any]:
    """Validate and bind a managed sidecar without exposing its bearer token."""
    if not args.ecgfounder_waveform_evidence or not args.manage_ecgfounder_sidecar:
        return {}

    runtime_dir = _resolve_repo_path(args.ecgfounder_runtime_dir)
    python_executable = runtime_dir / ".venv" / "Scripts" / "python.exe"
    checkpoint = runtime_dir / "checkpoints" / "12_lead_ECGFounder.pth"
    manifest = read_json_dict(manifest_path)
    registry_path = args.ecgfounder_registry
    if registry_path is None:
        registry_metadata = manifest.get("waveform_registry")
        registry_name = (
            registry_metadata.get("path")
            if isinstance(registry_metadata, dict)
            else "waveform-registry.json"
        )
        registry_path = manifest_path.parent / str(registry_name)
    registry = _resolve_repo_path(registry_path)

    for label, path in (
        ("ECGFounder Python runtime", python_executable),
        ("ECGFounder checkpoint", checkpoint),
        ("waveform registry", registry),
    ):
        if not path.is_file():
            raise ValueError(f"{label} is missing: {path}")

    registry_payload = read_json_dict(registry)
    registered = registry_payload.get("artifacts")
    if not isinstance(registered, dict):
        raise ValueError("waveform registry has no artifacts object")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise ValueError("MEETI manifest has no cases array")
    required = {
        str(row.get("waveform_artifact_id"))
        for row in cases
        if isinstance(row, dict) and row.get("waveform_artifact_id")
    }
    missing = sorted(required - registered.keys())
    if missing:
        raise ValueError(
            "waveform registry does not cover the selected manifest: "
            f"{len(missing)} missing artifact(s)"
        )

    port = int(args.ecgfounder_port)
    env["DICOM_ECGFOUNDER_TOKEN"] = secrets.token_urlsafe(32)
    env["DICOM_ECGFOUNDER_ENDPOINT"] = f"http://127.0.0.1:{port}/v1/analyze"
    env.setdefault("DICOM_ECGFOUNDER_TIMEOUT_MS", "30000")
    return {
        "python_executable": python_executable,
        "checkpoint": checkpoint,
        "registry": registry,
        "port": port,
        "required_artifact_count": len(required),
        "registered_artifact_count": len(registered),
    }


def managed_ecgfounder_metadata(spec: dict[str, Any]) -> dict[str, Any]:
    if not spec:
        return {"ecgfounder_sidecar_managed": False}
    return {
        "ecgfounder_sidecar_managed": True,
        "ecgfounder_registry": str(spec["registry"]),
        "ecgfounder_required_artifact_count": spec["required_artifact_count"],
        "ecgfounder_registered_artifact_count": spec[
            "registered_artifact_count"
        ],
        "ecgfounder_port": spec["port"],
    }


def start_ecgfounder_sidecar(
    spec: dict[str, Any],
    *,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> tuple[EcgFounderProcess, float]:
    """Start the pinned sidecar and wait for authenticated deep readiness."""
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout = stdout_path.open("w", encoding="utf-8", errors="replace")
    stderr = stderr_path.open("w", encoding="utf-8", errors="replace")
    try:
        process = subprocess.Popen(
            [
                str(spec["python_executable"]),
                "-m",
                "sidecars.ecgfounder.server",
                "--registry",
                str(spec["registry"]),
                "--checkpoint",
                str(spec["checkpoint"]),
                "--port",
                str(spec["port"]),
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=stdout,
            stderr=stderr,
            text=True,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            ),
        )
    finally:
        stdout.close()
        stderr.close()

    sidecar = EcgFounderProcess(process=process)
    started = time.monotonic()
    deadline = started + max(10, timeout_seconds)
    endpoint = urllib.parse.urlsplit(env["DICOM_ECGFOUNDER_ENDPOINT"])
    health_url = urllib.parse.urlunsplit(
        (endpoint.scheme, endpoint.netloc, "/health", "deep=1", "")
    )
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    "ECGFounder sidecar exited before readiness "
                    f"(exit {process.returncode}); see {stderr_path}"
                )
            request = urllib.request.Request(
                health_url,
                headers={"Authorization": f"Bearer {env['DICOM_ECGFOUNDER_TOKEN']}"},
            )
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if isinstance(payload, dict) and payload.get("status") == "ready":
                    return sidecar, round(time.monotonic() - started, 3)
            except (
                OSError,
                TimeoutError,
                urllib.error.URLError,
                json.JSONDecodeError,
            ):
                pass
            time.sleep(1)
        raise TimeoutError(
            f"ECGFounder sidecar was not deep-ready within {timeout_seconds} seconds"
        )
    except BaseException:
        stop_ecgfounder_sidecar(sidecar)
        raise


def stop_ecgfounder_sidecar(sidecar: EcgFounderProcess | None) -> None:
    if sidecar is None:
        return
    process = sidecar.process
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _resolve_repo_path(path: Path) -> Path:
    candidate = path.expanduser()
    return (candidate if candidate.is_absolute() else REPO_ROOT / candidate).resolve()


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


def resolve_native_codex_home(explicit: Path | None) -> Path:
    """Resolve Codex state before OpenClaw replaces HOME for isolation."""
    if explicit is not None:
        return explicit.expanduser().resolve()
    configured = os.environ.get("CODEX_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    user_home = (
        os.environ.get("USERPROFILE", "").strip() or os.environ.get("HOME", "").strip()
    )
    if not user_home:
        raise RuntimeError("Could not resolve the native user home for Codex auth")
    return (Path(user_home).expanduser() / ".codex").resolve()


def resolve_native_codex_command(explicit: Path | None) -> tuple[Path, str]:
    """Resolve and probe the Codex CLI associated with source OAuth state."""
    candidate = str(explicit.expanduser()) if explicit is not None else ""
    resolved_text = shutil.which(candidate or "codex")
    if resolved_text is None and candidate:
        explicit_path = Path(candidate)
        if explicit_path.is_file():
            resolved_text = str(explicit_path)
    if resolved_text is None:
        raise RuntimeError(
            "Codex CLI was not found; install Codex or pass --codex-command"
        )
    resolved = Path(resolved_text).resolve()
    process = subprocess.run(
        [str(resolved), "--version"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
    )
    version = (process.stdout or process.stderr).strip()
    if process.returncode != 0 or not version:
        raise RuntimeError(
            f"Codex CLI version probe failed with exit code {process.returncode}"
        )
    return resolved, version


def prepare_codex_subscription_env(
    env: dict[str, str], codex_home: Path
) -> dict[str, Any]:
    """Bind a run to verified ChatGPT auth without API-key fallback."""
    auth_path = codex_home / "auth.json"
    if not auth_path.is_file():
        raise RuntimeError(f"Codex auth file is missing: {auth_path}")
    try:
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read Codex auth metadata: {exc}") from exc
    if not isinstance(auth, dict) or auth.get("auth_mode") != "chatgpt":
        raise RuntimeError(
            "Codex must be logged in with ChatGPT for subscription-backed runs"
        )
    if not isinstance(auth.get("tokens"), dict):
        raise RuntimeError("Codex ChatGPT token bundle is missing")

    platform_key_was_present = bool(env.pop("OPENAI_API_KEY", "").strip())
    inherited_codex_home_was_present = bool(env.pop("CODEX_HOME", "").strip())
    return {
        "provider_auth_mode": ProviderAuthMode.CODEX_SUBSCRIPTION.value,
        "billing_route": "chatgpt_codex_subscription",
        "codex_source_home": str(codex_home.resolve()),
        "codex_auth_mode": "chatgpt",
        "codex_auth_verified": True,
        "platform_api_key_disabled": True,
        "platform_api_key_was_present_before_isolation": platform_key_was_present,
        "inherited_codex_home_removed": inherited_codex_home_was_present,
    }


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


def resolve_experiment_config_base(
    *,
    resume: bool,
    target_config: Path,
    repo_config: Path = BASE_OPENCLAW_CONFIG,
) -> Path:
    """Reuse the experiment config on resume, including imported OAuth state."""

    if resume and target_config.is_file():
        return target_config
    return repo_config


def effective_provider_profile(
    model_id: str, explicit: str, env: dict[str, str]
) -> str:
    if explicit:
        return explicit
    from_env = env.get("DICOM_OVERLAY_PROVIDER_PROFILE", "")
    if from_env:
        return from_env
    matching_profiles = [
        profile
        for profile in default_provider_profiles()
        if profile.model_ref.lower() == model_id.lower()
        and "image" in profile.input_modalities
    ]
    for profile in sorted(
        matching_profiles,
        key=lambda item: item.auth_mode is not ProviderAuthMode.CODEX_SUBSCRIPTION,
    ):
        return profile.key
    if model_id.lower().startswith("openrouter/"):
        return "openrouter"
    return ""


def assert_subscription_experiment_profile(profile_key: str) -> ProviderProfile:
    if not profile_key:
        raise RuntimeError("a provider profile is required")
    profile = find_provider_profile(profile_key)
    if profile.auth_mode is not ProviderAuthMode.CODEX_SUBSCRIPTION:
        raise RuntimeError(
            "provider profile must use ChatGPT/Codex subscription OAuth; "
            f"'{profile.key}' uses {profile.auth_mode.value}"
        )
    if profile.agent_runtime != "openclaw":
        raise RuntimeError("provider profile must declare agentRuntime=openclaw")
    if profile.api != "openai-chatgpt-responses":
        raise RuntimeError(
            "provider profile must use openai-chatgpt-responses transport"
        )
    return profile


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
            item.strip().lower() for item in parts[1].split("+") if item.strip()
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
    enable_harness: bool = True,
    enable_ecg_founder_tool: bool = False,
    inference_timeout_sec: int = DEFAULT_INFERENCE_TIMEOUT_SEC,
    thinking_level: str = "off",
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
            "thinking_level": thinking_level,
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
        selected_agent_model = merged["agents"]["defaults"]["models"][profile.model_ref]
        merged["agents"]["defaults"]["models"] = {
            profile.model_ref: selected_agent_model
        }
        metadata.update(
            {
                "provider_profile": profile.key,
                "provider_id": profile.provider_id,
                "model_ref": profile.model_ref,
                "api_key_env": profile.api_key_env,
                "provider_auth_mode": profile.auth_mode.value,
                "billing_route": (
                    "chatgpt_codex_subscription"
                    if profile.auth_mode is ProviderAuthMode.CODEX_SUBSCRIPTION
                    else "provider_api_key"
                ),
                "platform_api_key_disabled": (
                    profile.auth_mode is ProviderAuthMode.CODEX_SUBSCRIPTION
                ),
                "agent_runtime": profile.agent_runtime or "auto",
                "agent_loop_owner": (
                    "openclaw" if profile.agent_runtime == "openclaw" else "external"
                ),
                "inference_transport": profile.api or "provider_default",
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
                "provider_auth_mode": "unmanaged",
                "billing_route": "unmanaged",
                "platform_api_key_disabled": False,
            }
        )
    defaults = merged.setdefault("agents", {}).setdefault("defaults", {})
    defaults["thinkingDefault"] = thinking_level
    models_config = merged.get("models", {})
    providers = (
        models_config.get("providers", {}) if isinstance(models_config, dict) else {}
    )
    openai_provider = (
        providers.get("openai") if isinstance(providers, dict) else None
    )
    needs_openai_provider_plugin = bool(
        isinstance(openai_provider, dict)
        and openai_provider.get("api") == "openai-chatgpt-responses"
    )
    if harness_plugin_path is not None:
        plugin_path = str(harness_plugin_path.resolve())
        workspace_path = str(harness_plugin_path.resolve().parent.parent)
        defaults["workspace"] = workspace_path
        plugins = merged.setdefault("plugins", {})
        enabled_plugin_ids = (
            [_OPENAI_PROVIDER_PLUGIN] if needs_openai_provider_plugin else []
        )
        if enable_harness:
            plugins["allow"] = ["dicom-overlay-agent-harness", *enabled_plugin_ids]
            plugins.setdefault("load", {})["paths"] = [plugin_path]
            entries = plugins.setdefault("entries", {})
            entries.clear()
            entries["dicom-overlay-agent-harness"] = {"enabled": True}
            for plugin_id in enabled_plugin_ids:
                entries[plugin_id] = {"enabled": True}
            allowed_tools = ["dicom_bbox_validate"]
            if enable_ecg_founder_tool:
                allowed_tools.append("ecg_founder_analyze_waveform")
            merged["tools"] = build_analysis_tool_policy(allowed_tools)
        else:
            plugins["allow"] = enabled_plugin_ids
            plugins.setdefault("load", {})["paths"] = []
            entries = plugins.setdefault("entries", {})
            entries.clear()
            for plugin_id in enabled_plugin_ids:
                entries[plugin_id] = {"enabled": True}
            merged["tools"] = build_analysis_tool_policy([])
            defaults["skills"] = []
        metadata["harness_plugin_path"] = plugin_path
        metadata["agent_workspace_path"] = workspace_path
        metadata["harness_enabled"] = bool(enable_harness)
        metadata["openai_provider_plugin_enabled"] = needs_openai_provider_plugin
        metadata["ecg_founder_tool_enabled"] = bool(
            enable_harness and enable_ecg_founder_tool
        )
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
    workspace_dir: Path,
) -> GatewayProcess:
    lock_dir = acquire_gateway_lock()
    resolved_workspace = workspace_dir.resolve()
    resolved_workspace.mkdir(parents=True, exist_ok=True)
    paths["gateway_stdout"].parent.mkdir(parents=True, exist_ok=True)
    stdout = paths["gateway_stdout"].open("w", encoding="utf-8")
    stderr = paths["gateway_stderr"].open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            [node_executable, str(OPENCLAW_CLI), "gateway", "run", "--verbose"],
            cwd=resolved_workspace,
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
        if attempt > 1 and "--resume-retry-errors" not in attempt_command:
            attempt_command.append("--resume-retry-errors")
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
        try:
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                captured = append_bounded(captured, line)
            exit_code = process.wait()
            log.write(f"\nexit_code={exit_code}\n")
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            raise
    return {"exit_code": exit_code, "captured": captured}


def assert_openclaw_subscription_ownership(
    config_path: Path,
    *,
    model_id: str,
) -> None:
    """Fail closed unless OpenClaw owns the subscription-backed agent loop."""
    config = read_json_dict(config_path)
    provider_id, separator, provider_model_id = model_id.partition("/")
    if not separator or provider_id != "openai" or not provider_model_id:
        raise RuntimeError("subscription ownership guard requires an openai model id")

    providers = config.get("models", {}).get("providers", {})
    provider = providers.get("openai") if isinstance(providers, dict) else None
    if not isinstance(provider, dict):
        raise RuntimeError("OpenAI provider configuration is missing")
    if provider.get("api") != "openai-chatgpt-responses":
        raise RuntimeError("OpenAI subscription transport is not configured")
    if "apiKey" in provider or "baseUrl" in provider:
        raise RuntimeError("Platform API transport leaked into subscription config")

    provider_models = provider.get("models")
    provider_model = (
        next(
            (
                item
                for item in provider_models
                if isinstance(item, dict) and item.get("id") == provider_model_id
            ),
            None,
        )
        if isinstance(provider_models, list)
        else None
    )
    if not isinstance(provider_model, dict) or provider_model.get("agentRuntime") != {
        "id": "openclaw"
    }:
        raise RuntimeError("provider model runtime is not explicitly OpenClaw")

    agent_models = config.get("agents", {}).get("defaults", {}).get("models", {})
    agent_model = agent_models.get(model_id) if isinstance(agent_models, dict) else None
    if not isinstance(agent_model, dict) or agent_model.get("agentRuntime") != {
        "id": "openclaw"
    }:
        raise RuntimeError("agent model runtime is not explicitly OpenClaw")

    plugins = config.get("plugins")
    if not isinstance(plugins, dict):
        raise RuntimeError("OpenAI provider plugin configuration is missing")
    allow = plugins.get("allow")
    entries = plugins.get("entries")
    if not isinstance(allow, list) or _OPENAI_PROVIDER_PLUGIN not in allow:
        raise RuntimeError("OpenAI provider plugin is not in the plugin allowlist")
    openai_entry = entries.get(_OPENAI_PROVIDER_PLUGIN) if isinstance(entries, dict) else None
    if not isinstance(openai_entry, dict) or openai_entry.get("enabled") is not True:
        raise RuntimeError("OpenAI provider plugin is not explicitly enabled")
    if isinstance(allow, list) and "codex" in allow:
        raise RuntimeError("Codex runtime plugin remains in the plugin allowlist")
    if isinstance(entries, dict) and "codex" in entries:
        raise RuntimeError("Codex runtime plugin remains configured")


def bootstrap_openclaw_subscription_auth(
    *,
    node_executable: str,
    env: dict[str, str],
    config_path: Path,
    state_home: Path,
    source_codex_home: Path,
    audit_path: Path,
    model_id: str,
) -> dict[str, object]:
    """Import OAuth through the bundled provider, then prove OpenClaw ownership."""
    audit = ensure_openclaw_subscription_auth(
        node_executable=node_executable,
        openclaw_cli=OPENCLAW_CLI,
        config_path=config_path,
        state_home=state_home,
        source_codex_home=source_codex_home,
        plugin_path=OPENCLAW_CLI.parent / "dist" / "extensions" / "codex",
        working_directory=REPO_ROOT,
        audit_path=audit_path,
        environment=env,
    )
    assert_openclaw_subscription_ownership(config_path, model_id=model_id)
    return audit


def wait_for_gateway_log_marker(
    gateway: GatewayProcess,
    *,
    log_path: Path,
    marker: str,
    timeout_seconds: int,
) -> float:
    """Fail before inference when a required provider plugin did not load."""

    started = time.monotonic()
    deadline = started + max(1, timeout_seconds)
    expected = marker.lower()
    while time.monotonic() < deadline:
        return_code = gateway.process.poll()
        if return_code is not None:
            raise RuntimeError(
                "OpenClaw Gateway exited before provider readiness "
                f"(exit {return_code})"
            )
        try:
            if expected in log_path.read_text(
                encoding="utf-8", errors="replace"
            ).lower():
                return round(time.monotonic() - started, 3)
        except OSError:
            pass
        time.sleep(0.1)
    raise TimeoutError(
        "OpenClaw provider plugin readiness marker was not observed within "
        f"{timeout_seconds} seconds: {marker}"
    )


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


def build_transport_receipt(
    *,
    gateway_log: Path,
    state_home: Path,
    fast_mode_requested: bool,
) -> dict[str, Any]:
    """Summarize provider payload facts without claiming an unobserved tier."""
    request_count = 0
    service_tiers: dict[str, int] = {}
    apis: dict[str, int] = {}
    providers: dict[str, int] = {}
    if gateway_log.exists():
        with gateway_log.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "[openai-transport] [responses] start " not in line:
                    continue
                request_count += 1
                for field, counts in (
                    ("serviceTier", service_tiers),
                    ("api", apis),
                    ("provider", providers),
                ):
                    value = _transport_log_field(line, field) or "missing"
                    counts[value] = counts.get(value, 0) + 1

    fast_trace = _read_fast_mode_trajectory_counts(state_home)
    priority_count = service_tiers.get("priority", 0)
    observed_priority: bool | None = (
        priority_count > 0 if request_count > 0 else None
    )
    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "gateway_log": str(gateway_log),
        "fast_mode_requested": fast_mode_requested,
        "gateway_fast_mode_trace": fast_trace,
        "transport_request_count": request_count,
        "providers": dict(sorted(providers.items())),
        "apis": dict(sorted(apis.items())),
        "service_tier_values": dict(sorted(service_tiers.items())),
        "priority_service_observed": observed_priority,
        "service_tier_claim": (
            "priority_observed"
            if observed_priority is True
            else "priority_not_observed"
            if observed_priority is False
            else "no_transport_observation"
        ),
    }


def _transport_log_field(line: str, field: str) -> str | None:
    match = re.search(rf"(?:^|\s){re.escape(field)}=([^\s]+)", line)
    return match.group(1) if match else None


def _read_fast_mode_trajectory_counts(state_home: Path) -> dict[str, Any]:
    counts = {"true": 0, "false": 0, "other": 0}
    read_errors = 0
    sessions_dir = state_home / "agents" / "main" / "sessions"
    if sessions_dir.exists():
        for path in sessions_dir.glob("*.trajectory.jsonl"):
            try:
                with path.open(encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if event.get("type") != "trace.metadata":
                            continue
                        value = (
                            event.get("data", {})
                            .get("model", {})
                            .get("fastMode")
                        )
                        key = (
                            "true"
                            if value is True
                            else "false"
                            if value is False
                            else "other"
                        )
                        counts[key] += 1
                        break
            except OSError:
                read_errors += 1
    observed: bool | None
    if counts["true"] > 0 and counts["false"] == 0:
        observed = True
    elif counts["false"] > 0 and counts["true"] == 0:
        observed = False
    else:
        observed = None
    return {
        "observed": observed,
        "counts": counts,
        "read_errors": read_errors,
    }


def base_record(
    args: argparse.Namespace,
    provider_profile: str,
    manifest_path: Path,
    experiment_dir: Path,
    paths: dict[str, Path],
) -> dict[str, Any]:
    protocol_summary = read_protocol_summary(paths["protocol_fingerprint"])
    auth_summary = provider_auth_summary(provider_profile)
    return {
        "requested_model": args.model_id,
        "provider_profile": provider_profile,
        **auth_summary,
        "timeout_sec": args.timeout_sec,
        "limit": args.limit,
        "experiment_arm": experiment_arm(args),
        "analysis_prompt_profile": args.analysis_prompt_profile,
        "thinking_level": args.thinking_level,
        "openclaw_fast_mode": bool(args.fast_mode),
        "rhythm_strip_pass": bool(args.multi_pass),
        "multi_pass": bool(args.multi_pass),
        "multi_pass_max_targets": args.multi_pass_max_targets,
        "multi_pass_max_ekg_systematic_probes": (
            args.multi_pass_max_ekg_systematic_probes
        ),
        "analysis_sla_sec": {
            "initial_response": args.initial_response_sla_sec,
            "first_crop_refinement": args.first_refinement_sla_sec,
            "total": args.total_analysis_sla_sec,
        },
        "ecgfounder_waveform_evidence": bool(args.ecgfounder_waveform_evidence),
        "ecgfounder_sidecar_mode": (
            "managed"
            if args.ecgfounder_waveform_evidence and args.manage_ecgfounder_sidecar
            else "external"
            if args.ecgfounder_waveform_evidence
            else "disabled"
        ),
        "ecgfounder_registry": (
            str(args.ecgfounder_registry) if args.ecgfounder_registry else "manifest"
        ),
        "require_perfect": bool(args.require_perfect),
        "artifact_safety_policy": (
            "require_zero_misses"
            if args.require_perfect
            else "record_misses_as_outcomes"
        ),
        "minimum_strict_pass_rate": args.min_strict_pass_rate,
        "minimum_mean_partial_credit": args.min_mean_partial_credit,
        "minimum_initial_response_sla_rate": (
            args.min_initial_response_sla_rate
        ),
        "minimum_first_crop_sla_rate": args.min_first_crop_sla_rate,
        "minimum_total_sla_rate": args.min_total_sla_rate,
        "resume": bool(args.resume),
        "resume_retry_errors": bool(args.resume_retry_errors),
        "resume_legacy_policy": args.resume_legacy_policy,
        "partial_scorecard_interval": args.partial_scorecard_interval,
        "artifact_verify_min_cases": artifact_min_cases(args),
        "skip_artifact_verify": bool(args.skip_artifact_verify),
        "manifest": str(manifest_path),
        "scoring_manifest": str(
            args.scoring_manifest.resolve()
            if args.scoring_manifest
            else manifest_path
        ),
        "experiment_dir": str(experiment_dir),
        "openclaw_config": str(paths["openclaw_config"]),
        "openclaw_state": str(paths["openclaw_state"]),
        "bbox_tool_audit": str(paths["bbox_tool_audit"]),
        "ecg_founder_tool_audit": str(paths["ecg_founder_tool_audit"]),
        "ecgfounder_sidecar_stdout": str(paths["ecgfounder_sidecar_stdout"]),
        "ecgfounder_sidecar_stderr": str(paths["ecgfounder_sidecar_stderr"]),
        "config_generation_log": str(paths["config_generation"]),
        "subscription_auth_audit": str(paths["codex_auth_import"]),
        "model_catalog_log": str(paths["models_list"]),
        "gateway_stdout": str(paths["gateway_stdout"]),
        "gateway_stderr": str(paths["gateway_stderr"]),
        "transport_receipt": str(paths["transport_receipt"]),
        "eval_console": str(paths["eval_console"]),
        "eval_artifacts": str(paths["eval_dir"]),
        "scorecard_rebuilt": str(paths["scorecard_rebuilt"]),
        "protocol_fingerprint": str(paths["protocol_fingerprint"]),
        "protocol_digest": protocol_summary.get("protocol_digest", ""),
        "protocol_comparability": protocol_summary.get("comparability"),
        "review_artifacts": str(paths["review_dir"]),
    }


def provider_auth_summary(profile_key: str) -> dict[str, Any]:
    if not profile_key:
        return {
            "provider_auth_mode": "unmanaged",
            "billing_route": "unmanaged",
            "platform_api_key_disabled": False,
        }
    profile = find_provider_profile(profile_key)
    is_subscription = profile.auth_mode is ProviderAuthMode.CODEX_SUBSCRIPTION
    return {
        "provider_auth_mode": profile.auth_mode.value,
        "billing_route": (
            "chatgpt_codex_subscription" if is_subscription else "provider_api_key"
        ),
        "platform_api_key_disabled": is_subscription,
        "agent_runtime": profile.agent_runtime or "auto",
        "agent_loop_owner": (
            "openclaw" if profile.agent_runtime == "openclaw" else "external"
        ),
        "inference_transport": profile.api or "provider_default",
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
    half = MAX_CAPTURED_COMMAND_OUTPUT_CHARS // 2
    size = path.stat().st_size
    with path.open("rb") as handle:
        head = handle.read(half)
        if size <= MAX_CAPTURED_COMMAND_OUTPUT_CHARS:
            tail = handle.read(MAX_CAPTURED_COMMAND_OUTPUT_CHARS - len(head))
        else:
            handle.seek(max(0, size - half))
            tail = handle.read(half)
    return (head + b"\n...[bounded log middle omitted]...\n" + tail).decode(
        "utf-8", errors="replace"
    )


def verify_openclaw_runtime_ownership(
    log_path: Path,
    *,
    expected_model: str = "openai/gpt-5.4-mini",
    runtime_node_modules: Path | None = None,
) -> dict[str, object]:
    """Prove OpenClaw owned inference without a Codex app-server handoff."""
    text = read_text_bounded(log_path).lower()
    observed = [
        name for name, marker in _OPENCLAW_RUNTIME_MARKERS.items() if marker in text
    ]
    missing = [name for name in _OPENCLAW_RUNTIME_MARKERS if name not in observed]
    provider_id, separator, model_id = expected_model.lower().partition("/")
    expected_route = f"{provider_id}/{model_id}" if separator else expected_model.lower()
    observed_routes: set[str] = set()
    unexpected_routes: set[str] = set()
    for line in text.splitlines():
        if "[agent/embedded] embedded run start:" not in line:
            continue
        provider_match = re.search(r"\bprovider=([^\s]+)", line)
        model_match = re.search(r"\bmodel=([^\s]+)", line)
        if provider_match is None or model_match is None:
            unexpected_routes.add("unparseable")
            continue
        route = f"{provider_match.group(1)}/{model_match.group(1)}"
        observed_routes.add(route)
        if route != expected_route:
            unexpected_routes.add(route)

    observed_handoffs = [
        name
        for name, marker in _CODEX_AGENT_HANDOFF_MARKERS.items()
        if marker in text
        and (
            name != "codex_provider_route"
            or any(route.startswith("codex/") for route in observed_routes)
        )
    ]
    node_modules = runtime_node_modules or (REPO_ROOT / "openclaw" / "node_modules")
    runtime_dependency_candidates = (
        node_modules / "@openai" / "codex",
        node_modules / "@openclaw" / "codex" / "node_modules" / "@openai" / "codex",
        OPENCLAW_CLI.parent
        / "dist"
        / "extensions"
        / "codex"
        / "node_modules"
        / "@openai"
        / "codex",
    )
    runtime_dependencies = [
        str(path) for path in runtime_dependency_candidates if path.exists()
    ]
    platform_binaries = (
        [str(path) for path in node_modules.rglob("codex.exe")]
        if node_modules.is_dir()
        else []
    )
    verified = bool(
        not missing
        and observed_routes
        and not unexpected_routes
        and not observed_handoffs
        and not runtime_dependencies
        and not platform_binaries
    )
    return {
        "verified": verified,
        "agent_loop_owner": "openclaw" if verified else "unverified",
        "codex_agent_runtime_used": bool(
            observed_handoffs
            or any(route.startswith("codex/") for route in observed_routes)
        ),
        "required_markers": list(_OPENCLAW_RUNTIME_MARKERS),
        "observed_markers": observed,
        "missing_markers": missing,
        "forbidden_handoff_markers": list(_CODEX_AGENT_HANDOFF_MARKERS),
        "observed_handoff_markers": observed_handoffs,
        "expected_agent_route": expected_route,
        "observed_agent_routes": sorted(observed_routes),
        "unexpected_agent_routes": sorted(unexpected_routes),
        "codex_extension_loaded": "[plugins] loading codex from" in text,
        "codex_agent_runtime_dependencies": runtime_dependencies,
        "codex_platform_binaries": platform_binaries,
        "gateway_log": str(log_path),
    }


def detect_provider_block(*log_paths: Path) -> dict[str, str]:
    """Identify non-retryable provider billing/auth failures without secrets."""
    combined = "\n".join(read_text_bounded(path) for path in log_paths).lower()
    for marker, (code, reason) in _PROVIDER_BLOCK_MARKERS.items():
        if marker in combined:
            return {"code": code, "reason": reason}
    return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def render_command(command: list[str]) -> str:
    return " ".join(command)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
