from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def module():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts/build-prospective-desktop-cohort.py"
    )
    spec = importlib.util.spec_from_file_location("prospective", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def row(index, **kwargs):
    return dict(
        label=f"meeti_{index}",
        report=f"Synthetic report {index}",
        concepts=["rbbb", "long_qt", "left_axis"],
        label_status="asserted",
        expected_severity="warning",
        **kwargs,
    )


def profile(count=2):
    return {
        "seed": 19,
        "signature_cap": 4,
        "quotas": {"conduction_qt": {"asserted": count}},
    }


def test_deterministic_order_independent_and_answer_free():
    m = module()
    rows = [row(i) for i in range(8)]
    kwargs = {
        "denied": set(),
        "image_digest": lambda r: r["label"],
        "profile": profile(),
    }
    selected = m.select_cases(rows, **kwargs)
    assert selected == m.select_cases(rows[::-1], **kwargs)
    inference = m.SELECTOR._build_inference_manifest(
        source={"dataset": "synthetic"},
        selected=[dict(r, image="a.png") for r in selected],
        source_manifest_path=Path("source/gold.json").resolve(),
        output_path=Path("dest/inference.json").resolve(),
        pair_id="pair",
        identity_order_sha256="identities",
        input_image_order_sha256="images",
    )
    m.SELECTOR._assert_answer_free_manifest(inference)
    assert all("report" not in r and "concepts" not in r for r in inference["cases"])


@pytest.mark.parametrize("alias", ["identity", "image", "report"])
def test_exposed_alias_cannot_reenter(alias):
    m = module()
    rows = [row(i) for i in range(5)]
    if alias == "report":
        rows[1]["report"] = "  SYNTHETIC REPORT 0 "

    def digest(r):
        return (
            "exposed"
            if alias == "image" and r["label"] in {"meeti_0", "meeti_1"}
            else r["label"]
        )

    selected = m.select_cases(
        rows, denied={"meeti_0"}, image_digest=digest, profile=profile(3)
    )
    assert "meeti_0" not in {r["label"] for r in selected}
    if alias != "identity":
        assert "meeti_1" not in {r["label"] for r in selected}


@pytest.mark.parametrize(
    "failure", ["signature", "image", "report", "uncertain", "normal", "identity"]
)
def test_infeasible_selection_fails_instead_of_relaxing(failure):
    m = module()
    rows = [row(i) for i in range(6)]

    def digest(r):
        return "same" if failure == "image" else r["label"]

    if failure == "report":
        for r in rows:
            r["report"] = "same report"
    if failure == "uncertain":
        for r in rows:
            r["uncertain_concepts"] = ["long_qt"]
    if failure == "normal":
        for r in rows:
            r["concepts"] = ["rbbb", "sinus", "normal"]
    if failure == "identity":
        rows[1]["label"] = rows[0]["label"]
    with pytest.raises(ValueError):
        m.select_cases(
            rows,
            denied=set(),
            image_digest=digest,
            profile=profile(5 if failure == "signature" else 2),
        )


def test_existing_output_and_changed_pool_are_rejected_before_writes(tmp_path):
    m = module()
    existing = tmp_path / "keep"
    existing.mkdir()
    with pytest.raises(ValueError, match="must be new"):
        m.build(
            source_path=tmp_path / "absent",
            denylist_path=tmp_path / "absent",
            output_dir=existing,
        )
    source = tmp_path / "source.json"
    source.write_text('{"cases": []}')
    output = tmp_path / "new"
    with pytest.raises(ValueError, match="Source hash"):
        m.build(
            source_path=source, denylist_path=tmp_path / "absent", output_dir=output
        )
    assert not output.exists()


def test_build_binds_real_paired_field_names_without_leaking_gold(
    tmp_path, monkeypatch
):
    m = module()
    rows = [dict(row(i), concepts=[], image=f"{i}.png") for i in range(9922)]
    for i in range(2):
        rows[i] = dict(row(i), image=f"{i}.png")
    for i in range(3):
        (tmp_path / f"{i}.png").write_bytes(f"synthetic bytes {i}".encode())
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"dataset": "synthetic", "cases": rows}))
    deny = tmp_path / "deny.txt"
    deny.write_text("meeti_2\n")
    monkeypatch.setattr(
        m.SELECTOR,
        "_MEETI_BLIND_IMPORTANT_MULTI_128_SOURCE_SHA256",
        m.SELECTOR._sha256(source),
    )
    monkeypatch.setattr(m, "PROFILE", profile())
    output = tmp_path / "cohort"
    receipt = m.build(source_path=source, denylist_path=deny, output_dir=output)
    gold = json.loads((output / "gold.json").read_text())
    inference = json.loads((output / "inference.json").read_text())
    m.SELECTOR._assert_paired_case_order(gold, inference)
    m.SELECTOR._assert_answer_free_manifest(inference)
    assert receipt["cases"] == 2 and receipt["source_cases"] == 9922
    assert receipt["model_execution_status"] == "not_run"
    assert receipt["gold_sha256"] == m.SELECTOR._sha256(output / "gold.json")
    assert receipt["inference_sha256"] == m.SELECTOR._sha256(output / "inference.json")
    assert {r["label"] for r in inference["cases"]} == {"meeti_0", "meeti_1"}
