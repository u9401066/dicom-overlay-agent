"""Unit tests for the multi-pass interpretation orchestrator.

Covers the pure coordinate maths (clamp / pad / remap), zoom-target selection,
and the coarse -> crop -> refine orchestration including the privacy invariant
that a zoom crop only ever shrinks the captured region.
"""

from __future__ import annotations

import pytest

from dicom_overlay.application.multi_pass import (
    MultiPassAnalyzer,
    MultiPassInterpreter,
    build_manual_zoom_message,
    clamp_unit,
    needs_manual_zoom,
    pad_region,
    region_source_edge_px,
    remap_bbox,
    select_zoom_targets,
)
from dicom_overlay.domain.entities import (
    AnalysisResult,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.domain.services import VisionAnalyzerService


def _result(findings: list[Finding]) -> AnalysisResult:
    return AnalysisResult(
        modality=Modality.CXR,
        summary="test",
        severity=Severity.WARNING if findings else Severity.NORMAL,
        findings=findings,
        checklist={"x": ChecklistItem(value="ok", status=Severity.NORMAL)},
    )


def _finding(
    fid: str,
    severity: Severity,
    bbox: RegionRect | None,
    *,
    label: str = "lesion",
    detail: str = "",
) -> Finding:
    return Finding(
        id=fid,
        regions=[],
        label=label,
        detail=detail,
        severity=severity,
        bboxes=[bbox] if bbox else [],
    )


# ── clamp_unit ───────────────────────────────────────────────────────


class TestClampUnit:
    def test_passthrough(self):
        assert clamp_unit(0.5) == 0.5

    def test_below_zero(self):
        assert clamp_unit(-0.3) == 0.0

    def test_above_one(self):
        assert clamp_unit(1.4) == 1.0


# ── pad_region ───────────────────────────────────────────────────────


class TestPadRegion:
    def test_grows_by_fraction_of_size(self):
        region = RegionRect(x=0.4, y=0.4, w=0.2, h=0.2)
        padded = pad_region(region, 0.5)  # +/- 0.1 per side
        assert padded.x == pytest.approx(0.3)
        assert padded.y == pytest.approx(0.3)
        assert padded.w == pytest.approx(0.4)
        assert padded.h == pytest.approx(0.4)

    def test_clamped_to_roi_frame(self):
        region = RegionRect(x=0.0, y=0.0, w=0.2, h=0.2)
        padded = pad_region(region, 1.0)
        assert padded.x == 0.0  # cannot go negative
        assert padded.y == 0.0
        assert padded.x + padded.w <= 1.0 + 1e-9

    def test_negative_pad_rejected(self):
        with pytest.raises(ValueError):
            pad_region(RegionRect(x=0.1, y=0.1, w=0.1, h=0.1), -0.1)


# ── remap_bbox ───────────────────────────────────────────────────────


class TestRemapBbox:
    def test_full_crop_bbox_is_identity(self):
        parent = RegionRect(x=0.0, y=0.0, w=1.0, h=1.0)
        child = RegionRect(x=0.25, y=0.5, w=0.1, h=0.2)
        out = remap_bbox(child, parent)
        assert out.x == pytest.approx(0.25)
        assert out.y == pytest.approx(0.5)
        assert out.w == pytest.approx(0.1)
        assert out.h == pytest.approx(0.2)

    def test_center_of_crop_maps_into_crop(self):
        # Crop occupies the bottom-right quarter of the ROI.
        parent = RegionRect(x=0.5, y=0.5, w=0.5, h=0.5)
        # A bbox centered in the crop.
        child = RegionRect(x=0.4, y=0.4, w=0.2, h=0.2)
        out = remap_bbox(child, parent)
        # Global center should be 0.5 + 0.5*0.5 = 0.75
        assert (out.x + out.w / 2) == pytest.approx(0.75)
        assert (out.y + out.h / 2) == pytest.approx(0.75)
        # Width scales by the crop width.
        assert out.w == pytest.approx(0.1)

    def test_result_stays_in_unit_square(self):
        parent = RegionRect(x=0.8, y=0.8, w=0.2, h=0.2)
        child = RegionRect(x=0.9, y=0.9, w=0.3, h=0.3)
        out = remap_bbox(child, parent)
        assert 0.0 <= out.x <= 1.0
        assert 0.0 <= out.y <= 1.0
        assert out.x + out.w <= 1.0 + 1e-9
        assert out.y + out.h <= 1.0 + 1e-9

    def test_child_bbox_overflow_is_clamped_to_parent_crop(self):
        parent = RegionRect(x=0.2, y=0.2, w=0.3, h=0.3)
        child = RegionRect(x=0.8, y=0.8, w=0.5, h=0.5)
        out = remap_bbox(child, parent)
        assert out.x == pytest.approx(0.44)
        assert out.y == pytest.approx(0.44)
        assert out.w == pytest.approx(0.06)
        assert out.h == pytest.approx(0.06)
        assert out.x + out.w <= parent.x + parent.w + 1e-9
        assert out.y + out.h <= parent.y + parent.h + 1e-9


# ── select_zoom_targets ──────────────────────────────────────────────


class TestSelectZoomTargets:
    def test_skips_normal_but_includes_info_after_abnormal(self):
        box = RegionRect(x=0.1, y=0.1, w=0.1, h=0.1)
        res = _result(
            [
                _finding("a", Severity.NORMAL, box),
                _finding("i", Severity.INFO, box),
                _finding("w", Severity.WARNING, box),
            ]
        )
        assert [t.id for t in select_zoom_targets(res, max_targets=3)] == ["w", "i"]

    def test_skips_findings_without_bbox(self):
        res = _result([_finding("a", Severity.CRITICAL, None)])
        assert select_zoom_targets(res, max_targets=3) == []

    def test_critical_prioritized_over_warning(self):
        box = RegionRect(x=0.1, y=0.1, w=0.1, h=0.1)
        res = _result(
            [
                _finding("w", Severity.WARNING, box),
                _finding("c", Severity.CRITICAL, box),
            ]
        )
        targets = select_zoom_targets(res, max_targets=1)
        assert [t.id for t in targets] == ["c"]

    def test_respects_max_targets(self):
        box = RegionRect(x=0.1, y=0.1, w=0.1, h=0.1)
        res = _result(
            [_finding(str(i), Severity.WARNING, box) for i in range(5)]
        )
        assert len(select_zoom_targets(res, max_targets=2)) == 2

    def test_zero_max_targets(self):
        box = RegionRect(x=0.1, y=0.1, w=0.1, h=0.1)
        res = _result([_finding("a", Severity.CRITICAL, box)])
        assert select_zoom_targets(res, max_targets=0) == []


# ── MultiPassInterpreter orchestration ───────────────────────────────


class _FakeAnalyzer(VisionAnalyzerService):
    """Returns a scripted result per call; records the images it received."""

    def __init__(self, results: list[AnalysisResult]) -> None:
        self._results = list(results)
        self.images: list[str] = []

    async def analyze(self, image_base64, modality, valid_regions):
        self.images.append(image_base64)
        return self._results.pop(0)

    async def chat(self, message):  # pragma: no cover - unused here
        return ""

    async def connect(self):  # pragma: no cover
        return None

    async def disconnect(self):  # pragma: no cover
        return None

    def is_connected(self):  # pragma: no cover
        return True


class _RecordingCropper:
    """Fake cropper: records crop regions, returns a marker string."""

    def __init__(self) -> None:
        self.regions: list[RegionRect] = []

    def __call__(self, image_base64: str, region: RegionRect) -> str:
        self.regions.append(region)
        return f"crop::{region.x:.3f},{region.y:.3f}"


@pytest.mark.asyncio
class TestMultiPassInterpreter:
    async def test_no_abnormal_findings_skips_zoom(self):
        coarse = _result([])
        analyzer = _FakeAnalyzer([coarse])
        cropper = _RecordingCropper()
        interp = MultiPassInterpreter(analyzer, cropper)

        out = await interp.interpret("img", Modality.CXR, [])

        assert out is coarse
        assert cropper.regions == []
        assert len(analyzer.images) == 1  # only the coarse pass

    async def test_refines_abnormal_finding_bbox(self):
        coarse_box = RegionRect(x=0.5, y=0.5, w=0.2, h=0.2)
        coarse = _result(
            [_finding("f1", Severity.CRITICAL, coarse_box, detail="coarse")]
        )
        # Zoom returns a tighter bbox relative to the crop, plus new detail.
        zoom_box = RegionRect(x=0.4, y=0.4, w=0.1, h=0.1)
        zoom = _result(
            [_finding("z", Severity.CRITICAL, zoom_box, detail="sharper")]
        )
        analyzer = _FakeAnalyzer([coarse, zoom])
        cropper = _RecordingCropper()
        interp = MultiPassInterpreter(
            analyzer, cropper, zoom_padding=0.0
        )

        out = await interp.interpret("img", Modality.CXR, [])

        # Two analyze calls: coarse + one zoom.
        assert len(analyzer.images) == 2
        # The zoom received the cropped image, not the original.
        assert analyzer.images[1].startswith("crop::")
        # Coarse finding kept its id but got refined detail + remapped bbox.
        refined = out.findings[0]
        assert refined.id == "f1"
        assert refined.detail == "sharper"
        # Remapped global center: crop = padded coarse box (pad 0) = coarse box.
        # child center 0.45 within crop [0.5..0.7] -> 0.5 + 0.45*0.2 = 0.59
        b = refined.bboxes[0]
        assert (b.x + b.w / 2) == pytest.approx(0.59)

    async def test_crop_region_is_subset_of_roi(self):
        # Privacy invariant: a zoom crop must never widen beyond the ROI.
        box = RegionRect(x=0.3, y=0.3, w=0.2, h=0.2)
        coarse = _result([_finding("f1", Severity.WARNING, box)])
        zoom = _result([_finding("z", Severity.WARNING, box)])
        analyzer = _FakeAnalyzer([coarse, zoom])
        cropper = _RecordingCropper()
        interp = MultiPassInterpreter(analyzer, cropper, zoom_padding=0.2)

        await interp.interpret("img", Modality.CXR, [])

        region = cropper.regions[0]
        assert region.x >= 0.0
        assert region.y >= 0.0
        assert region.x + region.w <= 1.0 + 1e-9
        assert region.y + region.h <= 1.0 + 1e-9

    async def test_failed_zoom_keeps_coarse_finding(self):
        box = RegionRect(x=0.3, y=0.3, w=0.2, h=0.2)
        coarse = _result(
            [_finding("f1", Severity.WARNING, box, detail="coarse")]
        )
        analyzer = _FakeAnalyzer([coarse])  # no zoom result -> pop raises

        def _boom(image_base64, region):
            raise RuntimeError("crop failed")

        interp = MultiPassInterpreter(analyzer, _boom)
        out = await interp.interpret("img", Modality.CXR, [])

        # Coarse finding survives unchanged.
        assert out.findings[0].detail == "coarse"
        assert out.findings[0].bboxes[0] == box

    async def test_local_candidate_refines_abnormal_finding_without_bbox(self):
        coarse = _result(
            [
                _finding(
                    "f1",
                    Severity.WARNING,
                    None,
                    label="possible opacity",
                    detail="coarse finding without coordinates",
                )
            ]
        )
        candidate = RegionRect(x=0.2, y=0.2, w=0.4, h=0.4)
        zoom = _result(
            [
                _finding(
                    "z",
                    Severity.WARNING,
                    RegionRect(x=0.25, y=0.25, w=0.5, h=0.5),
                    detail="candidate crop confirms opacity",
                )
            ]
        )
        analyzer = _FakeAnalyzer([coarse, zoom])
        cropper = _RecordingCropper()
        interp = MultiPassInterpreter(
            analyzer, cropper, zoom_padding=0.0
        )

        out = await interp.interpret(
            "img",
            Modality.CXR,
            [],
            local_candidate_regions=[candidate],
        )

        assert len(analyzer.images) == 2
        assert cropper.regions == [candidate]
        refined = out.findings[0]
        assert refined.id == "f1"
        assert refined.detail == "candidate crop confirms opacity"
        assert refined.bboxes
        bbox = refined.bboxes[0]
        assert bbox.x == pytest.approx(0.3)
        assert bbox.y == pytest.approx(0.3)
        assert bbox.w == pytest.approx(0.2)
        assert bbox.h == pytest.approx(0.2)

    async def test_local_candidate_does_not_zoom_normal_coarse_result(self):
        coarse = _result([])
        analyzer = _FakeAnalyzer([coarse])
        cropper = _RecordingCropper()
        interp = MultiPassInterpreter(analyzer, cropper)

        out = await interp.interpret(
            "img",
            Modality.CXR,
            [],
            local_candidate_regions=[RegionRect(x=0.2, y=0.2, w=0.4, h=0.4)],
        )

        assert out is coarse
        assert len(analyzer.images) == 1
        assert cropper.regions == []

    async def test_extra_zoom_findings_appended(self):
        box = RegionRect(x=0.4, y=0.4, w=0.2, h=0.2)
        coarse = _result([_finding("f1", Severity.CRITICAL, box)])
        zbox = RegionRect(x=0.1, y=0.1, w=0.1, h=0.1)
        zoom = _result(
            [
                _finding("z1", Severity.CRITICAL, zbox, detail="primary"),
                _finding("z2", Severity.WARNING, zbox, detail="extra"),
            ]
        )
        analyzer = _FakeAnalyzer([coarse, zoom])
        interp = MultiPassInterpreter(
            analyzer, _RecordingCropper(), zoom_padding=0.0
        )

        out = await interp.interpret("img", Modality.CXR, [])

        ids = [f.id for f in out.findings]
        assert ids[0] == "f1"  # refined in place
        assert "f1_z2" in ids  # extra finding appended, linked to parent

    async def test_negative_max_zoom_rejected(self):
        with pytest.raises(ValueError):
            MultiPassInterpreter(
                _FakeAnalyzer([]), _RecordingCropper(), max_zoom_targets=-1
            )


# ── resolution-aware zoom (screenshot 4K cap) ────────────────────────


class TestRegionSourceEdgePx:
    def test_short_edge_in_source_pixels(self):
        # 4K capture; region 10% wide x 5% tall -> short edge = 0.05*2160 = 108
        region = RegionRect(x=0.1, y=0.1, w=0.1, h=0.05)
        assert region_source_edge_px(region, (3840, 2160)) == 108

    def test_uses_min_of_width_and_height(self):
        region = RegionRect(x=0.0, y=0.0, w=0.5, h=0.02)
        # width 1920px, height 43px -> short edge 43
        assert region_source_edge_px(region, (3840, 2160)) == 43


class TestNeedsManualZoom:
    def test_small_region_needs_manual_zoom(self):
        # 4% of a 4K short edge = 0.04*2160 = 86px < 256 -> manual zoom
        region = RegionRect(x=0.1, y=0.1, w=0.04, h=0.04)
        assert needs_manual_zoom(region, (3840, 2160)) is True

    def test_large_region_digitally_zoomable(self):
        # 20% of 4K = 432px >= 256 -> digital crop still recovers detail
        region = RegionRect(x=0.1, y=0.1, w=0.2, h=0.2)
        assert needs_manual_zoom(region, (3840, 2160)) is False

    def test_threshold_is_configurable(self):
        region = RegionRect(x=0.1, y=0.1, w=0.2, h=0.2)  # 432px
        assert needs_manual_zoom(
            region, (3840, 2160), min_source_edge_px=500
        ) is True


class TestBuildManualZoomMessage:
    def test_includes_label_and_pixels(self):
        msg = build_manual_zoom_message("Lung nodule", 80)
        assert "Lung nodule" in msg
        assert "80px" in msg

    def test_blank_label_falls_back(self):
        msg = build_manual_zoom_message("   ", 50)
        assert "此區域" in msg


@pytest.mark.asyncio
class TestMultiPassResolutionAware:
    async def test_small_region_emits_manual_hint_not_crop(self):
        # A tiny critical lesion in a 4K capture: 3% short edge = 64px < 256.
        box = RegionRect(x=0.4, y=0.4, w=0.03, h=0.03)
        coarse = _result(
            [_finding("f1", Severity.CRITICAL, box, label="Micro-nodule")]
        )
        analyzer = _FakeAnalyzer([coarse])  # no zoom pass should occur
        cropper = _RecordingCropper()
        interp = MultiPassInterpreter(analyzer, cropper)

        out = await interp.interpret(
            "img", Modality.CXR, [], source_size_px=(3840, 2160)
        )

        # No digital crop / second analyze; instead a manual-zoom hint.
        assert cropper.regions == []
        assert len(analyzer.images) == 1
        assert len(out.zoom_hints) == 1
        assert "Micro-nodule" in out.zoom_hints[0]
        # Coarse finding preserved unchanged.
        assert out.findings[0].bboxes[0] == box

    async def test_large_region_still_digitally_zoomed(self):
        box = RegionRect(x=0.3, y=0.3, w=0.3, h=0.3)  # 648px short edge
        coarse = _result([_finding("f1", Severity.CRITICAL, box)])
        zoom = _result(
            [_finding("z", Severity.CRITICAL, RegionRect(0.4, 0.4, 0.1, 0.1))]
        )
        analyzer = _FakeAnalyzer([coarse, zoom])
        cropper = _RecordingCropper()
        interp = MultiPassInterpreter(analyzer, cropper, zoom_padding=0.0)

        out = await interp.interpret(
            "img", Modality.CXR, [], source_size_px=(3840, 2160)
        )

        assert len(analyzer.images) == 2  # digital zoom happened
        assert cropper.regions  # crop was taken
        assert out.zoom_hints == []  # no manual hint needed

    async def test_unknown_source_size_zooms_as_before(self):
        # Without source_size_px the orchestrator can't reason about pixels, so
        # it digitally zooms every target (backward compatible).
        box = RegionRect(x=0.4, y=0.4, w=0.03, h=0.03)
        coarse = _result([_finding("f1", Severity.CRITICAL, box)])
        zoom = _result(
            [_finding("z", Severity.CRITICAL, RegionRect(0.4, 0.4, 0.1, 0.1))]
        )
        analyzer = _FakeAnalyzer([coarse, zoom])
        interp = MultiPassInterpreter(
            analyzer, _RecordingCropper(), zoom_padding=0.0
        )

        out = await interp.interpret("img", Modality.CXR, [])

        assert len(analyzer.images) == 2  # digital zoom still happens
        assert out.zoom_hints == []

    async def test_mixed_targets_split_between_crop_and_hint(self):
        big = RegionRect(x=0.1, y=0.1, w=0.3, h=0.3)  # digital
        small = RegionRect(x=0.6, y=0.6, w=0.03, h=0.03)  # manual
        coarse = _result(
            [
                _finding("big", Severity.CRITICAL, big, label="Mass"),
                _finding("small", Severity.CRITICAL, small, label="Spot"),
            ]
        )
        zoom = _result(
            [_finding("z", Severity.CRITICAL, RegionRect(0.4, 0.4, 0.1, 0.1))]
        )
        analyzer = _FakeAnalyzer([coarse, zoom])
        cropper = _RecordingCropper()
        interp = MultiPassInterpreter(analyzer, cropper, zoom_padding=0.0)

        out = await interp.interpret(
            "img", Modality.CXR, [], source_size_px=(3840, 2160)
        )

        # Exactly one digital crop (the big mass) and one manual hint (the spot).
        assert len(cropper.regions) == 1
        assert len(out.zoom_hints) == 1
        assert "Spot" in out.zoom_hints[0]


# ── MultiPassAnalyzer drop-in adapter ──────────────────────────


@pytest.mark.asyncio
class TestMultiPassAnalyzer:
    """The adapter must be a drop-in VisionAnalyzerService for OverlayAgent."""

    async def test_analyze_routes_through_interpreter(self):
        coarse_box = RegionRect(x=0.5, y=0.5, w=0.2, h=0.2)
        coarse = _result(
            [_finding("a", Severity.WARNING, coarse_box)]
        )
        refined = _result(
            [_finding("a", Severity.WARNING, RegionRect(0.0, 0.0, 1.0, 1.0))]
        )
        inner = _FakeAnalyzer([coarse, refined])
        cropper = _RecordingCropper()
        interp = MultiPassInterpreter(inner, cropper)
        adapter = MultiPassAnalyzer(inner=inner, interpreter=interp)

        out = await adapter.analyze("img", Modality.CXR, [])

        # Multi-pass ran: a coarse + a refine call happened (2 analyzer images).
        assert len(inner.images) == 2
        assert cropper.regions  # a digital crop was taken
        assert out.findings

    async def test_analyze_with_source_size_routes_resolution_context(self):
        tiny_box = RegionRect(x=0.4, y=0.4, w=0.03, h=0.03)
        coarse = _result(
            [_finding("tiny", Severity.WARNING, tiny_box, label="Tiny target")]
        )
        inner = _FakeAnalyzer([coarse])
        cropper = _RecordingCropper()
        interp = MultiPassInterpreter(inner, cropper)
        adapter = MultiPassAnalyzer(inner=inner, interpreter=interp)

        out = await adapter.analyze_with_source_size(
            "img",
            Modality.CXR,
            [],
            source_size_px=(100, 100),
        )

        assert len(inner.images) == 1
        assert cropper.regions == []
        assert out.zoom_hints

    async def test_non_analyze_methods_delegate_to_inner(self):
        inner = _FakeAnalyzer([_result([])])
        interp = MultiPassInterpreter(inner, _RecordingCropper())
        adapter = MultiPassAnalyzer(inner=inner, interpreter=interp)

        assert adapter.is_connected() is True
        assert await adapter.chat("hi") == ""
        await adapter.connect()
        await adapter.disconnect()

    async def test_is_a_vision_analyzer_service(self):
        from dicom_overlay.domain.services import VisionAnalyzerService

        inner = _FakeAnalyzer([_result([])])
        interp = MultiPassInterpreter(inner, _RecordingCropper())
        adapter = MultiPassAnalyzer(inner=inner, interpreter=interp)
        assert isinstance(adapter, VisionAnalyzerService)
