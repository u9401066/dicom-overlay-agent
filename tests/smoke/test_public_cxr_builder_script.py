from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image


def _tiny_png(path: Path, color: str) -> None:
    Image.new("RGB", (8, 8), color).save(path, format="PNG")


def test_public_cxr_builder_accepts_local_rows_manifest(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    normal = source_dir / "normal.png"
    pneumonia = source_dir / "pneumonia.png"
    _tiny_png(normal, "black")
    _tiny_png(pneumonia, "white")
    rows_file = tmp_path / "rows.json"
    rows_file.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "image_url": normal.as_uri(),
                        "label": "NORMAL",
                        "row_idx": 0,
                    },
                    {
                        "image_url": pneumonia.as_uri(),
                        "label": "PNEUMONIA",
                        "row_idx": 1,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "public-cxr"
    script = Path(__file__).resolve().parents[2] / "scripts" / "build-public-cxr-eval.py"

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--rows-from",
            str(rows_file),
            "--output",
            str(output),
            "--min-cases",
            "2",
        ],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["cases"] == 2
    assert (output / "cxr" / "000000.png").exists()
    assert (output / "cxr" / "000001.png").exists()
    assert manifest["cases"][1]["keywords"] == [
        "pneumonia",
        "opacity",
        "consolidation",
    ]
