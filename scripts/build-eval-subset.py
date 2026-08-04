"""Build a deterministic severity-stratified subset of an eval manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from collections import Counter
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
) -> dict[str, Any]:
    source = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = source.get("cases")
    if not isinstance(cases, list):
        raise ValueError("source manifest has no cases array")

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in cases:
        if not isinstance(row, dict):
            continue
        severity = str(row.get("expected_severity") or "")
        if severity in severity_counts:
            groups.setdefault(severity, []).append(dict(row))

    selected_by_severity: dict[str, list[dict[str, Any]]] = {}
    for severity, count in severity_counts.items():
        available = sorted(
            groups.get(severity, []),
            key=lambda row: str(row.get("label") or row.get("image") or ""),
        )
        if len(available) < count:
            raise ValueError(
                f"severity {severity!r} has {len(available)} cases, needs {count}"
            )
        rng = random.Random(f"{seed}:{severity}")
        rng.shuffle(available)
        selected_by_severity[severity] = available[:count]

    selected: list[dict[str, Any]] = []
    severity_order = list(severity_counts)
    for index in range(max(severity_counts.values())):
        for severity in severity_order:
            rows = selected_by_severity[severity]
            if index < len(rows):
                selected.append(rows[index])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    for row in selected:
        image = row.get("image")
        if not isinstance(image, str):
            raise ValueError("selected case has no image path")
        source_image = (manifest_path.parent / image).resolve()
        if not source_image.is_file():
            raise ValueError(f"selected image does not exist: {source_image}")
        row["image"] = Path(
            os.path.relpath(source_image, output_path.parent)
        ).as_posix()

    labels = [str(row.get("label") or "") for row in selected]
    if len(labels) != len(set(labels)):
        raise ValueError("selected case labels are not unique")

    result = {
        key: value
        for key, value in source.items()
        if key not in {"selection", "counts", "cases"}
    }
    result["selection"] = {
        "mode": "deterministic_severity_stratified_subset",
        "source_manifest": os.path.relpath(
            manifest_path.resolve(),
            output_path.parent.resolve(),
        ).replace(os.sep, "/"),
        "source_manifest_sha256": _sha256(manifest_path),
        "seed": seed,
        "severity_counts": severity_counts,
    }
    result["counts"] = {
        "cases": len(selected),
        "by_severity": dict(
            sorted(Counter(row["expected_severity"] for row in selected).items())
        ),
    }
    result["cases"] = selected
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--severity-count",
        action="append",
        default=[],
        metavar="NAME=COUNT",
        help="Repeat for each desired expected_severity stratum.",
    )
    parser.add_argument("--seed", type=int, default=20260725)
    args = parser.parse_args()
    try:
        counts = _parse_counts(args.severity_count)
        result = build_subset(
            manifest_path=args.manifest.resolve(),
            output_path=args.output.resolve(),
            severity_counts=counts,
            seed=args.seed,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"Wrote {result['counts']['cases']} cases to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
