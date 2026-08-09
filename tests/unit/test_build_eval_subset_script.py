from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image


def _load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "build-eval-subset.py"
    spec = importlib.util.spec_from_file_location("build_eval_subset", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_subset_is_deterministic_stratified_and_relocatable(
    tmp_path: Path,
) -> None:
    module = _load_module()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    cases = []
    for severity in ("normal", "warning", "critical"):
        for index in range(4):
            image = source_dir / f"{severity}-{index}.png"
            Image.new("RGB", (4, 4), "white").save(image)
            cases.append(
                {
                    "label": f"{severity}-{index}",
                    "image": image.name,
                    "expected_severity": severity,
                }
            )
    manifest = source_dir / "manifest.json"
    registry = source_dir / "waveform-registry.json"
    registry.write_text(json.dumps({"artifacts": {}}))
    manifest.write_text(
        json.dumps(
            {
                "dataset": "test",
                "waveform_registry": {"path": registry.name},
                "cases": cases,
            }
        )
    )
    first = tmp_path / "subsets" / "first.json"
    second = tmp_path / "subsets" / "second.json"

    first_result = module.build_subset(
        manifest_path=manifest,
        output_path=first,
        severity_counts={"normal": 2, "warning": 2, "critical": 2},
        seed=17,
    )
    second_result = module.build_subset(
        manifest_path=manifest,
        output_path=second,
        severity_counts={"normal": 2, "warning": 2, "critical": 2},
        seed=17,
    )

    assert [row["label"] for row in first_result["cases"]] == [
        row["label"] for row in second_result["cases"]
    ]
    assert first_result["counts"]["by_severity"] == {
        "critical": 2,
        "normal": 2,
        "warning": 2,
    }
    assert [row["expected_severity"] for row in first_result["cases"]] == [
        "normal",
        "warning",
        "critical",
        "normal",
        "warning",
        "critical",
    ]
    for row in first_result["cases"]:
        assert (first.parent / row["image"]).is_file()
    assert (first.parent / first_result["waveform_registry"]["path"]).is_file()


def test_build_subset_satisfies_coverage_with_overlap(tmp_path: Path) -> None:
    module = _load_module()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    cases = []
    for severity in ("normal", "warning", "critical"):
        for index in range(4):
            image = source_dir / f"{severity}-{index}.png"
            Image.new("RGB", (4, 4), "white").save(image)
            cases.append(
                {
                    "label": f"{severity}-{index}",
                    "image": image.name,
                    "expected_severity": severity,
                    "concepts": ["a", "b", "c"] if index < 2 else ["a"],
                    "cant_miss": ["acute MI"]
                    if severity == "critical" and index == 0
                    else [],
                    "urgent_concerns": ["STEMI"]
                    if severity == "critical" and index < 2
                    else [],
                    "label_status": "asserted"
                    if index % 2 == 0
                    else "partially_uncertain",
                }
            )
    manifest = source_dir / "manifest.json"
    manifest.write_text(json.dumps({"dataset": "test", "cases": cases}))

    result = module.build_subset(
        manifest_path=manifest,
        output_path=tmp_path / "pilot" / "manifest.json",
        severity_counts={"normal": 2, "warning": 2, "critical": 2},
        coverage_counts={
            "cant_miss": 1,
            "urgent_concern": 2,
            "multi_concept": 3,
            "asserted": 2,
            "partially_uncertain": 2,
        },
        seed=23,
    )

    assert result["counts"]["by_coverage"]["cant_miss"] >= 1
    assert result["counts"]["by_coverage"]["urgent_concern"] >= 2
    assert result["counts"]["by_coverage"]["multi_concept"] >= 3
    assert result["counts"]["by_coverage"]["asserted"] >= 2
    assert result["counts"]["by_coverage"]["partially_uncertain"] >= 2


def test_build_subset_excludes_denylisted_cases_reproducibly(
    tmp_path: Path,
) -> None:
    module = _load_module()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    cases = []
    for index in range(5):
        image = source_dir / f"normal-{index}.png"
        Image.new("RGB", (4, 4), "white").save(image)
        cases.append(
            {
                "label": f"normal-{index}",
                "image": image.name,
                "expected_severity": "normal",
            }
        )
    manifest = source_dir / "manifest.json"
    manifest.write_text(json.dumps({"dataset": "test", "cases": cases}))
    first_denylist = tmp_path / "first-denylist.txt"
    first_denylist.write_text(
        "# cases used during development\nnormal-0\nnormal-1\nmissing-case\n"
    )
    second_denylist = tmp_path / "second-denylist.txt"
    second_denylist.write_text(
        "missing-case\nnormal-1\n\n# same effective set\nnormal-0\n"
    )

    first = module.build_subset(
        manifest_path=manifest,
        output_path=tmp_path / "first" / "manifest.json",
        severity_counts={"normal": 3},
        seed=31,
        exposure_denylist_path=first_denylist,
    )
    second = module.build_subset(
        manifest_path=manifest,
        output_path=tmp_path / "second" / "manifest.json",
        severity_counts={"normal": 3},
        seed=31,
        exposure_denylist_path=second_denylist,
    )

    first_ids = [row["label"] for row in first["cases"]]
    assert first_ids == [row["label"] for row in second["cases"]]
    assert set(first_ids) == {"normal-2", "normal-3", "normal-4"}
    assert not {"normal-0", "normal-1"} & set(first_ids)
    first_exposure = first["selection"]["exposure_denylist"]
    second_exposure = second["selection"]["exposure_denylist"]
    assert first_exposure["entries"] == 3
    assert first_exposure["case_ids_sha256"] == second_exposure["case_ids_sha256"]
    assert first["selection"]["population"] == {
        "source_cases": 5,
        "eligible_before_denylist": 5,
        "excluded_by_denylist": 2,
        "eligible_after_denylist": 3,
        "denylist_entries_matched_in_source": 2,
        "denylist_entries_not_in_source": 1,
    }


def test_build_subset_writes_blind_pair_and_verifiable_report(
    tmp_path: Path,
) -> None:
    module = _load_module()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    cases = []
    for severity in ("normal", "warning"):
        for index in range(2):
            case_id = f"{severity}-{index}"
            image = source_dir / f"{case_id}.png"
            Image.new("RGB", (4, 4), "white").save(image)
            cases.append(
                {
                    "label": case_id,
                    "image": image.name,
                    "modality": "EKG",
                    "regions": [{"id": "full", "bbox": [0, 0, 1, 1]}],
                    "source": "test-source",
                    "waveform_artifact_id": f"wf-{case_id}",
                    "waveform_lead_mode": "standard-12-lead",
                    "report": f"diagnostic report for {case_id}",
                    "expected_severity": severity,
                    "expected_custom_answer": "must not leak",
                    "internal_diagnosis": "must not leak",
                    "keywords": ["answer"],
                    "negatives": ["answer"],
                    "target_axes": ["answer"],
                    "cant_miss": ["answer"],
                    "urgent_concerns": ["answer"],
                    "concepts": ["answer"],
                    "uncertain_concepts": ["answer"],
                    "label_status": "asserted",
                    "ungradable_reasons": ["answer"],
                }
            )
    registry = source_dir / "waveform-registry.json"
    registry.write_text(json.dumps({"artifacts": {}}))
    manifest = source_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "dataset": "test",
                "modality": "EKG",
                "note": "ground-truth generation details",
                "labeling": {"classifier": "test-classifier"},
                "counts": {"by_severity": {"normal": 2, "warning": 2}},
                "waveform_registry": {"path": registry.name},
                "cases": cases,
            }
        )
    )
    gold_path = tmp_path / "gold" / "manifest.json"
    inference_path = tmp_path / "inference" / "manifest.json"
    report_path = tmp_path / "audit" / "selection-report.json"

    gold = module.build_subset(
        manifest_path=manifest,
        output_path=gold_path,
        inference_output_path=inference_path,
        selection_report_path=report_path,
        severity_counts={"normal": 1, "warning": 1},
        seed=41,
    )
    inference = json.loads(inference_path.read_text())
    report = json.loads(report_path.read_text())

    gold_ids = [row["label"] for row in gold["cases"]]
    inference_ids = [row["label"] for row in inference["cases"]]
    assert gold_ids == inference_ids
    assert gold["selection"]["manifest_role"] == "gold"
    assert inference["selection"]["manifest_role"] == "inference"
    assert gold["selection"]["pair_id"] == inference["selection"]["pair_id"]
    assert report["pair_id"] == gold["selection"]["pair_id"]
    assert "selection_report" not in inference["selection"]

    answer_fields = {
        "cant_miss",
        "concepts",
        "expected_severity",
        "keywords",
        "label_status",
        "negatives",
        "report",
        "target_axes",
        "uncertain_concepts",
        "ungradable_reasons",
        "urgent_concerns",
    }
    for gold_case, inference_case in zip(
        gold["cases"], inference["cases"], strict=True
    ):
        assert answer_fields.isdisjoint(inference_case)
        assert not any(key.startswith("expected_") for key in inference_case)
        assert "internal_diagnosis" not in inference_case
        for field in (
            "label",
            "modality",
            "regions",
            "source",
            "waveform_artifact_id",
            "waveform_lead_mode",
        ):
            assert inference_case[field] == gold_case[field]
        gold_image = (gold_path.parent / gold_case["image"]).resolve()
        inference_image = (inference_path.parent / inference_case["image"]).resolve()
        assert gold_image == inference_image
        assert gold_image.is_file()

    assert "note" not in inference
    assert "labeling" not in inference
    assert inference["counts"] == {"cases": 2}
    assert (
        gold_path.parent / gold["waveform_registry"]["path"]
    ).resolve() == registry.resolve()
    assert (
        inference_path.parent / inference["waveform_registry"]["path"]
    ).resolve() == registry.resolve()
    assert report["sampling"]["selected"]["case_identities"] == gold_ids
    assert report["manifests"]["gold"]["sha256"] == _sha256(gold_path)
    assert report["manifests"]["inference"]["sha256"] == _sha256(inference_path)
    assert report["source_manifest"]["sha256"] == _sha256(manifest)


def test_main_supports_gold_alias_and_blind_output_options(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    image = source_dir / "case-1.png"
    Image.new("RGB", (4, 4), "white").save(image)
    manifest = source_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "label": "case-1",
                        "image": image.name,
                        "modality": "EKG",
                        "expected_severity": "normal",
                        "waveform_artifact_id": "wf-case-1",
                    }
                ]
            }
        )
    )
    denylist = tmp_path / "denylist.txt"
    denylist.write_text("not-this-case\n")
    gold_path = tmp_path / "gold.json"
    inference_path = tmp_path / "inference.json"
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build-eval-subset.py",
            "--manifest",
            str(manifest),
            "--gold-output",
            str(gold_path),
            "--inference-output",
            str(inference_path),
            "--selection-report",
            str(report_path),
            "--exposure-denylist",
            str(denylist),
            "--severity-count",
            "normal=1",
        ],
    )

    assert module.main() == 0
    assert gold_path.is_file()
    assert inference_path.is_file()
    assert report_path.is_file()


def test_meeti_blind_pilot_profile_is_mutually_stratified_and_seals_five() -> None:
    module = _load_module()
    rows: list[dict[str, object]] = []

    def add(
        prefix: str,
        count: int,
        *,
        severity: str,
        status: str,
        concepts: int,
        cant_miss: bool = False,
    ) -> None:
        for index in range(count):
            rows.append(
                {
                    "label": f"{prefix}-{index}",
                    "image": f"{prefix}-{index}.png",
                    "expected_severity": severity,
                    "label_status": status,
                    "concepts": [f"c-{item}" for item in range(concepts)],
                    "cant_miss": ["acute MI"] if cant_miss else [],
                }
            )

    add("normal", 20, severity="normal", status="asserted", concepts=0)
    add("wa-single", 10, severity="warning", status="asserted", concepts=1)
    add("wa-multi", 10, severity="warning", status="asserted", concepts=3)
    add(
        "wp-single",
        10,
        severity="warning",
        status="partially_uncertain",
        concepts=1,
    )
    add(
        "wp-multi",
        10,
        severity="warning",
        status="partially_uncertain",
        concepts=3,
    )
    add(
        "critical-cant",
        9,
        severity="critical",
        status="partially_uncertain",
        concepts=3,
        cant_miss=True,
    )
    add(
        "critical-other",
        20,
        severity="critical",
        status="partially_uncertain",
        concepts=3,
    )

    selected, metadata = module._select_meeti_blind_pilot_64(
        rows,
        seed=20260806,
        multi_concept_min=3,
    )

    assert len(selected) == 64
    assert metadata["selected_by_stratum"] == {
        "normal_asserted": 16,
        "warning_asserted_single": 7,
        "warning_asserted_multi": 7,
        "warning_partial_single": 7,
        "warning_partial_multi": 7,
        "critical_cant_miss": 4,
        "critical_non_cant_miss": 16,
    }
    assert metadata["sealed_critical_cant_miss_remaining"] == 5
    assert len({str(row["label"]) for row in selected}) == 64


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
