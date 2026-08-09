"""Run a resumable OpenClaw MEETI baseline/candidate experiment pair."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
ARM_RUNNER = REPO_ROOT / "scripts" / "run-meeti-openclaw-experiment.py"
COMPARATOR = REPO_ROOT / "scripts" / "compare-eval-runs.py"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        Path(temp_name).replace(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            Path(temp_name).unlink()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _manifest_case_count(path: Path) -> int:
    payload = _read_json(path)
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"manifest has no cases: {path}")
    return len(cases)


def _arm_complete(experiment_dir: Path) -> bool:
    metadata = _read_json(experiment_dir / "experiment.json")
    return bool(
        metadata.get("status") == "completed"
        and metadata.get("exit_code") == 0
        and (experiment_dir / "eval" / "scorecard.json").is_file()
    )


def _arm_ready_for_comparison(
    experiment_dir: Path,
    *,
    expected_case_count: int,
    expected_manifest_sha256: str,
    expected_scoring_manifest_sha256: str,
) -> bool:
    """Accept measured arm failures without accepting incomplete provenance."""
    metadata = _read_json(experiment_dir / "experiment.json")
    if metadata.get("status") not in {"completed", "completed_with_failures"}:
        return False
    results_dir = experiment_dir / "eval" / "results"
    if len(list(results_dir.glob("*.json"))) != expected_case_count:
        return False
    if not (experiment_dir / "eval" / "scorecard.json").is_file():
        return False
    if not (experiment_dir / "eval" / "protocol-fingerprint.json").is_file():
        return False
    manifest_pair = metadata.get("manifest_pair")
    ownership = metadata.get("runtime_ownership")
    return bool(
        isinstance(manifest_pair, dict)
        and manifest_pair.get("blinded_inference") is True
        and manifest_pair.get("case_count") == expected_case_count
        and manifest_pair.get("inference_manifest_sha256")
        == expected_manifest_sha256
        and manifest_pair.get("scoring_manifest_sha256")
        == expected_scoring_manifest_sha256
        and isinstance(ownership, dict)
        and ownership.get("verified") is True
        and ownership.get("codex_agent_runtime_used") is False
    )


def _record_arm_runtime_ownership(
    state: dict[str, Any],
    *,
    arm: str,
    experiment_dir: Path,
) -> None:
    metadata = _read_json(experiment_dir / "experiment.json")
    proof = metadata.get("runtime_ownership")
    proof = proof if isinstance(proof, dict) else {}
    state[f"{arm}_runtime_ownership_verified"] = bool(proof.get("verified"))
    state[f"{arm}_codex_agent_runtime_used"] = (
        bool(proof.get("codex_agent_runtime_used"))
        if "codex_agent_runtime_used" in proof
        else None
    )


def _record_arm_outcome(
    state: dict[str, Any],
    *,
    arm: str,
    experiment_dir: Path,
) -> None:
    metadata = _read_json(experiment_dir / "experiment.json")
    scorecard = _read_json(experiment_dir / "eval" / "scorecard.json")
    error_count = metadata.get("eval_error_count")
    if not isinstance(error_count, int):
        error_count = scorecard.get("error_count")
    state[f"{arm}_status"] = metadata.get("status")
    state[f"{arm}_acceptance_passed"] = bool(
        metadata.get("status") == "completed" and metadata.get("exit_code") == 0
    )
    state[f"{arm}_eval_error_count"] = (
        error_count if isinstance(error_count, int) else None
    )
    state[f"{arm}_postprocess_exit_code"] = metadata.get("postprocess_exit_code")
    state[f"{arm}_artifact_verify_exit_code"] = metadata.get(
        "artifact_verify_exit_code"
    )


def build_arm_command(
    *,
    arm: str,
    manifest: Path,
    scoring_manifest: Path,
    experiment_dir: Path,
    model_id: str,
    thinking_level: str,
    fast_mode: bool,
    timeout_sec: int,
    artifact_min_cases: int,
    multi_pass_max_targets: int,
    multi_pass_max_ekg_systematic_probes: int,
    resume: bool,
) -> list[str]:
    """Build one arm command with OpenClaw as the only agent runtime."""
    if arm not in {"baseline", "candidate"}:
        raise ValueError(f"unsupported arm: {arm}")
    command = [
        sys.executable,
        str(ARM_RUNNER),
        "--model-id",
        model_id,
        "--manifest",
        str(manifest),
        "--scoring-manifest",
        str(scoring_manifest),
        "--timeout-sec",
        str(timeout_sec),
        "--experiment-dir",
        str(experiment_dir),
        "--thinking-level",
        thinking_level,
        ("--fast-mode" if fast_mode else "--no-fast-mode"),
        "--min-strict-pass-rate",
        "0",
        "--min-mean-partial-credit",
        "0",
        "--artifact-min-cases",
        str(artifact_min_cases),
        "--multi-pass-max-targets",
        str(multi_pass_max_targets),
        "--multi-pass-max-ekg-systematic-probes",
        str(multi_pass_max_ekg_systematic_probes),
    ]
    if arm == "baseline":
        command.extend(
            [
                "--analysis-prompt-profile",
                "minimal_control",
                "--no-multi-pass",
                "--no-ecgfounder-waveform-evidence",
            ]
        )
    else:
        command.extend(
            [
                "--analysis-prompt-profile",
                "clinical",
                "--multi-pass",
                "--ecgfounder-waveform-evidence",
            ]
        )
    if resume:
        command.extend(["--resume", "--resume-retry-errors"])
    return command


def _run_logged(command: list[str], *, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", errors="replace") as log:
        log.write(f"\n[{_now()}] command={json.dumps(command)}\n")
        log.flush()
        process = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            ),
        )
        log.write(f"[{_now()}] exit_code={process.returncode}\n")
        return int(process.returncode)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--scoring-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--model-id", default="openai/gpt-5.4-mini")
    parser.add_argument(
        "--thinking-level",
        choices=("off", "minimal", "low", "medium", "high"),
        default="off",
    )
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument(
        "--fast-mode",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--artifact-min-cases", type=int, default=0)
    parser.add_argument("--multi-pass-max-targets", type=int, default=2)
    parser.add_argument(
        "--multi-pass-max-ekg-systematic-probes",
        type=int,
        default=1,
    )
    parser.add_argument("--random-seed", type=int, default=20260806)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = args.manifest.resolve()
    scoring_manifest = args.scoring_manifest.resolve()
    output_root = args.output_root.resolve()
    if manifest == scoring_manifest:
        raise SystemExit("inference and scoring manifests must be distinct")
    inference_cases = _manifest_case_count(manifest)
    scoring_cases = _manifest_case_count(scoring_manifest)
    if inference_cases != scoring_cases:
        raise SystemExit("inference and scoring manifest counts differ")
    artifact_min_cases = args.artifact_min_cases or inference_cases
    if not 1 <= artifact_min_cases <= inference_cases:
        raise SystemExit("artifact-min-cases must be between 1 and case count")

    output_root.mkdir(parents=True, exist_ok=True)
    baseline_dir = output_root / "baseline"
    candidate_dir = output_root / "candidate"
    comparison_dir = output_root / "comparison"
    state_path = output_root / "paired-experiment.json"
    log_path = output_root / "supervisor.log"
    state: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "active_arm": "baseline",
        "agent_runtime": "openclaw",
        "agent_loop_owner": "openclaw",
        "oauth_source": "codex_chatgpt_subscription",
        "codex_agent_runtime_allowed": False,
        "codex_agent_runtime_used": None,
        "model_id": args.model_id,
        "thinking_level": args.thinking_level,
        "openclaw_fast_mode": bool(args.fast_mode),
        "analysis_sla_sec": {
            "initial_response": 60,
            "first_crop_refinement": 100,
            "total": 180,
        },
        "case_count": inference_cases,
        "manifest": str(manifest),
        "manifest_sha256": _sha256(manifest),
        "scoring_manifest": str(scoring_manifest),
        "scoring_manifest_sha256": _sha256(scoring_manifest),
        "baseline_dir": str(baseline_dir),
        "candidate_dir": str(candidate_dir),
        "comparison_dir": str(comparison_dir),
        "updated_at": _now(),
    }
    _write_json_atomic(state_path, state)
    manifest_sha256 = state["manifest_sha256"]
    scoring_manifest_sha256 = state["scoring_manifest_sha256"]

    for arm, experiment_dir in (
        ("baseline", baseline_dir),
        ("candidate", candidate_dir),
    ):
        state["active_arm"] = arm
        state["updated_at"] = _now()
        _write_json_atomic(state_path, state)
        if _arm_complete(experiment_dir) and _arm_ready_for_comparison(
            experiment_dir,
            expected_case_count=inference_cases,
            expected_manifest_sha256=manifest_sha256,
            expected_scoring_manifest_sha256=scoring_manifest_sha256,
        ):
            state[f"{arm}_exit_code"] = 0
            state[f"{arm}_reused_completed"] = True
            _record_arm_runtime_ownership(
                state,
                arm=arm,
                experiment_dir=experiment_dir,
            )
            _record_arm_outcome(
                state,
                arm=arm,
                experiment_dir=experiment_dir,
            )
            continue
        if _arm_ready_for_comparison(
            experiment_dir,
            expected_case_count=inference_cases,
            expected_manifest_sha256=manifest_sha256,
            expected_scoring_manifest_sha256=scoring_manifest_sha256,
        ):
            metadata = _read_json(experiment_dir / "experiment.json")
            state[f"{arm}_exit_code"] = int(metadata.get("exit_code") or 0)
            state[f"{arm}_reused_completed_with_failures"] = True
            _record_arm_runtime_ownership(
                state,
                arm=arm,
                experiment_dir=experiment_dir,
            )
            _record_arm_outcome(
                state,
                arm=arm,
                experiment_dir=experiment_dir,
            )
            continue
        resume = (experiment_dir / "eval" / "results").is_dir()
        command = build_arm_command(
            arm=arm,
            manifest=manifest,
            scoring_manifest=scoring_manifest,
            experiment_dir=experiment_dir,
            model_id=args.model_id,
            thinking_level=args.thinking_level,
            fast_mode=bool(args.fast_mode),
            timeout_sec=args.timeout_sec,
            artifact_min_cases=artifact_min_cases,
            multi_pass_max_targets=args.multi_pass_max_targets,
            multi_pass_max_ekg_systematic_probes=(
                args.multi_pass_max_ekg_systematic_probes
            ),
            resume=resume,
        )
        exit_code = _run_logged(command, log_path=log_path)
        state[f"{arm}_exit_code"] = exit_code
        state[f"{arm}_resumed"] = resume
        state["updated_at"] = _now()
        if not _arm_ready_for_comparison(
            experiment_dir,
            expected_case_count=inference_cases,
            expected_manifest_sha256=manifest_sha256,
            expected_scoring_manifest_sha256=scoring_manifest_sha256,
        ):
            state["status"] = "interrupted"
            state["failure_reason"] = (
                f"{arm} did not produce a complete, provenance-bound result set "
                f"(exit code {exit_code})"
            )
            _write_json_atomic(state_path, state)
            return exit_code or 1
        _record_arm_runtime_ownership(
            state,
            arm=arm,
            experiment_dir=experiment_dir,
        )
        _record_arm_outcome(
            state,
            arm=arm,
            experiment_dir=experiment_dir,
        )
        _write_json_atomic(state_path, state)

    state["runtime_ownership_verified"] = all(
        state.get(f"{arm}_runtime_ownership_verified") is True
        for arm in ("baseline", "candidate")
    )
    state["codex_agent_runtime_used"] = any(
        state.get(f"{arm}_codex_agent_runtime_used") is True
        for arm in ("baseline", "candidate")
    )

    state["active_arm"] = "comparison"
    state["updated_at"] = _now()
    _write_json_atomic(state_path, state)
    compare_command = [
        sys.executable,
        str(COMPARATOR),
        "--baseline",
        str(baseline_dir),
        "--candidate",
        str(candidate_dir),
        "--output",
        str(comparison_dir),
        "--random-seed",
        str(args.random_seed),
    ]
    allow_incomplete = any(
        (state.get(f"{arm}_eval_error_count") or 0) > 0
        for arm in ("baseline", "candidate")
    )
    if allow_incomplete:
        compare_command.append("--allow-incomplete")
    state["comparison_allow_incomplete"] = allow_incomplete
    state["comparison_scope"] = (
        "shared_non_error_cases" if allow_incomplete else "all_cases"
    )
    compare_exit = _run_logged(compare_command, log_path=log_path)
    state["comparison_exit_code"] = compare_exit
    comparison = _read_json(comparison_dir / "comparison.json")
    state["comparison_paired_cases"] = comparison.get("paired_cases")
    state["comparison_baseline_only_cases"] = comparison.get(
        "baseline_only_cases"
    )
    state["comparison_candidate_only_cases"] = comparison.get(
        "candidate_only_cases"
    )
    state["active_arm"] = None
    arm_acceptance_passed = all(
        state.get(f"{arm}_acceptance_passed") is True
        for arm in ("baseline", "candidate")
    )
    state["execution_complete"] = compare_exit == 0
    state["acceptance_passed"] = bool(
        compare_exit == 0 and arm_acceptance_passed and not allow_incomplete
    )
    state["status"] = (
        "completed"
        if state["acceptance_passed"]
        else "completed_with_failures"
        if compare_exit == 0
        else "comparison_failed"
    )
    state["updated_at"] = _now()
    state["finished_at"] = _now()
    if compare_exit != 0:
        state["failure_reason"] = f"comparison exited with code {compare_exit}"
    elif not arm_acceptance_passed:
        state["failure_reason"] = (
            "comparison completed, but one or more arms failed acceptance gates"
        )
    _write_json_atomic(state_path, state)
    return compare_exit or (0 if arm_acceptance_passed else 1)


if __name__ == "__main__":
    raise SystemExit(main())
