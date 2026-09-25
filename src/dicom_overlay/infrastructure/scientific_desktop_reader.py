"""Concrete public-Gateway scientific workflow for the desktop application port."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dicom_overlay.application.scientific_review_port import (
    NonDiagnosticScientificInput,
)
from dicom_overlay.infrastructure.scientific_image_session import ScientificImageSession

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from dicom_overlay.application.contract_assembly import PreparedReview
    from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
    from medical_image_harness.models import AnalysisResult, Modality


class ScientificDesktopReader:
    """One captured ROI per reader, no legacy parsing, automatic retry or fallback."""

    def __init__(
        self,
        client: OpenClawClient,
        *,
        image_bytes: bytes,
        modality: Modality,
        deidentified: bool,
        receipt_root: Path | None = None,
    ) -> None:
        self.session = ScientificImageSession(
            client,
            image_bytes=image_bytes,
            modality=modality,
            deidentified=deidentified,
            receipt_root=receipt_root,
        )

    @property
    def run_id(self) -> str:
        records = self.session.records
        return records[0].run_id if records else ""

    async def prepare(self) -> PreparedReview:
        if await self.session.read_blind() is None:
            raise NonDiagnosticScientificInput("scientific_input_non_diagnostic")
        await self.session.localize_and_reconcile()
        await self.session.targeted_second_look()
        return await self.session.prepare_review()

    async def handoff(
        self, presenter: Callable[[str, PreparedReview], Awaitable[bytes]]
    ) -> AnalysisResult:
        return await self.session.offer_review(presenter)
