from __future__ import annotations

import pytest

from dicom_overlay.application.roi import (
    compute_roi_crop_from_safe_rect,
    normalize_selection,
)
from dicom_overlay.domain.entities import ROICrop, WindowRect


def test_normalize_selection_forward() -> None:
    assert normalize_selection(10, 20, 110, 220) == (10, 20, 100, 200)


def test_normalize_selection_reverse() -> None:
    assert normalize_selection(110, 220, 10, 20) == (10, 20, 100, 200)


def test_compute_roi_crop_from_safe_rect() -> None:
    base = WindowRect(left=0, top=0, width=1000, height=800)
    crop = compute_roi_crop_from_safe_rect(base, (50, 60, 900, 700))
    assert crop == ROICrop(top=60, bottom=40, left=50, right=50)


def test_compute_roi_crop_rejects_out_of_bounds() -> None:
    base = WindowRect(left=0, top=0, width=1000, height=800)
    with pytest.raises(ValueError):
        compute_roi_crop_from_safe_rect(base, (50, 60, 980, 700))


def test_compute_roi_crop_rejects_empty() -> None:
    base = WindowRect(left=0, top=0, width=1000, height=800)
    with pytest.raises(ValueError):
        compute_roi_crop_from_safe_rect(base, (50, 60, 0, 700))


# ─── DPI conversion tests ───


class TestDpiConversion:
    def test_physical_to_logical_no_scaling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dicom_overlay.infrastructure import dpi

        monkeypatch.setattr(dpi, "_cached_dpr", 1.0)
        rect = WindowRect(left=100, top=200, width=1920, height=1080)
        result = dpi.physical_to_logical(rect)
        assert result == rect  # identity when dpr=1.0

    def test_physical_to_logical_125_scaling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dicom_overlay.infrastructure import dpi

        monkeypatch.setattr(dpi, "_cached_dpr", 1.25)
        rect = WindowRect(left=0, top=0, width=2560, height=1440)
        result = dpi.physical_to_logical(rect)
        assert result == WindowRect(left=0, top=0, width=2048, height=1152)

    def test_physical_to_logical_150_scaling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dicom_overlay.infrastructure import dpi

        monkeypatch.setattr(dpi, "_cached_dpr", 1.5)
        rect = WindowRect(left=150, top=300, width=1920, height=1080)
        result = dpi.physical_to_logical(rect)
        assert result == WindowRect(left=100, top=200, width=1280, height=720)

    def test_logical_to_physical_roi_roundtrip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dicom_overlay.infrastructure import dpi

        monkeypatch.setattr(dpi, "_cached_dpr", 1.25)
        original = (431, 279, 1279, 0)
        logical = dpi.physical_to_logical_roi(*original)
        back = dpi.logical_to_physical_roi(*logical)
        # Round-trip should be close (rounding may differ by ±1)
        for orig, rt in zip(original, back, strict=True):
            assert abs(orig - rt) <= 1

    def test_no_scaling_returns_same_roi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dicom_overlay.infrastructure import dpi

        monkeypatch.setattr(dpi, "_cached_dpr", 1.0)
        roi = (60, 30, 0, 0)
        assert dpi.physical_to_logical_roi(*roi) == roi
        assert dpi.logical_to_physical_roi(*roi) == roi
