from __future__ import annotations

import json
from typing import TYPE_CHECKING

from dicom_overlay.infrastructure.eval_artifact_validator import (
    verify_eval_artifacts,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_minimal_eval(eval_dir: Path, manifest_path: Path, count: int = 2) -> None:
    manifest_path.write_text(
        json.dumps(
            {
                "cases": [
                    {"label": f"case_{index}", "image": f"case_{index}.png"}
                    for index in range(count)
                ]
            }
        ),
        encoding="utf-8",
    )
    eval_dir.mkdir(parents=True)
    (eval_dir / "scorecard.json").write_text(
        json.dumps(
            {
                "gateway_mode": "mock",
                "manifest_total": count,
                "result_count": count,
                "total": count,
                "scored": count,
                "error_count": 0,
                "is_partial": False,
                "schema_pass_rate": 1.0,
                "bbox_in_bounds_rate": 1.0,
                "cant_miss_missed": [],
                "strict_pass_rate": 1.0,
            }
        ),
        encoding="utf-8",
    )
    results = eval_dir / "results"
    results.mkdir()
    for index in range(count):
        (results / f"case_{index}.json").write_text(
            json.dumps(
                {
                    "case": f"case_{index}",
                    "local_image_quality": {"low_signal": False},
                    "local_signal_candidates": {
                        "candidate_count": 1,
                        "candidates": [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}],
                    },
                }
            ),
            encoding="utf-8",
        )
    review = eval_dir / "review"
    review.mkdir()
    (review / "index.html").write_text("<html></html>", encoding="utf-8")
    (review / "bbox-audit.jsonl").write_text(
        "".join(json.dumps({"case": f"case_{index}"}) + "\n" for index in range(count)),
        encoding="utf-8",
    )


def test_multipass_trace_requires_local_candidate_audit_fields(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    (eval_dir / "multipass-trace.jsonl").write_text(
        json.dumps(
            {
                "case": "case_0",
                "openclaw_analyze_calls": 1,
                "crop_calls": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
    )

    assert not verification.ok
    assert any(
        failure.startswith("multipass_trace_artifacts:")
        for failure in verification.failures
    )


def test_multipass_trace_with_local_candidate_audit_fields_passes(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    (eval_dir / "multipass-trace.jsonl").write_text(
        json.dumps(
            {
                "case": "case_0",
                "openclaw_analyze_calls": 1,
                "crop_calls": 0,
                "local_candidate_count": 1,
                "local_candidate_regions": [
                    {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
    )

    assert verification.ok
    assert "multipass_trace_artifacts" in verification.passed_checks
