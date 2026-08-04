"""Reproducible sequential ECGFounder evaluation over a paired MEETI registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean, median
from typing import Any

from sidecars.ecgfounder.server import (
    CHECKPOINT_SHA256_12_LEAD,
    MODEL_ID,
    MODEL_REVISION,
    ECGFounderRuntime,
    analyze_record,
    load_registry,
    preprocessing_revision,
    sha256_file,
)

SCHEMA_VERSION = 1
MAX_OFFLINE_PREDICTIONS = 150
RUNNER_ID = "ecgfounder-meeti-batch-v3"
DEFAULT_REGISTRY = Path("data/eval-datasets/meeti-1000-all/waveform-registry.json")
DEFAULT_MANIFEST = Path("data/eval-datasets/meeti-1000-all/manifest.json")
DEFAULT_CHECKPOINT = Path(
    "data/external/ecgfounder-runtime/checkpoints/12_lead_ECGFounder.pth"
)


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def load_paired_cases(
    manifest_path: Path,
    *,
    registry_ids: set[str],
    max_cases: int = 0,
) -> list[dict[str, Any]]:
    manifest = _read_json_object(manifest_path)
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("MEETI manifest has no cases")
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, dict):
            raise ValueError(f"manifest case {index} is not an object")
        artifact_id = str(raw_case.get("waveform_artifact_id") or "").strip()
        if not artifact_id:
            raise ValueError(f"manifest case {index} has no waveform artifact")
        if artifact_id not in registry_ids:
            raise ValueError(f"manifest case {index} references an unknown artifact")
        if artifact_id in seen:
            raise ValueError(f"duplicate waveform artifact in manifest: {artifact_id}")
        seen.add(artifact_id)
        cases.append(
            {
                "artifact_id": artifact_id,
                "lead_mode": str(raw_case.get("waveform_lead_mode") or "12_lead"),
                "case_label": str(raw_case.get("label") or f"case-{index + 1}"),
                "expected_severity": str(raw_case.get("expected_severity") or ""),
                "label_status": str(raw_case.get("label_status") or ""),
                "concepts": [
                    str(item)
                    for item in raw_case.get("concepts", [])
                    if isinstance(item, str)
                ],
                "uncertain_concepts": [
                    str(item)
                    for item in raw_case.get("uncertain_concepts", [])
                    if isinstance(item, str)
                ],
                "ungradable_reasons": [
                    str(item)
                    for item in raw_case.get("ungradable_reasons", [])
                    if isinstance(item, str)
                ],
                "urgent_concerns": [
                    str(item)
                    for item in raw_case.get("urgent_concerns", [])
                    if isinstance(item, str)
                ],
                "reference_report_sha256": hashlib.sha256(
                    str(raw_case.get("report") or "").encode("utf-8")
                ).hexdigest(),
            }
        )
        if max_cases > 0 and len(cases) >= max_cases:
            break
    return cases


def build_protocol(
    *,
    registry_path: Path,
    manifest_path: Path,
    checkpoint_path: Path,
    calibration_path: Path | None,
    max_predictions: int,
    case_count: int,
) -> dict[str, Any]:
    sidecar_dir = Path(__file__).resolve().parent
    protocol: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "runner": RUNNER_ID,
        "runner_revision": sha256_file(Path(__file__).resolve()),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "expected_checkpoint_sha256": CHECKPOINT_SHA256_12_LEAD,
        "registry_sha256": sha256_file(registry_path),
        "manifest_sha256": sha256_file(manifest_path),
        "preprocessing_revision": preprocessing_revision(sidecar_dir),
        "calibration_sha256": (
            sha256_file(calibration_path) if calibration_path is not None else ""
        ),
        "calibration_status": "validated" if calibration_path is not None else "uncalibrated",
        "max_predictions": max_predictions,
        "case_count": case_count,
        "execution": "sequential_cpu",
    }
    protocol["fingerprint"] = _canonical_hash(protocol)
    return protocol


def _write_json_atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_completed(
    results_path: Path,
) -> tuple[set[str], Counter[str], Counter[str], list[float]]:
    completed: set[str] = set()
    statuses: Counter[str] = Counter()
    top_labels: Counter[str] = Counter()
    latencies_ms: list[float] = []
    if not results_path.is_file():
        return completed, statuses, top_labels, latencies_ms
    with results_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid results JSONL at line {line_number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"invalid results JSONL object at line {line_number}")
            artifact_id = str(row.get("artifact_id") or "")
            if not artifact_id or artifact_id in completed:
                raise ValueError("results JSONL has a missing or duplicate artifact id")
            completed.add(artifact_id)
            statuses[str(row.get("status") or "unknown")] += 1
            try:
                latency_ms = float(row.get("latency_ms"))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid result latency at line {line_number}"
                ) from exc
            if latency_ms < 0:
                raise ValueError(f"negative result latency at line {line_number}")
            latencies_ms.append(latency_ms)
            predictions = row.get("predictions")
            if isinstance(predictions, list) and predictions:
                first = predictions[0]
                if isinstance(first, dict) and first.get("label"):
                    top_labels[str(first["label"])] += 1
    return completed, statuses, top_labels, latencies_ms


def _latency_stats(latencies_ms: list[float]) -> dict[str, float | int]:
    if not latencies_ms:
        return {
            "count": 0,
            "total_ms": 0.0,
            "mean_ms": 0.0,
            "median_ms": 0.0,
            "p95_ms": 0.0,
            "max_ms": 0.0,
        }
    ordered = sorted(latencies_ms)
    count = len(ordered)
    return {
        "count": count,
        "total_ms": round(sum(ordered), 3),
        "mean_ms": round(fmean(ordered), 3),
        "median_ms": round(median(ordered), 3),
        "p95_ms": round(ordered[min(count - 1, int(count * 0.95))], 3),
        "max_ms": round(ordered[-1], 3),
    }


def _summary(
    *,
    protocol: dict[str, Any],
    statuses: Counter[str],
    top_labels: Counter[str],
    latencies_ms: list[float],
    elapsed_sec: float,
    started_at: str,
) -> dict[str, Any]:
    completed = sum(statuses.values())
    target = int(protocol["case_count"])
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete" if completed == target and statuses.get("ok", 0) == target else "incomplete",
        "started_at": started_at,
        "updated_at": datetime.now(UTC).isoformat(),
        "protocol": protocol,
        "target_case_count": target,
        "completed_case_count": completed,
        "status_counts": dict(sorted(statuses.items())),
        "top_prediction_counts": dict(top_labels.most_common()),
        "elapsed_sec_this_invocation": round(elapsed_sec, 3),
        "recorded_inference_latency": _latency_stats(latencies_ms),
        "interpretation": {
            "use_policy": "supporting_evidence_only",
            "calibration_warning": (
                "Uncalibrated scores are rankings only and must not be converted "
                "to positive/negative diagnoses."
                if protocol["calibration_status"] == "uncalibrated"
                else "Installed thresholds are valid only for their recorded calibration cohort."
            ),
            "spatial_localization": "not_provided",
            "accuracy_claim": "not_computed_by_this_waveform-only runner",
        },
    }


def run_batch(
    *,
    registry_path: Path,
    manifest_path: Path,
    checkpoint_path: Path,
    output_dir: Path,
    calibration_path: Path | None = None,
    max_cases: int = 0,
    max_predictions: int = 20,
    resume: bool = False,
    progress_every: int = 25,
) -> int:
    if not 1 <= max_predictions <= MAX_OFFLINE_PREDICTIONS:
        raise ValueError(
            f"max_predictions must be in 1..{MAX_OFFLINE_PREDICTIONS}"
        )
    registry_path = registry_path.resolve()
    manifest_path = manifest_path.resolve()
    checkpoint_path = checkpoint_path.resolve()
    calibration_path = calibration_path.resolve() if calibration_path else None
    output_dir = output_dir.resolve()
    if sha256_file(checkpoint_path) != CHECKPOINT_SHA256_12_LEAD:
        raise ValueError("checkpoint SHA-256 does not match the pinned official weight")
    registry = load_registry(registry_path)
    cases = load_paired_cases(
        manifest_path,
        registry_ids=set(registry),
        max_cases=max_cases,
    )
    protocol = build_protocol(
        registry_path=registry_path,
        manifest_path=manifest_path,
        checkpoint_path=checkpoint_path,
        calibration_path=calibration_path,
        max_predictions=max_predictions,
        case_count=len(cases),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    protocol_path = output_dir / "protocol.json"
    results_path = output_dir / "results.jsonl"
    summary_path = output_dir / "summary.json"
    if protocol_path.exists():
        existing = _read_json_object(protocol_path)
        if existing.get("fingerprint") != protocol["fingerprint"]:
            raise ValueError("output directory contains a different experiment protocol")
        if not resume and results_path.exists():
            raise ValueError("results already exist; pass --resume or choose a new output directory")
    else:
        if results_path.exists():
            raise ValueError("results exist without a protocol record")
        _write_json_atomic(protocol_path, protocol)

    completed, statuses, top_labels, latencies_ms = _load_completed(results_path)
    if completed and not resume:
        raise ValueError("results already exist; pass --resume")
    unknown_completed = completed - {case["artifact_id"] for case in cases}
    if unknown_completed:
        raise ValueError("results contain artifacts outside the selected manifest cohort")

    runtime = ECGFounderRuntime(
        checkpoint_path=checkpoint_path,
        tasks_path=Path(__file__).resolve().parent / "tasks.txt",
        calibration_path=calibration_path,
    )
    started_at = datetime.now(UTC).isoformat()
    invocation_started = time.perf_counter()
    pending = [case for case in cases if case["artifact_id"] not in completed]
    with results_path.open("a", encoding="utf-8", buffering=1) as stream:
        for offset, case in enumerate(pending, start=1):
            case_started = time.perf_counter()
            result = analyze_record(
                runtime,
                registry[case["artifact_id"]],
                max_predictions=max_predictions,
            )
            elapsed_ms = round((time.perf_counter() - case_started) * 1000, 3)
            row = {
                "schema_version": SCHEMA_VERSION,
                "artifact_id": case["artifact_id"],
                "case": {key: value for key, value in case.items() if key != "artifact_id"},
                "latency_ms": elapsed_ms,
                **result,
            }
            stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
            status = str(result.get("status") or "unknown")
            statuses[status] += 1
            latencies_ms.append(elapsed_ms)
            predictions = result.get("predictions")
            if isinstance(predictions, list) and predictions:
                first = predictions[0]
                if isinstance(first, dict) and first.get("label"):
                    top_labels[str(first["label"])] += 1
            completed.add(case["artifact_id"])
            if offset % max(1, progress_every) == 0 or offset == len(pending):
                elapsed = time.perf_counter() - invocation_started
                _write_json_atomic(
                    summary_path,
                    _summary(
                        protocol=protocol,
                        statuses=statuses,
                        top_labels=top_labels,
                        latencies_ms=latencies_ms,
                        elapsed_sec=elapsed,
                        started_at=started_at,
                    ),
                )
                print(
                    f"[ecgfounder] {len(completed)}/{len(cases)} "
                    f"ok={statuses.get('ok', 0)} elapsed={elapsed:.1f}s",
                    flush=True,
                )

    elapsed = time.perf_counter() - invocation_started
    summary = _summary(
        protocol=protocol,
        statuses=statuses,
        top_labels=top_labels,
        latencies_ms=latencies_ms,
        elapsed_sec=elapsed,
        started_at=started_at,
    )
    _write_json_atomic(summary_path, summary)
    return 0 if summary["status"] == "complete" else 2


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("data/eval-runs") / f"ecgfounder-meeti-{stamp}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument(
        "--max-predictions",
        type=int,
        default=20,
        choices=range(1, MAX_OFFLINE_PREDICTIONS + 1),
        help="Ranked scores to persist offline (1-150); HTTP tool responses stay capped at 20.",
    )
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_batch(
            registry_path=args.registry,
            manifest_path=args.manifest,
            checkpoint_path=args.checkpoint,
            calibration_path=args.calibration,
            output_dir=args.output_dir or _default_output_dir(),
            max_cases=max(0, args.max_cases),
            max_predictions=args.max_predictions,
            progress_every=max(1, args.progress_every),
            resume=args.resume,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
