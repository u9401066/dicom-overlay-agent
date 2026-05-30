"""Prepare the labeled evaluation dataset for the recognition harness.

Real labeled medical *images* (not signal/WFDB) are scarce for ECG and gated for
most CXR sets, so this script does two things:

1. If a URL manifest is provided (``--urls-from <json>``), download those real
   public-domain images and use the supplied labels. This is the path to a real
   accuracy benchmark -- drop in any openly licensed dataset URLs.
2. Otherwise, deterministically generate a small *synthetic* labeled set so the
   evaluation pipeline always has data to run against. Synthetic cases verify
   the measurement pipeline only -- they are NOT a diagnostic-accuracy claim.

Output: ``data/eval-datasets/<modality>/<name>.png`` plus a ``manifest.json``
consumed by ``scripts/run-eval.py``.

URL manifest format::

    {"cases": [
        {"url": "https://.../normal_cxr.png", "modality": "CXR",
         "expected_severity": "normal", "label": "normal_01",
         "keywords": ["clear", "no acute"]}
    ]}
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATASET_DIR = _REPO_ROOT / "data" / "eval-datasets"


def _font() -> Any:
    return ImageFont.load_default()


def _synthetic_cxr(path: Path, *, abnormal: bool, label: str) -> None:
    """Draw a schematic chest film. Deterministic; not diagnostic."""
    w, h = 512, 600
    img = Image.new("RGB", (w, h), (8, 8, 8))
    draw = ImageDraw.Draw(img)
    # Rib cage / lung fields (two bright ovals on dark background)
    draw.ellipse((70, 120, 240, 470), outline=(120, 120, 120), width=3)
    draw.ellipse((272, 120, 442, 470), outline=(120, 120, 120), width=3)
    # Mediastinum
    draw.rectangle((240, 130, 272, 470), fill=(60, 60, 60))
    # Spine
    for y in range(140, 470, 28):
        draw.rectangle((248, y, 264, y + 18), outline=(90, 90, 90), width=1)
    if abnormal:
        # Opacity in right lower lung field (the "finding")
        draw.ellipse((300, 360, 410, 450), fill=(190, 190, 190))
        draw.text((300, 330), "consolidation", fill=(255, 120, 120), font=_font())
    draw.text((12, 12), f"CXR {label}", fill=(220, 220, 220), font=_font())
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


def _synthetic_ekg(path: Path, *, abnormal: bool, label: str) -> None:
    """Draw a schematic 12-lead ECG. Deterministic; not diagnostic."""
    w, h = 900, 600
    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    for x in range(0, w, 25):
        draw.line((x, 0, x, h), fill=(238, 220, 220), width=1)
    for y in range(0, h, 25):
        draw.line((0, y, w, y), fill=(238, 220, 220), width=1)
    font = _font()
    leads = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    cw, ch = w // 4, h // 3
    for i, lead in enumerate(leads):
        col, row = i % 4, i // 4
        x0, y0 = col * cw + 18, row * ch + 22
        draw.text((x0, y0), f"Lead {lead}", fill=(30, 30, 30), font=font)
        baseline = y0 + 85
        pts: list[tuple[int, int]] = []
        for step in range(0, cw - 40, 12):
            x = x0 + step
            y = baseline
            if step % 60 == 24:
                y -= 38
            elif step % 60 == 36:
                y += 28
            if abnormal and lead in ("V2", "V3") and 60 <= step <= 120:
                y -= 30  # ST elevation bump
            pts.append((x, y))
        draw.line(pts, fill=(15, 15, 15), width=2)
    if abnormal:
        draw.rectangle((460, 300, 620, 392), outline=(220, 53, 69), width=4)
        draw.text((466, 396), "ST elevation V2-V3", fill=(180, 20, 35), font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


_SYNTHETIC_PLAN: list[dict[str, Any]] = [
    {"modality": "CXR", "label": "cxr_normal_01", "abnormal": False,
     "expected_severity": "normal", "keywords": ["clear", "no acute"]},
    {"modality": "CXR", "label": "cxr_normal_02", "abnormal": False,
     "expected_severity": "normal", "keywords": ["clear"]},
    {"modality": "CXR", "label": "cxr_consolidation_01", "abnormal": True,
     "expected_severity": "warning", "keywords": ["consolidation", "opacity"]},
    {"modality": "CXR", "label": "cxr_consolidation_02", "abnormal": True,
     "expected_severity": "warning", "keywords": ["consolidation"]},
    {"modality": "EKG", "label": "ekg_normal_01", "abnormal": False,
     "expected_severity": "normal", "keywords": ["sinus", "normal"]},
    {"modality": "EKG", "label": "ekg_stemi_01", "abnormal": True,
     "expected_severity": "critical", "keywords": ["st elevation", "stemi"]},
]


def _build_synthetic(dataset_dir: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for plan in _SYNTHETIC_PLAN:
        modality = str(plan["modality"])
        rel = f"{modality.lower()}/{plan['label']}.png"
        out = dataset_dir / rel
        if modality == "CXR":
            _synthetic_cxr(out, abnormal=bool(plan["abnormal"]), label=str(plan["label"]))
        else:
            _synthetic_ekg(out, abnormal=bool(plan["abnormal"]), label=str(plan["label"]))
        cases.append({
            "image": rel,
            "modality": modality,
            "expected_severity": plan["expected_severity"],
            "label": plan["label"],
            "keywords": plan["keywords"],
            "source": "synthetic",
        })
    return cases


def _download_real(dataset_dir: Path, urls_file: Path) -> list[dict[str, Any]]:
    spec = json.loads(urls_file.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    for entry in spec.get("cases", []):
        url = entry["url"]
        modality = entry["modality"]
        label = entry["label"]
        rel = f"{modality.lower()}/{label}.png"
        out = dataset_dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        print(f"  downloading {label} <- {url}")
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
                data = resp.read()
            # Normalize to PNG via PIL so downstream is uniform.
            from io import BytesIO

            Image.open(BytesIO(data)).convert("RGB").save(out, format="PNG")
        except Exception as exc:  # noqa: BLE001
            print(f"    WARNING: download failed ({exc}); skipping")
            continue
        cases.append({
            "image": rel,
            "modality": modality,
            "expected_severity": entry["expected_severity"],
            "label": label,
            "keywords": entry.get("keywords", []),
            "source": "real",
            "url": url,
        })
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare eval dataset")
    parser.add_argument(
        "--urls-from",
        type=Path,
        default=None,
        help="JSON file of real public-domain image URLs + labels",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DATASET_DIR,
        help="Dataset output directory",
    )
    args = parser.parse_args()
    dataset_dir = args.output
    dataset_dir.mkdir(parents=True, exist_ok=True)

    if args.urls_from is not None:
        print(f"Downloading real images from {args.urls_from} ...")
        cases = _download_real(dataset_dir, args.urls_from)
        if not cases:
            print("No real images downloaded; falling back to synthetic.")
            cases = _build_synthetic(dataset_dir)
    else:
        print("No --urls-from supplied; generating synthetic labeled set "
              "(pipeline verification only, NOT diagnostic accuracy).")
        cases = _build_synthetic(dataset_dir)

    manifest = {"cases": cases}
    manifest_path = dataset_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {len(cases)} cases -> {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
