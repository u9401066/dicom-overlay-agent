from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from sidecars.ecgfounder import batch, server


def _registry_payload(
    root: Path,
    *,
    artifact_id: str = "wf-test-artifact",
    relative_path: str = "waveforms/case.mat",
) -> tuple[Path, str]:
    waveform_path = root / "waveforms" / "case.mat"
    waveform_path.parent.mkdir(parents=True)
    waveform_path.write_bytes(b"trusted-waveform")
    source_hash = hashlib.sha256(waveform_path.read_bytes()).hexdigest()
    artifacts = {
        artifact_id: {
            "path": relative_path,
            "source_kind": "raw_waveform",
            "source_sha256": source_hash,
            "source_sample_rate_hz": 500,
            "source_duration_sec": 10,
            "source_points_per_lead": 5000,
            "source_lead_names": list(server.SOURCE_LEADS),
            "model_lead_names": list(server.MODEL_LEADS),
            "lead_mode": "12_lead",
            "dataset": "MEETI",
        }
    }
    index_hash = hashlib.sha256(
        json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    registry_path = root / "waveform-registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_index_sha256": index_hash,
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )
    return registry_path, artifact_id


def test_registry_loads_explicit_meeti_to_model_lead_contract(
    tmp_path: Path,
) -> None:
    registry_path, artifact_id = _registry_payload(tmp_path)

    records = server.load_registry(registry_path)

    assert records[artifact_id].source_lead_names[4:6] == ("aVF", "aVL")
    assert records[artifact_id].model_lead_names[4:6] == ("aVL", "aVF")
    assert records[artifact_id].path == (tmp_path / "waveforms" / "case.mat").resolve()


def test_registry_rejects_path_escape(tmp_path: Path) -> None:
    registry_path, _ = _registry_payload(tmp_path, relative_path="../outside.mat")

    with pytest.raises(server.RegistryError, match="escapes registry root"):
        server.load_registry(registry_path)


def test_registry_rejects_tampered_index(tmp_path: Path) -> None:
    registry_path, _ = _registry_payload(tmp_path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    payload["artifacts"]["wf-test-artifact"]["dataset"] = "tampered"
    registry_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(server.RegistryError, match="index hash mismatch"):
        server.load_registry(registry_path)


class _FakeRuntime:
    ready = False
    preprocessing_revision = "preprocess-test-revision"

    def ensure_ready(self) -> None:
        self.ready = True

    def analyze(
        self,
        record: server.ArtifactRecord,
        *,
        max_predictions: int,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "status": "ok",
            "artifact_seen": record.artifact_id,
            "max_predictions_seen": max_predictions,
        }


class _UnavailableRuntime(_FakeRuntime):
    def ensure_ready(self) -> None:
        raise server.RuntimeUnavailable("checkpoint_not_installed")


def test_service_health_distinguishes_configured_from_deep_ready(
    tmp_path: Path,
) -> None:
    registry_path, _artifact_id = _registry_payload(tmp_path)
    runtime = _FakeRuntime()
    service = server.ECGFounderService(
        registry=server.load_registry(registry_path),
        runtime=runtime,  # type: ignore[arg-type]
    )

    shallow = service.health(deep=False)
    deep = service.health(deep=True)

    assert shallow["status"] == "configured"
    assert shallow["deep"] is False
    assert deep["status"] == "ready"
    assert deep["deep"] is True
    assert deep["preprocessing_revision"] == "preprocess-test-revision"


def test_service_deep_health_reports_runtime_unavailable(tmp_path: Path) -> None:
    registry_path, _artifact_id = _registry_payload(tmp_path)
    service = server.ECGFounderService(
        registry=server.load_registry(registry_path),
        runtime=_UnavailableRuntime(),  # type: ignore[arg-type]
    )

    result = service.health(deep=True)

    assert result["status"] == "unavailable"
    assert result["reason"] == "checkpoint_not_installed"


def test_service_resolves_only_registered_opaque_artifact(tmp_path: Path) -> None:
    registry_path, artifact_id = _registry_payload(tmp_path)
    service = server.ECGFounderService(
        registry=server.load_registry(registry_path),
        runtime=_FakeRuntime(),  # type: ignore[arg-type]
    )

    missing = service.analyze(
        {
            "schema_version": 1,
            "artifact_id": "wf-not-registered",
            "lead_mode": "12_lead",
        }
    )
    found = service.analyze(
        {
            "schema_version": 1,
            "artifact_id": artifact_id,
            "lead_mode": "12_lead",
            "max_predictions": 999,
        }
    )

    assert missing["status"] == "ineligible"
    assert missing["reason"] == "artifact_not_registered"
    assert found["status"] == "ok"
    assert found["artifact_seen"] == artifact_id
    assert found["max_predictions_seen"] == server.MAX_PREDICTIONS


def test_offline_analysis_can_retain_all_scores_without_expanding_tool_payload(
    tmp_path: Path,
) -> None:
    registry_path, artifact_id = _registry_payload(tmp_path)
    record = server.load_registry(registry_path)[artifact_id]
    runtime = _FakeRuntime()

    result = server.analyze_record(
        runtime,  # type: ignore[arg-type]
        record,
        max_predictions=batch.MAX_OFFLINE_PREDICTIONS,
    )

    assert result["status"] == "ok"
    assert result["max_predictions_seen"] == 150


def test_batch_parser_accepts_full_scores_but_rejects_more_than_task_count() -> None:
    parser = batch.build_parser()

    args = parser.parse_args(["--max-predictions", "150"])

    assert args.max_predictions == 150
    with pytest.raises(SystemExit):
        parser.parse_args(["--max-predictions", "151"])


def test_http_endpoint_requires_bearer_token(tmp_path: Path) -> None:
    registry_path, artifact_id = _registry_payload(tmp_path)
    service = server.ECGFounderService(
        registry=server.load_registry(registry_path),
        runtime=_FakeRuntime(),  # type: ignore[arg-type]
    )
    token = "t" * 32
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        server.build_handler(service, token=token),
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{httpd.server_port}/v1/analyze"
    health_endpoint = f"http://127.0.0.1:{httpd.server_port}/health"
    payload = json.dumps(
        {
            "schema_version": 1,
            "artifact_id": artifact_id,
            "lead_mode": "12_lead",
        }
    ).encode()
    try:
        with pytest.raises(urllib.error.HTTPError) as unauthorized:
            urllib.request.urlopen(
                urllib.request.Request(endpoint, data=payload, method="POST"),
                timeout=2,
            )
        assert unauthorized.value.code == 401

        health_request = urllib.request.Request(
            health_endpoint,
            headers={"authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(health_request, timeout=2) as response:
            health = json.loads(response.read())
        assert health["status"] == "configured"

        deep_health_request = urllib.request.Request(
            f"{health_endpoint}?deep=1",
            headers={"authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(deep_health_request, timeout=2) as response:
            deep_health = json.loads(response.read())
        assert deep_health["status"] == "ready"

        request = urllib.request.Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "authorization": f"Bearer {token}",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            result = json.loads(response.read())
        assert result["status"] == "ok"
        assert result["artifact_seen"] == artifact_id
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_non_loopback_bind_is_rejected() -> None:
    with pytest.raises(Exception, match="loopback"):
        server._loopback_host("8.8.8.8")


def test_batch_loader_requires_one_registered_waveform_per_case(tmp_path: Path) -> None:
    registry_path, artifact_id = _registry_payload(tmp_path)
    registry = server.load_registry(registry_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "label": "meeti_case",
                        "report": "Sinus rhythm.",
                        "waveform_artifact_id": artifact_id,
                        "waveform_lead_mode": "12_lead",
                        "expected_severity": "info",
                        "label_status": "confirmed",
                        "concepts": ["sinus_rhythm"],
                        "uncertain_concepts": ["st_elevation"],
                        "ungradable_reasons": ["lead_quality"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = batch.load_paired_cases(manifest_path, registry_ids=set(registry))

    assert cases[0]["artifact_id"] == artifact_id
    assert cases[0]["case_label"] == "meeti_case"
    assert (
        cases[0]["reference_report_sha256"]
        == hashlib.sha256(b"Sinus rhythm.").hexdigest()
    )
    assert cases[0]["uncertain_concepts"] == ["st_elevation"]
    assert cases[0]["ungradable_reasons"] == ["lead_quality"]
    assert "report" not in cases[0]


def test_batch_loader_rejects_unregistered_waveform(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "label": "meeti_case",
                        "waveform_artifact_id": "wf-not-in-registry",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown artifact"):
        batch.load_paired_cases(manifest_path, registry_ids={"wf-other"})


def test_batch_latency_stats_are_stable_across_resume_reads(tmp_path: Path) -> None:
    results_path = tmp_path / "results.jsonl"
    results_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "artifact_id": "wf-one",
                        "status": "ok",
                        "latency_ms": 100.0,
                        "predictions": [{"label": "A"}],
                    }
                ),
                json.dumps(
                    {
                        "artifact_id": "wf-two",
                        "status": "ok",
                        "latency_ms": 300.0,
                        "predictions": [{"label": "B"}],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    completed, statuses, _, latencies = batch._load_completed(results_path)
    stats = batch._latency_stats(latencies)

    assert completed == {"wf-one", "wf-two"}
    assert statuses == {"ok": 2}
    assert stats["total_ms"] == 400.0
    assert stats["mean_ms"] == 200.0
    assert stats["median_ms"] == 200.0


def test_checkpoint_loader_never_falls_back_to_unsafe_pickle() -> None:
    source = Path(server.__file__).read_text(encoding="utf-8")

    assert "weights_only=True" in source
    assert "weights_only=False," not in source
    assert "clear_safe_globals" in source
