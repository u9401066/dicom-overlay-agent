"""Synthetic native tool/Python receipt parity at decimal and ROI boundaries."""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from dicom_overlay.infrastructure.bbox_receipts import canonical_bbox_coordinate
from dicom_overlay.infrastructure.eval_artifact_validator import _bbox_payload_digest
from dicom_overlay.infrastructure.openclaw_client import (
    BboxEvidenceError,
    OpenClawClient,
    _bbox_coordinates_digest,
)
from medical_image_harness.models import (
    AnalysisResult,
    Finding,
    Modality,
    RegionRect,
    Severity,
)

ROOT = Path(__file__).resolve().parents[2]
VECTORS = [
    {"id": f"synthetic-{i}", "x": x, "y": y, "w": w, "h": h}
    for i, (x, y, w, h) in enumerate(
        (x, y, w, h)
        for x in (0.1, 0.25, 0.5)
        for y in (0.1, 0.25, 0.5, 0.8)
        for w, h in ((0.085, 0.07475), (0.07475, 0.085), (0.12345, 0.05675))
    )
]
VECTORS.extend(
    {"id": f"origin-half-{axis}-{index}", "x": 0.1, "y": 0.1,
     "w": 0.01, "h": 0.01, axis: value}
    for axis in ("x", "y")
    for index, value in enumerate((
        math.nextafter(0.00005, 0), 0.00005, math.nextafter(0.00005, 1),
    ))
)
EDGE_VECTORS = [
    {"id": "left", "x": -0.05, "y": 0.2, "w": 0.15, "h": 0.1},
    {"id": "top", "x": 0.2, "y": -0.05, "w": 0.1, "h": 0.15},
    {"id": "right", "x": 0.9, "y": 0.2, "w": 0.15, "h": 0.1},
    {"id": "bottom", "x": 0.2, "y": 0.9, "w": 0.1, "h": 0.15},
    {"id": "outside", "x": 1.1, "y": 0.2, "w": 0.1, "h": 0.1},
    {"id": "broad", "x": 0.1, "y": 0.1, "w": 0.4, "h": 0.1},
    {"id": "round-right", "x": 0.99495, "y": 0.2, "w": 0.00505, "h": 0.01},
    {"id": "round-bottom", "x": 0.2, "y": 0.99495, "w": 0.01, "h": 0.00505},
]


@pytest.fixture(scope="module")
def native_results():
    bundled = ROOT / "node" / ("node.exe" if sys.platform == "win32" else "node")
    executable = str(bundled) if bundled.is_file() else shutil.which("node")
    if executable is None:
        pytest.skip("Native plugin checks require Node.js")
    module_uri = (ROOT / "openclaw/workspace/plugins/dicom-overlay-agent-harness/index.js").as_uri()
    source = f"""
delete process.env.DICOM_BBOX_AUDIT_PATH;
const module = await import({json.dumps(module_uri)});
const tool = module.createBboxValidationTool();
const rows = [];
for (const box of {json.dumps(VECTORS + EDGE_VECTORS)}) {{
  const response = await tool.execute('synthetic', {{
    modality: 'EKG', source_image_sha256: 'a'.repeat(64),
    evidence_nonce: 'b'.repeat(32), boxes: [box]
  }});
  rows.push({{details: response.details,
              digest: module.acceptedBoxesDigest(response.details.accepted)}});
}}
console.log(JSON.stringify(rows));
"""
    result = subprocess.run(
        [executable, "--input-type=module", "--eval", source],
        cwd=ROOT, check=True, capture_output=True, text=True, timeout=30,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("index", range(len(VECTORS)))
def test_unclipped_coordinates_match_exact_python_receipt(index, native_results):
    vector = VECTORS[index]
    coordinates = RegionRect(**{key: vector[key] for key in ("x", "y", "w", "h")})
    result = native_results[index]
    assert result["details"]["rejected"] == []
    assert result["details"]["accepted"][0]["clipped"] is False
    assert result["digest"] == _bbox_coordinates_digest([coordinates])
    payload_digest, count = _bbox_payload_digest([
        {"bboxes": [{key: vector[key] for key in ("x", "y", "w", "h")}]}
    ])
    assert count == 1
    assert payload_digest == result["digest"]


@pytest.mark.parametrize("index", range(4))
def test_real_clipping_stays_contained_and_is_not_silently_disabled(index, native_results):
    result = native_results[len(VECTORS) + index]
    assert result["details"]["rejected"] == []
    accepted = result["details"]["accepted"][0]
    assert accepted["clipped"] is True
    box = accepted["box"]
    assert 0 <= box["x"] < box["x"] + box["w"] <= 1
    assert 0 <= box["y"] < box["y"] + box["h"] <= 1


@pytest.mark.parametrize("index,reason", [
    (4, "too_small_after_clipping"), (5, "ekg_box_too_broad"),
    (6, "rounded_box_out_of_bounds"), (7, "rounded_box_out_of_bounds"),
])
def test_invalid_or_quantized_overflow_box_fails_closed(index, reason, native_results):
    details = native_results[len(VECTORS) + index]["details"]
    assert details["accepted"] == []
    assert details["rejected"][0]["reason"] == reason


def test_finalization_accepts_exact_native_receipt_without_relaxing_geometry(tmp_path, native_results):
    raw = VECTORS[3]
    original = RegionRect(**{key: raw[key] for key in ("x", "y", "w", "h")})
    accepted = RegionRect(**native_results[3]["details"]["accepted"][0]["box"])

    def result(box):
        return AnalysisResult(
            modality=Modality.EKG, summary="Synthetic fixture", severity=Severity.INFO,
            findings=[Finding(id="f1", regions=[], label="Synthetic morphology",
                              detail="Test only", severity=Severity.INFO, bboxes=[box])],
            checklist={},
        )

    client = OpenClawClient(gateway_token="test-token", base_dir=tmp_path)
    client._refresh_tool_audit = lambda: None
    client._last_tool_audit_records = [{
        "tool": "dicom_bbox_validate", "accepted_count": 1,
        "accepted_boxes_sha256": native_results[3]["digest"],
    }]
    locked = client._lock_finalization_geometry(result(original), result(accepted))
    assert locked.findings[0].bboxes == [original]
    assert locked.analysis_trace[-1]["digest_tolerance_applied"] is False
    client._last_tool_audit_records[0]["accepted_boxes_sha256"] = "c" * 64
    with pytest.raises(BboxEvidenceError):
        client._lock_finalization_geometry(result(original), result(accepted))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 1e308])
def test_nonfinite_receipt_coordinate_is_rejected(value):
    with pytest.raises(ValueError):
        canonical_bbox_coordinate(value)
    _digest, count = _bbox_payload_digest([
        {"bboxes": [{"x": value, "y": 0.1, "w": 0.1, "h": 0.1}]}
    ])
    assert count == 0


def test_all_four_decimal_half_ties_and_adjacent_floats_match_javascript():
    bundled = ROOT / "node" / ("node.exe" if sys.platform == "win32" else "node")
    executable = str(bundled) if bundled.is_file() else shutil.which("node")
    if executable is None:
        pytest.skip("Native coordinate checks require Node.js")
    values = [
        value
        for index in range(10_000)
        for midpoint in [(index + 0.5) / 10_000]
        for value in (math.nextafter(midpoint, 0), midpoint, math.nextafter(midpoint, 1))
    ]
    source = """
import { readFileSync } from 'node:fs';
const values = JSON.parse(readFileSync(0, 'utf8'));
console.log(JSON.stringify(values.map(v => (Math.round(v * 10000) / 10000).toFixed(4))));
"""
    completed = subprocess.run(
        [executable, "--input-type=module", "--eval", source],
        input=json.dumps(values), capture_output=True, text=True, check=True, timeout=30,
    )
    expected = json.loads(completed.stdout)
    mismatches = [
        (value, native, canonical_bbox_coordinate(value))
        for value, native in zip(values, expected, strict=True)
        if canonical_bbox_coordinate(value) != native
    ]
    assert not mismatches[:5]
