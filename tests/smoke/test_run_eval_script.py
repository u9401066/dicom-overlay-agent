from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from dicom_overlay.application.multi_pass import RefinementResult
from dicom_overlay.domain.entities import (
    AnalysisResult,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.infrastructure.eval_harness import EvalCase, score_case
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient


def _load_run_eval_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "run-eval.py"
    spec = importlib.util.spec_from_file_location("run_eval_script", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_cases_defaults_valid_regions_from_modality(tmp_path: Path) -> None:
    module = _load_run_eval_module()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "image": "ekg.png",
                        "modality": "EKG",
                        "expected_severity": "normal",
                    },
                    {
                        "image": "cxr.png",
                        "modality": "CXR",
                        "expected_severity": "normal",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = module._load_cases(manifest)

    assert "lead_I" in cases[0].valid_regions
    assert "rhythm_strip" in cases[0].valid_regions
    assert "right_upper_lung" in cases[1].valid_regions
    assert "left_cp_angle" in cases[1].valid_regions


def test_mock_payload_scores_perfect_for_normal_case(tmp_path: Path) -> None:
    module = _load_run_eval_module()
    case = EvalCase(
        image_path=tmp_path / "cxr.png",
        modality=Modality.CXR,
        expected_severity=Severity.NORMAL,
        expected_keywords=("clear", "no acute", "normal"),
        expected_negatives=("no pneumothorax", "no effusion", "no consolidation"),
        label="normal_cxr",
    )
    payload = module._mock_payload_for(case)

    client = OpenClawClient.__new__(OpenClawClient)
    result = client._parse_result(payload, elapsed_ms=0, request_modality=case.modality)
    score = score_case(case, result, latency_ms=0)

    assert score.severity_match is True
    assert score.keyword_misses == []
    assert score.negative_misses == []


def test_make_client_uses_eval_timeout_for_inference() -> None:
    module = _load_run_eval_module()

    client = module._make_client("ws://example.invalid", timeout_sec=90)

    assert client._timeout == 90
    assert client._connect_timeout == 90
    assert client._inference_timeout == 90
    assert client._registry is module.get_active_registry()
    assert client._base_dir == module._REPO_ROOT


def test_waveform_evidence_requires_one_nonce_correlated_pinned_receipt() -> None:
    module = _load_run_eval_module()
    artifact_id = "wf-opaque-123"
    nonce = "a" * 32
    artifact_digest = hashlib.sha256(artifact_id.encode()).hexdigest()
    predictions = [{"label": "NORMAL SINUS RHYTHM", "probability": 0.9}]
    response_evidence = {
        "schema_version": 1,
        "status": "ok",
        "evidence_type": "ecg_waveform_classification",
        "lead_mode": "12_lead",
        "evidence_nonce": nonce,
        "artifact_id_sha256": artifact_digest,
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
    receipt = {
        "schema_version": 1,
        "tool": "ecg_founder_analyze_waveform",
        "tool_call_id": "call-1",
        "status": "ok",
        "evidence_nonce": nonce,
        "artifact_id_sha256": artifact_digest,
        "lead_mode": "12_lead",
        "model_id": "PKUDigitalHealth/ECGFounder",
        "model_revision": "04edac702b61c91face519774ddcc0cd712fef23",
        "checkpoint_sha256": (
            "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997"
        ),
        "source_sha256": "b" * 64,
        "preprocessing_revision": "preprocess-v1",
        "calibration_status": "uncalibrated",
        "calibration_revision": "",
        "prediction_count": 1,
        "predictions": predictions,
        "response_evidence": response_evidence,
        "response_sha256": hashlib.sha256(
            json.dumps(
                response_evidence,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
    }

    evidence = module._build_waveform_evidence(
        artifact_id=artifact_id,
        lead_mode="12_lead",
        evidence_nonce=nonce,
        receipts=[receipt],
    )

    assert evidence["verified_exactly_once"] is True
    assert evidence["receipt_count"] == 1

    wrong_nonce = dict(receipt, evidence_nonce="b" * 32)
    rejected = module._build_waveform_evidence(
        artifact_id=artifact_id,
        lead_mode="12_lead",
        evidence_nonce=nonce,
        receipts=[wrong_nonce],
    )
    duplicate = module._build_waveform_evidence(
        artifact_id=artifact_id,
        lead_mode="12_lead",
        evidence_nonce=nonce,
        receipts=[receipt, receipt],
    )
    assert rejected["verified_exactly_once"] is False
    assert duplicate["verified_exactly_once"] is False


def test_ecgfounder_deep_health_requires_pinned_ready_provenance() -> None:
    module = _load_run_eval_module()
    requests: list[tuple[str, str, float]] = []
    payload = {
        "status": "ready",
        "deep": True,
        "model_id": "PKUDigitalHealth/ECGFounder",
        "model_revision": "04edac702b61c91face519774ddcc0cd712fef23",
        "checkpoint_sha256": (
            "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997"
        ),
        "preprocessing_revision": "preprocess-v1",
        "artifact_count": 1000,
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit: int) -> bytes:
            return json.dumps(payload).encode()

    def opener(request, *, timeout: float):
        requests.append(
            (request.full_url, request.get_header("Authorization"), timeout)
        )
        return Response()

    environment = {
        "DICOM_ECGFOUNDER_ENDPOINT": "http://127.0.0.1:18790/v1/analyze",
        "DICOM_ECGFOUNDER_TOKEN": "secret-token",
        "DICOM_ECGFOUNDER_TIMEOUT_MS": "5000",
    }
    health, reason = module._probe_ecg_founder_deep_health(
        environment,
        opener=opener,
    )

    assert health is not None
    assert health["preprocessing_revision"] == "preprocess-v1"
    assert reason == "ready"
    assert requests == [
        (
            "http://127.0.0.1:18790/health?deep=1",
            "Bearer secret-token",
            5.0,
        )
    ]

    payload["checkpoint_sha256"] = "f" * 64
    health, reason = module._probe_ecg_founder_deep_health(
        environment,
        opener=opener,
    )
    assert (health, reason) == (None, "health_provenance_mismatch")


def test_counting_analyzer_counts_delegated_analyze_calls() -> None:
    module = _load_run_eval_module()

    class Inner:
        async def analyze(
            self,
            image_base64: str,
            modality: Modality,
            valid_regions: list[str],
        ) -> tuple[str, Modality, list[str]]:
            return image_base64, modality, valid_regions

        async def chat(self, message: str) -> str:
            return message

        async def connect(self) -> None:
            return None

        async def disconnect(self) -> None:
            return None

        def is_connected(self) -> bool:
            return True

    counter = module._CountingAnalyzer(Inner())

    asyncio.run(counter.analyze("img", Modality.EKG, ["lead_I"]))
    asyncio.run(counter.analyze("img", Modality.EKG, ["lead_II"]))

    assert counter.analyze_calls == 2


def test_counting_analyzer_delegates_refine_and_runtime_trace() -> None:
    module = _load_run_eval_module()
    calls: list[tuple[object, ...]] = []
    expected = RefinementResult()

    class Inner:
        async def refine(
            self,
            image_base64: str,
            modality: Modality,
            valid_regions: list[str],
            *,
            hypothesis: Finding | None,
            crop_region: RegionRect,
        ) -> RefinementResult:
            calls.append(
                (
                    image_base64,
                    modality,
                    valid_regions,
                    hypothesis,
                    crop_region,
                )
            )
            return expected

        def last_run_trace(self) -> dict[str, object]:
            return {"run_id": "run-1", "tools": ["vision"]}

    counter = module._CountingAnalyzer(Inner())
    crop_region = RegionRect(x=0.1, y=0.2, w=0.3, h=0.4)

    result = asyncio.run(
        counter.refine(
            "crop",
            Modality.EKG,
            ["lead_II"],
            hypothesis=None,
            crop_region=crop_region,
        )
    )

    assert result is expected
    assert calls == [("crop", Modality.EKG, ["lead_II"], None, crop_region)]
    assert counter.analyze_calls == 1
    assert counter.last_run_trace() == {
        "run_id": "run-1",
        "tools": ["vision"],
    }


def test_eval_image_payload_keeps_original_and_bounds_only_coarse_pass() -> None:
    module = _load_run_eval_module()
    processor = module.ImageProcessor()
    source = Image.new("RGB", (2200, 1100), "white")
    buffer = BytesIO()
    source.save(buffer, format="PNG")

    payload = module._prepare_eval_image_payload(processor, buffer.getvalue())

    source_bytes = base64.b64decode(payload.source_image_base64)
    coarse_bytes = base64.b64decode(payload.coarse_image_base64)
    assert payload.source_size_px == (2200, 1100)
    assert payload.coarse_size_px == (1568, 784)
    assert processor.image_size(source_bytes) == payload.source_size_px
    assert processor.image_size(coarse_bytes) == payload.coarse_size_px
    assert payload.source_image_base64 != payload.coarse_image_base64


def test_multipass_uses_coarse_for_first_read_and_original_for_refine_crop() -> None:
    module = _load_run_eval_module()
    analyzed_images: list[str] = []
    refined_images: list[str] = []
    crop_sources: list[str] = []

    class Inner:
        async def analyze(
            self,
            image_base64: str,
            modality: Modality,
            valid_regions: list[str],
        ) -> AnalysisResult:
            analyzed_images.append(image_base64)
            return AnalysisResult(
                modality=modality,
                summary="Focal opacity.",
                severity=Severity.WARNING,
                findings=[
                    Finding(
                        id="f1",
                        label="opacity",
                        detail="Focal opacity",
                        severity=Severity.WARNING,
                        regions=["left_lower_lung"],
                        bboxes=[RegionRect(x=0.2, y=0.2, w=0.3, h=0.3)],
                    )
                ],
                checklist={},
            )

        async def refine(
            self,
            image_base64: str,
            modality: Modality,
            valid_regions: list[str],
            *,
            hypothesis: Finding | None,
            crop_region: RegionRect,
        ) -> RefinementResult:
            refined_images.append(image_base64)
            assert hypothesis is not None
            assert hypothesis.id == "f1"
            return RefinementResult()

        def is_connected(self) -> bool:
            return True

    def cropper(image_base64: str, region: RegionRect) -> str:
        crop_sources.append(image_base64)
        assert region.w > 0
        return "refine-crop"

    analyzer, counter = module._build_multi_pass_analyzer(
        Inner(),
        cropper=cropper,
        max_zoom_targets=1,
    )

    result = asyncio.run(
        module._invoke_analyzer_with_source(
            analyzer,
            coarse_image_base64="coarse-image",
            source_image_base64="original-image",
            modality=Modality.CXR,
            valid_regions=["left_lower_lung"],
            source_size_px=(2000, 1000),
            local_candidate_regions=[],
        )
    )

    assert result.summary == "Focal opacity."
    assert analyzed_images == ["coarse-image"]
    assert crop_sources == ["original-image"]
    assert refined_images == ["refine-crop"]
    assert counter.analyze_calls == 2


def test_eval_analyzer_wiring_matches_app_hooks_and_bbox_calibrator() -> None:
    module = _load_run_eval_module()

    class Inner:
        pass

    hooked = module._wrap_with_app_hooks(Inner())
    analyzer, counter = module._build_multi_pass_analyzer(
        hooked,
        cropper=lambda image, region: image,
        max_zoom_targets=2,
    )

    assert [hook.__class__.__name__ for hook in hooked._hooks] == [
        "InputGuard",
        "ClinicalConsistencyHook",
        "BboxCalibrationHook",
        "OutputValidator",
    ]
    assert counter._inner is hooked
    assert analyzer._inner is counter
    assert analyzer._interpreter._bbox_calibrator is module.calibrate_ekg_bboxes


def test_limited_cases_caps_console_preview() -> None:
    module = _load_run_eval_module()

    shown, remaining = module._limited_cases(list(range(1000)), limit=50)

    assert shown == list(range(50))
    assert remaining == 950


def test_limited_cases_zero_prints_all() -> None:
    module = _load_run_eval_module()

    shown, remaining = module._limited_cases([1, 2, 3], limit=0)

    assert shown == [1, 2, 3]
    assert remaining == 0


def test_pending_cases_skips_only_persisted_results(tmp_path: Path) -> None:
    module = _load_run_eval_module()
    cases = [
        EvalCase(
            image_path=tmp_path / f"case_{index}.png",
            modality=Modality.EKG,
            expected_severity=Severity.NORMAL,
            label=f"case_{index}",
        )
        for index in range(3)
    ]
    results_dir = tmp_path / "eval" / "results"
    results_dir.mkdir(parents=True)
    (results_dir / "case_1.json").write_text("{}", encoding="utf-8")

    pending, skipped = module._pending_cases(cases, tmp_path / "eval")

    assert [case.label for case in pending] == ["case_0", "case_2"]
    assert skipped == 1


def test_pending_cases_uses_writer_filename_sanitization(tmp_path: Path) -> None:
    module = _load_run_eval_module()
    case = EvalCase(
        image_path=tmp_path / "fallback.png",
        modality=Modality.EKG,
        expected_severity=Severity.NORMAL,
        label="case/with spaces",
    )
    results_dir = tmp_path / "eval" / "results"
    results_dir.mkdir(parents=True)
    (results_dir / "case_with_spaces.json").write_text("{}", encoding="utf-8")

    pending, skipped = module._pending_cases([case], tmp_path / "eval")

    assert pending == []
    assert skipped == 1


def _fingerprint(module, *, model: str, image_sha256: str) -> dict:
    protocol = {
        "model": {"id": model},
        "manifest": {
            "cases": [
                {
                    "case": "case_1",
                    "image_name": "case.png",
                    "sha256": image_sha256,
                }
            ]
        },
    }
    return {
        "schema_version": 1,
        "created_at": "2026-07-25T00:00:00+00:00",
        "protocol_scope": "entire_run",
        "protocol_digest": module._protocol_digest(protocol),
        "comparability": {
            "status": "comparable",
            "comparable": True,
            "reasons": [],
        },
        "protocol": protocol,
    }


def _resume_case(tmp_path: Path) -> EvalCase:
    image = tmp_path / "case.png"
    image.write_bytes(b"image-bytes")
    return EvalCase(
        image_path=image,
        modality=Modality.EKG,
        expected_severity=Severity.NORMAL,
        label="case_1",
    )


def _write_resume_result(
    eval_dir: Path,
    *,
    protocol_digest: str | None,
    image_sha256: str | None,
) -> None:
    results = eval_dir / "results"
    results.mkdir(parents=True, exist_ok=True)
    payload = {
        "case": "case_1",
        "modality": "EKG",
        "score": {"case_label": "case_1", "image": "case.png"},
    }
    if protocol_digest is not None:
        payload["protocol_digest"] = protocol_digest
    if image_sha256 is not None:
        payload["source_image_sha256"] = image_sha256
    (results / "case_1.json").write_text(json.dumps(payload), encoding="utf-8")


def test_resume_accepts_only_matching_immutable_fingerprint_and_result(
    tmp_path: Path,
) -> None:
    module = _load_run_eval_module()
    case = _resume_case(tmp_path)
    image_sha256 = module._sha256_file(case.image_path)
    current = _fingerprint(module, model="openai/gpt-test", image_sha256=image_sha256)
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()

    module._prepare_protocol_fingerprint(
        output_dir=eval_dir,
        current=current,
        cases=[case],
        resume=False,
        legacy_policy="reject",
    )
    _write_resume_result(
        eval_dir,
        protocol_digest=current["protocol_digest"],
        image_sha256=image_sha256,
    )

    resumed = module._prepare_protocol_fingerprint(
        output_dir=eval_dir,
        current=_fingerprint(
            module,
            model="openai/gpt-test",
            image_sha256=image_sha256,
        ),
        cases=[case],
        resume=True,
        legacy_policy="reject",
    )

    assert resumed["protocol_digest"] == current["protocol_digest"]


def test_resume_rejects_protocol_change_before_using_existing_results(
    tmp_path: Path,
) -> None:
    module = _load_run_eval_module()
    case = _resume_case(tmp_path)
    image_sha256 = module._sha256_file(case.image_path)
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    original = _fingerprint(module, model="openai/model-a", image_sha256=image_sha256)
    module._prepare_protocol_fingerprint(
        output_dir=eval_dir,
        current=original,
        cases=[case],
        resume=False,
        legacy_policy="reject",
    )
    _write_resume_result(
        eval_dir,
        protocol_digest=original["protocol_digest"],
        image_sha256=image_sha256,
    )

    with pytest.raises(module.ProtocolFingerprintError, match="protocol mismatch"):
        module._prepare_protocol_fingerprint(
            output_dir=eval_dir,
            current=_fingerprint(
                module,
                model="openai/model-b",
                image_sha256=image_sha256,
            ),
            cases=[case],
            resume=True,
            legacy_policy="reject",
        )


def test_resume_rejects_invalid_or_wrong_identity_result(tmp_path: Path) -> None:
    module = _load_run_eval_module()
    case = _resume_case(tmp_path)
    eval_dir = tmp_path / "eval"
    results = eval_dir / "results"
    results.mkdir(parents=True)
    (results / "case_1.json").write_text(
        json.dumps({"case": "wrong", "score": {"image": "case.png"}}),
        encoding="utf-8",
    )

    with pytest.raises(module.ProtocolFingerprintError, match="case mismatch"):
        module._validate_resume_results(
            [case],
            eval_dir,
            protocol_digest="",
            require_protocol_metadata=False,
        )

    (results / "case_1.json").write_text("{truncated", encoding="utf-8")
    with pytest.raises(module.ProtocolFingerprintError, match="not valid JSON"):
        module._validate_resume_results(
            [case],
            eval_dir,
            protocol_digest="",
            require_protocol_metadata=False,
        )


def test_legacy_resume_is_rejected_or_explicitly_marked_noncomparable(
    tmp_path: Path,
) -> None:
    module = _load_run_eval_module()
    case = _resume_case(tmp_path)
    image_sha256 = module._sha256_file(case.image_path)
    eval_dir = tmp_path / "eval"
    _write_resume_result(eval_dir, protocol_digest=None, image_sha256=None)

    with pytest.raises(module.ProtocolFingerprintError, match="legacy eval artifacts"):
        module._prepare_protocol_fingerprint(
            output_dir=eval_dir,
            current=_fingerprint(
                module,
                model="openai/gpt-test",
                image_sha256=image_sha256,
            ),
            cases=[case],
            resume=True,
            legacy_policy="reject",
        )

    marked = module._prepare_protocol_fingerprint(
        output_dir=eval_dir,
        current=_fingerprint(
            module,
            model="openai/gpt-test",
            image_sha256=image_sha256,
        ),
        cases=[case],
        resume=True,
        legacy_policy="mark",
    )

    assert marked["protocol_scope"] == "resume_segment_only"
    assert marked["comparability"]["status"] == "mixed_protocol_legacy"
    assert marked["comparability"]["comparable"] is False


def test_fresh_run_rejects_stale_nonresult_eval_artifacts(tmp_path: Path) -> None:
    module = _load_run_eval_module()
    case = _resume_case(tmp_path)
    image_sha256 = module._sha256_file(case.image_path)
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "scorecard.json").write_text("{}", encoding="utf-8")

    with pytest.raises(module.ProtocolFingerprintError, match=r"scorecard\.json"):
        module._prepare_protocol_fingerprint(
            output_dir=eval_dir,
            current=_fingerprint(
                module,
                model="openai/gpt-test",
                image_sha256=image_sha256,
            ),
            cases=[case],
            resume=False,
            legacy_policy="reject",
        )


def test_mock_run_and_resume_leave_full_canonical_scorecard(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "run-eval.py"
    image = tmp_path / "case.png"
    Image.new("RGB", (32, 24), "white").save(image)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "image": "case.png",
                        "modality": "EKG",
                        "expected_severity": "normal",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "eval"
    command = [
        sys.executable,
        str(script),
        "--mock",
        "--model-id",
        "mock-eval-gateway",
        "--manifest",
        str(manifest),
        "--output",
        str(output),
        "--no-rhythm-strip-pass",
    ]

    first = subprocess.run(command, capture_output=True, text=True, check=False)
    resumed = subprocess.run(
        [*command, "--resume"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    fingerprint = json.loads(
        (output / "protocol-fingerprint.json").read_text(encoding="utf-8")
    )
    result = json.loads(
        (output / "results" / "case_png.json").read_text(encoding="utf-8")
    )
    scorecard = json.loads((output / "scorecard.json").read_text(encoding="utf-8"))
    protocol = fingerprint["protocol"]
    assert protocol["source"]["commit"]
    assert isinstance(protocol["source"]["dirty"], bool)
    assert protocol["model"]["id"] == "mock-eval-gateway"
    assert protocol["model"]["openclaw"]["version"]
    assert protocol["prompts"]
    assert protocol["skills"]
    assert protocol["clinical_rules"]
    assert protocol["manifest"]["selected_case_count"] == 1
    assert protocol["manifest"]["cases"][0]["case"] == "case.png"
    assert protocol["flags"]["guardrail_hooks"] == [
        "InputGuard",
        "OutputValidator",
        "BboxCalibrationHook",
        "ClinicalConsistencyHook",
    ]
    assert protocol["flags"]["single_pass_bbox_calibrator"] == ("calibrate_ekg_bboxes")
    assert protocol["flags"]["multi_pass_bbox_calibrator"] == ("calibrate_ekg_bboxes")
    assert protocol["flags"]["multi_pass_max_ekg_systematic_probes"] == 2
    assert protocol["flags"]["refinement_crop_source"] == "original_roi"
    assert protocol["flags"]["rhythm_strip_pass"] is False
    assert result["protocol_digest"] == fingerprint["protocol_digest"]
    assert result["source_image_sha256"]
    assert scorecard["scorecard_kind"] == "full_rebuild"
    assert scorecard["result_count"] == 1
    assert scorecard["cases"][0]["case_label"] == "case.png"
