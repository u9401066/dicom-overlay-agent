"""Build deterministic cropped/partial ECG variants from PHI-cleared PNGs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dicom_overlay.infrastructure.ecg_variant_corpus import (
    build_variant_corpus,
    verify_variant_corpus,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sources",
        nargs="+",
        type=Path,
        help="Already ROI-cropped, PHI-cleared ECG PNG files.",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    missing = [str(path) for path in args.sources if not path.is_file()]
    if missing:
        parser.error(f"source PNG does not exist: {', '.join(missing)}")
    manifest = build_variant_corpus(args.sources, args.output)
    verify_variant_corpus(args.output)
    print(
        f"Wrote and verified {manifest['variant_count']} answer-free ECG variants "
        f"to {args.output} (manifest_sha256={manifest['manifest_sha256']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
