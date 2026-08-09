from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "build-exposure-denylist.py"
    )
    spec = importlib.util.spec_from_file_location("build_exposure_denylist", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_denylist_is_sorted_unique_and_auditable(tmp_path: Path) -> None:
    module = _load_module()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "one.json").write_text(
        '{"case":"meeti_20","other":"meeti_3"}', encoding="utf-8"
    )
    (artifacts / "two.log").write_text(
        "meeti_3\nnot_meeti_99\nmeeti_100x\n", encoding="utf-8"
    )
    (artifacts / "ignored.png").write_bytes(b"meeti_999")
    ignored_runtime = artifacts / "openclaw-state"
    ignored_runtime.mkdir()
    (ignored_runtime / "runtime.json").write_text(
        '{"case":"meeti_888"}', encoding="utf-8"
    )
    output = tmp_path / "denylist.txt"
    report_path = tmp_path / "report.json"

    report = module.build_denylist(
        sources=[artifacts],
        output_path=output,
        report_path=report_path,
    )

    assert output.read_text(encoding="utf-8").splitlines() == [
        "meeti_20",
        "meeti_3",
    ]
    assert report["case_count"] == 2
    assert report["files_scanned"] == 1
    assert json.loads(report_path.read_text(encoding="utf-8"))[
        "denylist_sha256"
    ] == report["denylist_sha256"]
