"""Unit tests for the EKG rhythm-strip refinement pass."""

from __future__ import annotations

from dicom_overlay.application.rhythm_strip import (
    merge_rhythm_strip,
    refine_rhythm_strip,
    resolve_rhythm_strip_region,
)
from dicom_overlay.domain.entities import (
    AnalysisResult,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    Severity,
)


def _result(
    *,
    modality: Modality = Modality.EKG,
    summary: str = "ok",
    severity: Severity = Severity.NORMAL,
    findings: list[Finding] | None = None,
    checklist: dict[str, ChecklistItem] | None = None,
    layout: dict | None = None,
) -> AnalysisResult:
    return AnalysisResult(
        modality=modality,
        summary=summary,
        severity=severity,
        findings=findings or [],
        checklist=checklist or {},
        layout=layout or {},
    )


def test_resolve_rhythm_strip_region_from_layout() -> None:
    region = resolve_rhythm_strip_region(
        _result(layout={"rhythm_strip_bbox": [0.0, 0.8, 1.0, 0.18]})
    )
    assert region is not None
    assert region.y == 0.8
    assert region.h == 0.18


def test_resolve_rhythm_strip_region_none_when_absent_or_malformed() -> None:
    assert resolve_rhythm_strip_region(_result(layout={})) is None
    assert resolve_rhythm_strip_region(_result(layout={"rhythm_strip_bbox": None})) is None
    assert resolve_rhythm_strip_region(_result(layout={"rhythm_strip_bbox": [0, 1]})) is None


def test_resolve_clamps_and_drops_degenerate() -> None:
    # y at the bottom edge leaves no height -> degenerate -> None.
    assert (
        resolve_rhythm_strip_region(_result(layout={"rhythm_strip_bbox": [0.0, 1.0, 1.0, 0.2]}))
        is None
    )
    # Out-of-range values are clamped into the unit square.
    region = resolve_rhythm_strip_region(
        _result(layout={"rhythm_strip_bbox": [-0.1, 0.8, 2.0, 0.1]})
    )
    assert region is not None
    assert region.x == 0.0
    assert region.w == 1.0


def test_merge_escalates_rhythm_axis_and_appends_finding() -> None:
    coarse = _result(
        checklist={"rhythm": ChecklistItem(value="sinus", status=Severity.NORMAL)},
        findings=[
            Finding(id="f1", regions=[], label="Sinus Rhythm", detail="", severity=Severity.NORMAL)
        ],
        severity=Severity.NORMAL,
    )
    strip = _result(
        checklist={"rhythm": ChecklistItem(value="atrial_fibrillation", status=Severity.WARNING)},
        findings=[
            Finding(
                id="s1",
                regions=[],
                label="Atrial Fibrillation",
                detail="irregularly irregular",
                severity=Severity.WARNING,
                bboxes=[RegionRect(0.1, 0.1, 0.2, 0.2)],
            )
        ],
        severity=Severity.WARNING,
    )
    merged = merge_rhythm_strip(coarse, strip, RegionRect(0.0, 0.8, 1.0, 0.2))
    assert merged.checklist["rhythm"].status is Severity.WARNING
    assert merged.severity is Severity.WARNING
    af = next(f for f in merged.findings if f.label == "Atrial Fibrillation")
    # Remapped into the bottom strip region (y >= 0.8).
    assert af.bboxes[0].y >= 0.8


def test_merge_never_downgrades_and_is_noop_when_nothing_added() -> None:
    coarse = _result(
        checklist={"rhythm": ChecklistItem(value="afib", status=Severity.CRITICAL)},
        severity=Severity.CRITICAL,
    )
    strip = _result(
        checklist={"rhythm": ChecklistItem(value="sinus", status=Severity.NORMAL)},
    )
    merged = merge_rhythm_strip(coarse, strip, RegionRect(0.0, 0.8, 1.0, 0.2))
    assert merged is coarse
    assert merged.checklist["rhythm"].status is Severity.CRITICAL


def test_merge_does_not_duplicate_existing_finding_label() -> None:
    coarse = _result(
        findings=[
            Finding(id="f1", regions=[], label="Atrial Fibrillation", detail="", severity=Severity.WARNING)
        ],
        severity=Severity.WARNING,
    )
    strip = _result(
        findings=[
            Finding(
                id="s1",
                regions=[],
                label="atrial fibrillation",
                detail="dup",
                severity=Severity.WARNING,
                bboxes=[RegionRect(0.1, 0.1, 0.2, 0.2)],
            )
        ],
        severity=Severity.WARNING,
    )
    merged = merge_rhythm_strip(coarse, strip, RegionRect(0.0, 0.8, 1.0, 0.2))
    assert sum(1 for f in merged.findings if f.label.lower() == "atrial fibrillation") == 1


async def test_refine_noop_for_non_ekg() -> None:
    calls: list[int] = []

    async def fake_analyze(img: str, modality: Modality, regions: list[str]) -> AnalysisResult:
        calls.append(1)
        return _result()

    result = _result(modality=Modality.CXR, layout={"rhythm_strip_bbox": [0.0, 0.8, 1.0, 0.2]})
    out = await refine_rhythm_strip(
        result,
        "img",
        analyze_fn=fake_analyze,
        cropper=lambda _img, _region: "crop",
        valid_regions=[],
    )
    assert out is result
    assert not calls


async def test_refine_noop_when_no_bbox_declared() -> None:
    calls: list[int] = []

    async def fake_analyze(img: str, modality: Modality, regions: list[str]) -> AnalysisResult:
        calls.append(1)
        return _result()

    result = _result(layout={})
    out = await refine_rhythm_strip(
        result,
        "img",
        analyze_fn=fake_analyze,
        cropper=lambda _img, _region: "crop",
        valid_regions=[],
    )
    assert out is result
    assert not calls


async def test_refine_merges_when_bbox_present() -> None:
    async def fake_analyze(img: str, modality: Modality, regions: list[str]) -> AnalysisResult:
        return _result(
            checklist={"av_block": ChecklistItem(value="first_degree", status=Severity.WARNING)},
            findings=[
                Finding(
                    id="s1",
                    regions=[],
                    label="First Degree AV Block",
                    detail="prolonged PR",
                    severity=Severity.WARNING,
                    bboxes=[RegionRect(0.1, 0.1, 0.1, 0.1)],
                )
            ],
            severity=Severity.WARNING,
        )

    coarse = _result(
        checklist={"av_block": ChecklistItem(value="absent", status=Severity.NORMAL)},
        severity=Severity.NORMAL,
        layout={"rhythm_strip_bbox": [0.0, 0.8, 1.0, 0.2]},
    )
    out = await refine_rhythm_strip(
        coarse,
        "img",
        analyze_fn=fake_analyze,
        cropper=lambda _img, _region: "crop",
        valid_regions=["rhythm_strip"],
    )
    assert out.checklist["av_block"].status is Severity.WARNING
    assert any(f.label == "First Degree AV Block" for f in out.findings)


async def test_refine_returns_coarse_on_analyze_failure() -> None:
    async def boom(img: str, modality: Modality, regions: list[str]) -> AnalysisResult:
        raise RuntimeError("gateway down")

    coarse = _result(layout={"rhythm_strip_bbox": [0.0, 0.8, 1.0, 0.2]})
    out = await refine_rhythm_strip(
        coarse,
        "img",
        analyze_fn=boom,
        cropper=lambda _img, _region: "crop",
        valid_regions=[],
    )
    assert out is coarse
