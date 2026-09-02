"""Deterministic, PHI-minimizing ECG image variants for robustness evaluation."""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from dicom_overlay.application.interpretation_harness import (
    PARTIAL_ECG_VISIBLE_PIXELS_SCOPE,
)

VARIANT_NAMES = (
    "crop_top_20",
    "crop_bottom_20",
    "crop_left_20",
    "crop_right_20",
    "crop_vertical_middle_50",
    "mask_labels_left_12",
    "crop_horizontal_band_06_of_12",
    "tiny_short_edge_48px",
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TRANSFORM_VERSION = 2
PARTIAL_INPUT_SCHEMA_VERSION = 2
PARTIAL_CORPUS_SCHEMA_VERSION = 2
PARTIAL_CORPUS_KIND = "phi_free_incomplete_ecg_variant_corpus"
EKG_NAMED_REGIONS = (
    "lead_I",
    "lead_II",
    "lead_III",
    "lead_aVR",
    "lead_aVL",
    "lead_aVF",
    "lead_V1",
    "lead_V2",
    "lead_V3",
    "lead_V4",
    "lead_V5",
    "lead_V6",
    "rhythm_strip",
)
EKG_CHECKLIST_AXES = (
    "heart_rate",
    "rhythm",
    "regularity",
    "axis",
    "p_wave",
    "pr_interval",
    "qrs_duration",
    "qrs_morphology",
    "st_segment",
    "t_wave",
    "qtc_interval",
    "chamber_enlargement",
    "conduction",
    "av_block",
    "stemi_pattern",
    "ischemia",
)
_MULTILEAD_CONTEXT_AXES = (
    "axis",
    "qrs_morphology",
    "st_segment",
    "t_wave",
    "chamber_enlargement",
    "conduction",
    "stemi_pattern",
    "ischemia",
)
_ANSWER_FIELDS = frozenset(
    {
        "answer",
        "answers",
        "concepts",
        "diagnosis",
        "diagnoses",
        "expected_severity",
        "expected_keywords",
        "gold",
        "ground_truth",
        "keywords",
        "negatives",
        "report",
        "target_axes",
        "cant_miss",
        "urgent_concerns",
        "uncertain_concepts",
        "ungradable_reasons",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "transform_version",
        "kind",
        "answer_free",
        "source_policy",
        "source_count",
        "variants_per_source",
        "variant_count",
        "case_count",
        "variants",
        "cases",
        "manifest_sha256",
    }
)
_VARIANT_RECORD_KEYS = frozenset(
    {
        "source_id",
        "source_sha256",
        "source_size_px",
        "variant",
        "image",
        "variant_sha256",
        "variant_size_px",
        "transform",
    }
)
_CASE_KEYS = frozenset(
    {
        "image",
        "modality",
        "label",
        "label_status",
        "source",
        "valid_regions",
        "partial_input",
    }
)
_PARTIAL_INPUT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "source_id",
        "source_sha256",
        "source_size_px",
        "variant",
        "variant_sha256",
        "variant_size_px",
        "transform_version",
        "transform",
        "expected_visibility",
        "required_output",
    }
)
_LIMITATION_CLASS_BY_VARIANT = {
    "crop_top_20": "top_edge_cropped",
    "crop_bottom_20": "bottom_edge_cropped",
    "crop_left_20": "left_edge_cropped",
    "crop_right_20": "right_edge_cropped",
    "crop_vertical_middle_50": "central_horizontal_band_only",
    "mask_labels_left_12": "left_labels_masked",
    "crop_horizontal_band_06_of_12": "narrow_horizontal_band_only",
    "tiny_short_edge_48px": "low_resolution_downsample",
}
_LIMITATION_PATTERNS = {
    "top_edge_cropped": (
        re.compile(
            r"(?:\b(?:top|upper)\b|上方|頂部).{0,48}"
            r"(?:crop|cut[ -]?off|truncat|missing|absent|裁切|截斷|缺失)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:crop|cut[ -]?off|truncat|missing|absent|裁切|截斷|缺失)"
            r".{0,48}(?:\b(?:top|upper)\b|上方|頂部)",
            re.IGNORECASE,
        ),
    ),
    "bottom_edge_cropped": (
        re.compile(
            r"(?:\b(?:bottom|lower)\b|下方|底部).{0,48}"
            r"(?:crop|cut[ -]?off|truncat|missing|absent|裁切|截斷|缺失)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:crop|cut[ -]?off|truncat|missing|absent|裁切|截斷|缺失)"
            r".{0,48}(?:\b(?:bottom|lower)\b|下方|底部)",
            re.IGNORECASE,
        ),
    ),
    "left_edge_cropped": (
        re.compile(
            r"(?:\bleft\b|左側|左邊).{0,48}"
            r"(?:crop|cut[ -]?off|truncat|missing|absent|裁切|截斷|缺失)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:crop|cut[ -]?off|truncat|missing|absent|裁切|截斷|缺失)"
            r".{0,48}(?:\bleft\b|左側|左邊)",
            re.IGNORECASE,
        ),
    ),
    "right_edge_cropped": (
        re.compile(
            r"(?:\bright\b|右側|右邊).{0,48}"
            r"(?:crop|cut[ -]?off|truncat|missing|absent|裁切|截斷|缺失)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:crop|cut[ -]?off|truncat|missing|absent|裁切|截斷|缺失)"
            r".{0,48}(?:\bright\b|右側|右邊)",
            re.IGNORECASE,
        ),
    ),
    "central_horizontal_band_only": (
        re.compile(
            r"(?:\b(?:central|middle)\b|中央|中間).{0,48}"
            r"(?:horizontal[ -]?)?(?:band|strip|section|帶|區段)",
            re.IGNORECASE,
        ),
    ),
    "left_labels_masked": (
        re.compile(
            r"(?:label|identifier|標籤|標示|導程名稱).{0,48}"
            r"(?:mask|obscur|hidden|unreadable|unavailable|遮蔽|無法辨識|不可見)",
            re.IGNORECASE,
        ),
    ),
    "narrow_horizontal_band_only": (
        re.compile(
            r"(?:\b(?:narrow|isolated)\b|狹窄|孤立|單一).{0,48}"
            r"(?:horizontal[ -]?)?(?:band|strip|帶|區段)",
            re.IGNORECASE,
        ),
    ),
    "low_resolution_downsample": (
        re.compile(
            r"(?:low|reduced)[ -]?resolution|downsampl|pixelat|"
            r"(?:48\s*(?:px|pixels?))|低解析|降採樣|像素化",
            re.IGNORECASE,
        ),
    ),
}
_NAMED_EKG_REGION_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:"
    r"leads?[\s_:-]*(?:iii|ii|i|avr|avl|avf|v[1-6])|"
    r"(?:lead[\s_:-]*)?(?:avr|avl|avf|v[1-6])|"
    r"rhythm[\s_-]*strip"
    r")(?![a-z0-9])",
    re.IGNORECASE,
)
_FULL_LAYOUT_DESCRIPTOR = re.compile(
    r"\b(?:full|complete|standard)\s+(?:12[\s_-]*lead|lead)"
    r"(?:\s+(?:ECG|EKG|tracing|layout|inventory|context))?\b|"
    r"\b12[\s_-]*lead[\s_-]*(?:3x4(?:[\s_-]*rhythm)?|12x1)\b",
    re.IGNORECASE,
)
_FULL_LAYOUT_NEGATED_BEFORE = re.compile(
    r"(?:\bno\b|\bnot\s+(?:a|the)\b|\bwithout\b|"
    r"\bcannot\s+(?:confirm|verify)\b|\bunable\s+to\s+verify\b)\s*$",
    re.IGNORECASE,
)
_FULL_LAYOUT_NEGATED_AFTER = re.compile(
    r"^\s*(?:(?:is|was|remains?)\s+)?not\s+"
    r"(?:available|verified|visible|present|intact|readable|assessable)\b|"
    r"^\s*(?:(?:is|was|remains?)\s+)?"
    r"(?:unavailable|unverified|incomplete|missing|absent|unknown)\b|"
    r"^\s*(?:cannot|can\s+not|can't)\s+(?:be\s+)?"
    r"(?:confirmed|verified|seen|assessed)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EkgImageVariant:
    """One encoded PNG plus auditable pixel-space provenance."""

    name: str
    png_bytes: bytes
    width: int
    height: int
    transform: dict[str, Any]


@dataclass(frozen=True)
class PartialEcgInputContract:
    """Validated answer-free contract for one deliberately degraded ECG."""

    source_id: str
    source_sha256: str
    source_size_px: tuple[int, int]
    variant: str
    variant_sha256: str
    variant_size_px: tuple[int, int]
    transform_version: int
    transform: dict[str, Any]
    expected_visibility: dict[str, Any]
    required_output: dict[str, Any]

    @property
    def analysis_regions(self) -> tuple[str, ...]:
        return tuple(self.expected_visibility["analysis_scope_regions"])

    @property
    def claimable_regions(self) -> tuple[str, ...]:
        return tuple(self.expected_visibility["claimable_regions"])

    @property
    def non_claimable_regions(self) -> tuple[str, ...]:
        return tuple(self.expected_visibility["invisible_or_unverified_regions"])

    @property
    def context_dependent_axes(self) -> tuple[str, ...]:
        return tuple(self.expected_visibility["context_dependent_axes"])

    @property
    def limitation_class(self) -> str:
        """Non-clinical transform class the model must recognize from pixels."""

        return str(self.expected_visibility["limitation_class"])

    def to_manifest_payload(self) -> dict[str, Any]:
        return {
            "schema_version": PARTIAL_INPUT_SCHEMA_VERSION,
            "kind": "deliberately_incomplete_ecg",
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "source_size_px": list(self.source_size_px),
            "variant": self.variant,
            "variant_sha256": self.variant_sha256,
            "variant_size_px": list(self.variant_size_px),
            "transform_version": self.transform_version,
            "transform": dict(self.transform),
            "expected_visibility": dict(self.expected_visibility),
            "required_output": dict(self.required_output),
        }


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def is_partial_ecg_corpus_manifest(value: object) -> bool:
    """Detect partial ECG manifests, including malformed roots, for fail-closed use."""

    if not isinstance(value, dict):
        return False
    if value.get("kind") == PARTIAL_CORPUS_KIND:
        return True
    cases = value.get("cases")
    return bool(
        isinstance(cases, list)
        and any(isinstance(case, dict) and "partial_input" in case for case in cases)
    )


def partial_ecg_text_leaves(*values: object) -> tuple[str, ...]:
    """Flatten only caller-selected presentation values into auditable text leaves."""

    leaves: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, str):
            if value.strip():
                leaves.append(value.strip())
            return
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
            return
        if isinstance(value, list | tuple):
            for item in value:
                visit(item)

    for value in values:
        visit(value)
    return tuple(leaves)


def partial_ecg_text_claim_failures(texts: tuple[str, ...]) -> list[str]:
    """Reject named-region and positive full-layout claims in partial ECG prose."""

    failures: list[str] = []
    named_claims = sorted(
        {
            match.group(0)
            for text in texts
            for match in _NAMED_EKG_REGION_PATTERN.finditer(text)
        },
        key=str.casefold,
    )
    if named_claims:
        failures.append(
            "partial ECG text asserts unverified named regions: "
            + ", ".join(named_claims)
        )
    if any(_has_unnegated_full_layout_claim(text) for text in texts):
        failures.append("partial ECG text asserts an unverified full lead layout")
    return failures


def partial_ecg_limitation_class_supported(
    limitation_class: str,
    texts: tuple[str, ...],
) -> bool:
    """Require exactly one, transform-matching blind degradation description."""

    if limitation_class not in _LIMITATION_PATTERNS:
        return False
    matched_classes = {
        candidate
        for candidate, patterns in _LIMITATION_PATTERNS.items()
        if any(pattern.search(text) for pattern in patterns for text in texts)
    }
    return matched_classes == {limitation_class}


def partial_ecg_axis_value_is_safe(value: object, status: object) -> bool:
    """Enforce not-assessable-or-abnormal semantics without status-only bypasses."""

    normalized_status = str(status or "").strip().casefold()
    normalized_value = re.sub(
        r"[^a-z0-9]+",
        "_",
        str(value or "").casefold(),
    ).strip("_")
    if normalized_status == "info":
        return any(
            marker in normalized_value for marker in _PARTIAL_UNASSESSABLE_MARKERS
        )
    if normalized_status not in {"warning", "critical"} or not normalized_value:
        return False
    return not _is_normal_value(normalized_value) and any(
        marker in normalized_value for marker in _PARTIAL_ABNORMAL_VALUE_MARKERS
    )


_PARTIAL_UNASSESSABLE_MARKERS = (
    "not_assessable",
    "not_assessed",
    "indeterminate",
    "unknown",
    "unavailable",
    "cannot_assess",
    "unable_to_assess",
)
_PARTIAL_NORMAL_VALUE_MARKERS = frozenset(
    {
        "normal",
        "within_normal_limits",
        "within_normal_range",
        "wnl",
        "unremarkable",
        "no_abnormality",
        "no_abnormalities",
        "negative",
        "none",
        "normal_sinus_rhythm",
        "sinus_rhythm",
        "regular",
        "normal_rate",
        "normal_axis",
        "no_stemi",
        "no_ischemia",
        "no_block",
        "no_hypertrophy",
        "no_enlargement",
        "narrow_qrs",
        "normal_qtc",
    }
)
_PARTIAL_ABNORMAL_VALUE_MARKERS = (
    "abnormal",
    "elevat",
    "depress",
    "inver",
    "prolong",
    "shorten",
    "wide",
    "block",
    "delay",
    "deviat",
    "leftward",
    "rightward",
    "irregular",
    "tachy",
    "brady",
    "fibrillat",
    "flutter",
    "ectop",
    "premature",
    "escape",
    "paced",
    "ischemi",
    "infarct",
    "stemi",
    "hypertroph",
    "enlarg",
    "patholog",
    "poor",
    "discord",
    "absent",
    "missing",
    "non_sinus",
    "low_voltage",
    "high_voltage",
    "fragment",
    "notch",
)


def _is_normal_value(normalized: str) -> bool:
    if normalized in _PARTIAL_NORMAL_VALUE_MARKERS:
        return True
    tokens = set(normalized.split("_"))
    return bool(
        "normal" in tokens
        or "unremarkable" in tokens
        or normalized.startswith("no_abnormal")
    )


def _has_unnegated_full_layout_claim(text: str) -> bool:
    for match in _FULL_LAYOUT_DESCRIPTOR.finditer(text):
        before = text[max(0, match.start() - 48) : match.start()]
        after = text[match.end() : match.end() + 64]
        if _FULL_LAYOUT_NEGATED_BEFORE.search(before):
            continue
        if _FULL_LAYOUT_NEGATED_AFTER.search(after):
            continue
        return True
    return False


def parse_partial_ecg_input_contract(
    entry: dict[str, Any],
    *,
    image_path: Path,
) -> PartialEcgInputContract | None:
    """Validate a partial-ECG case contract and bind it to persisted bytes."""

    raw = entry.get("partial_input")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("partial_input must be an object")
    if entry.get("modality") != "EKG":
        raise ValueError("partial_input is only valid for EKG cases")
    if _contains_answer_field(entry):
        raise ValueError("partial ECG inference cases must remain answer-free")
    if set(entry) != _CASE_KEYS:
        raise ValueError("partial ECG case keys do not match the closed allow-list")
    if "valid_regions" not in entry or entry["valid_regions"] != []:
        raise ValueError(
            "geometry-only partial ECG cases require explicit valid_regions=[]"
        )
    if set(raw) != _PARTIAL_INPUT_KEYS:
        raise ValueError("partial_input keys do not match the frozen contract")
    if (
        raw.get("schema_version") != PARTIAL_INPUT_SCHEMA_VERSION
        or raw.get("kind") != "deliberately_incomplete_ecg"
        or raw.get("transform_version") != TRANSFORM_VERSION
        or raw.get("variant") not in VARIANT_NAMES
    ):
        raise ValueError("partial_input version/kind/variant is invalid")
    source_id = raw.get("source_id")
    if not isinstance(source_id, str) or not re.fullmatch(
        r"source-[0-9a-f]{16}", source_id
    ):
        raise ValueError("partial_input source_id must be opaque")
    for field in ("source_sha256", "variant_sha256"):
        if not _is_sha256(raw.get(field)):
            raise ValueError(f"partial_input {field} must be a SHA-256 digest")
    source_size = _parse_size(raw.get("source_size_px"), field="source_size_px")
    variant_size = _parse_size(raw.get("variant_size_px"), field="variant_size_px")
    if source_id != f"source-{raw['source_sha256'][:16]}":
        raise ValueError("partial_input source_id does not match source_sha256")
    expected_filename = f"{source_id}-{raw['variant']}-{raw['variant_sha256'][:12]}.png"
    if entry.get("image") != expected_filename or image_path.name != expected_filename:
        raise ValueError("partial ECG image name is not bound to variant provenance")
    if (
        entry.get("label") != f"partial-{source_id}-{raw['variant']}"
        or entry.get("label_status") != "blinded_inference"
        or entry.get("source") != "deterministic_partial_ecg_variant"
    ):
        raise ValueError("partial ECG case identity contract mismatch")
    if not image_path.is_file():
        raise ValueError(f"partial ECG variant image is missing: {image_path.name}")
    if sha256_bytes(image_path.read_bytes()) != raw["variant_sha256"]:
        raise ValueError("partial_input variant_sha256 does not match image bytes")
    with Image.open(image_path) as variant_image:
        if variant_image.format != "PNG" or variant_image.size != variant_size:
            raise ValueError("partial_input variant_size_px/format mismatch")
    transform = raw.get("transform")
    visibility = raw.get("expected_visibility")
    required_output = raw.get("required_output")
    if not isinstance(transform, dict):
        raise ValueError("partial_input transform must be an object")
    if not isinstance(visibility, dict):
        raise ValueError("partial_input expected_visibility must be an object")
    if not isinstance(required_output, dict):
        raise ValueError("partial_input required_output must be an object")
    expected_transform = _expected_transform_for(
        str(raw["variant"]),
        source_size=source_size,
    )
    if transform != expected_transform:
        raise ValueError("partial_input transform does not match deterministic variant")
    expected_variant_size = _variant_size_for_transform(
        expected_transform,
        source_size=source_size,
    )
    if expected_variant_size != variant_size:
        raise ValueError("partial_input variant dimensions do not match transform")
    _validate_expected_visibility(visibility, variant=str(raw["variant"]))
    if visibility != _expected_visibility_for(
        str(raw["variant"]),
        transform=expected_transform,
        source_size=source_size,
    ):
        raise ValueError("partial_input expected_visibility does not match transform")
    if required_output != _required_partial_output_contract():
        raise ValueError("partial_input required_output contract mismatch")
    return PartialEcgInputContract(
        source_id=source_id,
        source_sha256=str(raw["source_sha256"]),
        source_size_px=source_size,
        variant=str(raw["variant"]),
        variant_sha256=str(raw["variant_sha256"]),
        variant_size_px=variant_size,
        transform_version=TRANSFORM_VERSION,
        transform=dict(transform),
        expected_visibility=dict(visibility),
        required_output=dict(required_output),
    )


def _required_partial_output_contract() -> dict[str, Any]:
    return {
        "incomplete": True,
        "review_required": True,
        "named_region_claims_allowed": False,
        "full_12_lead_layout_allowed": False,
        "context_dependent_axis_policy": "not_assessable_or_abnormal",
        "bbox_receipt_source": "exact_variant_sha256_when_boxes_present",
    }


def _context_dependent_axes(variant_name: str) -> list[str]:
    if variant_name == "tiny_short_edge_48px":
        return list(EKG_CHECKLIST_AXES)
    return list(_MULTILEAD_CONTEXT_AXES)


def _contains_answer_field(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).casefold() in _ANSWER_FIELDS or _contains_answer_field(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_answer_field(item) for item in value)
    return False


def _parse_size(value: object, *, field: str) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(
            not isinstance(item, int) or isinstance(item, bool) or item <= 0
            for item in value
        )
    ):
        raise ValueError(f"partial_input {field} must contain two positive integers")
    return int(value[0]), int(value[1])


def _expected_transform_for(
    variant_name: str,
    *,
    source_size: tuple[int, int],
) -> dict[str, Any]:
    width, height = source_size
    crop_boxes = {
        "crop_top_20": (0, _fraction(height, 0.2), width, height),
        "crop_bottom_20": (0, 0, width, _fraction(height, 0.8)),
        "crop_left_20": (_fraction(width, 0.2), 0, width, height),
        "crop_right_20": (0, 0, _fraction(width, 0.8), height),
        "crop_vertical_middle_50": (
            0,
            _fraction(height, 0.25),
            width,
            _fraction(height, 0.75),
        ),
        "crop_horizontal_band_06_of_12": (
            0,
            math.floor(5 * height / 12),
            width,
            min(
                height, max(math.floor(5 * height / 12) + 1, math.ceil(6 * height / 12))
            ),
        ),
    }
    if variant_name in crop_boxes:
        return {
            "kind": "crop",
            "crop_box_px": list(crop_boxes[variant_name]),
            "source_subset": True,
        }
    if variant_name == "mask_labels_left_12":
        return {
            "kind": "pixel_mask",
            "mask_box_px": [0, 0, max(1, _fraction(width, 0.12)), height],
            "fill_rgb": [255, 255, 255],
            "source_subset": False,
        }
    if variant_name == "tiny_short_edge_48px":
        scale = min(1.0, 48 / min(width, height))
        target_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        return {
            "kind": "downsample",
            "source_size_px": [width, height],
            "target_size_px": list(target_size),
            "resampling": "lanczos",
            "source_subset": False,
        }
    raise ValueError("unknown partial ECG variant")


def _variant_size_for_transform(
    transform: dict[str, Any],
    *,
    source_size: tuple[int, int],
) -> tuple[int, int]:
    if transform["kind"] == "crop":
        x0, y0, x1, y1 = transform["crop_box_px"]
        return x1 - x0, y1 - y0
    if transform["kind"] == "downsample":
        width, height = transform["target_size_px"]
        return width, height
    return source_size


def _expected_visibility_for(
    variant_name: str,
    *,
    transform: dict[str, Any],
    source_size: tuple[int, int],
) -> dict[str, Any]:
    width, height = source_size
    visible_box = [0.0, 0.0, 1.0, 1.0]
    obscured_boxes: list[list[float]] = []
    if transform.get("kind") == "crop":
        x0, y0, x1, y1 = transform["crop_box_px"]
        visible_box = [
            round(x0 / width, 6),
            round(y0 / height, 6),
            round((x1 - x0) / width, 6),
            round((y1 - y0) / height, 6),
        ]
    elif transform.get("kind") == "pixel_mask":
        x0, y0, x1, y1 = transform["mask_box_px"]
        obscured_boxes = [
            [
                round(x0 / width, 6),
                round(y0 / height, 6),
                round((x1 - x0) / width, 6),
                round((y1 - y0) / height, 6),
            ]
        ]
    return {
        "assessment_basis": "deterministic_pixel_transform_only",
        "limitation_class": _LIMITATION_CLASS_BY_VARIANT[variant_name],
        "visible_source_box_normalized": visible_box,
        "obscured_source_boxes_normalized": obscured_boxes,
        "claimable_regions": [],
        "analysis_scope_regions": [PARTIAL_ECG_VISIBLE_PIXELS_SCOPE],
        "invisible_or_unverified_regions": list(EKG_NAMED_REGIONS),
        "context_dependent_axes": _context_dependent_axes(variant_name),
        "full_12_lead_inventory_expected": False,
    }


def _validate_expected_visibility(
    value: dict[str, Any],
    *,
    variant: str,
) -> None:
    required_keys = {
        "assessment_basis",
        "limitation_class",
        "visible_source_box_normalized",
        "obscured_source_boxes_normalized",
        "claimable_regions",
        "analysis_scope_regions",
        "invisible_or_unverified_regions",
        "context_dependent_axes",
        "full_12_lead_inventory_expected",
    }
    if set(value) != required_keys:
        raise ValueError("partial ECG expected_visibility keys are invalid")
    if (
        value.get("assessment_basis") != "deterministic_pixel_transform_only"
        or value.get("limitation_class") != _LIMITATION_CLASS_BY_VARIANT[variant]
        or value.get("claimable_regions") != []
        or value.get("analysis_scope_regions") != [PARTIAL_ECG_VISIBLE_PIXELS_SCOPE]
        or value.get("invisible_or_unverified_regions") != list(EKG_NAMED_REGIONS)
        or value.get("context_dependent_axes") != _context_dependent_axes(variant)
        or value.get("full_12_lead_inventory_expected") is not False
    ):
        raise ValueError("partial ECG expected_visibility policy mismatch")
    visible_box = value.get("visible_source_box_normalized")
    obscured = value.get("obscured_source_boxes_normalized")
    if not _is_normalized_box(visible_box):
        raise ValueError("partial ECG visible source box is invalid")
    if not isinstance(obscured, list) or any(
        not _is_normalized_box(box) for box in obscured
    ):
        raise ValueError("partial ECG obscured source boxes are invalid")


def _is_normalized_box(value: object) -> bool:
    if not isinstance(value, list) or len(value) != 4:
        return False
    if any(
        not isinstance(item, int | float) or isinstance(item, bool) for item in value
    ):
        return False
    x, y, width, height = (float(item) for item in value)
    return bool(
        0.0 <= x <= 1.0
        and 0.0 <= y <= 1.0
        and 0.0 < width <= 1.0
        and 0.0 < height <= 1.0
        and x + width <= 1.0 + 1e-6
        and y + height <= 1.0 + 1e-6
    )


def _is_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def build_ecg_variants(source_png: bytes) -> tuple[EkgImageVariant, ...]:
    """Create fixed robustness variants without widening the source image.

    The source is expected to be an already ROI-cropped, PHI-cleared ECG PNG.
    No OCR, report text, filename, or clinical label is inspected.
    """

    if not source_png.startswith(PNG_SIGNATURE):
        raise ValueError("source ECG must be a PNG image")
    with Image.open(io.BytesIO(source_png)) as opened:
        if opened.format != "PNG" or getattr(opened, "n_frames", 1) != 1:
            raise ValueError("source ECG must be a single-frame PNG image")
        opened.load()
        source = opened.convert("RGB")
    width, height = source.size
    if width < 12 or height < 12:
        raise ValueError("source ECG must be at least 12x12 pixels")

    top = _crop_variant(
        source, "crop_top_20", (0, _fraction(height, 0.2), width, height)
    )
    bottom = _crop_variant(
        source, "crop_bottom_20", (0, 0, width, _fraction(height, 0.8))
    )
    left = _crop_variant(
        source, "crop_left_20", (_fraction(width, 0.2), 0, width, height)
    )
    right = _crop_variant(
        source, "crop_right_20", (0, 0, _fraction(width, 0.8), height)
    )
    middle = _crop_variant(
        source,
        "crop_vertical_middle_50",
        (0, _fraction(height, 0.25), width, _fraction(height, 0.75)),
    )

    mask_width = max(1, _fraction(width, 0.12))
    masked = source.copy()
    masked.paste((255, 255, 255), (0, 0, mask_width, height))
    label_mask = _encode_variant(
        "mask_labels_left_12",
        masked,
        {
            "kind": "pixel_mask",
            "mask_box_px": [0, 0, mask_width, height],
            "fill_rgb": [255, 255, 255],
            "source_subset": False,
        },
    )

    row_index = 5
    row_y0 = math.floor(row_index * height / 12)
    row_y1 = max(row_y0 + 1, math.ceil((row_index + 1) * height / 12))
    horizontal_band = _crop_variant(
        source,
        "crop_horizontal_band_06_of_12",
        (0, row_y0, width, min(height, row_y1)),
    )

    short_edge = min(width, height)
    scale = min(1.0, 48 / short_edge)
    tiny_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    tiny = source.resize(tiny_size, Image.Resampling.LANCZOS)
    tiny_variant = _encode_variant(
        "tiny_short_edge_48px",
        tiny,
        {
            "kind": "downsample",
            "source_size_px": [width, height],
            "target_size_px": list(tiny_size),
            "resampling": "lanczos",
            "source_subset": False,
        },
    )
    variants = (
        top,
        bottom,
        left,
        right,
        middle,
        label_mask,
        horizontal_band,
        tiny_variant,
    )
    assert tuple(item.name for item in variants) == VARIANT_NAMES
    return variants


def build_variant_corpus(source_paths: list[Path], output_dir: Path) -> dict[str, Any]:
    """Write an answer-free corpus and manifest in stable source-hash order."""

    if not source_paths:
        raise ValueError("at least one source ECG is required")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory must be empty to prevent stale variants")
    sources = []
    for path in source_paths:
        payload = path.read_bytes()
        sources.append((sha256_bytes(payload), payload))
    if len({digest for digest, _payload in sources}) != len(sources):
        raise ValueError("duplicate source image content is not allowed")

    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    for source_digest, source_png in sorted(sources):
        with Image.open(io.BytesIO(source_png)) as source_image:
            source_size = list(source_image.size)
        opaque_source_id = f"source-{source_digest[:16]}"
        for variant in build_ecg_variants(source_png):
            variant_digest = sha256_bytes(variant.png_bytes)
            filename = f"{opaque_source_id}-{variant.name}-{variant_digest[:12]}.png"
            (output_dir / filename).write_bytes(variant.png_bytes)
            records.append(
                {
                    "source_id": opaque_source_id,
                    "source_sha256": source_digest,
                    "source_size_px": source_size,
                    "variant": variant.name,
                    "image": filename,
                    "variant_sha256": variant_digest,
                    "variant_size_px": [variant.width, variant.height],
                    "transform": variant.transform,
                }
            )
            contract = PartialEcgInputContract(
                source_id=opaque_source_id,
                source_sha256=source_digest,
                source_size_px=(source_size[0], source_size[1]),
                variant=variant.name,
                variant_sha256=variant_digest,
                variant_size_px=(variant.width, variant.height),
                transform_version=TRANSFORM_VERSION,
                transform=dict(variant.transform),
                expected_visibility=_expected_visibility_for(
                    variant.name,
                    transform=variant.transform,
                    source_size=(source_size[0], source_size[1]),
                ),
                required_output=_required_partial_output_contract(),
            )
            cases.append(
                {
                    "image": filename,
                    "modality": "EKG",
                    "label": f"partial-{opaque_source_id}-{variant.name}",
                    "label_status": "blinded_inference",
                    "source": "deterministic_partial_ecg_variant",
                    # Empty is deliberate. The runtime uses the non-clinical
                    # analysis scope token recorded inside partial_input; it
                    # must never silently expand this to all 12 named leads.
                    "valid_regions": [],
                    "partial_input": contract.to_manifest_payload(),
                }
            )

    manifest: dict[str, Any] = {
        "schema_version": PARTIAL_CORPUS_SCHEMA_VERSION,
        "transform_version": TRANSFORM_VERSION,
        "kind": PARTIAL_CORPUS_KIND,
        "answer_free": True,
        "source_policy": "already_roi_cropped_phi_cleared_png",
        "source_count": len(sources),
        "variants_per_source": len(VARIANT_NAMES),
        "variant_count": len(records),
        "case_count": len(cases),
        "variants": records,
        "cases": cases,
    }
    manifest["manifest_sha256"] = sha256_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def verify_variant_corpus(output_dir: Path) -> dict[str, Any]:
    """Fail closed unless a persisted corpus exactly matches its manifest."""

    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("variant corpus manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("variant corpus manifest must be an object")
    if _contains_answer_field(manifest):
        raise ValueError("variant corpus manifest must remain recursively answer-free")
    if set(manifest) != _MANIFEST_KEYS:
        raise ValueError("variant corpus root keys do not match the closed allow-list")
    expected_digest = str(manifest.get("manifest_sha256", ""))
    digest_payload = dict(manifest)
    digest_payload.pop("manifest_sha256", None)
    actual_digest = sha256_bytes(
        json.dumps(
            digest_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if expected_digest != actual_digest:
        raise ValueError("variant corpus manifest digest mismatch")
    if (
        manifest.get("schema_version") != PARTIAL_CORPUS_SCHEMA_VERSION
        or manifest.get("transform_version") != TRANSFORM_VERSION
        or manifest.get("kind") != PARTIAL_CORPUS_KIND
        or manifest.get("answer_free") is not True
        or manifest.get("source_policy") != "already_roi_cropped_phi_cleared_png"
        or manifest.get("variants_per_source") != len(VARIANT_NAMES)
    ):
        raise ValueError("variant corpus contract mismatch")
    source_count = manifest.get("source_count")
    if not _is_positive_int(source_count):
        raise ValueError("variant corpus source_count must be a positive integer")

    records = manifest.get("variants")
    if (
        not isinstance(records, list)
        or manifest.get("variant_count") != len(records)
        or len(records) != source_count * len(VARIANT_NAMES)
    ):
        raise ValueError("variant corpus record count mismatch")
    cases = manifest.get("cases")
    if (
        not isinstance(cases, list)
        or manifest.get("case_count") != len(cases)
        or len(cases) != len(records)
    ):
        raise ValueError("variant corpus eval case count mismatch")
    expected_files = {"manifest.json"}
    variants_by_source: dict[str, list[str]] = {}
    records_by_image: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("variant corpus record must be an object")
        if _contains_answer_field(record):
            raise ValueError("variant corpus record must remain answer-free")
        if set(record) != _VARIANT_RECORD_KEYS:
            raise ValueError(
                "variant corpus record keys do not match the closed allow-list"
            )
        source_id = record.get("source_id")
        source_sha256 = record.get("source_sha256")
        variant_sha256 = record.get("variant_sha256")
        variant_name = record.get("variant")
        if (
            not isinstance(source_id, str)
            or not re.fullmatch(r"source-[0-9a-f]{16}", source_id)
            or not _is_sha256(source_sha256)
            or source_id != f"source-{source_sha256[:16]}"
            or not _is_sha256(variant_sha256)
            or variant_name not in VARIANT_NAMES
        ):
            raise ValueError("variant corpus record identity is invalid")
        source_size = _parse_size(
            record.get("source_size_px"), field="record source_size_px"
        )
        variant_size = _parse_size(
            record.get("variant_size_px"), field="record variant_size_px"
        )
        expected_transform = _expected_transform_for(
            str(variant_name),
            source_size=source_size,
        )
        if record.get(
            "transform"
        ) != expected_transform or variant_size != _variant_size_for_transform(
            expected_transform,
            source_size=source_size,
        ):
            raise ValueError("variant corpus record transform is invalid")
        filename = str(record.get("image", ""))
        expected_filename = f"{source_id}-{variant_name}-{variant_sha256[:12]}.png"
        if (
            not filename
            or Path(filename).name != filename
            or filename != expected_filename
        ):
            raise ValueError("variant corpus image path must be a safe basename")
        image_path = output_dir / filename
        if not image_path.is_file():
            raise ValueError(f"variant corpus image is missing: {filename}")
        if sha256_bytes(image_path.read_bytes()) != variant_sha256:
            raise ValueError(f"variant corpus image digest mismatch: {filename}")
        with Image.open(image_path) as image:
            if image.format != "PNG" or image.size != variant_size:
                raise ValueError(f"variant corpus image geometry mismatch: {filename}")
        expected_files.add(filename)
        if filename in records_by_image:
            raise ValueError("variant corpus contains duplicate image identity")
        records_by_image[filename] = record
        variants_by_source.setdefault(source_id, []).append(str(variant_name))
    if manifest.get("source_count") != len(variants_by_source):
        raise ValueError("variant corpus source count mismatch")
    if any(tuple(names) != VARIANT_NAMES for names in variants_by_source.values()):
        raise ValueError("variant corpus source does not contain the fixed variant set")
    seen_labels: set[str] = set()
    seen_case_images: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("variant corpus eval case must be an object")
        if _contains_answer_field(case):
            raise ValueError("variant corpus eval case must remain answer-free")
        if set(case) != _CASE_KEYS:
            raise ValueError(
                "variant corpus case keys do not match the closed allow-list"
            )
        label = case.get("label")
        filename = case.get("image")
        if not isinstance(label, str) or not label or label in seen_labels:
            raise ValueError("variant corpus eval case label is invalid or duplicate")
        seen_labels.add(label)
        if not isinstance(filename, str) or filename in seen_case_images:
            raise ValueError("variant corpus eval case image is invalid or duplicate")
        seen_case_images.add(filename)
        record = records_by_image.get(str(filename))
        if record is None:
            raise ValueError("variant corpus eval case lacks a variant record")
        contract = parse_partial_ecg_input_contract(
            case,
            image_path=output_dir / str(filename),
        )
        assert contract is not None
        if (
            contract.source_id != record.get("source_id")
            or contract.source_sha256 != record.get("source_sha256")
            or list(contract.source_size_px) != record.get("source_size_px")
            or contract.variant != record.get("variant")
            or contract.variant_sha256 != record.get("variant_sha256")
            or list(contract.variant_size_px) != record.get("variant_size_px")
            or contract.transform != record.get("transform")
        ):
            raise ValueError("variant corpus eval provenance does not match record")
    if seen_case_images != set(records_by_image):
        raise ValueError("variant corpus cases do not cover each variant exactly once")
    actual_entries = {path.name for path in output_dir.iterdir()}
    if actual_entries != expected_files:
        raise ValueError("variant corpus contains stale or unmanifested files")
    return manifest


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _fraction(value: int, fraction: float) -> int:
    return max(1, min(value - 1, round(value * fraction)))


def _crop_variant(
    source: Image.Image, name: str, box: tuple[int, int, int, int]
) -> EkgImageVariant:
    cropped = source.crop(box)
    return _encode_variant(
        name,
        cropped,
        {
            "kind": "crop",
            "crop_box_px": list(box),
            "source_subset": True,
        },
    )


def _encode_variant(
    name: str, image: Image.Image, transform: dict[str, Any]
) -> EkgImageVariant:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    return EkgImageVariant(
        name=name,
        png_bytes=buffer.getvalue(),
        width=image.width,
        height=image.height,
        transform=transform,
    )
