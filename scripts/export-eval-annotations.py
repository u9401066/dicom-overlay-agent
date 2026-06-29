"""Export eval results as bbox-marked PNGs for expert review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dicom_overlay.infrastructure.annotation_exporter import (  # noqa: E402
    export_eval_annotations,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval-dir",
        type=Path,
        required=True,
        help="Evaluation artifact dir containing results/*.json.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_REPO_ROOT / "data" / "eval-datasets" / "meeti" / "manifest.json",
        help="Dataset manifest used to resolve source image paths.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory. Defaults to <eval-dir>/review.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Keep previously generated review PNG/crop artifacts in the output dir.",
    )
    args = parser.parse_args()

    try:
        paths = export_eval_annotations(
            eval_dir=args.eval_dir,
            manifest_path=args.manifest,
            output_dir=args.output,
            limit=args.limit,
            clean=not args.no_clean,
        )
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    out_dir = args.output or (args.eval_dir / "review")
    print(f"Exported {len(paths)} annotated review image(s) to {out_dir}")
    print(f"Index: {out_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
