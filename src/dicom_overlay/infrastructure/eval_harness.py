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
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
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
_PARTIAL_CREDIT_WEIGHTS: dict[str, float] = {
    "severity_abnormal": 0.30,
    "severity_exact": 0.20,
    "keyword_recall": 0.35,
    "negative_recall": 0.15,
}
_KEYWORD_ALIASES: dict[str, tuple[str, ...]] = {
    "no acute": (
        "no acute",
        "no focal",
        "without focal",
        "no visible acute",
        "without acute",
        "no evidence of acute",
        "no acute cardiopulmonary",
    ),
    "infarction": ("infarction", "stemi", "lad territory occlusion", "myocardial infarction"),
    "left ventricular hypertrophy": ("left ventricular hypertrophy", "lvh"),
    "t wave changes": (
        "t wave changes",
        "t wave abnormal",
        "st-t abnormal",
        "st-t changes",
        "st-t repolarization",
        "secondary st-t",
        "repolarization abnormal",
        "repolarization changes",
        "t_wave_changes",
        "inverted",
        "flattened",
    ),
    # EKG clinical synonyms / abbreviations mined from real MEETI runs. Each
    # alias is a strict clinical equivalent of its key, so crediting it reflects
    # a correct read rather than a lexical coincidence. Ambiguous bare
    # abbreviations (e.g. "LAD" = left-axis OR left-anterior-descending) are
    # deliberately excluded to avoid false positives. Negation is still honored
    # by ``_positive_phrase_hit`` so "no atrial fibrillation" never counts.
    "atrial fibrillation": (
        "atrial fibrillation",
        "afib",
        "a fib",
        "irregularly irregular",
    ),
    "irregularly irregular": (
        "irregularly irregular",
        "atrial fibrillation",
        "afib",
    ),
    "atrial flutter": ("atrial flutter", "flutter waves", "sawtooth"),
    "flutter waves": ("flutter waves", "atrial flutter", "sawtooth"),
    "right bundle branch block": ("right bundle branch block", "rbbb"),
    "left bundle branch block": ("left bundle branch block", "lbbb"),
    "axis deviation": (
        "axis deviation",
        "left axis",
        "right axis",
        "leftward axis",
        "rightward axis",
    ),
    "premature ventricular complexes": (
        "premature ventricular complexes",
        "premature ventricular contractions",
        "pvc",
        "ventricular ectopy",
        "ventricular premature",
    ),
    "poor r wave progression": (
        "poor r wave progression",
        "poor precordial r wave",
    ),
    "atrial abnormality": (
        "atrial abnormality",
        "atrial enlargement",
        "left atrial enlargement",
        "right atrial enlargement",
        "left atrial abnormality",
        "right atrial abnormality",
        "p mitrale",
        "p pulmonale",
    ),
    "first degree av block": (
        "first degree av block",
        "1st degree av block",
        "prolonged pr",
    ),
    "prolonged pr": (
        "prolonged pr",
        "pr prolongation",
        "long pr",
        "first degree av block",
    ),
    "low voltage": ("low voltage", "low qrs voltage"),
    "q waves": ("q waves", "q wave", "pathological q", "pathologic q"),
    "fascicular block": (
        "fascicular block",
        "lafb",
        "lpfb",
        "hemiblock",
        "left anterior fascicular",
        "left posterior fascicular",
    ),
    "st elevation": ("st elevation", "st segment elevation", "elevated st"),
    "st depression": ("st depression", "st segment depression", "depressed st"),
}

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
    strict_pass: bool = False
    partial_credit: float = 0.0
    partial_credit_breakdown: dict[str, float] = field(default_factory=dict)
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
    strict_pass_rate: float = 0.0
    mean_partial_credit: float = 0.0
    partial_credit_breakdown: dict[str, float] = field(default_factory=dict)
    # Can't-miss hard gate (Task C).
    cant_miss_total: int = 0
    cant_miss_caught_count: int = 0
    cant_miss_missed: list[str] = field(default_factory=list)
    # Framework coverage matrix (Task B): per-modality axis coverage.
    axis_coverage: dict[str, Any] = field(default_factory=dict)
    target_axis_performance: dict[str, Any] = field(default_factory=dict)
    manifest_total: int = 0
    result_count: int = 0
    is_partial: bool = False
    aborted_reason: str = ""
    updated_at: str = ""
    cases: list[CaseScore] = field(default_factory=list)

    @property
    def cant_miss_passed(self) -> bool:
        """True iff every can't-miss diagnosis across all cases was caught."""
        return not self.cant_miss_missed

    @property
    def is_perfect(self) -> bool:
        """True when every scored dimension is perfect for every case."""
        return not self.perfect_failures()

    def perfect_failures(self) -> list[str]:
        """Human-readable failures for the strict "all image tests pass" gate."""
        failures: list[str] = []
        for score in self.cases:
            prefix = score.case_label
            if score.error:
                failures.append(f"{prefix}: error {score.error}")
                continue
            if not _strict_severity_match(score):
                failures.append(
                    f"{prefix}: severity expected {score.expected_severity} "
                    f"got {score.actual_severity}"
                )
            if score.keyword_misses:
                failures.append(
                    f"{prefix}: missing keywords {', '.join(score.keyword_misses)}"
                )
            if score.negative_misses:
                failures.append(
                    f"{prefix}: missing negatives {', '.join(score.negative_misses)}"
                )
            if not score.schema_ok:
                failures.append(f"{prefix}: schema {score.schema_issue}")
            if not score.bbox_in_bounds:
                failures.append(f"{prefix}: bbox out of bounds")
            for missed in score.cant_miss_missed:
                failures.append(f"{prefix}: missed can't-miss {missed}")
        return failures

    def to_json(self) -> str:
        payload = asdict(self)
        payload.pop("cant_miss_passed", None)
        payload.pop("is_perfect", None)
        return json.dumps(payload, indent=2, ensure_ascii=False)


def _strict_severity_match(score: CaseScore) -> bool:
    """Severity match for strict gate.

    ``info`` is allowed for expected-normal cases because it means a
    non-abnormal observation (e.g. benign early repolarization) rather than a
    missed warning/critical condition. Abnormal severities still require exact
    matching so a STEMI downgraded to warning remains a strict failure.
    """
    if score.severity_match:
        return True
    normalish = {"normal", "info"}
    return (
        score.expected_severity in normalish
        and score.actual_severity in normalish
        and score.severity_abnormal_match
    )


def _strict_severity_values(
    *,
    expected: Severity,
    actual: Severity,
    exact_match: bool,
    abnormal_match: bool,
) -> bool:
    """Strict severity match without needing a pre-built ``CaseScore``."""
    if exact_match:
        return True
    normalish = {Severity.NORMAL, Severity.INFO}
    return expected in normalish and actual in normalish and abnormal_match


def _partial_credit(
    *,
    severity_exact: bool,
    severity_abnormal: bool,
    keyword_recall: float,
    negative_recall: float,
    has_expected_negatives: bool,
    cant_miss_missed: bool,
) -> tuple[float, dict[str, float]]:
    """Clinical partial-credit score for near-miss analysis.

    This intentionally excludes transport/schema/bbox quality: those are
    reported separately so the clinical score answers "how much of the read was
    right?" rather than "was the artifact machine-parseable?".
    """
    breakdown = {
        "severity_abnormal": 1.0 if severity_abnormal else 0.0,
        "severity_exact": 1.0 if severity_exact else 0.0,
        "keyword_recall": keyword_recall,
    }
    weights = dict(_PARTIAL_CREDIT_WEIGHTS)
    if has_expected_negatives:
        breakdown["negative_recall"] = negative_recall
    else:
        weights.pop("negative_recall")
    denominator = sum(weights.values()) or 1.0
    score = sum(
        breakdown[name] * weight for name, weight in weights.items()
    ) / denominator
    if cant_miss_missed:
        score = min(score, 0.4)
    return round(score, 3), breakdown


def _severity_group(sev: Severity) -> str:
    return "abnormal" if sev in _ABNORMAL else "normal"


def _normalize_lexical(text: str) -> str:
    """Fold punctuation/spacing variants so clinical phrasings match.

    Hyphens, underscores, and slashes become spaces and runs of whitespace
    collapse, so "R-wave", "first-degree", "low-voltage", and "ST/T" match
    "r wave", "first degree", "low voltage", and "st t". Purely lexical: it
    never changes clinical meaning, only surface form. Idempotent.
    """
    lowered = text.lower()
    swapped = re.sub(r"[-_/]+", " ", lowered)
    return re.sub(r"\s+", " ", swapped).strip()


def _haystack(result: AnalysisResult) -> str:
    parts = [result.summary]
    for finding in result.findings:
        parts.append(finding.label)
        parts.append(finding.detail)
    for key, item in result.checklist.items():
        parts.append(item.value)
        parts.append(item.value.replace("_", " "))
        if item.status in _ABNORMAL:
            parts.append(key)
            parts.append(key.replace("_", " "))
    return _normalize_lexical(" ".join(parts))


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
    return _normalize_lexical(" ".join(parts))


def _recall(needles: tuple[str, ...], haystack: str) -> tuple[list[str], list[str], float]:
    """Split ``needles`` into hits/misses against ``haystack`` and return recall."""
    hits: list[str] = []
    misses: list[str] = []
    for needle in needles:
        if _keyword_hit(needle, haystack):
            hits.append(needle)
        else:
            misses.append(needle)
    recall = len(hits) / len(needles) if needles else 1.0
    return hits, misses, round(recall, 3)


def _keyword_hit(needle: str, haystack: str) -> bool:
    if _positive_phrase_hit(needle, haystack):
        return True
    return any(
        _positive_phrase_hit(alias, haystack)
        for alias in _KEYWORD_ALIASES.get(_normalize_lexical(needle), ())
    )


def _positive_phrase_hit(phrase: str, haystack: str) -> bool:
    phrase_l = _normalize_lexical(phrase)
    if not phrase_l:
        return False
    start = 0
    while True:
        index = haystack.find(phrase_l, start)
        if index < 0:
            return False
        if not _is_negated_positive_hit(phrase_l, haystack, index):
            return True
        start = index + len(phrase_l)


def _is_negated_positive_hit(phrase: str, haystack: str, index: int) -> bool:
    if phrase.startswith(("no ", "without ", "absent", "negative for ")):
        return False
    before = haystack[max(0, index - 48) : index]
    after = haystack[index + len(phrase) : index + len(phrase) + 48]
    return bool(
        re.search(
            r"\b(no|without|absent|negative for|free of|lack of|"
            r"no evidence of|ruled out|rule out)\b[\w\s,-]{0,32}$",
            before,
        )
        or re.search(r"^\s*(is|was|are|were)?\s*(absent|negative|not seen)\b", after)
    )


def _negative_recall(
    needles: tuple[str, ...], haystack: str
) -> tuple[list[str], list[str], float]:
    """Recall for pertinent negatives, including shared "no A, B, C" clauses."""
    hits: list[str] = []
    misses: list[str] = []
    for needle in needles:
        if _negative_hit(needle, haystack):
            hits.append(needle)
        else:
            misses.append(needle)
    recall = len(hits) / len(needles) if needles else 1.0
    return hits, misses, round(recall, 3)


def _negative_hit(needle: str, haystack: str) -> bool:
    needle_l = _normalize_lexical(needle)
    if needle_l in haystack:
        return True
    if not needle_l.startswith("no "):
        return False

    target = needle_l[3:].strip()
    if not target:
        return False

    # Models often write one negation cue for a list:
    # "No consolidation, pleural effusion, pneumothorax."  Treat each item in
    # that local clause as negated so the scorer does not require awkward
    # repeated phrasing ("no X, no Y, no Z").
    for match in re.finditer(
        r"\b(no|without|absent|negative for|free of)\b", haystack
    ):
        window = haystack[match.end() : match.end() + 160]
        clause = re.split(r"[.;:]", window, maxsplit=1)[0]
        if target in clause:
            return True
    return False


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
        validated = validator.post_analyze(request, result)
    except HookError as exc:
        return False, str(exc)
    if validated.incomplete:
        return False, "; ".join(validated.incomplete_reasons)
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
    haystack = _haystack(result)
    missed: list[str] = []
    for label in case.cant_miss:
        if not abnormal_match or not _keyword_hit(label, haystack):
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
    neg_hits, neg_misses, neg_recall = _negative_recall(
        case.expected_negatives, _negative_haystack(result)
    )

    schema_ok, schema_issue = _schema_check(case, result)

    abnormal_match = (
        _severity_group(result.severity)
        == _severity_group(case.expected_severity)
    )
    severity_match = result.severity == case.expected_severity
    cant_miss_caught, cant_miss_missed = _cant_miss_check(
        case, result, abnormal_match
    )
    partial_credit, partial_breakdown = _partial_credit(
        severity_exact=severity_match,
        severity_abnormal=abnormal_match,
        keyword_recall=recall,
        negative_recall=neg_recall,
        has_expected_negatives=bool(case.expected_negatives),
        cant_miss_missed=bool(cant_miss_missed),
    )
    strict_pass = (
        _strict_severity_values(
            expected=case.expected_severity,
            actual=result.severity,
            exact_match=severity_match,
            abnormal_match=abnormal_match,
        )
        and not misses
        and not neg_misses
        and schema_ok
        and _bbox_in_bounds(result)
        and not cant_miss_missed
    )

    return CaseScore(
        case_label=case.label or case.image_path.name,
        image=case.image_path.name,
        modality=case.modality.value,
        expected_severity=case.expected_severity.value,
        actual_severity=result.severity.value,
        severity_match=severity_match,
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
        strict_pass=strict_pass,
        partial_credit=partial_credit,
        partial_credit_breakdown=partial_breakdown,
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


def _aggregate_partial_breakdown(scores: list[CaseScore]) -> dict[str, float]:
    if not scores:
        return dict.fromkeys(_PARTIAL_CREDIT_WEIGHTS, 0.0)
    output: dict[str, float] = {}
    for name in _PARTIAL_CREDIT_WEIGHTS:
        output[name] = round(
            sum(s.partial_credit_breakdown.get(name, 0.0) for s in scores)
            / len(scores),
            3,
        )
    return output


def _target_axis_performance(scores: list[CaseScore]) -> dict[str, Any]:
    """Aggregate scored performance by manifest ``target_axes``."""
    by_axis: dict[str, list[CaseScore]] = {}
    for score in scores:
        for axis in score.target_axes:
            by_axis.setdefault(axis, []).append(score)

    performance: dict[str, Any] = {}
    for axis, axis_scores in sorted(by_axis.items()):
        count = len(axis_scores)
        performance[axis] = {
            "case_count": count,
            "strict_pass_rate": round(
                sum(1 for s in axis_scores if s.strict_pass) / count, 3
            ),
            "mean_partial_credit": round(
                sum(s.partial_credit for s in axis_scores) / count, 3
            ),
            "mean_keyword_recall": round(
                sum(s.keyword_recall for s in axis_scores) / count, 3
            ),
            "mean_negative_recall": round(
                sum(s.negative_recall for s in axis_scores) / count, 3
            ),
        }
    return performance


def _aggregate(
    gateway_mode: str,
    scores: list[CaseScore],
    cases: list[EvalCase],
    registry: ModalityRegistry,
    *,
    manifest_total: int | None = None,
    aborted_reason: str = "",
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
    total_n = len(scores)
    strict_pass_rate = (
        round(sum(1 for s in scores if s.strict_pass) / total_n, 3)
        if total_n
        else 0.0
    )
    mean_partial_credit = (
        round(sum(s.partial_credit for s in scores) / total_n, 3)
        if total_n
        else 0.0
    )
    partial_breakdown = _aggregate_partial_breakdown(scores)

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
    axis_performance = _target_axis_performance(scores)
    total_manifest = len(cases) if manifest_total is None else manifest_total
    result_count = len(scores)

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
        strict_pass_rate=strict_pass_rate,
        mean_partial_credit=mean_partial_credit,
        partial_credit_breakdown=partial_breakdown,
        cant_miss_total=cant_miss_total,
        cant_miss_caught_count=cant_miss_caught_count,
        cant_miss_missed=cant_miss_missed,
        axis_coverage=coverage,
        target_axis_performance=axis_performance,
        manifest_total=total_manifest,
        result_count=result_count,
        is_partial=result_count < total_manifest or bool(aborted_reason),
        aborted_reason=aborted_reason,
        updated_at=datetime.now(UTC).isoformat(),
        cases=scores,
    )


async def run_evaluation(
    cases: list[EvalCase],
    analyze: Callable[[EvalCase], Awaitable[AnalysisResult]],
    *,
    output_dir: Path,
    gateway_mode: str,
    registry: ModalityRegistry | None = None,
    max_consecutive_infra_errors: int = 5,
    partial_scorecard_interval: int = 50,
    case_metadata: Callable[[EvalCase], dict[str, Any]] | None = None,
) -> EvalReport:
    """Drive every case through ``analyze``, score it, and persist artifacts.

    ``analyze`` is an async callable that returns the structured
    ``AnalysisResult`` for a case (real gateway or mock).  Latency is measured
    here so both modes are timed identically. ``registry`` supplies the
    systematic-checklist axes for the framework-coverage matrix (defaults to
    the active registry). ``partial_scorecard_interval`` bounds checkpoint
    rewrites for 1000+ image runs; the final or aborted scorecard is always
    written.
    """
    active_registry = registry or get_active_registry()
    results_dir = output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    scores: list[CaseScore] = []
    consecutive_infra_errors = 0
    aborted_reason = ""
    for case in cases:
        start = time.monotonic()
        try:
            result = await analyze(case)
        except Exception as exc:
            score = _error_score(case, f"{type(exc).__name__}: {exc}")
            scores.append(score)
            _write_error_result(results_dir, score)
            if _is_infrastructure_error(exc):
                consecutive_infra_errors += 1
            else:
                consecutive_infra_errors = 0
            if (
                max_consecutive_infra_errors > 0
                and consecutive_infra_errors >= max_consecutive_infra_errors
            ):
                aborted_reason = "consecutive_infrastructure_errors"
                _write_scorecard(
                    output_dir / "scorecard.partial.json",
                    gateway_mode,
                    scores,
                    cases,
                    active_registry,
                    aborted_reason=aborted_reason,
                )
                break
            if _should_write_partial_scorecard(
                len(scores), len(cases), partial_scorecard_interval
            ):
                _write_scorecard(
                    output_dir / "scorecard.partial.json",
                    gateway_mode,
                    scores,
                    cases,
                    active_registry,
                )
            continue
        consecutive_infra_errors = 0
        latency_ms = int((time.monotonic() - start) * 1000)
        score = score_case(case, result, latency_ms)
        scores.append(score)
        metadata = case_metadata(case) if case_metadata else None
        _write_raw_result(results_dir, result, score, case_metadata=metadata)
        if _should_write_partial_scorecard(
            len(scores), len(cases), partial_scorecard_interval
        ):
            _write_scorecard(
                output_dir / "scorecard.partial.json",
                gateway_mode,
                scores,
                cases,
                active_registry,
            )

    report = _aggregate(
        gateway_mode,
        scores,
        cases,
        active_registry,
        manifest_total=len(cases),
        aborted_reason=aborted_reason,
    )
    (output_dir / "scorecard.json").write_text(report.to_json(), encoding="utf-8")
    return report


def _write_scorecard(
    path: Path,
    gateway_mode: str,
    scores: list[CaseScore],
    cases: list[EvalCase],
    registry: ModalityRegistry,
    *,
    aborted_reason: str = "",
) -> None:
    report = _aggregate(
        gateway_mode,
        scores,
        cases,
        registry,
        manifest_total=len(cases),
        aborted_reason=aborted_reason,
    )
    path.write_text(report.to_json(), encoding="utf-8")


def _is_infrastructure_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return (
        isinstance(exc, ConnectionError)
        or "not connected to openclaw gateway" in text
        or "connectionclosed" in text
        or "connection closed" in text
        or "websocket" in text
    )


def _should_write_partial_scorecard(
    result_count: int,
    total_count: int,
    interval: int,
) -> bool:
    """Return True when a partial scorecard checkpoint should be refreshed."""
    if result_count <= 0:
        return False
    if result_count >= total_count:
        return True
    return interval > 0 and result_count % interval == 0


def _write_raw_result(
    results_dir: Path,
    result: AnalysisResult,
    score: CaseScore,
    *,
    case_metadata: dict[str, Any] | None = None,
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
        "zoom_hints": list(result.zoom_hints),
        "score": asdict(score),
    }
    if case_metadata:
        raw.update(case_metadata)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in score.case_label)
    (results_dir / f"{safe}.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _write_error_result(results_dir: Path, score: CaseScore) -> None:
    raw = {
        "case": score.case_label,
        "image": score.image,
        "modality": score.modality,
        "summary": "",
        "severity": "(error)",
        "model_used": "",
        "findings": [],
        "checklist": {},
        "zoom_hints": [],
        "error": score.error,
        "score": asdict(score),
    }
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in score.case_label)
    (results_dir / f"{safe}.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )
