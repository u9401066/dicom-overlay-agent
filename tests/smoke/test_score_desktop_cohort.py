"""Synthetic evidence only: no desktop, patient images, auth or model calls."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def module():
    script = Path(__file__).resolve().parents[2] / "scripts/score-desktop-cohort.py"
    spec = importlib.util.spec_from_file_location("score_desktop_cohort", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def evidence(tmp_path, module):
    inventory, receipts, rows, blind_cases, gold_cases = {}, [], [], [], []

    def record(path):
        item = {"bytes": path.stat().st_size, "sha256": module.sha256(path)}
        inventory[path.relative_to(tmp_path).as_posix()] = item
        return item

    for index in range(100):
        label = f"synthetic_{index:03}"
        export = tmp_path / label
        export.mkdir()
        source = export / "source.png"
        # Hash-binding fixture bytes, deliberately not an image/inference claim.
        source.write_bytes(f"synthetic non-image {index}".encode())
        source_receipt = record(source)
        raw = {"modality": "EKG", "severity": "info", "findings": [],
               "source_image": {"sha256": source_receipt["sha256"]},
               "summary": "No affirmative ischemia finding in this synthetic draft.",
               "checklist": {}, "analysis_time_ms": 1200, "model_used": "fixture"}
        write_json(export / "result.json", raw)
        result_receipt = record(export / "result.json")
        usage_name = "usage-receipt.recovered.json" if index == 0 else "usage-receipt.json"
        write_json(export / usage_name, {
            "fixture_only": True, "source_image_sha256": source_receipt["sha256"],
            "turns": [{"runtime_observation": {"model": "gpt-6-astra", "reasoning_effort": "low"}}],
        })
        usage_receipt = record(export / usage_name)
        row = {"index": index, "case_id": label, "export_dir": label,
               "status": "exported_source_model_verified",
               "interaction": "real_QFileDialog_Analyze_Export",
               "runtime_model": "gpt-6-astra", "reasoning_effort": "low", "recorded_turns": 1,
               "clinical_accuracy_pass": None}
        rows.append(row)
        receipts.append({"index": index, "case_id": label, "attempt": index,
                         "export_dir": label, "source_sha256": source_receipt["sha256"],
                         "result_sha256": result_receipt["sha256"],
                         "usage_receipt_name": usage_name, "usage_sha256": usage_receipt["sha256"]})
        blind = {"label": label, "image": f"{label}/source.png", "modality": "EKG"}
        blind_cases.append(blind)
        gold_cases.append(blind | {"expected_severity": "critical", "keywords": ["ischemia"],
                                   "cant_miss": ["STEMI"] if index == 0 else [],
                                   "label_status": "asserted" if index < 50 else "partially_uncertain"})
    inference = tmp_path / "inference.json"
    gold = tmp_path / "gold.json"
    selection = {"pair_id": "synthetic-pair"}
    write_json(inference, {"selection": selection, "cases": blind_cases})
    record(inference)
    write_json(gold, {"selection": selection, "cases": gold_cases})
    ledger = tmp_path / "receipts.jsonl"
    ledger.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    seal = {"schema_version": 1, "kind": "real_gui_primary_cohort_hash_inventory",
            "clinical_scoring_performed": False, "early_pilots_included": False,
            "missing_success_indices": [], "planned_indices": [0, 99],
            "planned_distinct_cases": 100, "verified_distinct_cases": 100,
            "cases": receipts, "files": inventory,
            "ledger": {"path": "receipts.jsonl", "bytes": ledger.stat().st_size,
                       "sha256": module.sha256(ledger)},
            "failed_attempts": [{"index": 0, "status": "technical_failure"}],
            "runtime_fingerprints": ["synthetic-only"], "frozen_release_evidence": False}
    seal_path = tmp_path / "seal.json"
    write_json(seal_path, seal)
    return {"workspace": tmp_path, "seal_path": seal_path, "inference_path": inference,
            "gold_path": gold, "expected_gold_sha256": module.sha256(gold),
            "output_path": tmp_path / "scorecard.new.json"}


def test_complete_cohort_scores_immutable_exports_and_retains_failures(module, evidence):
    before = {p: module.sha256(p) for p in evidence["workspace"].rglob("*") if p.is_file()}
    result = module.score_desktop_cohort(**evidence)
    assert result["total"] == 100
    assert result["source_results_mutated"] is False
    assert result["guardrails_replayed"] is False
    assert result["clinical_release_pass"] is False
    assert result["early_pilots_included"] is False
    assert len(result["technical_failure_attempts"]) == 1
    assert result["case_level_intervals"]["strict_complete_reference"]["denominator"] == 50
    assert result["case_level_intervals"]["exact_severity"]["denominator"] == 100
    assert result["case_level_intervals"]["all_cant_miss_caught"]["numerator"] == 0
    assert result["cant_miss_total"] == 1
    assert result["cant_miss_caught_count"] == 0
    assert before == {p: module.sha256(p) for p in before}
    assert json.loads(evidence["output_path"].read_text("utf-8")) == result


@pytest.mark.parametrize("field,value", [
    ("missing_success_indices", [99]), ("early_pilots_included", True),
    ("clinical_scoring_performed", True), ("verified_distinct_cases", 99),
    ("planned_distinct_cases", 99), ("planned_indices", [0, 98]),
])
def test_incomplete_or_mixed_cohort_refused_before_gold(module, evidence, field, value):
    seal = json.loads(evidence["seal_path"].read_text("utf-8"))
    seal[field] = value
    write_json(evidence["seal_path"], seal)
    evidence["gold_path"] = evidence["workspace"] / "must-not-open-gold.json"
    with pytest.raises(ValueError):
        module.score_desktop_cohort(**evidence)
    assert not evidence["output_path"].exists()


@pytest.mark.parametrize("relative", ["synthetic_001/result.json", "synthetic_001/source.png",
                                      "synthetic_000/usage-receipt.recovered.json", "receipts.jsonl"])
def test_changed_evidence_refused_before_gold(module, evidence, relative):
    path = evidence["workspace"] / relative
    path.write_bytes(path.read_bytes() + b" ")
    evidence["gold_path"] = evidence["workspace"] / "must-not-open-gold.json"
    with pytest.raises(ValueError, match="hash/size"):
        module.score_desktop_cohort(**evidence)


@pytest.mark.parametrize("mutation", ["duplicate", "missing_usage", "wrong_export", "outside_path", "negative_attempt"])
def test_invalid_seal_bindings_fail(module, evidence, mutation):
    seal = json.loads(evidence["seal_path"].read_text("utf-8"))
    if mutation == "duplicate":
        seal["cases"][1] = seal["cases"][0]
    elif mutation == "missing_usage":
        del seal["files"]["synthetic_000/usage-receipt.recovered.json"]
    elif mutation == "wrong_export":
        seal["cases"][0]["export_dir"] = "synthetic_001"
    elif mutation == "outside_path":
        seal["files"]["../outside.json"] = {"bytes": 0, "sha256": "x"}
    else:
        seal["cases"][0]["attempt"] = -1
    write_json(evidence["seal_path"], seal)
    with pytest.raises(ValueError):
        module.score_desktop_cohort(**evidence)


@pytest.mark.parametrize("mutation", ["pair", "order", "source", "duplicate"])
def test_unpaired_gold_is_rejected(module, evidence, mutation):
    gold = json.loads(evidence["gold_path"].read_text("utf-8"))
    if mutation == "pair":
        gold["selection"]["pair_id"] = "different-pair"
    elif mutation == "order":
        gold["cases"].reverse()
    elif mutation == "source":
        gold["cases"][0]["image"] = "synthetic_001/source.png"
    else:
        gold["cases"][1] = gold["cases"][0]
    write_json(evidence["gold_path"], gold)
    # Test pairing checks independently of the separate frozen-gold hash gate.
    evidence["expected_gold_sha256"] = module.sha256(evidence["gold_path"])
    with pytest.raises(ValueError):
        module.score_desktop_cohort(**evidence)


def test_output_never_overwrites_existing_file(module, evidence):
    evidence["output_path"].write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        module.score_desktop_cohort(**evidence)
    assert evidence["output_path"].read_bytes() == b"keep me"


def test_wrong_frozen_gold_hash_is_rejected(module, evidence):
    evidence["expected_gold_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="pre-recorded reference digest"):
        module.score_desktop_cohort(**evidence)


@pytest.mark.parametrize("mutation", ["model", "effort", "source"])
def test_reinventoried_wrong_usage_is_not_accepted(module, evidence, mutation):
    seal = json.loads(evidence["seal_path"].read_text("utf-8"))
    relative = "synthetic_000/usage-receipt.recovered.json"
    path = evidence["workspace"] / relative
    usage = json.loads(path.read_text("utf-8"))
    if mutation == "source":
        usage["source_image_sha256"] = "0" * 64
    else:
        key = "model" if mutation == "model" else "reasoning_effort"
        usage["turns"][0]["runtime_observation"][key] = "wrong"
    write_json(path, usage)
    digest = module.sha256(path)
    seal["files"][relative] = {"bytes": path.stat().st_size, "sha256": digest}
    seal["cases"][0]["usage_sha256"] = digest
    write_json(evidence["seal_path"], seal)
    with pytest.raises(ValueError):
        module.score_desktop_cohort(**evidence)


def test_gold_mutation_during_scoring_prevents_output(module, evidence, monkeypatch):
    scorer = module._load_scorer()
    aggregate = scorer._aggregate

    def mutate_gold(*args):
        evidence["gold_path"].write_bytes(evidence["gold_path"].read_bytes() + b" ")
        return aggregate(*args)

    monkeypatch.setattr(scorer, "_aggregate", mutate_gold)
    monkeypatch.setattr(module, "_load_scorer", lambda: scorer)
    with pytest.raises(ValueError, match="changed during scoring"):
        module.score_desktop_cohort(**evidence)
    assert not evidence["output_path"].exists()


@pytest.mark.parametrize("numerator,denominator", [(0, 0), (0, 100), (50, 100), (100, 100)])
def test_wilson_intervals_include_denominators(module, numerator, denominator):
    result = module.wilson(numerator, denominator)
    assert result["denominator"] == denominator
    if denominator:
        low, high = result["wilson_95"]
        assert low <= numerator / denominator <= high
    else:
        assert result["rate"] is None and result["wilson_95"] is None
