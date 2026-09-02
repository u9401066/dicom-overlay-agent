from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PIL import Image

from dicom_overlay.presentation.harness_viewer import (
    WINDOW_TITLE,
    HarnessViewerWindow,
)

if TYPE_CHECKING:
    from pathlib import Path


def _png(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def test_harness_viewer_shows_image_at_exact_size(qtbot, tmp_path):
    image = _png(tmp_path / "a.png", (1000, 720), (255, 255, 255))

    window = HarnessViewerWindow(image, x=100, y=100)
    qtbot.addWidget(window)

    assert window.windowTitle() == WINDOW_TITLE
    assert window.width() == 1000
    assert window.height() == 720
    assert window.current_path == str(image)


def test_harness_viewer_rejects_unreadable_image(qtbot, tmp_path):
    bogus = tmp_path / "broken.png"
    bogus.write_text("not an image", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot load image"):
        HarnessViewerWindow(bogus)


def test_harness_viewer_swap_file_advances_image(qtbot, tmp_path):
    first = _png(tmp_path / "first.png", (1000, 720), (255, 255, 255))
    second = _png(tmp_path / "second.png", (640, 480), (0, 0, 0))
    swap = tmp_path / "swap.txt"
    swap.write_text(str(first), encoding="utf-8")

    window = HarnessViewerWindow(first, swap_file=swap)
    qtbot.addWidget(window)

    # Unchanged content keeps the current image.
    window.poll_swap_file()
    assert window.current_path == str(first)

    swap.write_text(str(second), encoding="utf-8")
    window.poll_swap_file()
    assert window.current_path == str(second)
    assert window.width() == 640
    assert window.height() == 480

    # Missing or unreadable swap content must not blank the display.
    swap.write_text(str(tmp_path / "does-not-exist.png"), encoding="utf-8")
    window.poll_swap_file()
    assert window.current_path == str(second)
