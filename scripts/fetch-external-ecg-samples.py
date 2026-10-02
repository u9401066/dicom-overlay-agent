"""Acquire a small, immutable, quarantined non-MEETI ECG inspection set.

No credentials, diagnosis headers, model calls, image edits or redistribution.
Downloaded images are NOT inference-ready until their pixels are privacy-reviewed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image

DATASET = "https://www.kaggle.com/datasets/physionet/ecg-image-database"
API = "https://www.kaggle.com/api/v1/datasets/"
VERSION = 2
LICENSE = "Attribution-NoDerivatives 4.0 International (CC BY-ND 4.0)"
LIMIT = 8 * 1024 * 1024
RECORD = "D0/D0_000022/D0_000022"
SAMPLES = (("_02.png", 372153), ("_04.jpeg", 1426751), ("_15.png", 383318))


def retrieve(url: str, *, maximum: int = LIMIT) -> bytes:
    request = Request(url, headers={"User-Agent": "dicom-overlay-source-audit/1"})
    with urlopen(request, timeout=30) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > maximum:
            raise ValueError("source_exceeds_download_limit")
        content = response.read(maximum + 1)
    if len(content) > maximum:
        raise ValueError("source_exceeds_download_limit")
    return content


def acquire(output: Path) -> dict[str, object]:
    metadata = json.loads(retrieve(API + "view/physionet/ecg-image-database"))
    if (
        metadata["currentVersionNumber"] != VERSION
        or metadata["licenseName"] != LICENSE
    ):
        raise ValueError("dataset_version_or_license_changed_review_required")
    listing = json.loads(
        retrieve(API + "list/physionet/ecg-image-database?pageSize=20")
    )
    sizes = {row["name"]: row["totalBytes"] for row in listing["datasetFiles"]}
    selected: list[tuple[str, str, str, int | None]] = []
    for index, (suffix, expected) in enumerate(SAMPLES, 1):
        source = RECORD + suffix
        if sizes.get(source) != expected:
            raise ValueError("dataset_listing_changed_review_required")
        url = API + "download/physionet/ecg-image-database/" + quote(source, safe="")
        selected.append(
            (
                f"sample-{index:02d}" + Path(source).suffix,
                url + "?datasetVersionNumber=2",
                source,
                expected,
            )
        )
    # Author-published thermal-paper precordial photograph. This preview is not
    # asserted to be an exact versioned dataset file or a paired gold reference.
    previews = re.findall(r"!\[\]\((https://[^\s)]+)\)", metadata["description"])
    preview = [
        url
        for url in previews
        if url.startswith(
            "https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/"
        )
        and "precordial_photo_iphone_16_pro_max_IMG_2253.jpg?generation=" in url
    ]
    if len(preview) != 1:
        raise ValueError("author_preview_changed_review_required")
    selected.append(("sample-04.jpg", preview[0], "author_description_preview", None))
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for filename, url, source, expected in selected:
        content = retrieve(url)
        if expected is not None and len(content) != expected:
            raise ValueError("download_size_mismatch")
        path = output / filename
        with path.open("xb") as handle:
            handle.write(content)
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format
            if (
                image_format not in {"PNG", "JPEG"}
                or getattr(image, "n_frames", 1) != 1
            ):
                raise ValueError("unexpected_image_format")
            image.verify()
        records.append(
            {
                "file": filename,
                "source": source,
                "download_request_url": url,
                "source_binding": "dataset_version_2"
                if expected
                else "author_preview_only",
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "width": width,
                "height": height,
                "format": image_format,
                "privacy_review": "pending",
                "inference_ready": False,
                "diagnostic_gold": "not_acquired",
                "transformations": [],
            }
        )
    receipt: dict[str, object] = {
        "schema_version": 1,
        "dataset": DATASET,
        "dataset_version": VERSION,
        "retrieved_utc": datetime.now(UTC).isoformat(),
        "dataset_license_as_advertised": LICENSE,
        "license_scope": "dataset label; author-preview-specific terms not separately verified",
        "publication_policy": "no source or transformed image redistribution",
        "purpose": "private source inspection; not clinical or live-App acceptance",
        "case_count_warning": "first three files are variants of ONE record; fourth is a preview",
        "model_requests": 0,
        "images": records,
    }
    with (output / "acquisition.json").open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = acquire(args.output)
    except Exception as exc:
        # Redirect URLs may contain signed storage query strings: do not log them.
        print(
            f"Acquisition failed ({type(exc).__name__}); preserve partial files, do not use for inference."
        )
        return 1
    print(
        f"Quarantined {len(receipt['images'])} original images; privacy review pending; no model calls."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
