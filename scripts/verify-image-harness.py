from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dicom_overlay.infrastructure.image_harness_validator import (
    verify_image_harness_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify DICOM Overlay image harness smoke artifacts."
    )
    parser.add_argument("--log", default="data/harness-smoke/harness_smoke.log")
    parser.add_argument("--result", default="data/harness-smoke/result.json")
    parser.add_argument("--require-viewer", action="store_true")
    args = parser.parse_args()

    verification = verify_image_harness_artifacts(
        log_path=Path(args.log),
        result_path=Path(args.result),
        require_viewer=args.require_viewer,
    )
    print(verification.to_json())
    return 0 if verification.ok else 1


if __name__ == "__main__":
    sys.exit(main())
