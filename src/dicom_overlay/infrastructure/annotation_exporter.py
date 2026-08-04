"""Export eval results as annotated review images.

This is an offline review helper for the evaluation harness: it draws the
model-returned normalized bboxes onto the original dataset image and appends a
right-side text panel with summary/finding details. It never captures screen
content and never widens any ROI; it only reads already-saved eval artifacts.
"""

from __future__ import annotations

import json
import math
import textwrap
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw, ImageFont

from dicom_overlay.domain.entities import RegionRect, WindowRect
from dicom_overlay.infrastructure.overlay_geometry import (
    BboxProjectionCalibration,
    project_bbox_to_overlay_highlight,
)

if TYPE_CHECKING:
    from PIL.ImageFont import ImageFont as PillowFont

_PANEL_WIDTH = 520
_MARGIN = 14
_LINE_SPACING = 4
_COLORS = {
    "critical": (210, 35, 35),
    "warning": (226, 130, 18),
    "info": (45, 110, 210),
    "normal": (46, 145, 80),
}
_TEXT = (24, 29, 36)
_MUTED = (92, 99, 112)
_PANEL_BG = (248, 249, 251)
_LOW_SIGNAL = (185, 42, 150)
_INK_THRESHOLD = 80
_LOW_SIGNAL_MIN_INK_RATIO = 0.01
_CROP_THUMBNAIL_MIN_EDGE = 180


@dataclass(frozen=True)
class ExportedAnnotation:
    """One exported review image."""

    case_label: str
    image_path: Path
    result_path: Path
    output_path: Path


@dataclass(frozen=True)
class BboxAudit:
    """Code-aided QA record for one model-returned bbox."""

    case_label: str
    finding_index: int
    bbox_index: int
    finding_id: str
    label: str
    severity: str
    normalized: dict[str, float]
    clamped_normalized: dict[str, float]
    pixels: dict[str, int]
    width_px: int
    height_px: int
    ink_pixel_ratio: float
    low_signal: bool
    was_clamped: bool
    invalid_reason: str
    projection_ok: bool
    projection_max_edge_drift_px: float
    projection_was_clamped: bool
    projection_back_projected_bbox: dict[str, float]
    crop: str
    review_image: str

    def to_json(self) -> dict[str, Any]:
        """Return a stable JSONL payload."""
        return {
            "audit_type": "bbox",
            "case": self.case_label,
            "finding_index": self.finding_index,
            "bbox_index": self.bbox_index,
            "finding_id": self.finding_id,
            "label": self.label,
            "severity": self.severity,
            "normalized": self.normalized,
            "clamped_normalized": self.clamped_normalized,
            "pixels": self.pixels,
            "width_px": self.width_px,
            "height_px": self.height_px,
            "ink_pixel_ratio": round(self.ink_pixel_ratio, 6),
            "low_signal": self.low_signal,
            "was_clamped": self.was_clamped,
            "invalid_reason": self.invalid_reason,
            "projection_ok": self.projection_ok,
            "projection_max_edge_drift_px": round(self.projection_max_edge_drift_px, 6),
            "projection_was_clamped": self.projection_was_clamped,
            "projection_back_projected_bbox": self.projection_back_projected_bbox,
            "crop": self.crop,
            "review_image": self.review_image,
        }


@dataclass(frozen=True)
class BboxPixelMapping:
    """Normalized bbox mapped onto source-image pixels."""

    normalized: dict[str, float]
    clamped_normalized: dict[str, float]
    pixels: tuple[int, int, int, int]
    was_clamped: bool
    invalid_reason: str
    projection: BboxProjectionCalibration


def export_eval_annotations(
    *,
    eval_dir: Path,
    manifest_path: Path,
    output_dir: Path | None = None,
    limit: int = 0,
    clean: bool = True,
) -> list[Path]:
    """Render all eval ``results/*.json`` files into annotated PNGs."""
    eval_dir = Path(eval_dir)
    output_dir = output_dir or (eval_dir / "review")
    output_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = output_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    if clean:
        _clean_generated_review_artifacts(output_dir)

    image_index = _load_manifest_image_index(manifest_path)
    result_paths = sorted((eval_dir / "results").glob("*.json"))
    if limit > 0:
        result_paths = result_paths[:limit]

    exported: list[ExportedAnnotation] = []
    audit_records: list[Any] = []
    for result_path in result_paths:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        image_path = _resolve_image_path(result, image_index)
        case_label = str(result.get("case") or result_path.stem)
        safe_name = _safe_filename(case_label)
        output_path = output_dir / f"{safe_name}.review.png"
        _, audits = _render_annotated_result_with_audit(
            image_path=image_path,
            result=result,
            output_path=output_path,
            case_label=case_label,
            crops_dir=crops_dir,
        )
        exported.append(
            ExportedAnnotation(
                case_label=case_label,
                image_path=image_path,
                result_path=result_path,
                output_path=output_path,
            )
        )
        if audits:
            audit_records.extend(audits)
        else:
            audit_records.append(
                {
                    "audit_type": "case",
                    "case": case_label,
                    "bbox_count": 0,
                    "finding_count": len(result.get("findings") or []),
                    "review_image": output_path.name,
                }
            )

    _write_index(output_dir, exported)
    _write_bbox_audit(output_dir, audit_records)
    return [item.output_path for item in exported]


def _clean_generated_review_artifacts(output_dir: Path) -> None:
    """Remove generated review files while preserving human notes."""
    for path in output_dir.glob("*.review.png"):
        path.unlink(missing_ok=True)
    for name in ("index.html", "bbox-audit.jsonl"):
        (output_dir / name).unlink(missing_ok=True)
    crops_dir = output_dir / "crops"
    if crops_dir.exists():
        for path in crops_dir.glob("*.png"):
            path.unlink(missing_ok=True)


def render_annotated_result(
    *,
    image_path: Path,
    result: dict[str, Any],
    output_path: Path,
) -> Path:
    """Draw bboxes + a finding description panel for one result."""
    path, _ = _render_annotated_result_with_audit(
        image_path=image_path,
        result=result,
        output_path=output_path,
        case_label=str(result.get("case") or output_path.stem),
        crops_dir=None,
    )
    return path


def _render_annotated_result_with_audit(
    *,
    image_path: Path,
    result: dict[str, Any],
    output_path: Path,
    case_label: str,
    crops_dir: Path | None,
) -> tuple[Path, list[BboxAudit | dict[str, Any]]]:
    """Draw review image and return per-bbox audit records."""
    source = Image.open(image_path).convert("RGB")
    canvas = Image.new("RGB", (source.width + _PANEL_WIDTH, source.height), "white")
    canvas.paste(source, (0, 0))
    draw = ImageDraw.Draw(canvas)
    font = _load_font(15)
    small = _load_font(13)
    title = _load_font(17)

    findings = list(result.get("findings") or [])
    audit_records: list[BboxAudit | dict[str, Any]] = []
    audits_by_finding: dict[int, list[BboxAudit]] = {}
    for index, finding in enumerate(findings, start=1):
        color = _color_for(str(finding.get("severity") or result.get("severity")))
        for bbox_index, bbox in enumerate(finding.get("bboxes") or [], start=1):
            mapping = (
                _bbox_pixels(bbox, source.width, source.height)
                if isinstance(bbox, dict)
                else None
            )
            if mapping is None:
                audit_records.append(
                    _invalid_bbox_audit(
                        bbox,
                        case_label=case_label,
                        finding=finding,
                        finding_index=index,
                        bbox_index=bbox_index,
                        review_image=output_path.name,
                    )
                )
                continue
            box = mapping.pixels
            crop_rel = ""
            if crops_dir is not None:
                crop_path = _save_bbox_crop(
                    source,
                    box,
                    crops_dir,
                    f"{_safe_filename(case_label)}-f{index:02d}-b{bbox_index:02d}.png",
                )
                crop_rel = _relative_posix(crop_path, crops_dir.parent)
            audit = _audit_bbox(
                source,
                mapping,
                case_label=case_label,
                finding=finding,
                finding_index=index,
                bbox_index=bbox_index,
                crop_rel=crop_rel,
                review_image=output_path.name,
            )
            audit_records.append(audit)
            audits_by_finding.setdefault(index, []).append(audit)
            draw.rectangle(box, outline=color, width=3)
            if audit.low_signal:
                _draw_low_signal_marker(draw, box)
            _draw_badge(draw, box[0], box[1], str(index), color, small)

    _draw_panel(
        draw,
        result,
        findings,
        source.width,
        source.height,
        font,
        small,
        title,
        audits_by_finding,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return output_path, audit_records


def _load_manifest_image_index(manifest_path: Path) -> dict[str, Path]:
    manifest_path = Path(manifest_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    index: dict[str, Path] = {}
    for case in data.get("cases", []):
        rel = Path(str(case["image"]))
        path = root / rel
        label = str(case.get("label") or rel.name)
        for key in {rel.name, rel.stem, label}:
            index[key] = path
    return index


def _resolve_image_path(result: dict[str, Any], image_index: dict[str, Path]) -> Path:
    for key in (
        str(result.get("image") or ""),
        Path(str(result.get("image") or "")).stem,
        str(result.get("case") or ""),
    ):
        if key and key in image_index:
            return image_index[key]
    raise FileNotFoundError(
        f"Could not resolve source image for result case={result.get('case')!r} "
        f"image={result.get('image')!r}"
    )


def _bbox_pixels(
    bbox: dict[str, Any],
    width: int,
    height: int,
) -> BboxPixelMapping | None:
    try:
        x = float(bbox["x"])
        y = float(bbox["y"])
        w = float(bbox["w"])
        h = float(bbox["h"])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (x, y, w, h)) or w <= 0 or h <= 0:
        return None
    x_start = _clamp(x)
    y_start = _clamp(y)
    x_end = _clamp(x + w)
    y_end = _clamp(y + h)
    x0 = round(x_start * width)
    y0 = round(y_start * height)
    x1 = round(x_end * width)
    y1 = round(y_end * height)
    if x1 <= x0 or y1 <= y0:
        return None
    raw = _normalized_payload(x, y, w, h)
    clamped = _normalized_payload(x_start, y_start, x_end - x_start, y_end - y_start)
    reason = _clamp_reason(x, y, w, h)
    projection = _project_bbox_for_review(
        x=x,
        y=y,
        w=w,
        h=h,
        width=width,
        height=height,
    )
    return BboxPixelMapping(
        normalized=raw,
        clamped_normalized=clamped,
        pixels=(x0, y0, x1, y1),
        was_clamped=bool(reason),
        invalid_reason=reason,
        projection=projection,
    )


def _audit_bbox(
    source: Image.Image,
    mapping: BboxPixelMapping,
    *,
    case_label: str,
    finding: dict[str, Any],
    finding_index: int,
    bbox_index: int,
    crop_rel: str,
    review_image: str,
) -> BboxAudit:
    box = mapping.pixels
    x0, y0, x1, y1 = box
    gray = source.crop(box).convert("L")
    total = max(1, gray.width * gray.height)
    histogram = gray.histogram()
    ink_pixels = sum(histogram[:_INK_THRESHOLD])
    ink_ratio = ink_pixels / total
    return BboxAudit(
        case_label=case_label,
        finding_index=finding_index,
        bbox_index=bbox_index,
        finding_id=str(finding.get("id") or ""),
        label=str(finding.get("label") or "finding"),
        severity=str(finding.get("severity") or ""),
        normalized=mapping.normalized,
        clamped_normalized=mapping.clamped_normalized,
        pixels={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        width_px=x1 - x0,
        height_px=y1 - y0,
        ink_pixel_ratio=ink_ratio,
        low_signal=ink_ratio < _LOW_SIGNAL_MIN_INK_RATIO,
        was_clamped=mapping.was_clamped,
        invalid_reason=mapping.invalid_reason,
        projection_ok=(
            mapping.projection.ok
            and not mapping.projection.was_clamped
            and not mapping.was_clamped
            and not mapping.invalid_reason
        ),
        projection_max_edge_drift_px=mapping.projection.max_edge_drift_px,
        projection_was_clamped=mapping.projection.was_clamped,
        projection_back_projected_bbox=_normalized_payload(
            mapping.projection.back_projected_bbox.x,
            mapping.projection.back_projected_bbox.y,
            mapping.projection.back_projected_bbox.w,
            mapping.projection.back_projected_bbox.h,
        ),
        crop=crop_rel,
        review_image=review_image,
    )


def _invalid_bbox_audit(
    bbox: Any,
    *,
    case_label: str,
    finding: dict[str, Any],
    finding_index: int,
    bbox_index: int,
    review_image: str,
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    reason = "bbox_not_an_object"
    if isinstance(bbox, dict):
        normalized = {key: bbox.get(key) for key in ("x", "y", "w", "h") if key in bbox}
        try:
            x = float(bbox["x"])
            y = float(bbox["y"])
            w = float(bbox["w"])
            h = float(bbox["h"])
        except (KeyError, TypeError, ValueError):
            reason = "bbox_non_numeric_or_missing_coordinate"
        else:
            if not all(math.isfinite(value) for value in (x, y, w, h)):
                normalized = {}
                reason = "bbox_non_finite_coordinate"
            else:
                normalized = _normalized_payload(x, y, w, h)
                reason = (
                    "bbox_degenerate"
                    if w <= 0.0 or h <= 0.0
                    else "bbox_out_of_bounds_or_subpixel"
                )
    return {
        "audit_type": "bbox",
        "case": case_label,
        "finding_index": finding_index,
        "bbox_index": bbox_index,
        "finding_id": str(finding.get("id") or ""),
        "label": str(finding.get("label") or "finding"),
        "severity": str(finding.get("severity") or ""),
        "normalized": normalized,
        "clamped_normalized": {},
        "pixels": {},
        "width_px": 0,
        "height_px": 0,
        "ink_pixel_ratio": 0.0,
        "low_signal": True,
        "was_clamped": False,
        "invalid_reason": reason,
        "projection_ok": False,
        "projection_max_edge_drift_px": 0.0,
        "projection_was_clamped": False,
        "projection_back_projected_bbox": {},
        "crop": "",
        "review_image": review_image,
    }


def _project_bbox_for_review(
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    width: int,
    height: int,
) -> BboxProjectionCalibration:
    return project_bbox_to_overlay_highlight(
        bbox=RegionRect(
            x=_clamp(x),
            y=_clamp(y),
            w=_clamp(w),
            h=_clamp(h),
        ),
        image_rect=WindowRect(left=0, top=0, width=width, height=height),
        dpr=1.0,
        severity="info",
        label="review",
    ).calibration


def _save_bbox_crop(
    source: Image.Image,
    box: tuple[int, int, int, int],
    crops_dir: Path,
    filename: str,
) -> Path:
    crop = source.crop(box)
    longest_edge = max(crop.width, crop.height)
    if longest_edge and longest_edge < _CROP_THUMBNAIL_MIN_EDGE:
        scale = _CROP_THUMBNAIL_MIN_EDGE / longest_edge
        crop = crop.resize(
            (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
            Image.Resampling.NEAREST,
        )
    path = crops_dir / filename
    crop.save(path)
    return path


def _relative_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _draw_low_signal_marker(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
) -> None:
    x0, y0, x1, y1 = box
    draw.rectangle((x0, y0, x1, y1), outline=_LOW_SIGNAL, width=1)
    draw.line((x0, y0, x1, y1), fill=_LOW_SIGNAL, width=2)
    draw.line((x1, y0, x0, y1), fill=_LOW_SIGNAL, width=2)


def _draw_panel(
    draw: ImageDraw.ImageDraw,
    result: dict[str, Any],
    findings: list[dict[str, Any]],
    image_width: int,
    image_height: int,
    font: PillowFont,
    small: PillowFont,
    title_font: PillowFont,
    audits_by_finding: dict[int, list[BboxAudit]],
) -> None:
    x = image_width
    draw.rectangle((x, 0, x + _PANEL_WIDTH, image_height), fill=_PANEL_BG)
    cursor = _MARGIN
    case_label = str(result.get("case") or "case")
    severity = str(result.get("severity") or "unknown")
    cursor = _draw_wrapped(
        draw,
        (x + _MARGIN, cursor),
        f"{case_label}  [{severity}]",
        title_font,
        _TEXT,
        42,
    )
    summary = str(result.get("summary") or "(no summary)")
    cursor = _draw_wrapped(
        draw,
        (x + _MARGIN, cursor + 6),
        f"Summary: {summary}",
        font,
        _TEXT,
        56,
    )
    cursor += 4
    for idx, finding in enumerate(findings[:12], start=1):
        label = str(finding.get("label") or "finding")
        sev = str(finding.get("severity") or severity)
        regions = ", ".join(str(r) for r in finding.get("regions") or [])
        detail = str(finding.get("detail") or "")
        source_name = str(finding.get("source") or "")
        color = _color_for(sev)
        _draw_badge(draw, x + _MARGIN, cursor + 1, str(idx), color, small)
        text_x = x + _MARGIN + 28
        cursor = _draw_wrapped(
            draw,
            (text_x, cursor),
            f"{label} [{sev}]",
            font,
            _TEXT,
            48,
        )
        if regions:
            cursor = _draw_wrapped(
                draw,
                (text_x, cursor),
                f"Regions: {regions}",
                small,
                _MUTED,
                54,
            )
        if source_name:
            cursor = _draw_wrapped(
                draw,
                (text_x, cursor),
                f"Source: {source_name}",
                small,
                _MUTED,
                54,
            )
        if detail:
            cursor = _draw_wrapped(
                draw,
                (text_x, cursor),
                detail,
                small,
                _TEXT,
                54,
            )
        for audit in audits_by_finding.get(idx, []):
            pixels = audit.pixels
            status = "LOW-SIGNAL" if audit.low_signal else "signal"
            fill = _LOW_SIGNAL if audit.low_signal else _MUTED
            cursor = _draw_wrapped(
                draw,
                (text_x, cursor),
                (
                    f"Box {audit.bbox_index}: px "
                    f"{pixels['x0']},{pixels['y0']}-{pixels['x1']},{pixels['y1']}; "
                    f"ink {audit.ink_pixel_ratio:.1%}; {status}"
                ),
                small,
                fill,
                54,
            )
        cursor += 6
        if cursor > image_height - 42:
            remaining = len(findings) - idx
            if remaining > 0:
                _draw_text(
                    draw,
                    (x + _MARGIN, cursor),
                    f"... {remaining} more findings in JSON",
                    small,
                    _MUTED,
                )
            break


def _draw_badge(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    color: tuple[int, int, int],
    font: PillowFont,
) -> None:
    draw.rounded_rectangle((x, y, x + 22, y + 18), radius=4, fill=color)
    _draw_text(draw, (x + 7, y + 2), text[:2], font, (255, 255, 255))


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: PillowFont,
    fill: tuple[int, int, int],
    width_chars: int,
) -> int:
    x, y = xy
    lines = textwrap.wrap(text, width=width_chars) or [""]
    for line in lines:
        _draw_text(draw, (x, y), line, font, fill)
        y += _line_height(font) + _LINE_SPACING
    return y


def _draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: PillowFont,
    fill: tuple[int, int, int],
) -> None:
    try:
        draw.text(xy, text, fill=fill, font=font)
    except UnicodeEncodeError:
        safe = text.encode("ascii", errors="replace").decode("ascii")
        draw.text(xy, safe, fill=fill, font=font)


def _write_index(output_dir: Path, exported: list[ExportedAnnotation]) -> None:
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(item.case_label)}</td>"
        f'<td><a href="{escape(item.output_path.name)}">'
        f"{escape(item.output_path.name)}</a></td>"
        f"<td>{escape(str(item.result_path))}</td>"
        "</tr>"
        for item in exported
    )
    html = (
        '<!doctype html><html><head><meta charset="utf-8">'
        "<title>Eval Annotation Review</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px}"
        "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px}"
        "</style></head><body>"
        "<h1>Eval Annotation Review</h1>"
        "<table><thead><tr><th>Case</th><th>Annotated PNG</th>"
        "<th>Raw Result</th></tr></thead><tbody>"
        f"{rows}</tbody></table>"
        '<p><a href="bbox-audit.jsonl">bbox-audit.jsonl</a> stores pixel '
        "coordinates, crop paths, and low-signal flags for every box.</p>"
        "</body></html>"
    )
    (output_dir / "index.html").write_text(html, encoding="utf-8")


def _write_bbox_audit(output_dir: Path, audit_records: list[Any]) -> None:
    lines = [
        json.dumps(
            record.to_json() if isinstance(record, BboxAudit) else record,
            ensure_ascii=False,
            sort_keys=True,
        )
        for record in audit_records
    ]
    text = "\n".join(lines)
    if text:
        text += "\n"
    (output_dir / "bbox-audit.jsonl").write_text(text, encoding="utf-8")


def _load_font(size: int) -> PillowFont:
    for candidate in (
        Path("C:/Windows/Fonts/msjh.ttc"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _line_height(font: PillowFont) -> int:
    bbox = font.getbbox("Ag")
    return bbox[3] - bbox[1]


def _color_for(severity: str) -> tuple[int, int, int]:
    return _COLORS.get(severity.lower(), _COLORS["info"])


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _normalized_payload(x: float, y: float, w: float, h: float) -> dict[str, float]:
    return {
        "x": round(x, 6),
        "y": round(y, 6),
        "w": round(w, 6),
        "h": round(h, 6),
    }


def _clamp_reason(x: float, y: float, w: float, h: float) -> str:
    if any(value < 0.0 or value > 1.0 for value in (x, y, w, h)):
        return "value_out_of_bounds"
    if x + w > 1.0 or y + h > 1.0:
        return "extent_out_of_bounds"
    return ""


def _safe_filename(value: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in value)
    return safe or "case"
