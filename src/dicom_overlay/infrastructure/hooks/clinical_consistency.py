"""Clinical consistency hook — runs the guideline-grounded safety net.

A post-analyze guardrail that applies the data-driven
:class:`~dicom_overlay.domain.clinical_rules.ClinicalConsistencyEngine` to the
AI's structured output. It only ever *escalates* severity and *flags for human
review* (never downgrades, never rewrites findings, never raises), so it is a
fail-safe advisory layer on top of OpenClaw's own read. Order it **after**
``OutputValidator`` so it operates on a schema-validated result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from dicom_overlay.domain.clinical_rules import (
    ClinicalConsistencyEngine,
    default_engine,
)
from dicom_overlay.domain.hooks import AnalyzeHook, AnalyzeRequest

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import AnalysisResult

logger = structlog.get_logger(__name__)


class ClinicalConsistencyHook(AnalyzeHook):
    """Escalates/flags results that contradict their own structured read."""

    def __init__(self, engine: ClinicalConsistencyEngine | None = None) -> None:
        self._engine = engine or default_engine()

    def pre_analyze(self, request: AnalyzeRequest) -> AnalyzeRequest:
        return request  # advisory only operates on output

    def post_analyze(
        self,
        request: AnalyzeRequest,  # noqa: ARG002 - advisory hook acts only on result
        result: AnalysisResult,
    ) -> AnalysisResult:
        violations = self._engine.apply(result)
        for violation in violations:
            logger.warning(
                "clinical_consistency_flag",
                rule_id=violation.rule.id,
                modality=result.modality.value,
                escalated_to=result.severity.value,
                guideline=violation.rule.guideline,
                evidence=list(violation.evidence),
                audit=violation.audit_line(),
            )
        return result
