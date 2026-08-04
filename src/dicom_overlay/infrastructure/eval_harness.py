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
    "keyword_recall": 0.20,
    "concept_f1": 0.15,
    "negative_recall": 0.15,
}
_FALSE_POSITIVE_PENALTY_WEIGHT = 0.25


def is_empty_read(result: AnalysisResult) -> bool:
    """True when a result is an unusable empty read (a retry candidate).

    An empty read has a blank summary and no findings: the model returned an
    empty or non-JSON response rather than a real "normal" study. The harness
    retries these once instead of banking a 0-score hard failure.
    """
    return not result.summary.strip() and not result.findings


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
    "infarction": (
        "infarction",
        "stemi",
        "lad territory occlusion",
        "myocardial infarction",
    ),
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
    "early transition": (
        "early transition",
        "early r wave transition",
        "early r/s transition",
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
    "long qt": ("long qt", "prolonged qt", "qtc prolongation"),
    "prolonged qt": ("prolonged qt", "long qt", "qtc prolongation"),
    "premature atrial complexes": (
        "premature atrial complexes",
        "premature atrial contractions",
        "pac",
        "atrial ectopy",
    ),
    "acute infarction": (
        "acute infarction",
        "acute myocardial infarction",
        "acute mi",
        "acute infarct",
    ),
    "nonspecific st-t changes": (
        "nonspecific st-t changes",
        "nonspecific st changes",
        "nonspecific t wave changes",
        "nonspecific repolarization",
    ),
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
    "intraventricular conduction delay": (
        "intraventricular conduction delay",
        "iv conduction defect",
        "iv conduction delay",
        "ivcd",
    ),
    "junctional rhythm": ("junctional rhythm", "accelerated junctional rhythm"),
    "ectopic atrial rhythm": ("ectopic atrial rhythm", "atrial tachycardia"),
    "sinus arrhythmia": ("sinus arrhythmia",),
    "paced rhythm": (
        "paced rhythm",
        "atrial pacing",
        "ventricular pacing",
        "demand pacing",
        "pacemaker rhythm",
    ),
}

# Controlled positive-concept vocabulary used to find *extra* diagnoses.  The
# legacy keyword scorer only measures recall, so an answer could improve its
# score by listing many diagnoses.  This list is intentionally limited to
# clinically meaningful findings rather than generic words such as "abnormal".
# Unknown structured finding labels are handled separately below.
_SCORABLE_CONCEPTS: tuple[str, ...] = (
    "atrial fibrillation",
    "atrial flutter",
    "bradycardia",
    "cardiomegaly",
    "complete heart block",
    "consolidation",
    "early repolarization",
    "fascicular block",
    "first degree av block",
    "hyperkalemia",
    "infarction",
    "ischemia",
    "intraventricular conduction delay",
    "junctional rhythm",
    "left bundle branch block",
    "left ventricular hypertrophy",
    "long qt",
    "low voltage",
    "pleural effusion",
    "pneumomediastinum",
    "pneumothorax",
    "poor r wave progression",
    "early transition",
    "premature ventricular complexes",
    "paced rhythm",
    "right bundle branch block",
    "st depression",
    "st elevation",
    "supraventricular tachycardia",
    "sinus arrhythmia",
    "t wave changes",
    "tension pneumothorax",
    "ventricular fibrillation",
    "ventricular tachycardia",
    "wellens",
)

_GENERIC_FINDING_LABELS = frozenset(
    {
        "abnormality",
        "finding",
        "none",
        "normal",
        "observation",
        "other",
    }
)

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
    # Urgent differentials raised by the reference report without a definitive
    # diagnosis. A correct answer must surface the concern urgently while
    # preserving uncertainty (for example, possible STEMI + reviewer question).
    urgent_concerns: tuple[str, ...] = ()
    label_status: str = "asserted"
    uncertain_concepts: tuple[str, ...] = ()
    ungradable_reasons: tuple[str, ...] = ()
    label: str = ""
    valid_regions: tuple[str, ...] = ()
    # Optional paired raw-waveform evidence. The value is an opaque registry id,
    # never a filesystem path. It is used only by an explicitly enabled
    # ECGFounder experiment arm.
    waveform_artifact_id: str = ""
    waveform_lead_mode: str = ""


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
    clinical_scorable: bool = True
    severity_scorable: bool = True
    false_positive_scorable: bool = True
    label_status: str = "asserted"
    reference_uncertain_concepts: list[str] = field(default_factory=list)
    reference_ungradable_reasons: list[str] = field(default_factory=list)
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
    urgent_concerns: list[str] = field(default_factory=list)
    urgent_concern_hits: list[str] = field(default_factory=list)
    urgent_concern_missed: list[str] = field(default_factory=list)
    urgent_concern_recall: float = 1.0
    # Assertion-aware concept metrics complement the legacy keyword-recall
    # fields. Defaults keep older scorecard readers and direct constructors
    # source-compatible.
    concept_hits: list[str] = field(default_factory=list)
    concept_misses: list[str] = field(default_factory=list)
    concept_false_positives: list[str] = field(default_factory=list)
    concept_precision: float = 1.0
    concept_recall: float = 1.0
    concept_f1: float = 1.0
    false_positive_penalty: float = 0.0


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
    mean_concept_precision: float = 1.0
    mean_concept_recall: float = 1.0
    mean_concept_f1: float = 1.0
    mean_false_positive_penalty: float = 0.0
    clinical_scorable_count: int = 0
    severity_scorable_count: int = 0
    keyword_scorable_count: int = 0
    negative_scorable_count: int = 0
    false_positive_scorable_count: int = 0
    urgent_concern_total: int = 0
    urgent_concern_caught_count: int = 0
    urgent_concern_missed: list[str] = field(default_factory=list)

    @property
    def cant_miss_passed(self) -> bool:
        """True iff every can't-miss diagnosis across all cases was caught."""
        return not self.cant_miss_missed

    @property
    def urgent_concern_passed(self) -> bool:
        """True iff every urgent uncertain differential was surfaced safely."""
        return not self.urgent_concern_missed

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
            if score.clinical_scorable and not _strict_severity_match(score):
                failures.append(
                    f"{prefix}: severity expected {score.expected_severity} "
                    f"got {score.actual_severity}"
                )
            if score.clinical_scorable and score.keyword_misses:
                failures.append(
                    f"{prefix}: missing keywords {', '.join(score.keyword_misses)}"
                )
            if score.clinical_scorable and score.negative_misses:
                failures.append(
                    f"{prefix}: missing negatives {', '.join(score.negative_misses)}"
                )
            if score.clinical_scorable and score.concept_false_positives:
                failures.append(
                    f"{prefix}: false-positive concepts "
                    f"{', '.join(score.concept_false_positives)}"
                )
            if not score.schema_ok:
                failures.append(f"{prefix}: schema {score.schema_issue}")
            if not score.bbox_in_bounds:
                failures.append(f"{prefix}: bbox out of bounds")
            for missed in score.cant_miss_missed:
                failures.append(f"{prefix}: missed can't-miss {missed}")
            for missed in score.urgent_concern_missed:
                failures.append(f"{prefix}: missed urgent concern {missed}")
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
    if not score.severity_scorable or score.severity_match:
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
    concept_precision: float,
    concept_recall: float,
    concept_f1: float,
    false_positive_penalty: float,
    false_positive_scorable: bool,
    negative_recall: float,
    has_expected_keywords: bool,
    has_expected_negatives: bool,
    severity_scorable: bool,
    clinical_scorable: bool,
    cant_miss_missed: bool,
    urgent_concern_recall: float,
    has_urgent_concerns: bool,
    urgent_concern_missed: bool,
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
        "concept_precision": concept_precision,
        "concept_recall": concept_recall,
        "concept_f1": concept_f1,
        "false_positive_penalty": false_positive_penalty,
        # Keep this key for every case so the aggregate breakdown has the same
        # vacuous-recall convention as ``mean_negative_recall``. Its weight is
        # still removed when a case has no expected negatives.
        "negative_recall": negative_recall,
    }
    if has_urgent_concerns:
        breakdown["urgent_concern_recall"] = urgent_concern_recall
    if not clinical_scorable:
        return 0.0, breakdown
    weights = dict(_PARTIAL_CREDIT_WEIGHTS)
    if not severity_scorable:
        weights.pop("severity_abnormal")
        weights.pop("severity_exact")
    if not has_expected_keywords:
        weights.pop("keyword_recall")
    if not false_positive_scorable:
        weights.pop("concept_f1")
    if not has_expected_negatives:
        weights.pop("negative_recall")
    if has_urgent_concerns:
        weights["urgent_concern_recall"] = 0.25
    denominator = sum(weights.values()) or 1.0
    score = (
        sum(breakdown[name] * weight for name, weight in weights.items()) / denominator
    )
    score = max(
        0.0,
        score - (_FALSE_POSITIVE_PENALTY_WEIGHT * false_positive_penalty),
    )
    if cant_miss_missed or urgent_concern_missed:
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


_NEGATED_PREFIX = re.compile(
    r"\b(?:no|not|without|neither|absent|negative for|free of|lack of|"
    r"lacks|denies|ruled out|rule out|excluded|rather than)\b[^.;:]{0,56}$"
)
_NEGATED_SUFFIX = re.compile(
    r"^\s*(?:is|was|are|were|has been)?\s*"
    r"(?:absent|negative|not seen|not present|excluded|ruled out)\b"
)
_UNCERTAIN_PREFIX = re.compile(
    r"\b(?:possible|possibly|probable|probably|suspected|suspicious for|"
    r"suggestive of|may(?: be| represent)?|might(?: be| represent)?|"
    r"could(?: be| represent)?|cannot exclude|can not exclude|"
    r"unable to exclude|questionable|equivocal|likely)\b[^.;:]{0,64}$"
)
_UNCERTAIN_SUFFIX = re.compile(
    r"^\s*(?:is|was|are|were|remains|pattern)?\s*"
    r"(?:possible|probable|suspected|questionable|equivocal|uncertain|likely|"
    r"cannot be excluded|can not be excluded|is not confirmed|not confirmed|"
    r"versus|vs\b)"
)
_LEADING_NON_ASSERTION = re.compile(
    r"^(?:no|not|without|possible|possibly|probable|probably|suspected|"
    r"questionable|equivocal|cannot exclude|can not exclude|"
    r"unable to exclude)\b"
)


def _checklist_value_is_affirmative(value: str) -> bool:
    folded = _normalize_lexical(value)
    if not folded:
        return False
    return not bool(
        re.search(
            r"\b(?:absent|normal|negative|none|not present|without|uncertain|"
            r"equivocal|possible|cannot exclude|early repolarization)\b",
            folded,
        )
    )


def _narrative_haystack(result: AnalysisResult) -> str:
    parts = [result.summary]
    for finding in result.findings:
        # Keep label and detail in one assertion scope. A structured label such
        # as "STEMI" followed by "cannot be excluded" is still uncertain.
        parts.append(f"{finding.label} {finding.detail}")
    return _normalize_lexical(". ".join(part for part in parts if part))


def _haystack(result: AnalysisResult) -> str:
    parts = [_narrative_haystack(result)]
    for key, item in result.checklist.items():
        parts.append(item.value)
        parts.append(item.value.replace("_", " "))
        if item.status in _ABNORMAL:
            # A checklist axis is not itself a diagnosis. In particular,
            # ``stemi_pattern: early_repolarization`` must not manufacture an
            # affirmative STEMI mention merely because the key contains the
            # word. A critical, affirmative structured value may support it.
            if key == "stemi_pattern":
                if (
                    item.status is Severity.CRITICAL
                    and _checklist_value_is_affirmative(item.value)
                    and re.search(
                        r"\b(?:stemi|myocardial infarction|present|positive)\b",
                        _normalize_lexical(item.value),
                    )
                ):
                    parts.append(f"stemi {item.value}")
            else:
                parts.append(key)
                parts.append(key.replace("_", " "))
    return _normalize_lexical(". ".join(part for part in parts if part))


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


def _recall(
    needles: tuple[str, ...], haystack: str
) -> tuple[list[str], list[str], float]:
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
    pattern = re.compile(rf"(?<!\w){re.escape(phrase_l)}(?!\w)")
    for match in pattern.finditer(haystack):
        if not _is_non_asserted_positive_hit(
            phrase_l,
            haystack,
            match.start(),
            match.end(),
        ):
            return True
    return False


def _is_non_asserted_positive_hit(
    phrase: str,
    haystack: str,
    start: int,
    end: int,
) -> bool:
    if phrase.startswith(("no ", "without ", "absent", "negative for ")):
        return False
    before = haystack[max(0, start - 96) : start]
    after = haystack[end : end + 80]
    # Contrast words start a new assertion scope: "no ischemia, but STEMI".
    before = re.split(r"\b(?:but|however|although|yet)\b", before)[-1]
    return bool(
        _NEGATED_PREFIX.search(before)
        or _NEGATED_SUFFIX.search(after)
        or _UNCERTAIN_PREFIX.search(before)
        or _UNCERTAIN_SUFFIX.search(after)
    )


def _canonical_concept(value: str) -> str:
    folded = _normalize_lexical(value)
    for canonical, aliases in _KEYWORD_ALIASES.items():
        forms = (canonical, *aliases)
        if folded in {_normalize_lexical(form) for form in forms}:
            return _normalize_lexical(canonical)
    return folded


def _is_negative_expectation(value: str) -> bool:
    folded = _normalize_lexical(value)
    return folded.startswith(("no ", "without ", "absent", "negative for "))


@dataclass(frozen=True)
class _ConceptMetrics:
    hits: list[str]
    misses: list[str]
    false_positives: list[str]
    precision: float
    recall: float
    f1: float
    false_positive_penalty: float


def _concept_metrics(
    expected_keywords: tuple[str, ...],
    expected_severity: Severity,
    result: AnalysisResult,
    haystack: str,
    *,
    score_false_positives: bool,
) -> _ConceptMetrics:
    expected_groups: dict[str, list[str]] = {}
    for keyword in expected_keywords:
        if _is_negative_expectation(keyword):
            continue
        expected_groups.setdefault(_canonical_concept(keyword), []).append(keyword)

    # Some legacy abnormal cases only label an exercised checklist axis, while
    # an empty ``info`` label can mean uncertain/ungradable. Precision is not
    # identifiable there; treating every diagnosis as false would manufacture
    # errors from missing labels. Only explicit empty-normal ground truth is a
    # valid negative set for false-alarm scoring.
    if not expected_groups and expected_severity is not Severity.NORMAL:
        return _ConceptMetrics(
            hits=[],
            misses=[],
            false_positives=[],
            precision=1.0,
            recall=1.0,
            f1=1.0,
            false_positive_penalty=0.0,
        )

    predicted: set[str] = set()
    for canonical, keywords in expected_groups.items():
        if any(_keyword_hit(keyword, haystack) for keyword in keywords):
            predicted.add(canonical)

    for candidate in _SCORABLE_CONCEPTS:
        if _keyword_hit(candidate, haystack):
            predicted.add(_canonical_concept(candidate))

    # An abnormal structured finding is an asserted prediction even when its
    # label is outside the controlled vocabulary. Do not double-count a label
    # when its full finding text already maps to an expected/known concept.
    for finding in result.findings:
        if finding.severity not in _ABNORMAL:
            continue
        finding_text = _normalize_lexical(f"{finding.label} {finding.detail}")
        label = _normalize_lexical(finding.label)
        if not label or label in _GENERIC_FINDING_LABELS:
            continue
        if _LEADING_NON_ASSERTION.search(finding_text):
            continue
        if any(
            _keyword_hit(keyword, finding_text)
            for keywords in expected_groups.values()
            for keyword in keywords
        ):
            continue
        if any(
            _keyword_hit(candidate, finding_text) for candidate in _SCORABLE_CONCEPTS
        ):
            continue
        predicted.add(_canonical_concept(label))

    expected = set(expected_groups)
    hits = sorted(expected & predicted)
    misses = sorted(expected - predicted)
    false_positives = (
        sorted(predicted - expected) if score_false_positives else []
    )

    precision_predictions = predicted if score_false_positives else predicted & expected
    if precision_predictions:
        precision = len(hits) / len(precision_predictions)
    else:
        precision = 1.0 if not expected else 0.0
    recall = len(hits) / len(expected) if expected else 1.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    penalty = len(false_positives) / len(predicted) if predicted else 0.0
    return _ConceptMetrics(
        hits=hits,
        misses=misses,
        false_positives=false_positives,
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(f1, 3),
        false_positive_penalty=round(penalty, 3),
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
    for match in re.finditer(r"\b(no|without|absent|negative for|free of)\b", haystack):
        window = haystack[match.end() : match.end() + 160]
        clause = re.split(r"[.;:]", window, maxsplit=1)[0]
        if target in clause:
            return True
    return False


def _bbox_in_bounds(result: AnalysisResult) -> bool:
    for finding in result.findings:
        for box in finding.bboxes:
            if box.w <= 0.0 or box.h <= 0.0:
                return False
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
    if validated.validation_warnings:
        return False, "; ".join(validated.validation_warnings)
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
        folded = _normalize_lexical(label)
        if folded == "stemi":
            # STEMI is only caught by a critical read with an affirmative
            # diagnosis. Warning-level early repolarization or a phrase such as
            # "without/cannot exclude STEMI" is not a can't-miss success.
            severity_ok = result.severity is Severity.CRITICAL
            narrative = _narrative_haystack(result)
            phrase_ok = _keyword_hit("stemi", narrative) or _keyword_hit(
                "acute myocardial infarction", narrative
            )
            narrative_mentions_stemi = bool(
                re.search(
                    r"\b(?:stemi|acute myocardial infarction|acute mi)\b",
                    narrative,
                )
            )
            checklist_item = result.checklist.get("stemi_pattern")
            checklist_ok = bool(
                checklist_item
                and checklist_item.status is Severity.CRITICAL
                and _checklist_value_is_affirmative(checklist_item.value)
            )
            caught = severity_ok and (
                phrase_ok or (checklist_ok and not narrative_mentions_stemi)
            )
        else:
            caught = abnormal_match and _keyword_hit(label, haystack)
        if not caught:
            missed.append(label)
    return (not missed), missed


_URGENT_CONCERN_ALIASES: dict[str, tuple[str, ...]] = {
    "stemi": (
        "stemi",
        "st elevation myocardial infarction",
        "acute st elevation mi",
        "hyperacute ischemia",
        "hyperacute ischemic t wave",
    ),
    "acute mi": (
        "acute mi",
        "acute myocardial infarction",
        "acute infarction",
        "acute infarct",
        "acute anterior infarct",
        "acute inferior infarct",
        "acute lateral infarct",
        "acute septal infarct",
        "acute anteroseptal infarct",
        "acute anterolateral infarct",
    ),
    "long qt": ("long qt", "prolonged qt", "qtc prolongation"),
}
_URGENT_NEGATED_PREFIX = re.compile(
    r"\b(?:no|not|without|neither|absent|negative for|free of|"
    r"excluded|ruled out)\b[^.;:]{0,64}$"
)
_URGENT_UNCERTAINTY_CUE = re.compile(
    r"\b(?:possible|possibly|probable|probably|suspected|consider|"
    r"concern(?:ing)? for|rule out|cannot exclude|can not exclude|"
    r"unable to exclude|questionable|equivocal)\b"
)


def _concern_forms(label: str) -> tuple[str, ...]:
    folded = _normalize_lexical(label)
    return _URGENT_CONCERN_ALIASES.get(folded, (folded,))


def _concern_occurrences(
    phrase: str,
    haystack: str,
) -> list[tuple[str, str]]:
    needle = _normalize_lexical(phrase)
    pattern = re.compile(rf"(?<!\w){re.escape(needle)}(?!\w)")
    occurrences: list[tuple[str, str]] = []
    for match in pattern.finditer(haystack):
        before = haystack[max(0, match.start() - 96) : match.start()]
        after = haystack[match.end() : match.end() + 80]
        before = re.split(r"\b(?:but|however|although|yet)\b", before)[-1]
        if _URGENT_NEGATED_PREFIX.search(before) or _NEGATED_SUFFIX.search(after):
            continue
        occurrences.append((before, after))
    return occurrences


def _non_negated_concern_hit(label: str, haystack: str) -> bool:
    return any(_concern_occurrences(form, haystack) for form in _concern_forms(label))


def _uncertainty_contract_for_concern(
    label: str,
    result: AnalysisResult,
) -> bool:
    narrative = _narrative_haystack(result)
    for form in _concern_forms(label):
        for before, after in _concern_occurrences(form, narrative):
            local = f"{before[-64:]} {after[:64]}"
            if (
                _UNCERTAIN_PREFIX.search(before)
                or _UNCERTAIN_SUFFIX.search(after)
                or _URGENT_UNCERTAINTY_CUE.search(local)
            ):
                return True
    for finding in result.findings:
        finding_text = _normalize_lexical(f"{finding.label} {finding.detail}")
        if (
            _non_negated_concern_hit(label, finding_text)
            and finding.confidence == "low"
            and finding.question.strip()
        ):
            return True
    return False


def _urgent_concern_check(
    case: EvalCase,
    result: AnalysisResult,
) -> tuple[list[str], list[str], float]:
    """Score urgent uncertain differentials without forcing a diagnosis."""
    if not case.urgent_concerns:
        return [], [], 1.0
    narrative = _narrative_haystack(result)
    hits: list[str] = []
    misses: list[str] = []
    for label in case.urgent_concerns:
        surfaced = (
            result.severity is Severity.CRITICAL
            and _non_negated_concern_hit(label, narrative)
            and _uncertainty_contract_for_concern(label, result)
        )
        (hits if surfaced else misses).append(label)
    return hits, misses, round(len(hits) / len(case.urgent_concerns), 3)


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
    haystack = _haystack(result)
    hits, misses, recall = _recall(case.expected_keywords, haystack)
    false_positive_scorable = case.label_status == "asserted"
    concept = _concept_metrics(
        case.expected_keywords,
        case.expected_severity,
        result,
        haystack,
        score_false_positives=false_positive_scorable,
    )
    neg_hits, neg_misses, neg_recall = _negative_recall(
        case.expected_negatives, _negative_haystack(result)
    )

    schema_ok, schema_issue = _schema_check(case, result)

    severity_scorable = case.expected_severity is not Severity.INFO
    clinical_scorable = severity_scorable or bool(
        case.expected_keywords
        or case.expected_negatives
        or case.cant_miss
        or case.urgent_concerns
    )
    abnormal_match = _severity_group(result.severity) == _severity_group(
        case.expected_severity
    )
    severity_match = result.severity == case.expected_severity
    severity_credit_match = not severity_scorable or _strict_severity_values(
        expected=case.expected_severity,
        actual=result.severity,
        exact_match=severity_match,
        abnormal_match=abnormal_match,
    )
    cant_miss_caught, cant_miss_missed = _cant_miss_check(case, result, abnormal_match)
    urgent_hits, urgent_missed, urgent_recall = _urgent_concern_check(case, result)
    partial_credit, partial_breakdown = _partial_credit(
        severity_exact=severity_credit_match,
        severity_abnormal=abnormal_match,
        keyword_recall=recall,
        concept_precision=concept.precision,
        concept_recall=concept.recall,
        concept_f1=concept.f1,
        false_positive_penalty=concept.false_positive_penalty,
        false_positive_scorable=false_positive_scorable,
        negative_recall=neg_recall,
        has_expected_keywords=bool(case.expected_keywords),
        has_expected_negatives=bool(case.expected_negatives),
        severity_scorable=severity_scorable,
        clinical_scorable=clinical_scorable,
        cant_miss_missed=bool(cant_miss_missed),
        urgent_concern_recall=urgent_recall,
        has_urgent_concerns=bool(case.urgent_concerns),
        urgent_concern_missed=bool(urgent_missed),
    )
    bbox_in_bounds = _bbox_in_bounds(result)
    strict_pass = (
        severity_credit_match
        and not misses
        and not neg_misses
        and not concept.false_positives
        and schema_ok
        and bbox_in_bounds
        and not cant_miss_missed
        and not urgent_missed
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
        bbox_in_bounds=bbox_in_bounds,
        finding_count=len(result.findings),
        latency_ms=latency_ms,
        clinical_scorable=clinical_scorable,
        severity_scorable=severity_scorable,
        false_positive_scorable=false_positive_scorable,
        label_status=case.label_status,
        reference_uncertain_concepts=list(case.uncertain_concepts),
        reference_ungradable_reasons=list(case.ungradable_reasons),
        strict_pass=strict_pass,
        partial_credit=partial_credit,
        partial_credit_breakdown=partial_breakdown,
        target_axes=list(case.target_axes),
        cant_miss=list(case.cant_miss),
        cant_miss_caught=cant_miss_caught,
        cant_miss_missed=cant_miss_missed,
        urgent_concerns=list(case.urgent_concerns),
        urgent_concern_hits=urgent_hits,
        urgent_concern_missed=urgent_missed,
        urgent_concern_recall=urgent_recall,
        concept_hits=concept.hits,
        concept_misses=concept.misses,
        concept_false_positives=concept.false_positives,
        concept_precision=concept.precision,
        concept_recall=concept.recall,
        concept_f1=concept.f1,
        false_positive_penalty=concept.false_positive_penalty,
    )


def _error_score(case: EvalCase, message: str) -> CaseScore:
    severity_scorable = case.expected_severity is not Severity.INFO
    clinical_scorable = severity_scorable or bool(
        case.expected_keywords
        or case.expected_negatives
        or case.cant_miss
        or case.urgent_concerns
    )
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
        clinical_scorable=clinical_scorable,
        severity_scorable=severity_scorable,
        false_positive_scorable=case.label_status == "asserted",
        label_status=case.label_status,
        reference_uncertain_concepts=list(case.uncertain_concepts),
        reference_ungradable_reasons=list(case.ungradable_reasons),
        error=message,
        target_axes=list(case.target_axes),
        cant_miss=list(case.cant_miss),
        cant_miss_caught=not case.cant_miss,
        cant_miss_missed=list(case.cant_miss),
        urgent_concerns=list(case.urgent_concerns),
        urgent_concern_missed=list(case.urgent_concerns),
        urgent_concern_recall=0.0 if case.urgent_concerns else 1.0,
        concept_misses=sorted(
            {
                _canonical_concept(keyword)
                for keyword in case.expected_keywords
                if not _is_negative_expectation(keyword)
            }
        ),
        concept_precision=0.0,
        concept_recall=0.0,
        concept_f1=0.0,
    )


def _aggregate_partial_breakdown(scores: list[CaseScore]) -> dict[str, float]:
    if not scores:
        return {
            **dict.fromkeys(_PARTIAL_CREDIT_WEIGHTS, 0.0),
            "concept_precision": 0.0,
            "concept_recall": 0.0,
            "false_positive_penalty": 0.0,
            "urgent_concern_recall": 0.0,
        }
    output: dict[str, float] = {}
    names = (
        *_PARTIAL_CREDIT_WEIGHTS,
        "concept_precision",
        "concept_recall",
        "false_positive_penalty",
        "urgent_concern_recall",
    )
    for name in names:
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
            "mean_concept_precision": round(
                sum(s.concept_precision for s in axis_scores) / count, 3
            ),
            "mean_concept_recall": round(
                sum(s.concept_recall for s in axis_scores) / count, 3
            ),
            "mean_concept_f1": round(sum(s.concept_f1 for s in axis_scores) / count, 3),
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

    def _rate(items: list[CaseScore], predicate: Any) -> float:
        if not items:
            return 0.0
        return round(sum(1 for s in items if predicate(s)) / len(items), 3)

    clinical_scored = [s for s in scored if s.clinical_scorable]
    clinical_all = [s for s in scores if s.clinical_scorable]
    severity_scored = [s for s in scored if s.severity_scorable]
    keyword_scored = [s for s in scored if s.keyword_hits or s.keyword_misses]
    negative_scored = [s for s in scored if s.negative_hits or s.negative_misses]
    false_positive_scored = [
        s for s in clinical_scored if s.false_positive_scorable
    ]

    severity_acc = _rate(severity_scored, lambda s: s.severity_match)
    abnormal_acc = _rate(severity_scored, lambda s: s.severity_abnormal_match)
    schema_rate = _rate(scored, lambda s: s.schema_ok)
    bbox_rate = _rate(scored, lambda s: s.bbox_in_bounds)
    mean_recall = (
        round(sum(s.keyword_recall for s in keyword_scored) / len(keyword_scored), 3)
        if keyword_scored
        else 1.0
    )
    mean_neg_recall = (
        round(
            sum(s.negative_recall for s in negative_scored) / len(negative_scored),
            3,
        )
        if negative_scored
        else 1.0
    )
    mean_concept_precision = (
        round(
            sum(s.concept_precision for s in false_positive_scored)
            / len(false_positive_scored),
            3,
        )
        if false_positive_scored
        else 0.0
    )
    mean_concept_recall = (
        round(
            sum(s.concept_recall for s in clinical_scored) / len(clinical_scored),
            3,
        )
        if clinical_scored
        else 0.0
    )
    mean_concept_f1 = (
        round(
            sum(s.concept_f1 for s in false_positive_scored)
            / len(false_positive_scored),
            3,
        )
        if false_positive_scored
        else 0.0
    )
    mean_false_positive_penalty = (
        round(
            sum(s.false_positive_penalty for s in false_positive_scored)
            / len(false_positive_scored),
            3,
        )
        if false_positive_scored
        else 0.0
    )
    mean_latency = round(sum(s.latency_ms for s in scored) / n, 1) if n else 0.0
    strict_pass_rate = (
        round(
            sum(1 for s in clinical_all if s.strict_pass) / len(clinical_all),
            3,
        )
        if clinical_all
        else 0.0
    )
    mean_partial_credit = (
        round(
            sum(s.partial_credit for s in clinical_all) / len(clinical_all),
            3,
        )
        if clinical_all
        else 0.0
    )
    partial_breakdown = _aggregate_partial_breakdown(clinical_scored)

    # Can't-miss hard gate: aggregate across every scored case. A can't-miss
    # diagnosis carried by a case that the read failed to catch is recorded as
    # "<case_label>: <diagnosis>" so the CLI can fail CI on it.
    cant_miss_total = sum(len(s.cant_miss) for s in scores)
    cant_miss_missed: list[str] = []
    for s in scores:
        for label in s.cant_miss_missed:
            cant_miss_missed.append(f"{s.case_label}: {label}")
    cant_miss_caught_count = cant_miss_total - len(cant_miss_missed)

    urgent_concern_total = sum(len(s.urgent_concerns) for s in scores)
    urgent_concern_missed: list[str] = []
    for score in scores:
        urgent_concern_missed.extend(
            f"{score.case_label}: {label}" for label in score.urgent_concern_missed
        )
    urgent_concern_caught_count = urgent_concern_total - len(urgent_concern_missed)

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
        mean_concept_precision=mean_concept_precision,
        mean_concept_recall=mean_concept_recall,
        mean_concept_f1=mean_concept_f1,
        mean_false_positive_penalty=mean_false_positive_penalty,
        clinical_scorable_count=len(clinical_all),
        severity_scorable_count=len(severity_scored),
        keyword_scorable_count=len(keyword_scored),
        negative_scorable_count=len(negative_scored),
        false_positive_scorable_count=len(false_positive_scored),
        urgent_concern_total=urgent_concern_total,
        urgent_concern_caught_count=urgent_concern_caught_count,
        urgent_concern_missed=urgent_concern_missed,
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
            metadata = case_metadata(case) if case_metadata else None
            score = _error_score(case, f"{type(exc).__name__}: {exc}")
            scores.append(score)
            _write_error_result(
                results_dir,
                score,
                case_metadata=metadata,
            )
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
        "analysis_time_ms": result.analysis_time_ms,
        "model_used": result.model_used,
        "image_quality": result.image_quality,
        "next_steps": list(result.next_steps),
        "incomplete": result.incomplete,
        "incomplete_reasons": list(result.incomplete_reasons),
        "validation_warnings": list(result.validation_warnings),
        "review_required": result.review_required,
        "review_reasons": list(result.review_reasons),
        "layout": dict(result.layout),
        "analysis_trace": list(result.analysis_trace),
        "findings": [
            {
                "id": f.id,
                "label": f.label,
                "detail": f.detail,
                "severity": f.severity.value,
                "regions": f.regions,
                "bboxes": [{"x": b.x, "y": b.y, "w": b.w, "h": b.h} for b in f.bboxes],
                "notes": list(f.notes),
                "confidence": f.confidence,
                "question": f.question,
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


def _write_error_result(
    results_dir: Path,
    score: CaseScore,
    *,
    case_metadata: dict[str, Any] | None = None,
) -> None:
    raw = {
        "case": score.case_label,
        "image": score.image,
        "modality": score.modality,
        "summary": "",
        "severity": "(error)",
        "analysis_time_ms": 0,
        "model_used": "",
        "image_quality": "",
        "next_steps": [],
        "incomplete": True,
        "incomplete_reasons": [score.error],
        "validation_warnings": [],
        "review_required": True,
        "review_reasons": [score.error],
        "layout": {},
        "analysis_trace": [],
        "findings": [],
        "checklist": {},
        "zoom_hints": [],
        "error": score.error,
        "score": asdict(score),
    }
    if case_metadata:
        raw.update(case_metadata)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in score.case_label)
    (results_dir / f"{safe}.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )
