#!/usr/bin/env python
"""Verify large recognition-eval artifacts.

Example:
    uv run python scripts/verify-eval-artifacts.py \
      --eval-dir data/eval/mock-20260629-120000 \
      --manifest data/eval-datasets/public-cxr/manifest.json \
      --min-cases 1000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dicom_overlay.infrastructure.eval_artifact_validator import (  # noqa: E402
    verify_eval_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--min-cases", type=int, default=1000)
    parser.add_argument(
        "--no-review",
        action="store_true",
        help="Do not require review/index.html and review/bbox-audit.jsonl.",
    )
    parser.add_argument(
        "--allow-nonperfect-mock",
        "--allow-nonperfect-real",
        dest="allow_nonperfect_mock",
        action="store_true",
        help=(
            "Do not require strict_pass_rate=100%% for mock pipeline self-tests. "
            "Real clinical runs are governed by the explicit minimum-rate gates."
        ),
    )
    parser.add_argument(
        "--min-strict-pass-rate",
        type=float,
        default=None,
        help="Optional minimum strict pass rate in [0, 1].",
    )
    parser.add_argument(
        "--min-mean-partial-credit",
        type=float,
        default=None,
        help="Optional minimum mean partial-credit score in [0, 1].",
    )
    parser.add_argument(
        "--require-multipass-trace",
        action="store_true",
        help=(
            "Require multipass-trace.jsonl and validate local candidate audit "
            "fields. Use for production multi-pass crop re-analysis runs."
        ),
    )
    parser.add_argument(
        "--require-multipass-refinement",
        action="store_true",
        help=(
            "Require real per-case crop/refine model turns and, for boxed "
            "findings, auditable decisions plus dicom_bbox_validate use."
        ),
    )
    parser.add_argument(
        "--require-ekg-systematic-probes",
        action="store_true",
        help=(
            "Require every EKG result to record a planned and completed "
            "layout-derived discovery crop from the original ROI."
        ),
    )
    parser.add_argument(
        "--require-projection-audit",
        action="store_true",
        help=(
            "Require review/bbox-audit.jsonl rows with model bboxes to include "
            "overlay projection round-trip calibration fields."
        ),
    )
    args = parser.parse_args()

    verification = verify_eval_artifacts(
        eval_dir=args.eval_dir,
        manifest_path=args.manifest,
        min_cases=args.min_cases,
        require_review=not args.no_review,
        require_perfect_mock=not args.allow_nonperfect_mock,
        require_multipass_trace=args.require_multipass_trace,
        require_multipass_refinement=args.require_multipass_refinement,
        require_ekg_systematic_probes=args.require_ekg_systematic_probes,
        require_projection_audit=args.require_projection_audit,
        min_strict_pass_rate=args.min_strict_pass_rate,
        min_mean_partial_credit=args.min_mean_partial_credit,
    )
    print(verification.to_json())
    return 0 if verification.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
