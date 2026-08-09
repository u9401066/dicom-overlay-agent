"""Validate completeness and protocol integrity of evaluation artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from dicom_overlay.domain.ekg_layout import (
    canonical_ekg_lead_name,
    parse_ekg_lead_inventory,
    parse_normalized_region,
)

_PROTOCOL_FINGERPRINT_NAME = "protocol-fingerprint.json"
_PROTOCOL_FINGERPRINT_SCHEMA_VERSION = 1
_ECG_FOUNDER_MODEL_REVISION = "04edac702b61c91face519774ddcc0cd712fef23"
_ECG_FOUNDER_CHECKPOINT_SHA256 = (
    "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997"
)
_ECG_FOUNDER_REQUEST_INELIGIBLE_REASONS = frozenset(
    {
        "invalid_request_schema",
        "invalid_artifact_id",
        "unsupported_lead_mode",
        "artifact_not_registered",
        "invalid_max_predictions",
    }
)


@dataclass(frozen=True)
class EvalArtifactVerification:
    """CI-readable verification report for a large eval run."""

    ok: bool
    passed_checks: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "passed_checks": self.passed_checks,
                "failures": self.failures,
            },
            indent=2,
            ensure_ascii=False,
        )


@dataclass(frozen=True)
class _ExpectedCase:
    label: str
    image_name: str
    image_path: Path
    image_sha256: str
    image_size_bytes: int
    waveform_artifact_sha256: str = ""


@dataclass
class _ResultInventory:
    cases: set[str] = field(default_factory=set)
    ekg_cases: set[str] = field(default_factory=set)
    bbox_counts: dict[str, int] = field(default_factory=dict)
    refinement_completed_cases: set[str] = field(default_factory=set)
    original_roi_refinement_cases: set[str] = field(default_factory=set)
    refinement_decision_cases: set[str] = field(default_factory=set)
    bbox_tool_cases: set[str] = field(default_factory=set)
    refinement_bbox_tool_accepted_cases: set[str] = field(default_factory=set)
    finalization_completed_cases: set[str] = field(default_factory=set)
    original_roi_finalization_cases: set[str] = field(default_factory=set)
    finalization_bbox_tool_accepted_cases: set[str] = field(default_factory=set)
    ekg_systematic_planned_cases: set[str] = field(default_factory=set)
    ekg_systematic_completed_cases: set[str] = field(default_factory=set)
    original_roi_ekg_systematic_cases: set[str] = field(default_factory=set)


def verify_eval_artifacts(
    *,
    eval_dir: Path,
    manifest_path: Path,
    min_cases: int,
    require_review: bool = True,
    require_perfect_mock: bool = True,
    require_multipass_trace: bool = False,
    require_multipass_refinement: bool = False,
    require_ekg_systematic_probes: bool = False,
    require_projection_audit: bool = False,
    require_zero_safety_misses: bool = True,
    min_strict_pass_rate: float | None = None,
    min_mean_partial_credit: float | None = None,
) -> EvalArtifactVerification:
    """Verify a complete eval run without invoking a model."""
    for name, value in (
        ("min_strict_pass_rate", min_strict_pass_rate),
        ("min_mean_partial_credit", min_mean_partial_credit),
    ):
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1]")
    eval_dir = Path(eval_dir)
    manifest_path = Path(manifest_path)
    failures: list[str] = []
    passed: list[str] = []

    manifest = _read_json(manifest_path, failures, label="manifest")
    fingerprint, expected_cases = _verify_protocol_fingerprint(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        manifest=manifest,
        failures=failures,
        passed=passed,
    )
    if len(expected_cases) >= min_cases:
        passed.append("min_cases")
    else:
        failures.append(
            "min_cases: protocol selects "
            f"{len(expected_cases)} cases, expected at least {min_cases}"
        )

    scorecard = _read_json(
        eval_dir / "scorecard.json",
        failures,
        label="scorecard",
    )
    protocol_digest = (
        str(fingerprint.get("protocol_digest")) if isinstance(fingerprint, dict) else ""
    )
    protocol = fingerprint.get("protocol") if isinstance(fingerprint, dict) else None
    flags = protocol.get("flags") if isinstance(protocol, dict) else None
    manifest_identity = (
        protocol.get("manifest") if isinstance(protocol, dict) else None
    )
    paired_gold_manifest = bool(
        isinstance(flags, dict)
        and flags.get("defer_scoring") is True
        and isinstance(manifest_identity, dict)
        and manifest_path.is_file()
        and manifest_identity.get("sha256") != _sha256_file(manifest_path)
    )
    require_ecgfounder_evidence = bool(
        isinstance(flags, dict) and flags.get("ecgfounder_waveform_evidence") is True
    )
    minimal_control = bool(
        isinstance(flags, dict)
        and flags.get("analysis_prompt_profile") == "minimal_control"
    )
    expected_ecgfounder_preprocessing_revision = (
        str(flags.get("ecgfounder_preprocessing_revision") or "")
        if isinstance(flags, dict)
        else ""
    )
    if require_ecgfounder_evidence and not expected_ecgfounder_preprocessing_revision:
        failures.append(
            "protocol_fingerprint: ECGFounder arm lacks preprocessing revision"
        )
    if isinstance(scorecard, dict):
        if paired_gold_manifest:
            provenance = scorecard.get("scoring_manifest_provenance")
            if (
                not isinstance(provenance, dict)
                or provenance.get("paired_gold_manifest") is not True
                or provenance.get("sha256") != _sha256_file(manifest_path)
            ):
                failures.append(
                    "scorecard_complete: paired gold manifest provenance mismatch"
                )
            else:
                passed.append("paired_gold_manifest")
        _verify_scorecard(
            scorecard,
            expected_cases=set(expected_cases),
            min_cases=min_cases,
            protocol_digest=protocol_digest,
            require_perfect_mock=require_perfect_mock,
            min_strict_pass_rate=min_strict_pass_rate,
            min_mean_partial_credit=min_mean_partial_credit,
            require_schema_gate=not minimal_control,
            require_zero_safety_misses=require_zero_safety_misses,
            failures=failures,
            passed=passed,
        )

    results = _verify_results(
        eval_dir / "results",
        expected_cases=expected_cases,
        protocol_digest=protocol_digest,
        require_ecgfounder_evidence=require_ecgfounder_evidence,
        expected_ecgfounder_preprocessing_revision=(
            expected_ecgfounder_preprocessing_revision
        ),
        require_model_assist=not minimal_control,
        failures=failures,
        passed=passed,
    )
    _verify_multipass_trace(
        eval_dir / "multipass-trace.jsonl",
        require=require_multipass_trace or require_multipass_refinement,
        require_refinement=require_multipass_refinement,
        results=results,
        failures=failures,
        passed=passed,
    )
    _verify_ekg_systematic_probes(
        results,
        require=require_ekg_systematic_probes,
        failures=failures,
        passed=passed,
    )
    if require_review:
        _verify_review_artifacts(
            eval_dir / "review",
            results=results,
            failures=failures,
            passed=passed,
            require_projection_audit=require_projection_audit,
        )

    return EvalArtifactVerification(
        ok=not failures,
        passed_checks=passed,
        failures=failures,
    )


def _read_json(path: Path, failures: list[str], *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        failures.append(f"{label}: could not read {path}: {exc}")
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )


def _is_evidence_nonce(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 32
        and all(char in "0123456789abcdef" for char in value)
    )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _valid_ecg_predictions(value: object) -> bool:
    if not isinstance(value, list) or not 1 <= len(value) <= 20:
        return False
    for prediction in value:
        if not isinstance(prediction, dict) or not isinstance(
            prediction.get("label"), str
        ):
            return False
        probability = prediction.get("probability")
        if (
            not prediction["label"].strip()
            or not isinstance(probability, (int, float))
            or isinstance(probability, bool)
            or not math.isfinite(float(probability))
            or not 0.0 <= float(probability) <= 1.0
        ):
            return False
    return True


def _ecg_response_matches_receipt(
    response: object,
    receipt: dict[str, Any],
    evidence: dict[str, Any],
) -> bool:
    if not isinstance(response, dict) or "artifact_id" in response:
        return False
    model = response.get("model")
    input_provenance = response.get("input")
    preprocessing = response.get("preprocessing")
    calibration = response.get("calibration")
    return bool(
        response.get("schema_version") == 1
        and response.get("status") == "ok"
        and response.get("evidence_type") == "ecg_waveform_classification"
        and response.get("lead_mode") == "12_lead"
        and response.get("evidence_nonce") == evidence.get("evidence_nonce")
        and response.get("artifact_id_sha256") == evidence.get("artifact_id_sha256")
        and response.get("use_policy") == "supporting_evidence_only"
        and response.get("spatial_localization") == "not_provided"
        and isinstance(model, dict)
        and model.get("id") == receipt.get("model_id")
        and model.get("revision") == receipt.get("model_revision")
        and model.get("checkpoint_sha256") == receipt.get("checkpoint_sha256")
        and isinstance(input_provenance, dict)
        and input_provenance.get("source_sha256") == receipt.get("source_sha256")
        and isinstance(preprocessing, dict)
        and preprocessing.get("implementation_revision")
        == receipt.get("preprocessing_revision")
        and isinstance(calibration, dict)
        and calibration.get("status") == receipt.get("calibration_status")
        and calibration.get("revision") == receipt.get("calibration_revision")
        and response.get("predictions") == receipt.get("predictions")
    )


def _ineligible_ecg_response_matches_receipt(
    response: object,
    receipt: dict[str, Any],
    evidence: dict[str, Any],
) -> bool:
    if not isinstance(response, dict) or "artifact_id" in response:
        return False
    reason = response.get("reason")
    return bool(
        response.get("schema_version") == 1
        and response.get("status") == "ineligible"
        and response.get("evidence_type") == "ecg_waveform_classification"
        and response.get("lead_mode") == "12_lead"
        and response.get("evidence_nonce") == evidence.get("evidence_nonce")
        and response.get("artifact_id_sha256") == evidence.get("artifact_id_sha256")
        and response.get("use_policy") == "supporting_evidence_only"
        and response.get("spatial_localization") == "not_provided"
        and isinstance(reason, str)
        and bool(reason)
        and reason not in _ECG_FOUNDER_REQUEST_INELIGIBLE_REASONS
        and receipt.get("failure_reason") == reason
        and response.get("predictions") == []
        and receipt.get("predictions") == []
        and receipt.get("prediction_count") == 0
    )


def _valid_ecg_founder_evidence(
    value: object,
    *,
    expected_artifact_sha256: str = "",
    expected_preprocessing_revision: str = "",
) -> bool:
    if not isinstance(value, dict) or value.get("requested") is not True:
        return False
    receipts = value.get("receipts")
    receipt = (
        receipts[0]
        if isinstance(receipts, list)
        and len(receipts) == 1
        and isinstance(receipts[0], dict)
        else None
    )
    response_evidence = receipt.get("response_evidence") if receipt else None
    common_valid = bool(
        value.get("verified_exactly_once") is True
        and value.get("receipt_count") == 1
        and value.get("lead_mode") == "12_lead"
        and _is_sha256(value.get("artifact_id_sha256"))
        and (
            not expected_artifact_sha256
            or value.get("artifact_id_sha256") == expected_artifact_sha256
        )
        and receipt is not None
        and receipt.get("schema_version") == 1
        and receipt.get("tool") == "ecg_founder_analyze_waveform"
        and isinstance(receipt.get("tool_call_id"), str)
        and bool(receipt.get("tool_call_id"))
        and receipt.get("lead_mode") == "12_lead"
        and _is_evidence_nonce(value.get("evidence_nonce"))
        and receipt.get("evidence_nonce") == value.get("evidence_nonce")
        and receipt.get("artifact_id_sha256") == value.get("artifact_id_sha256")
        and _is_sha256(receipt.get("response_sha256"))
        and isinstance(response_evidence, dict)
        and _canonical_sha256(response_evidence) == receipt.get("response_sha256")
        and (
            "evidence_status" not in value
            or value.get("evidence_status") == receipt.get("status")
        )
        and (
            "usable" not in value
            or value.get("usable") is (receipt.get("status") == "ok")
        )
    )
    if not common_valid:
        return False
    if receipt.get("status") == "ineligible":
        return _ineligible_ecg_response_matches_receipt(
            response_evidence,
            receipt,
            value,
        )
    return bool(
        receipt.get("status") == "ok"
        and receipt.get("model_id") == "PKUDigitalHealth/ECGFounder"
        and receipt.get("model_revision") == _ECG_FOUNDER_MODEL_REVISION
        and receipt.get("checkpoint_sha256") == _ECG_FOUNDER_CHECKPOINT_SHA256
        and _is_sha256(receipt.get("source_sha256"))
        and _ecg_response_matches_receipt(response_evidence, receipt, value)
        and isinstance(receipt.get("preprocessing_revision"), str)
        and bool(receipt.get("preprocessing_revision"))
        and (
            not expected_preprocessing_revision
            or receipt.get("preprocessing_revision") == expected_preprocessing_revision
        )
        and _valid_ecg_predictions(receipt.get("predictions"))
        and isinstance(receipt.get("prediction_count"), int)
        and not isinstance(receipt.get("prediction_count"), bool)
        and 1 <= receipt["prediction_count"] <= 20
        and len(receipt["predictions"]) == receipt.get("prediction_count")
    )


def _protocol_digest(protocol: dict[str, Any]) -> str:
    encoded = json.dumps(
        protocol,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _manifest_case_index(
    manifest: Any,
    manifest_path: Path,
    failures: list[str],
) -> dict[str, _ExpectedCase]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), list):
        return {}
    index: dict[str, _ExpectedCase] = {}
    for position, row in enumerate(manifest["cases"], start=1):
        if not isinstance(row, dict) or not isinstance(row.get("image"), str):
            failures.append(f"manifest_identity: invalid case row {position}")
            continue
        relative = Path(row["image"])
        label = str(row.get("label") or relative.name)
        if label in index:
            failures.append(f"manifest_identity: duplicate case label {label}")
            continue
        image_path = (manifest_path.parent / relative).resolve()
        if not image_path.is_file():
            failures.append(
                f"manifest_identity: missing image for {label}: {image_path}"
            )
            continue
        waveform_artifact_id = str(row.get("waveform_artifact_id") or "")
        index[label] = _ExpectedCase(
            label=label,
            image_name=image_path.name,
            image_path=image_path,
            image_sha256=_sha256_file(image_path),
            image_size_bytes=image_path.stat().st_size,
            waveform_artifact_sha256=(
                hashlib.sha256(waveform_artifact_id.encode("utf-8")).hexdigest()
                if waveform_artifact_id
                else ""
            ),
        )
    return index


def _verify_protocol_fingerprint(
    *,
    eval_dir: Path,
    manifest_path: Path,
    manifest: Any,
    failures: list[str],
    passed: list[str],
) -> tuple[dict[str, Any] | None, dict[str, _ExpectedCase]]:
    failure_count = len(failures)
    manifest_cases = _manifest_case_index(manifest, manifest_path, failures)
    path = eval_dir / _PROTOCOL_FINGERPRINT_NAME
    fingerprint = _read_json(path, failures, label="protocol_fingerprint")
    if not isinstance(fingerprint, dict):
        failures.append(
            "protocol_fingerprint: missing/invalid fingerprint; legacy runs are "
            "not comparable"
        )
        return None, manifest_cases
    if fingerprint.get("schema_version") != _PROTOCOL_FINGERPRINT_SCHEMA_VERSION:
        failures.append(
            "protocol_fingerprint: unsupported schema "
            f"{fingerprint.get('schema_version')!r}"
        )
    protocol = fingerprint.get("protocol")
    if not isinstance(protocol, dict):
        failures.append("protocol_fingerprint: missing protocol object")
        return fingerprint, manifest_cases
    if fingerprint.get("protocol_digest") != _protocol_digest(protocol):
        failures.append("protocol_fingerprint: digest does not match protocol payload")

    comparison = fingerprint.get("comparability")
    if not isinstance(comparison, dict) or comparison.get("comparable") is not True:
        status = comparison.get("status") if isinstance(comparison, dict) else None
        failures.append(
            f"protocol_fingerprint: run is mixed/non-comparable (status={status!r})"
        )

    source = protocol.get("source")
    model = protocol.get("model")
    prompts = protocol.get("prompts")
    skills = protocol.get("skills")
    flags = protocol.get("flags")
    if not isinstance(source, dict) or not {
        "commit",
        "dirty",
        "tracked_diff_sha256",
    }.issubset(source):
        failures.append("protocol_fingerprint: missing git commit/dirty identity")
    if not isinstance(model, dict) or not isinstance(model.get("id"), str):
        failures.append("protocol_fingerprint: missing model identity")
    elif not isinstance(model.get("openclaw"), dict) or not isinstance(
        model["openclaw"].get("version"), str
    ):
        failures.append("protocol_fingerprint: missing OpenClaw version identity")
    if not _valid_hash_records(prompts):
        failures.append("protocol_fingerprint: missing prompt hashes")
    if not _valid_hash_records(skills):
        failures.append("protocol_fingerprint: missing skill hashes")
    if not isinstance(flags, dict):
        failures.append("protocol_fingerprint: missing important flags")

    manifest_identity = protocol.get("manifest")
    if not isinstance(manifest_identity, dict):
        failures.append("protocol_fingerprint: missing manifest identity")
        return fingerprint, manifest_cases
    manifest_hash_matches = bool(
        manifest_path.is_file()
        and manifest_identity.get("sha256") == _sha256_file(manifest_path)
    )
    paired_gold_allowed = bool(
        not manifest_hash_matches
        and isinstance(flags, dict)
        and flags.get("defer_scoring") is True
    )
    if not manifest_hash_matches and not paired_gold_allowed:
        failures.append("protocol_fingerprint: manifest hash mismatch")
    selected_rows = manifest_identity.get("cases")
    if not isinstance(selected_rows, list) or not selected_rows:
        failures.append("protocol_fingerprint: selected image identities are missing")
        return fingerprint, manifest_cases

    selected: dict[str, _ExpectedCase] = {}
    for position, row in enumerate(selected_rows, start=1):
        if not isinstance(row, dict) or not isinstance(row.get("case"), str):
            failures.append(
                f"protocol_fingerprint: invalid selected case row {position}"
            )
            continue
        label = row["case"]
        case = manifest_cases.get(label)
        if case is None:
            failures.append(
                f"protocol_fingerprint: selected case absent from manifest: {label}"
            )
            continue
        if label in selected:
            failures.append(f"protocol_fingerprint: duplicate selected case: {label}")
            continue
        if (
            row.get("image_name") != case.image_name
            or row.get("size_bytes") != case.image_size_bytes
            or row.get("sha256") != case.image_sha256
        ):
            failures.append(
                f"protocol_fingerprint: image identity mismatch for {label}"
            )
            continue
        selected[label] = case
    if manifest_identity.get("selected_case_count") != len(selected_rows):
        failures.append(
            "protocol_fingerprint: selected_case_count does not match identity rows"
        )
    if len(selected) != len(selected_rows):
        failures.append(
            "protocol_fingerprint: one or more selected image identities are invalid"
        )
    if len(failures) == failure_count:
        passed.append("protocol_fingerprint")
    return fingerprint, selected or manifest_cases


def _valid_hash_records(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for row in value:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            return False
        digest = row.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest.lower())
        ):
            return False
    return True


def _verify_scorecard(
    scorecard: dict[str, Any],
    *,
    expected_cases: set[str],
    min_cases: int,
    protocol_digest: str,
    require_perfect_mock: bool,
    min_strict_pass_rate: float | None,
    min_mean_partial_credit: float | None,
    require_schema_gate: bool,
    require_zero_safety_misses: bool,
    failures: list[str],
    passed: list[str],
) -> None:
    failure_count = len(failures)
    expected_count = len(expected_cases)
    manifest_total = _int_value(scorecard.get("manifest_total"))
    result_count = _int_value(scorecard.get("result_count"))
    total = _int_value(scorecard.get("total"))
    scored = _int_value(scorecard.get("scored"))
    error_count = _int_value(scorecard.get("error_count"))

    if scorecard.get("scorecard_kind") != "full_rebuild":
        failures.append("scorecard_complete: canonical scorecard is not a full rebuild")
    if scorecard.get("is_partial"):
        failures.append("scorecard_complete: scorecard is partial")
    if scorecard.get("missing_cases") not in ([], None):
        failures.append(
            f"scorecard_complete: missing_cases={scorecard.get('missing_cases')}"
        )
    if manifest_total != expected_count or manifest_total < min_cases:
        failures.append(
            "scorecard_complete: "
            f"manifest_total={manifest_total}, expected exactly {expected_count}"
        )
    if result_count != expected_count or result_count < min_cases:
        failures.append(
            "scorecard_complete: "
            f"result_count={result_count}, expected exactly {expected_count}"
        )
    if total != result_count:
        failures.append(
            f"scorecard_complete: total={total} does not match result_count={result_count}"
        )
    if scored != result_count:
        failures.append(
            f"scorecard_complete: scored={scored} does not match result_count={result_count}"
        )
    if error_count:
        failures.append(f"scorecard_complete: error_count={error_count}")
    if not protocol_digest or scorecard.get("protocol_digest") != protocol_digest:
        failures.append("scorecard_complete: protocol digest mismatch")
    comparison = scorecard.get("protocol_comparability")
    if not isinstance(comparison, dict) or comparison.get("comparable") is not True:
        failures.append("scorecard_complete: scorecard is marked non-comparable")
    case_rows = scorecard.get("cases")
    scorecard_cases = (
        {
            str(row.get("case_label"))
            for row in case_rows
            if isinstance(row, dict) and row.get("case_label")
        }
        if isinstance(case_rows, list)
        else set()
    )
    if scorecard_cases != expected_cases or (
        isinstance(case_rows, list) and len(case_rows) != len(expected_cases)
    ):
        failures.append("scorecard_complete: scorecard case set is not exact")
    if len(failures) == failure_count:
        passed.append("scorecard_complete")

    schema_pass_rate = float(scorecard.get("schema_pass_rate", 0.0))
    if not require_schema_gate and 0.0 <= schema_pass_rate <= 1.0:
        passed.append("control_schema_observed")
    elif schema_pass_rate >= 1.0:
        passed.append("schema_gate")
    else:
        failures.append(
            f"schema_gate: schema_pass_rate={scorecard.get('schema_pass_rate')}"
        )
    if float(scorecard.get("bbox_in_bounds_rate", 0.0)) >= 1.0:
        passed.append("bbox_gate")
    else:
        failures.append(
            f"bbox_gate: bbox_in_bounds_rate={scorecard.get('bbox_in_bounds_rate')}"
        )
    misses = scorecard.get("cant_miss_missed", [])
    if not isinstance(misses, list):
        failures.append("cant_miss_metrics: cant_miss_missed is not a list")
    elif require_zero_safety_misses and misses:
        failures.append(f"cant_miss_gate: missed={misses}")
    elif require_zero_safety_misses:
        passed.append("cant_miss_gate")
    else:
        passed.append("cant_miss_metrics_recorded")
    urgent_misses = scorecard.get("urgent_concern_missed", [])
    if not isinstance(urgent_misses, list):
        failures.append(
            "urgent_concern_metrics: urgent_concern_missed is not a list"
        )
    elif require_zero_safety_misses and urgent_misses:
        failures.append(f"urgent_concern_gate: missed={urgent_misses}")
    elif require_zero_safety_misses:
        passed.append("urgent_concern_gate")
    else:
        passed.append("urgent_concern_metrics_recorded")
    if scorecard.get("gateway_mode") == "mock" and require_perfect_mock:
        if float(scorecard.get("strict_pass_rate", 0.0)) >= 1.0:
            passed.append("mock_perfect_gate")
        else:
            failures.append(
                f"mock_perfect_gate: strict_pass_rate={scorecard.get('strict_pass_rate')}"
            )
    _verify_minimum_rate(
        scorecard,
        field="strict_pass_rate",
        minimum=min_strict_pass_rate,
        check="strict_accuracy_gate",
        failures=failures,
        passed=passed,
    )
    _verify_minimum_rate(
        scorecard,
        field="mean_partial_credit",
        minimum=min_mean_partial_credit,
        check="partial_credit_gate",
        failures=failures,
        passed=passed,
    )


def _verify_minimum_rate(
    scorecard: dict[str, Any],
    *,
    field: str,
    minimum: float | None,
    check: str,
    failures: list[str],
    passed: list[str],
) -> None:
    if minimum is None:
        return
    try:
        raw_actual = scorecard.get(field)
        if not isinstance(raw_actual, int | float | str):
            raise TypeError
        actual = float(raw_actual)
    except (TypeError, ValueError):
        failures.append(f"{check}: {field} is missing or invalid")
        return
    if actual + 1e-12 >= minimum:
        passed.append(check)
    else:
        failures.append(f"{check}: {field}={actual:.6f}, minimum={minimum:.6f}")


def _verify_results(
    results_dir: Path,
    *,
    expected_cases: dict[str, _ExpectedCase],
    protocol_digest: str,
    require_ecgfounder_evidence: bool,
    expected_ecgfounder_preprocessing_revision: str,
    require_model_assist: bool,
    failures: list[str],
    passed: list[str],
) -> _ResultInventory:
    failure_count = len(failures)
    inventory = _ResultInventory()
    files = sorted(results_dir.glob("*.json")) if results_dir.exists() else []
    expected_filenames = {
        _result_filename(label): case for label, case in expected_cases.items()
    }
    if {path.name for path in files} != set(expected_filenames):
        missing = sorted(set(expected_filenames) - {path.name for path in files})
        extra = sorted({path.name for path in files} - set(expected_filenames))
        failures.append(
            "results_artifacts: result filename set mismatch "
            f"(missing={missing[:5]}, extra={extra[:5]})"
        )

    missing_preflight: list[str] = []
    missing_signal_candidates: list[str] = []
    for path in files:
        case = expected_filenames.get(path.name)
        if case is None:
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"results_artifacts: invalid JSON {path.name}: {exc}")
            continue
        if not isinstance(raw, dict):
            failures.append(f"results_artifacts: non-object JSON {path.name}")
            continue
        if raw.get("case") != case.label or case.label in inventory.cases:
            failures.append(f"results_artifacts: case identity mismatch {path.name}")
            continue
        score = raw.get("score")
        score = score if isinstance(score, dict) else {}
        image = raw.get("image") or score.get("image")
        if not isinstance(image, str) or Path(image).name != case.image_name:
            failures.append(f"results_artifacts: image identity mismatch {path.name}")
        if raw.get("protocol_digest") != protocol_digest:
            failures.append(f"results_artifacts: protocol digest mismatch {path.name}")
        if raw.get("source_image_sha256") != case.image_sha256:
            failures.append(
                f"results_artifacts: source image hash mismatch {path.name}"
            )
        inventory.cases.add(case.label)
        if raw.get("modality") == "EKG":
            inventory.ekg_cases.add(case.label)

        quality = raw.get("local_image_quality")
        if not isinstance(quality, dict) or "low_signal" not in quality:
            missing_preflight.append(path.name)
        signal = raw.get("local_signal_candidates")
        if not isinstance(signal, dict) or "candidate_count" not in signal:
            missing_signal_candidates.append(path.name)

        waveform_evidence = raw.get("waveform_evidence")
        evidence_requested = bool(
            isinstance(waveform_evidence, dict)
            and waveform_evidence.get("requested") is True
        )
        if require_ecgfounder_evidence and not evidence_requested:
            failures.append(
                "results_artifacts: required ECGFounder evidence is missing in "
                f"{path.name}"
            )
        elif evidence_requested and not _valid_ecg_founder_evidence(
            waveform_evidence,
            expected_artifact_sha256=case.waveform_artifact_sha256,
            expected_preprocessing_revision=(
                expected_ecgfounder_preprocessing_revision
            ),
        ):
            failures.append(
                "results_artifacts: ECGFounder evidence lacks exactly one valid "
                f"bound ok/ineligible receipt in {path.name}"
            )

        findings = raw.get("findings")
        if findings is None:
            findings = []
        if not isinstance(findings, list):
            failures.append(f"results_artifacts: findings is not a list {path.name}")
            inventory.bbox_counts[case.label] = 0
            continue
        bbox_count = 0
        for finding_index, finding in enumerate(findings, start=1):
            if not isinstance(finding, dict):
                failures.append(
                    "results_artifacts: "
                    f"finding {finding_index} is not an object in {path.name}"
                )
                continue
            bboxes = finding.get("bboxes") or []
            if not isinstance(bboxes, list):
                failures.append(
                    "results_artifacts: "
                    f"bboxes is not a list for finding {finding_index} in {path.name}"
                )
                continue
            bbox_count += len(bboxes)
            if raw.get("modality") == "EKG":
                mismatch = _ekg_bbox_lead_mismatch(
                    finding,
                    layout=raw.get("layout"),
                )
                if mismatch:
                    failures.append(
                        "results_artifacts: "
                        f"EKG bbox/lead mismatch in {path.name} finding "
                        f"{finding_index}: {mismatch}"
                    )
        inventory.bbox_counts[case.label] = bbox_count
        final_bbox_digest, final_bbox_digest_count = _bbox_payload_digest(findings)
        source_image_sha256 = str(raw.get("source_image_sha256") or "")
        trace = raw.get("analysis_trace")
        if isinstance(trace, list):
            for event in trace:
                if not isinstance(event, dict):
                    continue
                tools = event.get("tools")
                if isinstance(tools, list) and "dicom_bbox_validate" in tools:
                    inventory.bbox_tool_cases.add(case.label)
                if (
                    event.get("stage") == "finalize"
                    and event.get("status") == "completed"
                ):
                    inventory.finalization_completed_cases.add(case.label)
                    if event.get("source") == "original_roi":
                        inventory.original_roi_finalization_cases.add(case.label)
                    tool_audit = event.get("tool_audit")
                    if isinstance(tool_audit, list) and any(
                        _valid_bound_bbox_receipt(
                            record,
                            event,
                            expected_source_image_sha256=source_image_sha256,
                            expected_boxes_sha256=final_bbox_digest,
                            expected_count=final_bbox_digest_count,
                        )
                        for record in tool_audit
                    ):
                        inventory.finalization_bbox_tool_accepted_cases.add(case.label)
                if event.get("stage") == "systematic_assist":
                    probes = event.get("probes")
                    if isinstance(probes, list) and any(
                        isinstance(probe, dict)
                        and str(probe.get("target_id", "")).startswith(
                            "ekg_systematic_"
                        )
                        for probe in probes
                    ):
                        inventory.ekg_systematic_planned_cases.add(case.label)
                if event.get("stage") != "refine" or event.get("status") != "completed":
                    continue
                if event.get("tool") == "crop_region_base64":
                    inventory.refinement_completed_cases.add(case.label)
                    if event.get("crop_source") == "original_roi":
                        inventory.original_roi_refinement_cases.add(case.label)
                    if str(event.get("target_id", "")).startswith("ekg_systematic_"):
                        inventory.ekg_systematic_completed_cases.add(case.label)
                        if event.get("crop_source") == "original_roi":
                            inventory.original_roi_ekg_systematic_cases.add(case.label)
                tool_audit = event.get("tool_audit")
                if isinstance(tool_audit, list) and any(
                    _valid_bound_bbox_receipt(record, event)
                    for record in tool_audit
                ):
                    inventory.refinement_bbox_tool_accepted_cases.add(case.label)
                decisions = event.get("decisions")
                if isinstance(decisions, list) and any(
                    isinstance(decision, dict)
                    and decision.get("action")
                    in {"confirm", "revise", "retract", "add"}
                    and isinstance(decision.get("rationale"), str)
                    and bool(decision["rationale"].strip())
                    for decision in decisions
                ):
                    inventory.refinement_decision_cases.add(case.label)

    if inventory.cases != set(expected_cases):
        failures.append("results_artifacts: result case set is not exact")
    if missing_preflight:
        failures.append(
            "local_preflight_artifacts: missing local_image_quality in "
            + ", ".join(missing_preflight[:5])
        )
    else:
        passed.append("local_preflight_artifacts")
    if missing_signal_candidates and require_model_assist:
        failures.append(
            "model_assist_artifacts: missing local_signal_candidates in "
            + ", ".join(missing_signal_candidates[:5])
        )
    elif require_model_assist:
        passed.append("model_assist_artifacts")
    else:
        passed.append("control_model_assist_disabled")
    if len(failures) == failure_count:
        passed.append("results_artifacts")
    return inventory


def _bbox_payload_digest(findings: list[object]) -> tuple[str, int]:
    coordinates: list[list[str]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        bboxes = finding.get("bboxes")
        if not isinstance(bboxes, list):
            continue
        for box in bboxes:
            if not isinstance(box, dict):
                continue
            try:
                values = [
                    math.floor(float(box[key]) * 10_000 + 0.5) / 10_000
                    for key in ("x", "y", "w", "h")
                ]
            except (KeyError, TypeError, ValueError):
                continue
            coordinates.append([f"{value:.4f}" for value in values])
    coordinates.sort()
    encoded = json.dumps(coordinates, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), len(coordinates)


def _valid_bound_bbox_receipt(
    record: object,
    event: dict[str, Any],
    *,
    expected_source_image_sha256: str = "",
    expected_boxes_sha256: str = "",
    expected_count: int | None = None,
) -> bool:
    if not isinstance(record, dict) or record.get("schema_version") != 2:
        return False
    binding = event.get("bbox_evidence")
    if not isinstance(binding, dict):
        return False
    accepted_count = record.get("accepted_count")
    source_sha = record.get("source_image_sha256")
    nonce = record.get("evidence_nonce")
    boxes_sha = record.get("accepted_boxes_sha256")
    if not (
        record.get("tool") == "dicom_bbox_validate"
        and isinstance(accepted_count, int)
        and not isinstance(accepted_count, bool)
        and accepted_count > 0
        and _is_sha256(source_sha)
        and _is_sha256(boxes_sha)
        and isinstance(nonce, str)
        and len(nonce) == 32
        and all(character in "0123456789abcdef" for character in nonce)
        and binding.get("source_image_sha256") == source_sha
        and binding.get("evidence_nonce") == nonce
    ):
        return False
    if expected_source_image_sha256 and source_sha != expected_source_image_sha256:
        return False
    if expected_boxes_sha256 and boxes_sha != expected_boxes_sha256:
        return False
    return expected_count is None or accepted_count == expected_count


def _verify_ekg_systematic_probes(
    results: _ResultInventory,
    *,
    require: bool,
    failures: list[str],
    passed: list[str],
) -> None:
    if not require:
        return
    if not results.ekg_cases:
        failures.append("ekg_systematic_probe_artifacts: no EKG result cases")
        return
    missing_planned = sorted(results.ekg_cases - results.ekg_systematic_planned_cases)
    missing_completed = sorted(
        results.ekg_cases - results.ekg_systematic_completed_cases
    )
    missing_original = sorted(
        results.ekg_cases - results.original_roi_ekg_systematic_cases
    )
    if missing_planned:
        failures.append(
            "ekg_systematic_probe_artifacts: no planned discovery probe for "
            + ", ".join(missing_planned[:5])
        )
    if missing_completed:
        failures.append(
            "ekg_systematic_probe_artifacts: no completed discovery probe for "
            + ", ".join(missing_completed[:5])
        )
    if missing_original:
        failures.append(
            "ekg_systematic_probe_artifacts: discovery probe did not use "
            "original_roi for " + ", ".join(missing_original[:5])
        )
    if not (missing_planned or missing_completed or missing_original):
        passed.append("ekg_systematic_probe_artifacts")


def _canonical_ekg_region(value: object) -> str | None:
    name = str(value or "").strip()
    if name == "rhythm_strip":
        return name
    return canonical_ekg_lead_name(name)


def _ekg_layout_regions(layout: object) -> list[tuple[str, tuple[float, ...]]]:
    if not isinstance(layout, dict):
        return []
    regions: list[tuple[str, tuple[float, ...]]] = [
        (
            lead.name,
            (lead.bbox.x, lead.bbox.y, lead.bbox.w, lead.bbox.h),
        )
        for lead in parse_ekg_lead_inventory(layout).leads
    ]
    rhythm = _normalized_box_tuple(layout.get("rhythm_strip_bbox"))
    if rhythm is not None:
        regions.append(("rhythm_strip", rhythm))
    return regions


def _normalized_box_tuple(value: object) -> tuple[float, float, float, float] | None:
    region = parse_normalized_region(value)
    if region is None:
        return None
    return region.x, region.y, region.w, region.h


def _ekg_bbox_lead_mismatch(finding: dict[str, Any], *, layout: object) -> str:
    declared = {
        region
        for value in finding.get("regions") or []
        if (region := _canonical_ekg_region(value)) is not None
    }
    layout_regions = _ekg_layout_regions(layout)
    if not declared or not layout_regions:
        return ""
    for index, box in enumerate(finding.get("bboxes") or [], start=1):
        if not isinstance(box, dict) or not _is_normalized_region(box):
            continue
        center_x = float(box["x"]) + float(box["w"]) / 2.0
        center_y = float(box["y"]) + float(box["h"]) / 2.0
        candidates = [
            (name, region)
            for name, region in layout_regions
            if region[0] <= center_x <= region[0] + region[2]
            and region[1] <= center_y <= region[1] + region[3]
        ]
        if not candidates:
            continue
        actual = min(candidates, key=lambda item: item[1][2] * item[1][3])[0]
        if actual not in declared:
            return f"bbox {index} is in {actual}, declared={sorted(declared)}"
    return ""


def _verify_review_artifacts(
    review_dir: Path,
    *,
    results: _ResultInventory,
    failures: list[str],
    passed: list[str],
    require_projection_audit: bool,
) -> None:
    failure_count = len(failures)
    index_path = review_dir / "index.html"
    audit_path = review_dir / "bbox-audit.jsonl"
    if not index_path.is_file():
        failures.append("review_artifacts: missing index.html")
    if not audit_path.is_file():
        failures.append("review_artifacts: missing bbox-audit.jsonl")
        return

    expected_pngs = {f"{_safe_filename(case)}.review.png" for case in results.cases}
    png_paths = sorted(review_dir.glob("*.review.png"))
    actual_pngs = {path.name for path in png_paths}
    if actual_pngs != expected_pngs or len(png_paths) != len(results.cases):
        failures.append(
            "review_artifacts: review PNG set does not exactly match result cases"
        )
    for path in png_paths:
        try:
            with Image.open(path) as image:
                if image.format != "PNG" or image.width <= 0 or image.height <= 0:
                    raise ValueError("not a non-empty PNG")
                image.verify()
        except Exception as exc:
            failures.append(f"review_artifacts: unreadable PNG {path.name}: {exc}")

    rows: list[dict[str, Any]] = []
    for index, line in enumerate(
        audit_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            failures.append(
                f"review_artifacts: bbox-audit contains invalid JSONL row {index}"
            )
            continue
        if not isinstance(row, dict):
            failures.append(f"review_artifacts: audit row {index} is not an object")
            continue
        rows.append(row)

    rows_by_case: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(rows, start=1):
        case = row.get("case")
        if not isinstance(case, str) or case not in results.cases:
            failures.append(f"review_artifacts: unknown case in audit row {index}")
            continue
        expected_review = f"{_safe_filename(case)}.review.png"
        if row.get("review_image") != expected_review:
            failures.append(
                f"review_artifacts: review_image mismatch in audit row {index}"
            )
        rows_by_case.setdefault(case, []).append(row)
    if set(rows_by_case) != results.cases:
        failures.append("review_artifacts: bbox audit case set is not exact")

    for case in sorted(results.cases):
        case_rows = rows_by_case.get(case, [])
        bbox_rows = [row for row in case_rows if row.get("audit_type") == "bbox"]
        case_markers = [row for row in case_rows if row.get("audit_type") == "case"]
        expected_bbox_count = results.bbox_counts.get(case, 0)
        if len(bbox_rows) != expected_bbox_count:
            failures.append(
                "review_artifacts: "
                f"{case} has {len(bbox_rows)} bbox audit rows, expected "
                f"{expected_bbox_count}"
            )
        if expected_bbox_count == 0:
            if len(case_markers) != 1 or case_markers[0].get("bbox_count") != 0:
                failures.append(
                    f"review_artifacts: {case} lacks one zero-bbox case marker"
                )
        elif case_markers:
            failures.append(
                f"review_artifacts: {case} has unexpected case-level audit markers"
            )
        keys = [(row.get("finding_index"), row.get("bbox_index")) for row in bbox_rows]
        if len(set(keys)) != len(keys):
            failures.append(f"review_artifacts: duplicate bbox audit key for {case}")

    if len(failures) == failure_count:
        passed.append("review_artifacts")
    if require_projection_audit:
        _verify_projection_audit_rows(rows, failures, passed)


def _verify_projection_audit_rows(
    rows: list[dict[str, Any]],
    failures: list[str],
    passed: list[str],
) -> None:
    required_fields = (
        "normalized",
        "pixels",
        "width_px",
        "height_px",
        "invalid_reason",
        "was_clamped",
        "projection_ok",
        "projection_max_edge_drift_px",
        "projection_was_clamped",
        "projection_back_projected_bbox",
    )
    bbox_rows = [row for row in rows if row.get("audit_type") == "bbox"]
    for index, row in enumerate(bbox_rows, start=1):
        missing = [field for field in required_fields if field not in row]
        if missing:
            failures.append(
                "projection_audit_artifacts: "
                f"bbox row {index} missing {', '.join(missing)}"
            )
            return
        if row.get("projection_ok") is not True:
            failures.append(
                f"projection_audit_artifacts: bbox row {index} projection_ok is not true"
            )
            return
        if row.get("invalid_reason") not in ("", None):
            failures.append(
                f"projection_audit_artifacts: bbox row {index} is invalid/clamped"
            )
            return
        if row.get("was_clamped") is not False:
            failures.append(
                f"projection_audit_artifacts: bbox row {index} was source-clamped"
            )
            return
        if row.get("projection_was_clamped") is not False:
            failures.append(f"projection_audit_artifacts: bbox row {index} was clamped")
            return
        if not _is_normalized_region(row.get("normalized")):
            failures.append(
                f"projection_audit_artifacts: bbox row {index} is degenerate/out of bounds"
            )
            return
        if not _positive_pixel_box(row):
            failures.append(
                f"projection_audit_artifacts: bbox row {index} has zero pixel area"
            )
            return
        drift = row.get("projection_max_edge_drift_px")
        if (
            not isinstance(drift, int | float)
            or isinstance(drift, bool)
            or not math.isfinite(float(drift))
            or drift < 0
        ):
            failures.append(
                f"projection_audit_artifacts: bbox row {index} drift is invalid"
            )
            return
        if not _is_normalized_region(row.get("projection_back_projected_bbox")):
            failures.append(
                "projection_audit_artifacts: "
                f"bbox row {index} back-projected bbox is invalid"
            )
            return
    passed.append("projection_audit_artifacts")


def _positive_pixel_box(row: dict[str, Any]) -> bool:
    width = row.get("width_px")
    height = row.get("height_px")
    pixels = row.get("pixels")
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or width <= 0
        or not isinstance(height, int)
        or isinstance(height, bool)
        or height <= 0
        or not isinstance(pixels, dict)
    ):
        return False
    try:
        x0 = int(pixels["x0"])
        y0 = int(pixels["y0"])
        x1 = int(pixels["x1"])
        y1 = int(pixels["y1"])
    except (KeyError, TypeError, ValueError):
        return False
    return x1 - x0 == width and y1 - y0 == height


def _verify_multipass_trace(
    trace_path: Path,
    *,
    require: bool,
    require_refinement: bool,
    results: _ResultInventory,
    failures: list[str],
    passed: list[str],
) -> None:
    if not trace_path.exists():
        if require:
            failures.append("multipass_trace_artifacts: missing multipass-trace.jsonl")
        return
    lines = [
        line for line in trace_path.read_text(encoding="utf-8").splitlines() if line
    ]
    trace_cases: set[str] = set()
    counters_by_case: dict[str, dict[str, int]] = {}
    candidates_by_case: dict[str, int] = {}
    for index, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            failures.append(f"multipass_trace_artifacts: invalid JSONL row {index}")
            return
        if not isinstance(row, dict):
            failures.append(f"multipass_trace_artifacts: row {index} is not an object")
            return
        case = row.get("case")
        if not isinstance(case, str) or not case:
            failures.append(f"multipass_trace_artifacts: row {index} missing case")
            return
        trace_cases.add(case)
        count = row.get("local_candidate_count")
        regions = row.get("local_candidate_regions")
        if not isinstance(count, int) or isinstance(count, bool):
            failures.append(
                f"multipass_trace_artifacts: row {index} missing local_candidate_count"
            )
            return
        if not isinstance(regions, list):
            failures.append(
                f"multipass_trace_artifacts: row {index} missing local_candidate_regions"
            )
            return
        if count != len(regions):
            failures.append(
                "multipass_trace_artifacts: "
                f"row {index} local_candidate_count={count} but regions={len(regions)}"
            )
            return
        for region_index, region in enumerate(regions, start=1):
            if not _is_normalized_region(region):
                failures.append(
                    "multipass_trace_artifacts: "
                    f"row {index} region {region_index} is not normalized"
                )
                return
        counters = counters_by_case.setdefault(
            case,
            {
                "openclaw_analyze_calls": 0,
                "coarse_passes": 0,
                "zoom_passes": 0,
                "crop_calls": 0,
            },
        )
        for key in counters:
            value = row.get(key, 0)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                failures.append(
                    "multipass_trace_artifacts: "
                    f"row {index} has invalid {key}={value!r}"
                )
                return
            counters[key] += value
        candidates_by_case[case] = max(candidates_by_case.get(case, 0), count)
    if require and trace_cases != results.cases:
        failures.append(
            "multipass_trace_artifacts: trace case set does not exactly match results"
        )
        return
    passed.append("multipass_trace_artifacts")
    if not require_refinement:
        return

    evidence_cases = {
        case
        for case in results.cases
        if candidates_by_case.get(case, 0) > 0 or results.bbox_counts.get(case, 0) > 0
    }
    missing_turns: list[str] = []
    missing_completed: list[str] = []
    missing_original_roi: list[str] = []
    missing_decisions: list[str] = []
    missing_bbox_tool: list[str] = []
    missing_accepted_bbox_tool: list[str] = []
    missing_finalization: list[str] = []
    missing_original_roi_finalization: list[str] = []
    missing_finalization_bbox_tool: list[str] = []
    for case in sorted(evidence_cases):
        counters = counters_by_case.get(case, {})
        if (
            counters.get("crop_calls", 0) < 1
            or counters.get("zoom_passes", 0) < 1
            or counters.get("openclaw_analyze_calls", 0)
            <= counters.get("coarse_passes", 0)
        ):
            missing_turns.append(case)
        if case not in results.refinement_completed_cases:
            missing_completed.append(case)
        if case not in results.original_roi_refinement_cases:
            missing_original_roi.append(case)
        if case not in results.finalization_completed_cases:
            missing_finalization.append(case)
        if case not in results.original_roi_finalization_cases:
            missing_original_roi_finalization.append(case)
        if results.bbox_counts.get(case, 0) > 0:
            if case not in results.refinement_decision_cases:
                missing_decisions.append(case)
            if case not in results.bbox_tool_cases:
                missing_bbox_tool.append(case)
            if case not in results.refinement_bbox_tool_accepted_cases:
                missing_accepted_bbox_tool.append(case)
            if case not in results.finalization_bbox_tool_accepted_cases:
                missing_finalization_bbox_tool.append(case)
    if missing_turns:
        failures.append(
            "multipass_refinement_artifacts: no real crop/refine model turn for "
            + ", ".join(missing_turns[:5])
        )
    if missing_completed:
        failures.append(
            "multipass_refinement_artifacts: no completed crop trace for "
            + ", ".join(missing_completed[:5])
        )
    if missing_original_roi:
        failures.append(
            "multipass_refinement_artifacts: refinement did not use original_roi for "
            + ", ".join(missing_original_roi[:5])
        )
    if missing_finalization:
        failures.append(
            "multipass_refinement_artifacts: no completed final report turn for "
            + ", ".join(missing_finalization[:5])
        )
    if missing_original_roi_finalization:
        failures.append(
            "multipass_refinement_artifacts: final report did not use original_roi for "
            + ", ".join(missing_original_roi_finalization[:5])
        )
    if missing_decisions:
        failures.append(
            "multipass_refinement_artifacts: boxed findings lack an evidence "
            "decision for " + ", ".join(missing_decisions[:5])
        )
    if missing_bbox_tool:
        failures.append(
            "multipass_refinement_artifacts: boxed findings lack actual "
            "dicom_bbox_validate use for " + ", ".join(missing_bbox_tool[:5])
        )
    if missing_accepted_bbox_tool:
        failures.append(
            "multipass_refinement_artifacts: boxed findings lack an accepted "
            "dicom_bbox_validate refinement receipt for "
            + ", ".join(missing_accepted_bbox_tool[:5])
        )
    if missing_finalization_bbox_tool:
        failures.append(
            "multipass_refinement_artifacts: final boxed report lacks an accepted "
            "dicom_bbox_validate receipt for "
            + ", ".join(missing_finalization_bbox_tool[:5])
        )
    if not any(
        (
            missing_turns,
            missing_completed,
            missing_original_roi,
            missing_finalization,
            missing_original_roi_finalization,
            missing_decisions,
            missing_bbox_tool,
            missing_accepted_bbox_tool,
            missing_finalization_bbox_tool,
        )
    ):
        passed.append("multipass_refinement_artifacts")


def _is_normalized_region(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        x = float(value["x"])
        y = float(value["y"])
        w = float(value["w"])
        h = float(value["h"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        all(math.isfinite(item) for item in (x, y, w, h))
        and 0.0 <= x <= 1.0
        and 0.0 <= y <= 1.0
        and 0.0 < w <= 1.0
        and 0.0 < h <= 1.0
        and x + w <= 1.0 + 1e-6
        and y + h <= 1.0 + 1e-6
    )


def _result_filename(label: str) -> str:
    return f"{_safe_filename(label)}.json"


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    return safe or "case"


def _int_value(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
