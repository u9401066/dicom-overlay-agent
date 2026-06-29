#!/usr/bin/env python
"""Write a real-model benchmark readiness artifact.

Exit codes:
  0  ready
 20  blocked by missing credential/artifact/manifest prerequisite
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dicom_overlay.infrastructure.real_model_readiness import (  # noqa: E402
    assess_real_model_readiness,
    write_readiness_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--eval-dir", type=Path, default=None)
    parser.add_argument("--min-cases", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = assess_real_model_readiness(
        model_id=args.model_id,
        manifest_path=args.manifest,
        eval_dir=args.eval_dir,
        min_cases=args.min_cases,
        env=os.environ,
    )
    if args.output is not None:
        write_readiness_report(report, args.output)
    print(report.to_json())
    return 0 if report.status == "ready" else 20


if __name__ == "__main__":
    raise SystemExit(main())
