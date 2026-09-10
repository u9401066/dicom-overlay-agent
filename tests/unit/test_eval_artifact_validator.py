from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from PIL import Image

from dicom_overlay.infrastructure.ecg_variant_corpus import (
    EKG_CHECKLIST_AXES,
    build_variant_corpus,
    parse_partial_ecg_input_contract,
)
from dicom_overlay.infrastructure.eval_artifact_validator import (
    _bbox_payload_digest,
    _valid_ecg_founder_evidence,
    verify_eval_artifacts,
)

if TYPE_CHECKING:
    from pathlib import Path


def _gateway_protocol_receipt() -> dict[str, object]:
    return {
        "verified": True,
        "advertised_min_protocol": 3,
        "advertised_max_protocol": 4,
        "negotiated_protocol": 4,
        "server_version": "2026.7.1-2",
    }


def _ecg_receipt() -> dict[str, object]:
    predictions = [{"label": "NORMAL SINUS RHYTHM", "probability": 0.9}]
    response_evidence = {
        "schema_version": 1,
        "status": "ok",
        "evidence_type": "ecg_waveform_classification",
        "lead_mode": "12_lead",
        "evidence_nonce": "d" * 32,
        "artifact_id_sha256": "a" * 64,
        "use_policy": "supporting_evidence_only",
        "spatial_localization": "not_provided",
        "model": {
            "id": "PKUDigitalHealth/ECGFounder",
            "revision": "04edac702b61c91face519774ddcc0cd712fef23",
            "checkpoint_sha256": (
                "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997"
            ),
        },
        "input": {"source_sha256": "b" * 64},
        "preprocessing": {"implementation_revision": "preprocess-v1"},
        "calibration": {"status": "uncalibrated", "revision": ""},
        "predictions": predictions,
    }
    return {
        "schema_version": 1,
        "tool": "ecg_founder_analyze_waveform",
        "tool_call_id": "call-1",
        "status": "ok",
        "evidence_nonce": "d" * 32,
        "artifact_id_sha256": "a" * 64,
        "lead_mode": "12_lead",
        "model_id": "PKUDigitalHealth/ECGFounder",
        "model_revision": "04edac702b61c91face519774ddcc0cd712fef23",
        "checkpoint_sha256": (
            "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997"
        ),
        "source_sha256": "b" * 64,
        "response_evidence": response_evidence,
        "response_sha256": hashlib.sha256(
            json.dumps(
                response_evidence,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "preprocessing_revision": "preprocess-v1",
        "calibration_status": "uncalibrated",
        "calibration_revision": "",
        "prediction_count": 1,
        "predictions": predictions,
    }


def _ineligible_ecg_receipt(
    reason: str = "waveform_contains_flat_lead",
) -> dict[str, object]:
    response_evidence = {
        "schema_version": 1,
        "status": "ineligible",
        "evidence_type": "ecg_waveform_classification",
        "lead_mode": "12_lead",
        "evidence_nonce": "d" * 32,
        "artifact_id_sha256": "a" * 64,
        "use_policy": "supporting_evidence_only",
        "spatial_localization": "not_provided",
        "limitations": ["No waveform classification evidence is available."],
        "reason": reason,
        "predictions": [],
    }
    return {
        "schema_version": 1,
        "tool": "ecg_founder_analyze_waveform",
        "tool_call_id": "call-ineligible",
        "status": "ineligible",
        "evidence_nonce": "d" * 32,
        "artifact_id_sha256": "a" * 64,
        "lead_mode": "12_lead",
        "response_evidence": response_evidence,
        "response_sha256": hashlib.sha256(
            json.dumps(
                response_evidence,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "prediction_count": 0,
        "predictions": [],
        "failure_reason": reason,
    }


def test_ecgfounder_evidence_requires_one_matching_pinned_receipt() -> None:
    receipt = _ecg_receipt()
    evidence = {
        "requested": True,
        "verified_exactly_once": True,
        "artifact_id_sha256": "a" * 64,
        "lead_mode": "12_lead",
        "evidence_nonce": "d" * 32,
        "receipt_count": 1,
        "receipts": [receipt],
    }

    assert (
        _valid_ecg_founder_evidence(
            evidence,
            expected_artifact_sha256="a" * 64,
        )
        is True
    )
    assert (
        _valid_ecg_founder_evidence(
            evidence,
            expected_artifact_sha256="f" * 64,
        )
        is False
    )
    receipt["evidence_nonce"] = "e" * 32
    assert _valid_ecg_founder_evidence(evidence) is False
    receipt["evidence_nonce"] = "d" * 32
    evidence["receipts"] = [receipt, receipt]
    evidence["receipt_count"] = 2
    assert _valid_ecg_founder_evidence(evidence) is False


def test_ecgfounder_evidence_accepts_bound_data_ineligibility_receipt() -> None:
    receipt = _ineligible_ecg_receipt()
    evidence = {
        "requested": True,
        "verified_exactly_once": True,
        "evidence_status": "ineligible",
        "usable": False,
        "ineligible_reason": "waveform_contains_flat_lead",
        "artifact_id_sha256": "a" * 64,
        "lead_mode": "12_lead",
        "evidence_nonce": "d" * 32,
        "receipt_count": 1,
        "receipts": [receipt],
    }

    assert _valid_ecg_founder_evidence(evidence) is True
    receipt["failure_reason"] = "artifact_not_registered"
    response = receipt["response_evidence"]
    assert isinstance(response, dict)
    response["reason"] = "artifact_not_registered"
    receipt["response_sha256"] = hashlib.sha256(
        json.dumps(response, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert _valid_ecg_founder_evidence(evidence) is False


def test_ecgfounder_response_hash_cannot_mask_provenance_disagreement() -> None:
    receipt = _ecg_receipt()
    evidence = {
        "requested": True,
        "verified_exactly_once": True,
        "artifact_id_sha256": "a" * 64,
        "lead_mode": "12_lead",
        "evidence_nonce": "d" * 32,
        "receipt_count": 1,
        "receipts": [receipt],
    }
    response = receipt["response_evidence"]
    assert isinstance(response, dict)
    model = response["model"]
    assert isinstance(model, dict)
    model["revision"] = "tampered-revision"
    receipt["response_sha256"] = hashlib.sha256(
        json.dumps(response, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    assert _valid_ecg_founder_evidence(evidence) is False


def _write_minimal_eval(
    eval_dir: Path,
    manifest_path: Path,
    count: int = 2,
    *,
    ecgfounder: bool = False,
    defer_scoring: bool = False,
) -> None:
    manifest_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "label": f"case_{index}",
                        "image": f"case_{index}.png",
                        **(
                            {"waveform_artifact_id": f"wf-case-{index}"}
                            if ecgfounder
                            else {}
                        ),
                    }
                    for index in range(count)
                ]
            }
        ),
        encoding="utf-8",
    )
    image_hashes: dict[str, str] = {}
    image_sizes: dict[str, int] = {}
    for index in range(count):
        image_path = manifest_path.parent / f"case_{index}.png"
        Image.new("RGB", (20, 20), "white").save(image_path)
        image_hashes[f"case_{index}"] = hashlib.sha256(
            image_path.read_bytes()
        ).hexdigest()
        image_sizes[f"case_{index}"] = image_path.stat().st_size
    protocol = {
        "source": {
            "commit": "abc123",
            "dirty": False,
            "tracked_diff_sha256": hashlib.sha256(b"").hexdigest(),
        },
        "model": {
            "id": "mock-eval-gateway",
            "openclaw": {"version": "test"},
        },
        "prompts": [{"path": "prompt.py", "sha256": "0" * 64}],
        "skills": [{"path": "skills/test/SKILL.md", "sha256": "1" * 64}],
        "flags": {
            "multi_pass": False,
            "defer_scoring": defer_scoring,
            "ecgfounder_waveform_evidence": ecgfounder,
            "ecgfounder_preprocessing_revision": (
                "preprocess-v1" if ecgfounder else ""
            ),
        },
        "manifest": {
            "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "selected_case_count": count,
            "cases": [
                {
                    "case": f"case_{index}",
                    "image": f"case_{index}.png",
                    "image_name": f"case_{index}.png",
                    "size_bytes": image_sizes[f"case_{index}"],
                    "sha256": image_hashes[f"case_{index}"],
                }
                for index in range(count)
            ],
        },
    }
    protocol_digest = hashlib.sha256(
        json.dumps(
            protocol,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    eval_dir.mkdir(parents=True)
    (eval_dir / "protocol-fingerprint.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "protocol_scope": "entire_run",
                "protocol_digest": protocol_digest,
                "comparability": {
                    "status": "comparable",
                    "comparable": True,
                    "reasons": [],
                },
                "protocol": protocol,
            }
        ),
        encoding="utf-8",
    )
    (eval_dir / "scorecard.json").write_text(
        json.dumps(
            {
                "gateway_mode": "mock",
                "scorecard_kind": "full_rebuild",
                "manifest_total": count,
                "result_count": count,
                "total": count,
                "scored": count,
                "error_count": 0,
                "is_partial": False,
                "schema_pass_rate": 1.0,
                "bbox_in_bounds_rate": 1.0,
                "cant_miss_missed": [],
                "strict_pass_rate": 1.0,
                "mean_partial_credit": 1.0,
                "missing_cases": [],
                "protocol_digest": protocol_digest,
                "protocol_comparability": {
                    "status": "comparable",
                    "comparable": True,
                    "reasons": [],
                },
                "cases": [{"case_label": f"case_{index}"} for index in range(count)],
            }
        ),
        encoding="utf-8",
    )
    results = eval_dir / "results"
    results.mkdir()
    for index in range(count):
        (results / f"case_{index}.json").write_text(
            json.dumps(
                {
                    "case": f"case_{index}",
                    "image": f"case_{index}.png",
                    "protocol_digest": protocol_digest,
                    "source_image_sha256": image_hashes[f"case_{index}"],
                    "gateway_protocol_receipt": _gateway_protocol_receipt(),
                    "findings": [
                        {
                            "id": "f1",
                            "bboxes": [{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.2}],
                        }
                    ],
                    "local_image_quality": {"low_signal": False},
                    "local_signal_candidates": {
                        "candidate_count": 1,
                        "candidates": [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}],
                    },
                }
            ),
            encoding="utf-8",
        )
    review = eval_dir / "review"
    review.mkdir()
    (review / "index.html").write_text("<html></html>", encoding="utf-8")
    for index in range(count):
        Image.new("RGB", (40, 20), "white").save(review / f"case_{index}.review.png")
    (review / "bbox-audit.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "audit_type": "bbox",
                    "case": f"case_{index}",
                    "finding_index": 1,
                    "bbox_index": 1,
                    "review_image": f"case_{index}.review.png",
                }
            )
            + "\n"
            for index in range(count)
        ),
        encoding="utf-8",
    )


def _write_partial_ecg_eval(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "source.png"
    Image.new("RGB", (120, 120), "white").save(source)
    corpus = tmp_path / "partial-corpus"
    manifest = build_variant_corpus([source], corpus)
    manifest_path = corpus / "manifest.json"
    entry = manifest["cases"][0]
    image_path = corpus / entry["image"]
    contract = parse_partial_ecg_input_contract(entry, image_path=image_path)
    assert contract is not None
    label = entry["label"]
    image_sha = contract.variant_sha256
    protocol = {
        "source": {
            "commit": "abc123",
            "dirty": False,
            "tracked_diff_sha256": hashlib.sha256(b"").hexdigest(),
        },
        "model": {"id": "mock-eval-gateway", "openclaw": {"version": "test"}},
        "prompts": [{"path": "prompt.py", "sha256": "0" * 64}],
        "skills": [{"path": "skills/test/SKILL.md", "sha256": "1" * 64}],
        "flags": {
            "multi_pass": True,
            "analysis_prompt_profile": "clinical",
            "partial_ecg_case_count": 1,
        },
        "manifest": {
            "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "selected_case_count": 1,
            "cases": [
                {
                    "case": label,
                    "image": entry["image"],
                    "image_name": image_path.name,
                    "size_bytes": image_path.stat().st_size,
                    "sha256": image_sha,
                }
            ],
        },
    }
    protocol_digest = hashlib.sha256(
        json.dumps(
            protocol,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "protocol-fingerprint.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "protocol_scope": "entire_run",
                "protocol_digest": protocol_digest,
                "comparability": {
                    "status": "comparable",
                    "comparable": True,
                    "reasons": [],
                },
                "protocol": protocol,
            }
        ),
        encoding="utf-8",
    )
    (eval_dir / "scorecard.json").write_text(
        json.dumps(
            {
                "gateway_mode": "mock",
                "scorecard_kind": "full_rebuild",
                "manifest_total": 1,
                "result_count": 1,
                "total": 1,
                "scored": 1,
                "error_count": 0,
                "is_partial": False,
                "schema_pass_rate": 1.0,
                "bbox_in_bounds_rate": 1.0,
                "cant_miss_missed": [],
                "urgent_concern_missed": [],
                "strict_pass_rate": 0.0,
                "mean_partial_credit": 0.0,
                "partial_input_case_count": 1,
                "partial_input_contract_pass_count": 1,
                "partial_input_contract_pass_rate": 1.0,
                "missing_cases": [],
                "protocol_digest": protocol_digest,
                "protocol_comparability": {
                    "status": "comparable",
                    "comparable": True,
                    "reasons": [],
                },
                "cases": [{"case_label": label}],
            }
        ),
        encoding="utf-8",
    )
    results = eval_dir / "results"
    results.mkdir()
    result_path = results / f"{label}.json"
    result_path.write_text(
        json.dumps(
            {
                "case": label,
                "image": image_path.name,
                "modality": "EKG",
                "protocol_digest": protocol_digest,
                "source_image_sha256": image_sha,
                "gateway_protocol_receipt": _gateway_protocol_receipt(),
                "declared_valid_regions": [],
                "analysis_valid_regions": list(contract.analysis_regions),
                "partial_input_provenance": contract.to_manifest_payload(),
                "summary": "Incomplete ECG: the top edge is cropped.",
                "severity": "normal",
                "findings": [],
                "checklist": {
                    axis: {"value": "not_assessable", "status": "info"}
                    for axis in EKG_CHECKLIST_AXES
                },
                "layout": {"format": "partial", "leads": []},
                "incomplete": True,
                "incomplete_reasons": ["The top edge is cropped."],
                "review_required": True,
                "review_reasons": ["Incomplete ECG requires human review."],
                "analysis_trace": [],
                "local_image_quality": {"low_signal": False},
                "local_signal_candidates": {
                    "candidate_count": 0,
                    "candidates": [],
                },
                "score": {
                    "image": image_path.name,
                    "partial_input_expected": True,
                    "partial_input_contract_ok": True,
                    "partial_input_failures": [],
                    "partial_variant_sha256": image_sha,
                    "bbox_receipt_matches_variant": None,
                    "partial_limitation_class": contract.limitation_class,
                    "partial_limitation_class_verified": True,
                },
            }
        ),
        encoding="utf-8",
    )
    return eval_dir, manifest_path, result_path


def test_partial_ecg_artifacts_enforce_visibility_review_and_variant_receipt(
    tmp_path: Path,
) -> None:
    eval_dir, manifest_path, result_path = _write_partial_ecg_eval(tmp_path)

    accepted = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=1,
        require_review=False,
        require_perfect_mock=False,
    )

    assert accepted.ok is True
    assert "partial_ecg_manifest_contract" in accepted.passed_checks
    assert "partial_ecg_contract" in accepted.passed_checks

    raw = json.loads(result_path.read_text(encoding="utf-8"))
    box = {"x": 0.2, "y": 0.3, "w": 0.1, "h": 0.1}
    raw["findings"] = [{"id": "f1", "regions": ["lead_I"], "bboxes": [box]}]
    raw["layout"] = {"format": "12lead_12x1", "leads": []}
    raw["incomplete"] = False
    raw["incomplete_reasons"] = []
    raw["checklist"] = {
        axis: {"value": "normal", "status": "warning"} for axis in EKG_CHECKLIST_AXES
    }
    raw["summary"] += " Claimed abnormality in V3."
    boxes_digest, _count = _bbox_payload_digest(raw["findings"])
    nonce = "d" * 32
    raw["analysis_trace"] = [
        {
            "stage": "finalize",
            "status": "completed",
            "source": "original_roi",
            "bbox_evidence": {
                "source_image_sha256": "0" * 64,
                "evidence_nonce": nonce,
            },
            "tool_audit": [
                {
                    "schema_version": 2,
                    "tool": "dicom_bbox_validate",
                    "accepted_count": 1,
                    "source_image_sha256": "0" * 64,
                    "evidence_nonce": nonce,
                    "accepted_boxes_sha256": boxes_digest,
                }
            ],
        }
    ]
    raw["score"]["bbox_receipt_matches_variant"] = False
    result_path.write_text(json.dumps(raw), encoding="utf-8")

    rejected = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=1,
        require_review=False,
        require_perfect_mock=False,
    )

    assert rejected.ok is False
    assert any("explicitly incomplete" in item for item in rejected.failures)
    assert any("invisible/unverified regions" in item for item in rejected.failures)
    assert any("non-claimable leads" in item for item in rejected.failures)
    assert any("unverified named regions" in item for item in rejected.failures)
    assert any("falsely assessable/normal" in item for item in rejected.failures)
    assert any("variant_sha256" in item for item in rejected.failures)


def test_partial_ecg_artifacts_recompute_limitation_class_instead_of_trusting_score(
    tmp_path: Path,
) -> None:
    eval_dir, manifest_path, result_path = _write_partial_ecg_eval(tmp_path)
    raw = json.loads(result_path.read_text(encoding="utf-8"))
    raw["summary"] = "Incomplete ECG image."
    raw["incomplete_reasons"] = ["Image content is incomplete."]
    raw["review_reasons"] = ["Incomplete ECG requires human review."]
    raw["score"]["partial_limitation_class_verified"] = True
    result_path.write_text(json.dumps(raw), encoding="utf-8")

    rejected = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=1,
        require_review=False,
        require_perfect_mock=False,
    )

    assert rejected.ok is False
    assert any(
        "transform-specific limitation class" in item for item in rejected.failures
    )
    assert any("score receipt is inconsistent" in item for item in rejected.failures)


def test_partial_ecg_artifacts_reject_manifest_allow_list_drift(
    tmp_path: Path,
) -> None:
    eval_dir, manifest_path, _result_path = _write_partial_ecg_eval(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metadata"] = "unexpected"
    digest_payload = dict(manifest)
    digest_payload.pop("manifest_sha256")
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(
            digest_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    rejected = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=1,
        require_review=False,
        require_perfect_mock=False,
    )

    assert rejected.ok is False
    assert any(
        failure.startswith("partial_ecg_manifest_contract: ")
        and "closed allow-list" in failure
        for failure in rejected.failures
    )


def test_accuracy_and_partial_credit_thresholds_gate_real_completion(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    scorecard_path = eval_dir / "scorecard.json"
    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    scorecard["gateway_mode"] = "real"
    scorecard["strict_pass_rate"] = 0.74
    scorecard["mean_partial_credit"] = 0.84
    scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
        min_strict_pass_rate=0.75,
        min_mean_partial_credit=0.85,
    )

    assert verification.ok is False
    assert any(
        failure.startswith("strict_accuracy_gate:") for failure in verification.failures
    )
    assert any(
        failure.startswith("partial_credit_gate:") for failure in verification.failures
    )


def test_accuracy_thresholds_accept_rates_at_target(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
        min_strict_pass_rate=1.0,
        min_mean_partial_credit=1.0,
    )

    assert verification.ok is True
    assert "strict_accuracy_gate" in verification.passed_checks
    assert "partial_credit_gate" in verification.passed_checks


def test_eval_artifacts_reject_unverified_gateway_protocol_receipt(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path, count=1)
    result_path = eval_dir / "results" / "case_0.json"
    raw = json.loads(result_path.read_text(encoding="utf-8"))
    raw["gateway_protocol_receipt"]["negotiated_protocol"] = 5
    result_path.write_text(json.dumps(raw), encoding="utf-8")

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=1,
        require_review=False,
    )

    assert verification.ok is False
    assert any(
        failure.startswith("gateway_protocol_receipts:")
        for failure in verification.failures
    )


def test_eval_artifacts_reject_fake_gateway_server_version(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path, count=1)
    result_path = eval_dir / "results" / "case_0.json"
    raw = json.loads(result_path.read_text(encoding="utf-8"))
    raw["gateway_protocol_receipt"]["server_version"] = "mock-2026.7.1-2"
    result_path.write_text(json.dumps(raw), encoding="utf-8")

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=1,
        require_review=False,
    )

    assert verification.ok is False
    assert any(
        failure.startswith("gateway_protocol_receipts:")
        for failure in verification.failures
    )


def test_multipass_trace_requires_local_candidate_audit_fields(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    (eval_dir / "multipass-trace.jsonl").write_text(
        json.dumps(
            {
                "case": "case_0",
                "openclaw_analyze_calls": 1,
                "crop_calls": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
    )

    assert not verification.ok
    assert any(
        failure.startswith("multipass_trace_artifacts:")
        for failure in verification.failures
    )


def test_required_ecgfounder_arm_rejects_missing_case_evidence(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(
        eval_dir,
        manifest_path,
        count=1,
        ecgfounder=True,
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=1,
    )

    assert not verification.ok
    assert any(
        "required ECGFounder evidence is missing" in failure
        for failure in verification.failures
    )


def test_multipass_trace_with_local_candidate_audit_fields_passes(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    (eval_dir / "multipass-trace.jsonl").write_text(
        json.dumps(
            {
                "case": "case_0",
                "openclaw_analyze_calls": 1,
                "crop_calls": 0,
                "local_candidate_count": 1,
                "local_candidate_regions": [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
    )

    assert verification.ok
    assert "multipass_trace_artifacts" in verification.passed_checks


def test_required_multipass_trace_rejects_missing_trace(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
        require_multipass_trace=True,
    )

    assert not verification.ok
    assert (
        "multipass_trace_artifacts: missing multipass-trace.jsonl"
        in verification.failures
    )


def test_required_multipass_trace_accepts_valid_trace(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    (eval_dir / "multipass-trace.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "case": f"case_{index}",
                    "local_candidate_count": 0,
                    "local_candidate_regions": [],
                }
            )
            + "\n"
            for index in range(2)
        ),
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
        require_multipass_trace=True,
    )

    assert verification.ok
    assert "multipass_trace_artifacts" in verification.passed_checks


def test_required_multipass_refinement_rejects_trace_only_run(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    (eval_dir / "multipass-trace.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "case": f"case_{index}",
                    "openclaw_analyze_calls": 1,
                    "coarse_passes": 1,
                    "zoom_passes": 0,
                    "crop_calls": 0,
                    "local_candidate_count": 1,
                    "local_candidate_regions": [
                        {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}
                    ],
                }
            )
            + "\n"
            for index in range(2)
        ),
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
        require_multipass_refinement=True,
    )

    assert not verification.ok
    assert any(
        "no real crop/refine model turn" in failure for failure in verification.failures
    )
    assert any(
        "lack actual dicom_bbox_validate" in failure
        for failure in verification.failures
    )


def _write_refinement_evidence(
    eval_dir: Path,
    *,
    crop_source: str = "original_roi",
    accepted_count: int = 1,
) -> None:
    for index in range(2):
        result_path = eval_dir / "results" / f"case_{index}.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        boxes_digest, _box_count = _bbox_payload_digest(result["findings"])
        source_sha = result["source_image_sha256"]
        evidence_nonce = f"{index + 1:032x}"
        bbox_binding = {
            "source_image_sha256": source_sha,
            "evidence_nonce": evidence_nonce,
            "receipt_count": 1,
        }
        bbox_receipt = {
            "schema_version": 2,
            "tool": "dicom_bbox_validate",
            "tool_call_id": f"bbox-{index}",
            "accepted_count": accepted_count,
            "rejected_count": 0,
            "source_image_sha256": source_sha,
            "evidence_nonce": evidence_nonce,
            "accepted_boxes_sha256": boxes_digest,
            "details_sha256": "d" * 64,
        }
        result["analysis_trace"] = [
            {
                "stage": "coarse",
                "status": "completed",
                "tools": ["dicom_bbox_validate"],
            },
            {
                "stage": "refine",
                "status": "completed",
                "tool": "crop_region_base64",
                "crop_source": crop_source,
                "tools": ["dicom_bbox_validate"],
                "bbox_evidence": bbox_binding,
                "tool_audit": [bbox_receipt],
                "decisions": [
                    {
                        "action": "confirm",
                        "target_id": "f1",
                        "rationale": "Visible morphology persists in the source crop.",
                    }
                ],
            },
            {
                "stage": "finalize",
                "status": "completed",
                "source": "original_roi",
                "tools": ["dicom_bbox_validate"],
                "bbox_evidence": bbox_binding,
                "tool_audit": [bbox_receipt],
            },
        ]
        result_path.write_text(json.dumps(result), encoding="utf-8")
    (eval_dir / "multipass-trace.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "case": f"case_{index}",
                    "openclaw_analyze_calls": 2,
                    "coarse_passes": 1,
                    "zoom_passes": 1,
                    "crop_calls": 1,
                    "local_candidate_count": 1,
                    "local_candidate_regions": [
                        {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}
                    ],
                }
            )
            + "\n"
            for index in range(2)
        ),
        encoding="utf-8",
    )


def test_required_multipass_refinement_accepts_real_turn_decision_and_tool(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    _write_refinement_evidence(eval_dir)

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
        require_multipass_refinement=True,
    )

    assert verification.ok
    assert "multipass_refinement_artifacts" in verification.passed_checks


def test_required_multipass_refinement_rejects_non_source_crop(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    _write_refinement_evidence(eval_dir, crop_source="coarse_image")

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
        require_multipass_refinement=True,
    )

    assert not verification.ok
    assert any("did not use original_roi" in item for item in verification.failures)


def test_required_multipass_refinement_rejects_unaccepted_bbox_tool_call(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    _write_refinement_evidence(eval_dir, accepted_count=0)

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
        require_multipass_refinement=True,
    )

    assert not verification.ok
    assert any(
        "lack an accepted dicom_bbox_validate" in item for item in verification.failures
    )


def _write_ekg_systematic_probe_evidence(
    eval_dir: Path,
    *,
    completed: bool,
    crop_source: str = "original_roi",
) -> None:
    for index in range(2):
        result_path = eval_dir / "results" / f"case_{index}.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["modality"] = "EKG"
        result["analysis_trace"] = [
            {
                "stage": "systematic_assist",
                "status": "planned",
                "probes": [
                    {
                        "target_id": "ekg_systematic_precordial_leads",
                        "crop_region": {"x": 0.0, "y": 0.5, "w": 1.0, "h": 0.5},
                    }
                ],
            },
            *(
                [
                    {
                        "stage": "refine",
                        "status": "completed",
                        "tool": "crop_region_base64",
                        "target_id": "ekg_systematic_precordial_leads",
                        "crop_source": crop_source,
                    }
                ]
                if completed
                else []
            ),
        ]
        result_path.write_text(json.dumps(result), encoding="utf-8")


def test_required_ekg_systematic_probes_rejects_legacy_multipass(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    _write_ekg_systematic_probe_evidence(eval_dir, completed=False)

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
        require_ekg_systematic_probes=True,
    )

    assert not verification.ok
    assert any(
        "no completed discovery probe" in failure for failure in verification.failures
    )


def test_required_ekg_systematic_probes_accepts_original_roi_turns(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    _write_ekg_systematic_probe_evidence(eval_dir, completed=True)

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
        require_ekg_systematic_probes=True,
    )

    assert verification.ok
    assert "ekg_systematic_probe_artifacts" in verification.passed_checks


def test_results_reject_ekg_bbox_outside_declared_lead(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    result_path = eval_dir / "results" / "case_0.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["modality"] = "EKG"
    result["layout"] = {
        "leads": [
            {"name": "V4", "bbox": [0.0, 0.5, 1.0, 0.25]},
            {"name": "V5", "bbox": [0.0, 0.75, 1.0, 0.25]},
        ]
    }
    result["findings"][0]["regions"] = ["lead_V5"]
    result["findings"][0]["bboxes"] = [{"x": 0.1, "y": 0.55, "w": 0.2, "h": 0.1}]
    result_path.write_text(json.dumps(result), encoding="utf-8")

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
    )

    assert not verification.ok
    assert any("EKG bbox/lead mismatch" in item for item in verification.failures)


def test_required_projection_audit_rejects_missing_fields(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
        require_projection_audit=True,
    )

    assert not verification.ok
    assert any(
        failure.startswith("projection_audit_artifacts:")
        for failure in verification.failures
    )


def test_required_projection_audit_accepts_roundtrip_fields(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    rows = []
    for index in range(2):
        rows.append(
            {
                "audit_type": "bbox",
                "case": f"case_{index}",
                "finding_index": 1,
                "bbox_index": 1,
                "review_image": f"case_{index}.review.png",
                "normalized": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.2},
                "pixels": {"x0": 2, "y0": 4, "x1": 8, "y1": 8},
                "width_px": 6,
                "height_px": 4,
                "invalid_reason": "",
                "was_clamped": False,
                "projection_ok": True,
                "projection_max_edge_drift_px": 0.4,
                "projection_was_clamped": False,
                "projection_back_projected_bbox": {
                    "x": 0.1,
                    "y": 0.2,
                    "w": 0.3,
                    "h": 0.2,
                },
            }
        )
    (eval_dir / "review" / "bbox-audit.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
        require_projection_audit=True,
    )

    assert verification.ok
    assert "projection_audit_artifacts" in verification.passed_checks


def test_review_verification_rejects_unreadable_png(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    (eval_dir / "review" / "case_0.review.png").write_bytes(b"not-a-png")

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
    )

    assert not verification.ok
    assert any(
        "unreadable PNG case_0.review.png" in item for item in verification.failures
    )


def test_review_verification_requires_exact_audit_case_set(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path)
    audit = eval_dir / "review" / "bbox-audit.jsonl"
    audit.write_text(audit.read_text(encoding="utf-8").splitlines()[0] + "\n")

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=2,
    )

    assert not verification.ok
    assert "review_artifacts: bbox audit case set is not exact" in verification.failures


def test_projection_verification_rejects_false_or_degenerate_bbox(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path, count=1)
    row = {
        "audit_type": "bbox",
        "case": "case_0",
        "finding_index": 1,
        "bbox_index": 1,
        "review_image": "case_0.review.png",
        "normalized": {"x": 0.1, "y": 0.2, "w": 0.0, "h": 0.2},
        "pixels": {},
        "width_px": 0,
        "height_px": 0,
        "invalid_reason": "bbox_degenerate",
        "was_clamped": False,
        "projection_ok": False,
        "projection_max_edge_drift_px": 0.0,
        "projection_was_clamped": False,
        "projection_back_projected_bbox": {},
    }
    (eval_dir / "review" / "bbox-audit.jsonl").write_text(
        json.dumps(row) + "\n",
        encoding="utf-8",
    )

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=1,
        require_projection_audit=True,
    )

    assert not verification.ok
    assert any("projection_ok is not true" in item for item in verification.failures)


def test_mixed_or_missing_protocol_is_never_reported_comparable(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    manifest_path = tmp_path / "manifest.json"
    _write_minimal_eval(eval_dir, manifest_path, count=1)
    fingerprint_path = eval_dir / "protocol-fingerprint.json"
    fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    fingerprint["comparability"] = {
        "status": "mixed_protocol_legacy",
        "comparable": False,
        "reasons": ["legacy results"],
    }
    fingerprint_path.write_text(json.dumps(fingerprint), encoding="utf-8")

    mixed = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=1,
    )
    assert not mixed.ok
    assert any("mixed/non-comparable" in item for item in mixed.failures)

    fingerprint_path.unlink()
    missing = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=manifest_path,
        min_cases=1,
    )
    assert not missing.ok
    assert any("legacy runs are not comparable" in item for item in missing.failures)


def test_deferred_run_accepts_only_identity_matched_gold_manifest(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "eval"
    inference_manifest = tmp_path / "manifest.inference.json"
    _write_minimal_eval(
        eval_dir,
        inference_manifest,
        count=1,
        defer_scoring=True,
    )
    gold_manifest = tmp_path / "manifest.gold.json"
    gold = json.loads(inference_manifest.read_text(encoding="utf-8"))
    gold["cases"][0]["expected_severity"] = "normal"
    gold_manifest.write_text(json.dumps(gold), encoding="utf-8")
    scorecard_path = eval_dir / "scorecard.json"
    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    scorecard["scoring_manifest_provenance"] = {
        "path": str(gold_manifest),
        "sha256": hashlib.sha256(gold_manifest.read_bytes()).hexdigest(),
        "paired_gold_manifest": True,
    }
    scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")

    verification = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=gold_manifest,
        min_cases=1,
    )

    assert verification.ok
    assert "paired_gold_manifest" in verification.passed_checks

    gold["cases"][0]["image"] = "wrong.png"
    gold_manifest.write_text(json.dumps(gold), encoding="utf-8")
    mismatched = verify_eval_artifacts(
        eval_dir=eval_dir,
        manifest_path=gold_manifest,
        min_cases=1,
    )
    assert not mismatched.ok
    assert any("image" in item for item in mismatched.failures)
