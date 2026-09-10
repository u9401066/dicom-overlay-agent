from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

_DATASET_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "eval-datasets" / "meeti-blind-v1"
)
_STEM = "important-multi-128-v1"
_SOURCE_SHA256 = "803ad1b205dbc7c3dcdd88f4218872c7811e3510a8167ce058e70d1459a5ba8b"
_DENYLIST_SHA256 = "3fce0fc2e3ed0689e69feefabda7bdb2dd59a2d53b538e53233557ae14a85384"
_DENYLIST_CASE_IDS_SHA256 = (
    "23a5d6d84e6da096b11b90d31f2fcf4503b13a2a276a1f9633298cf2e5ad19ec"
)
_GOLD_SHA256 = "10be5cf206fdfe097b757c0754f17356932992e144b230bfe05d0784bd077cf1"
_INFERENCE_SHA256 = "edad516b2659d5174c926890b19caa67186de8631efdd8f01862039ff9c3dfaf"
_REPORT_SHA256 = "1d07c46c8c5c15fda097b722022dbbb3e3105a9ac70431c9f1667fb12b751f76"
_PAIR_ID = "7bdc87f6d184b321938a09e4f02335692fbda75a378127305742b6f41e8a46e0"
_CASE_ORDER_SHA256 = "6e4a8de82a686601b72e08037300ac8d0a23556f570782a5dd167919271224f9"
_INPUT_IMAGE_ORDER_SHA256 = (
    "38bcf5b0bd4008ac3bb6a39da3cb7f430278c55aff4c818d0a08a1fd2348c7ca"
)
_PROFILE_DEFINITION_SHA256 = (
    "3761b7dbe2296f13ccfec2769891509031c4541c19392af61ce919c6e541adb7"
)
_TIER_ORDER = (
    "acute_risk",
    "ischemic_infarct",
    "rhythm_ectopy",
    "conduction_qt",
    "structure_voltage",
)
_ONTOLOGY = {
    "acute_risk": frozenset(
        {
            "stemi",
            "acute_mi",
            "high_risk_long_qt",
            "complete_heart_block",
            "vtach",
            "hyperkalemia",
            "wellens",
            "vfib",
        }
    ),
    "ischemic_infarct": frozenset(
        {
            "st_elevation",
            "st_depression",
            "ischemia",
            "infarct",
            "old_infarct",
            "q_waves",
        }
    ),
    "rhythm_ectopy": frozenset(
        {
            "afib",
            "aflutter",
            "svt",
            "second_degree_block",
            "av_dissociation",
            "junctional_rhythm",
            "ectopic_atrial_rhythm",
            "preexcitation",
            "paced",
            "pvc",
            "pac",
        }
    ),
    "conduction_qt": frozenset(
        {
            "lbbb",
            "rbbb",
            "fascicular_block",
            "iv_conduction_delay",
            "long_qt",
            "first_degree_block",
        }
    ),
    "structure_voltage": frozenset({"lvh", "rvh", "atrial_abnormality", "low_voltage"}),
}
_ACUTE_SIGNALS = {
    "cant_miss": frozenset({"acute MI", "ventricular tachycardia"}),
    "urgent_concerns": frozenset({"STEMI", "acute MI"}),
}
_ANSWER_FIELDS = frozenset(
    {
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
        "urgent_concern",
        "urgent_concerns",
    }
)


def test_frozen_important_multi_128_pair_is_blind_and_quota_complete() -> None:
    gold_path = _DATASET_DIR / f"{_STEM}.gold.json"
    inference_path = _DATASET_DIR / f"{_STEM}.inference.json"
    report_path = _DATASET_DIR / f"{_STEM}.selection-report.json"
    denylist_path = _DATASET_DIR / f"{_STEM}-preselection-denylist.txt"
    required = (gold_path, inference_path, report_path, denylist_path)
    present = [path.is_file() for path in required]
    if not any(present):
        pytest.skip("local frozen MEETI cohort artifacts are intentionally gitignored")
    assert all(present), "local frozen MEETI cohort is only partially present"
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    inference = json.loads(inference_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert _sha256(gold_path) == _GOLD_SHA256
    assert _sha256(inference_path) == _INFERENCE_SHA256
    assert _sha256(report_path) == _REPORT_SHA256
    assert report["pair_id"] == _PAIR_ID
    assert report["source_manifest"]["sha256"] == _SOURCE_SHA256
    source_path = (report_path.parent / report["source_manifest"]["path"]).resolve()
    assert source_path.is_file()
    assert _sha256(source_path) == _SOURCE_SHA256
    assert _sha256(denylist_path) == _DENYLIST_SHA256
    assert report["manifests"]["gold"]["sha256"] == _sha256(gold_path)
    assert report["manifests"]["inference"]["sha256"] == _sha256(inference_path)
    assert report["pair_id"] == gold["selection"]["pair_id"]
    assert report["pair_id"] == inference["selection"]["pair_id"]

    gold_ids = [str(row["label"]) for row in gold["cases"]]
    inference_ids = [str(row["label"]) for row in inference["cases"]]
    denylisted_ids = set(denylist_path.read_text(encoding="utf-8").splitlines())
    assert gold_ids == inference_ids
    assert len(gold_ids) == len(set(gold_ids)) == 128
    assert not set(gold_ids) & denylisted_ids
    assert len(denylisted_ids) == 1230
    assert _canonical_sha256(sorted(denylisted_ids)) == _DENYLIST_CASE_IDS_SHA256
    assert _canonical_sha256(gold_ids) == _CASE_ORDER_SHA256

    input_image_records = []
    input_image_hashes = set()
    for row in gold["cases"]:
        image_path = (gold_path.parent / row["image"]).resolve()
        assert image_path.is_file()
        image_sha256 = _sha256(image_path)
        input_image_records.append(
            {"case_identity": row["label"], "image_sha256": image_sha256}
        )
        input_image_hashes.add(image_sha256)
    assert len(input_image_hashes) == 128
    assert _canonical_sha256(input_image_records) == _INPUT_IMAGE_ORDER_SHA256

    for manifest in (gold, inference):
        selection = manifest["selection"]
        assert selection["pair_id"] == _PAIR_ID
        assert selection["case_identity_order_sha256"] == _CASE_ORDER_SHA256
        assert selection["input_image_order_sha256"] == _INPUT_IMAGE_ORDER_SHA256

    assert set(inference) == {
        "cases",
        "counts",
        "dataset",
        "modality",
        "selection",
        "source_record",
        "waveform_registry",
    }
    for row in inference["cases"]:
        assert _ANSWER_FIELDS.isdisjoint(row)
        assert not any(key.startswith("expected_") for key in row)
        assert (_DATASET_DIR / row["image"]).resolve().is_file()
        _assert_no_answer_keys(row)

    metadata = report["sampling"]["sampling_profile_metadata"]
    assert metadata["profile_definition_sha256"] == _PROFILE_DEFINITION_SHA256
    assert metadata["input_image_order_sha256"] == _INPUT_IMAGE_ORDER_SHA256
    assert metadata["unique_input_image_sha256"] == 128
    assert metadata["profile_definition"]["study_intent"] == {
        "design": "purposefully gold-enriched multi-finding stress cohort",
        "estimand_limit": (
            "not prevalence-weighted and must not be reported as population accuracy"
        ),
    }
    assert (
        _canonical_sha256(metadata["profile_definition"]) == _PROFILE_DEFINITION_SHA256
    )
    sampling = report["sampling"]
    assert sampling["selected"]["input_image_order_sha256"] == (
        _INPUT_IMAGE_ORDER_SHA256
    )
    pair_payload = {
        "source_manifest_sha256": _SOURCE_SHA256,
        "seed": sampling["seed"],
        "severity_counts": sampling["severity_counts"],
        "coverage_counts": sampling["coverage_counts"],
        "multi_concept_min": sampling["multi_concept_min"],
        "sampling_profile": sampling["sampling_profile"],
        "denylist_case_ids_sha256": _DENYLIST_CASE_IDS_SHA256,
        "case_identity_order_sha256": _CASE_ORDER_SHA256,
        "input_image_order_sha256": _INPUT_IMAGE_ORDER_SHA256,
        "sampling_profile_definition_sha256": _PROFILE_DEFINITION_SHA256,
    }
    assert _canonical_sha256(pair_payload) == _PAIR_ID
    assert metadata["eligible_after_profile_filters"] == 3384
    assert metadata["eligible_by_tier"] == {
        "acute_risk": 99,
        "ischemic_infarct": 940,
        "rhythm_ectopy": 1148,
        "conduction_qt": 1022,
        "structure_voltage": 175,
    }
    assert metadata["selected_by_tier"] == {
        "acute_risk": 24,
        "ischemic_infarct": 28,
        "rhythm_ectopy": 28,
        "conduction_qt": 32,
        "structure_voltage": 16,
    }
    assert metadata["selected_by_label_status"] == {
        "asserted": 48,
        "partially_uncertain": 80,
    }
    assert metadata["selected_by_severity"] == {"critical": 24, "warning": 104}
    assert min(metadata["selected_axis_coverage"].values()) >= 12
    assert metadata["critical_cant_miss_available_before_selection"] == 1
    assert metadata["critical_cant_miss_selected"] == 1
    assert metadata["sealed_critical_cant_miss_remaining"] == 0
    assert metadata["exposure_control"] == {
        "preselection_denylist_locked": True,
        "preselection_denylist_entries": 1230,
        "selected_overlap_with_preselection_denylist": 0,
        "model_execution_status": "not_run",
        "cohort_case_status_after_construction": "exposed_reserved",
        "selected_cases_to_add_before_next_prospective_selection": 128,
        "next_batch_gate": (
            "union this inference manifest's case identities into the exposure "
            "denylist before selecting any prospective batch"
        ),
    }

    normalized_reports = {
        " ".join(str(row["report"]).casefold().split()) for row in gold["cases"]
    }
    assert len(normalized_reports) == 128
    tier_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for row in gold["cases"]:
        canonical = _canonical_diagnoses(row)
        assert len(canonical) >= 3
        assert not set(row.get("concepts", ())) & set(row.get("uncertain_concepts", ()))
        tier = _important_tier(row, canonical)
        assert tier
        tier_counts[tier] += 1
        status_counts[str(row["label_status"])] += 1
        assert row["expected_severity"] == (
            "critical" if tier == "acute_risk" else "warning"
        )
    assert tier_counts == {
        "acute_risk": 24,
        "ischemic_infarct": 28,
        "rhythm_ectopy": 28,
        "conduction_qt": 32,
        "structure_voltage": 16,
    }
    assert status_counts == {"asserted": 48, "partially_uncertain": 80}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_diagnoses(row: dict[str, object]) -> tuple[str, ...]:
    diagnoses = {
        str(value).strip()
        for value in row.get("concepts", ())
        if isinstance(value, str) and value.strip()
    }
    diagnoses.difference_update(
        str(value).strip()
        for value in row.get("uncertain_concepts", ())
        if isinstance(value, str) and value.strip()
    )
    diagnoses.difference_update({"normal", "sinus"})
    if "old_infarct" in diagnoses:
        diagnoses.discard("infarct")
    if "high_risk_long_qt" in diagnoses:
        diagnoses.discard("long_qt")
    return tuple(sorted(diagnoses))


def _assert_no_answer_keys(value: object) -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            assert key not in _ANSWER_FIELDS
            assert not key.startswith("expected_")
            assert not any(
                marker in key.casefold()
                for marker in ("answer", "diagnos", "ground_truth")
            )
            _assert_no_answer_keys(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_answer_keys(child)


def _important_tier(row: dict[str, object], canonical: tuple[str, ...]) -> str:
    for field, allowed in _ACUTE_SIGNALS.items():
        values = row.get(field)
        if isinstance(values, list) and set(values) & allowed:
            return "acute_risk"
    diagnoses = set(canonical)
    for tier in _TIER_ORDER:
        if diagnoses & _ONTOLOGY[tier]:
            return tier
    return ""
