"""Offline smoke for codecs and review rendering in the frozen bundle."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from PIL import Image, ImageFont

from dicom_overlay.infrastructure.desktop_review_exporter import (
    export_desktop_review,
)
from dicom_overlay.infrastructure.logging_config import setup_logging
from medical_image_harness.models import (
    AnalysisResult,
    Finding,
    Modality,
    RegionRect,
    Severity,
)

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

    def harness_contract_smoke() -> None:
        from medical_image_harness.resources import load_skill
        from medical_image_harness.schema import load_schema, validation_errors

        if not load_skill().strip():
            raise RuntimeError("public harness method resource is empty")
        schema = load_schema()
        if "input_provenance" not in schema.get("required", []):
            raise RuntimeError("canonical harness contract lacks provenance gate")
        if not validation_errors({}):
            raise RuntimeError("canonical harness validator accepted an empty draft")

    def harness_engine_smoke() -> None:
        from medical_image_harness.image_ops import crop_source_image
        from medical_image_harness.multipass import (
            MultiPassInterpreter,
            RefinementAction,
            RefinementDelta,
            RefinementResult,
        )

        stages: list[str] = []
        box = RegionRect(0.2, 0.2, 0.4, 0.4)

        class SyntheticAnalyzer:
            async def analyze(self, image_base64, modality, valid_regions):
                del image_base64, valid_regions
                stages.append("coarse")
                return AnalysisResult(
                    modality=modality, summary="Synthetic package check",
                    severity=Severity.WARNING, checklist={},
                    findings=[Finding(id="synthetic", regions=[], label="Synthetic marker",
                        detail="Non-clinical fixture", severity=Severity.WARNING, bboxes=[box])],
                )

            async def refine(self, image_base64, modality, valid_regions, **context):
                del modality, valid_regions
                with Image.open(io.BytesIO(base64.b64decode(image_base64))) as crop:
                    if crop.width >= 96 or crop.height >= 48:
                        raise RuntimeError("shared engine did not supply a bounded crop")
                stages.append("refine")
                return RefinementResult((RefinementDelta(
                    RefinementAction.CONFIRM, target_id=context["hypothesis"].id,
                    rationale="Synthetic packaging check only",
                ),))

            async def finalize(self, image_base64, modality, valid_regions, *, draft, **context):
                del image_base64, modality, valid_regions, context
                stages.append("finalize")
                return draft

        interpreter = MultiPassInterpreter(
            SyntheticAnalyzer(),
            lambda image, region: crop_source_image(image, region).image_base64,
            max_zoom_targets=1, zoom_padding=0.0,
            checklist_keys_for=lambda _: frozenset(),
        )
        result = asyncio.run(interpreter.interpret(
            base64.b64encode(artifacts["png"]).decode("ascii"), Modality.CXR, [],
        ))
        if stages != ["coarse", "refine", "finalize"] or result.findings[0].bboxes != [box]:
            raise RuntimeError("shared engine stage/coordinate contract failed")

    try:
        check("logging_init", logging_smoke)
        check("png_encode_decode", png_smoke)
        check("jpeg_decode", jpeg_smoke)
        check("font_render", font_smoke)
        check("review_export", review_smoke)
        check("harness_contract", harness_contract_smoke)
        check("harness_engine", harness_engine_smoke)
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
