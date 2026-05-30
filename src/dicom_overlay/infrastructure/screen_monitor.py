"""Screen monitor — window detection + screenshot + hash comparison."""

from __future__ import annotations

import io
from collections.abc import Callable

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


_HashFunc = Callable[[Image.Image], str]


def _bits_to_hex(bits: list[bool]) -> str:
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    width = max(1, (len(bits) + 3) // 4)
    return f"{value:0{width}x}"


def _average_hash(img: Image.Image) -> str:
    gray = img.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    pixels = list(gray.tobytes())
    average = sum(pixels) / len(pixels)
    return _bits_to_hex([pixel > average for pixel in pixels])


def _difference_hash(img: Image.Image) -> str:
    gray = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(gray.tobytes())
    bits: list[bool] = []
    for row in range(8):
        start = row * 9
        for col in range(8):
            bits.append(pixels[start + col] > pixels[start + col + 1])
    return _bits_to_hex(bits)


def _hex_hamming_distance(hash1: str, hash2: str) -> int:
    value1 = int(hash1, 16)
    value2 = int(hash2, 16)
    return (value1 ^ value2).bit_count()


_HASH_FUNCS: dict[str, _HashFunc] = {
    "ahash": _average_hash,
    "dhash": _difference_hash,
}


class ScreenMonitor(ScreenMonitorService):
    """Detects DICOM viewer window and captures screen regions (spec §3.1)."""

    def __init__(self, hash_algorithm: str = "ahash") -> None:
        algo = hash_algorithm.lower()
        if algo not in _HASH_FUNCS:
            logger.warning(
                "Hash algorithm %r is unavailable in the desktop build; "
                "falling back to ahash",
                algo,
            )
            algo = "ahash"
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
        return self._hash_func(img)

    def has_changed(self, hash1: str, hash2: str, threshold: int) -> bool:
        try:
            diff = _hex_hamming_distance(hash1, hash2)
        except ValueError:
            logger.warning("Invalid image hash encountered; treating as changed")
            return True
        return diff > threshold


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

    def downscale_to_max_edge(self, image_data: bytes, max_edge: int) -> bytes:
        if max_edge <= 0:
            return image_data
        img = Image.open(io.BytesIO(image_data))
        w, h = img.size
        longest = max(w, h)
        if longest <= max_edge:
            return image_data
        scale = max_edge / longest
        new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
        resized = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="PNG")
        logger.info(
            "Downscaled image %dx%d -> %dx%d (max_edge=%d)",
            w,
            h,
            new_size[0],
            new_size[1],
            max_edge,
        )
        return buf.getvalue()
