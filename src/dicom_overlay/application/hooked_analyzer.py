"""Hooked Vision Analyzer -- decorator that wraps VisionAnalyzerService with hooks.

This is the application-layer component that chains AnalyzeHooks around
the actual analyze call, providing MCP-like enforcement without requiring
MCP protocol support from the underlying backend (OpenClaw).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from dicom_overlay.domain.hooks import AnalyzeHook, AnalyzeRequest, HookError
from dicom_overlay.domain.services import VisionAnalyzerService

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import AnalysisResult, Modality

logger = structlog.get_logger(__name__)


class HookedVisionAnalyzer(VisionAnalyzerService):
    """Decorator: wraps a VisionAnalyzerService with pre/post hooks.

    Pipeline:
      pre_analyze(hook1) -> pre_analyze(hook2) -> ... -> actual analyze
      -> ... -> post_analyze(hook2) -> post_analyze(hook1) -> result

    Post-hooks run in reverse order (LIFO) so the outermost hook sees
    the final result last -- consistent with middleware patterns.
    """

    def __init__(
        self,
        inner: VisionAnalyzerService,
        hooks: list[AnalyzeHook] | None = None,
    ) -> None:
        self._inner = inner
        self._hooks: list[AnalyzeHook] = hooks or []

    def add_hook(self, hook: AnalyzeHook) -> None:
        self._hooks.append(hook)
        logger.info("Hook registered: %s", hook.name)

    async def analyze(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        request = AnalyzeRequest(
            image_base64=image_base64,
            modality=modality,
            valid_regions=valid_regions,
        )

        # Pre-hooks (forward order)
        for hook in self._hooks:
            try:
                request = hook.pre_analyze(request)
            except HookError:
                logger.warning(
                    "Pre-hook rejected request",
                    hook=hook.name,
                    modality=modality.value,
                )
                raise

        # Execute actual analyze
        result = await self._inner.analyze(
            request.image_base64,
            request.modality,
            request.valid_regions,
        )

        # Post-hooks (reverse order)
        for hook in reversed(self._hooks):
            try:
                result = hook.post_analyze(request, result)
            except HookError:
                logger.warning(
                    "Post-hook rejected result",
                    hook=hook.name,
                    modality=modality.value,
                )
                raise

        return result

    # -- Delegate all other methods to inner --

    async def chat(self, message: str) -> str:
        return await self._inner.chat(message)

    async def connect(self) -> None:
        return await self._inner.connect()

    async def disconnect(self) -> None:
        return await self._inner.disconnect()

    def is_connected(self) -> bool:
        return self._inner.is_connected()
