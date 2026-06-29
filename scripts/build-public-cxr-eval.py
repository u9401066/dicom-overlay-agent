#!/usr/bin/env python
"""Build a 1000+ public CXR eval dataset from Hugging Face rows.

Default source:
    hf-vision/chest-xray-pneumonia

If direct Hugging Face access is blocked, set ``HF_ENDPOINT`` to a compatible
mirror that exposes ``/datasets-server`` rows, or prefetch rows to JSON and pass
``--rows-from``.

The output directory is under ``data/`` by default and is gitignored.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dicom_overlay.infrastructure.public_cxr_dataset import (  # noqa: E402
    HuggingFaceImageRow,
    build_hf_rows_url,
    build_public_cxr_manifest,
)

_HTTP_HEADERS = {
    "User-Agent": (
        "dicom-overlay-agent-public-cxr-eval/1.0 "
        "(+https://github.com/u9401066/dicom-overlay-agent)"
    )
}


def _load_rows_file(path: Path) -> list[HuggingFaceImageRow]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("rows", raw if isinstance(raw, list) else [])
    output: list[HuggingFaceImageRow] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        output.append(
            HuggingFaceImageRow(
                image_url=str(item["image_url"]),
                label=item["label"],
                row_idx=int(item.get("row_idx", len(output))),
            )
        )
    return output


def _fetch_hf_rows(
    *,
    dataset_id: str,
    config: str,
    split: str,
    limit: int,
    endpoint: str,
    page_size: int = 100,
) -> list[HuggingFaceImageRow]:
    rows: list[HuggingFaceImageRow] = []
    for offset in range(0, limit, page_size):
        length = min(page_size, limit - offset)
        url = build_hf_rows_url(
            dataset_id=dataset_id,
            config=config,
            split=split,
            offset=offset,
            length=length,
            endpoint=endpoint,
        )
        payload = _read_json_url(url)
        for row_obj in payload.get("rows", []):
            row_idx = int(row_obj.get("row_idx", len(rows)))
            row = row_obj.get("row", {})
            parsed = _parse_hf_row(row, row_idx=row_idx)
            if parsed is not None:
                rows.append(parsed)
        if len(rows) >= limit:
            break
    return rows[:limit]


def _parse_hf_row(row: dict[str, Any], *, row_idx: int) -> HuggingFaceImageRow | None:
    image_url = _extract_image_url(row)
    if not image_url:
        return None
    label = row.get("label", row.get("labels", row.get("class", "")))
    return HuggingFaceImageRow(image_url=image_url, label=label, row_idx=row_idx)


def _extract_image_url(row: dict[str, Any]) -> str:
    for key in ("image", "img", "png", "file"):
        value = row.get(key)
        if isinstance(value, dict):
            src = value.get("src") or value.get("url") or value.get("path")
            if src:
                return str(src)
        if isinstance(value, str) and value.startswith(("http://", "https://", "file:")):
            return value
    return ""


def _read_json_url(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=_HTTP_HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_images(rows: list[HuggingFaceImageRow], output_dir: Path) -> None:
    image_dir = output_dir / "cxr"
    image_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        target = image_dir / f"{row.row_idx:06d}.png"
        if target.exists():
            continue
        request = urllib.request.Request(row.image_url, headers=_HTTP_HEADERS)
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        Image.open(BytesIO(data)).convert("RGB").save(target, format="PNG")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", default="hf-vision/chest-xray-pneumonia")
    parser.add_argument("--config", default="default")
    parser.add_argument("--split", default="train")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--min-cases", type=int, default=1000)
    parser.add_argument("--rows-from", type=Path, default=None)
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("HF_ENDPOINT", "https://datasets-server.huggingface.co"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_REPO_ROOT / "data" / "eval-datasets" / "public-cxr",
    )
    args = parser.parse_args()

    try:
        rows = (
            _load_rows_file(args.rows_from)
            if args.rows_from is not None
            else _fetch_hf_rows(
                dataset_id=args.dataset_id,
                config=args.config,
                split=args.split,
                limit=args.limit,
                endpoint=args.endpoint,
            )
        )
        manifest = build_public_cxr_manifest(
            rows,
            dataset_id=args.dataset_id,
            image_prefix="cxr",
            min_cases=args.min_cases,
        )
        args.output.mkdir(parents=True, exist_ok=True)
        _download_images(rows[: len(manifest["cases"])], args.output)
        (args.output / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"ERROR: public CXR dataset build failed: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(manifest['cases'])} public CXR cases -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
