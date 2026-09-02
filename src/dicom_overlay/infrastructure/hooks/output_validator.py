"""Output validation hook -- enforces AnalysisResult schema after AI response."""

from __future__ import annotations

import dataclasses
import math
import re

import structlog

from dicom_overlay.application.interpretation_harness import (
    PARTIAL_ECG_VISIBLE_PIXELS_SCOPE,
)
from dicom_overlay.domain.ekg_layout import (
    normalize_ekg_row_strip_layout,
    parse_ekg_lead_inventory,
    parse_normalized_region,
)
from dicom_overlay.domain.entities import AnalysisResult, RegionRect, Severity
from dicom_overlay.domain.hooks import AnalyzeHook, AnalyzeRequest, HookError
from dicom_overlay.domain.modality_profile import (
    ModalityRegistry,
    get_active_registry,
)

logger = structlog.get_logger(__name__)

_VALID_SEVERITIES = frozenset(s.value for s in Severity)
_EKG_MAX_BOX_WIDTH = 0.35
_EKG_MAX_BOX_HEIGHT = 0.30
_EKG_MAX_BOX_AREA = 0.08
_PROFESSIONAL_REFUSAL_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bas an ai(?: language model| assistant)?\b",
        r"\bi(?: am|'m|’m) not (?:a )?(?:doctor|physician|medical professional|radiologist|cardiologist)\b",
        r"\bi (?:cannot|can't|can’t|am unable to) (?:analy[sz]e|interpret|review) (?:this|the|an? )?(?:medical )?(?:image|x[- ]?ray|radiograph|ecg|ekg)\b",
        r"\b(?:i|we|this (?:ai|assistant|system)|the (?:ai|assistant|system)) "
        r"(?:cannot|can't|can’t|am unable to|are unable to) provide (?:a )?"
        r"(?:diagnosis|medical advice|clinical interpretation)\b",
        r"\bnot (?:a )?substitute for (?:professional )?medical (?:advice|judg(?:e)?ment)\b",
        r"\bfor (?:informational|educational) purposes only\b",
        r"\bi (?:cannot|can't|can’t) assist with (?:that|this) request\b",
        r"(?:身為|作為)(?:一個)?\s*(?:ai|人工智慧)(?:語言模型|助理)?",
        r"(?:僅供|只供)(?:一般)?(?:參考|資訊|教育)(?:用途)?",
        r"(?:不能|無法|不可)取代(?:專業)?(?:醫療|醫師|醫生)(?:建議|判斷|診斷)?",
        r"(?:我|本系統|本助理|人工智慧(?:系統|助理)?)(?:無法|不能)提供"
        r"(?:醫療)?(?:診斷|醫療建議)",
    )
)
EKG_RESULT_LAYOUT_FORMATS = frozenset(
    {
        "12lead_3x4",
        "12lead_3x4_rhythm",
        "6lead",
        "3lead",
        "single_rhythm_strip",
        "partial",
        "non_standard",
        "unknown",
        # Compact public model form and internal canonical form used for a
        # full-width 12-row strip. The local normalizer supplies row geometry.
        "12lead_12x1",
    }
)


class OutputValidator(AnalyzeHook):
    """Post-analyze guardrail: validates AI output against expected schema."""

    def __init__(
        self, *, strict: bool = False, registry: ModalityRegistry | None = None
    ) -> None:
        self._strict = strict
        self._registry = registry or get_active_registry()

    def pre_analyze(self, request: AnalyzeRequest) -> AnalyzeRequest:
        return request  # Output validator only validates output

    def post_analyze(
        self, request: AnalyzeRequest, result: AnalysisResult
    ) -> AnalysisResult:
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Summary must not be empty
        if not result.summary or not result.summary.strip():
            errors.append("AI returned empty summary")
        if _contains_generic_refusal_or_disclaimer(result):
            errors.append(
                "AI returned generic refusal or disclaimer instead of "
                "professional co-reading output"
            )

        # 2. Modality must match request
        if result.modality != request.modality:
            warnings.append(
                f"Modality mismatch: requested {request.modality.value}, "
                f"got {result.modality.value} -- auto-corrected"
            )
            result.modality = request.modality

        ekg_inventory = None
        ekg_visible_regions: set[str] = set()
        if request.modality.value == "EKG":
            normalized_layout, layout_repaired = normalize_ekg_row_strip_layout(
                result.layout
            )
            if layout_repaired:
                result.layout = normalized_layout
                result.analysis_trace.append(
                    {
                        "stage": "layout_normalization",
                        "status": "repaired",
                        "tool": "local_ekg_row_strip_normalizer",
                        "format": "12lead_12x1",
                        "lead_count": 12,
                    }
                )
            ekg_inventory = parse_ekg_lead_inventory(result.layout)
            ekg_visible_regions = set(ekg_inventory.by_name())
            layout_format = str(result.layout.get("format") or "").strip()
            if layout_format not in EKG_RESULT_LAYOUT_FORMATS:
                warnings.append(
                    f"EKG layout has unsupported format: {layout_format or '(missing)'}"
                )
            if _has_normalized_bbox(
                result.layout.get("rhythm_strip_bbox")
                if isinstance(result.layout, dict)
                else None
            ):
                ekg_visible_regions.add("rhythm_strip")

        # 3. Validate findings
        seen_finding_ids: set[str] = set()
        for i, finding in enumerate(result.findings):
            if not finding.id:
                errors.append(f"Finding[{i}] missing id")
            elif finding.id in seen_finding_ids:
                errors.append(f"Finding[{i}] duplicates id '{finding.id}'")
            else:
                seen_finding_ids.add(finding.id)
            if not finding.label:
                errors.append(f"Finding[{i}] missing label")
            # Check regions are from valid set
            for region in finding.regions:
                if region not in request.valid_regions:
                    warnings.append(
                        f"Finding[{i}] region '{region}' "
                        f"not in valid regions"
                    )
            if request.modality.value == "EKG" and finding.regions:
                unavailable = [
                    region
                    for region in finding.regions
                    if region in request.valid_regions
                    and region not in ekg_visible_regions
                ]
                if unavailable:
                    finding = dataclasses.replace(
                        finding,
                        regions=[
                            region
                            for region in finding.regions
                            if region not in unavailable
                        ],
                    )
                    result.findings[i] = finding
                    warnings.append(
                        f"Finding[{i}] referenced leads absent from the visible "
                        f"inventory: {', '.join(unavailable)}; regions removed"
                    )
            if finding.severity is Severity.NORMAL and finding.bboxes:
                finding = dataclasses.replace(finding, bboxes=[])
                result.findings[i] = finding
                warnings.append(
                    f"Finding[{i}] normal/negative observation had overlay boxes; "
                    "boxes removed"
                )
            if finding.bboxes:
                accepted_boxes = [
                    box for box in finding.bboxes if _is_positive_normalized_bbox(box)
                ]
                if len(accepted_boxes) != len(finding.bboxes):
                    finding = dataclasses.replace(finding, bboxes=accepted_boxes)
                    result.findings[i] = finding
                    warnings.append(
                        f"Finding[{i}] zero-area or invalid overlay boxes were removed"
                    )
            if request.modality.value == "EKG" and finding.bboxes:
                accepted_boxes = [
                    box
                    for box in finding.bboxes
                    if box.w <= _EKG_MAX_BOX_WIDTH
                    and box.h <= _EKG_MAX_BOX_HEIGHT
                    and box.w * box.h <= _EKG_MAX_BOX_AREA
                ]
                if len(accepted_boxes) != len(finding.bboxes):
                    finding = dataclasses.replace(finding, bboxes=accepted_boxes)
                    result.findings[i] = finding
                    warnings.append(
                        f"Finding[{i}] broad EKG lead-strip boxes were removed"
                    )
            if (
                finding.severity is Severity.INFO
                and finding.bboxes
                and not finding.confidence.strip()
            ):
                finding = dataclasses.replace(finding, bboxes=[])
                result.findings[i] = finding
                warnings.append(
                    f"Finding[{i}] unqualified info finding had overlay boxes; "
                    "boxes removed"
                )
            if finding.confidence == "low" and not finding.question.strip():
                finding_name = finding.label.strip() or finding.id or f"Finding[{i}]"
                finding = dataclasses.replace(
                    finding,
                    question=(
                        f"Can the reviewer confirm whether {finding_name} is present "
                        "in the highlighted source-image region?"
                    ),
                )
                result.findings[i] = finding
                warnings.append(
                    f"Finding[{i}] low-confidence finding lacked a reviewer "
                    "question; a bounded confirmation question was added"
                )
            if (
                finding.severity is Severity.INFO
                and finding.bboxes
                and (
                    not finding.confidence
                    or (
                        finding.confidence == "low"
                        and not finding.question.strip()
                    )
                )
            ):
                warnings.append(
                    f"Finding[{i}] boxed info finding must declare confidence; "
                    "low confidence requires a reviewer question"
                )
            finding_name = finding.label.strip() or finding.id or f"Finding[{i}]"
            if finding.confidence == "low":
                result.review_required = True
                _append_review_reason(
                    result,
                    f"Low-confidence finding requires review: {finding_name}",
                )
                if not finding.question.strip() and not (
                    finding.severity is Severity.INFO and finding.bboxes
                ):
                    warnings.append(
                        f"Finding[{i}] low-confidence finding requires a "
                        "reviewer question"
                    )
            elif finding.question.strip():
                result.review_required = True
                _append_review_reason(
                    result,
                    f"Finding includes a reviewer question: {finding_name}",
                )
            if (
                request.modality.value == "EKG"
                and finding.severity in {Severity.WARNING, Severity.CRITICAL}
                and not finding.bboxes
            ):
                warnings.append(
                    f"Finding[{i}] actionable EKG finding has no accepted tight bbox"
                )

        # 4. Checklist completeness (modality-specific)
        required = self._registry.resolve(request.modality.value).checklist_keys
        if required:
            actual = set(result.checklist)
            missing = required - actual
            unexpected = actual - required
            if missing:
                warnings.append(
                    f"Checklist missing keys: {', '.join(sorted(missing))}"
                )
            if unexpected:
                warnings.append(
                    f"Checklist has unexpected keys: {', '.join(sorted(unexpected))}"
                )

        # 5. The layout drives systematic crop/refine passes, so an EKG cannot
        # be represented as complete without a valid visible 12-lead inventory.
        if request.modality.value == "EKG":
            assert ekg_inventory is not None
            # Deliberately degraded ECG eval inputs expose only an opaque
            # visible-pixels scope.  Their empty/partial layout is required by
            # the v2 contract, so manufacturing a list of absent named leads
            # here would both leak unverified anatomy into the result and make
            # the recursive text safety gate reject an otherwise honest read.
            partial_pixels_only = set(request.valid_regions) == {
                PARTIAL_ECG_VISIBLE_PIXELS_SCOPE
            }
            if not partial_pixels_only:
                warnings.extend(ekg_inventory.validation_warnings())

        # 6. Checklist value validation
        for key, item in result.checklist.items():
            if not isinstance(item.value, str) or not item.value.strip():
                warnings.append(f"Checklist[{key}] has empty value")

        # 7. Report-level fields are part of the production result contract.
        # Keep non-strict desktop operation fail-soft (the UI visibly marks the
        # result incomplete), while strict smoke/eval gates reject omissions.
        if not _has_meaningful_image_quality(result.image_quality):
            warnings.append("image_quality is missing or empty")
        if not isinstance(result.next_steps, list) or not result.next_steps:
            warnings.append("next_steps is missing or empty")
        elif any(
            not isinstance(step, str) or not step.strip() for step in result.next_steps
        ):
            warnings.append("next_steps contains an empty or invalid item")

        # Log warnings
        for w in warnings:
            logger.warning("OutputValidator: %s", w)

        # Surface degradation to the UI: a result that passed hard checks but
        # tripped warnings (e.g. partial JSON missing checklist keys) is marked
        # incomplete so the overlay can show "結果不完整" instead of a false
        # "all normal".
        if warnings:
            result.incomplete = True
            result.incomplete_reasons = list(
                dict.fromkeys([*result.incomplete_reasons, *warnings])
            )
            result.validation_warnings = list(
                dict.fromkeys([*result.validation_warnings, *warnings])
            )

        if result.incomplete:
            result.review_required = True
            _append_review_reason(result, "Incomplete analysis requires human review")
        elif result.review_required and not result.review_reasons:
            _append_review_reason(result, "Model requested human review")

        # In strict mode, warnings become errors
        if self._strict:
            errors.extend(warnings)

        if errors:
            detail = "; ".join(errors)
            raise HookError(f"AI output validation failed: {detail}")

        logger.debug(
            "OutputValidator passed",
            findings=len(result.findings),
            checklist_keys=len(result.checklist),
        )
        return result


def _append_review_reason(result: AnalysisResult, reason: str) -> None:
    if reason and reason not in result.review_reasons:
        result.review_reasons.append(reason)


def _contains_generic_refusal_or_disclaimer(result: AnalysisResult) -> bool:
    """Reject boilerplate while preserving case-specific image limitations."""

    text_values: list[str] = [result.summary]
    text_values.extend(step for step in result.next_steps if isinstance(step, str))
    text_values.extend(
        reason for reason in result.incomplete_reasons if isinstance(reason, str)
    )
    text_values.extend(
        reason for reason in result.review_reasons if isinstance(reason, str)
    )
    text_values.extend(hint for hint in result.zoom_hints if isinstance(hint, str))
    if isinstance(result.image_quality, str):
        text_values.append(result.image_quality)
    elif isinstance(result.image_quality, dict):
        text_values.extend(
            value for value in result.image_quality.values() if isinstance(value, str)
        )
    for finding in result.findings:
        text_values.extend(
            (finding.label, finding.detail, finding.confidence, finding.question)
        )
        text_values.extend(note for note in finding.notes if isinstance(note, str))
    text_values.extend(
        item.value for item in result.checklist.values() if isinstance(item.value, str)
    )
    return any(
        pattern.search(value)
        for value in text_values
        if isinstance(value, str)
        for pattern in _PROFESSIONAL_REFUSAL_PATTERNS
    )


def _has_normalized_bbox(value: object) -> bool:
    return parse_normalized_region(value) is not None


def _is_positive_normalized_bbox(value: RegionRect) -> bool:
    """Defensively validate boxes from analyzers that bypass JSON parsing."""

    try:
        raw_values = (value.x, value.y, value.w, value.h)
    except AttributeError:
        return False
    if any(isinstance(item, bool) for item in raw_values):
        return False
    try:
        x, y, width, height = (float(item) for item in raw_values)
    except (AttributeError, TypeError, ValueError):
        return False
    return bool(
        all(math.isfinite(item) for item in (x, y, width, height))
        and x >= 0.0
        and y >= 0.0
        and width > 0.0
        and height > 0.0
        and x + width <= 1.0 + 1e-9
        and y + height <= 1.0 + 1e-9
    )


def _has_meaningful_image_quality(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value) and any(
            bool(item.strip()) if isinstance(item, str) else item is not None
            for item in value.values()
        )
    return False
