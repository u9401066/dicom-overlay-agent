"""Public CXR dataset helpers for large evaluation manifests.

The runtime app stays dependency-light: this module uses only stdlib types and
does not import Hugging Face SDKs. Network/download code lives in scripts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode


@dataclass(frozen=True)
class HuggingFaceImageRow:
    """Minimal row metadata needed to build a public CXR eval case."""

    image_url: str
    label: str | int
    row_idx: int


def build_hf_rows_url(
    *,
    dataset_id: str,
    config: str,
    split: str,
    offset: int,
    length: int,
    endpoint: str = "https://datasets-server.huggingface.co",
) -> str:
    """Build a Hugging Face dataset-server rows URL.

    ``HF_ENDPOINT=https://hf-mirror.com`` is supported by mapping it to the
    mirror's ``/datasets-server`` path.
    """
    base = endpoint.rstrip("/")
    if not base.endswith("datasets-server.huggingface.co"):
        base = f"{base}/datasets-server"
    query = urlencode(
        {
            "dataset": dataset_id,
            "config": config,
            "split": split,
            "offset": offset,
            "length": length,
        }
    )
    return f"{base}/rows?{query}"


def build_public_cxr_manifest(
    rows: list[HuggingFaceImageRow],
    *,
    dataset_id: str,
    image_prefix: str,
    min_cases: int,
) -> dict[str, Any]:
    """Convert public CXR rows into the existing eval manifest schema."""
    if len(rows) < min_cases:
        raise ValueError(
            f"public CXR manifest requires at least {min_cases} cases; got {len(rows)}"
        )

    cases = []
    severity_counts: dict[str, int] = {}
    for row in rows:
        label_text = _label_text(row.label)
        severity = _severity_for_label(label_text)
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        filename = f"{image_prefix}/{row.row_idx:06d}.png"
        case: dict[str, Any] = {
            "image": filename,
            "modality": "CXR",
            "expected_severity": severity,
            "label": f"public_cxr_{row.row_idx:06d}",
            "keywords": _keywords_for_label(label_text),
            "target_axes": _target_axes_for_label(label_text),
            "source": "huggingface",
            "source_dataset": dataset_id,
            "source_url": row.image_url,
            "source_label": label_text,
        }
        if severity == "normal":
            case["negatives"] = (
                "no pneumothorax",
                "no effusion",
                "no consolidation",
            )
        cases.append(case)

    return {
        "dataset": "public-cxr",
        "modality": "CXR",
        "source": {
            "type": "huggingface",
            "dataset_id": dataset_id,
            "note": (
                "Public CXR classification set used for transport/schema/bbox "
                "and report artifact validation. Clinical accuracy remains "
                "model-dependent and must be reviewed separately."
            ),
        },
        "counts": {
            "cases": len(cases),
            "by_severity": severity_counts,
        },
        "cases": cases,
    }


def _label_text(label: str | int) -> str:
    if isinstance(label, int):
        return "NORMAL" if label == 0 else "PNEUMONIA"
    return label.strip() or "UNKNOWN"


def _severity_for_label(label: str) -> str:
    lowered = label.lower()
    if "normal" in lowered or lowered in {"0", "negative"}:
        return "normal"
    return "warning"


def _keywords_for_label(label: str) -> list[str]:
    lowered = label.lower()
    if "normal" in lowered or lowered in {"0", "negative"}:
        return ["clear", "no acute", "normal"]
    if "pneumonia" in lowered:
        return ["pneumonia", "opacity", "consolidation"]
    return [lowered.replace("_", " ")]


def _target_axes_for_label(label: str) -> list[str]:
    lowered = label.lower()
    if "normal" in lowered or lowered in {"0", "negative"}:
        return ["lungs", "pleura", "cardiac_silhouette"]
    return ["lungs", "pleura"]
