"""Bind retained scientific turns to public sessions; never send inference.

The legacy projection's analysis_trace is not the scientific turn ledger. Read
the source-bound scientific attempt instead. Output is create-only; a previous
failed legacy receipt is never repaired or overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from medical_image_harness.schema import validate_payload

STAGES = (
    "quality_gate",
    "blind_pass",
    "independent_evidence",
    "reconcile",
    "targeted_second_look",
)
HOST = re.compile(r"\brun=([0-9a-f]{32}); source_sha256=([0-9a-f]{64});")
RUNTIME = re.compile(
    r"embedded run start: runId=(\S+) sessionId=(\S+) provider=(\S+) "
    r"model=(\S+) thinking=(\S+)"
)


def require(condition, category):
    if not condition:
        raise ValueError(category)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text("utf-8"))


def bind_usage(turns, sessions, log_text):
    """Pure identity binding; counts are snapshots, never a monetary bill."""
    require([t["stage"] for t in turns] == list(STAGES), "unexpected_turn_coverage")
    require(len({t["session_key"] for t in turns}) == len(turns), "reused_session")
    require(len({t["gateway_run_id"] for t in turns}) == len(turns), "reused_run")
    runtime = []
    for line_number, line in enumerate(log_text.splitlines(), 1):
        match = RUNTIME.search(line)
        if match:
            runtime.append(
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
                    log_line=line_number,
                )
            )
    bound = []
    for turn in turns:
        require(
            turn["terminal_seen"] is True and not turn["transport_failure"],
            "unfinished_turn",
        )
        candidates = [s for s in sessions if s["key"] == turn["session_key"]]
        require(len(candidates) == 1, "missing_or_duplicate_public_session")
        public = candidates[0]
        require(
            public.get("model") == "gpt-6-astra"
            and public.get("modelProvider") == "openai",
            "unexpected_public_model",
        )
        require(public.get("totalTokensFresh") is True, "stale_public_usage")
        for key in ("inputTokens", "outputTokens", "totalTokens"):
            require(
                type(public.get(key)) is int and public[key] >= 0, "unknown_token_count"
            )
        matches = [
            r
            for r in runtime
            if r["run_id"] == turn["gateway_run_id"]
            and r["session_id"] == public.get("sessionId")
        ]
        require(len(matches) == 1, "missing_or_duplicate_runtime_identity")
        actual = matches[0]
        require(
            actual["provider"] == "openai"
            and actual["model"] == "gpt-6-astra"
            and actual["reasoning_effort"] == "medium",
            "unexpected_runtime_profile",
        )
        bound.append(
            {
                "stage": turn["stage"],
                "session_key": turn["session_key"],
                "run_id": turn["gateway_run_id"],
                "model_text_sha256": turn["model_text_sha256"],
                "runtime_observation": actual,
                "public_session_fields": {
                    k: public.get(k)
                    for k in (
                        "sessionId",
                        "model",
                        "modelProvider",
                        "inputTokens",
                        "outputTokens",
                        "totalTokens",
                        "totalTokensFresh",
                        "cacheRead",
                        "cacheWrite",
                    )
                },
            }
        )
    return bound


def inspect_export(export, live):
    export, live = export.resolve(strict=True), live.resolve(strict=True)
    require(export.is_relative_to(live / "data/exports"), "export_outside_runtime")
    canonical_path = export / "scientific-result.json"
    canonical = read(canonical_path)
    try:
        validate_payload(canonical)
    except ValueError:
        raise ValueError("invalid_scientific_contract") from None
    source_sha = digest(export / "source.png")
    projection = read(export / "result.json")
    require(
        projection.get("scientific_contract") == "scientific-result.json"
        and projection["source_image"]["sha256"] == source_sha,
        "projection_source_or_contract_mismatch",
    )
    require(
        canonical["input_provenance"]["source_image_sha256"] == source_sha,
        "canonical_source_mismatch",
    )
    bindings = [HOST.search(e["detail"]) for e in canonical["analysis_trace"]]
    require(bool(bindings) and all(bindings), "missing_host_run_binding")
    identities = {b.group(1) for b in bindings}
    require(
        len(identities) == 1 and all(b.group(2) == source_sha for b in bindings),
        "ambiguous_host_run_binding",
    )
    attempt = live / "data/scientific-attempts" / next(iter(identities))
    require(
        attempt.resolve(strict=True).is_relative_to(live / "data/scientific-attempts"),
        "attempt_escape",
    )
    intake = read(attempt / "intake.json")
    require(
        intake["run_id"] in identities
        and intake["source_image_sha256"] == source_sha
        and digest(attempt / "source.png") == source_sha,
        "attempt_source_mismatch",
    )
    turns, receipt_hashes = [], {}
    require(
        all((p / "receipt.json").is_file() for p in attempt.glob("turn-*")),
        "incomplete_retained_turn",
    )
    for path in sorted(attempt.glob("turn-*/receipt.json")):
        turn = read(path)
        require(
            turn["sequence"] == len(turns) + 1 and turn["image_sha256"] == source_sha,
            "turn_source_or_sequence_mismatch",
        )
        for name, expected in turn["artifacts"].items():
            require(
                Path(name).name == name and "/" not in name and "\\" not in name,
                "unsafe_artifact_name",
            )
            artifact = path.parent / name
            require(
                artifact.resolve(strict=True).is_relative_to(attempt.resolve()),
                "artifact_escape",
            )
            require(digest(artifact) == expected, "turn_artifact_changed")
        require(
            digest(path.parent / "model-visible.txt") == turn["model_text_sha256"],
            "model_text_changed",
        )
        require(
            {p.name for p in path.parent.iterdir()}
            == {"receipt.json", *turn["artifacts"]},
            "turn_inventory_changed",
        )
        turns.append(turn)
        receipt_hashes[str(path.relative_to(live))] = digest(path)
    return turns, {
        "source_image_sha256": source_sha,
        "scientific_contract_sha256": digest(canonical_path),
        "host_run_id": next(iter(identities)),
        "turn_receipt_sha256": receipt_hashes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--live", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), "output_already_exists")
    require(
        not args.output.resolve().is_relative_to(args.live.resolve()),
        "output_must_be_outside_runtime",
    )
    turns, evidence = inspect_export(args.export, args.live)
    before = {p: digest(p) for p in args.export.rglob("*") if p.is_file()}
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.endswith("_API_KEY") and not k.startswith("OPENCLAW_")
    }
    env["OPENCLAW_STATE_DIR"] = str(args.live.resolve() / "openclaw-home")
    env["OPENCLAW_CONFIG_PATH"] = str(args.live.resolve() / "openclaw/openclaw.json")
    command = [
        str(args.live.resolve() / "node/node.exe"),
        str(args.live.resolve() / "openclaw/node_modules/openclaw/openclaw.mjs"),
        "sessions",
        "--agent",
        "main",
        "--active",
        "120",
        "--limit",
        "512",
        "--json",
    ]
    result = subprocess.run(
        command,
        env=env,
        cwd=args.live,
        capture_output=True,
        timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    require(result.returncode == 0, "public_session_query_failed")
    sessions = json.loads(result.stdout)["sessions"]
    log_bytes = (args.live / "gateway.log").read_bytes()
    bound = bind_usage(turns, sessions, log_bytes.decode("utf-8"))
    require(
        before == {p: digest(p) for p in args.export.rglob("*") if p.is_file()},
        "export_changed_during_audit",
    )
    require(
        inspect_export(args.export, args.live) == (turns, evidence),
        "retained_turns_changed_during_audit",
    )
    report = dict(
        receipt_version="scientific-desktop-usage-v1",
        collector_sha256=digest(Path(__file__)),
        gateway_log_prefix_bytes=len(log_bytes),
        gateway_log_prefix_sha256=hashlib.sha256(log_bytes).hexdigest(),
        **evidence,
        turns=bound,
        model_requests=0,
        source_results_mutated=False,
        source_export_sha256={
            str(p.relative_to(args.export)): value for p, value in before.items()
        },
        public_sessions_snapshot_sha256=hashlib.sha256(result.stdout).hexdigest(),
        all_turns_verified_astra_medium=True,
        billing_route="chatgpt_codex_subscription",
        is_monetary_charge=False,
        limitations=[
            "Public counters are snapshots, not a full billing ledger.",
            "This binds retained source/turn/session identities, not clinical correctness or remote image bytes.",
        ],
    )
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(
        json.dumps(
            {
                "turns": len(bound),
                "all_turns_verified_astra_medium": True,
                "output_sha256": digest(args.output),
                "model_requests": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
