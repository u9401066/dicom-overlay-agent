"""Freeze a fresh 120-case desktop stress cohort without exposing case answers.

Reuses the existing selector's canonical diagnoses, eligibility and answer-free
manifest contract. This does not run inference or imply patient independence.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path


def _existing_selector():
    path = Path(__file__).with_name("build-eval-subset.py")
    spec = importlib.util.spec_from_file_location("eval_subset", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SELECTOR = _existing_selector()
PROFILE = {
    "name": "prospective-desktop-important-multi-120-v1",
    "seed": 20260924,
    "canonical_diagnosis_minimum": 3,
    "signature_cap": 4,
    "quotas": {
        "acute_risk": {"partially_uncertain": 24},
        "ischemic_infarct": {"asserted": 14, "partially_uncertain": 14},
        "rhythm_ectopy": {"asserted": 14, "partially_uncertain": 14},
        "conduction_qt": {"asserted": 12, "partially_uncertain": 12},
        "structure_voltage": {"asserted": 6, "partially_uncertain": 10},
    },
    "acute_reference_limit": "Partially uncertain references; not confirmed urgent diagnoses.",
    "independence_limit": "Case identity and exact image/report uniqueness, not patient independence.",
    "estimand": "Gold-enriched stress cohort, not population accuracy.",
}


def select_cases(rows, *, denied, image_digest, profile=PROFILE):
    """Select deterministically, rejecting exposure/duplicate bytes before ranking."""
    ids = [SELECTOR._case_identity(row) for row in rows]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("Source case identities must be nonempty and unique")
    # Deny by bytes and report as well as ID: an alias must not re-enter a batch.
    blocked_images = {image_digest(row) for row in rows if row["label"] in denied}
    blocked_reports = {
        SELECTOR._normalized_report(row) for row in rows if row["label"] in denied
    }
    eligible = []
    for row in rows:
        if row["label"] in denied:
            continue
        tier = SELECTOR._important_multi_128_eligibility_tier(row)
        if tier and SELECTOR._normalized_report(row) not in blocked_reports:
            eligible.append((row, tier))
    signatures = Counter()
    reports, images = set(), set()
    selected, selected_groups = [], {}
    for tier, cells in profile["quotas"].items():
        selected_groups[tier] = []
        for status, quota in cells.items():
            candidates = sorted(
                (r for r, t in eligible if t == tier and r["label_status"] == status),
                key=lambda r: SELECTOR._stable_case_rank(r, profile["seed"]),
            )
            accepted = 0
            for row in candidates:
                signature = SELECTOR._canonical_diagnoses(row)
                report = SELECTOR._normalized_report(row)
                if (
                    signatures[signature] >= profile["signature_cap"]
                    or report in reports
                ):
                    continue
                digest = image_digest(row)
                if digest in images or digest in blocked_images:
                    continue
                selected_groups[tier].append(row)
                signatures[signature] += 1
                reports.add(report)
                images.add(digest)
                accepted += 1
                if accepted == quota:
                    break
            if accepted != quota:
                raise ValueError(
                    f"Insufficient eligible/diverse cases for {tier}/{status}: {accepted}/{quota}"
                )
    # Interleave tiers so a partial run cannot accidentally contain only one tier.
    for index in range(max(map(len, selected_groups.values()))):
        for group in selected_groups.values():
            if index < len(group):
                selected.append(group[index])
    return selected


def build(*, source_path, denylist_path, output_dir):
    source_path, denylist_path, output_dir = (
        Path(p).resolve() for p in (source_path, denylist_path, output_dir)
    )
    if output_dir.exists():
        raise ValueError("Output directory must be new; retain prior selections")
    source_sha = SELECTOR._sha256(source_path)
    if source_sha != SELECTOR._MEETI_BLIND_IMPORTANT_MULTI_128_SOURCE_SHA256:
        raise ValueError("Source hash differs from the frozen MEETI pool")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    rows = source["cases"]
    if len(rows) != 9922:
        raise ValueError("Expected the frozen 9,922-case source pool")
    denied, deny_metadata = SELECTOR._read_exposure_denylist(denylist_path)
    if not denied:
        raise ValueError("A nonempty current exposure denylist is required")
    missing_ids = denied - {row["label"] for row in rows}
    if missing_ids:
        raise ValueError("Denylist contains identities outside the source pool")
    digests = {}

    def image_digest(row):
        key = row["label"]
        if key not in digests:
            digests[key] = SELECTOR._sha256(
                (source_path.parent / row["image"]).resolve()
            )
        return digests[key]

    selected = select_cases(
        rows, denied=denied, image_digest=image_digest, profile=PROFILE
    )
    identities = [r["label"] for r in selected]
    records = [
        {"case_identity": r["label"], "image_sha256": image_digest(r)} for r in selected
    ]
    identity_sha = SELECTOR._canonical_sha256(identities)
    image_sha = SELECTOR._canonical_sha256(records)
    binding = {
        "source_sha256": source_sha,
        "denylist": deny_metadata,
        "profile": PROFILE,
        "case_identity_order_sha256": identity_sha,
        "input_image_order_sha256": image_sha,
    }
    pair_id = SELECTOR._canonical_sha256(binding)
    gold_path, inference_path = output_dir / "gold.json", output_dir / "inference.json"
    selection = dict(binding, pair_id=pair_id, manifest_role="gold")
    gold = SELECTOR._build_manifest(
        source=source,
        selected=selected,
        source_manifest_path=source_path,
        output_path=gold_path,
        selection=selection,
        counts=SELECTOR._selection_counts(selected, multi_concept_min=3),
    )
    inference = SELECTOR._build_inference_manifest(
        source=source,
        selected=selected,
        source_manifest_path=source_path,
        output_path=inference_path,
        pair_id=pair_id,
        identity_order_sha256=identity_sha,
        input_image_order_sha256=image_sha,
    )
    SELECTOR._assert_answer_free_manifest(inference)
    SELECTOR._assert_paired_case_order(gold, inference)
    for row in selected:
        if SELECTOR._sha256(
            (source_path.parent / row["image"]).resolve()
        ) != image_digest(row):
            raise ValueError("Selected image changed during selection")
    if (
        SELECTOR._sha256(source_path) != source_sha
        or SELECTOR._sha256(denylist_path) != deny_metadata["sha256"]
    ):
        raise ValueError("Source/denylist changed during selection")
    # No outputs exist until eligibility and paired contracts have passed.
    output_dir.mkdir(parents=True, exist_ok=False)
    SELECTOR._write_json(gold_path, gold)
    SELECTOR._write_json(inference_path, inference)
    report = dict(
        binding,
        pair_id=pair_id,
        source_cases=len(rows),
        cases=len(selected),
        gold_sha256=SELECTOR._sha256(gold_path),
        inference_sha256=SELECTOR._sha256(inference_path),
        input_images=records,
        counts=gold["counts"],
        source_manifest=str(source_path),
        selector_sha256=SELECTOR._sha256(Path(__file__)),
        shared_selector_sha256=SELECTOR._sha256(
            Path(__file__).with_name("build-eval-subset.py")
        ),
        selected_axis_coverage=dict(
            Counter(axis for r in selected for axis in r.get("target_axes", []))
        ),
        exposure_status="exposed_reserved",
        model_execution_status="not_run",
        next_batch_gate="Union these case identities into the exposure denylist before future selection",
    )
    SELECTOR._write_json(output_dir / "selection-report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--denylist", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build(
        source_path=args.source, denylist_path=args.denylist, output_dir=args.output_dir
    )
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "cases",
                    "pair_id",
                    "gold_sha256",
                    "inference_sha256",
                    "model_execution_status",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
