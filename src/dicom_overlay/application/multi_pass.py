"""Multi-pass interpretation orchestrator (application layer).

Lets the agent look at a complex image more than once: a coarse first pass
finds candidate regions, then the orchestrator crops each abnormal region out
of the *original-resolution* ROI image and re-sends just that slice for a
closer, higher-effective-resolution look. Refined bounding boxes are mapped
back into the global ROI coordinate space so the overlay can draw them in the
right place.

Design constraints (see AGENTS.md four cores):
- Core 1: refined ``Finding.bboxes`` stay in normalized 0-1 ROI coordinates.
- Core 3: the orchestrator only calls the stable ``VisionAnalyzerService``
  (``connect`` + ``analyze``); it never touches OpenClaw internals.
- Privacy: every crop is a *subset* of the user-defined ROI, so capture is
  never widened beyond the ROI (a zoom crop can only shrink the region).
- DDD: this module decodes no images itself. Image slicing is delegated to an
  injected :class:`ImageCropper`, keeping PIL/numpy out of the application and
  domain layers.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Protocol

import structlog

from dicom_overlay.domain.entities import (
    AnalysisResult,
    Finding,
    RegionRect,
    Severity,
)

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import Modality
    from dicom_overlay.domain.services import VisionAnalyzerService

logger = structlog.get_logger(__name__)

# Findings worth a closer second look. Normal / info findings are not zoomed.
_ABNORMAL: frozenset[Severity] = frozenset({Severity.WARNING, Severity.CRITICAL})

# Default minimum source-pixel edge for a *digital* zoom to be worthwhile.
# Until the real image API lands, frames come from a screen capture capped at
# the screen resolution (e.g. 4K = 3840x2160). Cropping a region out of that
# capture only recovers detail that pass-1 downscaling threw away -- it cannot
# invent pixels the screenshot never had. If a lesion spans fewer than this
# many *captured* pixels on its short edge, a digital crop just upscales blur,
# so the orchestrator asks the user to zoom in their DICOM viewer and
# re-capture instead (the viewer re-renders from the full DICOM data).
DEFAULT_MIN_ZOOM_SOURCE_EDGE_PX = 256


class ImageCropper(Protocol):
    """Crops a normalized sub-region out of a base64 PNG image.

    Implemented by infrastructure (which owns PIL). ``region`` is expressed in
    normalized 0-1 coordinates relative to the *input* image. Implementations
    may upscale the crop so small lesions become legible; the returned image is
    still a base64 PNG. The crop must never extend outside the input image.
    """

    def __call__(self, image_base64: str, region: RegionRect) -> str: ...


def clamp_unit(value: float) -> float:
    """Clamp a scalar into the closed unit interval [0, 1]."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def pad_region(region: RegionRect, pad: float) -> RegionRect:
    """Grow ``region`` outward by ``pad`` fraction of its own size per side.

    Padding gives the model surrounding context when it re-examines a tight
    bounding box. The result is clamped to stay inside the ROI [0, 1] frame.
    ``pad`` of 0 returns an equivalent region (clamped).
    """
    if pad < 0.0:
        raise ValueError(f"pad must be >= 0, got {pad}")
    dx = region.w * pad
    dy = region.h * pad
    x0 = clamp_unit(region.x - dx)
    y0 = clamp_unit(region.y - dy)
    x1 = clamp_unit(region.x + region.w + dx)
    y1 = clamp_unit(region.y + region.h + dy)
    return RegionRect(x=x0, y=y0, w=clamp_unit(x1 - x0), h=clamp_unit(y1 - y0))


def remap_bbox(child: RegionRect, parent: RegionRect) -> RegionRect:
    """Map a bbox expressed relative to a crop back to global ROI coordinates.

    ``parent`` is the crop region in ROI coordinates; ``child`` is a bbox the
    model returned relative to that crop (its own 0-1 frame). The result is the
    bbox in the original ROI's 0-1 frame, clamped so ``x + w`` and ``y + h``
    never exceed 1.
    """
    gx = clamp_unit(parent.x + child.x * parent.w)
    gy = clamp_unit(parent.y + child.y * parent.h)
    gw = clamp_unit(child.w * parent.w)
    gh = clamp_unit(child.h * parent.h)
    # Keep the box inside the unit square after clamping the origin.
    gw = min(gw, 1.0 - gx)
    gh = min(gh, 1.0 - gy)
    return RegionRect(x=gx, y=gy, w=gw, h=gh)


def select_zoom_targets(
    result: AnalysisResult,
    *,
    max_targets: int,
) -> list[Finding]:
    """Pick abnormal findings that have a bbox and are worth a closer look.

    Critical findings are prioritized over warnings; findings without a bbox
    cannot be cropped and are skipped. At most ``max_targets`` are returned.
    """
    if max_targets <= 0:
        return []
    candidates = [
        f for f in result.findings if f.severity in _ABNORMAL and f.bboxes
    ]
    # Critical first, then warning; preserve original order within a tier.
    candidates.sort(key=lambda f: 0 if f.severity is Severity.CRITICAL else 1)
    return candidates[:max_targets]


def region_source_edge_px(
    region: RegionRect, source_size_px: tuple[int, int]
) -> int:
    """Short edge of ``region`` measured in *captured* source pixels.

    ``source_size_px`` is the actual ``(width, height)`` of the ROI image that
    was captured from the screen (≤ the screen resolution). This is the real
    pixel budget a lesion occupies; it bounds how much a digital crop can ever
    show, since a screenshot has no detail beyond its own pixels.
    """
    src_w, src_h = source_size_px
    w_px = region.w * src_w
    h_px = region.h * src_h
    return int(min(w_px, h_px))


def needs_manual_zoom(
    region: RegionRect,
    source_size_px: tuple[int, int],
    *,
    min_source_edge_px: int = DEFAULT_MIN_ZOOM_SOURCE_EDGE_PX,
) -> bool:
    """True when ``region`` is too small in captured pixels for a digital zoom.

    Below ``min_source_edge_px`` captured pixels on the short edge, cropping the
    screenshot only upscales blur -- the user must zoom in their viewer and
    re-capture to gain real resolution.
    """
    return region_source_edge_px(region, source_size_px) < min_source_edge_px


def build_manual_zoom_message(label: str, source_edge_px: int) -> str:
    """Traditional-Chinese hint asking the user to zoom in their viewer.

    Kept pure so the wording is unit-testable and the overlay just renders it.
    """
    name = label.strip() or "此區域"
    return (
        f"🔍 建議手動放大：「{name}」在目前截圖僅約 {source_edge_px}px，"
        "已達螢幕截圖解析度上限；請於 DICOM 檢視器中放大該區後重新截圖，"
        "以取得更清晰影像。"
    )


class MultiPassInterpreter:
    """Coarse → crop → refine orchestrator over a ``VisionAnalyzerService``.

    Pass 1 analyzes the whole (downscaled) ROI image. For each abnormal finding
    with a bounding box, the original-resolution ROI image is cropped to that
    region (with padding) and re-analyzed. Refined bboxes replace the coarse
    finding's bboxes after being mapped back to ROI coordinates; any extra
    findings discovered inside a crop are appended as linked findings.
    """

    def __init__(
        self,
        analyzer: VisionAnalyzerService,
        cropper: ImageCropper,
        *,
        max_zoom_targets: int = 3,
        zoom_padding: float = 0.15,
        min_zoom_source_edge_px: int = DEFAULT_MIN_ZOOM_SOURCE_EDGE_PX,
    ) -> None:
        if max_zoom_targets < 0:
            raise ValueError("max_zoom_targets must be >= 0")
        if min_zoom_source_edge_px < 0:
            raise ValueError("min_zoom_source_edge_px must be >= 0")
        self._analyzer = analyzer
        self._cropper = cropper
        self._max_zoom_targets = max_zoom_targets
        self._zoom_padding = zoom_padding
        self._min_zoom_source_edge_px = min_zoom_source_edge_px

    async def interpret(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        source_size_px: tuple[int, int] | None = None,
    ) -> AnalysisResult:
        """Run the coarse pass, then optional zoom passes, and merge results.

        ``source_size_px`` is the ``(width, height)`` in pixels of the captured
        ROI image. When provided, a target whose lesion spans too few *captured*
        pixels to gain from a digital crop is not zoomed digitally; instead a
        manual-zoom hint is surfaced on ``result.zoom_hints`` asking the user to
        zoom in their DICOM viewer and re-capture. When ``None`` (resolution
        unknown), every target is digitally zoomed as before.
        """
        coarse = await self._analyzer.analyze(
            image_base64, modality, valid_regions
        )

        targets = select_zoom_targets(coarse, max_targets=self._max_zoom_targets)
        if not targets:
            return coarse

        zoom_hints: list[str] = []
        refined_by_id: dict[str, list[Finding]] = {}
        for target in targets:
            bbox = target.bboxes[0]
            if source_size_px is not None and needs_manual_zoom(
                bbox,
                source_size_px,
                min_source_edge_px=self._min_zoom_source_edge_px,
            ):
                edge_px = region_source_edge_px(bbox, source_size_px)
                logger.info(
                    "Region too small for digital zoom; suggesting manual zoom",
                    finding_id=target.id,
                    source_edge_px=edge_px,
                )
                zoom_hints.append(
                    build_manual_zoom_message(target.label, edge_px)
                )
                continue
            crop_region = pad_region(bbox, self._zoom_padding)
            try:
                crop_b64 = self._cropper(image_base64, crop_region)
                zoom = await self._analyzer.analyze(
                    crop_b64, modality, valid_regions
                )
            except Exception:  # one bad zoom must not sink the whole pass
                logger.warning(
                    "Zoom pass failed; keeping coarse finding",
                    finding_id=target.id,
                )
                continue
            remapped = [
                self._remap_finding(zf, crop_region, parent_id=target.id)
                for zf in zoom.findings
                if zf.bboxes
            ]
            if remapped:
                refined_by_id[target.id] = remapped

        if not refined_by_id and not zoom_hints:
            return coarse
        return self._merge(coarse, refined_by_id, zoom_hints)


    def _remap_finding(
        self, finding: Finding, crop_region: RegionRect, *, parent_id: str
    ) -> Finding:
        remapped_boxes = [remap_bbox(b, crop_region) for b in finding.bboxes]
        new_id = finding.id or f"{parent_id}_zoom"
        return dataclasses.replace(finding, id=new_id, bboxes=remapped_boxes)

    def _merge(
        self,
        coarse: AnalysisResult,
        refined_by_id: dict[str, list[Finding]],
        zoom_hints: list[str],
    ) -> AnalysisResult:
        """Replace zoomed findings' bboxes with refined ones; append extras.

        ``zoom_hints`` (manual-zoom suggestions for regions too small to crop
        digitally) are carried on the merged result for the overlay to render.
        """
        merged: list[Finding] = []
        for finding in coarse.findings:
            refined = refined_by_id.get(finding.id)
            if not refined:
                merged.append(finding)
                continue
            # First refined finding refines the coarse one in place; any extra
            # findings discovered in the crop are appended as linked findings.
            primary = refined[0]
            merged.append(
                dataclasses.replace(
                    finding,
                    detail=primary.detail or finding.detail,
                    bboxes=primary.bboxes,
                )
            )
            for extra in refined[1:]:
                merged.append(
                    dataclasses.replace(extra, id=f"{finding.id}_{extra.id}")
                )
        return dataclasses.replace(
            coarse,
            findings=merged,
            zoom_hints=[*coarse.zoom_hints, *zoom_hints],
        )
