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

from dicom_overlay.infrastructure.env_file import read_env_file  # noqa: E402
from dicom_overlay.infrastructure.real_model_readiness import (  # noqa: E402
    assess_real_model_readiness,
    probe_provider_for_model,
    write_readiness_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--eval-dir", type=Path, default=None)
    parser.add_argument("--min-cases", type=int, default=1000)
    parser.add_argument(
        "--dotenv",
        type=Path,
        default=None,
        help="Optional .env file to merge into readiness checks without printing values.",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--probe-provider",
        action="store_true",
        help="Also probe provider metadata/egress and advertised image support.",
    )
    args = parser.parse_args()

    env = dict(os.environ)
    if args.dotenv is not None:
        env.update(read_env_file(args.dotenv))

    report = assess_real_model_readiness(
        model_id=args.model_id,
        manifest_path=args.manifest,
        eval_dir=args.eval_dir,
        min_cases=args.min_cases,
        env=env,
        provider_probe=probe_provider_for_model if args.probe_provider else None,
    )
    if args.output is not None:
        write_readiness_report(report, args.output)
    print(report.to_json())
    return 0 if report.status == "ready" else 20


if __name__ == "__main__":
    raise SystemExit(main())
