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
from dicom_overlay.domain.modality_profile import get_active_registry
from dicom_overlay.infrastructure.hooks.output_validator import OutputValidator

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from dicom_overlay.domain.modality_profile import ModalityRegistry

# Severity grouping for the clinically meaningful binary "abnormal vs normal".
_ABNORMAL = frozenset({Severity.WARNING, Severity.CRITICAL})

# Can't-miss diagnoses -- the lethal calls that must NEVER be silently dropped.
# These are the *reference* fatal list per modality; the per-case ground truth
# (which can't-miss a given image actually contains) is annotated on each
# ``EvalCase.cant_miss`` in the dataset manifest. A miss here is a hard CI
# failure (non-zero exit code), not just a logged line.
CANT_MISS: dict[Modality, tuple[str, ...]] = {
    Modality.EKG: (
        "STEMI",
        "complete heart block",
        "ventricular tachycardia",
        "hyperkalemia",
        "long QT",
        "Wellens",
    ),
    Modality.CXR: (
        "tension pneumothorax",
        "pneumothorax",
        "large pleural effusion",
        "pneumomediastinum",
        "free air",
    ),
}


@dataclass(frozen=True)
class EvalCase:
    """One labeled evaluation image (the ground truth)."""

    image_path: Path
    modality: Modality
    expected_severity: Severity
    expected_keywords: tuple[str, ...] = ()
    # Clinically important *pertinent negatives* the read must state to rule a
    # condition out (e.g. "no pleural effusion", "stemi absent"). Scored against
    # the summary, findings, AND the systematic checklist -- because for EKG the
    # negatives live in the 16-key checklist (e.g. ``stemi_pattern: absent``).
    expected_negatives: tuple[str, ...] = ()
    # Systematic-checklist axes this image is meant to exercise (e.g.
    # ``("st_segment", "stemi_pattern")`` for a STEMI EKG). Drives the
    # "framework coverage" matrix: every checklist axis should be hit by at
    # least one normal AND one abnormal case.
    target_axes: tuple[str, ...] = ()
    # Can't-miss diagnoses this image actually contains. Each must be caught
    # (abnormal severity + the phrase appears in the read) or the harness
    # fails hard. e.g. ``("STEMI",)`` for an anterior STEMI tracing.
    cant_miss: tuple[str, ...] = ()
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
    negative_hits: list[str]
    negative_misses: list[str]
    negative_recall: float
    schema_ok: bool
    schema_issue: str
    bbox_in_bounds: bool
    finding_count: int
    latency_ms: int
    error: str | None = None
    target_axes: list[str] = field(default_factory=list)
    cant_miss: list[str] = field(default_factory=list)
    # True when every can't-miss diagnosis for this case was caught (abnormal
    # severity AND the phrase appears in the read). Vacuously True when the
    # case carries no can't-miss labels.
    cant_miss_caught: bool = True
    cant_miss_missed: list[str] = field(default_factory=list)


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
    mean_negative_recall: float
    schema_pass_rate: float
    bbox_in_bounds_rate: float
    mean_latency_ms: float
    # Can't-miss hard gate (Task C).
    cant_miss_total: int = 0
    cant_miss_caught_count: int = 0
    cant_miss_missed: list[str] = field(default_factory=list)
    # Framework coverage matrix (Task B): per-modality axis coverage.
    axis_coverage: dict[str, Any] = field(default_factory=dict)
    cases: list[CaseScore] = field(default_factory=list)

    @property
    def cant_miss_passed(self) -> bool:
        """True iff every can't-miss diagnosis across all cases was caught."""
        return not self.cant_miss_missed

    def to_json(self) -> str:
        payload = asdict(self)
        payload.pop("cant_miss_passed", None)
        return json.dumps(payload, indent=2, ensure_ascii=False)


def _severity_group(sev: Severity) -> str:
    return "abnormal" if sev in _ABNORMAL else "normal"


def _haystack(result: AnalysisResult) -> str:
    parts = [result.summary]
    for finding in result.findings:
        parts.append(finding.label)
        parts.append(finding.detail)
    return " ".join(parts).lower()


def _negative_haystack(result: AnalysisResult) -> str:
    """Searchable text for pertinent negatives.

    Extends the positive haystack with the systematic checklist, because a
    pertinent negative is most often expressed there (e.g. EKG
    ``stemi_pattern: absent``) rather than in free-text findings. Both the
    checklist key and its value are included so a negative phrased as either
    ``"stemi"`` (key) or ``"absent"`` (value) can match.
    """
    parts = [_haystack(result)]
    for key, item in result.checklist.items():
        parts.append(key)
        parts.append(item.value)
    return " ".join(parts).lower()


def _recall(needles: tuple[str, ...], haystack: str) -> tuple[list[str], list[str], float]:
    """Split ``needles`` into hits/misses against ``haystack`` and return recall."""
    hits: list[str] = []
    misses: list[str] = []
    for needle in needles:
        if needle.lower() in haystack:
            hits.append(needle)
        else:
            misses.append(needle)
    recall = len(hits) / len(needles) if needles else 1.0
    return hits, misses, round(recall, 3)


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


def _cant_miss_check(
    case: EvalCase, result: AnalysisResult, abnormal_match: bool
) -> tuple[bool, list[str]]:
    """Decide whether every can't-miss diagnosis on this case was caught.

    A can't-miss is *caught* only when BOTH conditions hold:

    * the read flagged the case as abnormal (``severity_abnormal_match``) --
      catching a STEMI but calling it "normal" is still a miss; and
    * the can't-miss phrase appears somewhere in the read (summary, findings,
      or the systematic checklist).

    Returns ``(all_caught, missed_labels)``. Vacuously ``(True, [])`` when the
    case carries no can't-miss labels.
    """
    if not case.cant_miss:
        return True, []
    haystack = _negative_haystack(result)
    missed: list[str] = []
    for label in case.cant_miss:
        if not abnormal_match or label.lower() not in haystack:
            missed.append(label)
    return (not missed), missed


def compute_axis_coverage(
    cases: list[EvalCase], registry: ModalityRegistry
) -> dict[str, Any]:
    """Build the per-modality framework-coverage matrix (Task B).

    For each modality present in ``cases`` we look up its systematic checklist
    axes from ``registry`` and report, per axis, whether at least one *normal*
    and one *abnormal* case exercised it. The headline ``coverage_rate`` is the
    fraction of axes touched by ANY case; ``full_coverage_rate`` is the
    fraction touched by BOTH a normal and an abnormal case (the real bar).
    """
    by_modality: dict[str, dict[str, Any]] = {}
    for case in cases:
        mod_key = case.modality.value
        if mod_key not in by_modality:
            profile = registry.resolve(mod_key)
            axes = sorted(profile.checklist_keys)
            by_modality[mod_key] = {
                "axes": axes,
                "matrix": {a: {"normal": False, "abnormal": False} for a in axes},
            }
        matrix = by_modality[mod_key]["matrix"]
        group = _severity_group(case.expected_severity)
        for axis in case.target_axes:
            if axis in matrix:
                matrix[axis][group] = True

    coverage: dict[str, Any] = {}
    for mod_key, data in by_modality.items():
        axes = data["axes"]
        matrix = data["matrix"]
        total = len(axes)
        touched = [a for a in axes if matrix[a]["normal"] or matrix[a]["abnormal"]]
        full = [a for a in axes if matrix[a]["normal"] and matrix[a]["abnormal"]]
        missing = [a for a in axes if a not in touched]
        coverage[mod_key] = {
            "total_axes": total,
            "covered_axes": len(touched),
            "coverage_rate": round(len(touched) / total, 3) if total else 0.0,
            "fully_covered_axes": len(full),
            "full_coverage_rate": round(len(full) / total, 3) if total else 0.0,
            "missing_axes": missing,
            "matrix": matrix,
        }
    return coverage


def score_case(case: EvalCase, result: AnalysisResult, latency_ms: int) -> CaseScore:
    """Score a single structured result against the case ground truth."""
    hits, misses, recall = _recall(case.expected_keywords, _haystack(result))
    neg_hits, neg_misses, neg_recall = _recall(
        case.expected_negatives, _negative_haystack(result)
    )

    schema_ok, schema_issue = _schema_check(case, result)

    abnormal_match = (
        _severity_group(result.severity)
        == _severity_group(case.expected_severity)
    )
    cant_miss_caught, cant_miss_missed = _cant_miss_check(
        case, result, abnormal_match
    )

    return CaseScore(
        case_label=case.label or case.image_path.name,
        image=case.image_path.name,
        modality=case.modality.value,
        expected_severity=case.expected_severity.value,
        actual_severity=result.severity.value,
        severity_match=result.severity == case.expected_severity,
        severity_abnormal_match=abnormal_match,
        keyword_hits=hits,
        keyword_misses=misses,
        keyword_recall=recall,
        negative_hits=neg_hits,
        negative_misses=neg_misses,
        negative_recall=neg_recall,
        schema_ok=schema_ok,
        schema_issue=schema_issue,
        bbox_in_bounds=_bbox_in_bounds(result),
        finding_count=len(result.findings),
        latency_ms=latency_ms,
        target_axes=list(case.target_axes),
        cant_miss=list(case.cant_miss),
        cant_miss_caught=cant_miss_caught,
        cant_miss_missed=cant_miss_missed,
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
        negative_hits=[],
        negative_misses=list(case.expected_negatives),
        negative_recall=0.0,
        schema_ok=False,
        schema_issue=message,
        bbox_in_bounds=False,
        finding_count=0,
        latency_ms=0,
        error=message,
        target_axes=list(case.target_axes),
        cant_miss=list(case.cant_miss),
        cant_miss_caught=not case.cant_miss,
        cant_miss_missed=list(case.cant_miss),
    )


def _aggregate(
    gateway_mode: str,
    scores: list[CaseScore],
    cases: list[EvalCase],
    registry: ModalityRegistry,
) -> EvalReport:
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
    mean_neg_recall = (
        round(sum(s.negative_recall for s in scored) / n, 3) if n else 0.0
    )
    mean_latency = (
        round(sum(s.latency_ms for s in scored) / n, 1) if n else 0.0
    )

    # Can't-miss hard gate: aggregate across every scored case. A can't-miss
    # diagnosis carried by a case that the read failed to catch is recorded as
    # "<case_label>: <diagnosis>" so the CLI can fail CI on it.
    cant_miss_total = sum(len(s.cant_miss) for s in scores)
    cant_miss_missed: list[str] = []
    for s in scores:
        for label in s.cant_miss_missed:
            cant_miss_missed.append(f"{s.case_label}: {label}")
    cant_miss_caught_count = cant_miss_total - len(cant_miss_missed)

    coverage = compute_axis_coverage(cases, registry)

    return EvalReport(
        gateway_mode=gateway_mode,
        total=len(scores),
        scored=n,
        error_count=errors,
        severity_accuracy=severity_acc,
        severity_abnormal_accuracy=abnormal_acc,
        mean_keyword_recall=mean_recall,
        mean_negative_recall=mean_neg_recall,
        schema_pass_rate=schema_rate,
        bbox_in_bounds_rate=bbox_rate,
        mean_latency_ms=mean_latency,
        cant_miss_total=cant_miss_total,
        cant_miss_caught_count=cant_miss_caught_count,
        cant_miss_missed=cant_miss_missed,
        axis_coverage=coverage,
        cases=scores,
    )


async def run_evaluation(
    cases: list[EvalCase],
    analyze: Callable[[EvalCase], Awaitable[AnalysisResult]],
    *,
    output_dir: Path,
    gateway_mode: str,
    registry: ModalityRegistry | None = None,
) -> EvalReport:
    """Drive every case through ``analyze``, score it, and persist artifacts.

    ``analyze`` is an async callable that returns the structured
    ``AnalysisResult`` for a case (real gateway or mock).  Latency is measured
    here so both modes are timed identically. ``registry`` supplies the
    systematic-checklist axes for the framework-coverage matrix (defaults to
    the active registry).
    """
    active_registry = registry or get_active_registry()
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
        _write_raw_result(results_dir, result, score)

    report = _aggregate(gateway_mode, scores, cases, active_registry)
    (output_dir / "scorecard.json").write_text(report.to_json(), encoding="utf-8")
    return report


def _write_raw_result(
    results_dir: Path,
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
