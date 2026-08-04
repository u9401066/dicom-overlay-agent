"""Loopback-only ECGFounder inference sidecar.

The OpenClaw tool sends an opaque artifact id. This process resolves that id
through a trusted registry, verifies the waveform and checkpoint hashes, then
returns bounded probability evidence with explicit provenance. It never accepts
a filesystem path from the agent and never returns image coordinates.
"""

from __future__ import annotations

import argparse
import codecs
import collections
import hashlib
import hmac
import ipaddress
import json
import os
import re
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

SCHEMA_VERSION = 1
MODEL_ID = "PKUDigitalHealth/ECGFounder"
MODEL_REVISION = "04edac702b61c91face519774ddcc0cd712fef23"
CHECKPOINT_SHA256_12_LEAD = (
    "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997"
)
SOURCE_LEADS = (
    "I",
    "II",
    "III",
    "aVR",
    "aVF",
    "aVL",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
)
MODEL_LEADS = (
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
)
SAMPLE_RATE_HZ = 500
DURATION_SEC = 10
POINTS_PER_LEAD = 5000
MAX_REQUEST_BYTES = 16 * 1024
MAX_PREDICTIONS = 20
_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class RegistryError(ValueError):
    """The trusted artifact registry is malformed."""


class ArtifactIneligible(ValueError):
    """A registered waveform does not satisfy the model input contract."""


class RuntimeUnavailable(RuntimeError):
    """The optional model runtime or checkpoint is not ready."""


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    path: Path
    source_kind: str
    source_sha256: str
    source_sample_rate_hz: int
    source_duration_sec: int
    source_points_per_lead: int
    source_lead_names: tuple[str, ...]
    model_lead_names: tuple[str, ...]
    lead_mode: str
    dataset: str


@dataclass(frozen=True)
class Calibration:
    status: str = "uncalibrated"
    dataset: str = ""
    revision: str = ""
    thresholds: dict[str, float] | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_artifact_hash(artifacts: object) -> str:
    payload = json.dumps(
        artifacts,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RegistryError(f"{field} must be a string list")
    return tuple(value)


def _bounded_registry_path(root: Path, raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise RegistryError("artifact path is required")
    relative = Path(raw_path)
    if relative.is_absolute():
        raise RegistryError("artifact paths must be registry-relative")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RegistryError("artifact path escapes registry root") from exc
    if resolved.suffix.lower() != ".mat":
        raise RegistryError("ECGFounder artifacts must be .mat waveforms")
    return resolved


def load_registry(path: Path) -> dict[str, ArtifactRecord]:
    registry_path = path.resolve()
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError("cannot read waveform registry") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise RegistryError("unsupported waveform registry schema")
    artifacts = raw.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RegistryError("waveform registry artifacts must be an object")
    expected_index_hash = str(raw.get("artifact_index_sha256") or "").lower()
    if not _SHA256.fullmatch(expected_index_hash):
        raise RegistryError("waveform registry lacks artifact index provenance")
    if not hmac.compare_digest(
        expected_index_hash, _canonical_artifact_hash(artifacts)
    ):
        raise RegistryError("waveform registry artifact index hash mismatch")

    records: dict[str, ArtifactRecord] = {}
    root = registry_path.parent
    for artifact_id, value in artifacts.items():
        if not isinstance(artifact_id, str) or not _ARTIFACT_ID.fullmatch(artifact_id):
            raise RegistryError("waveform registry contains an invalid artifact id")
        if not isinstance(value, dict):
            raise RegistryError("waveform registry entry must be an object")
        source_sha256 = str(value.get("source_sha256") or "").lower()
        if not _SHA256.fullmatch(source_sha256):
            raise RegistryError("waveform registry entry lacks a source hash")
        record = ArtifactRecord(
            artifact_id=artifact_id,
            path=_bounded_registry_path(root, value.get("path")),
            source_kind=str(value.get("source_kind") or ""),
            source_sha256=source_sha256,
            source_sample_rate_hz=int(value.get("source_sample_rate_hz") or 0),
            source_duration_sec=int(value.get("source_duration_sec") or 0),
            source_points_per_lead=int(value.get("source_points_per_lead") or 0),
            source_lead_names=_string_tuple(
                value.get("source_lead_names"), field="source_lead_names"
            ),
            model_lead_names=_string_tuple(
                value.get("model_lead_names"), field="model_lead_names"
            ),
            lead_mode=str(value.get("lead_mode") or ""),
            dataset=str(value.get("dataset") or ""),
        )
        _validate_record_contract(record)
        records[artifact_id] = record
    return records


def _validate_record_contract(record: ArtifactRecord) -> None:
    if record.source_kind != "raw_waveform":
        raise RegistryError("only raw waveform artifacts are currently supported")
    if record.lead_mode != "12_lead":
        raise RegistryError("only the pinned 12-lead checkpoint is supported")
    if record.source_sample_rate_hz != SAMPLE_RATE_HZ:
        raise RegistryError("waveform sample rate must be 500 Hz")
    if record.source_duration_sec != DURATION_SEC:
        raise RegistryError("waveform duration must be 10 seconds")
    if record.source_points_per_lead != POINTS_PER_LEAD:
        raise RegistryError("waveform must contain 5000 points per lead")
    if record.source_lead_names != SOURCE_LEADS:
        raise RegistryError("unexpected MEETI/MIMIC source lead order")
    if record.model_lead_names != MODEL_LEADS:
        raise RegistryError("unexpected ECGFounder model lead order")


def load_calibration(path: Path | None, tasks: tuple[str, ...]) -> Calibration:
    if path is None:
        return Calibration()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError("cannot read calibration file") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise RegistryError("unsupported calibration schema")
    if raw.get("checkpoint_sha256") != CHECKPOINT_SHA256_12_LEAD:
        raise RegistryError("calibration checkpoint hash mismatch")
    thresholds = raw.get("thresholds")
    if not isinstance(thresholds, dict) or set(thresholds) != set(tasks):
        raise RegistryError("validated calibration must cover all 150 tasks")
    clean_thresholds: dict[str, float] = {}
    for label, value in thresholds.items():
        threshold = float(value)
        if not 0.0 <= threshold <= 1.0:
            raise RegistryError("calibration threshold is outside [0, 1]")
        clean_thresholds[label] = threshold
    dataset = str(raw.get("dataset") or "").strip()
    revision = str(raw.get("revision") or "").strip()
    if not dataset or not revision:
        raise RegistryError("validated calibration lacks dataset provenance")
    return Calibration(
        status="validated",
        dataset=dataset,
        revision=revision,
        thresholds=clean_thresholds,
    )


def load_tasks(path: Path) -> tuple[str, ...]:
    try:
        tasks = tuple(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise RuntimeUnavailable("task vocabulary is unavailable") from exc
    if len(tasks) != 150 or len(set(tasks)) != 150:
        raise RuntimeUnavailable("task vocabulary must contain 150 unique labels")
    return tasks


def preprocessing_revision(base_dir: Path) -> str:
    digest = hashlib.sha256()
    for filename in ("server.py", "model.py", "tasks.txt"):
        digest.update(filename.encode("ascii"))
        digest.update((base_dir / filename).read_bytes())
    return digest.hexdigest()


class ECGFounderRuntime:
    def __init__(
        self,
        *,
        checkpoint_path: Path,
        tasks_path: Path,
        calibration_path: Path | None = None,
    ) -> None:
        self._checkpoint_path = checkpoint_path.resolve()
        self._tasks = load_tasks(tasks_path.resolve())
        self._calibration = load_calibration(calibration_path, self._tasks)
        self._model: Any | None = None
        self._torch: Any | None = None
        self._load_lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._preprocessing_revision = preprocessing_revision(Path(__file__).parent)

    @property
    def tasks(self) -> tuple[str, ...]:
        return self._tasks

    @property
    def ready(self) -> bool:
        return self._model is not None

    @property
    def preprocessing_revision(self) -> str:
        return self._preprocessing_revision

    def ensure_ready(self) -> None:
        """Load and verify the pinned checkpoint for a deep health probe."""

        self._ensure_model()

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            if not self._checkpoint_path.is_file():
                raise RuntimeUnavailable("checkpoint_not_installed")
            actual_hash = sha256_file(self._checkpoint_path)
            if not hmac.compare_digest(actual_hash, CHECKPOINT_SHA256_12_LEAD):
                raise RuntimeUnavailable("checkpoint_hash_mismatch")
            try:
                import numpy as np
                import torch

                from sidecars.ecgfounder.model import build_ecgfounder_12lead_model
            except ImportError as exc:
                raise RuntimeUnavailable("torch_runtime_not_installed") from exc

            model = build_ecgfounder_12lead_model()
            try:
                # The published pickle contains only the globals listed by the
                # Hugging Face safety scan. Torch 2.4 requires the NumPy scalar
                # and dtype builders to be explicitly allowlisted even in
                # weights-only mode. Never fall back to weights_only=False.
                torch.serialization.add_safe_globals(
                    [
                        codecs.encode,
                        collections.OrderedDict,
                        np.core.multiarray.scalar,
                        np.dtype,
                        type(np.dtype(np.float64)),
                    ]
                )
                try:
                    checkpoint = torch.load(
                        self._checkpoint_path,
                        map_location="cpu",
                        weights_only=True,
                    )
                finally:
                    torch.serialization.clear_safe_globals()
                state_dict = checkpoint["state_dict"]
            except Exception as exc:
                raise RuntimeUnavailable("checkpoint_load_failed") from exc
            if not isinstance(state_dict, dict):
                raise RuntimeUnavailable("checkpoint_state_dict_missing")
            if state_dict and all(str(key).startswith("module.") for key in state_dict):
                state_dict = {str(key)[7:]: value for key, value in state_dict.items()}
            load_result = model.load_state_dict(state_dict, strict=False)
            if load_result.missing_keys or load_result.unexpected_keys:
                raise RuntimeUnavailable("checkpoint_architecture_mismatch")
            model.eval()
            for parameter in model.parameters():
                parameter.requires_grad_(False)
            self._torch = torch
            self._model = model

    @staticmethod
    def _load_and_preprocess(record: ArtifactRecord) -> Any:
        if not record.path.is_file():
            raise ArtifactIneligible("waveform_file_missing")
        if not hmac.compare_digest(sha256_file(record.path), record.source_sha256):
            raise ArtifactIneligible("waveform_source_hash_mismatch")
        try:
            import numpy as np
            from scipy.io import loadmat
            from scipy.signal import butter, filtfilt, iirnotch, medfilt
        except ImportError as exc:
            raise RuntimeUnavailable("numpy_scipy_runtime_not_installed") from exc

        try:
            raw = loadmat(record.path, variable_names=["signal"]).get("signal")
        except Exception as exc:
            raise ArtifactIneligible("waveform_mat_read_failed") from exc
        if raw is None:
            raise ArtifactIneligible("waveform_signal_variable_missing")
        signal = np.asarray(raw)
        if signal.shape != (12, POINTS_PER_LEAD):
            raise ArtifactIneligible("waveform_shape_must_be_12_by_5000")
        if not np.issubdtype(signal.dtype, np.number) or np.iscomplexobj(signal):
            raise ArtifactIneligible("waveform_signal_must_be_real_numeric")
        finite_ratio = np.mean(np.isfinite(signal), axis=1)
        if np.any(finite_ratio < 0.999):
            raise ArtifactIneligible("waveform_lead_non_finite_ratio")
        signal = np.nan_to_num(
            signal.astype(np.float64, copy=False),
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )
        lead_std = np.std(signal, axis=1)
        if np.any(lead_std <= 1e-12):
            raise ArtifactIneligible("waveform_contains_flat_lead")
        for lead in signal:
            low_count = int(np.count_nonzero(lead == np.min(lead)))
            high_count = int(np.count_nonzero(lead == np.max(lead)))
            if max(low_count, high_count) / lead.size > 0.20:
                raise ArtifactIneligible("waveform_lead_clipping_or_saturation")

        lead_indices = [record.source_lead_names.index(lead) for lead in MODEL_LEADS]
        signal = signal[lead_indices, :]

        notch_b, notch_a = iirnotch(50, 30, SAMPLE_RATE_HZ)
        filtered = np.zeros_like(signal)
        for channel in range(signal.shape[0]):
            filtered[channel] = filtfilt(notch_b, notch_a, signal[channel])
        band_b, band_a = butter(
            N=4,
            Wn=[0.67, 40],
            btype="bandpass",
            fs=SAMPLE_RATE_HZ,
        )
        for channel in range(filtered.shape[0]):
            filtered[channel] = filtfilt(
                band_b,
                band_a,
                filtered[channel],
            )
        baseline = np.zeros_like(filtered)
        for channel in range(filtered.shape[0]):
            baseline[channel] = medfilt(filtered[channel], kernel_size=201)
        filtered -= baseline
        normalized = (filtered - np.mean(filtered)) / (np.std(filtered) + 1e-8)
        if not np.isfinite(normalized).all():
            raise ArtifactIneligible("waveform_preprocessing_produced_non_finite_data")
        return np.ascontiguousarray(normalized, dtype=np.float32)

    def analyze(
        self, record: ArtifactRecord, *, max_predictions: int
    ) -> dict[str, Any]:
        self._ensure_model()
        signal = self._load_and_preprocess(record)
        assert self._torch is not None
        assert self._model is not None
        with self._inference_lock, self._torch.inference_mode():
            tensor = self._torch.from_numpy(signal).unsqueeze(0)
            probabilities = self._torch.sigmoid(self._model(tensor))[0]
            scores = probabilities.detach().cpu().tolist()
        ranked = sorted(
            zip(self._tasks, scores, strict=True),
            key=lambda pair: pair[1],
            reverse=True,
        )[:max_predictions]
        thresholds = self._calibration.thresholds or {}
        predictions = []
        for label, probability in ranked:
            prediction: dict[str, object] = {
                "label": label,
                "probability": round(float(probability), 8),
            }
            if self._calibration.status == "validated":
                prediction["threshold"] = thresholds[label]
            predictions.append(prediction)

        limitations = [
            "Supporting waveform evidence only; clinician review remains required.",
            "The model provides no image bounding boxes or spatial localization.",
            "Scores were trained for ECG statement classification and are not independent diagnoses.",
        ]
        if self._calibration.status != "validated":
            limitations.append(
                "No deployment calibration is installed; probabilities must not be thresholded as positive or negative."
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok",
            "model": {
                "id": MODEL_ID,
                "revision": MODEL_REVISION,
                "checkpoint_sha256": CHECKPOINT_SHA256_12_LEAD,
            },
            "input": {
                "source_kind": record.source_kind,
                "source_sha256": record.source_sha256,
                "source_sample_rate_hz": record.source_sample_rate_hz,
                "model_sample_rate_hz": SAMPLE_RATE_HZ,
                "model_duration_sec": DURATION_SEC,
                "model_points_per_lead": POINTS_PER_LEAD,
                "lead_names": list(MODEL_LEADS),
            },
            "preprocessing": {
                "implementation": "dicom-overlay-agent ECGFounder sidecar",
                "implementation_revision": self._preprocessing_revision,
                "upstream_revision": MODEL_REVISION,
                "steps": [
                    "verify trusted registry metadata and source SHA-256",
                    "load MATLAB signal variable with required shape 12x5000",
                    "replace non-finite samples with zero",
                    "reorder MIMIC leads I,II,III,aVR,aVF,aVL,V1-V6 to ECGFounder I,II,III,aVR,aVL,aVF,V1-V6",
                    "50 Hz notch filter, Q=30",
                    "fourth-order 0.67-40 Hz Butterworth band-pass filter",
                    "subtract 0.4-second median-filter baseline",
                    "global z-score normalization across all leads and samples",
                ],
            },
            "calibration": {
                "status": self._calibration.status,
                "dataset": self._calibration.dataset,
                "revision": self._calibration.revision,
            },
            "predictions": predictions,
            "limitations": limitations,
        }


class ECGFounderService:
    def __init__(
        self,
        *,
        registry: dict[str, ArtifactRecord],
        runtime: ECGFounderRuntime,
    ) -> None:
        self._registry = registry
        self._runtime = runtime

    @property
    def artifact_count(self) -> int:
        return len(self._registry)

    def health(self, *, deep: bool) -> dict[str, Any]:
        try:
            if deep:
                self._runtime.ensure_ready()
        except RuntimeUnavailable as exc:
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "unavailable",
                "reason": str(exc),
                "model_id": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "checkpoint_sha256": CHECKPOINT_SHA256_12_LEAD,
                "preprocessing_revision": self._runtime.preprocessing_revision,
                "artifact_count": self.artifact_count,
                "deep": deep,
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ready" if self._runtime.ready else "configured",
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "checkpoint_sha256": CHECKPOINT_SHA256_12_LEAD,
            "preprocessing_revision": self._runtime.preprocessing_revision,
            "artifact_count": self.artifact_count,
            "deep": deep,
        }

    def analyze(self, request: object) -> dict[str, Any]:
        if (
            not isinstance(request, dict)
            or request.get("schema_version") != SCHEMA_VERSION
        ):
            return _status_payload("ineligible", "invalid_request_schema")
        artifact_id = request.get("artifact_id")
        lead_mode = request.get("lead_mode")
        if not isinstance(artifact_id, str) or not _ARTIFACT_ID.fullmatch(artifact_id):
            return _status_payload("ineligible", "invalid_artifact_id")
        if lead_mode != "12_lead":
            return _status_payload("ineligible", "unsupported_lead_mode")
        record = self._registry.get(artifact_id)
        if record is None:
            return _status_payload("ineligible", "artifact_not_registered")
        try:
            requested_max = int(request.get("max_predictions", 10))
        except (TypeError, ValueError):
            return _status_payload("ineligible", "invalid_max_predictions")
        max_predictions = min(MAX_PREDICTIONS, max(1, requested_max))
        return analyze_record(
            self._runtime,
            record,
            max_predictions=max_predictions,
        )


def analyze_record(
    runtime: ECGFounderRuntime,
    record: ArtifactRecord,
    *,
    max_predictions: int,
) -> dict[str, Any]:
    """Run one trusted record with caller-owned output-size policy."""
    try:
        return runtime.analyze(record, max_predictions=max_predictions)
    except ArtifactIneligible as exc:
        return _status_payload("ineligible", str(exc))
    except RuntimeUnavailable as exc:
        return _status_payload("unavailable", str(exc))
    except Exception:
        return _status_payload("error", "sidecar_inference_failed")


def _status_payload(status: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "reason": reason,
        "predictions": [],
        "limitations": [
            "No waveform classification evidence is available for this request."
        ],
    }


def _authorized(headers: Any, token: str) -> bool:
    supplied = str(headers.get("authorization") or "")
    return hmac.compare_digest(supplied, f"Bearer {token}")


def build_handler(
    service: ECGFounderService,
    *,
    token: str,
    endpoint_path: str = "/v1/analyze",
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "ECGFounderSidecar/1"
        sys_version = ""

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path != "/health":
                self._json(HTTPStatus.NOT_FOUND, {"status": "not_found"})
                return
            if not _authorized(self.headers, token):
                self._json(HTTPStatus.UNAUTHORIZED, {"status": "unauthorized"})
                return
            deep = parse_qs(parsed.query).get("deep") == ["1"]
            payload = service.health(deep=deep)
            status = (
                HTTPStatus.OK
                if payload["status"] != "unavailable"
                else HTTPStatus.SERVICE_UNAVAILABLE
            )
            self._json(status, payload)

        def do_POST(self) -> None:
            if urlsplit(self.path).path != endpoint_path:
                self._json(HTTPStatus.NOT_FOUND, {"status": "not_found"})
                return
            if not _authorized(self.headers, token):
                self._json(HTTPStatus.UNAUTHORIZED, {"status": "unauthorized"})
                return
            try:
                content_length = int(self.headers.get("content-length") or "0")
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
                self._json(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"status": "invalid_request_size"},
                )
                return
            body = self.rfile.read(content_length)
            try:
                request = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json(HTTPStatus.BAD_REQUEST, {"status": "invalid_json"})
                return
            self._json(HTTPStatus.OK, service.analyze(request))

    return Handler


def _loopback_host(value: str) -> str:
    host = value.strip().lower()
    if host == "localhost":
        return "127.0.0.1"
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("sidecar host must be loopback") from exc
    if not address.is_loopback:
        raise argparse.ArgumentTypeError("sidecar host must be loopback")
    return str(address)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=os.environ.get("DICOM_ECGFOUNDER_REGISTRY", ""),
        required=not bool(os.environ.get("DICOM_ECGFOUNDER_REGISTRY")),
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=os.environ.get("DICOM_ECGFOUNDER_CHECKPOINT", ""),
        required=not bool(os.environ.get("DICOM_ECGFOUNDER_CHECKPOINT")),
    )
    parser.add_argument("--tasks", type=Path, default=base_dir / "tasks.txt")
    parser.add_argument("--calibration", type=Path, default=None)
    parser.add_argument("--token", default=os.environ.get("DICOM_ECGFOUNDER_TOKEN", ""))
    parser.add_argument("--host", type=_loopback_host, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18790)
    parser.add_argument("--self-test-artifact", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if len(args.token) < 32:
        raise SystemExit("DICOM_ECGFOUNDER_TOKEN must contain at least 32 characters")
    if not 1 <= args.port <= 65535:
        raise SystemExit("port must be in 1..65535")
    try:
        registry = load_registry(args.registry)
        runtime = ECGFounderRuntime(
            checkpoint_path=args.checkpoint,
            tasks_path=args.tasks,
            calibration_path=args.calibration,
        )
    except (RegistryError, RuntimeUnavailable) as exc:
        raise SystemExit(str(exc)) from exc
    service = ECGFounderService(registry=registry, runtime=runtime)
    if args.self_test_artifact:
        result = service.analyze(
            {
                "schema_version": SCHEMA_VERSION,
                "artifact_id": args.self_test_artifact,
                "lead_mode": "12_lead",
                "max_predictions": 10,
            }
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") == "ok" else 2

    server = ThreadingHTTPServer(
        (args.host, args.port),
        build_handler(service, token=args.token),
    )
    print(
        json.dumps(
            {
                "status": "configured",
                "endpoint": f"http://{args.host}:{args.port}/v1/analyze",
                "deep_health": f"http://{args.host}:{args.port}/health?deep=1",
                "artifact_count": service.artifact_count,
                "model_revision": MODEL_REVISION,
            }
        ),
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
