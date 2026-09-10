"""Score a completed, hash-sealed real-GUI cohort without rerunning inference.

Gold is opened only after the complete primary evidence inventory is verified.
The scorecard is a new derived file; original exports/ledger are never rewritten.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _inside(root: Path, relative: str) -> Path:
    """Resolve evidence paths inside the explicitly selected workspace."""
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Evidence paths must be workspace-relative without traversal")
    resolved = (root / path).resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("Evidence must be a file inside the workspace")
    return resolved


def _verify_file(path: Path, receipt: dict[str, Any]) -> None:
    if path.stat().st_size != receipt["bytes"] or sha256(path) != receipt["sha256"]:
        raise ValueError(f"Evidence hash/size mismatch: {path.name}")


def verify_seal(root: Path, seal_path: Path) -> dict[str, Any]:
    """Validate complete primary coverage and every recorded artifact before gold."""
    root = root.resolve(strict=True)
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    if (seal.get("schema_version") != 1
            or seal.get("kind") != "real_gui_primary_cohort_hash_inventory"
            or seal.get("clinical_scoring_performed") is not False
            or seal.get("early_pilots_included") is not False
            or seal.get("missing_success_indices") != []):
        raise ValueError("A complete, unscored primary GUI seal is required")
    first, last = seal["planned_indices"]
    if type(first) is not int or type(last) is not int or first < 0 or last < first:
        raise ValueError("Invalid planned cohort range")
    cases = seal["cases"]
    expected = set(range(first, last + 1))
    if (len(expected) < 100 or seal["planned_distinct_cases"] != len(expected)
            or seal["verified_distinct_cases"] != len(expected)
            or len(cases) != len(expected)
            or {case["index"] for case in cases} != expected
            or len({case["case_id"] for case in cases}) != len(cases)):
        raise ValueError("Primary cohort must contain every planned distinct case (at least 100)")
    inventory = seal["files"]
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError("Evidence inventory is empty")
    for relative, receipt in inventory.items():
        _verify_file(_inside(root, relative), receipt)
    ledger = _inside(root, seal["ledger"]["path"])
    _verify_file(ledger, seal["ledger"])
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    for case in cases:
        if type(case["attempt"]) is not int or not 0 <= case["attempt"] < len(rows):
            raise ValueError("Invalid original GUI attempt index")
        row = rows[case["attempt"]]
        if (row["case_id"] != case["case_id"] or row["index"] != case["index"]
                or row["status"] != "exported_source_model_verified"
                or row["interaction"] != "real_QFileDialog_Analyze_Export"
                or row["clinical_accuracy_pass"] is not None):
            raise ValueError("Seal does not bind the original successful GUI attempt")
        if Path(row["export_dir"]) != Path(case["export_dir"]):
            raise ValueError("Export directory does not match the original ledger")
        for name, digest in (("result.json", case["result_sha256"]),
                             ("source.png", case["source_sha256"]),
                             (case["usage_receipt_name"], case["usage_sha256"])):
            relative = (Path(case["export_dir"]) / name).as_posix()
            if relative not in inventory or inventory[relative]["sha256"] != digest:
                raise ValueError("Required result/source/usage proof is not inventoried")
        raw = json.loads(_inside(root, case["export_dir"] + "/result.json").read_text("utf-8"))
        usage_path = (Path(case["export_dir"]) / case["usage_receipt_name"]).as_posix()
        usage = json.loads(_inside(root, usage_path).read_text("utf-8"))
        if (raw.get("source_image", {}).get("sha256") != case["source_sha256"]
                or usage.get("source_image_sha256") != case["source_sha256"]):
            raise ValueError("Result or usage receipt is bound to a different source")
        turns = usage.get("turns", [])
        if (not turns or len(turns) != row.get("recorded_turns")
                or row.get("runtime_model") != "gpt-6-astra"
                or row.get("reasoning_effort") != "low"
                or any((turn.get("runtime_observation") or {}).get("model") != "gpt-6-astra"
                       or (turn.get("runtime_observation") or {}).get("reasoning_effort") != "low"
                       for turn in turns)):
            raise ValueError("Astra-low runtime observations are missing or inconsistent")
    return seal


def _paired_cases(root: Path, seal: dict, inference_path: Path, gold_path: Path) -> dict:
    inference_relative = inference_path.relative_to(root).as_posix()
    if inference_relative not in seal["files"]:
        raise ValueError("Inference manifest is not in the sealed inventory")
    inference = json.loads(inference_path.read_text(encoding="utf-8"))
    # No gold access before verify_seal has checked all coverage and hashes.
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    pair_id = inference.get("selection", {}).get("pair_id")
    if not pair_id or gold.get("selection", {}).get("pair_id") != pair_id:
        raise ValueError("Gold is not paired with the sealed inference manifest")
    infer_cases, gold_cases = inference["cases"], gold["cases"]
    if len(infer_cases) != len(gold_cases):
        raise ValueError("Paired manifests have different case counts")
    identities = []
    for blind, reference in zip(infer_cases, gold_cases, strict=True):
        identity = tuple(blind[key] for key in ("label", "image", "modality"))
        if identity != tuple(reference[key] for key in ("label", "image", "modality")):
            raise ValueError("Paired image identity/order mismatch")
        identities.append(identity[0])
    if len(set(identities)) != len(identities):
        raise ValueError("Paired manifests contain duplicate case identities")
    for case in seal["cases"]:
        blind = infer_cases[case["index"]]
        if blind["label"] != case["case_id"]:
            raise ValueError("Primary selection does not match paired manifest order")
        source = (inference_path.parent / blind["image"]).resolve(strict=True)
        relative = source.relative_to(root).as_posix()
        if relative not in seal["files"]:
            raise ValueError("Original dataset image is not in the sealed inventory")
        gold_source = (gold_path.parent / gold_cases[case["index"]]["image"]).resolve(strict=True)
        if gold_source != source:
            raise ValueError("Gold points to a different source image")
    return gold


def wilson(successes: int, denominator: int) -> dict[str, Any]:
    """Descriptive case-level Wilson interval; not a population-accuracy claim."""
    if not 0 <= successes <= denominator:
        raise ValueError("Invalid binomial counts")
    if not denominator:
        return {"numerator": 0, "denominator": 0, "rate": None, "wilson_95": None}
    z = 1.959963984540054
    p = successes / denominator
    scale = 1 + z * z / denominator
    center = (p + z * z / (2 * denominator)) / scale
    radius = z * math.sqrt(p * (1 - p) / denominator + z * z / (4 * denominator**2)) / scale
    return {"numerator": successes, "denominator": denominator, "rate": p,
            "wilson_95": [0.0 if successes == 0 else max(0, center - radius),
                          1.0 if successes == denominator else min(1, center + radius)]}


def _load_scorer():
    spec = importlib.util.spec_from_file_location(
        "desktop_rebuild_scorer", REPO_ROOT / "scripts/rebuild-eval-scorecard.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Scorer implementation is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def score_desktop_cohort(*, workspace: Path, seal_path: Path, inference_path: Path,
                         gold_path: Path, expected_gold_sha256: str, output_path: Path) -> dict:
    root = workspace.resolve(strict=True)
    if output_path.exists():
        raise FileExistsError("Scorecard output already exists; choose a new path")
    seal_hash = sha256(seal_path)
    seal = verify_seal(root, seal_path)
    if sha256(gold_path) != expected_gold_sha256:
        raise ValueError("Gold hash does not match the pre-recorded reference digest")
    _paired_cases(root, seal, inference_path.resolve(strict=True), gold_path)
    gold_hash = sha256(gold_path)
    scorer = _load_scorer()
    all_cases = {case.label: case for case in scorer._load_cases(gold_path)}
    scores, selected = [], []
    for receipt in sorted(seal["cases"], key=lambda row: row["index"]):
        case = all_cases[receipt["case_id"]]
        raw = json.loads(_inside(root, receipt["export_dir"] + "/result.json").read_text("utf-8"))
        result = scorer._analysis_result_from_raw(raw, fallback_modality=case.modality)
        scores.append(scorer.score_case(case, result, latency_ms=result.analysis_time_ms))
        selected.append(case)
    report = scorer._aggregate("real_desktop_export_posthoc", scores, selected,
                               scorer.get_active_registry())
    payload = json.loads(report.to_json())
    complete = [s for s in scores if s.reference_complete and s.clinical_scorable]
    severe = [s for s in scores if s.severity_scorable]
    cant_miss = [s for s in scores if s.cant_miss]
    urgent = [s for s in scores if s.urgent_concerns]
    payload.update({
        "scorecard_kind": "sealed_real_desktop_primary_posthoc",
        "created_at": datetime.now(UTC).isoformat(),
        "source_seal_sha256": seal_hash, "gold_manifest_sha256": gold_hash,
        "source_results_mutated": False, "guardrails_replayed": False,
        "early_pilots_included": False, "clinical_release_pass": False,
        "planned_distinct_cases": seal["planned_distinct_cases"],
        "technical_failure_attempts": seal["failed_attempts"],
        "runtime_fingerprints": seal["runtime_fingerprints"],
        "frozen_release_evidence": seal["frozen_release_evidence"],
        "scorer_provenance": scorer._current_scorer_provenance(),
        "desktop_scorer_sha256": sha256(Path(__file__)),
        "case_level_intervals": {
            "strict_complete_reference": wilson(sum(s.strict_pass for s in complete), len(complete)),
            "exact_severity": wilson(sum(s.severity_match for s in severe), len(severe)),
            "all_cant_miss_caught": wilson(sum(s.cant_miss_caught for s in cant_miss), len(cant_miss)),
            "all_urgent_concerns_caught": wilson(sum(not s.urgent_concern_missed for s in urgent), len(urgent)),
        },
        "interpretation_limits": [
            "Gold-enriched selected cases, not prevalence-weighted population evidence.",
            "Wilson intervals are descriptive; within-patient independence is not established.",
            "Automated concept/schema scores require specialist adjudication.",
            "Bounding-box containment is not clinical localization accuracy (no reference boxes).",
            "Pilot runs are excluded; retained technical failures are attempts, not extra patients.",
            "Concurrent engineering workloads prevent a controlled speed comparison.",
        ],
    })
    # Detect changes during scoring; no update is made to any source artifact.
    verify_seal(root, seal_path)
    if sha256(seal_path) != seal_hash or sha256(gold_path) != gold_hash:
        raise ValueError("Sealed evidence or gold changed during scoring")
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "seal", "inference", "gold", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--gold-sha256", required=True,
                        help="Gold digest recorded before inference, not a newly substituted reference")
    args = parser.parse_args()
    payload = score_desktop_cohort(workspace=args.workspace, seal_path=args.seal,
                                  inference_path=args.inference, gold_path=args.gold,
                                  expected_gold_sha256=args.gold_sha256,
                                  output_path=args.output)
    print(json.dumps({"cases": payload["total"], "output": str(args.output),
                      "source_results_mutated": False, "clinical_release_pass": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
