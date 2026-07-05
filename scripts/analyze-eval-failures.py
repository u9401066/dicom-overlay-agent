"""Aggregate eval failure modes from a run's scorecard to guide harness fixes.

OOM-safe: reads only ``scorecard.json`` (one bounded file) and prints a
failure-pattern report. Use it to decide the next harness/prompt increment.

Usage:
    python scripts/analyze-eval-failures.py <eval-dir> [--top 15]

``<eval-dir>`` is a directory containing ``scorecard.json`` (e.g.
``data/experiments/<run>/eval``).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _load_scorecard(eval_dir: Path) -> dict:
    path = eval_dir / "scorecard.json"
    if not path.exists():
        raise SystemExit(f"scorecard.json not found in {eval_dir}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"scorecard.json is not a JSON object: {path}")
    return data


def _severity_confusion(cases: list[dict]) -> tuple[Counter, int, int]:
    """Return (confusion counter keyed 'exp->act', over_calls, under_calls)."""
    order = {"info": 0, "normal": 0, "warning": 1, "critical": 2}
    confusion: Counter = Counter()
    over = under = 0
    for case in cases:
        exp = case.get("expected_severity", "?")
        act = case.get("actual_severity", "?")
        if exp == act:
            continue
        confusion[f"{exp} -> {act}"] += 1
        exp_rank = order.get(exp, 0)
        act_rank = order.get(act, 0)
        if act_rank > exp_rank:
            over += 1
        elif act_rank < exp_rank:
            under += 1
    return confusion, over, under


def _axis_pass_rates(cases: list[dict]) -> list[tuple[str, int, int]]:
    """Per target-axis (name, fails, total) sorted by fail count desc."""
    total: Counter = Counter()
    fails: Counter = Counter()
    for case in cases:
        strict = bool(case.get("strict_pass"))
        for axis in case.get("target_axes", []):
            total[axis] += 1
            if not strict:
                fails[axis] += 1
    rows = [(axis, fails[axis], total[axis]) for axis in total]
    rows.sort(key=lambda r: (-r[1], r[0]))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eval_dir", type=Path)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()

    card = _load_scorecard(args.eval_dir)
    cases = card.get("cases", [])

    print(f"== Run: {args.eval_dir} ==")
    print(
        "gateway={} total={} scored={} err={}".format(
            card.get("gateway_mode"),
            card.get("total"),
            card.get("scored"),
            card.get("error_count"),
        )
    )
    print(
        "severity_acc={} kw_recall={} neg_recall={} schema={} "
        "bbox={} strict={} partial={} latency_ms={}".format(
            card.get("severity_accuracy"),
            card.get("mean_keyword_recall"),
            card.get("mean_negative_recall"),
            card.get("schema_pass_rate"),
            card.get("bbox_in_bounds_rate"),
            card.get("strict_pass_rate"),
            round(card.get("mean_partial_credit", 0.0), 3),
            card.get("mean_latency_ms"),
        )
    )

    confusion, over, under = _severity_confusion(cases)
    print("\n-- Severity confusion (expected -> actual) --")
    print(f"over-call={over}  under-call={under}  (under-call = missed acuity)")
    for label, count in confusion.most_common():
        print(f"  {count:>3}x  {label}")

    kw_miss: Counter = Counter()
    for case in cases:
        for miss in case.get("keyword_misses", []):
            kw_miss[miss] += 1
    print(f"\n-- Top {args.top} missed keywords (findings not reported) --")
    for kw, count in kw_miss.most_common(args.top):
        print(f"  {count:>3}x  {kw}")

    neg_miss: Counter = Counter()
    for case in cases:
        for miss in case.get("negative_misses", []):
            neg_miss[miss] += 1
    if neg_miss:
        print("\n-- Negative misses (should have been excluded) --")
        for kw, count in neg_miss.most_common(args.top):
            print(f"  {count:>3}x  {kw}")

    schema_bad = [
        (c.get("case_label"), c.get("schema_issue"))
        for c in cases
        if not c.get("schema_ok")
    ]
    print(f"\n-- Schema failures: {len(schema_bad)} --")
    for label, issue in schema_bad:
        print(f"  {label}: {issue}")

    print("\n-- Per target-axis strict-fail rate --")
    for axis, fails, total in _axis_pass_rates(cases):
        rate = fails / total if total else 0.0
        print(f"  {axis:<20} {fails:>3}/{total:<3}  fail_rate={rate:.2f}")

    cant_miss_missed = [
        (c.get("case_label"), c.get("cant_miss_missed", []))
        for c in cases
        if c.get("cant_miss_missed")
    ]
    if cant_miss_missed:
        print(f"\n-- CAN'T-MISS missed: {len(cant_miss_missed)} (safety-critical) --")
        for label, missed in cant_miss_missed:
            print(f"  {label}: {', '.join(missed)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
