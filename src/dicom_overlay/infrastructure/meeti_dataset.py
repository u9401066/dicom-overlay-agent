"""MEETI ECG dataset adapter.

The MEETI corpus (a MIMIC-IV-ECG derived multimodal set) ships one ``.mat`` per
study containing the 12-lead ``signal``, a free-text ``report`` (the cardiologist
/ machine ground-truth diagnosis, semicolon separated), an ``LLM_Interpretation``
narrative, and per-lead ``featuredb_*`` measurement dicts. Studies that also
carry a rendered ``.png`` are the ones usable by the *image* harness.

This module turns a raw MEETI ``report`` string into the ground-truth fields our
evaluation harness consumes (``expected_severity`` / ``keywords`` /
``negatives`` / ``target_axes`` / ``cant_miss``). The mapping is **pure stdlib**
so it is unit-testable without scipy; the ``.mat`` reading helper is isolated and
imports scipy lazily (scipy is a dev/eval-only dependency, never bundled in the
packaged runtime).

The clinical vocabulary deliberately mirrors the EKG can't-miss reference list in
:mod:`dicom_overlay.infrastructure.eval_harness` (``CANT_MISS[Modality.EKG]``):
STEMI, complete heart block, ventricular tachycardia, hyperkalemia, long QT,
Wellens. Severity follows the agent charter -- only *escalate*, never downgrade a
lethal call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The 16 systematic-checklist axes for EKG (must match the dicom-ekg-analysis
# skill and run-eval's ``_EKG_CHECKLIST_KEYS``).
_EKG_AXES = (
    "heart_rate",
    "rhythm",
    "regularity",
    "axis",
    "p_wave",
    "pr_interval",
    "qrs_duration",
    "qrs_morphology",
    "st_segment",
    "t_wave",
    "qtc_interval",
    "chamber_enlargement",
    "conduction",
    "av_block",
    "stemi_pattern",
    "ischemia",
)

# Severity ranks for "only escalate" merging.
_SEV_RANK = {"normal": 0, "warning": 1, "critical": 2}


@dataclass(frozen=True)
class ReportLabels:
    """Ground-truth labels derived from a MEETI ``report`` string."""

    severity: str = "normal"
    keywords: tuple[str, ...] = ()
    negatives: tuple[str, ...] = ()
    target_axes: tuple[str, ...] = ()
    cant_miss: tuple[str, ...] = ()
    # The diagnostic concepts matched (for auditing / dataset balancing).
    concepts: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Concept:
    """One diagnostic concept and how it maps to harness ground truth."""

    name: str
    # Regex (case-insensitive) matched against the report text.
    pattern: str
    severity: str
    keywords: tuple[str, ...]
    axes: tuple[str, ...]
    cant_miss: tuple[str, ...] = ()


# Ordered concept table. Order matters only for ``concepts`` readability; the
# resulting labels are unioned. Patterns use word-ish boundaries to avoid
# substring false-positives (e.g. "infarct" must not fire on "no infarct" -- the
# negation guard below handles that).
_CONCEPTS: tuple[_Concept, ...] = (
    # ---- Can't-miss / critical -------------------------------------------
    _Concept(
        "acute_mi",
        r"\bacute (myocardial infarction|mi|infarct)\b|\bstemi\b|\bst[- ]?elevation\b",
        "critical",
        ("st elevation", "stemi", "infarction"),
        ("st_segment", "stemi_pattern", "ischemia", "t_wave"),
        ("STEMI",),
    ),
    _Concept(
        "complete_heart_block",
        r"\b(complete heart block|third[- ]degree (av )?block|3rd[- ]degree (av )?block)\b",
        "critical",
        ("complete heart block", "av dissociation"),
        ("av_block", "conduction", "rhythm", "pr_interval"),
        ("complete heart block",),
    ),
    _Concept(
        "vtach",
        r"\bventricular tachycardia\b|\bv[- ]?tach\b|\bwide[- ]complex tachycardia\b",
        "critical",
        ("ventricular tachycardia", "wide complex"),
        ("rhythm", "qrs_duration", "qrs_morphology", "heart_rate"),
        ("ventricular tachycardia",),
    ),
    _Concept(
        "hyperkalemia",
        r"\bhyperkalemi|\bpeaked t[- ]?wave",
        "critical",
        ("hyperkalemia", "peaked t wave"),
        ("t_wave", "qrs_duration", "rhythm"),
        ("hyperkalemia",),
    ),
    _Concept(
        "long_qt",
        r"\b(prolonged|long) qt\b|\bqtc? prolong",
        "critical",
        ("prolonged qt", "long qt"),
        ("qtc_interval", "t_wave"),
        ("long QT",),
    ),
    _Concept(
        "wellens",
        r"\bwellens\b|\bbiphasic t[- ]?wave.*v[23]\b",
        "critical",
        ("wellens", "biphasic t wave"),
        ("t_wave", "ischemia", "stemi_pattern"),
        ("Wellens",),
    ),
    _Concept(
        "vfib",
        r"\bventricular fibrillation\b|\bv[- ]?fib\b",
        "critical",
        ("ventricular fibrillation",),
        ("rhythm", "qrs_morphology"),
    ),
    # ---- Warnings (abnormal but not on the EKG can't-miss list) ----------
    _Concept(
        "old_infarct",
        r"\b(old|prior|age[- ]indeterminate|possible) (anterior |inferior |lateral |septal |)infarct",
        "warning",
        ("infarct", "q waves"),
        ("qrs_morphology", "stemi_pattern", "ischemia"),
    ),
    _Concept(
        "ischemia",
        r"\bischemi",
        "warning",
        ("ischemia",),
        ("ischemia", "st_segment", "t_wave"),
    ),
    _Concept(
        "st_depression",
        r"\bst[- ]depression\b",
        "warning",
        ("st depression",),
        ("st_segment", "ischemia"),
    ),
    _Concept(
        "t_wave_abnormality",
        r"\bt[- ]wave (inversion|change|abnormalit)",
        "warning",
        ("t wave changes",),
        ("t_wave",),
    ),
    _Concept(
        "afib",
        r"\batrial fibrillation\b|\ba[- ]?fib\b",
        "warning",
        ("atrial fibrillation", "irregularly irregular"),
        ("rhythm", "regularity", "p_wave", "heart_rate"),
    ),
    _Concept(
        "aflutter",
        r"\batrial flutter\b",
        "warning",
        ("atrial flutter", "flutter waves"),
        ("rhythm", "p_wave", "regularity"),
    ),
    _Concept(
        "svt",
        r"\bsupraventricular tachycardia\b|\bsvt\b|\bpsvt\b",
        "warning",
        ("supraventricular tachycardia",),
        ("rhythm", "heart_rate", "regularity"),
    ),
    _Concept(
        "second_degree_block",
        r"\bsecond[- ]degree (av )?block\b|\bmobitz\b|\bwenckebach\b|\b2:1 (av )?block\b",
        "warning",
        ("second degree av block",),
        ("av_block", "conduction", "pr_interval"),
    ),
    _Concept(
        "first_degree_block",
        r"\bfirst[- ]degree (av )?block\b|\bprolonged pr\b",
        "warning",
        ("first degree av block", "prolonged pr"),
        ("av_block", "pr_interval", "conduction"),
    ),
    _Concept(
        "lbbb",
        r"\bleft bundle[- ]branch block\b|\blbbb\b",
        "warning",
        ("left bundle branch block",),
        ("qrs_duration", "qrs_morphology", "conduction"),
    ),
    _Concept(
        "rbbb",
        r"\bright bundle[- ]branch block\b|\brbbb\b",
        "warning",
        ("right bundle branch block",),
        ("qrs_duration", "qrs_morphology", "conduction"),
    ),
    _Concept(
        "fascicular_block",
        r"\b(left|right) anterior fascicular block\b|\bfascicular block\b|\bbifascicular\b|\bhemiblock\b",
        "warning",
        ("fascicular block",),
        ("axis", "conduction", "qrs_morphology"),
    ),
    _Concept(
        "lvh",
        r"\bleft ventricular hypertrophy\b|\blvh\b",
        "warning",
        ("left ventricular hypertrophy",),
        ("chamber_enlargement", "qrs_morphology", "axis"),
    ),
    _Concept(
        "rvh",
        r"\bright ventricular hypertrophy\b|\brvh\b",
        "warning",
        ("right ventricular hypertrophy",),
        ("chamber_enlargement", "qrs_morphology", "axis"),
    ),
    _Concept(
        "atrial_abnormality",
        r"\b(left|right) atrial (abnormality|enlargement)\b|\bbiatrial\b",
        "warning",
        ("atrial abnormality",),
        ("p_wave", "chamber_enlargement"),
    ),
    _Concept(
        "pvc",
        r"\bpremature ventricular (complex|contraction|beat)|\bpvc\b|\bventricular (premature|ectop|bigeminy|trigeminy|couplet)",
        "warning",
        ("premature ventricular complexes",),
        ("rhythm", "qrs_morphology"),
    ),
    _Concept(
        "pac",
        r"\bpremature atrial (complex|contraction|beat)|\bpac\b|\batrial (premature|ectopic)",
        "warning",
        ("premature atrial complexes",),
        ("rhythm", "p_wave"),
    ),
    _Concept(
        "brady",
        r"\bbradycardi|\bsinus bradycard",
        "warning",
        ("bradycardia",),
        ("heart_rate", "rhythm"),
    ),
    _Concept(
        "tachy",
        r"\btachycardi|\bsinus tachycard",
        "warning",
        ("tachycardia",),
        ("heart_rate", "rhythm"),
    ),
    _Concept(
        "preexcitation",
        r"\bwolff[- ]parkinson|\bwpw\b|\bpre[- ]?excitation\b|\bdelta wave\b",
        "warning",
        ("pre-excitation", "delta wave"),
        ("pr_interval", "qrs_morphology", "conduction"),
    ),
    _Concept(
        "paced",
        r"\bpac(ed|ing) (rhythm|spike|complex)|\bventricular paced\b|\batrial paced\b|\bpacemaker\b",
        "warning",
        ("paced rhythm",),
        ("rhythm", "qrs_morphology", "conduction"),
    ),
    _Concept(
        "axis_deviation",
        r"\b(left|right) axis deviation\b",
        "warning",
        ("axis deviation",),
        ("axis",),
    ),
    _Concept(
        "low_voltage",
        r"\blow voltage\b|\blow qrs voltage\b",
        "warning",
        ("low voltage",),
        ("qrs_morphology",),
    ),
    _Concept(
        "poor_r_progression",
        r"\bpoor r[- ]wave progression\b",
        "warning",
        ("poor r wave progression",),
        ("qrs_morphology", "stemi_pattern"),
    ),
    _Concept(
        "nonspecific_stt",
        r"\bnonspecific (st|t|st[- ]?t)\b|\bnon[- ]specific st",
        "warning",
        ("nonspecific st-t changes",),
        ("st_segment", "t_wave"),
    ),
    _Concept(
        "qt_short",
        r"\bshort qt\b",
        "warning",
        ("short qt",),
        ("qtc_interval",),
    ),
    _Concept(
        "early_repol",
        r"\bearly repolarization\b",
        "warning",
        ("early repolarization",),
        ("st_segment",),
    ),
    # ---- Normal -----------------------------------------------------------
    _Concept(
        "normal",
        r"\bnormal ecg\b|\bnormal sinus rhythm\b|\bwithin normal limits\b|"
        r"\bwithin normal range\b|\bwnl\b|\botherwise normal\b",
        "normal",
        ("normal", "sinus"),
        ("rhythm", "heart_rate", "st_segment"),
    ),
    _Concept(
        "sinus",
        r"\bsinus rhythm\b",
        "normal",
        ("sinus rhythm",),
        ("rhythm", "p_wave", "regularity"),
    ),
)

# Phrases that, when they directly precede a finding, negate it. Used to avoid
# firing a concept on an explicitly ruled-out statement ("no acute infarct").
_NEGATION = re.compile(r"\b(no|without|absent|negative for|rule[d]? out)\b[^;.,]{0,40}$", re.IGNORECASE)


def _is_negated(text: str, match_start: int) -> bool:
    """True if a negation cue appears in the clause just before ``match_start``."""

    clause_start = max(
        text.rfind(";", 0, match_start),
        text.rfind(".", 0, match_start),
        text.rfind(",", 0, match_start),
    )
    prefix = text[clause_start + 1 : match_start]
    return bool(_NEGATION.search(prefix))


def classify_report(report: str) -> ReportLabels:
    """Map a MEETI ``report`` string to harness ground-truth labels.

    Severity is the **maximum** across all matched concepts ("only escalate").
    A report with no abnormal concept (or only sinus/normal) is ``normal``.
    """

    text = (report or "").strip()
    if not text:
        return ReportLabels()

    severity = "normal"
    keywords: list[str] = []
    axes: list[str] = []
    cant_miss: list[str] = []
    concepts: list[str] = []

    for concept in _CONCEPTS:
        match = re.search(concept.pattern, text, re.IGNORECASE)
        if match is None:
            continue
        if _is_negated(text, match.start()):
            continue
        concepts.append(concept.name)
        if _SEV_RANK[concept.severity] > _SEV_RANK[severity]:
            severity = concept.severity
        for kw in concept.keywords:
            if kw not in keywords:
                keywords.append(kw)
        for ax in concept.axes:
            if ax not in axes:
                axes.append(ax)
        for cm in concept.cant_miss:
            if cm not in cant_miss:
                cant_miss.append(cm)

    # A normal tracing should still assert the headline pertinent negatives so
    # the read is scored on ruling lethal calls out, not just on silence.
    negatives: tuple[str, ...] = ()
    if severity == "normal":
        negatives = ("no st elevation", "no block", "no ischemia")
        if not axes:
            axes = ["rhythm", "heart_rate", "st_segment"]

    return ReportLabels(
        severity=severity,
        keywords=tuple(keywords),
        negatives=negatives,
        target_axes=tuple(axes),
        cant_miss=tuple(cant_miss),
        concepts=tuple(concepts),
    )


def read_mat_report(mat_path: str) -> str:
    """Read the ``report`` ground-truth string from a MEETI ``.mat`` file.

    scipy is imported lazily: it is a dev/eval-only dependency and must never be
    pulled into the packaged runtime.
    """

    from scipy.io import loadmat  # type: ignore[import-not-found]  # eval-only dep

    data = loadmat(mat_path)
    raw = data.get("report")
    if raw is None:
        return ""
    flat = raw.ravel()
    if flat.size == 0:
        return ""
    return str(flat[0]).strip()
