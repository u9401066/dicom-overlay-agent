from __future__ import annotations

import importlib.util
from pathlib import Path

from dicom_overlay.domain.entities import RegionRect

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_run_eval_module():
    path = _REPO_ROOT / "scripts" / "run-eval.py"
    spec = importlib.util.spec_from_file_location("run_eval_script", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_signal_candidates_convert_to_region_rects() -> None:
    run_eval = _load_run_eval_module()
    signal = {
        "candidates": [
            {"x": 0.2, "y": 0.3, "w": 0.4, "h": 0.2},
            {"x": -0.1, "y": 0.9, "w": 0.4, "h": 0.4},
            {"x": 0.1, "y": 0.1, "w": 0.0, "h": 0.4},
        ]
    }

    regions = run_eval._local_candidate_regions_from_signal(signal, max_regions=3)

    assert regions == [
        RegionRect(x=0.2, y=0.3, w=0.4, h=0.2),
        RegionRect(x=0.0, y=0.9, w=0.3, h=0.1),
    ]


def test_run_eval_passes_local_candidates_into_multipass_source() -> None:
    source = (_REPO_ROOT / "scripts" / "run-eval.py").read_text(encoding="utf-8")

    assert "local_candidate_regions = _local_candidate_regions_from_signal" in source
    assert "local_candidate_regions=local_candidate_regions" in source


def test_multipass_trace_records_local_candidate_audit_fields() -> None:
    source = (_REPO_ROOT / "scripts" / "run-eval.py").read_text(encoding="utf-8")

    assert '"local_candidate_count": len(local_candidate_regions)' in source
    assert '"local_candidate_regions": [' in source
    assert "region.x" in source
    assert "region.y" in source
    assert "region.w" in source
    assert "region.h" in source
