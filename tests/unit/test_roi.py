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
