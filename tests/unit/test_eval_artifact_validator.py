from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from PIL import Image

from dicom_overlay.infrastructure.eval_artifact_validator import (
    _valid_ecg_founder_evidence,
    verify_eval_artifacts,
)

if TYPE_CHECKING:
    from pathlib import Path


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
                "tool_audit": [
                    {
                        "tool": "dicom_bbox_validate",
                        "accepted_count": accepted_count,
                    }
                ],
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
                "tool_audit": [
                    {
                        "tool": "dicom_bbox_validate",
                        "accepted_count": accepted_count,
                    }
                ],
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
