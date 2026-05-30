"""Smoke tests for the recognition evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path

from dicom_overlay.domain.entities import (
    AnalysisResult,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.infrastructure.eval_harness import (
    EvalCase,
    run_evaluation,
    score_case,
)


def _case(
    tmp_path: Path,
    severity: Severity,
    keywords: tuple[str, ...],
    name: str = "x",
) -> EvalCase:
    img = tmp_path / f"{name}.png"
    img.write_bytes(b"\x89PNG\r\n")
    return EvalCase(
        image_path=img,
        modality=Modality.CXR,
        expected_severity=severity,
        expected_keywords=keywords,
        label=name,
    )


def _result(severity: Severity, *, summary: str, bbox: RegionRect | None = None) -> AnalysisResult:
    findings = []
    if bbox is not None:
        findings.append(
            Finding(
                id="f1",
                regions=[],
                label="consolidation",
                detail="opacity right base",
                severity=severity,
                bboxes=[bbox],
            )
        )
    return AnalysisResult(
        modality=Modality.CXR,
        summary=summary,
        severity=severity,
        findings=findings,
        checklist={"x": ChecklistItem(value="ok", status=Severity.NORMAL)},
    )


def test_score_case_exact_severity_and_keyword_recall(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.WARNING, ("consolidation", "opacity"))
    result = _result(
        Severity.WARNING,
        summary="CXR: consolidation",
        bbox=RegionRect(x=0.5, y=0.5, w=0.2, h=0.2),
    )
    score = score_case(case, result, latency_ms=12)
    assert score.severity_match is True
    assert score.severity_abnormal_match is True
    assert score.keyword_recall == 1.0
    assert score.schema_ok is True
    assert score.bbox_in_bounds is True


def test_score_case_detects_out_of_bounds_bbox(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.WARNING, ())
    result = _result(
        Severity.WARNING,
        summary="bad bbox",
        bbox=RegionRect(x=0.9, y=0.5, w=0.5, h=0.2),  # x+w = 1.4 > 1
    )
    score = score_case(case, result, latency_ms=0)
    assert score.bbox_in_bounds is False


def test_score_case_abnormal_group_mismatch(tmp_path: Path) -> None:
    case = _case(tmp_path, Severity.CRITICAL, ())
    result = _result(Severity.NORMAL, summary="all clear")
    score = score_case(case, result, latency_ms=0)
    assert score.severity_match is False
    assert score.severity_abnormal_match is False


async def test_run_evaluation_writes_scorecard_and_aggregates(tmp_path: Path) -> None:
    cases = [
        _case(tmp_path, Severity.WARNING, ("consolidation",), name="abnormal"),
        _case(tmp_path, Severity.NORMAL, (), name="normal"),
    ]
    answers = {
        cases[0].image_path: _result(
            Severity.WARNING,
            summary="consolidation seen",
            bbox=RegionRect(x=0.1, y=0.1, w=0.2, h=0.2),
        ),
        cases[1].image_path: _result(Severity.NORMAL, summary="clear"),
    }

    async def analyze(case: EvalCase) -> AnalysisResult:
        return answers[case.image_path]

    out = tmp_path / "out"
    report = await run_evaluation(
        cases, analyze, output_dir=out, gateway_mode="mock"
    )

    assert report.total == 2
    assert report.scored == 2
    assert report.severity_accuracy == 1.0
    scorecard = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["gateway_mode"] == "mock"
    assert len(scorecard["cases"]) == 2
    assert (out / "results").is_dir()


async def test_run_evaluation_records_errors_without_aborting(tmp_path: Path) -> None:
    cases = [_case(tmp_path, Severity.WARNING, ())]

    async def analyze(_case: EvalCase) -> AnalysisResult:
        raise ConnectionError("gateway down")

    report = await run_evaluation(
        cases, analyze, output_dir=tmp_path / "o", gateway_mode="real"
    )
    assert report.error_count == 1
    assert report.scored == 0
    assert report.cases[0].error is not None
