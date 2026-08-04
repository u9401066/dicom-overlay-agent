#!/usr/bin/env python
"""Re-derive MEETI report labels without overwriting the source manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dicom_overlay.infrastructure.meeti_dataset import (  # noqa: E402
    REPORT_LABEL_SCHEMA_VERSION,
    classify_report,
)

_CLASSIFIER_PATH = (
    _REPO_ROOT / "src" / "dicom_overlay" / "infrastructure" / "meeti_dataset.py"
)
_DERIVED_FIELDS = frozenset(
    {
        "expected_severity",
        "keywords",
        "negatives",
        "target_axes",
        "cant_miss",
        "urgent_concerns",
        "concepts",
        "label_status",
        "uncertain_concepts",
        "ungradable_reasons",
    }
)
_SCORING_FIELDS = frozenset(
    {
        "expected_severity",
        "keywords",
        "negatives",
        "target_axes",
        "cant_miss",
    }
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relocatable_image(
    image: str,
    *,
    source_dir: Path,
    output_dir: Path,
) -> str:
    source_image = (source_dir / image).resolve()
    if not source_image.is_file():
        raise ValueError(f"manifest image does not exist: {source_image}")
    return Path(os.path.relpath(source_image, output_dir.resolve())).as_posix()


def relabel_manifest(*, manifest_path: Path, output_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    output_path = output_path.resolve()
    if manifest_path == output_path:
        raise ValueError(
            "output must differ from source manifest to preserve provenance"
        )

    source = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_cases = source.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("source manifest has no cases array")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    severity_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    concept_counts: Counter[str] = Counter()
    uncertain_concept_counts: Counter[str] = Counter()
    cant_miss_counts: Counter[str] = Counter()
    urgent_counts: Counter[str] = Counter()
    changed_cases = 0
    enriched_cases = 0

    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise ValueError(f"case {index} is not an object")
        report = raw.get("report")
        if not isinstance(report, str):
            raise ValueError(f"case {index} has no report text")
        image = raw.get("image")
        if not isinstance(image, str):
            raise ValueError(f"case {index} has no image path")

        labels = classify_report(report)
        derived = labels.manifest_fields()
        previous = {
            key: raw.get(key, [] if key != "expected_severity" else "")
            for key in _SCORING_FIELDS
        }
        if any(previous[key] != derived[key] for key in _SCORING_FIELDS):
            changed_cases += 1
        if any(key not in raw for key in _DERIVED_FIELDS - _SCORING_FIELDS):
            enriched_cases += 1

        row = {key: value for key, value in raw.items() if key not in _DERIVED_FIELDS}
        row["image"] = _relocatable_image(
            image,
            source_dir=manifest_path.parent,
            output_dir=output_path.parent,
        )
        row.update(derived)
        cases.append(row)

        severity_counts[labels.severity] += 1
        status_counts[labels.label_status] += 1
        concept_counts.update(labels.concepts)
        uncertain_concept_counts.update(labels.uncertain_concepts)
        cant_miss_counts.update(labels.cant_miss)
        urgent_counts.update(labels.urgent_concerns)

    result = {
        key: value
        for key, value in source.items()
        if key not in {"counts", "cases", "labeling"}
    }
    result["labeling"] = {
        "schema_version": REPORT_LABEL_SCHEMA_VERSION,
        "classifier": "classify_report",
        "classifier_source": _CLASSIFIER_PATH.relative_to(_REPO_ROOT).as_posix(),
        "classifier_sha256": _sha256(_CLASSIFIER_PATH),
        "source_manifest": Path(
            os.path.relpath(manifest_path, output_path.parent)
        ).as_posix(),
        "source_manifest_sha256": _sha256(manifest_path),
        "changed_cases": changed_cases,
        "enriched_cases": enriched_cases,
    }
    result["counts"] = {
        "cases": len(cases),
        "by_severity": dict(sorted(severity_counts.items())),
        "by_label_status": dict(sorted(status_counts.items())),
        "by_concept": dict(sorted(concept_counts.items())),
        "by_uncertain_concept": dict(sorted(uncertain_concept_counts.items())),
        "cant_miss": dict(sorted(cant_miss_counts.items())),
        "urgent_concerns": dict(sorted(urgent_counts.items())),
    }
    result["cases"] = cases
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = relabel_manifest(
            manifest_path=args.manifest,
            output_path=args.output,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    labeling = result["labeling"]
    print(
        f"Relabeled {result['counts']['cases']} cases; "
        f"changed={labeling['changed_cases']} -> {args.output.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
