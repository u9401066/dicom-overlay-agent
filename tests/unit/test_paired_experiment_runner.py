from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "run-meeti-paired-experiment.py"
    )
    spec = importlib.util.spec_from_file_location("paired_experiment_runner", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _command(tmp_path: Path, *, arm: str, resume: bool = False) -> list[str]:
    module = _load_module()
    return module.build_arm_command(
        arm=arm,
        manifest=tmp_path / "inference.json",
        scoring_manifest=tmp_path / "gold.json",
        experiment_dir=tmp_path / arm,
        model_id="openai/gpt-5.4-mini",
        thinking_level="medium",
        fast_mode=True,
        timeout_sec=420,
        artifact_min_cases=64,
        multi_pass_max_targets=3,
        multi_pass_max_ekg_systematic_probes=2,
        resume=resume,
    )


def _write_manifest(path: Path, *, case_count: int = 2) -> None:
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {"image": f"case-{index}.png", "label": f"case-{index}"}
                    for index in range(case_count)
                ]
            }
        ),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_ready_arm(
    experiment: Path,
    *,
    inference_manifest: Path,
    scoring_manifest: Path,
    status: str = "completed",
    exit_code: int = 0,
) -> None:
    results = experiment / "eval" / "results"
    results.mkdir(parents=True)
    for index in range(2):
        (results / f"case-{index}.json").write_text("{}", encoding="utf-8")
    (experiment / "eval" / "scorecard.json").write_text("{}", encoding="utf-8")
    (experiment / "eval" / "protocol-fingerprint.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (experiment / "experiment.json").write_text(
        json.dumps(
            {
                "status": status,
                "exit_code": exit_code,
                "eval_error_count": 1 if exit_code else 0,
                "postprocess_exit_code": exit_code,
                "artifact_verify_exit_code": exit_code,
                "manifest_pair": {
                    "blinded_inference": True,
                    "case_count": 2,
                    "inference_manifest_sha256": _sha256(inference_manifest),
                    "scoring_manifest_sha256": _sha256(scoring_manifest),
                },
                "runtime_ownership": {
                    "verified": True,
                    "codex_agent_runtime_used": False,
                },
            }
        ),
        encoding="utf-8",
    )


def test_baseline_command_is_openclaw_minimal_control(tmp_path: Path) -> None:
    command = _command(tmp_path, arm="baseline")

    assert command[0] == sys.executable
    assert "run-meeti-openclaw-experiment.py" in command[1]
    assert "minimal_control" in command
    assert "--no-multi-pass" in command
    assert "--no-ecgfounder-waveform-evidence" in command
    assert "--fast-mode" in command
    assert "--codex-command" not in command


def test_candidate_command_enables_app_harness_and_waveform_tool(
    tmp_path: Path,
) -> None:
    command = _command(tmp_path, arm="candidate", resume=True)

    assert "clinical" in command
    assert "--multi-pass" in command
    assert "--ecgfounder-waveform-evidence" in command
    assert "--fast-mode" in command
    assert command[-2:] == ["--resume", "--resume-retry-errors"]


def test_arm_complete_requires_metadata_and_scorecard(tmp_path: Path) -> None:
    module = _load_module()
    experiment = tmp_path / "baseline"
    (experiment / "eval").mkdir(parents=True)
    (experiment / "experiment.json").write_text(
        '{"status":"completed","exit_code":0}',
        encoding="utf-8",
    )

    assert module._arm_complete(experiment) is False
    (experiment / "eval" / "scorecard.json").write_text("{}", encoding="utf-8")
    assert module._arm_complete(experiment) is True


def test_runtime_ownership_is_observed_from_arm_record(tmp_path: Path) -> None:
    module = _load_module()
    experiment = tmp_path / "baseline"
    experiment.mkdir()
    (experiment / "experiment.json").write_text(
        json.dumps(
            {
                "runtime_ownership": {
                    "verified": True,
                    "codex_agent_runtime_used": False,
                }
            }
        ),
        encoding="utf-8",
    )
    state = {}

    module._record_arm_runtime_ownership(
        state,
        arm="baseline",
        experiment_dir=experiment,
    )

    assert state == {
        "baseline_runtime_ownership_verified": True,
        "baseline_codex_agent_runtime_used": False,
    }


def test_arm_ready_for_comparison_accepts_complete_measured_failures(
    tmp_path: Path,
) -> None:
    module = _load_module()
    inference = tmp_path / "inference.json"
    scoring = tmp_path / "gold.json"
    _write_manifest(inference)
    _write_manifest(scoring)
    experiment = tmp_path / "candidate"
    _write_ready_arm(
        experiment,
        inference_manifest=inference,
        scoring_manifest=scoring,
        status="completed_with_failures",
        exit_code=1,
    )

    assert module._arm_ready_for_comparison(
        experiment,
        expected_case_count=2,
        expected_manifest_sha256=_sha256(inference),
        expected_scoring_manifest_sha256=_sha256(scoring),
    )


def test_arm_ready_for_comparison_rejects_provenance_or_result_gaps(
    tmp_path: Path,
) -> None:
    module = _load_module()
    inference = tmp_path / "inference.json"
    scoring = tmp_path / "gold.json"
    _write_manifest(inference)
    _write_manifest(scoring)
    experiment = tmp_path / "candidate"
    _write_ready_arm(
        experiment,
        inference_manifest=inference,
        scoring_manifest=scoring,
    )
    expected = {
        "expected_case_count": 2,
        "expected_manifest_sha256": _sha256(inference),
        "expected_scoring_manifest_sha256": _sha256(scoring),
    }

    assert not module._arm_ready_for_comparison(
        experiment,
        **(expected | {"expected_manifest_sha256": "wrong"}),
    )
    (experiment / "eval" / "results" / "case-1.json").unlink()
    assert not module._arm_ready_for_comparison(experiment, **expected)


def test_main_compares_reusable_failed_arm_without_accepting_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    inference = tmp_path / "inference.json"
    scoring = tmp_path / "gold.json"
    output = tmp_path / "experiment"
    _write_manifest(inference)
    _write_manifest(scoring)
    _write_ready_arm(
        output / "baseline",
        inference_manifest=inference,
        scoring_manifest=scoring,
    )
    _write_ready_arm(
        output / "candidate",
        inference_manifest=inference,
        scoring_manifest=scoring,
        status="completed_with_failures",
        exit_code=1,
    )
    commands: list[list[str]] = []

    def _fake_run(command: list[str], *, log_path: Path) -> int:
        commands.append(command)
        return 0

    monkeypatch.setattr(module, "_run_logged", _fake_run)

    exit_code = module.main(
        [
            "--manifest",
            str(inference),
            "--scoring-manifest",
            str(scoring),
            "--output-root",
            str(output),
        ]
    )

    assert exit_code == 1
    assert len(commands) == 1
    assert str(module.COMPARATOR) in commands[0]
    assert "--allow-incomplete" in commands[0]
    state = json.loads((output / "paired-experiment.json").read_text("utf-8"))
    assert state["status"] == "completed_with_failures"
    assert state["execution_complete"] is True
    assert state["acceptance_passed"] is False
    assert state["comparison_allow_incomplete"] is True
    assert state["comparison_scope"] == "shared_non_error_cases"
    assert state["baseline_reused_completed"] is True
    assert state["candidate_reused_completed_with_failures"] is True
    assert state["baseline_acceptance_passed"] is True
    assert state["candidate_acceptance_passed"] is False
    assert state["runtime_ownership_verified"] is True
    assert state["codex_agent_runtime_used"] is False
