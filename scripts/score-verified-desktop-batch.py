"""Seal then score a complete Astra-medium GUI batch without inference or repairs.

Keep seal and score as separate invocations. The operator must first observe the
original driver terminating successfully; complete case receipts alone are not a
process-exit observer. Gold is never opened by seal, or before verified score gates.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIND = "verified_astra_medium_desktop_batch_v1"


def load_script(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), ROOT / "scripts" / name
    )
    if spec is None or spec.loader is None:
        raise ValueError("required_script_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def hash_file(path, *, prefix=None):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        remaining = prefix
        while remaining is None or remaining > 0:
            chunk = stream.read(
                1024 * 1024 if remaining is None else min(remaining, 1024 * 1024)
            )
            if not chunk:
                if remaining not in (None, 0):
                    raise ValueError("sealed_file_truncated")
                break
            digest.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return digest.hexdigest()


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def audit_arguments(arguments):
    args = {
        key: Path(arguments[key]).resolve(strict=True)
        for key in ("run", "manifest", "exports_root", "gateway_log")
    }
    args.update(
        plan_sha256=arguments["plan_sha256"], expected_cases=arguments["expected_cases"]
    )
    if type(args["expected_cases"]) is not int or args["expected_cases"] < 100:
        raise ValueError("at_least_100_planned_cases_required")
    return args


def complete_audit(arguments):
    report = load_script("verify-desktop-batch.py").audit(**audit_arguments(arguments))
    if (
        report["complete"] is not True
        or report["pending"]
        or report["invalid"]
        or report["technical_failure"]
        or report["verified"] != report["planned"]
    ):
        raise ValueError("batch_not_completely_verified")
    return report


def safe_output(path, arguments):
    target = Path(path).resolve()
    if any(
        target.is_relative_to(Path(arguments[key]).resolve())
        for key in ("run", "exports_root")
    ):
        raise ValueError("derived_output_must_not_change_primary_evidence_tree")


def evidence_paths(arguments):
    args = audit_arguments(arguments)
    run, manifest, exports = args["run"], args["manifest"], args["exports_root"]
    paths = {run / "plan.json", manifest}
    cases = []
    for index, row in enumerate(read(manifest)["cases"]):
        case_dir = run / f"case-{index:03d}"
        paths.update(
            case_dir / name
            for name in ("attempt.json", "receipt.json", "visible-roi.png")
        )
        source = (manifest.parent / row["image"]).resolve(strict=True)
        paths.add(source)
        receipt = read(case_dir / "receipt.json")
        export = Path(receipt["export_dir"]).resolve(strict=True)
        if export == exports or not export.is_relative_to(exports):
            raise ValueError("export_outside_permitted_root")
        for path in export.rglob("*"):
            if not path.resolve(strict=True).is_relative_to(export):
                raise ValueError("export_link_escapes_case")
            if path.is_file():
                paths.add(path.resolve(strict=True))
        cases.append(
            {"index": index, "case_id": row["label"], "export_dir": str(export)}
        )
    return paths, cases


def inventory(arguments):
    paths, cases = evidence_paths(arguments)
    items = {
        str(path.resolve(strict=True)): {
            "bytes": path.stat().st_size,
            "sha256": hash_file(path),
            "prefix": False,
        }
        for path in sorted(paths)
    }
    # The App may append harmless log lines after the last completed inference.
    # Bind its exact existing prefix, not a copied/recreated model-identity log.
    log = Path(arguments["gateway_log"]).resolve(strict=True)
    size = log.stat().st_size
    items[str(log)] = {
        "bytes": size,
        "sha256": hash_file(log, prefix=size),
        "prefix": True,
    }
    return items, cases


def verify_inventory(arguments, expected):
    paths, _ = evidence_paths(arguments)
    log = Path(arguments["gateway_log"]).resolve(strict=True)
    if {str(path.resolve(strict=True)) for path in paths} | {str(log)} != set(expected):
        raise ValueError("sealed_inventory_changed")
    for name, item in expected.items():
        path = Path(name)
        prefix = path == log
        if (
            item["prefix"] is not prefix
            or type(item["bytes"]) is not int
            or item["bytes"] < 0
        ):
            raise ValueError("invalid_sealed_inventory_record")
        if not prefix and path.stat().st_size != item["bytes"]:
            raise ValueError("sealed_file_size_changed")
        if hash_file(path, prefix=item["bytes"] if prefix else None) != item["sha256"]:
            raise ValueError("sealed_file_hash_changed")


def seal_batch(*, arguments, output, driver_completed):
    if Path(output).exists():
        raise FileExistsError("seal_output_exists")
    if driver_completed is not True:
        raise ValueError("operator_must_observe_driver_completion")
    args = audit_arguments(arguments)
    safe_output(output, args)
    report = complete_audit(args)
    files, cases = inventory(args)
    payload = {
        "kind": KIND,
        "created_at": datetime.now(UTC).isoformat(),
        "driver_completed_operator_assertion": True,
        "gold_read": False,
        "clinical_scored": False,
        "clinical_release_pass": False,
        "arguments": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in args.items()
        },
        "audit": report,
        "cases": cases,
        "files": files,
        "verifier_sha256": hash_file(ROOT / "scripts/verify-desktop-batch.py"),
        "sealer_sha256": hash_file(Path(__file__)),
        "limits": [
            "Driver completion is a recorded operator observation, not independent process attestation.",
            "Plan digest was independently captured mid-run, not a trusted pre-run signature.",
            "Export crop subdirectories are first sealed here, not retroactively by original receipts.",
            "Gateway log binds an exact prefix; later append-only text is outside that hash.",
            "No canonical medical ledger or diagnostic accuracy is validated by this seal.",
        ],
    }
    if complete_audit(args) != report:
        raise ValueError("audit_changed_during_sealing")
    verify_inventory(args, files)
    write_new(output, payload)
    return payload


def verify_seal(path, expected_sha256):
    if hash_file(path) != expected_sha256:
        raise ValueError("seal_digest_mismatch")
    seal = read(path)
    if (
        seal.get("kind") != KIND
        or seal.get("gold_read") is not False
        or seal.get("clinical_scored") is not False
        or seal.get("driver_completed_operator_assertion") is not True
    ):
        raise ValueError("invalid_unscored_batch_seal")
    if seal["verifier_sha256"] != hash_file(ROOT / "scripts/verify-desktop-batch.py"):
        raise ValueError("verifier_changed_after_sealing")
    if seal["sealer_sha256"] != hash_file(Path(__file__)):
        raise ValueError("sealer_changed_after_sealing")
    verify_inventory(seal["arguments"], seal["files"])
    if complete_audit(seal["arguments"]) != seal["audit"]:
        raise ValueError("sealed_audit_changed")
    if evidence_paths(seal["arguments"])[1] != seal["cases"]:
        raise ValueError("sealed_case_identity_changed")
    return seal


def paired_gold(seal, gold_path, expected_gold_sha256):
    if hash_file(gold_path) != expected_gold_sha256:
        raise ValueError("gold_digest_mismatch")
    manifest = Path(seal["arguments"]["manifest"])
    inference, gold = read(manifest), read(gold_path)
    pair_id = inference.get("selection", {}).get("pair_id")
    if not pair_id or pair_id != gold.get("selection", {}).get("pair_id"):
        raise ValueError("gold_pair_mismatch")
    if len(inference["cases"]) != len(gold["cases"]):
        raise ValueError("gold_case_count_mismatch")
    for blind, reference in zip(inference["cases"], gold["cases"], strict=True):
        if any(blind[key] != reference[key] for key in ("label", "image", "modality")):
            raise ValueError("gold_case_identity_order_mismatch")
        if (manifest.parent / blind["image"]).resolve(strict=True) != (
            Path(gold_path).parent / reference["image"]
        ).resolve(strict=True):
            raise ValueError("gold_image_path_mismatch")


def score_batch(
    *, seal_path, expected_seal_sha256, gold_path, expected_gold_sha256, output
):
    if Path(output).exists():
        raise FileExistsError("score_output_exists")
    seal = verify_seal(seal_path, expected_seal_sha256)  # No gold access before this.
    safe_output(output, seal["arguments"])
    paired_gold(seal, gold_path, expected_gold_sha256)
    legacy = load_script("score-desktop-cohort.py")
    scorer = legacy._load_scorer()
    references = {case.label: case for case in scorer._load_cases(gold_path)}
    scores, selected = [], []
    for item in seal["cases"]:
        case = references[item["case_id"]]
        raw = read(Path(item["export_dir"]) / "result.json")
        result = scorer._analysis_result_from_raw(raw, fallback_modality=case.modality)
        scores.append(
            scorer.score_case(case, result, latency_ms=result.analysis_time_ms)
        )
        selected.append(case)
    report = scorer._aggregate(
        "verified_real_desktop_medium_posthoc",
        scores,
        selected,
        scorer.get_active_registry(),
    )
    payload = json.loads(report.to_json())
    complete = [s for s in scores if s.reference_complete and s.clinical_scorable]
    severe = [s for s in scores if s.severity_scorable]
    cant_miss = [s for s in scores if s.cant_miss]
    urgent = [s for s in scores if s.urgent_concerns]
    payload.update(
        {
            "scorecard_kind": KIND,
            "created_at": datetime.now(UTC).isoformat(),
            "source_seal_sha256": expected_seal_sha256,
            "gold_manifest_sha256": expected_gold_sha256,
            "source_results_mutated": False,
            "guardrails_replayed": False,
            "clinical_release_pass": False,
            "canonical_ledger_validated": False,
            "model_requests": 0,
            "scorer_provenance": scorer._current_scorer_provenance(),
            "batch_scorer_sha256": hash_file(Path(__file__)),
            "model_profile": {"model": "gpt-6-astra", "reasoning": "medium"},
            "execution_audit": seal["audit"],
            "case_level_intervals": {
                "strict_complete_reference": legacy.wilson(
                    sum(s.strict_pass for s in complete), len(complete)
                ),
                "exact_severity": legacy.wilson(
                    sum(s.severity_match for s in severe), len(severe)
                ),
                "all_cant_miss_caught": legacy.wilson(
                    sum(s.cant_miss_caught for s in cant_miss), len(cant_miss)
                ),
                "all_urgent_concerns_caught": legacy.wilson(
                    sum(not s.urgent_concern_missed for s in urgent), len(urgent)
                ),
            },
            "interpretation_limits": [
                "Gold-enriched selected cases, not prevalence-weighted population evidence.",
                "Partial/uncertain references remain separate from strict complete-reference denominators.",
                "A zero denominator means unmeasured, not perfect or zero clinical sensitivity; use explicit intervals.",
                "Wilson intervals are descriptive; patient independence is not established.",
                "Automated concept/schema scores require specialist adjudication; schema is the legacy draft check.",
                "No reference boxes: coordinate containment is not clinical localization accuracy.",
                "Concurrent engineering workloads prevent a controlled speed comparison.",
            ],
        }
    )
    verify_seal(seal_path, expected_seal_sha256)
    if hash_file(gold_path) != expected_gold_sha256:
        raise ValueError("gold_changed_during_scoring")
    write_new(output, payload)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    seal = sub.add_parser("seal")
    for key in ("run", "manifest", "exports-root", "gateway-log", "output"):
        seal.add_argument("--" + key, type=Path, required=True)
    seal.add_argument("--plan-sha256", required=True)
    seal.add_argument("--expected-cases", type=int, default=120)
    seal.add_argument("--driver-completed", action="store_true")
    score = sub.add_parser("score")
    for key in ("seal-path", "gold-path", "output"):
        score.add_argument("--" + key, type=Path, required=True)
    score.add_argument("--expected-seal-sha256", required=True)
    score.add_argument("--expected-gold-sha256", required=True)
    args = vars(parser.parse_args())
    command, output = args.pop("command"), args.pop("output")
    if command == "seal":
        completed = args.pop("driver_completed")
        payload = seal_batch(arguments=args, output=output, driver_completed=completed)
        count = len(payload["cases"])
    else:
        payload = score_batch(output=output, **args)
        count = payload["total"]
    print(
        json.dumps(
            {
                "command": command,
                "cases": count,
                "output_sha256": hash_file(output),
                "clinical_release_pass": False,
                "model_requests": 0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
