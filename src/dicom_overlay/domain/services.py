"""Domain service interfaces (ABCs) for DICOM Overlay Agent.

These define the contracts that infrastructure implementations must fulfill.
Domain layer MUST NOT depend on any external libraries.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from medical_image_harness.protocols import VisionAnalyzerService

__all__ = [
    "ImageProcessorService",
    "RegionMapperService",
    "ScreenMonitorService",
    "VisionAnalyzerService",
]

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import (
        DisplayFrame,
        Modality,
        RegionRect,
        WindowRect,
    )


class ScreenMonitorService(ABC):
    """Detects DICOM viewer window and monitors for image changes (spec §3.1)."""

    @abstractmethod
    def find_target_window(self, keywords: list[str]) -> WindowRect | None:
        """Find the DICOM viewer window by title keywords."""

    def display_for_window(self, window: WindowRect) -> DisplayFrame | None:
        """Return the physical display containing ``window`` when available.

        This has a concrete fallback so test and third-party monitor adapters
        written before per-display coordinate support remain compatible.
        """
        del window
        return None

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

    @abstractmethod
    def image_size(self, image_data: bytes) -> tuple[int, int]:
        """Return ``(width, height)`` for PNG image bytes."""


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
