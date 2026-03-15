"""Screen monitor — window detection + screenshot + hash comparison."""

from __future__ import annotations

import io

import imagehash
import mss
import structlog
from PIL import Image

from dicom_overlay.domain.entities import WindowRect
from dicom_overlay.domain.services import ImageProcessorService, ScreenMonitorService

logger = structlog.get_logger(__name__)

# pywin32 imports — Windows only
win32gui = None
try:
    import win32gui as _win32gui

    win32gui = _win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    logger.warning("pywin32 not available — window detection disabled")


_HASH_FUNCS = {
    "ahash": imagehash.average_hash,
    "phash": imagehash.phash,
    "dhash": imagehash.dhash,
    "whash": imagehash.whash,
}


class ScreenMonitor(ScreenMonitorService):
    """Detects DICOM viewer window and captures screen regions (spec §3.1)."""

    def __init__(self, hash_algorithm: str = "phash") -> None:
        algo = hash_algorithm.lower()
        if algo not in _HASH_FUNCS:
            logger.warning("Unknown hash algorithm %r, falling back to phash", algo)
            algo = "phash"
        self._hash_func = _HASH_FUNCS[algo]
        logger.info("Hash algorithm: %s", algo)

    def find_target_window(self, keywords: list[str]) -> WindowRect | None:
        if not HAS_WIN32 or win32gui is None:
            return None

        gui = win32gui

        result: WindowRect | None = None

        def _enum_callback(hwnd: int, _: object) -> None:
            nonlocal result
            if result is not None:
                return
            if not gui.IsWindowVisible(hwnd):
                return
            title = gui.GetWindowText(hwnd)
            if not title:
                return
            for kw in keywords:
                if kw.lower() in title.lower():
                    rect = gui.GetWindowRect(hwnd)
                    left, top, right, bottom = rect
                    w = right - left
                    h = bottom - top
                    if w > 100 and h > 100:
                        result = WindowRect(
                            left=left, top=top, width=w, height=h
                        )
                    return

        try:
            gui.EnumWindows(_enum_callback, None)
        except Exception:
            logger.exception("Error enumerating windows")

        return result

    def capture_region(self, rect: WindowRect) -> bytes:
        monitor = {
            "left": rect.left,
            "top": rect.top,
            "width": rect.width,
            "height": rect.height,
        }
        with mss.mss() as sct:
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

    def compute_hash(self, image_data: bytes) -> str:
        img = Image.open(io.BytesIO(image_data))
        h = self._hash_func(img)
        return str(h)

    def has_changed(self, hash1: str, hash2: str, threshold: int) -> bool:
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        diff = h1 - h2
        return bool(diff > threshold)


class ImageProcessor(ImageProcessorService):
    """Handles ROI cropping and encoding (spec §3.2)."""

    def crop_roi(
        self, image_data: bytes, top: int, bottom: int, left: int, right: int
    ) -> bytes:
        img = Image.open(io.BytesIO(image_data))
        w, h = img.size
        crop_box = (
            left,
            top,
            w - right,
            h - bottom,
        )
        # Validate crop doesn't exceed image
        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            logger.warning("Invalid crop dimensions, returning original")
            return image_data
        cropped = img.crop(crop_box)
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue()

    def to_base64(self, image_data: bytes) -> str:
        import base64

        return base64.b64encode(image_data).decode("ascii")
