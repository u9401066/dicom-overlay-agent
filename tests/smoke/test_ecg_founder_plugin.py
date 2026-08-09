from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from dicom_overlay.infrastructure.eval_artifact_validator import (
    _valid_ecg_founder_evidence,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = (
    _REPO_ROOT / "openclaw" / "workspace" / "plugins" / "dicom-overlay-agent-harness"
)


def _node_executable() -> str:
    bundled = _REPO_ROOT / "node" / ("node.exe" if sys.platform == "win32" else "node")
    if bundled.exists():
        return str(bundled)
    system = shutil.which("node")
    if system is None:
        pytest.skip("Node.js is required for the native plugin smoke test")
    return system


def _run_node_module(source: str) -> dict[str, object]:
    result = subprocess.run(
        [_node_executable(), "--input-type=module", "--eval", source],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return json.loads(result.stdout)


def _valid_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "ok",
        "model": {
            "id": "PKUDigitalHealth/ECGFounder",
            "revision": "04edac702b61c91face519774ddcc0cd712fef23",
            "checkpoint_sha256": (
                "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997"
            ),
        },
        "input": {
            "source_kind": "raw_waveform",
            "source_sha256": "b" * 64,
            "source_sample_rate_hz": 500,
            "model_sample_rate_hz": 500,
            "model_duration_sec": 10,
            "model_points_per_lead": 5000,
            "lead_names": [
                "I",
                "II",
                "III",
                "aVR",
                "aVL",
                "aVF",
                "V1",
                "V2",
                "V3",
                "V4",
                "V5",
                "V6",
            ],
        },
        "preprocessing": {
            "implementation": "ecgfounder-sidecar",
            "implementation_revision": "test",
            "steps": ["resample_500_hz", "official_filter", "z_score"],
        },
        "calibration": {"status": "uncalibrated"},
        "predictions": [
            {"label": "ATRIAL FIBRILLATION", "probability": 0.91, "threshold": 0.5}
        ],
        "rhythm_measurement": {
            "method": "lead_II_qrs_energy_v1",
            "lead": "II",
            "status": "ok",
            "diagnostic_scope": "rhythm_regularity_only",
            "beat_count": 7,
            "rr_interval_count": 6,
            "rr_intervals_ms": [860, 720, 650, 810, 690, 840],
            "median_rr_ms": 765.0,
            "heart_rate_bpm_from_median_rr": 78.4,
            "rr_cv": 0.11,
            "rr_rmssd_ms": 130.0,
            "rr_range_ms": 210.0,
            "successive_rr_diff_over_80ms_fraction": 0.8,
            "regularity_signal": "irregular",
            "limitations": ["R-peak timing only; not an AF diagnosis."],
        },
        "limitations": ["Research support only"],
    }


def test_ecg_founder_tool_is_optional_and_not_bundled_as_model_weights() -> None:
    plugin_manifest = json.loads(
        (_PLUGIN_ROOT / "openclaw.plugin.json").read_text(encoding="utf-8")
    )
    capability_manifest = json.loads(
        (_PLUGIN_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    package_manifest = json.loads(
        (_PLUGIN_ROOT / "package.json").read_text(encoding="utf-8")
    )

    metadata = plugin_manifest["toolMetadata"]["ecg_founder_analyze_waveform"]
    assert {
        plugin_manifest["version"],
        capability_manifest["version"],
        package_manifest["version"],
    } == {"1.5.7"}
    assert metadata["optional"] is True
    assert capability_manifest["capabilities"]["noScreenshotToWaveformInference"]
    assert not list(_PLUGIN_ROOT.rglob("*.pth"))


def test_ecg_founder_plugin_rejects_non_loopback_and_sanitizes_scores() -> None:
    module_uri = (_PLUGIN_ROOT / "index.js").as_uri()
    payload = json.dumps(_valid_payload())
    source = f"""
const module = await import({json.dumps(module_uri)});
let remoteRejected = false;
try {{
  module.resolveEcgFounderConfig({{
    DICOM_ECGFOUNDER_ENDPOINT: "https://example.com/v1/analyze",
    DICOM_ECGFOUNDER_TOKEN: "secret"
  }});
}} catch {{
  remoteRejected = true;
}}
const config = module.resolveEcgFounderConfig({{
  DICOM_ECGFOUNDER_ENDPOINT: "http://127.0.0.1:18790/v1/analyze",
  DICOM_ECGFOUNDER_TOKEN: "secret",
  DICOM_ECGFOUNDER_TIMEOUT_MS: "120000"
}});
const details = module.sanitizeEcgFounderResponse(
  {payload},
  {{ artifact_id: "artifact-1", lead_mode: "12_lead", evidence_nonce: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", max_predictions: 10 }}
);
console.log(JSON.stringify({{
  remoteRejected,
  endpoint: config.endpoint,
  timeoutMs: config.timeoutMs,
  decision: details.predictions[0].decision,
  threshold: details.predictions[0].threshold,
  localization: details.spatial_localization,
  sourceKind: details.input.source_kind,
  regularitySignal: details.rhythm_measurement.regularity_signal,
  rrIntervalCount: details.rhythm_measurement.rr_interval_count
}}));
"""

    result = _run_node_module(source)

    assert result["remoteRejected"] is True
    assert str(result["endpoint"]).startswith("http://127.0.0.1:")
    assert result["timeoutMs"] == 30_000
    assert result["decision"] == "uncalibrated_score"
    assert result["threshold"] is None
    assert result["localization"] == "not_provided"
    assert result["sourceKind"] == "raw_waveform"
    assert result["regularitySignal"] == "irregular"
    assert result["rrIntervalCount"] == 6


def test_ecg_founder_plugin_rejects_screenshot_source() -> None:
    module_uri = (_PLUGIN_ROOT / "index.js").as_uri()
    payload = _valid_payload()
    payload["input"]["source_kind"] = "screenshot"  # type: ignore[index]
    source = f"""
const module = await import({json.dumps(module_uri)});
let rejected = false;
try {{
  module.sanitizeEcgFounderResponse(
    {json.dumps(payload)},
    {{ artifact_id: "artifact-1", lead_mode: "12_lead", evidence_nonce: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", max_predictions: 10 }}
  );
}} catch {{
  rejected = true;
}}
console.log(JSON.stringify({{ rejected }}));
"""

    assert _run_node_module(source)["rejected"] is True


def test_bbox_tool_binds_receipt_to_image_turn_and_exact_boxes(
    tmp_path: Path,
) -> None:
    module_uri = (_PLUGIN_ROOT / "index.js").as_uri()
    audit_path = tmp_path / "bbox-audit.jsonl"
    source_sha = "a" * 64
    evidence_nonce = "b" * 32
    source = f"""
process.env.DICOM_BBOX_AUDIT_PATH = {json.dumps(str(audit_path))};
const module = await import({json.dumps(module_uri)});
const tool = module.createBboxValidationTool();
const response = await tool.execute("bbox-call", {{
  modality: "EKG",
  source_image_sha256: {json.dumps(source_sha)},
  evidence_nonce: {json.dumps(evidence_nonce)},
  boxes: [{{ id: "f1", x: 0.1, y: 0.2, w: 0.2, h: 0.1 }}]
}});
let badNonceRejected = false;
try {{
  await tool.execute("bad-call", {{
    modality: "EKG",
    source_image_sha256: {json.dumps(source_sha)},
    evidence_nonce: "wrong",
    boxes: []
  }});
}} catch {{
  badNonceRejected = true;
}}
console.log(JSON.stringify({{
  badNonceRejected,
  details: response.details,
  digest: module.acceptedBoxesDigest(response.details.accepted)
}}));
"""

    result = _run_node_module(source)
    records = [
        json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]

    assert result["badNonceRejected"] is True
    assert result["details"]["source_image_sha256"] == source_sha  # type: ignore[index]
    assert result["details"]["evidence_nonce"] == evidence_nonce  # type: ignore[index]
    assert len(records) == 1
    assert records[0]["schema_version"] == 2
    assert records[0]["source_image_sha256"] == source_sha
    assert records[0]["evidence_nonce"] == evidence_nonce
    assert records[0]["accepted_boxes_sha256"] == result["digest"]


def test_ecg_founder_tool_persists_bounded_success_and_failure_receipts(
    tmp_path: Path,
) -> None:
    module_uri = (_PLUGIN_ROOT / "index.js").as_uri()
    audit_path = tmp_path / "ecgfounder-audit.jsonl"
    payload = json.dumps(_valid_payload())
    source = f"""
const module = await import({json.dumps(module_uri)});
const config = {{
  endpoint: "http://127.0.0.1:18790/v1/analyze",
  token: "secret",
  timeoutMs: 5000,
  auditPath: {json.dumps(str(audit_path))}
}};
const okFetch = async () => new Response({json.dumps(payload)}, {{
  status: 200,
  headers: {{ "content-type": "application/json" }}
}});
const tool = module.createEcgFounderTool(config, okFetch);
await tool.execute("call-ok", {{
  artifact_id: "artifact-1",
  lead_mode: "12_lead",
  evidence_nonce: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  max_predictions: 10
}});
const failedTool = module.createEcgFounderTool(config, async () => {{
  throw new Error("transport_down");
}});
try {{
  await failedTool.execute("call-failed", {{
    artifact_id: "artifact-1",
    lead_mode: "12_lead",
    evidence_nonce: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    max_predictions: 10
  }});
}} catch {{}}
console.log(JSON.stringify({{ done: true }}));
"""

    assert _run_node_module(source)["done"] is True
    records = [
        json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["status"] for record in records] == ["ok", "error"]
    assert {record["evidence_nonce"] for record in records} == {"a" * 32}
    assert records[0]["source_sha256"] == "b" * 64
    assert records[0]["predictions"][0]["label"] == "ATRIAL FIBRILLATION"
    response_evidence = records[0]["response_evidence"]
    assert "artifact_id" not in response_evidence
    expected_digest = hashlib.sha256(
        json.dumps(
            response_evidence,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    assert records[0]["response_sha256"] == expected_digest
    evidence = {
        "requested": True,
        "verified_exactly_once": True,
        "artifact_id_sha256": hashlib.sha256(b"artifact-1").hexdigest(),
        "lead_mode": "12_lead",
        "evidence_nonce": "a" * 32,
        "receipt_count": 1,
        "receipts": [records[0]],
    }
    assert _valid_ecg_founder_evidence(
        evidence,
        expected_preprocessing_revision="test",
    )
    assert records[1]["failure_reason"] == "transport_down"


def test_ecg_founder_tool_suppresses_duplicate_nonce_without_second_fetch(
    tmp_path: Path,
) -> None:
    module_uri = (_PLUGIN_ROOT / "index.js").as_uri()
    audit_path = tmp_path / "ecgfounder-audit.jsonl"
    payload = json.dumps(_valid_payload())
    source = f"""
const module = await import({json.dumps(module_uri)});
const config = {{
  endpoint: "http://127.0.0.1:18790/v1/analyze",
  token: "secret",
  timeoutMs: 5000,
  auditPath: {json.dumps(str(audit_path))}
}};
let fetchCalls = 0;
const fetchOnce = async () => {{
  fetchCalls += 1;
  return new Response({json.dumps(payload)}, {{ status: 200 }});
}};
const tool = module.createEcgFounderTool(config, fetchOnce);
const args = {{
  artifact_id: "artifact-1",
  lead_mode: "12_lead",
  evidence_nonce: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  max_predictions: 10
}};
const first = await tool.execute("call-first", args);
const duplicate = await tool.execute("call-duplicate", args);
let mismatchRejected = false;
try {{
  await tool.execute("call-mismatch", {{ ...args, max_predictions: 5 }});
}} catch {{
  mismatchRejected = true;
}}
console.log(JSON.stringify({{
  fetchCalls,
  mismatchRejected,
  first: first.details,
  duplicate: duplicate.details
}}));
"""

    result = _run_node_module(source)
    records = [
        json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]

    assert result["fetchCalls"] == 1
    assert result["mismatchRejected"] is True
    assert result["first"]["tool_call_policy"]["duplicate_suppressed"] is False  # type: ignore[index]
    duplicate = result["duplicate"]  # type: ignore[assignment]
    assert duplicate["tool_call_policy"]["duplicate_suppressed"] is True  # type: ignore[index]
    assert "rr_intervals_ms" not in duplicate["rhythm_measurement"]  # type: ignore[index]
    assert [record["tool"] for record in records] == [
        "ecg_founder_analyze_waveform",
        "ecg_founder_duplicate_suppressed",
    ]
    assert records[1]["original_tool_call_id"] == "call-first"
    assert records[1]["tool_call_id"] == "call-duplicate"
