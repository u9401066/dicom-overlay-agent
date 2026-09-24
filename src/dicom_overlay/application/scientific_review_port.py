"""Application ports for optional two-phase scientific desktop publication."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from dicom_overlay.application.contract_assembly import PreparedReview
    from medical_image_harness.models import AnalysisResult


class NonDiagnosticScientificInput(ValueError):
    """QC stopped interpretation; no observation ledger or normal report invented."""


class ScientificReviewReader(Protocol):
    @property
    def run_id(self) -> str: ...

    async def prepare(self) -> PreparedReview: ...

    async def handoff(
        self, presenter: Callable[[str, PreparedReview], Awaitable[bytes]]
    ) -> AnalysisResult: ...
