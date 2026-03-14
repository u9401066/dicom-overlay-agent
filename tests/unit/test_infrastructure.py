"""Unit tests for infrastructure — config loader and region mapper."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from dicom_overlay.domain.entities import Modality, ROICrop, WindowRect
from dicom_overlay.infrastructure.config_loader import load_config, save_roi_config
from dicom_overlay.infrastructure.region_mapper import RegionMapper


class TestConfigLoader:
    def test_load_defaults_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "dicom_overlay.infrastructure.config_loader._DEFAULT_CONFIG_PATHS", []
        )
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.monitor.polling_interval_ms == 500
        assert config.phi_roi.top == 60

    def test_load_from_file(self, tmp_path):
        config_data = {
            "monitor": {"polling_interval_ms": 250, "hash_threshold": 15},
            "phi_roi": {"top": 100, "bottom": 50, "left": 10, "right": 10},
            "openclaw": {"gateway_url": "ws://localhost:9999"},
        }
        config_file = tmp_path / "config.yaml"
        with config_file.open("w") as f:
            yaml.dump(config_data, f)

        config = load_config(config_file)
        assert config.monitor.polling_interval_ms == 250
        assert config.monitor.hash_threshold == 15
        assert config.phi_roi.top == 100
        assert config.openclaw.gateway_url == "ws://localhost:9999"

    def test_save_roi_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        initial = {"monitor": {"polling_interval_ms": 500}}
        with config_file.open("w") as f:
            yaml.dump(initial, f)

        roi = ROICrop(top=80, bottom=40, left=5, right=5)
        save_roi_config(config_file, roi)

        with config_file.open() as f:
            raw = yaml.safe_load(f)
        assert raw["phi_roi"]["top"] == 80
        assert raw["phi_roi"]["bottom"] == 40
        # Original data preserved
        assert raw["monitor"]["polling_interval_ms"] == 500


class TestRegionMapper:
    @pytest.fixture()
    def mapper(self) -> RegionMapper:
        region_maps = {
            "EKG": {
                "layout": "standard_4x3",
                "regions": {
                    "lead_I": {"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.27},
                    "lead_V4": {"x": 0.75, "y": 0.0, "w": 0.25, "h": 0.27},
                    "rhythm_strip": {"x": 0.0, "y": 0.81, "w": 1.0, "h": 0.19},
                },
            },
            "CXR": {
                "layout": "standard_pa",
                "regions": {
                    "right_upper_lung": {"x": 0.05, "y": 0.08, "w": 0.30, "h": 0.22},
                },
            },
        }
        return RegionMapper(region_maps)

    def test_get_valid_regions(self, mapper: RegionMapper):
        regions = mapper.get_valid_regions(Modality.EKG)
        assert "lead_I" in regions
        assert "lead_V4" in regions
        assert "rhythm_strip" in regions
        assert len(regions) == 3

    def test_get_region_rect(self, mapper: RegionMapper):
        rect = mapper.get_region_rect("lead_I", Modality.EKG)
        assert rect is not None
        assert rect.x == 0.0
        assert rect.w == 0.25

    def test_get_region_rect_unknown(self, mapper: RegionMapper):
        rect = mapper.get_region_rect("unknown_region", Modality.EKG)
        assert rect is None

    def test_get_region_rect_wrong_modality(self, mapper: RegionMapper):
        rect = mapper.get_region_rect("lead_I", Modality.CXR)
        assert rect is None

    def test_to_screen_rect(self, mapper: RegionMapper):
        from dicom_overlay.domain.entities import RegionRect

        region = RegionRect(x=0.0, y=0.0, w=0.25, h=0.27)
        window = WindowRect(left=100, top=200, width=1000, height=800)
        sx, sy, sw, sh = mapper.to_screen_rect(region, window)

        assert sx == 100  # left + 0.0 * 1000
        assert sy == 200  # top + 0.0 * 800
        assert sw == 250  # 0.25 * 1000
        assert sh == 216  # 0.27 * 800

    def test_cxr_regions(self, mapper: RegionMapper):
        regions = mapper.get_valid_regions(Modality.CXR)
        assert "right_upper_lung" in regions
