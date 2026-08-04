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

# Severity ranks for "only escalate" merging. ``info`` is the conservative
# non-diagnostic state used for uncertain or ungradable reports.
_SEV_RANK = {"normal": 0, "info": 0, "warning": 1, "critical": 2}
REPORT_LABEL_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class ReportLabels:
    """Ground-truth labels derived from a MEETI ``report`` string."""

    severity: str = "info"
    keywords: tuple[str, ...] = ()
    negatives: tuple[str, ...] = ()
    target_axes: tuple[str, ...] = ()
    cant_miss: tuple[str, ...] = ()
    # High-urgency differentials explicitly raised but not asserted by the
    # report (for example, "CONSIDER ACUTE ST ELEVATION MI"). They are scored
    # separately from definitive can’t-miss ground truth.
    urgent_concerns: tuple[str, ...] = ()
    # The diagnostic concepts matched (for auditing / dataset balancing).
    concepts: tuple[str, ...] = ()
    # ``asserted`` labels are suitable positive/normal ground truth. Other
    # values make uncertainty and image/report limitations auditable without
    # pretending that silence means a normal ECG.
    label_status: str = "ungradable"
    uncertain_concepts: tuple[str, ...] = ()
    ungradable_reasons: tuple[str, ...] = ()

    def manifest_fields(self) -> dict[str, object]:
        """Return the complete, auditable manifest projection for one report."""
        return {
            "expected_severity": self.severity,
            "keywords": list(self.keywords),
            "negatives": list(self.negatives),
            "target_axes": list(self.target_axes),
            "cant_miss": list(self.cant_miss),
            "urgent_concerns": list(self.urgent_concerns),
            "concepts": list(self.concepts),
            "label_status": self.label_status,
            "uncertain_concepts": list(self.uncertain_concepts),
            "ungradable_reasons": list(self.ungradable_reasons),
        }


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
    uncertain_urgency: str | None = None


# Ordered concept table. Order matters only for ``concepts`` readability; the
# resulting labels are unioned. Patterns use word-ish boundaries to avoid
# substring false-positives (e.g. "infarct" must not fire on "no infarct" -- the
# negation guard below handles that).
_CONCEPTS: tuple[_Concept, ...] = (
    # ---- Can't-miss / critical -------------------------------------------
    _Concept(
        "stemi",
        r"\bstemi\b|\b(?:acute )?st[- ]?elevation "
        r"(?:myocardial infarction|mi)\b",
        "critical",
        ("st elevation", "stemi"),
        ("st_segment", "stemi_pattern", "ischemia", "t_wave"),
        ("STEMI",),
        "critical",
    ),
    _Concept(
        "acute_mi",
        r"\bacute (?!(?:st[- ]?elevation\b))"
        r"(?:myocardial (?:infarction|infarct)|mi|"
        r"(?:(?:anterior|inferior|lateral|septal|anteroseptal|anterolateral) )?"
        r"infarct(?:ion)?)\b",
        "critical",
        ("acute infarction",),
        ("st_segment", "stemi_pattern", "ischemia", "t_wave"),
        ("acute MI",),
        "critical",
    ),
    _Concept(
        "high_risk_long_qt",
        r"\bqtc?\b[^;.]{0,20}\b(?:5\d{2}|[6-9]\d{2})\s*(?:ms|msec)\b|"
        r"\blong qt syndrome\b",
        "critical",
        ("long qt",),
        ("qtc_interval", "t_wave"),
        ("long QT",),
    ),
    _Concept(
        "complete_heart_block",
        r"\b(?:complete heart block|(?:third|3rd)[- ]degree "
        r"(?:a[- ]?v )?block)\b",
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
        r"\bhyperkalemi",
        "critical",
        ("hyperkalemia",),
        ("t_wave", "qrs_duration", "rhythm"),
        ("hyperkalemia",),
    ),
    _Concept(
        "peaked_t_waves",
        r"\bpeaked t[- ]?wave",
        "warning",
        ("peaked t wave",),
        ("t_wave",),
    ),
    _Concept(
        "tall_t_waves",
        r"\btall t[- ]?wave",
        "warning",
        ("tall t wave",),
        ("t_wave",),
    ),
    _Concept(
        "long_qt",
        r"\b(prolonged|long) qt\b|\bqtc? prolong",
        "warning",
        ("prolonged qt", "long qt"),
        ("qtc_interval", "t_wave"),
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
        "st_elevation",
        r"\bst[- ]?elevation\b|\bst elev\b",
        "warning",
        ("st elevation",),
        ("st_segment", "stemi_pattern", "ischemia"),
    ),
    _Concept(
        "old_infarct",
        r"\b(old|prior|age[- ]indeterminate) "
        r"(anterior |inferior |lateral |septal |)infarct",
        "warning",
        ("infarct", "q waves"),
        ("qrs_morphology", "stemi_pattern", "ischemia"),
    ),
    _Concept(
        "infarct",
        r"\b(anterior |inferior |lateral |septal |myocardial )?infarct(?:ion)?\b",
        "warning",
        ("infarct",),
        ("qrs_morphology", "stemi_pattern", "ischemia"),
    ),
    _Concept(
        "av_dissociation",
        r"\ba[- ]?v dissociation\b|\batrioventricular dissociation\b",
        "warning",
        ("av dissociation",),
        ("av_block", "conduction", "rhythm", "pr_interval"),
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
        r"\bst(?:[- ]junctional)?[- ]depression\b",
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
        "q_waves",
        r"\b(?:pathologic(?:al)? )?"
        r"(?:(?:anterior|inferior|lateral|septal) )?q[- ]?waves?\b",
        "warning",
        ("q waves",),
        ("qrs_morphology", "stemi_pattern", "ischemia"),
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
        r"\b(?:second|2nd)[- ]degree (?:a[- ]?v )?block\b|"
        r"\bmobitz\b|\bwenckebach\b|\b2:1 (?:a[- ]?v )?block\b",
        "warning",
        ("second degree av block",),
        ("av_block", "conduction", "pr_interval"),
    ),
    _Concept(
        "first_degree_block",
        r"\b(?:first|1st)[- ]degree (?:a[- ]?v )?block\b|\bprolonged pr\b",
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
        r"\bpremature ventricular (complex|contraction|beat)|\bpvcs?\b|"
        r"\bventricular (premature|ectop|bigeminy|trigeminy|couplet)",
        "warning",
        ("premature ventricular complexes",),
        ("rhythm", "qrs_morphology"),
    ),
    _Concept(
        "pac",
        r"\bpremature atrial (complex|contraction|beat)|\bpacs?\b|"
        r"\batrial (premature|ectopic)",
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
        r"\bpac(?:ed|ing) (?:rhythm|spike|complex)|"
        r"\b(?:ventricular|atrial|demand) pac(?:ed|ing)\b|\bpacemaker\b",
        "warning",
        ("paced rhythm",),
        ("rhythm", "qrs_morphology", "conduction"),
    ),
    _Concept(
        "axis_deviation",
        r"\b(?:left|right) axis deviation\b|\b(?:left|right)ward axis\b",
        "warning",
        ("axis deviation",),
        ("axis",),
    ),
    _Concept(
        "low_voltage",
        r"\blow voltage\b|\blow qrs voltages?\b",
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
        "early_r_transition",
        r"\babnormal r[- ]wave progression\s*,?\s*early transition\b",
        "warning",
        ("early transition",),
        ("qrs_morphology",),
    ),
    _Concept(
        "nonspecific_stt",
        r"\bnonspecific (?:st|t|st[- ]?t)\b|\bnon[- ]specific st|"
        r"\b(?:st[- ]?t|st junctional|t wave) changes? (?:are |is )?nonspecific\b|"
        r"\bst junctional depression (?:are |is )?nonspecific\b",
        "warning",
        ("nonspecific st-t changes",),
        ("st_segment", "t_wave"),
    ),
    _Concept(
        "iv_conduction_delay",
        r"\b(?:iv|intraventricular) conduction (?:defect|delay)\b|\bivcd\b",
        "warning",
        ("intraventricular conduction delay",),
        ("conduction", "qrs_duration", "qrs_morphology"),
    ),
    _Concept(
        "junctional_rhythm",
        r"\b(?:accelerated )?junctional rhythm\b",
        "warning",
        ("junctional rhythm",),
        ("rhythm", "p_wave", "regularity"),
    ),
    _Concept(
        "ectopic_atrial_rhythm",
        r"\bectopic atrial rhythm\b|\batrial tachycardia\b",
        "warning",
        ("ectopic atrial rhythm",),
        ("rhythm", "p_wave", "heart_rate"),
    ),
    _Concept(
        "sinus_arrhythmia",
        r"\bsinus arrhythmia\b",
        "info",
        ("sinus arrhythmia",),
        ("rhythm", "regularity"),
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
        r"\bearly repol(?:arization)?(?: pattern)?\b",
        "info",
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
        "info",
        ("sinus rhythm",),
        ("rhythm", "p_wave", "regularity"),
    ),
)

# Assertion cues are evaluated per concept occurrence. A concept is ground
# truth only when at least one occurrence is affirmative; negated and uncertain
# mentions are retained for audit but never become positive keywords/can't-miss
# labels.
_NEGATION = re.compile(
    r"\b(no|not|without|neither|absent|negative for|free of|lack of|"
    r"rule[d]? out|excluded)\b[^;.]{0,64}$",
    re.IGNORECASE,
)
_UNCERTAINTY_PREFIX = re.compile(
    r"\b(possible|possibly|probable|probably|suspected|suspicious for|"
    r"suggest(?:s|ed|ing)?(?:ive of)?|consider(?:s|ed|ing)?|"
    r"concerning for|raises? concern for|"
    r"may(?: be| represent)?|might(?: be| represent)?|"
    r"could(?: be| represent)?|cannot exclude|can not exclude|"
    r"unable to exclude|questionable|equivocal|likely)\b[^;.]{0,80}$",
    re.IGNORECASE,
)
_UNCERTAINTY_SUFFIX = re.compile(
    r"^[\s,:-]*(is|was|are|were|remains|pattern)?\s*"
    r"(possible|possibly|probable|probably|suspected|questionable|equivocal|"
    r"uncertain|likely|may(?: be| represent)?|might(?: be| represent)?|"
    r"could(?: be| represent)?|"
    r"suggest(?:s|ed|ing)?(?:ive of)?|consider(?:s|ed|ing)?|"
    r"concerning for|raises? concern for|"
    r"cannot be excluded|can not be excluded|not confirmed|versus|vs\b)",
    re.IGNORECASE,
)
_EXPLANATORY_CONTINUATION = re.compile(
    r"^\s*(?:possibly|probably|likely|"
    r"(?:may|might|could)(?: be| represent)?)\s+"
    r"(?:due to|secondary to|related to|from)\b",
    re.IGNORECASE,
)
_AMBIGUOUS_REPORT = re.compile(
    r"\b(borderline|equivocal|questionable|possible abnormality|"
    r"cannot exclude|can not exclude|unable to exclude)\b",
    re.IGNORECASE,
)
_UNSPECIFIED_ABNORMAL = re.compile(
    r"\babnormal\s+(ecg|electrocardiogram|tracing)\b",
    re.IGNORECASE,
)
_UNGRADABLE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "unsuitable_leads",
        re.compile(
            r"\b(?:lead|leads)\b[^;.]{0,80}\b(?:unsuitable|not suitable|"
            r"uninterpretable|not interpretable|cannot be analyzed|"
            r"unable to analyze)\b|"
            r"\b(?:unsuitable|not suitable|uninterpretable|not interpretable)\b"
            r"[^;.]{0,80}\b(?:lead|leads|analysis|interpretation)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "incomplete_leads",
        re.compile(
            r"\b(?:missing|absent|incomplete)\s+(?:ecg\s+)?lead(?:s)?\b|"
            r"\blead(?:s)?\b[^;.]{0,40}\b(?:missing|not recorded)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "quality_limited",
        re.compile(
            r"\b(?:artifact|noise|poor quality|poor signal)\b[^;.]{0,80}"
            r"\b(?:precludes|precluding|limits|limiting|cannot|unable|"
            r"uninterpretable)\b|"
            r"\b(?:cannot|unable to)\s+(?:analyze|interpret)\b",
            re.IGNORECASE,
        ),
    ),
)


def _clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    markers = (";", ".", ",", "\n")
    left = max(text.rfind(marker, 0, start) for marker in markers) + 1
    candidates = [
        position
        for marker in markers
        if (position := text.find(marker, end)) >= 0
    ]
    right = min(candidates) if candidates else len(text)
    return left, right


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """Return wider context used only for linked morphology explanations."""

    markers = (";", ".", "\n")
    left = max(text.rfind(marker, 0, start) for marker in markers) + 1
    candidates = [
        position
        for marker in markers
        if (position := text.find(marker, end)) >= 0
    ]
    right = min(candidates) if candidates else len(text)
    return left, right


def _assertion_state(
    concept: _Concept,
    text: str,
    match: re.Match[str],
) -> str:
    """Return ``asserted``, ``uncertain``, or ``negated`` for one mention."""

    clause_start, clause_end = _clause_bounds(text, match.start(), match.end())
    prefix = text[clause_start : match.start()]
    suffix = text[match.end() : clause_end]
    matched = re.sub(r"[-_]", " ", match.group(0).lower())
    context_start, context_end = _sentence_bounds(text, match.start(), match.end())
    context = re.sub(r"[-_]", " ", text[context_start:context_end].lower())

    if _NEGATION.search(prefix):
        return "negated"

    # A comma usually separates MEETI findings, but it can also introduce a
    # causal qualifier ("Q waves, possibly due to LVH"). Only carry that
    # narrow explanatory form backward; "RBBB, Possible LVH" stays separate.
    continuation = ""
    if clause_end < len(text) and text[clause_end] == ",":
        continuation_end = min(
            (
                position
                for marker in (";", ".", ",", "\n")
                if (position := text.find(marker, clause_end + 1)) >= 0
            ),
            default=len(text),
        )
        continuation = text[clause_end + 1 : continuation_end]
    if _EXPLANATORY_CONTINUATION.search(continuation):
        return "uncertain"

    # ST elevation attributed to a non-infarction alternative is not a strict
    # positive morphology label. Keep it auditable as uncertain rather than
    # manufacturing a STEMI target from an automated report differential.
    is_generic_st_elevation = concept.name == "st_elevation"
    if is_generic_st_elevation and (
        re.search(r"\bearly repol(?:arization)?\b", context)
        or "pericarditis" in context
        or re.search(
            r"\b(?:due to|secondary to)\s+(?:lvh|hypertrophy)\b", context
        )
        or "normal variant" in context
        or re.search(
            r"\b(?:no|not|without)\s+(?:evidence of\s+)?stemi\b",
            context,
        )
    ):
        return "uncertain"

    if (
        _UNCERTAINTY_PREFIX.search(prefix)
        or _UNCERTAINTY_SUFFIX.search(suffix)
        or re.match(
            r"^(possible|probable|suspected|questionable|equivocal)\b",
            matched,
            re.IGNORECASE,
        )
    ):
        return "uncertain"
    return "asserted"


def _concept_state(concept: _Concept, text: str) -> str | None:
    state: str | None = None
    for match in re.finditer(concept.pattern, text, re.IGNORECASE):
        occurrence = _assertion_state(concept, text, match)
        if occurrence == "asserted":
            return occurrence
        if occurrence == "uncertain":
            state = occurrence
    return state


def _append_unique(items: list[str], values: tuple[str, ...]) -> None:
    for value in values:
        if value not in items:
            items.append(value)


def classify_report(report: str) -> ReportLabels:
    """Map a MEETI ``report`` string to harness ground-truth labels.

    Severity is the **maximum** across affirmative concepts ("only escalate").
    Unmatched, uncertain, or technically ungradable text is ``info`` rather
    than silently becoming normal ground truth.
    """

    text = (report or "").strip()
    if not text:
        return ReportLabels(
            ungradable_reasons=("empty_report",),
        )

    keywords: list[str] = []
    axes: list[str] = []
    cant_miss: list[str] = []
    urgent_concerns: list[str] = []
    uncertain_urgencies: list[str] = []
    asserted: list[_Concept] = []
    uncertain_concepts: list[str] = []

    for concept in _CONCEPTS:
        state = _concept_state(concept, text)
        if state == "asserted":
            asserted.append(concept)
            _append_unique(keywords, concept.keywords)
            _append_unique(axes, concept.axes)
            _append_unique(cant_miss, concept.cant_miss)
        elif state == "uncertain":
            uncertain_concepts.append(concept.name)
            if concept.uncertain_urgency is not None:
                _append_unique(urgent_concerns, concept.cant_miss)
                uncertain_urgencies.append(concept.uncertain_urgency)

    # A STEMI concern already entails acute MI. Keep one gate per clinical
    # risk instead of making a single report satisfy two synonymous urgencies.
    if "STEMI" in urgent_concerns and "acute MI" in urgent_concerns:
        urgent_concerns.remove("acute MI")
    if "STEMI" in cant_miss and "acute MI" in cant_miss:
        cant_miss.remove("acute MI")

    ungradable_reasons = [
        reason for reason, pattern in _UNGRADABLE_RULES if pattern.search(text)
    ]
    has_asserted_abnormal = any(
        concept.severity in {"warning", "critical"} for concept in asserted
    )
    if (
        _UNSPECIFIED_ABNORMAL.search(text)
        and not has_asserted_abnormal
        and not uncertain_concepts
    ):
        ungradable_reasons.append("unspecified_abnormality")
    if _AMBIGUOUS_REPORT.search(text) and not uncertain_concepts:
        uncertain_concepts.append("unspecified_abnormality")
    if not asserted and not uncertain_concepts and not ungradable_reasons:
        ungradable_reasons.append("unmatched_report")

    if has_asserted_abnormal or uncertain_urgencies:
        severity = max(
            (
                *(
                    concept.severity
                    for concept in asserted
                    if concept.severity in {"warning", "critical"}
                ),
                *uncertain_urgencies,
            ),
            key=_SEV_RANK.__getitem__,
        )
    elif uncertain_concepts or ungradable_reasons:
        severity = "info"
    elif any(concept.severity == "normal" for concept in asserted):
        severity = "normal"
    elif any(concept.severity == "info" for concept in asserted):
        severity = "info"
    else:
        severity = "info"

    if ungradable_reasons:
        label_status = "partially_ungradable" if asserted else "ungradable"
    elif uncertain_concepts:
        label_status = "partially_uncertain" if asserted else "uncertain"
    else:
        label_status = "asserted" if asserted else "ungradable"

    # Keep diagnostic concepts separate from reference-label state.  Mixing
    # values such as ``ungradable`` into this field corrupts concept-balanced
    # sampling and makes audit summaries look like diagnoses.
    concepts = [concept.name for concept in asserted]

    return ReportLabels(
        severity=severity,
        keywords=tuple(keywords),
        negatives=(),
        target_axes=tuple(axes),
        cant_miss=tuple(cant_miss),
        urgent_concerns=tuple(urgent_concerns),
        concepts=tuple(concepts),
        label_status=label_status,
        uncertain_concepts=tuple(uncertain_concepts),
        ungradable_reasons=tuple(ungradable_reasons),
    )


def read_mat_report(mat_path: str) -> str:
    """Read the ``report`` ground-truth string from a MEETI ``.mat`` file.

    scipy is imported lazily: it is a dev/eval-only dependency and must never be
    pulled into the packaged runtime.
    """

    from scipy.io import loadmat  # type: ignore[import-untyped]  # eval-only dep

    data = loadmat(mat_path)
    raw = data.get("report")
    if raw is None:
        return ""
    flat = raw.ravel()
    if flat.size == 0:
        return ""
    return str(flat[0]).strip()
