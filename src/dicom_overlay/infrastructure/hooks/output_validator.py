"""Output validation hook -- enforces AnalysisResult schema after AI response."""

from __future__ import annotations

import dataclasses

import structlog

from dicom_overlay.domain.entities import AnalysisResult, Severity
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

        # 2. Modality must match request
        if result.modality != request.modality:
            warnings.append(
                f"Modality mismatch: requested {request.modality.value}, "
                f"got {result.modality.value} -- auto-corrected"
            )
            result.modality = request.modality

        # 3. Validate findings
        for i, finding in enumerate(result.findings):
            if not finding.id:
                errors.append(f"Finding[{i}] missing id")
            if not finding.label:
                errors.append(f"Finding[{i}] missing label")
            # Check regions are from valid set
            for region in finding.regions:
                if region not in request.valid_regions:
                    warnings.append(
                        f"Finding[{i}] region '{region}' "
                        f"not in valid regions"
                    )
            if finding.severity is Severity.NORMAL and finding.bboxes:
                finding = dataclasses.replace(finding, bboxes=[])
                result.findings[i] = finding
                warnings.append(
                    f"Finding[{i}] normal/negative observation had overlay boxes; "
                    "boxes removed"
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
            missing = required - set(result.checklist.keys())
            if missing:
                warnings.append(
                    f"Checklist missing keys: {', '.join(sorted(missing))}"
                )

        # 5. Checklist value validation
        for key, item in result.checklist.items():
            if not item.value or not item.value.strip():
                warnings.append(f"Checklist[{key}] has empty value")

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
