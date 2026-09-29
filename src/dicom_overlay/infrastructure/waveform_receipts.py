"""Prompt-time validation of the native plugin's waveform audit receipt.

This validates the existing local audit contract, not a screenshot-to-waveform
match, independent blind reading, original Gateway tool text, or clinical truth.
Keep frozen evaluation/scoring implementations separate from this runtime gate.
No waveform/model runtime or evaluation dependencies belong in the desktop app.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from dicom_overlay.infrastructure.strict_json import read_json_object

_MODEL = "PKUDigitalHealth/ECGFounder"
_REVISION = "04edac702b61c91face519774ddcc0cd712fef23"
_CHECKPOINT = "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997"


def valid_waveform_support_receipt(
    receipt: dict[str, Any], *, artifact_id: str, evidence_nonce: str
) -> bool:
    """Fail closed before copying any waveform labels into a later image prompt."""
    digest = hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()
    expected = {
        "schema_version": 1,
        "tool": "ecg_founder_analyze_waveform",
        "status": "ok",
        "evidence_nonce": evidence_nonce,
        "artifact_id_sha256": digest,
        "lead_mode": "12_lead",
        "model_id": _MODEL,
        "model_revision": _REVISION,
        "checkpoint_sha256": _CHECKPOINT,
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        return False
    call_id = receipt.get("tool_call_id")
    source_hash = receipt.get("source_sha256")
    preprocessing = receipt.get("preprocessing_revision")
    calibration = receipt.get("calibration_status")
    calibration_revision = receipt.get("calibration_revision")
    if not (
        type(receipt.get("schema_version")) is int
        and isinstance(call_id, str)
        and 0 < len(call_id.strip()) <= 256
        and isinstance(source_hash, str)
        and re.fullmatch(r"[a-f0-9]{64}", source_hash)
        and isinstance(preprocessing, str)
        and 0 < len(preprocessing.strip()) <= 256
        and calibration in ("uncalibrated", "validated")
        and isinstance(calibration_revision, str)
        and len(calibration_revision) <= 256
        and (calibration != "validated" or calibration_revision.strip())
    ):
        return False

    predictions = receipt.get("predictions")
    count = receipt.get("prediction_count")
    if not (
        type(count) is int
        and 1 <= count <= 20
        and isinstance(predictions, list)
        and len(predictions) == count
    ):
        return False
    labels: set[str] = set()
    for item in predictions:
        if not isinstance(item, dict):
            return False
        label, score = item.get("label"), item.get("probability")
        if not (
            isinstance(label, str)
            and 0 < len(label.strip()) <= 256
            and len(label) <= 256
            and label not in labels
            and isinstance(score, int | float)
            and not isinstance(score, bool)
            and 0 <= score <= 1
            and math.isfinite(score)
        ):
            return False
        labels.add(label)

    response = receipt.get("response_evidence")
    if not isinstance(response, dict) or "artifact_id" in response:
        return False
    try:
        encoded = json.dumps(
            response,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if "response_canonical_json" in receipt:
            native_text = receipt["response_canonical_json"]
            if not isinstance(native_text, str):
                return False
            native_bytes = native_text.encode("utf-8")
            native_object = read_json_object(native_bytes)
            # Compare typed JSON values, not Python's True == 1 equality. Hash
            # the producer's actual bytes rather than guessing JS float syntax.
            projected = json.dumps(
                native_object,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            if projected != encoded:
                return False
            encoded = native_bytes
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return False
    if len(encoded) > 512 * 1024 or hashlib.sha256(encoded).hexdigest() != receipt.get(
        "response_sha256"
    ):
        return False
    response_expected = {
        "schema_version": 1,
        "status": "ok",
        "evidence_type": "ecg_waveform_classification",
        "lead_mode": "12_lead",
        "evidence_nonce": evidence_nonce,
        "artifact_id_sha256": digest,
        "use_policy": "supporting_evidence_only",
        "spatial_localization": "not_provided",
        "predictions": predictions,
    }
    if type(response.get("schema_version")) is not int or any(
        response.get(key) != value for key, value in response_expected.items()
    ):
        return False
    nested_expected = {
        "model": {
            "id": _MODEL,
            "revision": _REVISION,
            "checkpoint_sha256": _CHECKPOINT,
        },
        "input": {"source_sha256": source_hash},
        "preprocessing": {"implementation_revision": preprocessing},
        "calibration": {"status": calibration, "revision": calibration_revision},
    }
    for key, fields in nested_expected.items():
        section = response.get(key)
        if not isinstance(section, dict) or any(
            section.get(field) != value for field, value in fields.items()
        ):
            return False
    return True
