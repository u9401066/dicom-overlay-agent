"""Build a deterministic severity-stratified subset of an eval manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
    if sampling_profile:
        if sampling_profile != _MEETI_BLIND_PILOT_64:
            raise ValueError(f"unsupported sampling profile: {sampling_profile}")
        if severity_counts and severity_counts != _MEETI_BLIND_PILOT_64_SEVERITY_COUNTS:
            raise ValueError(
                "sampling profile severity counts are fixed and cannot be overridden"
            )
        severity_counts = dict(_MEETI_BLIND_PILOT_64_SEVERITY_COUNTS)
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

    source = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = source.get("cases")
    if not isinstance(cases, list):
        raise ValueError("source manifest has no cases array")

    denylisted_ids, denylist_metadata = _read_exposure_denylist(exposure_denylist_path)
    source_rows = [dict(row) for row in cases if isinstance(row, dict)]
    source_identities = {_case_identity(row) for row in source_rows}
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

    for row in selected:
        image = row.get("image")
        if not isinstance(image, str):
            raise ValueError("selected case has no image path")
        source_image = (manifest_path.parent / image).resolve()
        if not source_image.is_file():
            raise ValueError(f"selected image does not exist: {source_image}")

    labels = [str(row.get("label") or "") for row in selected]
    if len(labels) != len(set(labels)):
        raise ValueError("selected case labels are not unique")

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
        "source_manifest_sha256": _sha256(manifest_path),
        "seed": seed,
        "severity_counts": severity_counts,
        "coverage_counts": coverage_counts,
        "multi_concept_min": multi_concept_min,
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
    pair_id = _canonical_sha256(
        {
            "source_manifest_sha256": _sha256(manifest_path),
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
        }
    )

    if inference_output_path is not None and selection_report_path is not None:
        selection.update(
            {
                "manifest_role": "gold",
                "pair_id": pair_id,
                "case_identity_order_sha256": identity_order_sha256,
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
    _write_json(output_path, result)

    if inference_output_path is not None and selection_report_path is not None:
        inference_result = _build_inference_manifest(
            source=source,
            selected=selected,
            source_manifest_path=manifest_path,
            output_path=inference_output_path,
            pair_id=pair_id,
            identity_order_sha256=identity_order_sha256,
        )
        _write_json(inference_output_path, inference_result)
        _assert_paired_case_order(result, inference_result)

        report = _build_selection_report(
            report_path=selection_report_path,
            source_manifest_path=manifest_path,
            gold_output_path=output_path,
            inference_output_path=inference_output_path,
            exposure_denylist_path=exposure_denylist_path,
            denylist_metadata=denylist_metadata,
            pair_id=pair_id,
            identity_order_sha256=identity_order_sha256,
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
) -> dict[str, Any]:
    result = {
        key: value
        for key, value in source.items()
        if key not in {"selection", "counts", "cases"}
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


def _is_answer_field(name: str) -> bool:
    return name in _INFERENCE_ANSWER_FIELDS or name.startswith("expected_")


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
        choices=(_MEETI_BLIND_PILOT_64,),
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
