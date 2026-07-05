"""Run a bounded MEETI OpenClaw experiment without shell wrappers."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dicom_overlay.infrastructure.openclaw_settings import (
    ProviderProfile,
    build_openclaw_config,
    default_provider_profiles,
    merge_openclaw_config,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "data" / "eval-datasets" / "meeti-1000-all" / "manifest.json"
OPENCLAW_CLI = REPO_ROOT / "openclaw" / "node_modules" / "openclaw" / "openclaw.mjs"
BASE_OPENCLAW_CONFIG = REPO_ROOT / "openclaw" / "openclaw.json"
GATEWAY_URL = "ws://127.0.0.1:18789"
OPENCLAW_GATEWAY_LOCK = REPO_ROOT / "data" / "tmp" / "openclaw-gateway.lock"
UV_TMP_RELATIVE = "data/tmp/uv"
MAX_CAPTURED_COMMAND_OUTPUT_CHARS = 200_000


@dataclass(frozen=True)
class GatewayProcess:
    process: subprocess.Popen[str]
    lock_dir: Path


def main() -> int:
    args = parse_args()
    env = build_child_env(REPO_ROOT)
    load_dotenv(REPO_ROOT / ".env", env)

    manifest_path = args.manifest.resolve() if args.manifest else DEFAULT_MANIFEST
    experiment_dir = resolve_experiment_dir(args.experiment_dir, args.model_id)
    experiment_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "experiment_json": experiment_dir / "experiment.json",
        "models_list": experiment_dir / "openclaw-models-list.txt",
        "config_generation": experiment_dir / "openclaw-config-generation.json",
        "gateway_stdout": experiment_dir / "gateway.stdout.log",
        "gateway_stderr": experiment_dir / "gateway.stderr.log",
        "eval_console": experiment_dir / "eval-console.log",
        "eval_dir": experiment_dir / "eval",
        "scorecard": experiment_dir / "eval" / "scorecard.json",
        "scorecard_rebuilt": experiment_dir / "eval" / "scorecard.rebuilt.json",
        "review_dir": experiment_dir / "eval" / "review",
        "openclaw_config": experiment_dir / "openclaw.experiment.json",
    }

    provider_profile = effective_provider_profile(args.model_id, args.provider_profile, env)
    env["DICOM_OVERLAY_PROVIDER_PROFILE"] = provider_profile

    try:
        config_metadata = write_experiment_openclaw_config(
            base_config=BASE_OPENCLAW_CONFIG,
            target_config=paths["openclaw_config"],
            model_id=args.model_id,
            profile_key=provider_profile,
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
        ["node", str(OPENCLAW_CLI), "models", "list"],
        cwd=REPO_ROOT,
        env=env,
        output_path=paths["models_list"],
    )
    catalog_text = read_text_bounded(paths["models_list"])
    model_catalog_warning = ""
    if catalog_result != 0 and not provider_profile:
        write_json(
            paths["experiment_json"],
            base_record(args, provider_profile, manifest_path, experiment_dir, paths)
            | {
                "status": "blocked",
                "reason": "could not read the local OpenClaw model catalog",
                "model_catalog_exit_code": catalog_result,
                "finished_at": now_iso(),
            },
        )
        print("BLOCKED: could not read local OpenClaw model catalog")
        print(f"Experiment record: {paths['experiment_json']}")
        return 20
    if catalog_result != 0:
        model_catalog_warning = (
            "OpenClaw models list failed before Gateway startup; "
            "provider-profile run will continue and rely on eval artifacts."
        )
    if catalog_result == 0 and args.model_id not in catalog_text:
        write_json(
            paths["experiment_json"],
            base_record(args, provider_profile, manifest_path, experiment_dir, paths)
            | {
                "status": "blocked",
                "reason": "requested model id is not exposed by the local OpenClaw catalog",
                "suggested_models": [
                    "openai/gpt-5.4-mini",
                    "openai/gpt-5.5",
                    "openai/gpt-5.5-pro",
                ],
                "model_catalog_exit_code": catalog_result,
                "finished_at": now_iso(),
            },
        )
        print(f"BLOCKED: requested model is not in OpenClaw model catalog: {args.model_id}")
        print(f"Experiment record: {paths['experiment_json']}")
        return 20

    gateway_process: GatewayProcess | None = None
    exit_code = 1
    eval_exit_code = 1
    postprocess_exit_code = 0
    artifact_verify_exit_code: int | None = None
    eval_attempts = 0
    eval_error_count = 0
    status = "failed"

    try:
        write_json(
            paths["experiment_json"],
            base_record(args, provider_profile, manifest_path, experiment_dir, paths)
            | {
                "status": "running",
                "model_catalog_exit_code": catalog_result,
                "model_catalog_warning": model_catalog_warning,
                "started_at": now_iso(),
                "updated_at": now_iso(),
            },
        )
        gateway_process = start_gateway(paths, env)
        time.sleep(args.gateway_wait_sec)

        eval_args = [
            sys.executable,
            "scripts/run-eval.py",
            "--gateway",
            GATEWAY_URL,
            "--manifest",
            str(manifest_path),
            "--timeout-sec",
            str(args.timeout_sec),
            "--output",
            str(paths["eval_dir"]),
            "--partial-scorecard-interval",
            str(args.partial_scorecard_interval),
        ]
        if args.limit > 0:
            eval_args += ["--limit", str(args.limit)]
        if args.require_perfect:
            eval_args.append("--require-perfect")
        if args.multi_pass:
            eval_args += ["--multi-pass", "--multi-pass-max-targets", str(args.multi_pass_max_targets)]

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
                    verify_command.append("--require-multipass-trace")
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
            except Exception as exc:
                eval_error_count = 1
                postprocess_exit_code = 1
                append_log(paths["eval_console"], f"\nCould not read eval error_count: {exc}\n")
        elif eval_exit_code == 0:
            eval_error_count = 1
            postprocess_exit_code = 1
            append_log(paths["eval_console"], "\nMissing eval scorecard.json after successful eval exit.\n")

        if eval_exit_code == 0 and eval_error_count > 0:
            exit_code = 1
        status = (
            "completed"
            if exit_code == 0 and postprocess_exit_code == 0 and eval_error_count == 0
            else "completed_with_failures"
        )
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
                "model_catalog_exit_code": catalog_result,
                "model_catalog_warning": model_catalog_warning,
                "eval_attempts": eval_attempts,
                "postprocess_exit_code": postprocess_exit_code,
                "artifact_verify_exit_code": artifact_verify_exit_code,
                "finished_at": now_iso(),
            },
        )
        print(f"Experiment record: {paths['experiment_json']}")

    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default="openai/gpt-5.5-mini")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--provider-profile", default="")
    parser.add_argument("--timeout-sec", type=int, default=90)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--experiment-dir", type=Path, default=None)
    parser.add_argument("--multi-pass", action="store_true")
    parser.add_argument("--multi-pass-max-targets", type=int, default=3)
    parser.add_argument("--require-perfect", action="store_true")
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
    parser.add_argument("--gateway-wait-sec", type=int, default=8)
    parser.add_argument("--gateway-retry-attempts", type=int, default=6)
    parser.add_argument("--gateway-retry-delay-sec", type=int, default=5)
    return parser.parse_args()


def artifact_min_cases(args: argparse.Namespace) -> int:
    if args.artifact_min_cases > 0:
        return int(args.artifact_min_cases)
    if args.limit > 0:
        return int(args.limit)
    return 1000


def build_child_env(repo_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("UV_CACHE_DIR", str(repo_root / ".uv-cache-codex"))
    env.setdefault("UV_NO_PROGRESS", "1")
    env.setdefault("UV_PYTHON_DOWNLOADS", "never")
    uv_tmp = repo_root / Path(UV_TMP_RELATIVE)
    uv_tmp.mkdir(parents=True, exist_ok=True)
    env["TMP"] = str(uv_tmp)
    env["TEMP"] = str(uv_tmp)
    openclaw_home = repo_root / "openclaw-home"
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


def effective_provider_profile(model_id: str, explicit: str, env: dict[str, str]) -> str:
    if explicit:
        return explicit
    from_env = env.get("DICOM_OVERLAY_PROVIDER_PROFILE", "")
    if from_env:
        return from_env
    if model_id.lower().startswith("openrouter/"):
        return "openrouter"
    return ""


def write_experiment_openclaw_config(
    *,
    base_config: Path,
    target_config: Path,
    model_id: str,
    profile_key: str,
) -> dict[str, Any]:
    existing = read_json_dict(base_config)
    metadata: dict[str, Any] = {
        "provider_profile": profile_key,
        "requested_model": model_id,
    }
    if profile_key:
        profile = find_provider_profile(profile_key)
        model = model_id
        provider_prefix = f"{profile.provider_id}/"
        if model.lower().startswith(provider_prefix.lower()):
            model = model[len(provider_prefix) :]
        profile = replace(profile, model=model)
        managed = build_openclaw_config(profile)
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
        defaults.setdefault("model", {})["primary"] = model_id
        defaults["model"].setdefault("fallbacks", [])
        models = defaults.setdefault("models", {})
        models.setdefault(model_id, {"alias": model_id})
        metadata.update(
            {
                "provider_profile": "",
                "provider_id": "",
                "model_ref": model_id,
                "api_key_env": "",
            }
        )
    write_json(target_config, merged)
    return metadata


def find_provider_profile(profile_key: str) -> ProviderProfile:
    profiles = default_provider_profiles()
    for profile in profiles:
        if profile.key == profile_key or profile.provider_id == profile_key:
            return profile
    known = sorted({item.key for item in profiles} | {item.provider_id for item in profiles})
    raise ValueError(f"Unknown provider profile '{profile_key}'. Known profiles: {', '.join(known)}")


def start_gateway(paths: dict[str, Path], env: dict[str, str]) -> GatewayProcess:
    lock_dir = acquire_gateway_lock()
    paths["gateway_stdout"].parent.mkdir(parents=True, exist_ok=True)
    stdout = paths["gateway_stdout"].open("w", encoding="utf-8")
    stderr = paths["gateway_stderr"].open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            ["node", str(OPENCLAW_CLI), "gateway", "run", "--verbose"],
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


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


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
        result = run_logged_command(
            command,
            cwd=cwd,
            env=env,
            log_path=log_path,
            section=f"eval attempt {attempt}",
        )
        if result["exit_code"] == 0:
            return {"exit_code": 0, "attempts": attempts}
        if "gateway starting; retry shortly" not in result["captured"] or attempt >= max_attempts:
            return {"exit_code": result["exit_code"], "attempts": attempts}
        append_log(log_path, f"Gateway not ready; retrying after {delay_seconds} seconds.\n")
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


def run_to_file(command: list[str], *, cwd: Path, env: dict[str, str], output_path: Path) -> int:
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
    return {
        "requested_model": args.model_id,
        "provider_profile": provider_profile,
        "timeout_sec": args.timeout_sec,
        "limit": args.limit,
        "multi_pass": bool(args.multi_pass),
        "multi_pass_max_targets": args.multi_pass_max_targets,
        "require_perfect": bool(args.require_perfect),
        "partial_scorecard_interval": args.partial_scorecard_interval,
        "artifact_verify_min_cases": artifact_min_cases(args),
        "skip_artifact_verify": bool(args.skip_artifact_verify),
        "manifest": str(manifest_path),
        "experiment_dir": str(experiment_dir),
        "openclaw_config": str(paths["openclaw_config"]),
        "config_generation_log": str(paths["config_generation"]),
        "model_catalog_log": str(paths["models_list"]),
        "gateway_stdout": str(paths["gateway_stdout"]),
        "gateway_stderr": str(paths["gateway_stderr"]),
        "eval_console": str(paths["eval_console"]),
        "eval_artifacts": str(paths["eval_dir"]),
        "scorecard_rebuilt": str(paths["scorecard_rebuilt"]),
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


def read_text_bounded(path: Path) -> str:
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(MAX_CAPTURED_COMMAND_OUTPUT_CHARS)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_command(command: list[str]) -> str:
    return " ".join(command)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
