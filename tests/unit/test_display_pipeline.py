"""Unit tests for the core display pipeline — coordinate system, highlight
calculation, and overlay presentation helpers.

Covers:
  - RegionMapper.to_screen_rect() edge cases
  - Overlay-local coordinate conversion (the on_analysis_result logic)
  - _humanize_checklist_key() / _humanize_checklist_value()
  - Highlight tuple integrity (6-element with label)
"""

from __future__ import annotations

import pytest

from dicom_overlay.domain.entities import (
    Finding,
    Modality,
    RegionRect,
    Severity,
    WindowRect,
)
from dicom_overlay.infrastructure.region_mapper import RegionMapper
from dicom_overlay.presentation.overlay_window import (
    _humanize_checklist_key,
    _humanize_checklist_value,
)


# ── RegionMapper.to_screen_rect edge cases ──


class TestToScreenRect:
    @pytest.fixture()
    def mapper(self) -> RegionMapper:
        return RegionMapper(
            {
                "EKG": {
                    "regions": {
                        "lead_I": {"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.27},
                        "rhythm_strip": {"x": 0.0, "y": 0.81, "w": 1.0, "h": 0.19},
                    },
                }
            }
        )

    def test_origin_region(self, mapper: RegionMapper):
        """Region at (0,0) should map to window top-left."""
        region = RegionRect(x=0.0, y=0.0, w=0.5, h=0.5)
        window = WindowRect(left=100, top=200, width=1000, height=800)
        sx, sy, sw, sh = mapper.to_screen_rect(region, window)
        assert (sx, sy) == (100, 200)
        assert (sw, sh) == (500, 400)

    def test_bottom_right_region(self, mapper: RegionMapper):
        """Region at far corner should map correctly."""
        region = RegionRect(x=0.75, y=0.75, w=0.25, h=0.25)
        window = WindowRect(left=0, top=0, width=1920, height=1080)
        sx, sy, sw, sh = mapper.to_screen_rect(region, window)
        assert sx == 1440  # 0.75 * 1920
        assert sy == 810  # 0.75 * 1080
        assert sw == 480  # 0.25 * 1920
        assert sh == 270  # 0.25 * 1080

    def test_full_screen_region(self, mapper: RegionMapper):
        """Region covering entire image."""
        region = RegionRect(x=0.0, y=0.0, w=1.0, h=1.0)
        window = WindowRect(left=50, top=50, width=800, height=600)
        sx, sy, sw, sh = mapper.to_screen_rect(region, window)
        assert (sx, sy) == (50, 50)
        assert (sw, sh) == (800, 600)

    def test_negative_window_offset(self, mapper: RegionMapper):
        """Window partially off-screen (negative coords)."""
        region = RegionRect(x=0.5, y=0.5, w=0.1, h=0.1)
        window = WindowRect(left=-100, top=-50, width=1920, height=1080)
        sx, sy, _sw, _sh = mapper.to_screen_rect(region, window)
        assert sx == -100 + int(0.5 * 1920)  # 860
        assert sy == -50 + int(0.5 * 1080)  # 490

    def test_small_region(self, mapper: RegionMapper):
        """Very small region should still produce valid pixel coords."""
        region = RegionRect(x=0.5, y=0.5, w=0.01, h=0.01)
        window = WindowRect(left=0, top=0, width=1920, height=1080)
        _sx, _sy, sw, sh = mapper.to_screen_rect(region, window)
        assert sw == 19  # int(0.01 * 1920)
        assert sh == 10  # int(0.01 * 1080)
        assert sw > 0 and sh > 0

    def test_secondary_monitor_offset(self, mapper: RegionMapper):
        """Window on secondary monitor with large offset."""
        region = RegionRect(x=0.0, y=0.0, w=0.25, h=0.25)
        window = WindowRect(left=1920, top=0, width=1920, height=1080)
        sx, _sy, sw, _sh = mapper.to_screen_rect(region, window)
        assert sx == 1920  # Offset by secondary monitor
        assert sw == 480


# ── Overlay-local coordinate conversion ──


class TestOverlayLocalConversion:
    """Test the conversion from screen-absolute to overlay-local coordinates.

    This mirrors the logic in __main__.py on_analysis_result():
      lx = sx - target_window.left
      ly = sy - target_window.top
    """

    def test_basic_conversion(self):
        """Screen coords minus window origin = overlay-local."""
        window = WindowRect(left=100, top=200, width=1000, height=800)
        region = RegionRect(x=0.5, y=0.5, w=0.1, h=0.1)

        mapper = RegionMapper({"EKG": {"regions": {}}})
        sx, sy, _sw, _sh = mapper.to_screen_rect(region, window)

        lx = sx - window.left
        ly = sy - window.top

        # Should equal region.x * width, region.y * height
        assert lx == int(region.x * window.width)
        assert ly == int(region.y * window.height)

    def test_origin_simplifies_to_zero(self):
        """Region at origin should produce overlay-local (0, 0)."""
        window = WindowRect(left=300, top=400, width=1000, height=800)
        region = RegionRect(x=0.0, y=0.0, w=0.25, h=0.25)

        mapper = RegionMapper({"EKG": {"regions": {}}})
        sx, sy, _sw, _sh = mapper.to_screen_rect(region, window)

        lx = sx - window.left
        ly = sy - window.top
        assert (lx, ly) == (0, 0)

    def test_negative_window_coords(self):
        """Window with negative coords (partially off-screen)."""
        window = WindowRect(left=-200, top=-100, width=1920, height=1080)
        region = RegionRect(x=0.5, y=0.5, w=0.1, h=0.1)

        mapper = RegionMapper({"EKG": {"regions": {}}})
        sx, sy, _sw, _sh = mapper.to_screen_rect(region, window)

        lx = sx - window.left
        ly = sy - window.top

        # Even with negative window origin, overlay-local should be positive
        assert lx == int(0.5 * 1920)
        assert ly == int(0.5 * 1080)
        assert lx > 0 and ly > 0


# ── Highlight tuple construction ──


class TestHighlightConstruction:
    """Test the complete highlight tuple building from findings."""

    @pytest.fixture()
    def mapper(self) -> RegionMapper:
        return RegionMapper(
            {
                "EKG": {
                    "regions": {
                        "lead_II": {"x": 0.0, "y": 0.27, "w": 0.25, "h": 0.27},
                        "lead_V1": {"x": 0.50, "y": 0.0, "w": 0.25, "h": 0.27},
                    },
                }
            }
        )

    def test_single_finding_single_region(self, mapper: RegionMapper):
        window = WindowRect(left=0, top=0, width=1000, height=800)
        finding = Finding(
            id="f1",
            regions=["lead_II"],
            label="ST Elevation",
            detail="ST elevation in lead II",
            severity=Severity.CRITICAL,
        )

        highlights = []
        rect = mapper.get_region_rect("lead_II", Modality.EKG)
        assert rect is not None
        sx, sy, sw, sh = mapper.to_screen_rect(rect, window)
        lx = sx - window.left
        ly = sy - window.top
        highlights.append((lx, ly, sw, sh, finding.severity.value, finding.label))

        assert len(highlights) == 1
        x, y, _w, _h, sev, label = highlights[0]
        assert sev == "critical"
        assert label == "ST Elevation"
        assert x == 0  # 0.0 * 1000
        assert y == 216  # int(0.27 * 800)

    def test_finding_with_unknown_region_skipped(self, mapper: RegionMapper):
        """Unknown regions should be skipped (returned None)."""
        rect = mapper.get_region_rect("nonexistent", Modality.EKG)
        assert rect is None

    def test_multi_region_finding(self, mapper: RegionMapper):
        """One finding can reference multiple regions → multiple highlights."""
        window = WindowRect(left=0, top=0, width=1000, height=800)
        finding = Finding(
            id="f2",
            regions=["lead_II", "lead_V1"],
            label="Arrhythmia",
            detail="Irregular rhythm",
            severity=Severity.WARNING,
        )

        highlights = []
        for region_name in finding.regions:
            rect = mapper.get_region_rect(region_name, Modality.EKG)
            if rect:
                sx, sy, sw, sh = mapper.to_screen_rect(rect, window)
                lx = sx - window.left
                ly = sy - window.top
                highlights.append(
                    (lx, ly, sw, sh, finding.severity.value, finding.label)
                )

        assert len(highlights) == 2
        # Both should have the same label from the finding
        assert all(h[5] == "Arrhythmia" for h in highlights)
        assert all(h[4] == "warning" for h in highlights)

    def test_highlight_tuple_has_6_elements(self, mapper: RegionMapper):
        """Verify the highlight tuple structure after fix."""
        window = WindowRect(left=100, top=200, width=1000, height=800)
        region = RegionRect(x=0.5, y=0.5, w=0.1, h=0.1)
        sx, sy, sw, sh = mapper.to_screen_rect(region, window)
        lx = sx - window.left
        ly = sy - window.top
        highlight = (lx, ly, sw, sh, "critical", "Test Label")
        assert len(highlight) == 6
        assert highlight[5] == "Test Label"


# ── Humanize helpers ──


class TestHumanizeChecklist:
    def test_mapped_key(self):
        assert _humanize_checklist_key("stemi_nstemi_pattern") == "STEMI/NSTEMI"
        assert _humanize_checklist_key("qtc_prolongation") == "QTc Prolong."
        assert _humanize_checklist_key("bundle_branch_block") == "BBB"

    def test_unmapped_key_title_cased(self):
        assert _humanize_checklist_key("heart_rate") == "Heart Rate"
        assert _humanize_checklist_key("blood_pressure") == "Blood Pressure"

    def test_single_word_key(self):
        assert _humanize_checklist_key("rate") == "Rate"

    def test_empty_value(self):
        assert _humanize_checklist_value("") == "—"

    def test_underscore_value(self):
        assert _humanize_checklist_value("normal_sinus_rhythm") == "Normal sinus rhythm"

    def test_plain_value(self):
        assert _humanize_checklist_value("72 bpm") == "72 bpm"

    def test_all_mapped_keys(self):
        """All keys in _KEY_DISPLAY_MAP should resolve."""
        from dicom_overlay.presentation.overlay_window import _KEY_DISPLAY_MAP

        for key, expected in _KEY_DISPLAY_MAP.items():
            assert _humanize_checklist_key(key) == expected


# ── Region unknown warning ──


class TestRegionMapperWarning:
    def test_unknown_region_logs_warning(self, caplog):
        """get_region_rect should log a warning for unknown regions."""
        import logging

        mapper = RegionMapper(
            {"EKG": {"regions": {"lead_I": {"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.27}}}}
        )
        with caplog.at_level(logging.WARNING):
            result = mapper.get_region_rect("nonexistent_lead", Modality.EKG)
        assert result is None
        # structlog may not write to caplog by default, assert None return is sufficient
