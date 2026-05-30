"""Recognition evaluation harness.

This module is the answer to "how do we know the recognition result and record
the test outcome?".  The overlay agent never makes a diagnosis on screen pixels
alone -- every interpretation is first produced as a structured
``AnalysisResult`` (modality / severity / findings / 16-key checklist).  This
harness feeds *labeled* images through the real interpretation path
(``OpenClawClient`` frame building + parsing), then scores each structured
result against the dataset ground truth and writes a machine-readable
scorecard.

Two run modes share the exact same scoring code:

* ``real``  -- a real OpenClaw Gateway answers (measures *model accuracy*).
* ``mock``  -- an in-process gateway echoes schema-valid payloads (verifies the
  *measurement pipeline* without an API token).

The scorecard captures, per image: expected vs actual severity, finding-keyword
recall, schema compliance (reusing :class:`OutputValidator`), normalized-bbox
in-bounds, finding count, and latency.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from dicom_overlay.domain.entities import AnalysisResult, Modality, Severity
from dicom_overlay.domain.hooks import AnalyzeRequest, HookError
from dicom_overlay.infrastructure.hooks.output_validator import OutputValidator

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

# Severity grouping for the clinically meaningful binary "abnormal vs normal".
_ABNORMAL = frozenset({Severity.WARNING, Severity.CRITICAL})


@dataclass(frozen=True)
class EvalCase:
    """One labeled evaluation image (the ground truth)."""

    image_path: Path
    modality: Modality
    expected_severity: Severity
    expected_keywords: tuple[str, ...] = ()
    label: str = ""
    valid_regions: tuple[str, ...] = ()


@dataclass
class CaseScore:
    """Per-image scored outcome -- the recorded evidence for one case."""

    case_label: str
    image: str
    modality: str
    expected_severity: str
    actual_severity: str
    severity_match: bool
    severity_abnormal_match: bool
    keyword_hits: list[str]
    keyword_misses: list[str]
    keyword_recall: float
    schema_ok: bool
    schema_issue: str
    bbox_in_bounds: bool
    finding_count: int
    latency_ms: int
    error: str | None = None


@dataclass
class EvalReport:
    """Aggregate scorecard across all cases."""

    gateway_mode: str
    total: int
    scored: int
    error_count: int
    severity_accuracy: float
    severity_abnormal_accuracy: float
    mean_keyword_recall: float
    schema_pass_rate: float
    bbox_in_bounds_rate: float
    mean_latency_ms: float
    cases: list[CaseScore] = field(default_factory=list)

    def to_json(self) -> str:
        payload = asdict(self)
        return json.dumps(payload, indent=2, ensure_ascii=False)


def _severity_group(sev: Severity) -> str:
    return "abnormal" if sev in _ABNORMAL else "normal"


def _haystack(result: AnalysisResult) -> str:
    parts = [result.summary]
    for finding in result.findings:
        parts.append(finding.label)
        parts.append(finding.detail)
    return " ".join(parts).lower()


def _bbox_in_bounds(result: AnalysisResult) -> bool:
    for finding in result.findings:
        for box in finding.bboxes:
            if box.x + box.w > 1.0 + 1e-6 or box.y + box.h > 1.0 + 1e-6:
                return False
    return True


def _schema_check(case: EvalCase, result: AnalysisResult) -> tuple[bool, str]:
    """Run the production OutputValidator as the schema gate."""
    validator = OutputValidator(strict=False)
    request = AnalyzeRequest(
        image_base64="",
        modality=case.modality,
        valid_regions=list(case.valid_regions),
    )
    try:
        validator.post_analyze(request, result)
    except HookError as exc:
        return False, str(exc)
    return True, ""


def score_case(case: EvalCase, result: AnalysisResult, latency_ms: int) -> CaseScore:
    """Score a single structured result against the case ground truth."""
    haystack = _haystack(result)
    hits: list[str] = []
    misses: list[str] = []
    for keyword in case.expected_keywords:
        if keyword.lower() in haystack:
            hits.append(keyword)
        else:
            misses.append(keyword)
    recall = len(hits) / len(case.expected_keywords) if case.expected_keywords else 1.0

    schema_ok, schema_issue = _schema_check(case, result)

    return CaseScore(
        case_label=case.label or case.image_path.name,
        image=case.image_path.name,
        modality=case.modality.value,
        expected_severity=case.expected_severity.value,
        actual_severity=result.severity.value,
        severity_match=result.severity == case.expected_severity,
        severity_abnormal_match=(
            _severity_group(result.severity)
            == _severity_group(case.expected_severity)
        ),
        keyword_hits=hits,
        keyword_misses=misses,
        keyword_recall=round(recall, 3),
        schema_ok=schema_ok,
        schema_issue=schema_issue,
        bbox_in_bounds=_bbox_in_bounds(result),
        finding_count=len(result.findings),
        latency_ms=latency_ms,
    )


def _error_score(case: EvalCase, message: str) -> CaseScore:
    return CaseScore(
        case_label=case.label or case.image_path.name,
        image=case.image_path.name,
        modality=case.modality.value,
        expected_severity=case.expected_severity.value,
        actual_severity="(error)",
        severity_match=False,
        severity_abnormal_match=False,
        keyword_hits=[],
        keyword_misses=list(case.expected_keywords),
        keyword_recall=0.0,
        schema_ok=False,
        schema_issue=message,
        bbox_in_bounds=False,
        finding_count=0,
        latency_ms=0,
        error=message,
    )


def _aggregate(gateway_mode: str, scores: list[CaseScore]) -> EvalReport:
    scored = [s for s in scores if s.error is None]
    errors = len(scores) - len(scored)
    n = len(scored)

    def _rate(predicate: Any) -> float:
        if n == 0:
            return 0.0
        return round(sum(1 for s in scored if predicate(s)) / n, 3)

    severity_acc = _rate(lambda s: s.severity_match)
    abnormal_acc = _rate(lambda s: s.severity_abnormal_match)
    schema_rate = _rate(lambda s: s.schema_ok)
    bbox_rate = _rate(lambda s: s.bbox_in_bounds)
    mean_recall = (
        round(sum(s.keyword_recall for s in scored) / n, 3) if n else 0.0
    )
    mean_latency = (
        round(sum(s.latency_ms for s in scored) / n, 1) if n else 0.0
    )

    return EvalReport(
        gateway_mode=gateway_mode,
        total=len(scores),
        scored=n,
        error_count=errors,
        severity_accuracy=severity_acc,
        severity_abnormal_accuracy=abnormal_acc,
        mean_keyword_recall=mean_recall,
        schema_pass_rate=schema_rate,
        bbox_in_bounds_rate=bbox_rate,
        mean_latency_ms=mean_latency,
        cases=scores,
    )


async def run_evaluation(
    cases: list[EvalCase],
    analyze: Callable[[EvalCase], Awaitable[AnalysisResult]],
    *,
    output_dir: Path,
    gateway_mode: str,
) -> EvalReport:
    """Drive every case through ``analyze``, score it, and persist artifacts.

    ``analyze`` is an async callable that returns the structured
    ``AnalysisResult`` for a case (real gateway or mock).  Latency is measured
    here so both modes are timed identically.
    """
    results_dir = output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    scores: list[CaseScore] = []
    for case in cases:
        start = time.monotonic()
        try:
            result = await analyze(case)
        except Exception as exc:
            scores.append(_error_score(case, f"{type(exc).__name__}: {exc}"))
            continue
        latency_ms = int((time.monotonic() - start) * 1000)
        score = score_case(case, result, latency_ms)
        scores.append(score)
        _write_raw_result(results_dir, case, result, score)

    report = _aggregate(gateway_mode, scores)
    (output_dir / "scorecard.json").write_text(report.to_json(), encoding="utf-8")
    return report


def _write_raw_result(
    results_dir: Path,
    case: EvalCase,
    result: AnalysisResult,
    score: CaseScore,
) -> None:
    raw = {
        "case": score.case_label,
        "modality": result.modality.value,
        "summary": result.summary,
        "severity": result.severity.value,
        "model_used": result.model_used,
        "findings": [
            {
                "id": f.id,
                "label": f.label,
                "detail": f.detail,
                "severity": f.severity.value,
                "regions": f.regions,
                "bboxes": [
                    {"x": b.x, "y": b.y, "w": b.w, "h": b.h} for b in f.bboxes
                ],
            }
            for f in result.findings
        ],
        "checklist": {
            k: {"value": v.value, "status": v.status.value}
            for k, v in result.checklist.items()
        },
        "score": asdict(score),
    }
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in score.case_label)
    (results_dir / f"{safe}.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )
