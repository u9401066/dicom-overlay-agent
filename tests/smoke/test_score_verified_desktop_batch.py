"""Synthetic 100-case pixel/audit fixtures; never load private cohort or gold."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image
from tests.unit.test_desktop_batch_verifier import evidence as evidence


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def module():
    path = (
        Path(__file__).resolve().parents[2] / "scripts/score-verified-desktop-batch.py"
    )
    spec = importlib.util.spec_from_file_location("score_verified_batch", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def cohort(evidence, module):
    auditor, args, first_export, _, _ = evidence
    root = args["run"].parent
    raw_base = json.loads((first_export / "result.json").read_text())
    usage_base = json.loads((first_export / "usage-receipt.json").read_text())
    rows, records, logs = [], [], []
    for index in range(100):
        source = root / f"input-{index}.png"
        Image.new("RGB", (4, 4), (60 + index, 90, 120)).save(source)
        rows.append(
            {"label": f"synthetic-{index}", "image": source.name, "modality": "EKG"}
        )
        records.append(
            {
                "case_identity": rows[-1]["label"],
                "image_sha256": module.hash_file(source),
            }
        )
        export = args["exports_root"] / f"export-{index}"
        case_dir = args["run"] / f"case-{index:03d}"
        export.mkdir(exist_ok=True)
        case_dir.mkdir(exist_ok=True)
        (case_dir / "visible-roi.png").write_bytes(source.read_bytes())
        for name in auditor.REQUIRED_ARTIFACTS:
            (export / name).write_bytes(
                source.read_bytes() if name.endswith(".png") else b"{}"
            )
        raw = deepcopy(raw_base)
        raw.update(
            modality="EKG",
            severity="info",
            findings=[],
            checklist={},
            summary="No affirmative ischemia finding in this synthetic draft.",
            model_used="synthetic",
            analysis_time_ms=1200,
        )
        raw["source_image"]["sha256"] = module.hash_file(source)
        raw["analysis_trace"][0].update(
            session_key=f"analysis-{index}", run_id=f"run-{index}"
        )
        write(export / "result.json", raw)
        usage = deepcopy(usage_base)
        usage["source_result_sha256"] = module.hash_file(export / "result.json")
        turn = usage["turns"][0]
        turn.update(session_key=f"agent:main:analysis-{index}", run_id=f"run-{index}")
        turn["public_session_fields"]["sessionId"] = f"session-{index}"
        turn["runtime_observation"].update(
            run_id=f"run-{index}", session_id=f"session-{index}", log_line=index + 1
        )
        write(export / "usage-receipt.json", usage)
        write(
            export / "ui-capture.json",
            {
                "method": "app_owned_widget_render",
                "desktop_background_captured": False,
                "capture_exclusion_disabled": False,
            },
        )
        start = datetime(2026, 9, 24, 12, tzinfo=UTC) + timedelta(minutes=2 * index)
        attempt = {
            "index": index,
            "case_id": rows[-1]["label"],
            "input_sha256": module.hash_file(source),
            "actual_gui": True,
            "gold_read": False,
            "direct_model_requests": 0,
            "started_utc": start.isoformat(),
        }
        write(case_dir / "attempt.json", attempt)
        write(
            case_dir / "receipt.json",
            {
                **attempt,
                "status": "exported_verified",
                "export_dir": str(export),
                "finished_utc": (start + timedelta(minutes=1)).isoformat(),
                "artifact_sha256": {
                    p.name: module.hash_file(p) for p in export.iterdir() if p.is_file()
                },
            },
        )
        logs.append(
            f"embedded run start: runId=run-{index} sessionId=session-{index} provider=openai model=gpt-6-astra thinking=medium"
        )
    crops = first_export / "crops"
    crops.mkdir()
    (crops / "synthetic.png").write_bytes((root / "input-0.png").read_bytes())
    selection = {
        "pair_id": "synthetic-only-pair",
        "input_image_order_sha256": auditor.canonical_digest(records),
    }
    write(args["manifest"], {"selection": selection, "cases": rows})
    plan = json.loads((args["run"] / "plan.json").read_text())
    plan["planned_cases"] = records
    plan["bindings"].update(
        inference_sha256=module.hash_file(args["manifest"]),
        input_image_order_sha256=selection["input_image_order_sha256"],
    )
    write(args["run"] / "plan.json", plan)
    args.update(
        expected_cases=100, plan_sha256=module.hash_file(args["run"] / "plan.json")
    )
    args["gateway_log"].write_text("\n".join(logs) + "\n", encoding="utf-8")
    gold = root / "synthetic-gold.json"
    write(
        gold,
        {
            "selection": selection,
            "cases": [
                row
                | {
                    "expected_severity": "critical",
                    "keywords": ["ischemia"],
                    "cant_miss": [],
                    "label_status": "asserted" if index < 50 else "partially_uncertain",
                }
                for index, row in enumerate(rows)
            ],
        },
    )
    return args, gold, root / "sealed.json", root / "score.json"


def sealed(module, cohort):
    args, gold, seal_path, output = cohort
    module.seal_batch(arguments=args, output=seal_path, driver_completed=True)
    return {
        "seal_path": seal_path,
        "expected_seal_sha256": module.hash_file(seal_path),
        "gold_path": gold,
        "expected_gold_sha256": module.hash_file(gold),
        "output": output,
    }


def test_complete_actual_auditor_path_scores_without_changing_sources(module, cohort):
    args, _, seal_path, output = cohort
    before = {
        p: module.hash_file(p) for p in args["run"].parent.rglob("*") if p.is_file()
    }
    kwargs = sealed(module, cohort)
    seal = module.verify_seal(seal_path, kwargs["expected_seal_sha256"])
    assert seal["gold_read"] is False and seal["audit"]["verified"] == 100
    crop = args["exports_root"] / "export-0/crops/synthetic.png"
    assert str(crop.resolve()) in seal["files"]
    result = module.score_batch(**kwargs)
    assert result["total"] == 100 and result["model_requests"] == 0
    assert (
        result["case_level_intervals"]["strict_complete_reference"]["denominator"] == 50
    )
    assert result["case_level_intervals"]["all_cant_miss_caught"]["rate"] is None
    assert (
        result["clinical_release_pass"] is False
        and result["guardrails_replayed"] is False
    )
    assert result["canonical_ledger_validated"] is False
    assert before == {p: module.hash_file(p) for p in before}
    assert json.loads(output.read_text()) == result


@pytest.mark.parametrize(
    "variant", ["pending", "failed", "not_observed", "too_small", "wrong_plan"]
)
def test_seal_refuses_incomplete_or_unverified_batch(module, cohort, variant):
    args, gold, seal_path, _ = cohort
    completed = True
    if variant == "pending":
        (args["run"] / "case-099/receipt.json").unlink()
    elif variant == "failed":
        path = args["run"] / "case-099/receipt.json"
        receipt = json.loads(path.read_text())
        receipt["status"] = "technical_failure"
        write(path, receipt)
    elif variant == "not_observed":
        completed = False
    elif variant == "too_small":
        args["expected_cases"] = 99
    else:
        args["plan_sha256"] = "0" * 64
    gold.unlink()  # Sealing must neither need nor open gold.
    with pytest.raises(ValueError):
        module.seal_batch(arguments=args, output=seal_path, driver_completed=completed)
    assert not seal_path.exists()


@pytest.mark.parametrize(
    "variant", ["source", "result", "usage", "crop", "added_crop", "log_prefix", "plan"]
)
def test_changed_sealed_evidence_is_rejected_before_gold_access(
    module, cohort, variant
):
    args, _, _, _ = cohort
    kwargs = sealed(module, cohort)
    export = args["exports_root"] / "export-0"
    path = {
        "source": export / "source.png",
        "result": export / "result.json",
        "usage": export / "usage-receipt.json",
        "crop": export / "crops/synthetic.png",
        "added_crop": export / "crops/added.png",
        "log_prefix": args["gateway_log"],
        "plan": args["run"] / "plan.json",
    }[variant]
    path.write_bytes((path.read_bytes() if path.exists() else b"") + b"changed")
    if variant == "log_prefix":
        # Appending is allowed; change the already-bound prefix for this case.
        path.write_bytes(b"X" + path.read_bytes()[1:])
    kwargs["gold_path"] = path.parent / "must-not-open-gold.json"
    with pytest.raises(ValueError):
        module.score_batch(**kwargs)
    assert not kwargs["output"].exists()


def test_harmless_gateway_log_append_preserves_sealed_prefix(module, cohort):
    args, _, _, _ = cohort
    kwargs = sealed(module, cohort)
    with args["gateway_log"].open("a", encoding="utf-8") as stream:
        stream.write("Synthetic post-run status line\n")
    seal = module.verify_seal(kwargs["seal_path"], kwargs["expected_seal_sha256"])
    assert seal["audit"]["verified"] == 100


@pytest.mark.parametrize("variant", ["digest", "pair", "order", "image", "denominator"])
def test_unpaired_or_changed_gold_cannot_score(module, cohort, variant):
    kwargs = sealed(module, cohort)
    gold = json.loads(kwargs["gold_path"].read_text())
    if variant == "digest":
        kwargs["expected_gold_sha256"] = "0" * 64
    else:
        if variant == "pair":
            gold["selection"]["pair_id"] = "different"
        elif variant == "order":
            gold["cases"].reverse()
        elif variant == "image":
            gold["cases"][0]["image"] = gold["cases"][1]["image"]
        else:
            gold["cases"].pop()
        write(kwargs["gold_path"], gold)
        kwargs["expected_gold_sha256"] = module.hash_file(kwargs["gold_path"])
    with pytest.raises(ValueError):
        module.score_batch(**kwargs)
    assert not kwargs["output"].exists()


def test_wrong_seal_digest_fails_before_missing_gold(module, cohort):
    kwargs = sealed(module, cohort)
    kwargs.update(
        expected_seal_sha256="0" * 64, gold_path=Path("must-not-open-gold.json")
    )
    with pytest.raises(ValueError, match="seal_digest_mismatch"):
        module.score_batch(**kwargs)


def test_gold_changed_during_scoring_refuses_derived_output(
    module, cohort, monkeypatch
):
    kwargs = sealed(module, cohort)
    original_load = module.load_script
    legacy = original_load("score-desktop-cohort.py")
    scorer = legacy._load_scorer()
    aggregate = scorer._aggregate

    def changed(*args):
        kwargs["gold_path"].write_bytes(kwargs["gold_path"].read_bytes() + b" ")
        return aggregate(*args)

    monkeypatch.setattr(scorer, "_aggregate", changed)
    monkeypatch.setattr(legacy, "_load_scorer", lambda: scorer)
    monkeypatch.setattr(
        module,
        "load_script",
        lambda name: (
            legacy if name == "score-desktop-cohort.py" else original_load(name)
        ),
    )
    with pytest.raises(ValueError, match="gold_changed_during_scoring"):
        module.score_batch(**kwargs)
    assert not kwargs["output"].exists()


def test_existing_outputs_are_never_overwritten(module, cohort):
    args, _, seal_path, _ = cohort
    kwargs = sealed(module, cohort)
    before = seal_path.read_bytes()
    with pytest.raises(FileExistsError):
        module.seal_batch(arguments=args, output=seal_path, driver_completed=True)
    assert seal_path.read_bytes() == before
    kwargs["output"].write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        module.score_batch(**kwargs)
    assert kwargs["output"].read_bytes() == b"keep"


@pytest.mark.parametrize("key", ["run", "exports_root"])
def test_sealing_cannot_add_files_inside_primary_evidence(module, cohort, key):
    args, _, _, _ = cohort
    output = args[key] / "not-allowed.json"
    with pytest.raises(ValueError, match="primary_evidence_tree"):
        module.seal_batch(arguments=args, output=output, driver_completed=True)
    assert not output.exists()
