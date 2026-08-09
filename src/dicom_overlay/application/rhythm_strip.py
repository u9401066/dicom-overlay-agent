"""EKG rhythm-strip refinement pass (application layer).

The coarse whole-image read often under-reports rhythm / P-wave / AV-conduction
findings because the rhythm strip is small in the down-scaled full image. This
pass crops the model-declared rhythm strip out of the original-resolution image
and re-reads just that strip, then merges the higher-confidence rhythm findings
back into the coarse result.

Design constraints (see AGENTS.md four cores):

- **General, not layout-assuming.** The strip region comes only from the
  model's Step-0 ``layout.rhythm_strip_bbox`` for THIS image. If the model did
  not declare one (single strip, partial, non-standard, unknown), this pass is
  a no-op -- it never guesses a fixed position.
- **Core 1.** Refined bboxes stay in normalized 0-1 ROI coordinates (remapped
  from the crop's own frame).
- **Escalate-only.** Rhythm checklist axes may be upgraded to a more severe
  reading but never downgraded, mirroring the clinical-safety rule.
- **DDD.** Image slicing and inference are injected; no PIL/numpy or network
  code lives here.
"""

from __future__ import annotations

import asyncio
import dataclasses
import math
import time
from typing import TYPE_CHECKING

import structlog

from dicom_overlay.application.multi_pass import (
    DEFAULT_MIN_FOLLOWUP_BUDGET_SEC,
    DEFAULT_TOTAL_ANALYSIS_SLA_SEC,
    pad_region,
    remap_bbox,
)
from dicom_overlay.domain.ekg_layout import parse_ekg_lead_inventory
from dicom_overlay.domain.entities import (
    AnalysisResult,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.domain.services import VisionAnalyzerService

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = structlog.get_logger(__name__)

# Checklist axes the rhythm strip is authoritative for.
RHYTHM_AXES: frozenset[str] = frozenset(
    {"heart_rate", "rhythm", "regularity", "p_wave", "pr_interval", "av_block"}
)

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.NORMAL: 0,
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.CRITICAL: 2,
}
_ABNORMAL: frozenset[Severity] = frozenset({Severity.WARNING, Severity.CRITICAL})
_MAX_RHYTHM_STRIP_HEIGHT = 0.35


def resolve_rhythm_strip_region(result: AnalysisResult) -> RegionRect | None:
    """Return the model-declared rhythm-strip region, or ``None``.

    General by design: the region comes only from the Step-0
    ``layout.rhythm_strip_bbox`` the model reported for THIS image, so a
    single-strip / partial / non-standard / unknown capture is never cropped on
    a guessed position. Accepts normalized array or object geometry, clamps it
    into the unit square, and rejects degenerate or near-full-frame regions.
    """
    layout = result.layout if isinstance(result.layout, dict) else {}
    raw = layout.get("rhythm_strip_bbox")
    if isinstance(raw, dict):
        values = tuple(raw.get(key) for key in ("x", "y", "w", "h"))
    elif isinstance(raw, (list, tuple)) and len(raw) >= 4:
        values = tuple(raw[:4])
    else:
        return None
    try:
        x, y, w, h = (float(value) for value in values)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (x, y, w, h)):
        return None
    x = min(max(x, 0.0), 1.0)
    y = min(max(y, 0.0), 1.0)
    w = min(max(w, 0.0), 1.0 - x)
    h = min(max(h, 0.0), 1.0 - y)
    if w <= 0.0 or h <= 0.0 or h > _MAX_RHYTHM_STRIP_HEIGHT:
        return None
    return RegionRect(x=x, y=y, w=w, h=h)


def _geometry_leads(
    result: AnalysisResult,
    boxes: list[RegionRect],
) -> list[str]:
    layout_leads = parse_ekg_lead_inventory(result.layout).leads
    names: list[str] = []
    for box in boxes:
        center_x = box.x + box.w / 2.0
        center_y = box.y + box.h / 2.0
        candidates = [
            lead
            for lead in layout_leads
            if lead.bbox.x <= center_x <= lead.bbox.x + lead.bbox.w
            and lead.bbox.y <= center_y <= lead.bbox.y + lead.bbox.h
        ]
        if not candidates:
            continue
        name = min(candidates, key=lambda lead: lead.bbox.w * lead.bbox.h).name
        if name not in names:
            names.append(name)
    return names


def _more_severe(a: Severity, b: Severity) -> Severity:
    return a if _SEVERITY_RANK[a] >= _SEVERITY_RANK[b] else b


def merge_rhythm_strip(
    coarse: AnalysisResult,
    strip: AnalysisResult,
    strip_region: RegionRect,
) -> AnalysisResult:
    """Merge rhythm findings/axes from a strip re-read into the coarse result.

    Conservative and escalate-only:

    - A rhythm checklist axis adopts the strip's reading only when the strip is
      *strictly more severe* (never downgraded).
    - Strip findings that are abnormal and not already present (by lowercased
      label) are appended, with bboxes remapped into global ROI coordinates.
    - Overall severity is escalated when an adopted axis/finding is more severe.

    Returns ``coarse`` unchanged when the strip adds nothing.
    """
    merged_checklist = dict(coarse.checklist)
    escalated: list[str] = []
    for axis in RHYTHM_AXES:
        strip_item = strip.checklist.get(axis)
        if strip_item is None:
            continue
        coarse_item = merged_checklist.get(axis)
        if coarse_item is None or (
            _SEVERITY_RANK[strip_item.status] > _SEVERITY_RANK[coarse_item.status]
        ):
            merged_checklist[axis] = strip_item
            if strip_item.status in _ABNORMAL:
                escalated.append(axis)

    existing_labels = {f.label.strip().lower() for f in coarse.findings}
    appended: list[Finding] = []
    for finding in strip.findings:
        if finding.severity not in _ABNORMAL:
            continue
        if finding.label.strip().lower() in existing_labels:
            continue
        remapped = [remap_bbox(b, strip_region) for b in finding.bboxes]
        declared_strip = resolve_rhythm_strip_region(coarse)
        regions = list(finding.regions)
        if declared_strip is not None and "rhythm_strip" not in regions:
            regions.append("rhythm_strip")
        for name in _geometry_leads(coarse, remapped):
            if name not in regions:
                regions.append(name)
        appended.append(
            dataclasses.replace(
                finding,
                id=f"rhythm_{finding.id}" if finding.id else f"rhythm_{len(appended) + 1}",
                regions=regions,
                bboxes=remapped,
            )
        )

    if not escalated and not appended:
        return coarse

    new_severity = coarse.severity
    for finding in appended:
        new_severity = _more_severe(new_severity, finding.severity)
    for axis in escalated:
        new_severity = _more_severe(new_severity, merged_checklist[axis].status)

    return dataclasses.replace(
        coarse,
        severity=new_severity,
        checklist=merged_checklist,
        findings=[*coarse.findings, *appended],
    )


async def refine_rhythm_strip(
    result: AnalysisResult,
    image_base64: str,
    *,
    analyze_fn: Callable[[str, Modality, list[str]], Awaitable[AnalysisResult]],
    cropper: Callable[[str, RegionRect], str],
    valid_regions: list[str],
    padding: float = 0.05,
    retry_attempts: int = 1,
    max_turn_sec: float = 35.0,
) -> AnalysisResult:
    """Crop the declared rhythm strip, re-read it, and merge rhythm findings.

    A no-op (returns ``result`` unchanged) when the modality is not EKG, when
    the model declared no rhythm-strip bbox, or when the strip re-read fails.
    That keeps non-standard / partial / single-strip captures safe: the pass
    only fires when a dedicated strip was explicitly localized by Step 0.
    """
    if retry_attempts < 0:
        raise ValueError("retry_attempts must be >= 0")
    if result.modality != Modality.EKG:
        return result
    region = resolve_rhythm_strip_region(result)
    if region is None:
        return result
    sla_event = next(
        (
            event
            for event in reversed(result.analysis_trace)
            if event.get("stage") == "analysis_sla"
        ),
        None,
    )
    sla_total_budget_sec = DEFAULT_TOTAL_ANALYSIS_SLA_SEC
    elapsed_before_ms = result.analysis_time_ms
    if sla_event is not None:
        budgets = sla_event.get("budgets_sec")
        timings = sla_event.get("timings_ms")
        if isinstance(budgets, dict):
            sla_total_budget_sec = float(
                budgets.get("total", DEFAULT_TOTAL_ANALYSIS_SLA_SEC)
            )
        if isinstance(timings, dict):
            elapsed_before_ms = int(timings.get("total") or elapsed_before_ms)
    remaining_total_sec = sla_total_budget_sec - (elapsed_before_ms / 1000) - 1.0
    if sla_event is not None and remaining_total_sec < DEFAULT_MIN_FOLLOWUP_BUDGET_SEC:
        return _finish_rhythm_with_sla(
            result,
            elapsed_before_ms=elapsed_before_ms,
            added_elapsed_ms=0,
            total_budget_sec=sla_total_budget_sec,
            status="deadline_reserve_exhausted",
        )
    crop_region = pad_region(region, padding)
    try:
        crop_b64 = cropper(image_base64, crop_region)
    except Exception:
        logger.warning("rhythm_strip_crop_failed")
        return result
    strip: AnalysisResult | None = None
    started_at = time.monotonic()
    turn_budget_sec = min(max_turn_sec, max(0.0, remaining_total_sec))
    for attempt in range(retry_attempts + 1):
        try:
            remaining_turn_sec = turn_budget_sec - (time.monotonic() - started_at)
            if remaining_turn_sec <= 0.0:
                raise TimeoutError("rhythm-strip SLA exhausted")
            strip = await asyncio.wait_for(
                analyze_fn(crop_b64, Modality.EKG, valid_regions),
                timeout=remaining_turn_sec,
            )
            if strip.summary.strip() or strip.findings:
                break
        except Exception:
            strip = None
        if attempt < retry_attempts:
            logger.warning(
                "rhythm_strip_analysis_retry",
                attempt=attempt + 1,
                max_retries=retry_attempts,
            )
    if strip is None or (not strip.summary.strip() and not strip.findings):
        logger.warning("rhythm_strip_analysis_failed")
        if sla_event is None:
            return result
        return _finish_rhythm_with_sla(
            result,
            elapsed_before_ms=elapsed_before_ms,
            added_elapsed_ms=int((time.monotonic() - started_at) * 1000),
            total_budget_sec=sla_total_budget_sec,
            status="deadline_exceeded",
        )
    merged = merge_rhythm_strip(result, strip, crop_region)
    event: dict[str, object] = {
        "stage": "rhythm_strip_refine",
        "status": "completed" if merged is not result else "completed_no_change",
        "tool": "crop_region_base64+openclaw_vision_analysis",
        "crop_source": "source_image",
        "crop_region": {
            "x": crop_region.x,
            "y": crop_region.y,
            "w": crop_region.w,
            "h": crop_region.h,
        },
        "finding_count_before": len(result.findings),
        "finding_count_after": len(merged.findings),
    }
    output = dataclasses.replace(
        merged,
        analysis_trace=[*merged.analysis_trace, event],
    )
    if sla_event is None:
        return output
    return _finish_rhythm_with_sla(
        output,
        elapsed_before_ms=elapsed_before_ms,
        added_elapsed_ms=int((time.monotonic() - started_at) * 1000),
        total_budget_sec=sla_total_budget_sec,
        status="completed",
    )


def _finish_rhythm_with_sla(
    result: AnalysisResult,
    *,
    elapsed_before_ms: int,
    added_elapsed_ms: int,
    total_budget_sec: float,
    status: str,
) -> AnalysisResult:
    """Refresh the shared SLA receipt after an optional rhythm-strip turn."""
    total_ms = elapsed_before_ms + max(0, added_elapsed_ms)
    total_met = total_ms <= int(total_budget_sec * 1000)
    trace: list[dict[str, object]] = []
    for event in result.analysis_trace:
        if event.get("stage") != "analysis_sla":
            trace.append(event)
            continue
        updated = dict(event)
        timings = dict(updated.get("timings_ms", {}))
        timings["total"] = total_ms
        met = dict(updated.get("met", {}))
        met["total"] = total_met
        updated["timings_ms"] = timings
        updated["met"] = met
        if status != "completed" or not total_met:
            updated["status"] = "degraded"
        trace.append(updated)
    trace.append(
        {
            "stage": "rhythm_strip_sla",
            "status": status,
            "added_elapsed_ms": max(0, added_elapsed_ms),
            "total_completed_ms": total_ms,
            "total_sla_met": total_met,
        }
    )
    if status == "completed" and total_met:
        return dataclasses.replace(
            result,
            analysis_time_ms=total_ms,
            analysis_trace=trace,
        )
    reason = (
        "Rhythm-strip refinement was stopped at the total analysis time budget; "
        "review rhythm and conduction manually."
    )
    return dataclasses.replace(
        result,
        analysis_time_ms=total_ms,
        analysis_trace=trace,
        incomplete=True,
        incomplete_reasons=list(
            dict.fromkeys([*result.incomplete_reasons, reason])
        ),
        review_required=True,
        review_reasons=list(dict.fromkeys([*result.review_reasons, reason])),
    )


class RhythmStripRefiningAnalyzer(VisionAnalyzerService):
    """Apply the shared rhythm-strip pass to a complete analyzer transaction.

    The desktop and evaluator can use the same application-layer implementation:
    the inner analyzer produces the full-image draft, then a separately injected
    analyzer re-reads only a model-localized strip from the original ROI.
    """

    def __init__(
        self,
        *,
        inner: VisionAnalyzerService,
        refinement_analyzer: VisionAnalyzerService,
        cropper: Callable[[str, RegionRect], str],
    ) -> None:
        self._inner = inner
        self._refinement_analyzer = refinement_analyzer
        self._cropper = cropper

    async def analyze(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> AnalysisResult:
        result = await self._inner.analyze(image_base64, modality, valid_regions)
        return await self._refine(
            result,
            image_base64,
            valid_regions=valid_regions,
        )

    async def analyze_with_source_size(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        source_size_px: tuple[int, int] | None,
        source_image_base64: str | None = None,
        local_candidate_regions: list[RegionRect] | None = None,
    ) -> AnalysisResult:
        analyze_with_source_size = getattr(
            self._inner,
            "analyze_with_source_size",
            None,
        )
        if callable(analyze_with_source_size):
            result = await analyze_with_source_size(
                image_base64,
                modality,
                valid_regions,
                source_size_px=source_size_px,
                source_image_base64=source_image_base64,
                local_candidate_regions=local_candidate_regions,
            )
        else:
            result = await self._inner.analyze(
                image_base64,
                modality,
                valid_regions,
            )
        return await self._refine(
            result,
            source_image_base64 or image_base64,
            valid_regions=valid_regions,
        )

    async def _refine(
        self,
        result: AnalysisResult,
        source_image_base64: str,
        *,
        valid_regions: list[str],
    ) -> AnalysisResult:
        return await refine_rhythm_strip(
            result,
            source_image_base64,
            analyze_fn=self._refinement_analyzer.analyze,
            cropper=self._cropper,
            valid_regions=valid_regions,
        )

    async def chat(self, message: str) -> str:
        return await self._inner.chat(message)

    async def connect(self) -> None:
        await self._inner.connect()

    async def disconnect(self) -> None:
        await self._inner.disconnect()

    def is_connected(self) -> bool:
        return self._inner.is_connected()
