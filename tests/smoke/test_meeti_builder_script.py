from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_builder_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "build-meeti-eval.py"
    spec = importlib.util.spec_from_file_location("build_meeti_eval_script", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tar_listing_parser_keeps_only_png_members() -> None:
    module = _load_builder_module()
    output = "\n".join(
        [
            "20260209_MEETI/p1000/p1/s1/1.mat",
            "20260209_MEETI/p1000/p1/s1/1.png",
            "20260209_MEETI/p1000/p1",
            "20260209_MEETI/p1000/p2/s2/2.PNG",
        ]
    )

    assert module._parse_tar_png_listing(output) == [
        "20260209_MEETI/p1000/p1/s1/1.png",
        "20260209_MEETI/p1000/p2/s2/2.PNG",
    ]


def test_scan_limit_zero_means_scan_all_candidates() -> None:
    module = _load_builder_module()
    entries = ["a.png", "b.png", "c.png"]

    assert module._candidate_slice(entries, 0) == entries
    assert module._candidate_slice(entries, 2) == ["a.png", "b.png"]


def test_min_cases_gate_rejects_underfilled_manifest() -> None:
    module = _load_builder_module()

    with pytest.raises(SystemExit, match="min-cases"):
        module._enforce_min_cases([{"label": "one"}], min_cases=2)


def test_flat_member_cache_detects_existing_archive_members(tmp_path: Path) -> None:
    module = _load_builder_module()
    (tmp_path / "1.mat").write_text("x", encoding="utf-8")
    (tmp_path / "2.mat").write_text("x", encoding="utf-8")
    members = [
        "root/patient/study/1.mat",
        "root/patient/study/2.mat",
    ]

    assert module._all_flat_members_exist(tmp_path, members) is True
    assert module._all_flat_members_exist(tmp_path, [*members, "missing.mat"]) is False
