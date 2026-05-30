"""Domain service interfaces (ABCs) for DICOM Overlay Agent.

These define the contracts that infrastructure implementations must fulfill.
Domain layer MUST NOT depend on any external libraries.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import (
        AnalysisResult,
        Modality,
        RegionRect,
        WindowRect,
    )


class ScreenMonitorService(ABC):
    """Detects DICOM viewer window and monitors for image changes (spec §3.1)."""

    @abstractmethod
    def find_target_window(self, keywords: list[str]) -> WindowRect | None:
        """Find the DICOM viewer window by title keywords."""

    @abstractmethod
    def capture_region(self, rect: WindowRect) -> bytes:
        """Capture a screen region as PNG bytes."""

    @abstractmethod
    def compute_hash(self, image_data: bytes) -> str:
        """Compute perceptual hash of image data."""

    @abstractmethod
    def has_changed(self, hash1: str, hash2: str, threshold: int) -> bool:
        """Compare two hashes, return True if difference exceeds threshold."""


class ImageProcessorService(ABC):
    """Handles ROI cropping for PHI removal (spec §3.2)."""

    @abstractmethod
    def crop_roi(
        self, image_data: bytes, top: int, bottom: int, left: int, right: int
    ) -> bytes:
        """Crop image to remove PHI regions, returns PNG bytes."""

    @abstractmethod
    def to_base64(self, image_data: bytes) -> str:
        """Encode image bytes to base64 string."""

    @abstractmethod
    def downscale_to_max_edge(self, image_data: bytes, max_edge: int) -> bytes:
        """Shrink image so its longest edge <= max_edge (PNG bytes).

        Only shrinks; never upscales. ``max_edge <= 0`` returns input unchanged.
        """


class VisionAnalyzerService(ABC):
    """Sends images to Vision API for analysis (spec §3.3)."""

    @abstractmethod
    async def analyze(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        """Analyze an image and return structured findings."""

    @abstractmethod
    async def chat(self, message: str) -> str:
        """Send a free-text question and return the AI's text response."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the analysis backend."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the analysis backend."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the connection is active."""


class RegionMapperService(ABC):
    """Maps semantic region names to screen coordinates (spec §3.3)."""

    @abstractmethod
    def get_region_rect(
        self, region_name: str, modality: Modality
    ) -> RegionRect | None:
        """Look up a region name and return its percentage rect."""

    @abstractmethod
    def get_valid_regions(self, modality: Modality) -> list[str]:
        """Get all valid region names for a modality."""

    @abstractmethod
    def to_screen_rect(
        self,
        region: RegionRect,
        image_rect: WindowRect,
    ) -> tuple[int, int, int, int]:
        """Convert percentage rect to absolute screen pixels (x, y, w, h)."""
