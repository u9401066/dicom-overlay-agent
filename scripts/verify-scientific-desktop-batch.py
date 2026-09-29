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


def audit(run, manifest, live, recovery, original_sha, continuation_sha):
    original_path, continuation_path = run / "plan.json", run / "plan-v2.json"
    require(digest(original_path) == original_sha, "original plan changed")
    require(digest(continuation_path) == continuation_sha, "continuation plan changed")
    original, plan = read(original_path), read(continuation_path)
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
                cases.append(result)
                gap = True
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
        "planned": len(rows),
        "counts": counts,
        "complete_evidence": counts["pending"]
        == counts["invalid_evidence"]
        == counts["technical_failure"]
        == 0,
        "clinical_scored": False,
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
