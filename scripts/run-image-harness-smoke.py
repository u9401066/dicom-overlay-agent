from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from dicom_overlay.infrastructure.image_harness_smoke import run_image_harness_smoke


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the DICOM Overlay image interpretation harness smoke test."
    )
    parser.add_argument(
        "--output-dir",
        default="data/harness-smoke",
        help="Directory for sample image, log, and result JSON.",
    )
    parser.add_argument(
        "--show-viewer",
        action="store_true",
        help="Display the synthetic dataset image in a desktop viewer window.",
    )
    args = parser.parse_args()

    result = asyncio.run(
        run_image_harness_smoke(
            output_dir=Path(args.output_dir),
            show_viewer=args.show_viewer,
        )
    )
    print(f"ok={result.ok}")
    print(f"summary={result.summary}")
    print(f"log={result.log_path}")
    print(f"result={result.result_path}")
    print(f"sample_image={result.sample_image_path}")


if __name__ == "__main__":
    main()
