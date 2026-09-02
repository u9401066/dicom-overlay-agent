"""Offline smoke for codecs and review rendering in the frozen bundle."""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from PIL import Image, ImageFont

from dicom_overlay.domain.entities import (
    AnalysisResult,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.infrastructure.desktop_review_exporter import (
    export_desktop_review,
)
from dicom_overlay.infrastructure.logging_config import setup_logging

if TYPE_CHECKING:
    from collections.abc import Callable

_LOG_MARKER = "packaged_runtime_smoke_logging_ok"


def run_package_runtime_smoke(work_dir: Path) -> dict[str, object]:
    """Exercise low-level packaged functionality without GUI/network access."""

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    checks: dict[str, bool] = {}
    failures: list[str] = []
    artifacts: dict[str, bytes] = {}

    root_logger = logging.getLogger()
    app_logger = logging.getLogger("dicom_overlay")
    previous_handlers = list(root_logger.handlers)
    previous_root_level = root_logger.level
    previous_app_level = app_logger.level

    def check(name: str, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:  # pragma: no cover - exercised by frozen failures
            checks[name] = False
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
        else:
            checks[name] = True

    def logging_smoke() -> None:
        log_path = work_dir / "runtime-smoke.log"
        setup_logging(log_level="INFO", log_file=str(log_path))
        structlog.get_logger("dicom_overlay.package_runtime_smoke").info(_LOG_MARKER)
        for handler in root_logger.handlers:
            handler.flush()
        if _LOG_MARKER not in log_path.read_text(encoding="utf-8"):
            raise RuntimeError("structured log marker was not persisted")

    def png_smoke() -> None:
        source = Image.new("RGB", (96, 48), (238, 241, 245))
        buffer = io.BytesIO()
        source.save(buffer, format="PNG")
        encoded = buffer.getvalue()
        with Image.open(io.BytesIO(encoded)) as decoded:
            decoded.load()
            if decoded.format != "PNG" or decoded.size != source.size:
                raise RuntimeError("PNG round-trip changed format or dimensions")
        artifacts["png"] = encoded

    def jpeg_smoke() -> None:
        source = Image.new("RGB", (80, 40), (90, 110, 130))
        buffer = io.BytesIO()
        source.save(buffer, format="JPEG", quality=88)
        with Image.open(io.BytesIO(buffer.getvalue())) as decoded:
            decoded.load()
            if decoded.format != "JPEG" or decoded.size != source.size:
                raise RuntimeError("JPEG decode changed format or dimensions")

    def font_smoke() -> None:
        font = ImageFont.load_default()
        left, top, right, bottom = font.getbbox("DICOM review")
        if right <= left or bottom <= top:
            raise RuntimeError("Pillow font renderer returned an empty glyph box")

    def review_smoke() -> None:
        source = artifacts.get("png")
        if source is None:
            raise RuntimeError("PNG source was unavailable for review rendering")
        result = AnalysisResult(
            modality=Modality.EKG,
            summary="Packaging review render smoke.",
            severity=Severity.WARNING,
            findings=[
                Finding(
                    id="package-smoke",
                    regions=["lead_II"],
                    label="Review marker",
                    detail="Synthetic non-clinical packaging fixture.",
                    severity=Severity.WARNING,
                    bboxes=[RegionRect(0.2, 0.2, 0.4, 0.4)],
                )
            ],
            checklist={},
        )
        review_path = export_desktop_review(
            image_base64=base64.b64encode(source).decode("ascii"),
            result=result,
            output_root=work_dir / "review",
        )
        with Image.open(review_path) as review:
            review.load()
            if review.format != "PNG" or review.width <= 96:
                raise RuntimeError("annotated review PNG was not rendered")
        if not (review_path.parent / "bbox-audit.json").is_file():
            raise RuntimeError("review coordinate audit was not written")

    try:
        check("logging_init", logging_smoke)
        check("png_encode_decode", png_smoke)
        check("jpeg_decode", jpeg_smoke)
        check("font_render", font_smoke)
        check("review_export", review_smoke)
    finally:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            if handler not in previous_handlers:
                handler.close()
        for handler in previous_handlers:
            root_logger.addHandler(handler)
        root_logger.setLevel(previous_root_level)
        app_logger.setLevel(previous_app_level)

    return {
        "status": "ok" if not failures else "failed",
        "checks": checks,
        "failures": failures,
    }
