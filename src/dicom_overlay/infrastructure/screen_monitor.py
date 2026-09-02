"""Screen monitor — window detection + screenshot + hash comparison."""

from __future__ import annotations

import io
import math
import os
import statistics
from collections.abc import Callable, Iterable
from typing import TypedDict

import mss
import structlog
from PIL import Image, ImageChops, ImageFilter

from dicom_overlay.domain.entities import DisplayFrame, RegionRect, WindowRect
from dicom_overlay.domain.services import ImageProcessorService, ScreenMonitorService

logger = structlog.get_logger(__name__)

# pywin32 imports — Windows only
win32api = None
win32con = None
win32gui = None
win32process = None
try:
    import win32api as _win32api
    import win32con as _win32con
    import win32gui as _win32gui
    import win32process as _win32process

    win32api = _win32api
    win32con = _win32con
    win32gui = _win32gui
    win32process = _win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    logger.warning("pywin32 not available — window detection disabled")


_HashFunc = Callable[[Image.Image], str]


class _SignalCandidate(TypedDict):
    label: str
    source: str
    x: float
    y: float
    w: float
    h: float
    confidence: float
    dark_pixel_ratio: float
    bbox_ink_density: float


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

    def __init__(
        self,
        hash_algorithm: str = "ahash",
        *,
        excluded_process_ids: Iterable[int] = (),
    ) -> None:
        algo = hash_algorithm.lower()
        if algo not in _HASH_FUNCS:
            logger.warning(
                "Hash algorithm %r is unavailable in the desktop build; "
                "falling back to ahash",
                algo,
            )
            algo = "ahash"
        self._hash_func = _HASH_FUNCS[algo]
        self._excluded_process_ids = frozenset(
            {os.getpid(), *(int(pid) for pid in excluded_process_ids)}
        )
        self._target_hwnd: int | None = None
        logger.info("Hash algorithm: %s", algo)

    def find_target_window(self, keywords: list[str]) -> WindowRect | None:
        if not HAS_WIN32 or win32gui is None or win32process is None:
            return None

        gui = win32gui
        process = win32process
        normalized_keywords = tuple(
            keyword.strip().casefold() for keyword in keywords if keyword.strip()
        )
        if not normalized_keywords:
            self._target_hwnd = None
            return None

        def _candidate(hwnd: int) -> tuple[tuple[int, int, int, int], WindowRect] | None:
            if not gui.IsWindowVisible(hwnd):
                return None
            is_iconic = getattr(gui, "IsIconic", None)
            if callable(is_iconic) and is_iconic(hwnd):
                return None
            try:
                _thread_id, process_id = process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return None
            if int(process_id) in self._excluded_process_ids:
                return None
            title = gui.GetWindowText(hwnd).strip()
            if not title:
                return None
            folded_title = title.casefold()
            matches = [
                index
                for index, keyword in enumerate(normalized_keywords)
                if keyword in folded_title
            ]
            if not matches:
                return None
            left, top, right, bottom = gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top
            if width <= 100 or height <= 100:
                return None
            starts_with_keyword = int(
                any(folded_title.startswith(keyword) for keyword in normalized_keywords)
            )
            # Multiple independent keyword hits (for example, "DICOM Viewer")
            # and an explicit title prefix outrank incidental mentions such as
            # a source-code editor showing this repository name.  Area is only
            # a final tie-breaker and never overrides title specificity.
            score = (
                len(matches),
                starts_with_keyword,
                -min(matches),
                width * height,
            )
            return score, WindowRect(left=left, top=top, width=width, height=height)

        if self._target_hwnd is not None:
            existing = _candidate(self._target_hwnd)
            if existing is not None:
                return existing[1]
            self._target_hwnd = None

        candidates: list[tuple[tuple[int, int, int, int], int, WindowRect]] = []

        def _enum_callback(hwnd: int, _: object) -> None:
            candidate = _candidate(hwnd)
            if candidate is not None:
                score, rect = candidate
                candidates.append((score, hwnd, rect))

        try:
            gui.EnumWindows(_enum_callback, None)
        except Exception:
            logger.exception("Error enumerating windows")

        if not candidates:
            return None
        _score, hwnd, result = max(candidates, key=lambda item: item[0])
        self._target_hwnd = hwnd
        return result

    def display_for_window(self, window: WindowRect) -> DisplayFrame | None:
        """Resolve a Win32 window rectangle to its nearest physical monitor."""
        if not HAS_WIN32 or win32api is None or win32con is None:
            return None
        try:
            handle = win32api.MonitorFromRect(
                (window.left, window.top, window.right, window.bottom),
                win32con.MONITOR_DEFAULTTONEAREST,
            )
            info = win32api.GetMonitorInfo(handle)
            left, top, right, bottom = info["Monitor"]
            monitor_handles = [
                item[0] for item in win32api.EnumDisplayMonitors(None, None)
            ]
            try:
                monitor_index = monitor_handles.index(handle)
            except ValueError:
                monitor_index = 0
            return DisplayFrame(
                physical_rect=WindowRect(
                    left=int(left),
                    top=int(top),
                    width=int(right - left),
                    height=int(bottom - top),
                ),
                device_name=str(info.get("Device", "")),
                monitor_index=monitor_index,
                is_primary=bool(
                    int(info.get("Flags", 0)) & win32con.MONITORINFOF_PRIMARY
                ),
            )
        except Exception:
            logger.exception("Error resolving viewer display")
            return None

    def capture_region(self, rect: WindowRect) -> bytes:
        monitor = {
            "left": rect.left,
            "top": rect.top,
            "width": rect.width,
            "height": rect.height,
        }
        with mss.mss() as sct:
            screenshot = sct.grab(monitor)
            img = Image.frombytes(
                "RGB", screenshot.size, screenshot.bgra, "raw", "BGRX"
            )
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

    # Upscale a second-pass crop so its short edge reaches at least this many
    # pixels, keeping small lesions legible for the closer look.
    _MIN_CROP_EDGE_PX = 512
    _MIN_SOURCE_SIGNAL_EDGE_PX = 64

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

    def crop_region_base64(self, image_base64: str, region: RegionRect) -> str:
        """Crop a normalized 0-1 sub-region out of a base64 PNG (ImageCropper).

        Matches the ``ImageCropper`` protocol used by the multi-pass
        orchestrator: ``region`` is a ``RegionRect`` in normalized coordinates
        relative to the input image. The crop is a strict subset of the input
        (PHI invariant: capture is never widened), then upscaled so its short
        edge reaches at least ``_MIN_CROP_EDGE_PX`` to keep small lesions legible
        for the second-pass read. Returns a base64 PNG.
        """
        import base64

        cropped = self._crop_region_image(image_base64, region)
        cw, ch = cropped.size
        short_edge = min(cw, ch)
        if 0 < short_edge < self._MIN_CROP_EDGE_PX:
            scale = self._MIN_CROP_EDGE_PX / short_edge
            cropped = cropped.resize(
                (max(1, round(cw * scale)), max(1, round(ch * scale))),
                Image.LANCZOS,
            )
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def crop_region_bytes(self, image_base64: str, region: RegionRect) -> bytes:
        """Return the exact source-pixel crop without synthetic upscaling."""

        cropped = self._crop_region_image(image_base64, region)
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def _crop_region_image(image_base64: str, region: RegionRect) -> Image.Image:
        import base64

        data = base64.b64decode(image_base64, validate=True)
        with Image.open(io.BytesIO(data)) as source:
            w, h = source.size
            if w <= 0 or h <= 0:
                raise ValueError("cannot crop an empty image")
            x0 = max(
                0,
                min(w - 1, math.floor(region.x * w)),
            )
            y0 = max(
                0,
                min(h - 1, math.floor(region.y * h)),
            )
            x1 = max(
                x0 + 1,
                min(w, math.ceil((region.x + region.w) * w)),
            )
            y1 = max(
                y0 + 1,
                min(h, math.ceil((region.y + region.h) * h)),
            )
            return source.crop((x0, y0, x1, y1))

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

    def image_size(self, image_data: bytes) -> tuple[int, int]:
        img = Image.open(io.BytesIO(image_data))
        return img.size

    def image_quality_profile(self, image_data: bytes) -> dict[str, object]:
        """Lightweight image preflight metrics before sending to an MLLM.

        This is a deterministic, local aid for the harness: it flags blank or
        very low-signal images so model errors can be separated from bad input.
        It is not a diagnostic model and never changes the captured ROI.
        """
        img = Image.open(io.BytesIO(image_data)).convert("L")
        histogram = img.histogram()
        total = max(1, img.width * img.height)
        dark_pixels = sum(histogram[:80])
        bright_pixels = sum(histogram[240:])
        ink_ratio = dark_pixels / total
        bright_ratio = bright_pixels / total
        entropy_bits = img.entropy()

        def percentile_gray(fraction: float) -> int:
            target = max(1, round(total * fraction))
            cumulative = 0
            for value, count in enumerate(histogram):
                cumulative += count
                if cumulative >= target:
                    return value
            return 255

        robust_dynamic_range = percentile_gray(0.99) - percentile_gray(0.01)
        edges = img.filter(ImageFilter.FIND_EDGES)
        if edges.width > 2 and edges.height > 2:
            edges = edges.crop((1, 1, edges.width - 1, edges.height - 1))
        edge_histogram = edges.histogram()
        edge_total = max(1, edges.width * edges.height)
        edge_pixel_ratio = sum(edge_histogram[24:]) / edge_total

        bright_blank = (
            bright_ratio > 0.75 and ink_ratio < 0.01 and edge_pixel_ratio < 0.005
        )
        structure_blank = edge_pixel_ratio < 0.001
        near_uniform = robust_dynamic_range < 8 and edge_pixel_ratio < 0.002
        source_short_edge_px = min(img.width, img.height)
        insufficient_source_resolution = (
            source_short_edge_px < self._MIN_SOURCE_SIGNAL_EDGE_PX
        )
        low_signal = (
            bright_blank
            or structure_blank
            or near_uniform
            or insufficient_source_resolution
        )
        return {
            "width_px": img.width,
            "height_px": img.height,
            "aspect_ratio": round(img.width / max(1, img.height), 6),
            "ink_pixel_ratio": round(ink_ratio, 6),
            "bright_pixel_ratio": round(bright_ratio, 6),
            "entropy_bits": round(entropy_bits, 6),
            "robust_dynamic_range": robust_dynamic_range,
            "edge_pixel_ratio": round(edge_pixel_ratio, 6),
            "source_short_edge_px": source_short_edge_px,
            "insufficient_source_resolution": insufficient_source_resolution,
            "low_signal": low_signal,
        }

    def ekg_row_strip_evidence(self, image_base64: str) -> dict[str, object]:
        """Detect a 12-row ECG strip from full-width black-ink periodicity.

        Red graph-paper lines are excluded by thresholding the maximum RGB
        channel instead of grayscale. The detector only reports geometry; it
        does not identify waveforms, leads, or diagnoses.
        """

        import base64

        raw = base64.b64decode(image_base64, validate=True)
        with Image.open(io.BytesIO(raw)) as source:
            image = source.convert("RGB")
        width, height = image.size
        method = "local_black_ink_row_periodicity_v2"
        if width < 240 or height < 240:
            return {
                "method": method,
                "status": "insufficient",
                "is_12_row_strip": False,
                "detected_row_count": 0,
                "reason": "image_too_small",
            }

        red, green, blue = image.split()
        max_channel = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        black_mask = max_channel.point(
            [255 if value < 110 else 0 for value in range(256)],
            mode="L",
        )
        left = max(1, round(width * 0.05))
        content = black_mask.crop((left, 0, width, height))
        content_width = content.width
        pixels = content.tobytes()
        row_counts = [
            sum(pixels[y * content_width : (y + 1) * content_width]) / 255.0
            for y in range(height)
        ]
        smooth_radius = max(1, round(height * 0.003))
        smoothed = [
            statistics.fmean(
                row_counts[
                    max(0, y - smooth_radius) : min(
                        height,
                        y + smooth_radius + 1,
                    )
                ]
            )
            for y in range(height)
        ]
        minimum_distance = max(4, round(height * 0.05))
        # ``smoothed`` is a vertical mean, so a one-pixel trace is diluted by
        # the smoothing-window height.  The former fixed 8% threshold therefore
        # became progressively stricter as screenshots got taller: at 1079 px,
        # a seven-row window required roughly 56% of a lead baseline to be
        # perfectly horizontal.  Scale the threshold back to a resolution-
        # independent horizontal-coherence requirement while retaining the old
        # 8% ceiling for smaller captures.
        smoothing_window_rows = 2 * smooth_radius + 1
        minimum_horizontal_coherence_ratio = 0.32
        minimum_peak_ink_ratio = min(
            0.08,
            minimum_horizontal_coherence_ratio / smoothing_window_rows,
        )
        minimum_strength = content_width * minimum_peak_ink_ratio
        # Window screenshots can contribute a solid one-pixel border.  It is
        # not ECG evidence and can otherwise displace the first/last lead peak.
        edge_guard = max(smooth_radius + 1, round(height * 0.01))
        peaks: list[int] = []
        candidate_rows = range(edge_guard, max(edge_guard, height - edge_guard))
        for y in sorted(candidate_rows, key=smoothed.__getitem__, reverse=True):
            if smoothed[y] < minimum_strength:
                break
            if all(abs(y - existing) >= minimum_distance for existing in peaks):
                peaks.append(y)
        peaks.sort()
        gaps = [peaks[index] - peaks[index - 1] for index in range(1, len(peaks))]
        median_gap = statistics.median(gaps) if gaps else 0.0
        consistent_gap_count = (
            sum(
                0.65 * median_gap <= gap <= 1.55 * median_gap
                for gap in gaps
            )
            if median_gap > 0.0
            else 0
        )
        period_ratio = median_gap / height
        span_ratio = (peaks[-1] - peaks[0]) / height if len(peaks) >= 2 else 0.0
        confirmed = (
            len(peaks) == 12
            and consistent_gap_count >= 10
            and 0.065 <= period_ratio <= 0.10
            and span_ratio >= 0.85
        )
        return {
            "method": method,
            "status": "ok",
            "is_12_row_strip": confirmed,
            "detected_row_count": len(peaks),
            "peak_y_normalized": [round(y / height, 6) for y in peaks],
            "median_row_period_normalized": round(period_ratio, 6),
            "consistent_gap_count": consistent_gap_count,
            "vertical_span_ratio": round(span_ratio, 6),
            "black_threshold_max_rgb": 110,
            "minimum_peak_ink_ratio": round(minimum_peak_ink_ratio, 6),
            "minimum_horizontal_coherence_ratio": (
                minimum_horizontal_coherence_ratio
            ),
            "smoothing_window_rows": smoothing_window_rows,
            "edge_guard_ratio": round(edge_guard / height, 6),
        }

    def local_signal_candidates(self, image_data: bytes) -> dict[str, object]:
        """Return deterministic local signal/bbox proposals.

        This is a cheap model-assist layer for ECG-like line images. A compact
        isolated trace is returned as one tight box. When ink spans most of the
        page (the common 12-lead case), the image is scored in generic spatial
        tiles so the caller receives local candidates instead of the useless
        near-full-frame ``[0, 0, 1, 1]`` proposal. It does not diagnose; it only
        gives the harness and reviewer auditable regions to inspect again.
        """
        threshold = 90
        img = Image.open(io.BytesIO(image_data)).convert("L")
        width, height = img.size
        table = [255 if value < threshold else 0 for value in range(256)]
        mask = img.point(table, mode="L")
        bbox = mask.getbbox()
        dark_pixels = mask.histogram()[255]
        total = max(1, width * height)
        dark_ratio = dark_pixels / total
        low_signal = dark_ratio < 0.01
        if bbox is None:
            return {
                "method": "local_threshold_ink_bbox",
                "threshold_gray": threshold,
                "candidate_count": 0,
                "candidates": [],
                "dark_pixel_ratio": 0.0,
                "low_signal": True,
            }

        def build_candidate(
            candidate_bbox: tuple[int, int, int, int],
            candidate_dark_pixels: int,
            *,
            source: str,
        ) -> _SignalCandidate:
            left, top, right, bottom = candidate_bbox
            bbox_area = max(1, (right - left) * (bottom - top))
            bbox_density = candidate_dark_pixels / bbox_area
            local_dark_ratio = candidate_dark_pixels / total
            aspect = (right - left) / max(1, bottom - top)
            confidence = min(
                0.99,
                (local_dark_ratio * 20.0)
                + (bbox_density * 0.2)
                + min(0.2, aspect * 0.02),
            )
            return {
                "label": "local_signal",
                "source": source,
                "x": round(left / max(1, width), 6),
                "y": round(top / max(1, height), 6),
                "w": round((right - left) / max(1, width), 6),
                "h": round((bottom - top) / max(1, height), 6),
                "confidence": round(confidence, 6),
                "dark_pixel_ratio": round(local_dark_ratio, 6),
                "bbox_ink_density": round(bbox_density, 6),
            }

        left, top, right, bottom = bbox
        overall_area_ratio = max(1, (right - left) * (bottom - top)) / total
        candidates: list[_SignalCandidate]
        if overall_area_ratio <= 0.55:
            candidates = [
                build_candidate(
                    bbox,
                    dark_pixels,
                    source="local_threshold_ink_bbox",
                )
            ]
            method = "local_threshold_ink_bbox"
            suppressed_candidate_count = 0
        else:
            # Spatial tiling is layout-agnostic: no lead name or fixed 3x4 ECG
            # position is assumed. Tight dark-pixel bounds inside each tile are
            # retained so crop/refine remains local and reviewable.
            aspect_ratio = width / max(1, height)
            columns = 4 if aspect_ratio >= 1.35 else 3
            rows = 3 if aspect_ratio >= 1.35 else 4
            candidates = []
            for row in range(rows):
                tile_top = round(row * height / rows)
                tile_bottom = round((row + 1) * height / rows)
                for column in range(columns):
                    tile_left = round(column * width / columns)
                    tile_right = round((column + 1) * width / columns)
                    tile = mask.crop((tile_left, tile_top, tile_right, tile_bottom))
                    local_bbox = tile.getbbox()
                    if local_bbox is None:
                        continue
                    tile_dark_pixels = tile.histogram()[255]
                    tile_area = max(1, tile.width * tile.height)
                    if tile_dark_pixels / tile_area < 0.002:
                        continue
                    local_left, local_top, local_right, local_bottom = local_bbox
                    global_bbox = (
                        tile_left + local_left,
                        tile_top + local_top,
                        tile_left + local_right,
                        tile_top + local_bottom,
                    )
                    candidate = build_candidate(
                        global_bbox,
                        tile_dark_pixels,
                        source="local_threshold_tile_bbox",
                    )
                    if float(candidate["w"]) * float(candidate["h"]) >= 0.55:
                        continue
                    candidates.append(candidate)
            candidates.sort(
                key=lambda candidate: float(candidate["confidence"]),
                reverse=True,
            )
            ranked_candidates = candidates
            if len(ranked_candidates) >= 3:
                median_density = statistics.median(
                    float(candidate["bbox_ink_density"])
                    for candidate in ranked_candidates
                )
                median_confidence = statistics.median(
                    float(candidate["confidence"]) for candidate in ranked_candidates
                )
                candidates = [
                    candidate
                    for candidate in ranked_candidates
                    if float(candidate["bbox_ink_density"]) >= median_density * 1.35
                    and float(candidate["confidence"]) >= median_confidence + 0.02
                ][:6]
            else:
                candidates = []
            suppressed_candidate_count = len(ranked_candidates) - len(candidates)
            method = "local_threshold_tile_bbox"

        return {
            "method": method,
            "threshold_gray": threshold,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "suppressed_candidate_count": suppressed_candidate_count,
            "selection_rule": "localized_density_outlier",
            "dark_pixel_ratio": round(dark_ratio, 6),
            "low_signal": low_signal,
        }
