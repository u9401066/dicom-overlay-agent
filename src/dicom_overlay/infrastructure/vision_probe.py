"""Vision capability smoke tests for configured LLM backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dicom_overlay.domain.entities import Modality

if TYPE_CHECKING:
    from dicom_overlay.domain.services import VisionAnalyzerService


_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/"
    "x8AAwMCAO+aF9sAAAAASUVORK5CYII="
)


@dataclass(frozen=True)
class VisionProbeResult:
    ok: bool
    supports_image: bool
    message: str
    model_used: str = ""


class VisionSmokeTester:
    """Runs a real image-shaped request through a VisionAnalyzerService."""

    def __init__(self, analyzer: VisionAnalyzerService) -> None:
        self._analyzer = analyzer

    async def probe(self) -> VisionProbeResult:
        try:
            if not self._analyzer.is_connected():
                await self._analyzer.connect()
            result = await self._analyzer.analyze(
                _TINY_PNG_B64,
                Modality.EKG,
                ["lead_I"],
            )
        except Exception as exc:
            return VisionProbeResult(
                ok=False,
                supports_image=False,
                message=str(exc),
            )

        if result is None:
            return VisionProbeResult(
                ok=False,
                supports_image=False,
                message="Vision probe returned no result",
            )

        return VisionProbeResult(
            ok=True,
            supports_image=True,
            message="Vision image smoke test passed",
            model_used=result.model_used,
        )
