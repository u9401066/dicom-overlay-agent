"""Offline audit of linked scientific desktop plans; never query models or gold.

This validates retained evidence, not physical-event attestation or clinical
accuracy. Independently preserve both plan hashes before their respective runs.
The special case-zero recovery is explicit and cannot hide other failures.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import stat
from datetime import datetime
from pathlib import Path

from PIL import Image


def module(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name(filename)
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


usage = module("scientific_usage_audit", "collect-scientific-desktop-usage.py")
legacy = module("desktop_pixel_audit", "verify-desktop-batch.py")
require = legacy.require
digest = legacy.digest
read = legacy.read_json
RECOVERY_ERROR = (
    "Usage binding not verified; inspect existing export, do not rerun inference"
)
REQUIRED = (legacy.REQUIRED_ARTIFACTS - {"usage-receipt.json"}) | {
    "scientific-result.json"
}


def inventory(root):
    """Exact recursive inventory, rejecting symlinks and Windows junctions."""
    root = root.resolve(strict=True)
    result = {}
    for path in root.rglob("*"):
        require(
            not path.is_symlink()
            and not getattr(path.lstat(), "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT,
            "linked artifact",
        )
        require(path.resolve(strict=True).is_relative_to(root), "artifact escape")
        if path.is_file():
            result[str(path.relative_to(root))] = digest(path)
    return result


def timestamp(value):
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, "timestamp lacks timezone")
    return result


def log_prefix(path, size, expected_sha):
    require(type(size) is int and size > 0, "invalid log prefix length")
    with path.open("rb") as stream:
        value = stream.read(size)
    require(
        len(value) == size and hashlib.sha256(value).hexdigest() == expected_sha,
        "retained log prefix changed",
    )
    return value.decode("utf-8")


def verify_failure_terminal(folder, live, path, expected_sha):
    """Recheck retained failed-turn bytes and usage, never promote to publication."""
    require(digest(path) == expected_sha, "terminal supplement changed")
    report = read(path)
    require(
        report["original_failure_sha256"] == digest(folder / "receipt.json"),
        "terminal failure link changed",
    )
    require(
        report["original_failure_preserved"] is True
        and report["model_requests"] == 0
        and report["clinical_scored"] is False,
        "unexpected terminal audit mode",
    )
    replay = report["replay"]
    require(
        replay["preflight_completed"] is True
        and replay["new_gui_handoff"] is False
        and replay["new_publication"] is False
        and replay["retained_turns_replayed"] == 5,
        "terminal audit is not a retained preflight",
    )
    matches = [
        p.parent
        for p in (live / "data/scientific-attempts").glob("*/intake.json")
        if read(p).get("source_image_sha256") == report["source_sha256"]
    ]
    require(len(matches) == 1, "failed source attempt missing or ambiguous")
    attempt = legacy.contained(matches[0], live / "data/scientific-attempts")
    files = inventory(attempt)
    require(
        files == report["retained_files"]
        and files["source.png"] == report["source_sha256"],
        "failed attempt artifacts changed",
    )
    require(
        read(attempt / "intake.json")["run_id"] == attempt.name,
        "failed host identity changed",
    )
    require(
        legacy.pixels(folder / "visible-roi.png", attempt / "source.png") == 0,
        "failed source differs from visible ROI",
    )
    turns = []
    require(
        all((p / "receipt.json").is_file() for p in attempt.glob("turn-*")),
        "incomplete failed retained turn",
    )
    for receipt in sorted(attempt.glob("turn-*/receipt.json")):
        turn = read(receipt)
        require(
            turn["sequence"] == len(turns) + 1
            and turn["image_sha256"] == report["source_sha256"],
            "failed turn source or sequence changed",
        )
        require(
            {p.name for p in receipt.parent.iterdir()}
            == {"receipt.json", *turn["artifacts"]},
            "failed turn inventory changed",
        )
        for name, expected in turn["artifacts"].items():
            require(
                Path(name).name == name and "/" not in name and "\\" not in name,
                "unsafe failed artifact",
            )
            require(
                digest(receipt.parent / name) == expected, "failed turn bytes changed"
            )
        require(
            digest(receipt.parent / "model-visible.txt") == turn["model_text_sha256"],
            "failed model text changed",
        )
        turns.append(turn)
    prefix = log_prefix(
        live / "gateway.log",
        report["gateway_log_prefix_bytes"],
        report["gateway_log_prefix_sha256"],
    )
    sessions = [
        dict(t["public_session_fields"], key=t["session_key"]) for t in report["turns"]
    ]
    require(
        len({s["sessionId"] for s in sessions}) == len(sessions),
        "reused failed public session",
    )
    require(
        usage.bind_usage(turns, sessions, prefix) == report["turns"],
        "failed usage binding changed",
    )
    require(
        inventory(attempt) == files and digest(path) == expected_sha,
        "terminal evidence changed during audit",
    )
    return {
        "host_run_id": attempt.name,
        "run_ids": [t["gateway_run_id"] for t in turns],
        "session_keys": [t["session_key"] for t in turns],
        "public_session_ids": [s["sessionId"] for s in sessions],
    }


def verify_resume(
    run, live, previous, previous_sha, path, expected_sha, terminal, app_log
):
    """One explicitly declared terminal failure can precede a new plan, not vanish."""
    require(digest(path) == expected_sha, "resume plan changed")
    resumed = read(path)
    require(resumed["previous_plan_sha256"] == previous_sha, "resume plan link changed")
    require(
        all(
            resumed[k] == value
            for k, value in previous.items()
            if k not in {"started_utc", "bindings", "changes"}
        ),
        "resume interpretation scope changed",
    )
    require(
        set(resumed["bindings"]) == set(previous["bindings"])
        and all(
            resumed["bindings"][k] == value
            for k, value in previous["bindings"].items()
            if k != "driver_sha256"
        ),
        "resume frozen bindings changed",
    )
    start = resumed["resume_from_index"]
    require(
        type(start) is int and 1 < start < len(previous["planned_cases"]),
        "invalid resume boundary",
    )
    failure = resumed["preserved_failure"]
    require(
        failure["index"] == start - 1
        and failure["status"] == "technical_failure"
        and failure["count_in_denominator"] is True
        and failure["rerun"] is False,
        "failure denominator or identity changed",
    )
    require(
        set(resumed["prior_receipt_sha256"]) == {str(i) for i in range(start)},
        "incomplete resume prefix",
    )
    for index in range(start):
        receipt = run / f"case-{index:03d}/receipt.json"
        require(
            digest(receipt) == resumed["prior_receipt_sha256"][str(index)],
            "prior receipt changed",
        )
        if index not in {0, start - 1}:
            require(
                read(receipt)["status"] == "exported_verified",
                "undeclared earlier failure",
            )
    folder = run / f"case-{start - 1:03d}"
    failed = read(folder / "receipt.json")
    require(
        digest(folder / "receipt.json") == failure["receipt_sha256"]
        and failed["status"] == "technical_failure",
        "declared failure changed",
    )
    require(
        timestamp(previous["started_utc"])
        <= timestamp(failed["finished_utc"])
        <= timestamp(resumed["started_utc"]),
        "resume predates failure termination",
    )
    observed = resumed["terminal_observation"]
    require(
        observed["original_driver_exit_code"] == 1
        and observed["app_monitoring"] is True
        and observed["ai_ready"] is True,
        "missing idle terminal observation",
    )
    left, top, width, height = previous["bindings"]["roi"]
    require(
        observed["viewer"]
        == {
            "found": True,
            "pid": previous["bindings"]["viewer_pid"],
            "visible": True,
            "minimized": False,
            "physical_rect": [left, top, left + width, top + height],
        },
        "resume viewer observation mismatch",
    )
    prefix = log_prefix(
        app_log, observed["app_log_prefix_bytes"], observed["app_log_prefix_sha256"]
    )
    states = [
        line.rsplit("State: ", 1)[1].strip()
        for line in prefix.splitlines()
        if "State: " in line
    ]
    require(
        bool(states)
        and states[-1] == "WAITING → MONITORING"
        and "ANALYZING → WAITING" in states,
        "terminal App log sequence missing",
    )
    identities = verify_failure_terminal(
        folder, live, terminal, failure["terminal_audit_sha256"]
    )
    require(digest(path) == expected_sha, "resume plan changed during audit")
    return resumed, identities


def verify_usage(export, live, receipt_path, expected_hash, collector_hash):
    require(digest(receipt_path) == expected_hash, "usage receipt changed")
    record = read(receipt_path)
    require(
        record["receipt_version"] == "scientific-desktop-usage-v1",
        "unknown usage version",
    )
    require(record["collector_sha256"] == collector_hash, "collector identity changed")
    require(
        record["model_requests"] == 0 and record["source_results_mutated"] is False,
        "collector execution mode changed",
    )
    require(
        record["all_turns_verified_astra_medium"] is True, "unverified model profile"
    )
    files = inventory(export)
    require(set(files) >= REQUIRED, "missing required export")
    require(files == record["source_export_sha256"], "recursive export changed")
    turns, binding = usage.inspect_export(export, live)
    require(all(record[k] == v for k, v in binding.items()), "retained binding changed")
    size = record["gateway_log_prefix_bytes"]
    require(type(size) is int and size > 0, "invalid log prefix length")
    with (live / "gateway.log").open("rb") as stream:
        prefix = stream.read(size)
    require(
        len(prefix) == size
        and hashlib.sha256(prefix).hexdigest() == record["gateway_log_prefix_sha256"],
        "gateway log prefix changed",
    )
    sessions = [
        dict(t["public_session_fields"], key=t["session_key"]) for t in record["turns"]
    ]
    require(
        len({s["sessionId"] for s in sessions}) == len(sessions),
        "reused public session identity",
    )
    require(
        usage.bind_usage(turns, sessions, prefix.decode("utf-8")) == record["turns"],
        "recorded usage binding changed",
    )
    require(
        inventory(export) == files
        and usage.inspect_export(export, live) == (turns, binding),
        "evidence changed during audit",
    )
    require(digest(receipt_path) == expected_hash, "usage changed during audit")
    return record


def verify_case(folder, row, index, plan, manifest, live, recovery, previous_finish):
    receipt_path = folder / "receipt.json"
    frozen = {p: digest(p) for p in (receipt_path, folder / "attempt.json")}
    receipt, attempt = read(receipt_path), read(folder / "attempt.json")
    for record in (receipt, attempt):
        require(
            record["index"] == index and record["case_id"] == row["label"],
            "case identity changed",
        )
        require(
            record["input_sha256"] == plan["planned_cases"][index]["image_sha256"],
            "case input changed",
        )
        require(
            record["actual_gui"] is True
            and record["gold_read"] is False
            and record["direct_model_requests"] == 0,
            "case execution mode changed",
        )
    require(receipt["started_utc"] == attempt["started_utc"], "attempt start changed")
    start, finish = (
        timestamp(receipt["started_utc"]),
        timestamp(receipt["finished_utc"]),
    )
    require(previous_finish <= start <= finish, "overlapping or reversed chronology")
    if index > 0 and receipt["status"] == "technical_failure":
        require(
            all(digest(p) == sha for p, sha in frozen.items()),
            "failure changed during audit",
        )
        return {
            "index": index,
            "status": "technical_failure",
            "original_status": receipt["status"],
            "receipt_sha256": frozen[receipt_path],
            "finished_utc": finish.isoformat(),
        }
    frozen[folder / "visible-roi.png"] = digest(folder / "visible-roi.png")
    recovered = index == 0
    if recovered:
        require(
            digest(receipt_path) == plan["retained_case0_failure_sha256"],
            "original failure changed",
        )
        require(
            receipt["status"] == "technical_failure"
            and receipt.get("error") == RECOVERY_ERROR,
            "not the declared collector failure",
        )
        usage_path, expected_hash = recovery, plan["case0_usage_recovery_sha256"]
    else:
        require(
            receipt["status"] == "exported_verified", "unrecovered technical failure"
        )
        usage_path, expected_hash = (
            folder / "scientific-usage-receipt.json",
            receipt["scientific_usage_sha256"],
        )
    export = legacy.contained(Path(receipt["export_dir"]), live / "data/exports")
    require(
        export != (live / "data/exports").resolve(), "export is not a case directory"
    )
    verified = verify_usage(
        export, live, usage_path, expected_hash, plan["bindings"]["collector_sha256"]
    )
    require(
        receipt["scientific_contract_sha256"] == verified["scientific_contract_sha256"],
        "contract receipt changed",
    )
    if not recovered:
        require(
            receipt["recursive_artifact_sha256"] == verified["source_export_sha256"],
            "case inventory changed",
        )
        require(
            receipt["artifact_sha256"]
            == {p.name: digest(p) for p in export.iterdir() if p.is_file()},
            "top-level inventory changed",
        )
    source = (manifest.parent / row["image"]).resolve(strict=True)
    file_mae = legacy.pixels(source, folder / "visible-roi.png", resize=True)
    require(file_mae < 2, "visible image differs from input")
    require(
        legacy.pixels(folder / "visible-roi.png", export / "source.png") == 0,
        "captured source differs",
    )
    require(
        abs(receipt["file_to_visible_bilinear_mae"] - file_mae) < 1e-8
        and receipt["visible_to_export_mae"] == 0,
        "recorded pixel comparison changed",
    )
    with Image.open(export / "source.png") as image:
        size = list(image.size)
    projection, ui = read(export / "result.json"), read(export / "ui-capture.json")
    require(size == plan["bindings"]["roi"][2:], "ROI size changed")
    require(
        [
            projection["source_image"]["width_px"],
            projection["source_image"]["height_px"],
        ]
        == size
        and projection["coordinate_space"] == "normalized_original_roi",
        "projection geometry changed",
    )
    require(
        ui["method"] == "app_owned_widget_render"
        and ui["desktop_background_captured"] is False
        and ui["capture_exclusion_disabled"] is False,
        "UI capture privacy mismatch",
    )
    require(
        all(digest(p) == sha for p, sha in frozen.items()), "case changed during audit"
    )
    return {
        "index": index,
        "status": "published_with_recovered_collector_failure"
        if recovered
        else "published_verified",
        "original_status": receipt["status"],
        "receipt_sha256": frozen[receipt_path],
        "usage_sha256": expected_hash,
        "scientific_contract_sha256": verified["scientific_contract_sha256"],
        "export_dir": str(export),
        "session_keys": [t["session_key"] for t in verified["turns"]],
        "public_session_ids": [
            t["public_session_fields"]["sessionId"] for t in verified["turns"]
        ],
        "host_run_id": verified["host_run_id"],
        "run_ids": [t["run_id"] for t in verified["turns"]],
        "finished_utc": finish.isoformat(),
    }


def audit(
    run,
    manifest,
    live,
    recovery,
    original_sha,
    continuation_sha,
    *,
    resume_plan=None,
    resume_sha=None,
    terminal=None,
    app_log=None,
):
    original_path, continuation_path = run / "plan.json", run / "plan-v2.json"
    require(digest(original_path) == original_sha, "original plan changed")
    require(digest(continuation_path) == continuation_sha, "continuation plan changed")
    original, plan = read(original_path), read(continuation_path)
    resume_options = (resume_plan, resume_sha, terminal, app_log)
    require(
        all(v is None for v in resume_options)
        or all(v is not None for v in resume_options),
        "incomplete resume audit arguments",
    )
    resumed, failed_identities = (None, None)
    if resume_plan is not None:
        resumed, failed_identities = verify_resume(
            run,
            live,
            plan,
            continuation_sha,
            resume_plan,
            resume_sha,
            terminal,
            app_log,
        )
    require(plan["original_plan_sha256"] == original_sha, "plan link changed")
    require(
        plan["source_head"] == original["source_head"], "source changed between plans"
    )
    require(
        set(plan["bindings"]) == set(original["bindings"]),
        "plan binding inventory changed",
    )
    require(
        all(
            v == original["bindings"][k]
            for k, v in plan["bindings"].items()
            if k not in {"driver_sha256", "collector_sha256"}
        ),
        "frozen bindings changed",
    )
    for entry in (original, plan):
        require(
            entry["expected_model"] == "gpt-6-astra"
            and entry["reasoning"] == "medium"
            and entry["actual_gui_required"] is True
            and entry["gold_read"] is False
            and entry["scientific_review"] is True,
            "unexpected plan execution mode",
        )
    require(
        digest(manifest) == plan["bindings"]["inference_sha256"],
        "inference manifest changed",
    )
    payload = read(manifest)
    require(
        payload["selection"]["manifest_role"] == "inference",
        "not an inference manifest",
    )
    rows = payload["cases"]
    records = [
        {
            "case_identity": r["label"],
            "image_sha256": digest((manifest.parent / r["image"]).resolve(strict=True)),
        }
        for r in rows
    ]
    require(
        bool(records) and records == original["planned_cases"] == plan["planned_cases"],
        "planned input order changed",
    )
    require(
        len({r["case_identity"] for r in records}) == len(records)
        and len({r["image_sha256"] for r in records}) == len(records),
        "duplicate cohort identity",
    )
    require(
        legacy.canonical_digest(records)
        == payload["selection"]["input_image_order_sha256"]
        == plan["bindings"]["input_image_order_sha256"],
        "input order digest changed",
    )
    require(payload["counts"]["cases"] == len(rows), "manifest count mismatch")
    require(
        timestamp(original["started_utc"]) <= timestamp(plan["started_utc"]),
        "plan chronology reversed",
    )
    expected_folders = {f"case-{i:03d}" for i in range(len(rows))}
    require(
        {p.name for p in run.glob("case-*")} <= expected_folders,
        "unexpected case directory",
    )
    # Fix the receipt set at observation time; a live new receipt remains pending
    # for this audit and is picked up on the next invocation, never a rerun cue.
    observed = {
        i for i in range(len(rows)) if (run / f"case-{i:03d}/receipt.json").is_file()
    }
    cases, sessions, runs, exports = [], set(), set(), set()
    public_sessions, host_runs = set(), set()
    previous = timestamp(original["started_utc"])
    gap = False
    for index, row in enumerate(rows):
        if index not in observed:
            cases.append({"index": index, "status": "pending"})
            gap = True
            continue
        try:
            require(not gap, "terminal case after unresolved gap")
            if index:
                previous = max(previous, timestamp(plan["started_utc"]))
            if resumed and index >= resumed["resume_from_index"]:
                previous = max(previous, timestamp(resumed["started_utc"]))
                for name in ("attempt.json", "receipt.json"):
                    require(
                        read(run / f"case-{index:03d}" / name)["driver_plan_sha256"]
                        == resume_sha,
                        "resumed case plan binding changed",
                    )
            result = verify_case(
                run / f"case-{index:03d}",
                row,
                index,
                plan,
                manifest,
                live,
                recovery,
                previous,
            )
            if result["status"] == "technical_failure":
                declared = resumed and index == resumed["preserved_failure"]["index"]
                if declared:
                    failed_folder = run / f"case-{index:03d}"
                    source = (manifest.parent / row["image"]).resolve(strict=True)
                    measured = legacy.pixels(
                        source, failed_folder / "visible-roi.png", resize=True
                    )
                    failure_receipt = read(failed_folder / "receipt.json")
                    require(
                        measured < 2
                        and abs(
                            failure_receipt["file_to_visible_bilinear_mae"] - measured
                        )
                        < 1e-8,
                        "failed visible input binding changed",
                    )
                    with Image.open(failed_folder / "visible-roi.png") as captured:
                        require(
                            list(captured.size) == plan["bindings"]["roi"][2:],
                            "failed ROI size changed",
                        )
                    require(
                        not sessions.intersection(failed_identities["session_keys"])
                        and not runs.intersection(failed_identities["run_ids"])
                        and not public_sessions.intersection(
                            failed_identities["public_session_ids"]
                        )
                        and failed_identities["host_run_id"] not in host_runs,
                        "reused failed case identity",
                    )
                    sessions.update(failed_identities["session_keys"])
                    runs.update(failed_identities["run_ids"])
                    public_sessions.update(failed_identities["public_session_ids"])
                    host_runs.add(failed_identities["host_run_id"])
                    result.update(
                        failed_identities,
                        preserved_by_resume_plan=True,
                        terminal_audit_sha256=resumed["preserved_failure"][
                            "terminal_audit_sha256"
                        ],
                    )
                    previous = timestamp(result["finished_utc"])
                cases.append(result)
                gap = not declared
                continue
            require(
                not sessions.intersection(result["session_keys"])
                and not public_sessions.intersection(result["public_session_ids"])
                and result["host_run_id"] not in host_runs
                and not runs.intersection(result["run_ids"])
                and result["export_dir"] not in exports,
                "reused cross-case evidence",
            )
            sessions.update(result["session_keys"])
            public_sessions.update(result["public_session_ids"])
            host_runs.add(result["host_run_id"])
            runs.update(result["run_ids"])
            exports.add(result["export_dir"])
            previous = timestamp(result["finished_utc"])
            if index == 0:
                require(
                    previous <= timestamp(plan["started_utc"]),
                    "recovery plan predates original failure",
                )
            cases.append(result)
        except (ValueError, KeyError, OSError, TypeError):
            # Do not echo arbitrary retained clinical text, filenames or errors.
            cases.append({"index": index, "status": "invalid_evidence"})
            gap = True
    require(
        digest(original_path) == original_sha
        and digest(continuation_path) == continuation_sha
        and digest(manifest) == plan["bindings"]["inference_sha256"],
        "plan changed during audit",
    )
    if resumed:
        require(digest(resume_plan) == resume_sha, "resume plan changed during audit")
    counts = {
        status: sum(c["status"] == status for c in cases)
        for status in (
            "published_verified",
            "published_with_recovered_collector_failure",
            "pending",
            "technical_failure",
            "invalid_evidence",
        )
    }
    return {
        "audit_version": "scientific-desktop-batch-v1",
        "audit_code_sha256": {
            Path(p).name: digest(Path(p))
            for p in (__file__, usage.__file__, legacy.__file__)
        },
        "plan_sha256": original_sha,
        "continuation_plan_sha256": continuation_sha,
        "resume_plan_sha256": resume_sha,
        "planned": len(rows),
        "counts": counts,
        "complete_evidence": counts["pending"]
        == counts["invalid_evidence"]
        == counts["technical_failure"]
        == 0,
        "clinical_scored": False,
        "all_cases_terminal": counts["pending"] == counts["invalid_evidence"] == 0,
        "gold_read": False,
        "model_requests": 0,
        "cases": cases,
        "limitations": [
            "Local evidence integrity, not independent physical-input attestation or clinical correctness.",
            "Public session fields are retained collector snapshots, not independently re-queried or signed.",
            "Frozen source/config identities are compared between plans, not a current installed-binary attestation.",
            "Previously exposed paired regression; not fresh blind or patient-independent accuracy.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "manifest", "live", "recovery", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--original-sha256", required=True)
    parser.add_argument("--continuation-sha256", required=True)
    parser.add_argument("--resume-plan", type=Path)
    parser.add_argument("--resume-sha256")
    parser.add_argument("--terminal-audit", type=Path)
    parser.add_argument("--app-log", type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), "output already exists")
    require(
        all(
            not args.output.resolve().is_relative_to(p.resolve())
            for p in (args.run, args.live, args.manifest.parent)
        ),
        "output must be outside primary evidence trees",
    )
    report = audit(
        args.run,
        args.manifest,
        args.live,
        args.recovery,
        args.original_sha256,
        args.continuation_sha256,
        resume_plan=args.resume_plan,
        resume_sha=args.resume_sha256,
        terminal=args.terminal_audit,
        app_log=args.app_log,
    )
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("planned", "counts", "complete_evidence", "clinical_scored")
            }
        )
    )
    return (
        1
        if report["counts"]["invalid_evidence"] or report["counts"]["technical_failure"]
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
