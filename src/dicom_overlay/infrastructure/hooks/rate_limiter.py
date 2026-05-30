"""Rate limiter hook -- prevents excessive API calls."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from dicom_overlay.domain.hooks import AnalyzeHook, AnalyzeRequest, HookError

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import AnalysisResult

logger = structlog.get_logger(__name__)


class RateLimiter(AnalyzeHook):
    """Pre-analyze guardrail: sliding-window rate limiter."""

    def __init__(self, max_per_minute: int = 10) -> None:
        self._max = max_per_minute
        self._timestamps: list[float] = []

    def pre_analyze(self, request: AnalyzeRequest) -> AnalyzeRequest:
        now = time.monotonic()
        cutoff = now - 60.0

        # Prune old entries
        self._timestamps = [t for t in self._timestamps if t > cutoff]

        if len(self._timestamps) >= self._max:
            raise HookError(
                f"Rate limit exceeded: {self._max} requests/min. "
                f"Please wait before retrying."
            )

        self._timestamps.append(now)
        return request

    def post_analyze(
        self, _request: AnalyzeRequest, result: AnalysisResult
    ) -> AnalysisResult:
        return result  # Rate limiter only validates input
