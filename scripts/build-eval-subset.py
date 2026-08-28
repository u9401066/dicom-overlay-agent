"""Build a deterministic severity-stratified subset of an eval manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from functools import partial
from pathlib import Path
from typing import Any

_SUPPORTED_COVERAGE_TAGS = frozenset(
    {
        "asserted",
        "cant_miss",
        "multi_concept",
        "partially_uncertain",
        "urgent_concern",
    }
)
_MEETI_BLIND_PILOT_64 = "meeti_blind_pilot_64"
_MEETI_BLIND_PILOT_64_STRATA = (
    ("normal_asserted", 16),
    ("warning_asserted_single", 7),
    ("warning_asserted_multi", 7),
    ("warning_partial_single", 7),
    ("warning_partial_multi", 7),
    ("critical_cant_miss", 4),
    ("critical_non_cant_miss", 16),
)
_MEETI_BLIND_PILOT_64_SEVERITY_COUNTS = {
    "normal": 16,
    "warning": 28,
    "critical": 20,
}

_MEETI_BLIND_IMPORTANT_MULTI_128 = "meeti_blind_important_multi_128_v1"
_MEETI_BLIND_IMPORTANT_MULTI_128_SEED = 1946247532
_MEETI_BLIND_IMPORTANT_MULTI_128_SEED_MATERIAL = (
    "dicom-overlay-agent:v0.4.7:meeti-important-multi-128:v1"
)
_MEETI_BLIND_IMPORTANT_MULTI_128_SEED_MATERIAL_SHA256 = (
    "7401616cf890651825a01358be0503d4617767d1db3b65f1ea2265584f44abb6"
)
_MEETI_BLIND_IMPORTANT_MULTI_128_SOURCE_SHA256 = (
    "803ad1b205dbc7c3dcdd88f4218872c7811e3510a8167ce058e70d1459a5ba8b"
)
_MEETI_BLIND_IMPORTANT_MULTI_128_DENYLIST_SHA256 = (
    "3fce0fc2e3ed0689e69feefabda7bdb2dd59a2d53b538e53233557ae14a85384"
)
_MEETI_BLIND_IMPORTANT_MULTI_128_DENYLIST_CASE_IDS_SHA256 = (
    "23a5d6d84e6da096b11b90d31f2fcf4503b13a2a276a1f9633298cf2e5ad19ec"
)
_MEETI_BLIND_IMPORTANT_MULTI_128_DENYLIST_ENTRIES = 1230
_MEETI_BLIND_IMPORTANT_MULTI_128_SEVERITY_COUNTS = {
    "warning": 104,
    "critical": 24,
}
_MEETI_BLIND_IMPORTANT_MULTI_128_MIN_DIAGNOSES = 3
_MEETI_BLIND_IMPORTANT_MULTI_128_SIGNATURE_CAP = 4
_MEETI_BLIND_IMPORTANT_MULTI_128_REPORT_CAP = 1
_MEETI_BLIND_IMPORTANT_MULTI_128_AXIS_MINIMUM = 12
_MEETI_BLIND_IMPORTANT_MULTI_128_AXES = (
    "av_block",
    "axis",
    "chamber_enlargement",
    "conduction",
    "heart_rate",
    "ischemia",
    "p_wave",
    "pr_interval",
    "qrs_duration",
    "qrs_morphology",
    "qtc_interval",
    "regularity",
    "rhythm",
    "st_segment",
    "stemi_pattern",
    "t_wave",
)
_MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER = (
    "acute_risk",
    "ischemic_infarct",
    "rhythm_ectopy",
    "conduction_qt",
    "structure_voltage",
)
_MEETI_BLIND_IMPORTANT_MULTI_128_ONTOLOGY = {
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
    "structure_voltage": frozenset(
        {"lvh", "rvh", "atrial_abnormality", "low_voltage"}
    ),
}
_MEETI_BLIND_IMPORTANT_MULTI_128_ACUTE_SIGNALS = {
    "cant_miss": frozenset({"acute MI", "ventricular tachycardia"}),
    "urgent_concerns": frozenset({"STEMI", "acute MI"}),
}
_MEETI_BLIND_IMPORTANT_MULTI_128_STATUS_QUOTAS = {
    "acute_risk": {"asserted": 1, "partially_uncertain": 23},
    "ischemic_infarct": {"asserted": 14, "partially_uncertain": 14},
    "rhythm_ectopy": {"asserted": 14, "partially_uncertain": 14},
    "conduction_qt": {"asserted": 14, "partially_uncertain": 18},
    "structure_voltage": {"asserted": 5, "partially_uncertain": 11},
}
_MEETI_BLIND_IMPORTANT_MULTI_128_COVERAGE_MINIMA = {
    "acute_risk": {
        "cant_miss": 1,
        "urgent:STEMI": 16,
        "urgent:acute MI": 6,
    },
    "ischemic_infarct": {
        "infarct": 8,
        "st_elevation": 4,
        "st_depression": 4,
        "ischemia": 2,
        "old_infarct": 2,
        "q_waves": 2,
    },
    "rhythm_ectopy": {
        "afib": 5,
        "aflutter": 2,
        "pvc": 4,
        "pac": 4,
        "second_degree_block": 1,
        "av_dissociation": 1,
        "paced": 2,
        "ectopic_atrial_rhythm": 1,
        "junctional_rhythm": 1,
        "preexcitation": 1,
        "svt": 1,
    },
    "conduction_qt": {
        "lbbb": 4,
        "rbbb": 6,
        "fascicular_block": 4,
        "iv_conduction_delay": 4,
        "long_qt": 4,
        "first_degree_block": 4,
    },
    "structure_voltage": {
        "lvh": 4,
        "rvh": 2,
        "atrial_abnormality": 2,
        "low_voltage": 4,
    },
}
_MEETI_CASE_ID_PATTERN = re.compile(r"meeti_[0-9]+\Z")

_INFERENCE_ANSWER_FIELDS = frozenset(
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
_INFERENCE_CASE_FIELDS = frozenset(
    {
        "image",
        "label",
        "modality",
        "regions",
        "source",
        "waveform_artifact_id",
        "waveform_lead_mode",
    }
)
_INFERENCE_TOP_LEVEL_OMIT_FIELDS = frozenset({"labeling", "note"})
_INFERENCE_TOP_LEVEL_FIELDS = frozenset(
    {
        "cases",
        "counts",
        "dataset",
        "modality",
        "selection",
        "source_record",
        "waveform_registry",
    }
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_exposure_denylist(
    path: Path | None,
) -> tuple[set[str], dict[str, Any] | None]:
    if path is None:
        return set(), None
    if not path.is_file():
        raise ValueError(f"exposure denylist does not exist: {path}")

    case_ids = {
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    canonical_ids = sorted(case_ids)
    return case_ids, {
        "sha256": _sha256(path),
        "case_ids_sha256": _canonical_sha256(canonical_ids),
        "entries": len(case_ids),
    }


def _parse_counts(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        name, separator, raw_count = value.partition("=")
        if not separator or not name.strip():
            raise ValueError(f"invalid severity count {value!r}; expected name=count")
        count = int(raw_count)
        if count < 0:
            raise ValueError("severity counts must be non-negative")
        counts[name.strip()] = count
    if not counts or not any(counts.values()):
        raise ValueError("at least one positive severity count is required")
    return counts


def build_subset(
    *,
    manifest_path: Path,
    output_path: Path,
    severity_counts: dict[str, int],
    seed: int,
    coverage_counts: dict[str, int] | None = None,
    multi_concept_min: int = 3,
    exposure_denylist_path: Path | None = None,
    inference_output_path: Path | None = None,
    selection_report_path: Path | None = None,
    sampling_profile: str = "",
) -> dict[str, Any]:
    if sampling_profile and sampling_profile not in {
        _MEETI_BLIND_PILOT_64,
        _MEETI_BLIND_IMPORTANT_MULTI_128,
    }:
        raise ValueError(f"unsupported sampling profile: {sampling_profile}")
    if sampling_profile == _MEETI_BLIND_PILOT_64:
        if severity_counts and severity_counts != _MEETI_BLIND_PILOT_64_SEVERITY_COUNTS:
            raise ValueError(
                "sampling profile severity counts are fixed and cannot be overridden"
            )
        severity_counts = dict(_MEETI_BLIND_PILOT_64_SEVERITY_COUNTS)
    elif sampling_profile == _MEETI_BLIND_IMPORTANT_MULTI_128:
        if (
            severity_counts
            and severity_counts
            != _MEETI_BLIND_IMPORTANT_MULTI_128_SEVERITY_COUNTS
        ):
            raise ValueError(
                "important-multi-128 severity counts are fixed and cannot be overridden"
            )
        if seed != _MEETI_BLIND_IMPORTANT_MULTI_128_SEED:
            raise ValueError(
                "important-multi-128 seed is fixed at "
                f"{_MEETI_BLIND_IMPORTANT_MULTI_128_SEED}"
            )
        if coverage_counts:
            raise ValueError(
                "important-multi-128 coverage minima are fixed by the profile"
            )
        if multi_concept_min != _MEETI_BLIND_IMPORTANT_MULTI_128_MIN_DIAGNOSES:
            raise ValueError(
                "important-multi-128 canonical diagnosis minimum is fixed at "
                f"{_MEETI_BLIND_IMPORTANT_MULTI_128_MIN_DIAGNOSES}"
            )
        if exposure_denylist_path is None:
            raise ValueError(
                "important-multi-128 requires the frozen preselection exposure denylist"
            )
        if inference_output_path is None or selection_report_path is None:
            raise ValueError(
                "important-multi-128 requires both inference and selection-report outputs"
            )
        severity_counts = dict(_MEETI_BLIND_IMPORTANT_MULTI_128_SEVERITY_COUNTS)
    coverage_counts = dict(coverage_counts or {})
    unknown_tags = sorted(set(coverage_counts) - _SUPPORTED_COVERAGE_TAGS)
    if unknown_tags:
        raise ValueError(f"unsupported coverage tags: {', '.join(unknown_tags)}")
    if multi_concept_min < 2:
        raise ValueError("multi_concept_min must be at least 2")

    manifest_path = manifest_path.resolve()
    output_path = output_path.resolve()
    if exposure_denylist_path is not None:
        exposure_denylist_path = exposure_denylist_path.resolve()
    if inference_output_path is not None:
        inference_output_path = inference_output_path.resolve()
        if inference_output_path == output_path:
            raise ValueError("gold and inference manifests must use different paths")
    if selection_report_path is not None:
        selection_report_path = selection_report_path.resolve()
        if inference_output_path is None:
            raise ValueError("selection report requires an inference manifest")
    elif inference_output_path is not None:
        selection_report_path = output_path.with_name(
            f"{output_path.stem}.selection-report.json"
        )
    if selection_report_path is not None and selection_report_path in {
        output_path,
        inference_output_path,
    }:
        raise ValueError("selection report must use a distinct path")
    protected_inputs = {manifest_path}
    if exposure_denylist_path is not None:
        protected_inputs.add(exposure_denylist_path)
    requested_outputs = {output_path}
    if inference_output_path is not None:
        requested_outputs.add(inference_output_path)
    if selection_report_path is not None:
        requested_outputs.add(selection_report_path)
    collided_inputs = sorted(protected_inputs & requested_outputs)
    if collided_inputs:
        raise ValueError(
            "output paths must not overwrite source or exposure-denylist inputs: "
            f"{collided_inputs[0]}"
        )

    source_manifest_sha256 = _sha256(manifest_path)
    source = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = source.get("cases")
    if not isinstance(cases, list):
        raise ValueError("source manifest has no cases array")

    denylisted_ids, denylist_metadata = _read_exposure_denylist(exposure_denylist_path)
    source_rows = [dict(row) for row in cases if isinstance(row, dict)]
    source_identities = {_case_identity(row) for row in source_rows}
    if sampling_profile == _MEETI_BLIND_IMPORTANT_MULTI_128:
        _validate_important_multi_128_inputs(
            source_rows=source_rows,
            source_identities=source_identities,
            source_manifest_sha256=source_manifest_sha256,
            denylisted_ids=denylisted_ids,
            denylist_metadata=denylist_metadata,
        )
    matched_denylisted_ids = source_identities & denylisted_ids
    eligible_before_denylist = sum(
        str(row.get("expected_severity") or "") in severity_counts
        for row in source_rows
    )
    excluded_eligible_ids = {
        _case_identity(row)
        for row in source_rows
        if str(row.get("expected_severity") or "") in severity_counts
        and _case_identity(row) in denylisted_ids
    }

    eligible_rows = [
        row for row in source_rows if _case_identity(row) not in denylisted_ids
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in eligible_rows:
        severity = str(row.get("expected_severity") or "")
        if severity in severity_counts:
            groups.setdefault(severity, []).append(row)

    profile_metadata: dict[str, Any] = {}
    if sampling_profile == _MEETI_BLIND_PILOT_64:
        selected, profile_metadata = _select_meeti_blind_pilot_64(
            eligible_rows,
            seed=seed,
            multi_concept_min=multi_concept_min,
        )
    elif sampling_profile == _MEETI_BLIND_IMPORTANT_MULTI_128:
        selected, profile_metadata = _select_meeti_blind_important_multi_128(
            eligible_rows,
            seed=seed,
        )
    else:
        ranked_by_severity: dict[str, list[dict[str, Any]]] = {}
        for severity, count in severity_counts.items():
            available = sorted(
                groups.get(severity, []),
                key=lambda row: _stable_case_rank(row, seed),
            )
            if len(available) < count:
                raise ValueError(
                    f"severity {severity!r} has {len(available)} cases, needs {count}"
                )
            ranked_by_severity[severity] = available

        selected_by_severity = _coverage_first_selection(
            ranked_by_severity=ranked_by_severity,
            severity_counts=severity_counts,
            coverage_counts=coverage_counts,
            multi_concept_min=multi_concept_min,
            seed=seed,
        )

        selected = []
        severity_order = list(severity_counts)
        for index in range(max(severity_counts.values())):
            for severity in severity_order:
                rows = selected_by_severity[severity]
                if index < len(rows):
                    selected.append(rows[index])

    input_image_records: list[dict[str, str]] = []
    for row in selected:
        image = row.get("image")
        if not isinstance(image, str):
            raise ValueError("selected case has no image path")
        source_image = (manifest_path.parent / image).resolve()
        if not source_image.is_file():
            raise ValueError(f"selected image does not exist: {source_image}")
        input_image_records.append(
            {
                "case_identity": _case_identity(row),
                "image_sha256": _sha256(source_image),
            }
        )

    input_image_order_sha256 = _canonical_sha256(input_image_records)
    unique_input_image_sha256 = len(
        {record["image_sha256"] for record in input_image_records}
    )
    if (
        sampling_profile == _MEETI_BLIND_IMPORTANT_MULTI_128
        and unique_input_image_sha256 != len(input_image_records)
    ):
        raise ValueError(
            "important-multi-128 selected duplicate input image bytes"
        )
    if profile_metadata:
        profile_metadata["input_image_order_sha256"] = input_image_order_sha256
        profile_metadata["unique_input_image_sha256"] = unique_input_image_sha256

    labels = [str(row.get("label") or "") for row in selected]
    if len(labels) != len(set(labels)):
        raise ValueError("selected case labels are not unique")
    if sampling_profile == _MEETI_BLIND_IMPORTANT_MULTI_128:
        overlap = set(labels) & denylisted_ids
        if overlap:
            raise RuntimeError(
                "important-multi-128 selected a preselection-denylisted case"
            )
        if any(_MEETI_CASE_ID_PATTERN.fullmatch(label) is None for label in labels):
            raise ValueError(
                "important-multi-128 selected a non-canonical case identity"
            )

    counts = _selection_counts(selected, multi_concept_min=multi_concept_min)
    if profile_metadata:
        counts["by_study_stratum"] = profile_metadata["selected_by_stratum"]
    population = {
        "source_cases": len(source_rows),
        "eligible_before_denylist": eligible_before_denylist,
        "excluded_by_denylist": len(excluded_eligible_ids),
        "eligible_after_denylist": eligible_before_denylist
        - len(excluded_eligible_ids),
        "denylist_entries_matched_in_source": len(matched_denylisted_ids),
        "denylist_entries_not_in_source": len(denylisted_ids - source_identities),
    }
    selection = {
        "mode": "deterministic_severity_stratified_subset",
        "source_manifest": os.path.relpath(
            manifest_path.resolve(),
            output_path.parent.resolve(),
        ).replace(os.sep, "/"),
        "source_manifest_sha256": source_manifest_sha256,
        "seed": seed,
        "severity_counts": severity_counts,
        "coverage_counts": coverage_counts,
        "multi_concept_min": multi_concept_min,
        "input_image_order_sha256": input_image_order_sha256,
        "population": population,
    }
    if sampling_profile:
        selection["sampling_profile"] = sampling_profile
        selection["sampling_profile_metadata"] = profile_metadata
    if denylist_metadata is not None and exposure_denylist_path is not None:
        selection["exposure_denylist"] = {
            "path": _relative_path(exposure_denylist_path, output_path.parent),
            **denylist_metadata,
        }

    selected_identities = [_case_identity(row) for row in selected]
    identity_order_sha256 = _canonical_sha256(selected_identities)
    pair_payload = {
        "source_manifest_sha256": source_manifest_sha256,
        "seed": seed,
        "severity_counts": severity_counts,
        "coverage_counts": coverage_counts,
        "multi_concept_min": multi_concept_min,
        "sampling_profile": sampling_profile,
        "denylist_case_ids_sha256": (
            denylist_metadata["case_ids_sha256"]
            if denylist_metadata is not None
            else None
        ),
        "case_identity_order_sha256": identity_order_sha256,
        "input_image_order_sha256": input_image_order_sha256,
    }
    if profile_metadata.get("profile_definition_sha256"):
        pair_payload["sampling_profile_definition_sha256"] = profile_metadata[
            "profile_definition_sha256"
        ]
    pair_id = _canonical_sha256(pair_payload)

    if inference_output_path is not None and selection_report_path is not None:
        selection.update(
            {
                "manifest_role": "gold",
                "pair_id": pair_id,
                "case_identity_order_sha256": identity_order_sha256,
                "input_image_order_sha256": input_image_order_sha256,
                "selection_report": _relative_path(
                    selection_report_path, output_path.parent
                ),
            }
        )

    result = _build_manifest(
        source=source,
        selected=selected,
        source_manifest_path=manifest_path,
        output_path=output_path,
        selection=selection,
        counts=counts,
    )
    inference_result: dict[str, Any] | None = None
    if inference_output_path is not None and selection_report_path is not None:
        inference_result = _build_inference_manifest(
            source=source,
            selected=selected,
            source_manifest_path=manifest_path,
            output_path=inference_output_path,
            pair_id=pair_id,
            identity_order_sha256=identity_order_sha256,
            input_image_order_sha256=input_image_order_sha256,
        )
        _assert_answer_free_manifest(inference_result)
        _assert_paired_case_order(result, inference_result)

    _write_json(output_path, result)

    if (
        inference_output_path is not None
        and selection_report_path is not None
        and inference_result is not None
    ):
        _write_json(inference_output_path, inference_result)

        report = _build_selection_report(
            report_path=selection_report_path,
            source_manifest_path=manifest_path,
            gold_output_path=output_path,
            inference_output_path=inference_output_path,
            exposure_denylist_path=exposure_denylist_path,
            denylist_metadata=denylist_metadata,
            pair_id=pair_id,
            identity_order_sha256=identity_order_sha256,
            input_image_order_sha256=input_image_order_sha256,
            selected_identities=selected_identities,
            seed=seed,
            severity_counts=severity_counts,
            coverage_counts=coverage_counts,
            multi_concept_min=multi_concept_min,
            sampling_profile=sampling_profile,
            profile_metadata=profile_metadata,
            population=population,
            counts=counts,
        )
        _write_json(selection_report_path, report)

    return result


def _selection_counts(
    selected: list[dict[str, Any]],
    *,
    multi_concept_min: int,
) -> dict[str, Any]:
    return {
        "cases": len(selected),
        "by_severity": dict(
            sorted(Counter(row["expected_severity"] for row in selected).items())
        ),
        "by_coverage": {
            tag: sum(
                tag in _coverage_tags(row, multi_concept_min=multi_concept_min)
                for row in selected
            )
            for tag in sorted(_SUPPORTED_COVERAGE_TAGS)
        },
    }


def _build_manifest(
    *,
    source: dict[str, Any],
    selected: list[dict[str, Any]],
    source_manifest_path: Path,
    output_path: Path,
    selection: dict[str, Any],
    counts: dict[str, Any],
) -> dict[str, Any]:
    result = {
        key: value
        for key, value in source.items()
        if key not in {"selection", "counts", "cases"}
    }
    _relocate_waveform_registry(
        result,
        source_manifest_path=source_manifest_path,
        output_path=output_path,
    )
    result["selection"] = selection
    result["counts"] = counts
    result["cases"] = _relocate_cases(
        selected,
        source_manifest_path=source_manifest_path,
        output_path=output_path,
    )
    return result


def _build_inference_manifest(
    *,
    source: dict[str, Any],
    selected: list[dict[str, Any]],
    source_manifest_path: Path,
    output_path: Path,
    pair_id: str,
    identity_order_sha256: str,
    input_image_order_sha256: str,
) -> dict[str, Any]:
    result = {
        key: value
        for key, value in source.items()
        if key in _INFERENCE_TOP_LEVEL_FIELDS
        and key not in {"selection", "counts", "cases"}
        and key not in _INFERENCE_TOP_LEVEL_OMIT_FIELDS
        and not _is_answer_field(key)
    }
    _relocate_waveform_registry(
        result,
        source_manifest_path=source_manifest_path,
        output_path=output_path,
    )
    result["selection"] = {
        "mode": "deterministic_blind_inference_subset",
        "manifest_role": "inference",
        "pair_id": pair_id,
        "case_identity_order_sha256": identity_order_sha256,
        "input_image_order_sha256": input_image_order_sha256,
    }
    result["counts"] = {"cases": len(selected)}
    relocated = _relocate_cases(
        selected,
        source_manifest_path=source_manifest_path,
        output_path=output_path,
    )
    result["cases"] = [
        {key: value for key, value in row.items() if key in _INFERENCE_CASE_FIELDS}
        for row in relocated
    ]
    return result


def _build_selection_report(
    *,
    report_path: Path,
    source_manifest_path: Path,
    gold_output_path: Path,
    inference_output_path: Path,
    exposure_denylist_path: Path | None,
    denylist_metadata: dict[str, Any] | None,
    pair_id: str,
    identity_order_sha256: str,
    input_image_order_sha256: str,
    selected_identities: list[str],
    seed: int,
    severity_counts: dict[str, int],
    coverage_counts: dict[str, int],
    multi_concept_min: int,
    sampling_profile: str,
    profile_metadata: dict[str, Any],
    population: dict[str, int],
    counts: dict[str, Any],
) -> dict[str, Any]:
    denylist_report = None
    if denylist_metadata is not None and exposure_denylist_path is not None:
        denylist_report = {
            "path": _relative_path(exposure_denylist_path, report_path.parent),
            **denylist_metadata,
        }
    return {
        "schema_version": 1,
        "pair_id": pair_id,
        "source_manifest": {
            "path": _relative_path(source_manifest_path, report_path.parent),
            "sha256": _sha256(source_manifest_path),
        },
        "sampling": {
            "mode": "deterministic_severity_stratified_subset",
            "seed": seed,
            "severity_counts": severity_counts,
            "coverage_counts": coverage_counts,
            "multi_concept_min": multi_concept_min,
            "sampling_profile": sampling_profile or None,
            "sampling_profile_metadata": profile_metadata or None,
            "exposure_denylist": denylist_report,
            "population": population,
            "selected": {
                **counts,
                "case_identities": selected_identities,
                "case_identity_order_sha256": identity_order_sha256,
                "input_image_order_sha256": input_image_order_sha256,
            },
        },
        "manifests": {
            "gold": {
                "path": _relative_path(gold_output_path, report_path.parent),
                "sha256": _sha256(gold_output_path),
            },
            "inference": {
                "path": _relative_path(inference_output_path, report_path.parent),
                "sha256": _sha256(inference_output_path),
            },
        },
    }


def _relocate_cases(
    selected: list[dict[str, Any]],
    *,
    source_manifest_path: Path,
    output_path: Path,
) -> list[dict[str, Any]]:
    relocated: list[dict[str, Any]] = []
    for original in selected:
        row = dict(original)
        source_image = (source_manifest_path.parent / str(row["image"])).resolve()
        row["image"] = _relative_path(source_image, output_path.parent)
        relocated.append(row)
    return relocated


def _relocate_waveform_registry(
    result: dict[str, Any],
    *,
    source_manifest_path: Path,
    output_path: Path,
) -> None:
    waveform_registry = result.get("waveform_registry")
    if not isinstance(waveform_registry, dict) or not isinstance(
        waveform_registry.get("path"), str
    ):
        return
    source_registry = (
        source_manifest_path.parent / str(waveform_registry["path"])
    ).resolve()
    if not source_registry.is_file():
        raise ValueError(f"source waveform registry does not exist: {source_registry}")
    result["waveform_registry"] = {
        **waveform_registry,
        "path": _relative_path(source_registry, output_path.parent),
    }


def _assert_paired_case_order(
    gold: dict[str, Any],
    inference: dict[str, Any],
) -> None:
    gold_ids = [_case_identity(row) for row in gold["cases"]]
    inference_ids = [_case_identity(row) for row in inference["cases"]]
    if gold_ids != inference_ids:
        raise RuntimeError("gold and inference manifest case order/identity diverged")
    gold_selection = gold.get("selection")
    inference_selection = inference.get("selection")
    if not isinstance(gold_selection, dict) or not isinstance(
        inference_selection, dict
    ):
        raise RuntimeError("paired manifests are missing selection metadata")
    for field in (
        "pair_id",
        "case_identity_order_sha256",
        "input_image_order_sha256",
    ):
        if gold_selection.get(field) != inference_selection.get(field):
            raise RuntimeError(f"paired manifests disagree on {field}")
    computed_order_sha256 = _canonical_sha256(gold_ids)
    if gold_selection.get("case_identity_order_sha256") != computed_order_sha256:
        raise RuntimeError("paired manifest identity-order hash is invalid")


def _assert_answer_free_manifest(inference: dict[str, Any]) -> None:
    unexpected_top_level = set(inference) - _INFERENCE_TOP_LEVEL_FIELDS
    if unexpected_top_level:
        raise RuntimeError(
            "inference manifest contains non-allowlisted top-level fields: "
            f"{sorted(unexpected_top_level)}"
        )
    if _INFERENCE_TOP_LEVEL_OMIT_FIELDS & inference.keys():
        raise RuntimeError("inference manifest contains answer-bearing metadata")
    selection = inference.get("selection")
    allowed_selection_fields = {
        "case_identity_order_sha256",
        "input_image_order_sha256",
        "manifest_role",
        "mode",
        "pair_id",
    }
    if not isinstance(selection, dict) or set(selection) != allowed_selection_fields:
        raise RuntimeError("inference selection metadata is not the minimal allowlist")
    if selection.get("manifest_role") != "inference":
        raise RuntimeError("inference manifest role is invalid")
    _assert_no_nested_answer_fields(inference)
    cases = inference.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("inference manifest cases must be an array")
    for row in cases:
        if not isinstance(row, dict):
            raise RuntimeError("inference manifest case must be an object")
        unexpected_fields = set(row) - _INFERENCE_CASE_FIELDS
        if unexpected_fields:
            raise RuntimeError(
                "inference case contains non-allowlisted fields: "
                f"{sorted(unexpected_fields)}"
            )
        if not isinstance(row.get("image"), str) or not isinstance(
            row.get("label"), str
        ):
            raise RuntimeError("inference case requires image and label identity fields")
        if any(_is_answer_field(key) for key in row):
            raise RuntimeError("inference case contains an answer field")


def _is_answer_field(name: str) -> bool:
    return name in _INFERENCE_ANSWER_FIELDS or name.startswith("expected_")


def _assert_no_nested_answer_fields(value: Any, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = key.casefold()
            if _is_answer_field(key) or any(
                marker in normalized
                for marker in ("answer", "diagnos", "ground_truth")
            ):
                raise RuntimeError(
                    f"inference manifest contains answer-bearing field at {path}.{key}"
                )
            _assert_no_nested_answer_fields(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_nested_answer_fields(child, path=f"{path}[{index}]")


def _relative_path(path: Path, parent: Path) -> str:
    return Path(os.path.relpath(path.resolve(), parent.resolve())).as_posix()


def _coverage_first_selection(
    *,
    ranked_by_severity: dict[str, list[dict[str, Any]]],
    severity_counts: dict[str, int],
    coverage_counts: dict[str, int],
    multi_concept_min: int,
    seed: int,
) -> dict[str, list[dict[str, Any]]]:
    selected: dict[str, list[dict[str, Any]]] = {
        severity: [] for severity in severity_counts
    }
    selected_labels: set[str] = set()

    def add(row: dict[str, Any]) -> None:
        severity = str(row.get("expected_severity") or "")
        selected[severity].append(row)
        selected_labels.add(_case_identity(row))

    while True:
        actual = _coverage_totals(
            (row for rows in selected.values() for row in rows),
            multi_concept_min=multi_concept_min,
        )
        unmet = {
            tag: count - actual.get(tag, 0)
            for tag, count in coverage_counts.items()
            if actual.get(tag, 0) < count
        }
        if not unmet:
            break

        candidates = [
            row
            for severity, rows in ranked_by_severity.items()
            if len(selected[severity]) < severity_counts[severity]
            for row in rows
            if _case_identity(row) not in selected_labels
            and _coverage_tags(row, multi_concept_min=multi_concept_min) & unmet.keys()
        ]
        if not candidates:
            missing = ", ".join(
                f"{tag}={remaining}" for tag, remaining in sorted(unmet.items())
            )
            raise ValueError(
                "coverage requirements cannot fit within severity quotas; "
                f"remaining: {missing}"
            )

        eligible_counts = {
            tag: sum(
                tag in _coverage_tags(row, multi_concept_min=multi_concept_min)
                for row in candidates
            )
            for tag in unmet
        }

        add(
            min(
                candidates,
                key=partial(
                    _coverage_candidate_key,
                    unmet_tags=frozenset(unmet),
                    eligible_counts=eligible_counts,
                    multi_concept_min=multi_concept_min,
                    seed=seed,
                ),
            )
        )

    for severity, target_count in severity_counts.items():
        for row in ranked_by_severity[severity]:
            if len(selected[severity]) >= target_count:
                break
            if _case_identity(row) not in selected_labels:
                add(row)

    return {
        severity: sorted(rows, key=lambda row: _stable_case_rank(row, seed))
        for severity, rows in selected.items()
    }


def _select_meeti_blind_pilot_64(
    rows: list[dict[str, Any]],
    *,
    seed: int,
    multi_concept_min: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        name: [] for name, _count in _MEETI_BLIND_PILOT_64_STRATA
    }
    for row in rows:
        stratum = _meeti_blind_pilot_stratum(
            row, multi_concept_min=multi_concept_min
        )
        if stratum:
            grouped[stratum].append(row)
    for name in grouped:
        grouped[name].sort(key=lambda row: _stable_case_rank(row, seed))

    selected_by_stratum: dict[str, list[dict[str, Any]]] = {}
    for name, count in _MEETI_BLIND_PILOT_64_STRATA:
        available = grouped[name]
        if len(available) < count:
            raise ValueError(
                f"sampling profile stratum {name!r} has {len(available)}, needs {count}"
            )
        selected_by_stratum[name] = available[:count]

    selected: list[dict[str, Any]] = []
    for index in range(max(count for _name, count in _MEETI_BLIND_PILOT_64_STRATA)):
        for name, _count in _MEETI_BLIND_PILOT_64_STRATA:
            stratum_rows = selected_by_stratum[name]
            if index < len(stratum_rows):
                selected.append(stratum_rows[index])

    cant_miss_available = len(grouped["critical_cant_miss"])
    cant_miss_selected = len(selected_by_stratum["critical_cant_miss"])
    return selected, {
        "eligible_by_stratum": {
            name: len(grouped[name]) for name, _count in _MEETI_BLIND_PILOT_64_STRATA
        },
        "selected_by_stratum": {
            name: len(selected_by_stratum[name])
            for name, _count in _MEETI_BLIND_PILOT_64_STRATA
        },
        "sealed_critical_cant_miss_remaining": (
            cant_miss_available - cant_miss_selected
        ),
    }


def _meeti_blind_pilot_stratum(
    row: dict[str, Any], *, multi_concept_min: int
) -> str:
    severity = str(row.get("expected_severity") or "")
    status = str(row.get("label_status") or "")
    concepts = row.get("concepts")
    multi = isinstance(concepts, list) and len(concepts) >= multi_concept_min
    if severity == "normal" and status == "asserted":
        return "normal_asserted"
    if severity == "warning" and status == "asserted":
        return "warning_asserted_multi" if multi else "warning_asserted_single"
    if severity == "warning" and status == "partially_uncertain":
        return "warning_partial_multi" if multi else "warning_partial_single"
    if severity == "critical":
        return "critical_cant_miss" if row.get("cant_miss") else "critical_non_cant_miss"
    return ""


def _validate_important_multi_128_inputs(
    *,
    source_rows: list[dict[str, Any]],
    source_identities: set[str],
    source_manifest_sha256: str,
    denylisted_ids: set[str],
    denylist_metadata: dict[str, Any] | None,
) -> None:
    if (
        hashlib.sha256(
            _MEETI_BLIND_IMPORTANT_MULTI_128_SEED_MATERIAL.encode("utf-8")
        ).hexdigest()
        != _MEETI_BLIND_IMPORTANT_MULTI_128_SEED_MATERIAL_SHA256
    ):
        raise RuntimeError("important-multi-128 seed material integrity check failed")
    derived_seed = int(
        _MEETI_BLIND_IMPORTANT_MULTI_128_SEED_MATERIAL_SHA256[:8], 16
    )
    if derived_seed != _MEETI_BLIND_IMPORTANT_MULTI_128_SEED:
        raise RuntimeError("important-multi-128 seed derivation check failed")
    if source_manifest_sha256 != _MEETI_BLIND_IMPORTANT_MULTI_128_SOURCE_SHA256:
        raise ValueError(
            "important-multi-128 source manifest hash mismatch; refusing to "
            "silently change the frozen population"
        )
    if len(source_rows) != 9922:
        raise ValueError("important-multi-128 source must contain exactly 9922 cases")
    if len(source_identities) != len(source_rows) or "" in source_identities:
        raise ValueError("important-multi-128 source case identities must be unique")
    invalid_source_ids = sorted(
        identity
        for identity in source_identities
        if _MEETI_CASE_ID_PATTERN.fullmatch(identity) is None
    )
    if invalid_source_ids:
        raise ValueError(
            "important-multi-128 source contains a non-canonical case identity: "
            f"{invalid_source_ids[0]}"
        )
    if denylist_metadata is None:
        raise ValueError("important-multi-128 denylist metadata is missing")
    expected_denylist = {
        "sha256": _MEETI_BLIND_IMPORTANT_MULTI_128_DENYLIST_SHA256,
        "case_ids_sha256": (
            _MEETI_BLIND_IMPORTANT_MULTI_128_DENYLIST_CASE_IDS_SHA256
        ),
        "entries": _MEETI_BLIND_IMPORTANT_MULTI_128_DENYLIST_ENTRIES,
    }
    if denylist_metadata != expected_denylist:
        raise ValueError(
            "important-multi-128 preselection denylist is not the frozen 1230-case "
            "snapshot"
        )
    unmatched = denylisted_ids - source_identities
    if unmatched:
        raise ValueError(
            "important-multi-128 denylist contains identities outside the frozen "
            "source population"
        )


def _important_multi_128_profile_definition() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profile": _MEETI_BLIND_IMPORTANT_MULTI_128,
        "study_intent": {
            "design": "purposefully gold-enriched multi-finding stress cohort",
            "estimand_limit": (
                "not prevalence-weighted and must not be reported as population "
                "accuracy"
            ),
        },
        "seed": {
            "value": _MEETI_BLIND_IMPORTANT_MULTI_128_SEED,
            "material": _MEETI_BLIND_IMPORTANT_MULTI_128_SEED_MATERIAL,
            "material_sha256": (
                _MEETI_BLIND_IMPORTANT_MULTI_128_SEED_MATERIAL_SHA256
            ),
            "derivation": "unsigned big-endian integer from first 8 SHA-256 hex digits",
        },
        "eligibility": {
            "label_status": ["asserted", "partially_uncertain"],
            "ungradable_reasons": "must be empty",
            "canonical_diagnosis_minimum": (
                _MEETI_BLIND_IMPORTANT_MULTI_128_MIN_DIAGNOSES
            ),
            "important_diagnosis_required": True,
            "expected_severity": {
                "acute_risk": "critical",
                "all_other_tiers": "warning",
            },
            "report": "non-empty",
        },
        "canonical_diagnosis_rules": {
            "remove_non_diagnostic": ["normal", "sinus"],
            "prefer_specific": {
                "old_infarct": "infarct",
                "high_risk_long_qt": "long_qt",
            },
            "uncertain_concepts_count_as_diagnoses": False,
        },
        "tier_precedence": list(_MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER),
        "important_diagnosis_ontology": {
            tier: sorted(_MEETI_BLIND_IMPORTANT_MULTI_128_ONTOLOGY[tier])
            for tier in _MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER
        },
        "acute_case_level_signals": {
            field: sorted(values)
            for field, values in (
                _MEETI_BLIND_IMPORTANT_MULTI_128_ACUTE_SIGNALS.items()
            )
        },
        "status_quotas": _MEETI_BLIND_IMPORTANT_MULTI_128_STATUS_QUOTAS,
        "coverage_minima": _MEETI_BLIND_IMPORTANT_MULTI_128_COVERAGE_MINIMA,
        "target_axis_minima": dict.fromkeys(
            _MEETI_BLIND_IMPORTANT_MULTI_128_AXES,
            _MEETI_BLIND_IMPORTANT_MULTI_128_AXIS_MINIMUM,
        ),
        "diversity": {
            "normalized_report_cap": (
                _MEETI_BLIND_IMPORTANT_MULTI_128_REPORT_CAP
            ),
            "canonical_diagnosis_signature_cap": (
                _MEETI_BLIND_IMPORTANT_MULTI_128_SIGNATURE_CAP
            ),
            "exact_input_image_sha256_cap": 1,
        },
        "input_binding": (
            "ordered case identity plus SHA-256 of the exact image bytes is bound "
            "into the pair id"
        ),
    }


def _canonical_diagnoses(row: dict[str, Any]) -> tuple[str, ...]:
    concepts = row.get("concepts")
    if not isinstance(concepts, list):
        return ()
    diagnoses = {
        str(concept).strip()
        for concept in concepts
        if isinstance(concept, str) and str(concept).strip()
    }
    diagnoses.difference_update(_string_values(row, "uncertain_concepts"))
    diagnoses.difference_update({"normal", "sinus"})
    if "old_infarct" in diagnoses:
        diagnoses.discard("infarct")
    if "high_risk_long_qt" in diagnoses:
        diagnoses.discard("long_qt")
    return tuple(sorted(diagnoses))


def _string_values(row: dict[str, Any], field: str) -> tuple[str, ...]:
    value = row.get(field)
    if not isinstance(value, list):
        return ()
    return tuple(
        str(item).strip()
        for item in value
        if isinstance(item, str) and str(item).strip()
    )


def _important_multi_128_tier(row: dict[str, Any]) -> str:
    diagnoses = frozenset(_canonical_diagnoses(row))
    if any(
        set(_string_values(row, field)) & allowed
        for field, allowed in _MEETI_BLIND_IMPORTANT_MULTI_128_ACUTE_SIGNALS.items()
    ):
        return "acute_risk"
    for tier in _MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER:
        if diagnoses & _MEETI_BLIND_IMPORTANT_MULTI_128_ONTOLOGY[tier]:
            return tier
    return ""


def _normalized_report(row: dict[str, Any]) -> str:
    report = row.get("report")
    if not isinstance(report, str):
        return ""
    return " ".join(report.casefold().split())


def _important_multi_128_tokens(row: dict[str, Any]) -> set[str]:
    tokens = set(_canonical_diagnoses(row))
    if _string_values(row, "cant_miss"):
        tokens.add("cant_miss")
    tokens.update(
        f"urgent:{concern}" for concern in _string_values(row, "urgent_concerns")
    )
    tokens.update(f"axis:{axis}" for axis in _string_values(row, "target_axes"))
    return tokens


def _important_multi_128_eligibility_tier(row: dict[str, Any]) -> str:
    status = str(row.get("label_status") or "")
    if status not in {"asserted", "partially_uncertain"}:
        return ""
    if _string_values(row, "ungradable_reasons"):
        return ""
    if any(
        set(_string_values(row, field)) - allowed
        for field, allowed in _MEETI_BLIND_IMPORTANT_MULTI_128_ACUTE_SIGNALS.items()
    ):
        return ""
    if (
        len(_canonical_diagnoses(row))
        < _MEETI_BLIND_IMPORTANT_MULTI_128_MIN_DIAGNOSES
    ):
        return ""
    if not _normalized_report(row):
        return ""
    tier = _important_multi_128_tier(row)
    if not tier:
        return ""
    expected_severity = "critical" if tier == "acute_risk" else "warning"
    if str(row.get("expected_severity") or "") != expected_severity:
        return ""
    return tier


def _important_multi_128_candidate_key(
    row: dict[str, Any],
    *,
    unmet_tokens: frozenset[str],
    eligible_counts: dict[str, int],
    tier: str,
    available_by_status: Counter[str],
    selected_cells: Counter[tuple[str, str]],
    seed: int,
) -> tuple[float, int, int, str]:
    tokens = _important_multi_128_tokens(row)
    useful = tokens & unmet_tokens
    rarity = sum(1.0 / eligible_counts[token] for token in useful)
    status = str(row.get("label_status") or "")
    remaining_cell = (
        _MEETI_BLIND_IMPORTANT_MULTI_128_STATUS_QUOTAS[tier][status]
        - selected_cells[(tier, status)]
    )
    cell_slack = available_by_status[status] - remaining_cell
    return (-rarity, cell_slack, -len(useful), _stable_case_rank(row, seed))


def _select_meeti_blind_important_multi_128(
    rows: list[dict[str, Any]],
    *,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if seed != _MEETI_BLIND_IMPORTANT_MULTI_128_SEED:
        raise ValueError(
            "important-multi-128 seed is fixed at "
            f"{_MEETI_BLIND_IMPORTANT_MULTI_128_SEED}"
        )

    grouped: dict[str, list[dict[str, Any]]] = {
        tier: [] for tier in _MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER
    }
    for row in rows:
        tier = _important_multi_128_eligibility_tier(row)
        if tier:
            grouped[tier].append(row)
    for tier in grouped:
        grouped[tier].sort(key=lambda row: _stable_case_rank(row, seed))

    selected_by_tier: dict[str, list[dict[str, Any]]] = {
        tier: [] for tier in _MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER
    }
    selected_ids: set[str] = set()
    selected_reports: set[str] = set()
    selected_signatures: Counter[tuple[str, ...]] = Counter()
    selected_cells: Counter[tuple[str, str]] = Counter()

    def fits(row: dict[str, Any], tier: str) -> bool:
        identity = _case_identity(row)
        status = str(row.get("label_status") or "")
        signature = _canonical_diagnoses(row)
        return (
            identity not in selected_ids
            and selected_cells[(tier, status)]
            < _MEETI_BLIND_IMPORTANT_MULTI_128_STATUS_QUOTAS[tier][status]
            and _normalized_report(row) not in selected_reports
            and selected_signatures[signature]
            < _MEETI_BLIND_IMPORTANT_MULTI_128_SIGNATURE_CAP
        )

    def add(row: dict[str, Any], tier: str) -> None:
        identity = _case_identity(row)
        status = str(row.get("label_status") or "")
        signature = _canonical_diagnoses(row)
        selected_by_tier[tier].append(row)
        selected_ids.add(identity)
        selected_reports.add(_normalized_report(row))
        selected_signatures[signature] += 1
        selected_cells[(tier, status)] += 1

    for tier in _MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER:
        minima = _MEETI_BLIND_IMPORTANT_MULTI_128_COVERAGE_MINIMA[tier]
        while True:
            totals = Counter(
                token
                for row in selected_by_tier[tier]
                for token in _important_multi_128_tokens(row)
            )
            unmet = {
                token: count - totals[token]
                for token, count in minima.items()
                if totals[token] < count
            }
            if not unmet:
                break
            candidates = [
                row
                for row in grouped[tier]
                if fits(row, tier)
                and _important_multi_128_tokens(row) & unmet.keys()
            ]
            if not candidates:
                missing = ", ".join(
                    f"{token}={remaining}"
                    for token, remaining in sorted(unmet.items())
                )
                raise ValueError(
                    f"important-multi-128 tier {tier!r} cannot satisfy fixed "
                    f"coverage minima; remaining: {missing}"
                )
            eligible_counts = {
                token: sum(
                    token in _important_multi_128_tokens(row) for row in candidates
                )
                for token in unmet
            }
            available_by_status = Counter(
                str(row.get("label_status") or "") for row in candidates
            )
            add(
                min(
                    candidates,
                    key=partial(
                        _important_multi_128_candidate_key,
                        unmet_tokens=frozenset(unmet),
                        eligible_counts=eligible_counts,
                        tier=tier,
                        available_by_status=available_by_status,
                        selected_cells=selected_cells,
                        seed=seed,
                    ),
                ),
                tier,
            )

        for status, quota in _MEETI_BLIND_IMPORTANT_MULTI_128_STATUS_QUOTAS[
            tier
        ].items():
            for row in grouped[tier]:
                if selected_cells[(tier, status)] >= quota:
                    break
                if str(row.get("label_status") or "") == status and fits(row, tier):
                    add(row, tier)
            if selected_cells[(tier, status)] != quota:
                raise ValueError(
                    f"important-multi-128 tier/status {tier}/{status} has "
                    f"{selected_cells[(tier, status)]}, needs {quota} after "
                    "diversity caps"
                )

    selected: list[dict[str, Any]] = []
    selected_by_tier_sorted = {
        tier: sorted(rows_for_tier, key=lambda row: _stable_case_rank(row, seed))
        for tier, rows_for_tier in selected_by_tier.items()
    }
    for index in range(max(map(len, selected_by_tier_sorted.values()))):
        for tier in _MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER:
            rows_for_tier = selected_by_tier_sorted[tier]
            if index < len(rows_for_tier):
                selected.append(rows_for_tier[index])

    _assert_important_multi_128_selection(selected)
    selected_axis_counts = {
        axis: sum(axis in _string_values(row, "target_axes") for row in selected)
        for axis in _MEETI_BLIND_IMPORTANT_MULTI_128_AXES
    }
    selected_coverage = {
        tier: {
            token: sum(
                token in _important_multi_128_tokens(row)
                for row in selected_by_tier[tier]
            )
            for token in _MEETI_BLIND_IMPORTANT_MULTI_128_COVERAGE_MINIMA[tier]
        }
        for tier in _MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER
    }
    selected_by_stratum = {
        f"{tier}/{status}": selected_cells[(tier, status)]
        for tier in _MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER
        for status in _MEETI_BLIND_IMPORTANT_MULTI_128_STATUS_QUOTAS[tier]
    }
    canonical_cardinality = Counter(len(_canonical_diagnoses(row)) for row in selected)
    cant_miss_available = sum(
        bool(_string_values(row, "cant_miss")) for row in grouped["acute_risk"]
    )
    cant_miss_selected = sum(
        bool(_string_values(row, "cant_miss"))
        for row in selected_by_tier["acute_risk"]
    )
    profile_definition = _important_multi_128_profile_definition()
    return selected, {
        "profile_definition": profile_definition,
        "profile_definition_sha256": _canonical_sha256(profile_definition),
        "eligible_after_profile_filters": sum(map(len, grouped.values())),
        "eligible_by_tier": {
            tier: len(grouped[tier])
            for tier in _MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER
        },
        "eligible_by_tier_and_status": {
            tier: dict(
                sorted(
                    Counter(
                        str(row.get("label_status") or "") for row in grouped[tier]
                    ).items()
                )
            )
            for tier in _MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER
        },
        "selected_by_tier": {
            tier: len(selected_by_tier[tier])
            for tier in _MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER
        },
        "selected_by_stratum": selected_by_stratum,
        "selected_by_label_status": dict(
            sorted(Counter(str(row["label_status"]) for row in selected).items())
        ),
        "selected_by_severity": dict(
            sorted(Counter(str(row["expected_severity"]) for row in selected).items())
        ),
        "selected_coverage": selected_coverage,
        "selected_axis_coverage": selected_axis_counts,
        "canonical_diagnosis_cardinality": {
            str(count): cases for count, cases in sorted(canonical_cardinality.items())
        },
        "unique_normalized_reports": len(selected_reports),
        "unique_canonical_diagnosis_signatures": len(selected_signatures),
        "maximum_canonical_diagnosis_signature_frequency": max(
            selected_signatures.values()
        ),
        "critical_cant_miss_available_before_selection": cant_miss_available,
        "critical_cant_miss_selected": cant_miss_selected,
        "sealed_critical_cant_miss_remaining": (
            cant_miss_available - cant_miss_selected
        ),
        "exposure_control": {
            "preselection_denylist_locked": True,
            "preselection_denylist_entries": (
                _MEETI_BLIND_IMPORTANT_MULTI_128_DENYLIST_ENTRIES
            ),
            "selected_overlap_with_preselection_denylist": 0,
            "model_execution_status": "not_run",
            "cohort_case_status_after_construction": "exposed_reserved",
            "selected_cases_to_add_before_next_prospective_selection": len(selected),
            "next_batch_gate": (
                "union this inference manifest's case identities into the exposure "
                "denylist before selecting any prospective batch"
            ),
        },
        "independence_limit": (
            "source manifest has no patient-group field; uniqueness is enforced at "
            "case identity, normalized report, and canonical diagnosis signature levels"
        ),
    }


def _assert_important_multi_128_selection(
    selected: list[dict[str, Any]],
) -> None:
    target_cases = sum(
        sum(status_quotas.values())
        for status_quotas in _MEETI_BLIND_IMPORTANT_MULTI_128_STATUS_QUOTAS.values()
    )
    if len(selected) != target_cases:
        raise ValueError(
            f"important-multi-128 selected {len(selected)} cases, needs {target_cases}"
        )
    identities = [_case_identity(row) for row in selected]
    if len(identities) != len(set(identities)):
        raise ValueError("important-multi-128 selected duplicate case identities")
    reports = [_normalized_report(row) for row in selected]
    if "" in reports or len(reports) != len(set(reports)):
        raise ValueError(
            "important-multi-128 normalized report cap was not satisfied"
        )
    signature_counts = Counter(_canonical_diagnoses(row) for row in selected)
    if max(signature_counts.values()) > _MEETI_BLIND_IMPORTANT_MULTI_128_SIGNATURE_CAP:
        raise ValueError(
            "important-multi-128 canonical diagnosis signature cap was not satisfied"
        )

    selected_by_tier: dict[str, list[dict[str, Any]]] = {
        tier: [] for tier in _MEETI_BLIND_IMPORTANT_MULTI_128_TIER_ORDER
    }
    for row in selected:
        tier = _important_multi_128_eligibility_tier(row)
        if not tier:
            raise ValueError("important-multi-128 selected an ineligible case")
        selected_by_tier[tier].append(row)
    for tier, status_quotas in (
        _MEETI_BLIND_IMPORTANT_MULTI_128_STATUS_QUOTAS.items()
    ):
        status_counts = Counter(
            str(row.get("label_status") or "") for row in selected_by_tier[tier]
        )
        if dict(status_counts) != status_quotas:
            raise ValueError(
                f"important-multi-128 tier/status quota mismatch for {tier}: "
                f"{dict(status_counts)}"
            )
        tokens = Counter(
            token
            for row in selected_by_tier[tier]
            for token in _important_multi_128_tokens(row)
        )
        missing = {
            token: minimum - tokens[token]
            for token, minimum in (
                _MEETI_BLIND_IMPORTANT_MULTI_128_COVERAGE_MINIMA[tier].items()
            )
            if tokens[token] < minimum
        }
        if missing:
            raise ValueError(
                f"important-multi-128 coverage mismatch for {tier}: {missing}"
            )

    axis_counts = Counter(
        axis for row in selected for axis in _string_values(row, "target_axes")
    )
    missing_axes = {
        axis: _MEETI_BLIND_IMPORTANT_MULTI_128_AXIS_MINIMUM - axis_counts[axis]
        for axis in _MEETI_BLIND_IMPORTANT_MULTI_128_AXES
        if axis_counts[axis] < _MEETI_BLIND_IMPORTANT_MULTI_128_AXIS_MINIMUM
    }
    if missing_axes:
        raise ValueError(
            "important-multi-128 target-axis minima are infeasible for the selected "
            f"cohort: {missing_axes}"
        )


def _coverage_totals(
    rows: Any,
    *,
    multi_concept_min: int,
) -> Counter[str]:
    return Counter(
        tag
        for row in rows
        for tag in _coverage_tags(row, multi_concept_min=multi_concept_min)
    )


def _coverage_candidate_key(
    row: dict[str, Any],
    *,
    unmet_tags: frozenset[str],
    eligible_counts: dict[str, int],
    multi_concept_min: int,
    seed: int,
) -> tuple[float, int, str]:
    tags = _coverage_tags(row, multi_concept_min=multi_concept_min)
    useful = tags & unmet_tags
    rarity = sum(1.0 / max(1, eligible_counts[tag]) for tag in useful)
    return (-rarity, -len(useful), _stable_case_rank(row, seed))


def _coverage_tags(
    row: dict[str, Any],
    *,
    multi_concept_min: int,
) -> set[str]:
    tags: set[str] = set()
    if row.get("cant_miss"):
        tags.add("cant_miss")
    if row.get("urgent_concerns"):
        tags.add("urgent_concern")
    concepts = row.get("concepts")
    if isinstance(concepts, list) and len(concepts) >= multi_concept_min:
        tags.add("multi_concept")
    label_status = str(row.get("label_status") or "")
    if label_status in {"asserted", "partially_uncertain"}:
        tags.add(label_status)
    return tags


def _case_identity(row: dict[str, Any]) -> str:
    return str(row.get("label") or row.get("image") or "")


def _stable_case_rank(row: dict[str, Any], seed: int) -> str:
    identity = _case_identity(row)
    return hashlib.sha256(f"{seed}:{identity}".encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--output",
        "--gold-output",
        dest="output",
        type=Path,
        required=True,
        help="Gold subset output (legacy --output remains supported).",
    )
    parser.add_argument(
        "--inference-output",
        type=Path,
        help="Optional answer-free manifest paired with the gold subset.",
    )
    parser.add_argument(
        "--selection-report",
        type=Path,
        help="Paired-manifest hash and sampling report output path.",
    )
    parser.add_argument(
        "--exposure-denylist",
        type=Path,
        help="UTF-8 text file containing one previously exposed case id per line.",
    )
    parser.add_argument(
        "--severity-count",
        action="append",
        default=[],
        metavar="NAME=COUNT",
        help="Repeat for each desired expected_severity stratum.",
    )
    parser.add_argument(
        "--coverage-count",
        action="append",
        default=[],
        metavar="TAG=COUNT",
        help=(
            "Minimum coverage across the selected set. Repeat with asserted, "
            "cant_miss, multi_concept, partially_uncertain, or urgent_concern."
        ),
    )
    parser.add_argument("--multi-concept-min", type=int, default=3)
    parser.add_argument(
        "--sampling-profile",
        choices=(
            _MEETI_BLIND_PILOT_64,
            _MEETI_BLIND_IMPORTANT_MULTI_128,
        ),
        default="",
        help="Use a fixed, mutually exclusive blinded study sampling design.",
    )
    parser.add_argument("--seed", type=int, default=20260725)
    args = parser.parse_args()
    try:
        if args.severity_count:
            counts = _parse_counts(args.severity_count)
        elif args.sampling_profile:
            counts = {}
        else:
            counts = _parse_counts([])
        coverage_counts = (
            _parse_counts(args.coverage_count) if args.coverage_count else {}
        )
        result = build_subset(
            manifest_path=args.manifest.resolve(),
            output_path=args.output.resolve(),
            severity_counts=counts,
            seed=args.seed,
            coverage_counts=coverage_counts,
            multi_concept_min=args.multi_concept_min,
            exposure_denylist_path=(
                args.exposure_denylist.resolve()
                if args.exposure_denylist is not None
                else None
            ),
            inference_output_path=(
                args.inference_output.resolve()
                if args.inference_output is not None
                else None
            ),
            selection_report_path=(
                args.selection_report.resolve()
                if args.selection_report is not None
                else None
            ),
            sampling_profile=args.sampling_profile,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"Wrote {result['counts']['cases']} cases to {args.output.resolve()}")
    if args.inference_output is not None:
        print(f"Wrote blind inference manifest to {args.inference_output.resolve()}")
        report_path = args.selection_report
        if report_path is None:
            output_path = args.output.resolve()
            report_path = output_path.with_name(
                f"{output_path.stem}.selection-report.json"
            )
        print(f"Wrote selection report to {report_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
