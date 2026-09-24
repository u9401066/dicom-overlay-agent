"""Read-only audit of frozen native-GUI batch evidence; never read clinical gold.

This verifies recorded evidence, not physical input events or clinical accuracy.
The caller must preserve the plan digest independently before running the batch.
No GUI, model, session-query or inference calls are made here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

REQUIRED_ARTIFACTS = {
    "source.png",
    "result.json",
    "usage-receipt.json",
    "ui-capture.json",
    "summary-panel.png",
    "overlay-layer.png",
    "control-bar.png",
    "review.png",
    "bbox-audit.json",
    "regional-conversations.json",
}
RUNTIME = re.compile(
    r"embedded run start: runId=(\S+) sessionId=(\S+) provider=(\S+) "
    r"model=(\S+) thinking=(\S+)"
)


class AuditError(ValueError):
    """A PHI-free invariant failure suitable for the audit report."""


def require(condition, message):
    if not condition:
        raise AuditError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def contained(path, root):
    resolved = path.resolve()
    require(resolved.is_relative_to(root.resolve()), "artifact outside permitted root")
    return resolved


def pixels(left, right, *, resize=False):
    with Image.open(left) as first, Image.open(right) as second:
        first, second = first.convert("RGB"), second.convert("RGB")
        if resize:
            first = first.resize(second.size, Image.Resampling.BILINEAR)
        require(first.size == second.size, "image dimensions differ")
        return sum(ImageStat.Stat(ImageChops.difference(first, second)).mean) / 3


def identity_matches(expected_run, expected_session, observed_run, observed_session):
    def masked(observed, expected):
        prefix = observed[:-3]
        return (
            observed.endswith("***")
            and "*" not in prefix
            and len(prefix) >= 16
            and expected.startswith(prefix)
        )

    return (
        (observed_run == expected_run and observed_session == expected_session)
        or (observed_session == expected_session and masked(observed_run, expected_run))
        or (observed_run == expected_run and masked(observed_session, expected_session))
    )


def verify_usage(result, result_digest, usage, observations, model, effort):
    require(
        usage["source_result_sha256"] == result_digest, "usage result hash mismatch"
    )
    require(usage["model_requests"] == 0, "collector made model requests")
    require(usage["source_results_mutated"] is False, "collector mutated results")
    expected = {}
    for stage in result["analysis_trace"]:
        events = [("stage", stage)] + [
            (f"attempt-{i + 1}", event)
            for i, event in enumerate(stage.get("attempts", []))
        ]
        for position, event in events:
            if not event.get("session_key") and not event.get("run_id"):
                continue
            require(
                bool(event.get("session_key") and event.get("run_id")),
                "partial trace identity",
            )
            key = "agent:main:" + event["session_key"]
            require(key not in expected, "duplicate trace identity")
            expected[key] = (event["run_id"], stage["stage"], position)
    turns = usage["turns"]
    require(bool(expected), "no model trace identities")
    require(len(turns) == len(expected), "usage does not cover every trace attempt")
    require(
        {t["session_key"] for t in turns} == set(expected), "usage identity mismatch"
    )
    for turn in turns:
        require(
            (turn["run_id"], turn["stage"], turn["position"])
            == expected[turn["session_key"]],
            "usage stage binding mismatch",
        )
        require(turn["usage_found"] is True, "missing public usage")
        public, recorded = turn["public_session_fields"], turn["runtime_observation"]
        require(
            isinstance(public, dict) and isinstance(recorded, dict),
            "missing runtime/public receipt",
        )
        require(
            public["model"] == model and public["modelProvider"] == "openai",
            "unexpected public model/provider",
        )
        require(public.get("totalTokensFresh") is True, "stale public token snapshot")
        for field in ("inputTokens", "outputTokens", "totalTokens"):
            require(
                type(public.get(field)) is int and public[field] >= 0,
                "unknown public token count",
            )
        matches = [
            o
            for o in observations
            if o["provider"] == "openai"
            and o["model"] == model
            and identity_matches(
                turn["run_id"], public["sessionId"], o["run_id"], o["session_id"]
            )
        ]
        require(len(matches) == 1, "runtime identity missing or ambiguous")
        observed = matches[0]
        require(observed["reasoning_effort"] == effort, "unexpected reasoning effort")
        require(
            all(recorded.get(k) == v for k, v in observed.items()),
            "recorded runtime differs from original log",
        )
    return len(turns)


def verify_case(case_dir, row, index, plan, manifest, exports_root, observations):
    receipt_path = contained(case_dir / "receipt.json", case_dir.parent)
    before = digest(receipt_path)
    receipt = read_json(receipt_path)
    attempt = read_json(contained(case_dir / "attempt.json", case_dir.parent))
    for record in (receipt, attempt):
        require(
            record["index"] == index and record["case_id"] == row["label"],
            "case identity/order mismatch",
        )
        require(
            record["input_sha256"] == plan["planned_cases"][index]["image_sha256"],
            "case source hash mismatch",
        )
        require(
            record["actual_gui"] is True
            and record["gold_read"] is False
            and record["direct_model_requests"] == 0,
            "wrong recorded execution mode",
        )
    require(receipt["started_utc"] == attempt["started_utc"], "attempt start changed")
    start, finish = (
        datetime.fromisoformat(receipt[k]) for k in ("started_utc", "finished_utc")
    )
    require(
        start.tzinfo is not None and finish.tzinfo is not None and finish >= start,
        "invalid attempt chronology",
    )
    if receipt["status"] == "technical_failure":
        return {"index": index, "status": "technical_failure"}
    require(receipt["status"] == "exported_verified", "unknown terminal status")
    export = contained(Path(receipt["export_dir"]), exports_root)
    require(export != exports_root.resolve(), "export must be a case directory")
    artifacts = receipt["artifact_sha256"]
    require(set(artifacts) >= REQUIRED_ARTIFACTS, "missing required artifact hashes")
    actual_files = {p.name for p in export.iterdir() if p.is_file()}
    require(set(artifacts) == actual_files, "export file inventory changed")
    for name, expected in artifacts.items():
        require(
            Path(name).name == name and "/" not in name and "\\" not in name,
            "unsafe artifact name",
        )
        path = contained(export / name, export)
        require(digest(path) == expected, "artifact hash mismatch")
    visible = contained(case_dir / "visible-roi.png", case_dir.parent)
    source = (manifest.parent / row["image"]).resolve()
    file_mae = pixels(source, visible, resize=True)
    export_mae = pixels(visible, export / "source.png")
    require(file_mae < 2, "visible image differs from intended file")
    require(export_mae == 0, "export differs from pre-analysis visible image")
    result = read_json(export / "result.json")
    with Image.open(export / "source.png") as image:
        size = list(image.size)
    require(size == plan["bindings"]["roi"][2:], "export differs from planned ROI size")
    require(
        result["source_image"]["sha256"] == artifacts["source.png"],
        "result source binding mismatch",
    )
    require(
        [result["source_image"]["width_px"], result["source_image"]["height_px"]]
        == size,
        "result source dimensions mismatch",
    )
    require(
        result["coordinate_space"] == "normalized_original_roi",
        "unexpected coordinate space",
    )
    ui = read_json(export / "ui-capture.json")
    require(
        ui["method"] == "app_owned_widget_render"
        and ui["desktop_background_captured"] is False
        and ui["capture_exclusion_disabled"] is False,
        "unexpected UI capture method",
    )
    usage = read_json(export / "usage-receipt.json")
    turns = verify_usage(
        result,
        artifacts["result.json"],
        usage,
        observations,
        plan["expected_model"],
        plan["reasoning"],
    )
    require(digest(receipt_path) == before, "receipt changed during audit")
    return {
        "index": index,
        "status": "verified",
        "export_identity": str(export),
        "session_identities": [
            t["public_session_fields"]["sessionId"] for t in usage["turns"]
        ],
        "file_to_visible_mae": file_mae,
        "visible_to_export_mae": export_mae,
        "model_turns": turns,
        "started_utc": start.isoformat(),
        "finished_utc": finish.isoformat(),
    }


def audit(run, manifest, exports_root, gateway_log, plan_sha256, *, expected_cases=120):
    plan_path = contained(run / "plan.json", run)
    require(digest(plan_path) == plan_sha256, "frozen plan digest mismatch")
    plan = read_json(plan_path)
    require(
        plan["actual_gui_required"] is True and plan["gold_read"] is False,
        "invalid planned execution mode",
    )
    require(
        plan["expected_model"] == "gpt-6-astra" and plan["reasoning"] == "medium",
        "unexpected planned model profile",
    )
    bindings = plan["bindings"]
    require(
        all(
            type(bindings[k]) is int and bindings[k] > 0
            for k in ("app_pid", "viewer_pid")
        ),
        "missing recorded process ownership",
    )
    roi = bindings["roi"]
    require(
        len(roi) == 4
        and all(type(x) is int for x in roi)
        and all(x > 0 for x in roi[2:]),
        "invalid planned ROI",
    )
    require(
        digest(manifest) == bindings["inference_sha256"], "inference manifest changed"
    )
    payload = read_json(manifest)
    cases = payload["cases"]
    require(len(cases) == expected_cases and bool(cases), "wrong planned denominator")
    records = [
        {
            "case_identity": row["label"],
            "image_sha256": digest((manifest.parent / row["image"]).resolve()),
        }
        for row in cases
    ]
    require(
        len({r["case_identity"] for r in records}) == len(records), "duplicate case IDs"
    )
    require(
        len({r["image_sha256"] for r in records}) == len(records),
        "duplicate source images",
    )
    require(records == plan["planned_cases"], "ordered source image binding mismatch")
    require(
        canonical_digest(records)
        == bindings["input_image_order_sha256"]
        == payload["selection"]["input_image_order_sha256"],
        "input order digest mismatch",
    )
    observations = []
    for number, line in enumerate(
        gateway_log.read_text(encoding="utf-8").splitlines(), 1
    ):
        match = RUNTIME.search(line)
        if match:
            observations.append(
                dict(
                    zip(
                        (
                            "run_id",
                            "session_id",
                            "provider",
                            "model",
                            "reasoning_effort",
                        ),
                        match.groups(),
                        strict=True,
                    ),
                    log_line=number,
                )
            )
    allowed_dirs = {f"case-{i:03d}" for i in range(len(cases))}
    require(
        all(p.name in allowed_dirs for p in run.glob("case-*")),
        "unexpected case directory",
    )
    outcomes, used_exports, previous_finish = [], set(), None
    used_sessions = set()
    pending_seen = False
    for index, row in enumerate(cases):
        case_dir = contained(run / f"case-{index:03d}", run)
        if not (case_dir / "receipt.json").is_file():
            outcomes.append({"index": index, "status": "pending"})
            pending_seen = True
            continue
        try:
            require(not pending_seen, "terminal case after unresolved order gap")
            outcome = verify_case(
                case_dir, row, index, plan, manifest, exports_root, observations
            )
            if outcome["status"] == "verified":
                export = outcome.pop("export_identity")
                require(export not in used_exports, "duplicate export reused")
                used_exports.add(export)
                sessions = outcome.pop("session_identities")
                require(
                    len(set(sessions)) == len(sessions)
                    and not used_sessions.intersection(sessions),
                    "model session reused across distinct input turns",
                )
                used_sessions.update(sessions)
                started = datetime.fromisoformat(outcome["started_utc"])
                require(
                    previous_finish is None or started >= previous_finish,
                    "overlapping sequential GUI attempts",
                )
                previous_finish = datetime.fromisoformat(outcome["finished_utc"])
            else:
                pending_seen = True
            outcomes.append(outcome)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            pending_seen = True
            outcomes.append(
                {
                    "index": index,
                    "status": "invalid",
                    "error": str(exc)
                    if isinstance(exc, AuditError)
                    else type(exc).__name__,
                }
            )
    counts = {
        s: sum(r["status"] == s for r in outcomes)
        for s in ("verified", "pending", "technical_failure", "invalid")
    }
    return {
        "planned": len(cases),
        **counts,
        "complete": counts["verified"] == len(cases),
        "clinical_scored": False,
        "canonical_ledger_validated": False,
        "plan_sha256": plan_sha256,
        "cases": outcomes,
        "limits": [
            "Recorded GUI evidence is not an independent input-event observer.",
            "Code/config ownership hashes are frozen provenance, not reattested here.",
            "Public token snapshots are not a monetary billing ledger.",
            "Only recorded top-level export files are hashed; crop subdirectories are not sealed.",
            "Pending includes live attempts; never restart inference on audit failure.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "manifest", "exports-root", "gateway-log"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = audit(
            args.run,
            args.manifest,
            args.exports_root,
            args.gateway_log,
            args.plan_sha256,
        )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(
            json.dumps(
                {
                    "complete": False,
                    "error": str(exc)
                    if isinstance(exc, AuditError)
                    else type(exc).__name__,
                }
            )
        )
        return 1
    print(json.dumps(report, indent=2))
    healthy = not report["invalid"] and not report["technical_failure"]
    return 0 if healthy and (report["complete"] or args.allow_partial) else 1


if __name__ == "__main__":
    raise SystemExit(main())
