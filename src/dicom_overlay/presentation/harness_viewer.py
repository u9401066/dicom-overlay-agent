"""Deterministic frameless image viewer for real desktop acceptance runs.

Opens a borderless top-level window titled ``DICOM Harness Viewer`` so the
desktop App's ScreenMonitor discovers it through the same Win32 window search
used for a real DICOM viewer.  The window shows one image at 1:1 logical
scale at a fixed position; an optional swap file lets an external driver
advance to the next case without restarting the window.

Acceptance tooling constraints:

- The window never adds any chrome, padding, or PHI around the image, so the
  App's configured viewer-relative ROI can cover exactly the image content.
- The window is never top-most; the App's overlay panels must win z-order.
- The swap file contains only an absolute image path; anything unreadable or
  unchanged is ignored so a partially written file cannot blank the display.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QLabel

WINDOW_TITLE = "DICOM Harness Viewer"
DEFAULT_X = 100
DEFAULT_Y = 100
DEFAULT_SWAP_POLL_MS = 500


class HarnessViewerWindow(QLabel):
    """Frameless image surface with exact 1:1 logical content geometry."""

    def __init__(
        self,
        image_path: Path,
        *,
        x: int = DEFAULT_X,
        y: int = DEFAULT_Y,
        swap_file: Path | None = None,
        swap_poll_ms: int = DEFAULT_SWAP_POLL_MS,
    ) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.move(x, y)
        self._swap_file = swap_file
        self._current_path = ""
        self.show_image(image_path)
        if swap_file is not None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.poll_swap_file)
            self._timer.start(swap_poll_ms)

    @property
    def current_path(self) -> str:
        return self._current_path

    def show_image(self, image_path: Path) -> None:
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            raise ValueError(f"Viewer cannot load image: {image_path}")
        self.setPixmap(pixmap)
        self.resize(pixmap.width(), pixmap.height())
        self._current_path = str(image_path)

    def poll_swap_file(self) -> None:
        """Advance to the image path in the swap file when it changes."""
        if self._swap_file is None:
            return
        try:
            target = self._swap_file.read_text(encoding="utf-8").strip()
        except OSError:
            return
        if not target or target == self._current_path:
            return
        target_path = Path(target)
        if not target_path.is_file():
            return
        try:
            self.show_image(target_path)
        except ValueError:
            return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Initial image to display")
    parser.add_argument("--x", type=int, default=DEFAULT_X)
    parser.add_argument("--y", type=int, default=DEFAULT_Y)
    parser.add_argument(
        "--swap-file",
        type=Path,
        default=None,
        help="Text file whose content path replaces the displayed image",
    )
    parser.add_argument(
        "--swap-poll-ms",
        type=int,
        default=DEFAULT_SWAP_POLL_MS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = QApplication(sys.argv[:1])
    window = HarnessViewerWindow(
        args.image,
        x=args.x,
        y=args.y,
        swap_file=args.swap_file,
        swap_poll_ms=args.swap_poll_ms,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
