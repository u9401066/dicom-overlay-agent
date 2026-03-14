"""Region mapper — maps semantic region names to screen coordinates."""

from __future__ import annotations

from typing import Any

import structlog

from dicom_overlay.domain.entities import Modality, RegionRect, WindowRect
from dicom_overlay.domain.services import RegionMapperService

logger = structlog.get_logger(__name__)


class RegionMapper(RegionMapperService):
    """Maps region names to percentage-based rectangles (spec §3.3).

    Region definitions come from config.yaml region_maps section.
    """

    def __init__(self, region_maps: dict[str, Any]) -> None:
        self._maps: dict[str, dict[str, RegionRect]] = {}
        self._load_maps(region_maps)

    def _load_maps(self, raw: dict[str, Any]) -> None:
        for modality_key, modality_data in raw.items():
            regions_raw = modality_data.get("regions", {})
            parsed: dict[str, RegionRect] = {}
            for name, rect_data in regions_raw.items():
                try:
                    parsed[name] = RegionRect(
                        x=float(rect_data["x"]),
                        y=float(rect_data["y"]),
                        w=float(rect_data["w"]),
                        h=float(rect_data["h"]),
                    )
                except (KeyError, ValueError) as e:
                    logger.warning("Invalid region %s.%s: %s", modality_key, name, e)
            self._maps[modality_key] = parsed
            logger.debug(
                "Loaded %d regions for %s", len(parsed), modality_key
            )

    def get_region_rect(
        self, region_name: str, modality: Modality
    ) -> RegionRect | None:
        mod_key = modality.value
        mod_map = self._maps.get(mod_key, {})
        rect = mod_map.get(region_name)
        if rect is None:
            logger.warning(
                "Unknown region '%s' for modality %s", region_name, mod_key
            )
        return rect

    def get_valid_regions(self, modality: Modality) -> list[str]:
        mod_key = modality.value
        return list(self._maps.get(mod_key, {}).keys())

    def to_screen_rect(
        self,
        region: RegionRect,
        image_rect: WindowRect,
    ) -> tuple[int, int, int, int]:
        x = int(image_rect.left + region.x * image_rect.width)
        y = int(image_rect.top + region.y * image_rect.height)
        w = int(region.w * image_rect.width)
        h = int(region.h * image_rect.height)
        return (x, y, w, h)
