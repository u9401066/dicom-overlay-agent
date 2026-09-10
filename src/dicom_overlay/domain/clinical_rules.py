"""Clinical consistency engine — a data-driven, guideline-grounded safety net.

Beyond *suggesting* a systematic read to OpenClaw (the soft skill prompts), this
module adds a **deterministic, medically-grounded** check that runs on the AI's
*own* structured output. It does **not** impose a diagnosis or second-guess the
model's vision. Instead it catches two failure modes that are clinically
unacceptable:

1. **Internal contradiction** — the structured read describes a lethal sign in
   one field but rates the overall study as normal/benign (e.g. ``st_segment``
   says "ST elevation in V1-V4" yet ``severity`` is ``NORMAL``).
2. **Can't-miss under-call** — a can't-miss pattern term appears anywhere in the
   structured output but the severity is below a clinically required floor.

When a rule fires the engine may:

* **escalate** severity toward an optional rule floor (it *never* downgrades),
  and/or
* **flag the result for human review**, attaching the guideline citation.

The physician always keeps the final diagnostic call (project charter).
Review-only rules preserve uncertainty instead of manufacturing an abnormal
diagnosis from ambiguous language; explicit can't-miss under-calls may still be
escalated. The original evidence always remains visible to the reviewer.

**Why this is not just a hard-coded rule.** Every rule is *data*: it carries a
guideline citation, version, and effective date, and is expressed declaratively
over the structured result (no embedded Python logic per rule). Built-ins are
generated from the audited ``clinical_knowledge`` YAML registry; an optional
site rule pack (``*.rules.yaml``) can still apply a deployment-specific overlay.
The generated Python is pure data so this domain module performs no YAML or file
I/O and cannot drift silently from the checked registry digest.

Domain layer — pure, no I/O, no GUI, no YAML. Loading lives in infrastructure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dicom_overlay.domain.entities import AnalysisResult, Severity
from dicom_overlay.domain.generated_clinical_rules import BUILTIN_RULE_SPECS

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

# Clinical urgency ordering. A higher rank = more urgent. Used so escalation
# only ever moves *up* this scale and never downgrades a finding.
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.NORMAL: 0,
    Severity.INFO: 1,
    Severity.WARNING: 2,
    Severity.CRITICAL: 3,
}


def _max_severity(a: Severity, b: Severity) -> Severity:
    """Return the more urgent of two severities (never downgrades)."""
    return a if _SEVERITY_RANK[a] >= _SEVERITY_RANK[b] else b


# ── Condition model ──────────────────────────────────────────────────


class ConditionError(ValueError):
    """Raised when a rule condition is malformed (unknown field/operator)."""


# Supported declarative operators. Kept tiny and side-effect free so a rule pack
# can never execute arbitrary code — conditions are data, not expressions.
_TEXT_OPS = frozenset(
    {
        "contains_any",
        "contains_any_asserted",
        "contains_any_non_negated",
        "not_contains_any",
        "equals",
    }
)
_SEVERITY_OPS = frozenset({"severity_at_most", "severity_at_least", "equals"})

# Human-readable labels used by the audit catalogue (``explain()`` / ``catalogue()``)
# so a clinician can review the active rule set without reading Python or YAML.
_FIELD_LABELS: dict[str, str] = {
    "severity": "整體嚴重度",
    "summary": "判讀摘要",
    "all_text": "判讀全文",
}
_OP_LABELS: dict[str, str] = {
    "contains_any": "包含任一",
    "contains_any_asserted": "明確肯定任一",
    "contains_any_non_negated": "未否定任一（可保留不確定性）",
    "not_contains_any": "不包含任何",
    "equals": "等於",
    "severity_at_most": "不高於",
    "severity_at_least": "不低於",
}


@dataclass(frozen=True)
class RuleCondition:
    """One declarative predicate over an :class:`AnalysisResult`.

    ``field`` selects a value from the result; ``op`` compares it against
    ``values`` / ``value``. A rule fires only when *all* of its conditions hold.

    Supported ``field`` accessors:

    * ``"severity"`` — the overall result severity (compared by urgency).
    * ``"summary"`` — the free-text summary.
    * ``"checklist.<key>"`` — the text value of one checklist item ("" if absent).
    * ``"checklist.<key>.status"`` — that item's severity (no match if absent).
    * ``"all_text"`` — summary + every finding label/detail + every checklist
      value, concatenated (the broadest haystack).

    Supported ``op`` (text fields): ``contains_any`` / ``not_contains_any``
    (case-insensitive substring against ``values``), ``contains_any_asserted``
    (whole clinical phrase, excluding nearby negation/uncertainty),
    ``contains_any_non_negated`` (whole phrase, allowing uncertainty but excluding
    negation), and ``equals``.
    Supported ``op`` (severity field): ``severity_at_most`` /
    ``severity_at_least`` (against ``value``) and ``equals``.
    """

    field: str
    op: str
    values: tuple[str, ...] = ()
    value: str = ""

    def __post_init__(self) -> None:
        is_severity = self.field == "severity" or self.field.endswith(".status")
        allowed = _SEVERITY_OPS if is_severity else _TEXT_OPS
        if self.op not in allowed:
            raise ConditionError(
                f"operator '{self.op}' not valid for field '{self.field}'"
            )

    def matches(self, result: AnalysisResult) -> bool:
        if self.field == "severity" or self.field.endswith(".status"):
            severity = _resolve_severity(self.field, result)
            return severity is not None and self._match_severity(severity)
        text = _resolve_text(self.field, result)
        return self._match_text(text)

    def matched_terms(self, result: AnalysisResult) -> tuple[str, ...]:
        """Which ``contains_any`` needles actually hit (concrete audit evidence).

        Returns the terms from ``values`` that were found in the target text, so
        a human reviewer can see *which* word in the AI's own output triggered
        the rule. Empty for severity comparisons and non-``contains_any`` ops.
        """
        if self.field == "severity" or self.field.endswith(".status"):
            return ()
        hay = _resolve_text(self.field, result)
        if self.op == "contains_any":
            lowered = hay.lower()
            return tuple(v for v in self.values if v.lower() in lowered)
        if self.op == "contains_any_asserted":
            return tuple(v for v in self.values if _has_asserted_term(hay, v))
        if self.op == "contains_any_non_negated":
            return tuple(v for v in self.values if _has_non_negated_term(hay, v))
        return ()

    def explain(self) -> str:
        """Plain-language description of this predicate for the audit catalogue."""
        label = self._field_label()
        op_label = _OP_LABELS.get(self.op, self.op)
        if self.field == "severity" or self.field.endswith(".status"):
            return f"{label} {op_label} {self.value}"
        operand = " / ".join(self.values) if self.values else self.value
        return f"{label} {op_label}：{operand}"

    def _field_label(self) -> str:
        if self.field.startswith("checklist.") and self.field.endswith(".status"):
            key = self.field.removeprefix("checklist.").removesuffix(".status")
            return f"檢核項目「{key}」狀態"
        if self.field.startswith("checklist."):
            return f"檢核項目「{self.field.split('.', 1)[1]}」"
        return _FIELD_LABELS.get(self.field, self.field)

    def _match_severity(self, severity: Severity) -> bool:
        target = _parse_severity(self.value)
        rank, target_rank = _SEVERITY_RANK[severity], _SEVERITY_RANK[target]
        if self.op == "severity_at_most":
            return rank <= target_rank
        if self.op == "severity_at_least":
            return rank >= target_rank
        return severity == target  # equals

    def _match_text(self, text: str) -> bool:
        hay = text.lower()
        needles = [v.lower() for v in self.values]
        if self.op == "contains_any":
            return any(n in hay for n in needles)
        if self.op == "contains_any_asserted":
            return any(_has_asserted_term(text, value) for value in self.values)
        if self.op == "contains_any_non_negated":
            return any(_has_non_negated_term(text, value) for value in self.values)
        if self.op == "not_contains_any":
            return all(n not in hay for n in needles)
        return hay.strip() == self.value.lower().strip()  # equals


_ASSERTION_NEGATED_PREFIX = re.compile(
    r"\b(?:no|not|without|neither|absent|negative for|free of|lack of|"
    r"lacks|ruled out|rule out|excluded)\b[^.;:\n]{0,56}$"
)
_ASSERTION_NEGATED_SUFFIX = re.compile(
    r"^\s*(?:is|was|are|were|has been)?\s*"
    r"(?:absent|negative|not seen|not present|excluded|ruled out)\b"
)
_ASSERTION_UNCERTAIN_PREFIX = re.compile(
    r"\b(?:possible|possibly|probable|probably|suspected|suspicious for|"
    r"suggestive of|may(?: be| represent)?|might(?: be| represent)?|"
    r"could(?: be| represent)?|cannot exclude|can not exclude|"
    r"unable to exclude|questionable|equivocal|likely)\b[^.;:\n]{0,64}$"
)
_ASSERTION_UNCERTAIN_SUFFIX = re.compile(
    r"^\s*(?:is|was|are|were|remains|pattern)?\s*"
    r"(?:possible|probable|suspected|questionable|equivocal|uncertain|likely|"
    r"cannot be excluded|can not be excluded|is not confirmed|not confirmed|"
    r"versus|vs\b)"
)


def _normalize_assertion_text(value: str) -> str:
    lowered = value.lower()
    separated = re.sub(r"[-_/]+", " ", lowered)
    return re.sub(r"\s+", " ", separated).strip()


def _has_asserted_term(text: str, term: str) -> bool:
    """Return whether ``term`` is asserted, not negated or merely uncertain.

    The bounded local assertion scope avoids false alarms such as ``no STEMI``
    and ``cannot exclude STEMI`` while still accepting a later contrasted
    assertion such as ``no ischemia, but definite STEMI``. This is deliberately
    lexical: the engine audits the model's own claim and does not infer one.
    """
    haystack = _normalize_assertion_text(text)
    needle = _normalize_assertion_text(term)
    if not haystack or not needle:
        return False

    if needle.isascii() and needle[0].isalnum() and needle[-1].isalnum():
        pattern = re.compile(rf"(?<!\w){re.escape(needle)}(?!\w)")
    else:
        pattern = re.compile(re.escape(needle))

    for match in pattern.finditer(haystack):
        before = haystack[max(0, match.start() - 96) : match.start()]
        after = haystack[match.end() : match.end() + 80]
        before = re.split(r"\b(?:but|however|although|yet)\b", before)[-1]
        if (
            _ASSERTION_NEGATED_PREFIX.search(before)
            or _ASSERTION_NEGATED_SUFFIX.search(after)
            or _ASSERTION_UNCERTAIN_PREFIX.search(before)
            or _ASSERTION_UNCERTAIN_SUFFIX.search(after)
        ):
            continue
        return True
    return False


def _has_non_negated_term(text: str, term: str) -> bool:
    """Return whether ``term`` is present and not locally negated.

    Unlike ``_has_asserted_term``, uncertainty is retained. This is for urgent
    rule-out rules where an equivocal emergency differential should alter
    triage without being converted into a confirmed diagnosis.
    """
    haystack = _normalize_assertion_text(text)
    needle = _normalize_assertion_text(term)
    if not haystack or not needle:
        return False

    if needle.isascii() and needle[0].isalnum() and needle[-1].isalnum():
        pattern = re.compile(rf"(?<!\w){re.escape(needle)}(?!\w)")
    else:
        pattern = re.compile(re.escape(needle))

    for match in pattern.finditer(haystack):
        before = haystack[max(0, match.start() - 96) : match.start()]
        after = haystack[match.end() : match.end() + 80]
        before = re.split(r"\b(?:but|however|although|yet)\b", before)[-1]
        if _ASSERTION_NEGATED_PREFIX.search(before) or _ASSERTION_NEGATED_SUFFIX.search(
            after
        ):
            continue
        return True
    return False


def _parse_severity(value: str) -> Severity:
    try:
        return Severity(value.strip().lower())
    except ValueError as exc:  # pragma: no cover - guarded by loader/tests
        raise ConditionError(f"unknown severity '{value}'") from exc


def _resolve_text(field_name: str, result: AnalysisResult) -> str:
    if field_name == "summary":
        return result.summary or ""
    if field_name == "all_text":
        return _all_text(result)
    if field_name.startswith("checklist."):
        key = field_name.split(".", 1)[1]
        item = result.checklist.get(key)
        return item.value if item else ""
    raise ConditionError(f"unknown field '{field_name}'")


def _resolve_severity(field_name: str, result: AnalysisResult) -> Severity | None:
    if field_name == "severity":
        return result.severity
    match = re.fullmatch(r"checklist\.([^.]+)\.status", field_name)
    if match:
        item = result.checklist.get(match.group(1))
        return item.status if item else None
    raise ConditionError(f"unknown severity field '{field_name}'")


def _all_text(result: AnalysisResult) -> str:
    parts: list[str] = [result.summary or ""]
    for finding in result.findings:
        parts.append(finding.label)
        parts.append(finding.detail)
    for item in result.checklist.values():
        parts.append(item.value)
    return " \n".join(p for p in parts if p)


# ── Rule + violation ─────────────────────────────────────────────────


@dataclass(frozen=True)
class ClinicalRule:
    """A single guideline-grounded consistency rule (data, not code).

    A rule fires when **all** ``conditions`` hold for a result. On firing it may
    escalate severity toward optional ``escalate_to`` (never downgrades) and,
    when ``require_review`` is set, flag the result for human review with a
    message that cites the originating guideline.
    """

    id: str
    description: str
    modality: str
    conditions: tuple[RuleCondition, ...]
    message: str
    guideline: str = ""
    guideline_version: str = ""
    effective_date: str = ""
    source_url: str = ""
    escalate_to: Severity | None = None
    require_review: bool = True

    def fires(self, result: AnalysisResult) -> bool:
        return bool(self.conditions) and all(c.matches(result) for c in self.conditions)

    def evidence(self, result: AnalysisResult) -> tuple[str, ...]:
        """Concrete terms from the AI's own output that triggered this rule.

        Aggregates the matched ``contains_any`` needles across all conditions so
        an auditor can see exactly *what wording* caused the escalation, not just
        that the rule fired.
        """
        seen: list[str] = []
        for cond in self.conditions:
            for term in cond.matched_terms(result):
                if term not in seen:
                    seen.append(term)
        return tuple(seen)

    def catalogue_entry(self) -> str:
        """A human-auditable block: intent, plain-language triggers, basis, action.

        This is the per-rule "對照文字說明" a clinician reads to review the rule
        without reading code or YAML.
        """
        lines = [f"[{self.id}] {self.modality}"]
        if self.description:
            lines.append(f"  說明：{self.description}")
        lines.append("  觸發條件（全部成立才命中）：")
        lines.extend(f"    - {c.explain()}" for c in self.conditions)
        citation = self.citation()
        if citation:
            lines.append(f"  醫學依據：{citation}")
        if self.source_url:
            lines.append(f"  來源：{self.source_url}")
        actions: list[str] = []
        if self.escalate_to is not None:
            actions.append(f"升級至 {self.escalate_to.value}")
        if self.require_review:
            actions.append("標記人工複核")
        lines.append(f"  命中行為：{'、'.join(actions) if actions else '僅記錄'}")
        lines.append(f"  訊息：{self.message}")
        return "\n".join(lines)

    def citation(self) -> str:
        """Human-readable provenance, e.g. ``ACC/AHA STEMI (v2013, 2013-01-01)``."""
        if not self.guideline:
            return ""
        bits = [self.guideline]
        meta = ", ".join(
            b
            for b in (
                f"v{self.guideline_version}" if self.guideline_version else "",
                self.effective_date,
            )
            if b
        )
        if meta:
            bits.append(f"({meta})")
        return " ".join(bits)


@dataclass(frozen=True)
class RuleViolation:
    """Records that one rule fired against a result."""

    rule: ClinicalRule
    evidence: tuple[str, ...] = ()

    def reason(self) -> str:
        """Physician-facing line: the message plus its guideline citation."""
        citation = self.rule.citation()
        return (
            f"{self.rule.message}（依據：{citation}）"
            if citation
            else self.rule.message
        )

    def audit_line(self) -> str:
        """Full audit line incl. the matched evidence terms (for logs/review).

        Lets a human see *why* the rule fired — which words in the AI's own
        output were matched — not just that it did.
        """
        base = self.reason()
        if self.evidence:
            return f"{base}｜命中關鍵字：{', '.join(self.evidence)}"
        return base


# ── Engine ───────────────────────────────────────────────────────────


@dataclass
class ClinicalConsistencyEngine:
    """Applies a per-modality rule set to AI results (pure, no I/O).

    ``rules_by_modality`` maps an upper-cased modality key to its rules. Build it
    from built-ins overlaid with an optional rule pack via the infrastructure
    loader; this domain class only interprets the data.
    """

    rules_by_modality: Mapping[str, tuple[ClinicalRule, ...]] = field(
        default_factory=dict
    )

    def rules_for(self, modality_key: str) -> tuple[ClinicalRule, ...]:
        return self.rules_by_modality.get(modality_key.strip().upper(), ())

    def evaluate(self, result: AnalysisResult) -> list[RuleViolation]:
        """Return the rules that fire for ``result`` (does not mutate)."""
        return [
            RuleViolation(rule=rule, evidence=rule.evidence(result))
            for rule in self.rules_for(result.modality.value)
            if rule.fires(result)
        ]

    def catalogue(self) -> str:
        """A human-auditable text dump of every active rule, grouped by modality.

        This is the "對照文字說明" surfaced by ``--explain-rules``: it lets a
        clinician review exactly which rules are live (built-in *plus* any YAML
        overrides), their plain-language triggers, medical basis, and the action
        each takes — without reading code or YAML.
        """
        if not self.rules_by_modality:
            return "（目前沒有生效的臨床一致性規則）"
        blocks: list[str] = []
        for modality in sorted(self.rules_by_modality):
            rules = self.rules_by_modality[modality]
            blocks.append(f"=== {modality}（{len(rules)} 條規則） ===")
            blocks.extend(rule.catalogue_entry() for rule in rules)
            blocks.append("")
        return "\n".join(blocks).rstrip()

    def apply(self, result: AnalysisResult) -> list[RuleViolation]:
        """Evaluate and apply escalations/flags to ``result`` in place.

        Severity is only ever raised. ``review_required`` is set and each fired
        rule's cited reason is appended (de-duplicated). Returns the violations
        so callers can log them. A clean result is left untouched.
        """
        violations = self.evaluate(result)
        if not violations:
            return []

        for violation in violations:
            floor = violation.rule.escalate_to
            if floor is not None:
                result.severity = _max_severity(result.severity, floor)
            if violation.rule.require_review:
                result.review_required = True
                reason = violation.reason()
                if reason not in result.review_reasons:
                    result.review_reasons.append(reason)
        return violations


# ── Built-in rules (generated pure data) ─────────────────────────────


def _generated_condition(raw: object) -> RuleCondition:
    if not isinstance(raw, dict):
        raise ConditionError("generated clinical condition must be an object")
    values = raw.get("values") or ()
    if not isinstance(values, (list, tuple)):
        raise ConditionError("generated clinical condition values must be a list")
    return RuleCondition(
        field=str(raw["field"]),
        op=str(raw["op"]),
        values=tuple(str(value) for value in values),
        value=str(raw.get("value") or ""),
    )


def _generated_rule(raw: object) -> ClinicalRule:
    if not isinstance(raw, dict):
        raise ConditionError("generated clinical rule must be an object")
    conditions = raw.get("conditions")
    if not isinstance(conditions, (list, tuple)) or not conditions:
        raise ConditionError("generated clinical rule must contain conditions")
    escalation = raw.get("escalate_to")
    return ClinicalRule(
        id=str(raw["id"]),
        modality=str(raw["modality"]),
        description=str(raw["description"]),
        conditions=tuple(_generated_condition(item) for item in conditions),
        message=str(raw["message"]),
        guideline=str(raw["guideline"]),
        guideline_version=str(raw["guideline_version"]),
        effective_date=str(raw["effective_date"]),
        source_url=str(raw["source_url"]),
        escalate_to=(
            None if escalation is None else _parse_severity(str(escalation))
        ),
        require_review=bool(raw["require_review"]),
    )


_BUILTIN_RULES: tuple[ClinicalRule, ...] = tuple(
    _generated_rule(spec) for spec in BUILTIN_RULE_SPECS
)

def builtin_rules() -> tuple[ClinicalRule, ...]:
    """Return the default, fully-cited rule set (a fresh tuple each call)."""
    return tuple(_BUILTIN_RULES)


def group_by_modality(
    rules: Iterable[ClinicalRule],
) -> dict[str, tuple[ClinicalRule, ...]]:
    """Group rules into the engine's ``{MODALITY: (rule, ...)}`` shape."""
    grouped: dict[str, list[ClinicalRule]] = {}
    for rule in rules:
        grouped.setdefault(rule.modality.strip().upper(), []).append(rule)
    return {k: tuple(v) for k, v in grouped.items()}


def default_engine() -> ClinicalConsistencyEngine:
    """Engine pre-loaded with the built-in rules only."""
    return ClinicalConsistencyEngine(group_by_modality(builtin_rules()))
