from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = (
    _REPO_ROOT
    / "openclaw"
    / "workspace"
    / "plugins"
    / "dicom-overlay-agent-harness"
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
            "checkpoint_sha256": "a" * 64,
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
        "limitations": ["Research support only"],
    }


def test_ecg_founder_tool_is_optional_and_not_bundled_as_model_weights() -> None:
    plugin_manifest = json.loads(
        (_PLUGIN_ROOT / "openclaw.plugin.json").read_text(encoding="utf-8")
    )
    capability_manifest = json.loads(
        (_PLUGIN_ROOT / "manifest.json").read_text(encoding="utf-8")
    )

    metadata = plugin_manifest["toolMetadata"]["ecg_founder_analyze_waveform"]
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
  DICOM_ECGFOUNDER_TOKEN: "secret"
}});
const details = module.sanitizeEcgFounderResponse(
  {payload},
  {{ artifact_id: "artifact-1", lead_mode: "12_lead", max_predictions: 10 }}
);
console.log(JSON.stringify({{
  remoteRejected,
  endpoint: config.endpoint,
  decision: details.predictions[0].decision,
  threshold: details.predictions[0].threshold,
  localization: details.spatial_localization,
  sourceKind: details.input.source_kind
}}));
"""

    result = _run_node_module(source)

    assert result["remoteRejected"] is True
    assert str(result["endpoint"]).startswith("http://127.0.0.1:")
    assert result["decision"] == "uncalibrated_score"
    assert result["threshold"] is None
    assert result["localization"] == "not_provided"
    assert result["sourceKind"] == "raw_waveform"


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
    {{ artifact_id: "artifact-1", lead_mode: "12_lead", max_predictions: 10 }}
  );
}} catch {{
  rejected = true;
}}
console.log(JSON.stringify({{ rejected }}));
"""

    assert _run_node_module(source)["rejected"] is True
