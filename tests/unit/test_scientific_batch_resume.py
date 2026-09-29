"""Explicit failed-case continuation retains the failure and rejects silent skips."""

from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest
from PIL import Image

from tests.unit.test_scientific_desktop_batch import batch as batch
from tests.unit.test_scientific_desktop_batch import case as case
from tests.unit.test_scientific_desktop_batch import evidence as evidence
from tests.unit.test_scientific_desktop_batch import verifier as verifier
from tests.unit.test_scientific_desktop_usage import inputs as inputs
from tests.unit.test_scientific_desktop_usage import retained as retained
from tests.unit.test_scientific_desktop_usage import usage as usage


@pytest.fixture
def resumed(batch):
    v, run, manifest, live, _recovery, write = batch
    source = manifest.parent / "pending.png"
    Image.new("RGB", (32, 24), "gray").save(source)
    future = manifest.parent / "future.png"
    Image.new("RGB", (32, 24), "black").save(future)
    payload = v.read(manifest)
    payload["cases"].append({"label": "future", "image": future.name})
    records = [
        {
            "case_identity": row["label"],
            "image_sha256": v.digest(manifest.parent / row["image"]),
        }
        for row in payload["cases"]
    ]
    payload["counts"]["cases"] = 3
    payload["selection"]["input_image_order_sha256"] = v.legacy.canonical_digest(
        records
    )
    write(manifest, payload)
    for name in ("plan.json", "plan-v2.json"):
        plan = v.read(run / name)
        plan["planned_cases"] = records
        plan["bindings"].update(
            inference_sha256=v.digest(manifest),
            input_image_order_sha256=v.legacy.canonical_digest(records),
            viewer_pid=42,
        )
        if name == "plan-v2.json":
            plan["original_plan_sha256"] = v.digest(run / "plan.json")
        write(run / name, plan)
    previous = v.read(run / "plan-v2.json")
    folder = run / "case-001"
    folder.mkdir()
    (folder / "visible-roi.png").write_bytes(source.read_bytes())
    failure = {
        "index": 1,
        "case_id": "pending",
        "input_sha256": v.digest(source),
        "actual_gui": True,
        "gold_read": False,
        "direct_model_requests": 0,
        "started_utc": "2026-09-29T11:03:00+00:00",
    }
    write(folder / "attempt.json", failure)
    failure.update(
        status="technical_failure",
        finished_utc="2026-09-29T11:04:00+00:00",
        file_to_visible_bilinear_mae=0.0,
    )
    write(folder / "receipt.json", failure)
    attempt = live / "data/scientific-attempts" / ("c" * 32)
    attempt.mkdir()
    (attempt / "source.png").write_bytes(source.read_bytes())
    write(
        attempt / "intake.json",
        {"run_id": attempt.name, "source_image_sha256": v.digest(source)},
    )
    turns, sessions, lines = [], [], []
    for index, stage in enumerate(v.usage.STAGES, 1):
        directory = attempt / f"turn-{index:04d}"
        directory.mkdir()
        (directory / "model-visible.txt").write_bytes(b"synthetic failed turn")
        turn = {
            "stage": stage,
            "sequence": index,
            "image_sha256": v.digest(source),
            "gateway_run_id": f"failed-run-{index}",
            "session_key": f"failed-key-{index}",
            "terminal_seen": True,
            "transport_failure": "",
            "model_text_sha256": v.digest(directory / "model-visible.txt"),
            "artifacts": {
                "model-visible.txt": v.digest(directory / "model-visible.txt")
            },
        }
        write(directory / "receipt.json", turn)
        turns.append(turn)
        sessions.append(
            {
                "key": turn["session_key"],
                "sessionId": f"failed-session-{index}",
                "model": "gpt-6-astra",
                "modelProvider": "openai",
                "totalTokensFresh": True,
                "inputTokens": 10,
                "outputTokens": 2,
                "totalTokens": 12,
            }
        )
        lines.append(
            f"embedded run start: runId=failed-run-{index} sessionId=failed-session-{index} "
            "provider=openai model=gpt-6-astra thinking=medium"
        )
    with (live / "gateway.log").open("ab") as stream:
        stream.write(("\n" + "\n".join(lines)).encode())
    log = (live / "gateway.log").read_bytes()
    terminal = manifest.parent / "terminal.json"
    write(
        terminal,
        {
            "original_failure_sha256": v.digest(folder / "receipt.json"),
            "source_sha256": v.digest(source),
            "retained_files": v.inventory(attempt),
            "original_failure_preserved": True,
            "model_requests": 0,
            "clinical_scored": False,
            "replay": {
                "preflight_completed": True,
                "new_gui_handoff": False,
                "new_publication": False,
                "retained_turns_replayed": 5,
            },
            "turns": v.usage.bind_usage(turns, sessions, log.decode()),
            "gateway_log_prefix_bytes": len(log),
            "gateway_log_prefix_sha256": hashlib.sha256(log).hexdigest(),
        },
    )
    app_log = manifest.parent / "app.log"
    app_log.write_text(
        "State: ANALYZING → WAITING\nState: WAITING → MONITORING\n", encoding="utf-8"
    )
    plan = deepcopy(previous)
    plan.update(
        started_utc="2026-09-29T11:05:00+00:00",
        previous_plan_sha256=v.digest(run / "plan-v2.json"),
        resume_from_index=2,
        preserved_failure={
            "index": 1,
            "receipt_sha256": v.digest(folder / "receipt.json"),
            "terminal_audit_sha256": v.digest(terminal),
            "status": "technical_failure",
            "count_in_denominator": True,
            "rerun": False,
        },
        prior_receipt_sha256={
            str(i): v.digest(run / f"case-{i:03d}/receipt.json") for i in range(2)
        },
        terminal_observation={
            "original_driver_exit_code": 1,
            "app_monitoring": True,
            "ai_ready": True,
            "viewer": {
                "found": True,
                "pid": 42,
                "visible": True,
                "minimized": False,
                "physical_rect": [0, 0, 32, 24],
            },
            "app_log_prefix_bytes": app_log.stat().st_size,
            "app_log_prefix_sha256": v.digest(app_log),
        },
    )
    plan["bindings"]["driver_sha256"] = "e" * 64
    resume_path = run / "plan-v3.json"
    write(resume_path, plan)
    return batch, resume_path, terminal, app_log, attempt


def audit(resumed):
    (v, run, manifest, live, recovery, _), plan, terminal, app_log, _ = resumed
    return v.audit(
        run,
        manifest,
        live,
        recovery,
        v.digest(run / "plan.json"),
        v.digest(run / "plan-v2.json"),
        resume_plan=plan,
        resume_sha=v.digest(plan),
        terminal=terminal,
        app_log=app_log,
    )


def test_verified_resume_keeps_failure_and_pending_counts(resumed):
    report = audit(resumed)
    assert report["counts"] == {
        "published_verified": 0,
        "published_with_recovered_collector_failure": 1,
        "technical_failure": 1,
        "pending": 1,
        "invalid_evidence": 0,
    }
    assert report["cases"][1]["preserved_by_resume_plan"] is True
    assert len(report["cases"][1]["run_ids"]) == 5
    assert not report["complete_evidence"] and not report["all_cases_terminal"]


@pytest.mark.parametrize(
    "tamper",
    [
        "link",
        "source",
        "collector",
        "roi",
        "order",
        "failure_index",
        "denominator",
        "rerun",
        "missing_prior",
        "prior_hash",
        "failure_hash",
        "terminal_hash",
        "chronology",
        "boundary",
        "idle",
        "minimized",
        "viewer_pid",
        "viewer_rect",
        "exit_code",
        "app_log",
    ],
)
def test_resume_plan_cannot_change_scope_or_silently_skip(resumed, tamper):
    (v, _, _, _, _, write), path, _, app_log, _ = resumed
    plan = v.read(path)
    if tamper == "link":
        plan["previous_plan_sha256"] = "d" * 64
    elif tamper == "source":
        plan["source_head"] = "changed"
    elif tamper == "collector":
        plan["bindings"]["collector_sha256"] = "d" * 64
    elif tamper == "roi":
        plan["bindings"]["roi"][2] += 1
    elif tamper == "order":
        plan["planned_cases"].reverse()
    elif tamper == "failure_index":
        plan["preserved_failure"]["index"] = 0
    elif tamper == "denominator":
        plan["preserved_failure"]["count_in_denominator"] = False
    elif tamper == "rerun":
        plan["preserved_failure"]["rerun"] = True
    elif tamper == "missing_prior":
        plan["prior_receipt_sha256"].pop("0")
    elif tamper == "prior_hash":
        plan["prior_receipt_sha256"]["0"] = "d" * 64
    elif tamper == "failure_hash":
        plan["preserved_failure"]["receipt_sha256"] = "d" * 64
    elif tamper == "terminal_hash":
        plan["preserved_failure"]["terminal_audit_sha256"] = "d" * 64
    elif tamper == "chronology":
        plan["started_utc"] = "2026-09-29T11:03:30+00:00"
    elif tamper == "boundary":
        plan["resume_from_index"] = True
    elif tamper == "idle":
        plan["terminal_observation"]["app_monitoring"] = False
    elif tamper == "minimized":
        plan["terminal_observation"]["viewer"]["minimized"] = True
    elif tamper == "viewer_pid":
        plan["terminal_observation"]["viewer"]["pid"] = 43
    elif tamper == "viewer_rect":
        plan["terminal_observation"]["viewer"]["physical_rect"][2] += 1
    elif tamper == "exit_code":
        plan["terminal_observation"]["original_driver_exit_code"] = 0
    elif tamper == "app_log":
        app_log.write_bytes(b"changed")
    write(path, plan)
    with pytest.raises(ValueError):
        audit(resumed)


@pytest.mark.parametrize(
    "tamper",
    [
        "source",
        "text",
        "sequence",
        "artifact",
        "log",
        "prefix",
        "missing_turn",
        "terminal_flag",
        "published",
        "failed_link",
        "public_model",
        "public_line",
    ],
)
def test_terminal_supplement_is_not_unchecked_success(resumed, tamper):
    (v, _, _, live, _, write), plan_path, terminal, _, attempt = resumed
    report = v.read(terminal)
    first = attempt / "turn-0001/receipt.json"
    if tamper == "source":
        (attempt / "source.png").write_bytes(b"changed")
    elif tamper == "text":
        (first.parent / "model-visible.txt").write_bytes(b"changed")
    elif tamper == "sequence":
        turn = v.read(first)
        turn["sequence"] = 2
        write(first, turn)
        report["retained_files"] = v.inventory(attempt)
    elif tamper == "artifact":
        (attempt / "unexpected.txt").write_bytes(b"unrecorded")
    elif tamper == "log":
        (live / "gateway.log").write_bytes(b"changed")
    elif tamper == "prefix":
        report["gateway_log_prefix_bytes"] = True
    elif tamper == "missing_turn":
        (attempt / "turn-0006").mkdir()
    elif tamper == "terminal_flag":
        turn = v.read(first)
        turn["terminal_seen"] = False
        write(first, turn)
        report["retained_files"] = v.inventory(attempt)
    elif tamper == "published":
        report["replay"]["new_publication"] = True
    elif tamper == "failed_link":
        report["original_failure_sha256"] = "d" * 64
    elif tamper == "public_model":
        report["turns"][0]["public_session_fields"]["model"] = "other"
    elif tamper == "public_line":
        report["turns"][0]["runtime_observation"]["log_line"] = 99
    write(terminal, report)
    plan = v.read(plan_path)
    plan["preserved_failure"]["terminal_audit_sha256"] = v.digest(terminal)
    write(plan_path, plan)
    with pytest.raises(ValueError):
        audit(resumed)


@pytest.mark.parametrize("mode", ["good", "wrong_plan", "early_start"])
def test_post_resume_case_binds_plan_and_time_without_erasing_failure(
    resumed, monkeypatch, mode
):
    (v, run, _, _, _, write), plan_path, _, _, _ = resumed
    folder = run / "case-002"
    folder.mkdir()
    for name in ("attempt.json", "receipt.json"):
        write(
            folder / name,
            {
                "driver_plan_sha256": "d" * 64
                if mode == "wrong_plan"
                else v.digest(plan_path)
            },
        )
    real = v.verify_case

    def verify(folder, row, index, plan, manifest, live, recovery, previous):
        if index != 2:
            return real(folder, row, index, plan, manifest, live, recovery, previous)
        start = v.timestamp(
            "2026-09-29T11:04:30+00:00"
            if mode == "early_start"
            else "2026-09-29T11:06:00+00:00"
        )
        v.require(start >= previous, "before resume plan")
        return {
            "index": index,
            "status": "published_verified",
            "session_keys": ["future-key"],
            "public_session_ids": ["future-session"],
            "run_ids": ["future-run"],
            "host_run_id": "future-host",
            "export_dir": "future-export",
            "finished_utc": "2026-09-29T11:07:00+00:00",
        }

    monkeypatch.setattr(v, "verify_case", verify)
    report = audit(resumed)
    assert report["counts"]["technical_failure"] == 1
    assert report["counts"]["invalid_evidence"] == (mode != "good")
    assert report["all_cases_terminal"] == (mode == "good")
    assert not report[
        "complete_evidence"
    ]  # Failure still exists when all cases are terminal.


def test_resume_arguments_are_all_or_none(batch):
    v, run, manifest, live, recovery, _ = batch
    with pytest.raises(ValueError, match="incomplete resume audit arguments"):
        v.audit(
            run,
            manifest,
            live,
            recovery,
            v.digest(run / "plan.json"),
            v.digest(run / "plan-v2.json"),
            resume_plan=run / "plan-v3.json",
        )
