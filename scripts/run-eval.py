"""Run the recognition evaluation harness and write a scorecard.

Usage::

    # Pipeline verification (no token needed) -- proves how results are scored:
    uv run python scripts/run-eval.py --mock

    # Real accuracy benchmark (start the OpenClaw Gateway first, see RUNBOOK):
    set ANTHROPIC_API_KEY=...    # in your shell, NOT in code
    uv run python scripts/run-eval.py --gateway ws://127.0.0.1:18789

The two modes share identical scoring (``eval_harness.run_evaluation``); only the
source of the structured result differs. Artifacts land in
``data/eval/<timestamp>/`` (scorecard.json + per-image raw results).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import structlog
import websockets

if TYPE_CHECKING:
    from collections.abc import Mapping

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dicom_overlay.application.hooked_analyzer import HookedVisionAnalyzer  # noqa: E402
from dicom_overlay.application.multi_pass import (  # noqa: E402
    DEFAULT_FIRST_REFINEMENT_SLA_SEC,
    DEFAULT_INITIAL_RESPONSE_SLA_SEC,
    DEFAULT_MAX_EKG_SYSTEMATIC_PROBES,
    DEFAULT_TOTAL_ANALYSIS_SLA_SEC,
    MultiPassAnalyzer,
    MultiPassInterpreter,
)
from dicom_overlay.application.rhythm_strip import (  # noqa: E402
    refine_rhythm_strip,
    resolve_rhythm_strip_region,
)
from dicom_overlay.domain.entities import Modality, RegionRect, Severity  # noqa: E402
from dicom_overlay.domain.modality_profile import get_active_registry  # noqa: E402
from dicom_overlay.domain.services import VisionAnalyzerService  # noqa: E402
from dicom_overlay.infrastructure.bbox_signal_calibrator import (  # noqa: E402
    calibrate_ekg_bboxes,
)
from dicom_overlay.infrastructure.clinical_rule_loader import (  # noqa: E402
    build_clinical_engine,
)
from dicom_overlay.infrastructure.eval_artifact_validator import (  # noqa: E402
    _valid_ecg_founder_evidence,
)
from dicom_overlay.infrastructure.eval_harness import (  # noqa: E402
    EvalCase,
    EvalReport,
    is_empty_read,
    run_evaluation,
)
from dicom_overlay.infrastructure.gateway_manager import (  # noqa: E402
    ecg_founder_tool_enabled,
)
from dicom_overlay.infrastructure.hooks.bbox_calibration import (  # noqa: E402
    BboxCalibrationHook,
)
from dicom_overlay.infrastructure.hooks.clinical_consistency import (  # noqa: E402
    ClinicalConsistencyHook,
)
from dicom_overlay.infrastructure.hooks.input_guard import InputGuard  # noqa: E402
from dicom_overlay.infrastructure.hooks.output_validator import (  # noqa: E402
    OutputValidator,
)
from dicom_overlay.infrastructure.openclaw_client import (  # noqa: E402
    OpenClawClient,
    _bbox_coordinates_digest,
)
from dicom_overlay.infrastructure.screen_monitor import ImageProcessor  # noqa: E402

logger = structlog.get_logger(__name__)

_DATASET_DIR = _REPO_ROOT / "data" / "eval-datasets"
# Match the production default (entities.OpenClawConfig.max_image_edge_px).
_MAX_IMAGE_EDGE_PX = 1568
_DEFAULT_TIMEOUT_SEC = int(DEFAULT_TOTAL_ANALYSIS_SLA_SEC)
_PROTOCOL_FINGERPRINT_NAME = "protocol-fingerprint.json"
_PROTOCOL_FINGERPRINT_SCHEMA_VERSION = 1
_ECG_FOUNDER_MODEL_ID = "PKUDigitalHealth/ECGFounder"
_PROTOCOL_SOURCE_PATHS = (
    "src/dicom_overlay",
    "scripts/run-eval.py",
    "scripts/rebuild-eval-scorecard.py",
    "scripts/export-eval-annotations.py",
    "scripts/verify-eval-artifacts.py",
    "scripts/run-meeti-openclaw-experiment.py",
    "scripts/run-meeti-paired-experiment.py",
    "scripts/compare-eval-runs.py",
    "openclaw/workspace/plugins/dicom-overlay-agent-harness",
    "openclaw/workspace/skills",
    "sidecars/ecgfounder",
    "clinical_rules",
    "pyproject.toml",
)
_ECG_FOUNDER_MODEL_REVISION = "04edac702b61c91face519774ddcc0cd712fef23"
_ECG_FOUNDER_CHECKPOINT_SHA256 = (
    "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997"
)
_PROMPT_SOURCE_PATHS = (
    "src/dicom_overlay/application/hooked_analyzer.py",
    "src/dicom_overlay/application/interpretation_harness.py",
    "src/dicom_overlay/application/multi_pass.py",
    "src/dicom_overlay/application/rhythm_strip.py",
    "src/dicom_overlay/domain/ekg_layout.py",
    "src/dicom_overlay/infrastructure/bbox_signal_calibrator.py",
    "src/dicom_overlay/infrastructure/clinical_rule_loader.py",
    "src/dicom_overlay/infrastructure/hooks/clinical_consistency.py",
    "src/dicom_overlay/infrastructure/hooks/bbox_calibration.py",
    "src/dicom_overlay/infrastructure/hooks/input_guard.py",
    "src/dicom_overlay/infrastructure/hooks/output_validator.py",
    "src/dicom_overlay/infrastructure/openclaw_client.py",
    "src/dicom_overlay/infrastructure/eval_harness.py",
    "scripts/run-eval.py",
)
_EKG_VALID_REGIONS = (
    "lead_I",
    "lead_II",
    "lead_III",
    "lead_aVR",
    "lead_aVL",
    "lead_aVF",
    "lead_V1",
    "lead_V2",
    "lead_V3",
    "lead_V4",
    "lead_V5",
    "lead_V6",
    "rhythm_strip",
)
_CXR_VALID_REGIONS = (
    "trachea",
    "right_upper_lung",
    "right_middle_lung",
    "right_lower_lung",
    "left_upper_lung",
    "left_middle_lung",
    "left_lower_lung",
    "right_cp_angle",
    "left_cp_angle",
    "cardiac_silhouette",
    "mediastinum",
    "diaphragm",
)
_CT_BRAIN_VALID_REGIONS = (
    "right_frontal",
    "left_frontal",
    "right_temporal",
    "left_temporal",
    "right_basal_ganglia",
    "left_basal_ganglia",
    "ventricles",
    "midline",
    "posterior_fossa",
)
_DEFAULT_VALID_REGIONS = {
    Modality.EKG: _EKG_VALID_REGIONS,
    Modality.CXR: _CXR_VALID_REGIONS,
    Modality.CT_BRAIN: _CT_BRAIN_VALID_REGIONS,
}
_EKG_CHECKLIST_KEYS = [
    "heart_rate",
    "rhythm",
    "regularity",
    "axis",
    "p_wave",
    "pr_interval",
    "qrs_duration",
    "qrs_morphology",
    "st_segment",
    "t_wave",
    "qtc_interval",
    "chamber_enlargement",
    "conduction",
    "av_block",
    "stemi_pattern",
    "ischemia",
]
_CXR_CHECKLIST_KEYS = [
    "airway",
    "lungs",
    "pleura",
    "cardiac_silhouette",
    "mediastinum",
    "hila",
    "diaphragm",
    "bones",
    "soft_tissue",
    "lines_tubes",
]


def _valid_regions_for(entry: dict[str, Any], modality: Modality) -> tuple[str, ...]:
    explicit = entry.get("valid_regions")
    if explicit:
        return tuple(str(item) for item in explicit)
    return tuple(_DEFAULT_VALID_REGIONS.get(modality, ()))


def _clamp_unit(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _local_candidate_regions_from_signal(
    signal: dict[str, object],
    *,
    max_regions: int,
) -> list[RegionRect]:
    """Convert local image-signal candidates into normalized crop regions."""
    if max_regions <= 0:
        return []
    raw_candidates = signal.get("candidates", [])
    if not isinstance(raw_candidates, list):
        return []

    regions: list[RegionRect] = []
    for raw in raw_candidates:
        if len(regions) >= max_regions:
            break
        if not isinstance(raw, dict):
            continue
        try:
            x = float(raw["x"])
            y = float(raw["y"])
            w = float(raw["w"])
            h = float(raw["h"])
        except (KeyError, TypeError, ValueError):
            continue
        x0 = _clamp_unit(x)
        y0 = _clamp_unit(y)
        x1 = _clamp_unit(x + w)
        y1 = _clamp_unit(y + h)
        width = round(x1 - x0, 6)
        height = round(y1 - y0, 6)
        if width <= 0.0 or height <= 0.0:
            continue
        regions.append(
            RegionRect(
                x=round(x0, 6),
                y=round(y0, 6),
                w=width,
                h=height,
            )
        )
    return regions


class ProtocolFingerprintError(RuntimeError):
    """Raised when an eval directory cannot be resumed without mixing protocols."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _protocol_digest(protocol: dict[str, Any]) -> str:
    encoded = json.dumps(
        protocol,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _openclaw_config_identity(config_path: Path | None) -> dict[str, Any]:
    """Hash semantic config while excluding OpenClaw's volatile touch timestamp."""

    if config_path is None or not config_path.is_file():
        return {
            "configured": config_path is not None,
            "path": config_path.name if config_path is not None else "",
            "identity": "canonical_json_without_meta.lastTouchedAt",
            "sha256": "",
        }
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolFingerprintError(
            f"could not parse active OpenClaw config {config_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProtocolFingerprintError("active OpenClaw config must be a JSON object")
    meta = payload.get("meta")
    if isinstance(meta, dict) and "lastTouchedAt" in meta:
        stable_meta = dict(meta)
        stable_meta.pop("lastTouchedAt", None)
        payload = dict(payload)
        if stable_meta:
            payload["meta"] = stable_meta
        else:
            payload.pop("meta", None)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return {
        "configured": True,
        "path": config_path.name,
        "identity": "canonical_json_without_meta.lastTouchedAt",
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _path_for_fingerprint(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _git_identity(repo_root: Path) -> dict[str, Any]:
    def run(*args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *args],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    commit_result = run("rev-parse", "HEAD")
    status_result = run(
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        *_PROTOCOL_SOURCE_PATHS,
    )
    diff_result = run(
        "diff",
        "--binary",
        "--no-ext-diff",
        "HEAD",
        "--",
        *_PROTOCOL_SOURCE_PATHS,
    )
    files_result = run(
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
        "--",
        *_PROTOCOL_SOURCE_PATHS,
    )
    available = all(
        result.returncode == 0
        for result in (commit_result, status_result, diff_result, files_result)
    )
    if not available:
        return {
            "available": False,
            "commit": "unknown",
            "dirty": None,
            "scope": list(_PROTOCOL_SOURCE_PATHS),
            "tracked_diff_sha256": "",
            "worktree_content_sha256": "",
            "worktree_file_count": 0,
        }
    relative_files = sorted(
        {
            os.fsdecode(raw)
            for raw in files_result.stdout.split(b"\0")
            if raw
        }
    )
    content_digest = hashlib.sha256()
    for relative_text in relative_files:
        normalized = Path(relative_text).as_posix()
        content_digest.update(normalized.encode("utf-8", errors="surrogateescape"))
        content_digest.update(b"\0")
        path = repo_root / relative_text
        if not path.is_file():
            content_digest.update(b"missing\0")
            continue
        content_digest.update(b"file\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                content_digest.update(chunk)
        content_digest.update(b"\0")
    return {
        "available": True,
        "commit": commit_result.stdout.decode("ascii", errors="replace").strip(),
        "dirty": bool(status_result.stdout.strip()),
        "scope": list(_PROTOCOL_SOURCE_PATHS),
        "worktree_status_sha256": hashlib.sha256(status_result.stdout).hexdigest(),
        "tracked_diff_sha256": hashlib.sha256(diff_result.stdout).hexdigest(),
        "worktree_content_sha256": content_digest.hexdigest(),
        "worktree_file_count": len(relative_files),
    }


def _hash_named_files(
    repo_root: Path, relative_paths: tuple[str, ...]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative in relative_paths:
        path = repo_root / relative
        records.append(
            {
                "path": relative,
                "exists": path.is_file(),
                "sha256": _sha256_file(path) if path.is_file() else "",
            }
        )
    return records


def _tree_identity(repo_root: Path, relative_root: str) -> list[dict[str, Any]]:
    root = repo_root / relative_root
    if not root.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        records.append(
            {
                "path": _path_for_fingerprint(path, repo_root),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return records


def _skill_identity(repo_root: Path) -> list[dict[str, Any]]:
    return _tree_identity(repo_root, "openclaw/workspace/skills")


def _openclaw_identity(repo_root: Path) -> dict[str, Any]:
    package_path = repo_root / "openclaw" / "node_modules" / "openclaw" / "package.json"
    cli_path = package_path.parent / "openclaw.mjs"
    version = "unknown"
    if package_path.is_file():
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            version = str(package.get("version") or "unknown")
        except (OSError, json.JSONDecodeError):
            version = "unreadable"
    return {
        "version": version,
        "package_sha256": _sha256_file(package_path) if package_path.is_file() else "",
        "cli_sha256": _sha256_file(cli_path) if cli_path.is_file() else "",
    }


def _manifest_identity(
    manifest_path: Path,
    cases: list[EvalCase],
) -> dict[str, Any]:
    labels: set[str] = set()
    result_filenames: set[str] = set()
    identities: list[dict[str, Any]] = []
    # A manifest may intentionally assign several blinded case identities to
    # one immutable source object (for example, an offline scale-plumbing
    # fixture).  Cache content identity by resolved path so protocol freezing
    # remains O(case count) without re-reading identical bytes per identity.
    source_identity_cache: dict[Path, tuple[int, str]] = {}
    for case in cases:
        label = case.label or case.image_path.name
        result_filename = _result_filename(label)
        if label in labels:
            raise ProtocolFingerprintError(f"duplicate manifest case label: {label}")
        if result_filename in result_filenames:
            raise ProtocolFingerprintError(
                "manifest case labels collide after filename sanitization: "
                f"{result_filename}"
            )
        labels.add(label)
        result_filenames.add(result_filename)
        image_path = case.image_path.resolve()
        if not image_path.is_file():
            raise ProtocolFingerprintError(
                f"manifest image does not exist for {label}: {image_path}"
            )
        source_identity = source_identity_cache.get(image_path)
        if source_identity is None:
            source_identity = (image_path.stat().st_size, _sha256_file(image_path))
            source_identity_cache[image_path] = source_identity
        size_bytes, source_sha256 = source_identity
        identities.append(
            {
                "case": label,
                "image": _path_for_fingerprint(image_path, manifest_path.parent),
                "image_name": image_path.name,
                "size_bytes": size_bytes,
                "sha256": source_sha256,
            }
        )
    return {
        "path": manifest_path.name,
        "sha256": _sha256_file(manifest_path),
        "selected_case_count": len(identities),
        "cases": identities,
    }


def _build_protocol_fingerprint(
    *,
    manifest_path: Path,
    cases: list[EvalCase],
    model_id: str,
    mode: str,
    flags: dict[str, Any],
    repo_root: Path = _REPO_ROOT,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    environment = env if env is not None else os.environ
    config_path_text = environment.get("OPENCLAW_CONFIG_PATH", "")
    config_path = Path(config_path_text) if config_path_text else None
    config_identity = _openclaw_config_identity(config_path)
    protocol = {
        "source": _git_identity(repo_root),
        "model": {
            "id": model_id,
            "gateway_mode": mode,
            "openclaw": _openclaw_identity(repo_root),
            "openclaw_config": config_identity,
        },
        "prompts": _hash_named_files(repo_root, _PROMPT_SOURCE_PATHS),
        "skills": _skill_identity(repo_root),
        "clinical_rules": _tree_identity(repo_root, "clinical_rules"),
        "manifest": _manifest_identity(manifest_path.resolve(), cases),
        "flags": dict(sorted(flags.items())),
    }
    return {
        "schema_version": _PROTOCOL_FINGERPRINT_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "protocol_scope": "entire_run",
        "protocol_digest": _protocol_digest(protocol),
        "comparability": {
            "status": "comparable",
            "comparable": True,
            "reasons": [],
        },
        "protocol": protocol,
    }


def _read_protocol_fingerprint(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolFingerprintError(
            f"could not parse protocol fingerprint {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProtocolFingerprintError("protocol fingerprint must be a JSON object")
    if payload.get("schema_version") != _PROTOCOL_FINGERPRINT_SCHEMA_VERSION:
        raise ProtocolFingerprintError(
            "unsupported protocol fingerprint schema: "
            f"{payload.get('schema_version')!r}"
        )
    protocol = payload.get("protocol")
    if not isinstance(protocol, dict):
        raise ProtocolFingerprintError("protocol fingerprint is missing protocol data")
    expected_digest = _protocol_digest(protocol)
    if payload.get("protocol_digest") != expected_digest:
        raise ProtocolFingerprintError(
            "protocol fingerprint digest does not match its protocol payload"
        )
    return payload


def _write_protocol_fingerprint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ProtocolFingerprintError(
            f"protocol fingerprint already exists and is immutable: {path}"
        ) from exc


def _prepare_protocol_fingerprint(
    *,
    output_dir: Path,
    current: dict[str, Any],
    cases: list[EvalCase],
    resume: bool,
    legacy_policy: str,
) -> dict[str, Any]:
    fingerprint_path = output_dir / _PROTOCOL_FINGERPRINT_NAME
    result_paths = sorted((output_dir / "results").glob("*.json"))
    existing_evidence = _existing_eval_evidence(output_dir)
    if not resume:
        if existing_evidence:
            raise ProtocolFingerprintError(
                "non-resume run refuses an eval directory containing existing "
                f"artifacts: {', '.join(existing_evidence[:5])}"
            )
        _write_protocol_fingerprint(fingerprint_path, current)
        return current

    if fingerprint_path.exists():
        existing = _read_protocol_fingerprint(fingerprint_path)
        if existing.get("protocol_digest") != current.get("protocol_digest"):
            raise ProtocolFingerprintError(
                "resume protocol mismatch: existing digest "
                f"{existing.get('protocol_digest')} != current "
                f"{current.get('protocol_digest')}"
            )
        comparison = existing.get("comparability")
        comparable = (
            isinstance(comparison, dict) and comparison.get("comparable") is True
        )
        if not comparable and legacy_policy != "mark":
            raise ProtocolFingerprintError(
                "resume target is explicitly marked mixed/non-comparable; use "
                "--resume-legacy-policy mark only to continue it as non-comparable"
            )
        _validate_resume_results(
            cases,
            output_dir,
            protocol_digest=str(existing["protocol_digest"]),
            require_protocol_metadata=comparable,
        )
        return existing

    if existing_evidence:
        if result_paths:
            _validate_resume_results(
                cases,
                output_dir,
                protocol_digest="",
                require_protocol_metadata=False,
            )
        if legacy_policy != "mark":
            raise ProtocolFingerprintError(
                "resume target contains legacy eval artifacts without "
                f"{_PROTOCOL_FINGERPRINT_NAME}; refusing mixed-protocol resume"
            )
        current["protocol_scope"] = "resume_segment_only"
        current["comparability"] = {
            "status": "mixed_protocol_legacy",
            "comparable": False,
            "reasons": ["pre-existing eval artifacts have no protocol fingerprint"],
            "legacy_result_count": len(result_paths),
            "legacy_artifacts": existing_evidence,
        }
        _write_protocol_fingerprint(fingerprint_path, current)
        return current

    _write_protocol_fingerprint(fingerprint_path, current)
    return current


def _existing_eval_evidence(output_dir: Path) -> list[str]:
    evidence: list[Path] = []
    for name in (
        _PROTOCOL_FINGERPRINT_NAME,
        "scorecard.json",
        "scorecard.rebuilt.json",
        "scorecard.partial.json",
        "multipass-trace.jsonl",
    ):
        path = output_dir / name
        if path.exists():
            evidence.append(path)
    results_dir = output_dir / "results"
    if results_dir.is_dir():
        evidence.extend(path for path in results_dir.iterdir() if path.is_file())
    review_dir = output_dir / "review"
    if review_dir.is_dir():
        evidence.extend(path for path in review_dir.rglob("*") if path.is_file())
    return sorted({path.relative_to(output_dir).as_posix() for path in evidence})


def _fingerprint_image_hashes(fingerprint: dict[str, Any]) -> dict[str, str]:
    protocol = fingerprint.get("protocol")
    manifest = protocol.get("manifest") if isinstance(protocol, dict) else None
    rows = manifest.get("cases") if isinstance(manifest, dict) else None
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("case")): str(row.get("sha256"))
        for row in rows
        if isinstance(row, dict) and row.get("case") and row.get("sha256")
    }


def _load_cases(manifest_path: Path) -> list[EvalCase]:
    spec = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases: list[EvalCase] = []
    for entry in spec["cases"]:
        modality = Modality(entry["modality"])
        cases.append(
            EvalCase(
                image_path=manifest_path.parent / entry["image"],
                modality=modality,
                # Blinded inference manifests deliberately omit every answer
                # field. Use a non-scorable placeholder until these persisted
                # results are rebuilt against the separate gold manifest.
                expected_severity=Severity(entry.get("expected_severity", "normal")),
                expected_keywords=tuple(entry.get("keywords", [])),
                expected_negatives=tuple(entry.get("negatives", [])),
                target_axes=tuple(entry.get("target_axes", [])),
                cant_miss=tuple(entry.get("cant_miss", [])),
                urgent_concerns=tuple(entry.get("urgent_concerns", [])),
                label_status=str(
                    entry.get("label_status")
                    or (
                        "asserted"
                        if "expected_severity" in entry
                        else "blinded_inference"
                    )
                ),
                uncertain_concepts=tuple(entry.get("uncertain_concepts", [])),
                ungradable_reasons=tuple(entry.get("ungradable_reasons", [])),
                label=entry.get("label", ""),
                valid_regions=_valid_regions_for(entry, modality),
                waveform_artifact_id=str(entry.get("waveform_artifact_id") or ""),
                waveform_lead_mode=str(entry.get("waveform_lead_mode") or ""),
            )
        )
    return cases


# ----------------------------------------------------------------------------
# Mock gateway -- emits a schema-valid payload derived from the case ground
# truth. Verifies the scoring pipeline end-to-end without a token.
# ----------------------------------------------------------------------------


def _mock_payload_for(case: EvalCase) -> dict[str, Any]:
    keywords = list(case.expected_keywords)
    # Fold the can't-miss labels into the synthesized read so the mock pipeline
    # self-test passes its own hard gate (mock mode proves the SCORING path,
    # not model skill -- a mock that drops the can't-miss would be a false fail).
    urgent_parts = [f"possible {label}" for label in case.urgent_concerns]
    detail_parts = (
        keywords + list(case.cant_miss) + urgent_parts + list(case.expected_negatives)
    )
    detail = ", ".join(detail_parts) if detail_parts else "no acute finding"
    findings = []
    if case.expected_severity in (Severity.WARNING, Severity.CRITICAL):
        finding = {
            "id": "f1",
            "label": detail_parts[0] if detail_parts else "finding",
            "detail": detail,
            "severity": case.expected_severity.value,
            "regions": [],
            "bboxes": [{"x": 0.55, "y": 0.6, "w": 0.2, "h": 0.15}],
        }
        if case.urgent_concerns:
            finding.update(
                {
                    "confidence": "low",
                    "question": "Can the urgent differential be confirmed?",
                }
            )
        findings.append(finding)
    checklist: dict[str, Any] = {}
    if case.modality is Modality.EKG:
        for key in _EKG_CHECKLIST_KEYS:
            checklist[key] = {"value": "normal", "status": "normal"}
        if case.expected_severity is Severity.CRITICAL and "STEMI" in case.cant_miss:
            checklist["st_segment"] = {"value": "ST elevation", "status": "critical"}
            checklist["stemi_pattern"] = {"value": "STEMI", "status": "critical"}
        elif (
            case.expected_severity is Severity.CRITICAL
            and "STEMI" in case.urgent_concerns
        ):
            checklist["st_segment"] = {"value": "ST elevation", "status": "critical"}
            checklist["stemi_pattern"] = {
                "value": "possible STEMI",
                "status": "critical",
            }
    elif case.modality is Modality.CXR:
        for key in _CXR_CHECKLIST_KEYS:
            checklist[key] = {"value": "normal", "status": "normal"}
        if case.expected_severity in (Severity.WARNING, Severity.CRITICAL):
            checklist["lungs"] = {"value": "consolidation", "status": "warning"}
    summary = f"{case.modality.value}: {detail}"
    payload = {
        "modality": case.modality.value,
        "summary": summary,
        "severity": case.expected_severity.value,
        "model_used": "mock-eval-gateway",
        "findings": findings,
        "checklist": checklist,
    }
    if case.modality is Modality.EKG:
        lead_names = [
            "lead_I",
            "lead_II",
            "lead_III",
            "lead_aVR",
            "lead_aVL",
            "lead_aVF",
            "lead_V1",
            "lead_V2",
            "lead_V3",
            "lead_V4",
            "lead_V5",
            "lead_V6",
        ]
        payload["layout"] = {
            "format": "12lead_12x1",
            "rhythm_strip_leads": [],
            "rhythm_strip_bbox": None,
            "leads": [
                {
                    "name": name,
                    "label_visible": True,
                    "bbox": [0.0, index / 12.0, 1.0, 1.0 / 12.0],
                }
                for index, name in enumerate(lead_names)
            ],
        }
    return payload


class _MockGateway:
    """In-process gateway answering connect + chat.send with queued payloads."""

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self._payloads = payloads
        self._index = 0
        self._server: Any = None
        self._current_payload: dict[str, Any] | None = None
        self.url = ""

    async def __aenter__(self) -> _MockGateway:
        # Match the client's raised frame limit so multi-MB real image
        # payloads are accepted instead of closing the socket (code 1009).
        self._server = await websockets.serve(
            self._handler, "127.0.0.1", 0, max_size=16 * 1024 * 1024
        )
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{port}"
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handler(self, ws: Any) -> None:
        connect_raw = await ws.recv()
        connect = json.loads(connect_raw)
        await ws.send(
            json.dumps(
                {
                    "type": "res",
                    "id": connect["id"],
                    "ok": True,
                    "payload": {"status": "connected"},
                }
            )
        )
        while True:
            try:
                chat_raw = await ws.recv()
            except websockets.ConnectionClosed:
                return
            chat = json.loads(chat_raw)
            run_id = str(uuid4())
            await ws.send(
                json.dumps(
                    {
                        "type": "res",
                        "id": chat["id"],
                        "ok": True,
                        "payload": {"status": "accepted", "runId": run_id},
                    }
                )
            )
            prompt = str(chat.get("params", {}).get("message", ""))
            if "verification turn" in prompt:
                if '"coarse_hypothesis": null' in prompt:
                    payload = {"deltas": []}
                else:
                    target_match = re.search(
                        r'"coarse_hypothesis":\s*\{.*?"id":\s*"([^"]+)"',
                        prompt,
                        re.DOTALL,
                    )
                    target_id = target_match.group(1) if target_match else "f1"
                    payload = {
                        "deltas": [
                            {
                                "action": "confirm",
                                "target_id": target_id,
                                "rationale": "Mock crop preserves the coarse finding.",
                            }
                        ]
                    }
            elif "final report-reconciliation turn" in prompt:
                payload = (
                    self._current_payload
                    or self._payloads[min(self._index, len(self._payloads) - 1)]
                )
            else:
                payload = self._payloads[min(self._index, len(self._payloads) - 1)]
                self._current_payload = payload
                self._index += 1
            await ws.send(
                json.dumps(
                    {
                        "type": "event",
                        "payload": {
                            "runId": run_id,
                            "state": "final",
                            "message": {
                                "content": [
                                    {"type": "text", "text": json.dumps(payload)}
                                ]
                            },
                        },
                    }
                )
            )


def _bbox_regions(value: object) -> list[RegionRect]:
    findings = getattr(value, "findings", None)
    if isinstance(findings, list):
        return [box for finding in findings for box in _bbox_regions(finding)]
    bboxes = getattr(value, "bboxes", None)
    if not isinstance(bboxes, list):
        return []
    return [box for box in bboxes if isinstance(box, RegionRect)]


class _CountingAnalyzer(VisionAnalyzerService):
    """Count model turns while preserving optional refinement/trace capabilities."""

    def __init__(
        self,
        inner: VisionAnalyzerService,
        *,
        synthetic_bbox_receipts: bool = False,
    ) -> None:
        self._inner = inner
        self.analyze_calls = 0
        self._synthetic_bbox_receipts = synthetic_bbox_receipts
        self._last_synthetic_receipts: list[dict[str, object]] = []

    async def analyze(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> Any:
        self.analyze_calls += 1
        result = await self._inner.analyze(image_base64, modality, valid_regions)
        self._set_synthetic_bbox_receipt(_bbox_regions(result))
        return result

    async def analyze_coarse(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> Any:
        coarse_method = getattr(self._inner, "analyze_coarse", None)
        if not callable(coarse_method):
            return await self.analyze(image_base64, modality, valid_regions)
        self.analyze_calls += 1
        result = await coarse_method(image_base64, modality, valid_regions)
        self._set_synthetic_bbox_receipt(_bbox_regions(result))
        return result

    async def refine(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        hypothesis: Any,
        crop_region: RegionRect,
        probe_id: str = "",
        crop_lead_regions: dict[str, RegionRect] | None = None,
    ) -> Any:
        refine_method = getattr(self._inner, "refine", None)
        if not callable(refine_method):
            raise NotImplementedError("inner analyzer does not support refine()")
        self.analyze_calls += 1
        refinement_context: dict[str, object] = {}
        if crop_lead_regions:
            refinement_context["crop_lead_regions"] = crop_lead_regions
        result = await refine_method(
            image_base64,
            modality,
            valid_regions,
            hypothesis=hypothesis,
            crop_region=crop_region,
            probe_id=probe_id,
            **refinement_context,
        )
        accepted_boxes = _bbox_regions(hypothesis)
        for delta in getattr(result, "deltas", ()):
            accepted_boxes.extend(_bbox_regions(getattr(delta, "finding", None)))
        self._set_synthetic_bbox_receipt(accepted_boxes)
        return result

    async def finalize(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
        *,
        draft: Any,
        refinement_trace: list[dict[str, object]],
    ) -> Any:
        finalize_method = getattr(self._inner, "finalize", None)
        if not callable(finalize_method):
            raise NotImplementedError("inner analyzer does not support finalize()")
        self.analyze_calls += 1
        result = await finalize_method(
            image_base64,
            modality,
            valid_regions,
            draft=draft,
            refinement_trace=refinement_trace,
        )
        self._set_synthetic_bbox_receipt(_bbox_regions(draft))
        return result

    def last_run_trace(self) -> dict[str, object]:
        trace_method = getattr(self._inner, "last_run_trace", None)
        if not callable(trace_method):
            return {}
        trace = trace_method()
        trace = dict(trace) if isinstance(trace, dict) else {}
        if self._last_synthetic_receipts:
            tools = trace.get("tools")
            tools = list(tools) if isinstance(tools, list) else []
            if "dicom_bbox_validate" not in tools:
                tools.append("dicom_bbox_validate")
            audit = trace.get("tool_audit")
            audit = list(audit) if isinstance(audit, list) else []
            trace["tools"] = tools
            trace["tool_audit"] = [*audit, *self._last_synthetic_receipts]
        return trace

    def _set_synthetic_bbox_receipt(self, boxes: list[RegionRect]) -> None:
        self._last_synthetic_receipts = []
        if not self._synthetic_bbox_receipts:
            return
        trace_method = getattr(self._inner, "last_run_trace", None)
        trace = trace_method() if callable(trace_method) else {}
        binding = trace.get("bbox_evidence") if isinstance(trace, dict) else None
        binding = binding if isinstance(binding, dict) else {}
        accepted_count = len(boxes)
        details = {
            "mode": "mock_protocol_selftest",
            "accepted_count": accepted_count,
            "rejected_count": 0,
        }
        self._last_synthetic_receipts = [
            {
                "schema_version": 2,
                "tool": "dicom_bbox_validate",
                "tool_call_id": f"mock-{uuid4()}",
                "accepted_count": accepted_count,
                "rejected_count": 0,
                "source_image_sha256": str(
                    binding.get("source_image_sha256") or "0" * 64
                ),
                "evidence_nonce": str(binding.get("evidence_nonce") or "0" * 32),
                "accepted_boxes_sha256": _bbox_coordinates_digest(boxes),
                "details_sha256": hashlib.sha256(
                    json.dumps(details, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                "source": "mock_protocol_selftest",
            }
        ]

    async def chat(self, message: str) -> str:
        return await self._inner.chat(message)

    async def connect(self) -> None:
        await self._inner.connect()

    async def disconnect(self) -> None:
        await self._inner.disconnect()

    def is_connected(self) -> bool:
        return self._inner.is_connected()


class _EvalImagePayload(NamedTuple):
    """Original ROI and bounded coarse-pass representations of one image."""

    source_image_base64: str
    coarse_image_base64: str
    source_size_px: tuple[int, int]
    coarse_size_px: tuple[int, int]


def _prepare_eval_image_payload(
    processor: ImageProcessor,
    source_image_bytes: bytes,
) -> _EvalImagePayload:
    source_size_px = processor.image_size(source_image_bytes)
    source_image_base64 = processor.to_base64(source_image_bytes)
    coarse_image_bytes = processor.downscale_to_max_edge(
        source_image_bytes,
        _MAX_IMAGE_EDGE_PX,
    )
    return _EvalImagePayload(
        source_image_base64=source_image_base64,
        coarse_image_base64=processor.to_base64(coarse_image_bytes),
        source_size_px=source_size_px,
        coarse_size_px=processor.image_size(coarse_image_bytes),
    )


def _wrap_with_app_hooks(
    inner: VisionAnalyzerService,
    *,
    include_bbox_calibration: bool = True,
) -> HookedVisionAnalyzer:
    registry = get_active_registry()
    clinical_engine = build_clinical_engine(_REPO_ROOT / "clinical_rules")
    hooks = [
        InputGuard(registry=registry),
        ClinicalConsistencyHook(engine=clinical_engine),
    ]
    if include_bbox_calibration:
        hooks.append(BboxCalibrationHook())
    hooks.append(OutputValidator(registry=registry))
    return HookedVisionAnalyzer(
        inner=inner,
        hooks=hooks,
    )


def _guardrail_hook_names(
    *, analysis_prompt_profile: str, multi_pass: bool
) -> list[str]:
    if analysis_prompt_profile == "minimal_control":
        return []
    return [
        "InputGuard",
        "ClinicalConsistencyHook",
        *([] if multi_pass else ["BboxCalibrationHook"]),
        "OutputValidator",
    ]


def _build_multi_pass_analyzer(
    inner: VisionAnalyzerService,
    *,
    cropper: Any,
    ekg_row_strip_detector: Any = None,
    max_zoom_targets: int,
    max_ekg_systematic_probes: int = DEFAULT_MAX_EKG_SYSTEMATIC_PROBES,
    initial_response_sla_sec: float = DEFAULT_INITIAL_RESPONSE_SLA_SEC,
    first_refinement_sla_sec: float = DEFAULT_FIRST_REFINEMENT_SLA_SEC,
    total_analysis_sla_sec: float = DEFAULT_TOTAL_ANALYSIS_SLA_SEC,
    synthetic_bbox_receipts: bool = False,
) -> tuple[MultiPassAnalyzer, _CountingAnalyzer]:
    counter = _CountingAnalyzer(
        inner,
        synthetic_bbox_receipts=synthetic_bbox_receipts,
    )
    interpreter = MultiPassInterpreter(
        analyzer=counter,
        cropper=cropper,
        bbox_calibrator=calibrate_ekg_bboxes,
        ekg_row_strip_detector=ekg_row_strip_detector,
        max_zoom_targets=max_zoom_targets,
        max_ekg_systematic_probes=max_ekg_systematic_probes,
        initial_response_sla_sec=initial_response_sla_sec,
        first_refinement_sla_sec=first_refinement_sla_sec,
        total_analysis_sla_sec=total_analysis_sla_sec,
    )
    return MultiPassAnalyzer(inner=counter, interpreter=interpreter), counter


async def _invoke_analyzer_with_source(
    analyzer: VisionAnalyzerService,
    *,
    coarse_image_base64: str,
    source_image_base64: str,
    modality: Modality,
    valid_regions: list[str],
    source_size_px: tuple[int, int],
    local_candidate_regions: list[RegionRect],
) -> Any:
    analyze_with_source_size = getattr(analyzer, "analyze_with_source_size", None)
    if callable(analyze_with_source_size):
        return await analyze_with_source_size(
            coarse_image_base64,
            modality,
            valid_regions,
            source_size_px=source_size_px,
            source_image_base64=source_image_base64,
            local_candidate_regions=local_candidate_regions,
        )
    return await analyzer.analyze(
        coarse_image_base64,
        modality,
        valid_regions,
    )


def _build_waveform_evidence(
    *,
    artifact_id: str,
    lead_mode: str,
    evidence_nonce: str,
    receipts: list[dict[str, object]],
    duplicate_attempts: list[dict[str, object]] | None = None,
    expected_preprocessing_revision: str = "",
) -> dict[str, object]:
    artifact_digest = (
        hashlib.sha256(artifact_id.encode("utf-8")).hexdigest() if artifact_id else ""
    )
    evidence: dict[str, object] = {
        "requested": bool(artifact_id),
        "verified_exactly_once": bool(artifact_id and len(receipts) == 1),
        "evidence_status": (
            str(receipts[0].get("status") or "") if len(receipts) == 1 else ""
        ),
        "usable": bool(len(receipts) == 1 and receipts[0].get("status") == "ok"),
        "ineligible_reason": (
            str(receipts[0].get("failure_reason") or "")
            if len(receipts) == 1 and receipts[0].get("status") == "ineligible"
            else ""
        ),
        "artifact_id_sha256": artifact_digest,
        "lead_mode": (lead_mode or "12_lead") if artifact_id else "",
        "evidence_nonce": evidence_nonce if artifact_id else "",
        "receipt_count": len(receipts),
        "receipts": receipts,
        "duplicate_suppressed_count": len(duplicate_attempts or []),
        "duplicate_attempts": list(duplicate_attempts or []),
    }
    evidence["verified_exactly_once"] = _valid_ecg_founder_evidence(
        evidence,
        expected_artifact_sha256=artifact_digest,
        expected_preprocessing_revision=expected_preprocessing_revision,
    )
    return evidence


def _probe_ecg_founder_deep_health(
    environment: Mapping[str, str],
    *,
    opener: Any | None = None,
) -> tuple[dict[str, object] | None, str]:
    endpoint = environment.get("DICOM_ECGFOUNDER_ENDPOINT", "").strip()
    token = environment.get("DICOM_ECGFOUNDER_TOKEN", "").strip()
    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        return None, "invalid_endpoint"
    if parsed.scheme != "http" or (parsed.hostname or "").casefold() not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        return None, "endpoint_not_loopback_http"
    if parsed.username or parsed.password or not token:
        return None, "invalid_auth_configuration"
    health_url = urlunsplit((parsed.scheme, parsed.netloc, "/health", "deep=1", ""))
    request = urllib.request.Request(
        health_url,
        method="GET",
        headers={"authorization": f"Bearer {token}", "accept": "application/json"},
    )
    try:
        timeout_ms = int(environment.get("DICOM_ECGFOUNDER_TIMEOUT_MS", "45000"))
    except ValueError:
        timeout_ms = 45_000
    timeout_sec = max(1.0, min(120.0, timeout_ms / 1000))
    open_request = opener or urllib.request.urlopen
    try:
        with open_request(request, timeout=timeout_sec) as response:
            body = response.read(65_537)
    except urllib.error.HTTPError as exc:
        return None, f"health_http_{exc.code}"
    except (OSError, urllib.error.URLError):
        return None, "health_unreachable"
    if len(body) > 65_536:
        return None, "health_response_too_large"
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "health_response_invalid_json"
    if not isinstance(payload, dict) or payload.get("status") != "ready":
        return None, "sidecar_not_ready"
    if (
        payload.get("deep") is not True
        or payload.get("model_id") != _ECG_FOUNDER_MODEL_ID
        or payload.get("model_revision") != _ECG_FOUNDER_MODEL_REVISION
        or payload.get("checkpoint_sha256") != _ECG_FOUNDER_CHECKPOINT_SHA256
        or not isinstance(payload.get("preprocessing_revision"), str)
        or not payload["preprocessing_revision"]
        or not isinstance(payload.get("artifact_count"), int)
        or payload["artifact_count"] <= 0
    ):
        return None, "health_provenance_mismatch"
    return {
        "model_id": payload["model_id"],
        "model_revision": payload["model_revision"],
        "checkpoint_sha256": payload["checkpoint_sha256"],
        "preprocessing_revision": payload["preprocessing_revision"],
        "artifact_count": payload["artifact_count"],
    }, "ready"


def _rhythm_trace_has_activity(
    rhythm_region: RegionRect | None,
    *,
    analyze_calls: int,
    crop_calls: int,
) -> bool:
    return rhythm_region is not None or analyze_calls > 0 or crop_calls > 0


async def _run(
    cases: list[EvalCase],
    gateway_url: str,
    mode: str,
    output_dir: Path,
    timeout_sec: int,
    *,
    multi_pass: bool,
    multi_pass_max_targets: int,
    multi_pass_max_ekg_systematic_probes: int,
    initial_response_sla_sec: float,
    first_refinement_sla_sec: float,
    total_analysis_sla_sec: float,
    analysis_prompt_profile: str,
    openclaw_fast_mode: bool,
    partial_scorecard_interval: int,
    rhythm_strip_pass: bool = True,
    ecg_founder_waveform_evidence: bool = False,
    ecg_founder_preprocessing_revision: str = "",
    protocol_digest: str = "",
    source_image_hashes: dict[str, str] | None = None,
) -> EvalReport:
    processor = ImageProcessor()
    image_hashes = source_image_hashes or {}

    async def analyze_with_client(client: OpenClawClient) -> EvalReport:
        hooked_analyzer: HookedVisionAnalyzer | None = None
        if analysis_prompt_profile == "minimal_control":
            analyzer: VisionAnalyzerService = client
        else:
            hooked_analyzer = _wrap_with_app_hooks(client)
            analyzer = hooked_analyzer
        counter: _CountingAnalyzer | None = None
        crop_calls = 0
        trace_path = output_dir / "multipass-trace.jsonl"
        local_quality_by_case: dict[str, dict[str, object]] = {}
        local_signal_by_case: dict[str, dict[str, object]] = {}
        waveform_evidence_by_case: dict[str, dict[str, object]] = {}

        if multi_pass:

            def cropper(image_base64: str, region: Any) -> str:
                nonlocal crop_calls
                crop_calls += 1
                return processor.crop_region_base64(image_base64, region)

            multi_pass_analyzer, counter = _build_multi_pass_analyzer(
                client,
                cropper=cropper,
                ekg_row_strip_detector=processor.ekg_row_strip_evidence,
                max_zoom_targets=multi_pass_max_targets,
                max_ekg_systematic_probes=(multi_pass_max_ekg_systematic_probes),
                initial_response_sla_sec=initial_response_sla_sec,
                first_refinement_sla_sec=first_refinement_sla_sec,
                total_analysis_sla_sec=total_analysis_sla_sec,
                synthetic_bbox_receipts=mode == "mock",
            )
            analyzer = _wrap_with_app_hooks(
                multi_pass_analyzer,
                include_bbox_calibration=False,
            )

        if not analyzer.is_connected():
            await analyzer.connect()

        async def analyze(case: EvalCase) -> Any:
            nonlocal crop_calls
            case_key = case.label or case.image_path.name
            source_image_bytes = case.image_path.read_bytes()
            image_payload = _prepare_eval_image_payload(
                processor,
                source_image_bytes,
            )
            local_quality_by_case[case_key] = processor.image_quality_profile(
                source_image_bytes
            )
            local_signal = (
                processor.local_signal_candidates(source_image_bytes)
                if analysis_prompt_profile == "clinical"
                else {}
            )
            local_signal_by_case[case_key] = local_signal
            local_candidate_regions = _local_candidate_regions_from_signal(
                local_signal,
                max_regions=multi_pass_max_targets,
            )
            before_calls = counter.analyze_calls if counter else 0
            before_crops = crop_calls
            coarse_invocations = 0
            artifact_id = (
                case.waveform_artifact_id if ecg_founder_waveform_evidence else ""
            )
            waveform_receipts: list[dict[str, object]] = []

            waveform_evidence_by_case[case_key] = {
                "requested": bool(artifact_id),
                "verified_exactly_once": False,
                "artifact_id_sha256": (
                    hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()
                    if artifact_id
                    else ""
                ),
                "lead_mode": (case.waveform_lead_mode or "12_lead")
                if artifact_id
                else "",
                "evidence_nonce": "",
                "receipt_count": 0,
                "receipts": [],
            }

            async def _invoke() -> Any:
                nonlocal coarse_invocations
                coarse_invocations += 1
                return await _invoke_analyzer_with_source(
                    analyzer,
                    coarse_image_base64=image_payload.coarse_image_base64,
                    source_image_base64=image_payload.source_image_base64,
                    modality=case.modality,
                    valid_regions=list(case.valid_regions),
                    source_size_px=image_payload.source_size_px,
                    local_candidate_regions=local_candidate_regions,
                )

            evidence_context = (
                client.use_waveform_artifact(
                    artifact_id,
                    lead_mode=case.waveform_lead_mode or "12_lead",
                )
                if artifact_id
                else nullcontext("")
            )
            result = None
            evidence_nonce = ""
            try:
                with evidence_context as bound_nonce:
                    evidence_nonce = str(bound_nonce or "")
                    result = await _invoke()
                # Retry an empty image read without re-binding waveform evidence;
                # an ECGFounder arm must prove exactly one tool call per case.
                if is_empty_read(result) and not multi_pass:
                    logger.warning("empty_read_retry", case=case_key)
                    retry = await _invoke()
                    if not is_empty_read(retry):
                        result = retry
            except Exception:
                waveform_receipts = client.waveform_evidence_receipts(evidence_nonce)
                duplicate_attempts = client.waveform_duplicate_attempts(
                    evidence_nonce
                )
                waveform_evidence_by_case[case_key] = _build_waveform_evidence(
                    artifact_id=artifact_id,
                    lead_mode=case.waveform_lead_mode,
                    evidence_nonce=evidence_nonce,
                    receipts=waveform_receipts,
                    duplicate_attempts=duplicate_attempts,
                    expected_preprocessing_revision=(
                        ecg_founder_preprocessing_revision
                    ),
                )
                raise
            finally:
                if multi_pass and counter:
                    calls = counter.analyze_calls - before_calls
                    crops = crop_calls - before_crops
                    result_trace = (
                        result.analysis_trace
                        if result is not None
                        and isinstance(result.analysis_trace, list)
                        else []
                    )
                    systematic_targets = [
                        str(probe.get("target_id"))
                        for event in result_trace
                        if isinstance(event, dict)
                        and event.get("stage") == "systematic_assist"
                        and isinstance(event.get("probes"), list)
                        for probe in event["probes"]
                        if isinstance(probe, dict) and probe.get("target_id")
                    ]
                    systematic_completed = [
                        str(event.get("target_id"))
                        for event in result_trace
                        if isinstance(event, dict)
                        and event.get("stage") == "refine"
                        and event.get("status") == "completed"
                        and str(event.get("target_id", "")).startswith(
                            "ekg_systematic_"
                        )
                    ]
                    sla_event = next(
                        (
                            event
                            for event in reversed(result_trace)
                            if isinstance(event, dict)
                            and event.get("stage") == "analysis_sla"
                        ),
                        {},
                    )
                    trace = {
                        "case": case.label or case.image_path.name,
                        "image": case.image_path.name,
                        "modality": case.modality.value,
                        "model_path": "MultiPassAnalyzer",
                        "openclaw_analyze_calls": calls,
                        "coarse_passes": coarse_invocations,
                        "zoom_passes": max(0, calls - coarse_invocations),
                        "crop_calls": crops,
                        "crop_source": "original_roi",
                        "source_size_px": list(image_payload.source_size_px),
                        "coarse_size_px": list(image_payload.coarse_size_px),
                        "max_zoom_targets": multi_pass_max_targets,
                        "max_ekg_systematic_probes": (
                            multi_pass_max_ekg_systematic_probes
                        ),
                        "openclaw_fast_mode_requested": openclaw_fast_mode,
                        "ekg_systematic_probe_count": len(systematic_targets),
                        "ekg_systematic_completed_count": len(systematic_completed),
                        "ekg_systematic_probe_targets": systematic_targets,
                        "ekg_systematic_completed_targets": systematic_completed,
                        "local_candidate_count": len(local_candidate_regions),
                        "local_candidate_regions": [
                            {
                                "x": region.x,
                                "y": region.y,
                                "w": region.w,
                                "h": region.h,
                            }
                            for region in local_candidate_regions
                        ],
                        "sla": sla_event,
                    }
                    with trace_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(trace, ensure_ascii=False) + "\n")

            try:
                if rhythm_strip_pass and case.modality == Modality.EKG:
                    # Re-read the model-declared rhythm strip at higher resolution
                    # to recover rhythm / P-wave / AV-block misses. It is a no-op
                    # unless Step 0 localized a rhythm-strip bbox, so it stays
                    # layout-general. Keep this pass separately traceable even
                    # when the broader --multi-pass option is disabled.
                    rhythm_region = resolve_rhythm_strip_region(result)
                    assert hooked_analyzer is not None
                    rhythm_counter = _CountingAnalyzer(hooked_analyzer)
                    rhythm_crop_calls = 0

                    def rhythm_cropper(image_base64: str, region: Any) -> str:
                        nonlocal rhythm_crop_calls
                        rhythm_crop_calls += 1
                        return processor.crop_region_base64(image_base64, region)

                    result = await refine_rhythm_strip(
                        result,
                        image_payload.source_image_base64,
                        analyze_fn=rhythm_counter.analyze,
                        cropper=rhythm_cropper,
                        valid_regions=list(case.valid_regions),
                    )
                    rhythm_sla = next(
                        (
                            event
                            for event in reversed(result.analysis_trace)
                            if isinstance(event, dict)
                            and event.get("stage") == "analysis_sla"
                        ),
                        {},
                    )
                    rhythm_trace = {
                        "case": case.label or case.image_path.name,
                        "image": case.image_path.name,
                        "model_path": "RhythmStripRefinement",
                        "openclaw_analyze_calls": rhythm_counter.analyze_calls,
                        "coarse_passes": 0,
                        "zoom_passes": 1 if rhythm_counter.analyze_calls else 0,
                        "crop_calls": rhythm_crop_calls,
                        "crop_source": "original_roi",
                        "source_size_px": list(image_payload.source_size_px),
                        "coarse_size_px": list(image_payload.coarse_size_px),
                        "max_zoom_targets": 1,
                        "retry_attempts": 1,
                        "sla": rhythm_sla,
                        "rhythm_strip_region": (
                            {
                                "x": rhythm_region.x,
                                "y": rhythm_region.y,
                                "w": rhythm_region.w,
                                "h": rhythm_region.h,
                            }
                            if rhythm_region is not None
                            else None
                        ),
                        "local_candidate_count": len(local_candidate_regions),
                        "local_candidate_regions": [
                            {
                                "x": region.x,
                                "y": region.y,
                                "w": region.w,
                                "h": region.h,
                            }
                            for region in local_candidate_regions
                        ],
                    }
                    if _rhythm_trace_has_activity(
                        rhythm_region,
                        analyze_calls=rhythm_counter.analyze_calls,
                        crop_calls=rhythm_crop_calls,
                    ):
                        with trace_path.open("a", encoding="utf-8") as fh:
                            fh.write(
                                json.dumps(rhythm_trace, ensure_ascii=False) + "\n"
                            )
            finally:
                waveform_receipts = client.waveform_evidence_receipts(evidence_nonce)
                duplicate_attempts = client.waveform_duplicate_attempts(
                    evidence_nonce
                )
                waveform_evidence_by_case[case_key] = _build_waveform_evidence(
                    artifact_id=artifact_id,
                    lead_mode=case.waveform_lead_mode,
                    evidence_nonce=evidence_nonce,
                    receipts=waveform_receipts,
                    duplicate_attempts=duplicate_attempts,
                    expected_preprocessing_revision=(
                        ecg_founder_preprocessing_revision
                    ),
                )
            if (
                artifact_id
                and not waveform_evidence_by_case[case_key]["verified_exactly_once"]
            ):
                raise RuntimeError(
                    "ECGFounder evidence arm requires exactly one valid bound "
                    "ok/ineligible receipt"
                )
            return result

        return await run_evaluation(
            cases,
            analyze,
            output_dir=output_dir,
            gateway_mode=mode,
            partial_scorecard_interval=partial_scorecard_interval,
            case_metadata=lambda case: {
                "local_image_quality": local_quality_by_case.get(
                    case.label or case.image_path.name,
                    {},
                ),
                "local_signal_candidates": local_signal_by_case.get(
                    case.label or case.image_path.name,
                    {},
                ),
                "protocol_digest": protocol_digest,
                "source_image_sha256": image_hashes.get(
                    case.label or case.image_path.name,
                    "",
                ),
                "waveform_evidence": waveform_evidence_by_case.get(
                    case.label or case.image_path.name,
                    {"requested": False, "verified_exactly_once": False},
                ),
                "openclaw_request_policy": {
                    "fast_mode_requested": openclaw_fast_mode,
                    "priority_service_observed": None,
                    "service_tier_evidence": "requires_gateway_transport_receipt",
                },
            },
        )

    if mode == "mock":
        payloads = [_mock_payload_for(c) for c in cases]
        async with _MockGateway(payloads) as gw:
            client = _make_client(
                gw.url,
                timeout_sec=timeout_sec,
                analysis_prompt_profile=analysis_prompt_profile,
                require_bound_bbox_receipts=False,
                fast_mode=openclaw_fast_mode,
            )
            try:
                return await analyze_with_client(client)
            finally:
                await client.disconnect()

    client = _make_client(
        gateway_url,
        timeout_sec=timeout_sec,
        analysis_prompt_profile=analysis_prompt_profile,
        fast_mode=openclaw_fast_mode,
    )
    try:
        return await analyze_with_client(client)
    finally:
        await client.disconnect()


def _make_client(
    gateway_url: str,
    *,
    timeout_sec: int,
    analysis_prompt_profile: str = "clinical",
    require_bound_bbox_receipts: bool = True,
    fast_mode: bool = True,
) -> OpenClawClient:
    return OpenClawClient(
        gateway_url=gateway_url,
        timeout_sec=timeout_sec,
        connect_timeout_sec=timeout_sec,
        inference_timeout_sec=timeout_sec,
        registry=get_active_registry(),
        base_dir=_REPO_ROOT,
        analysis_prompt_profile=analysis_prompt_profile,
        require_bound_bbox_receipts=require_bound_bbox_receipts,
        fast_mode=fast_mode,
    )


def _limited_cases(cases: list[Any], limit: int) -> tuple[list[Any], int]:
    """Return the console preview slice and remaining count.

    ``limit <= 0`` means print all cases. Full per-case evidence is always
    written to ``scorecard.json`` and ``results/*.json``.
    """
    if limit <= 0 or len(cases) <= limit:
        return cases, 0
    return cases[:limit], len(cases) - limit


def _pending_cases(
    cases: list[EvalCase],
    output_dir: Path,
    *,
    retry_errors: bool = False,
) -> tuple[list[EvalCase], int]:
    """Return cases without a persisted raw-result artifact.

    Resume deliberately keys off the same sanitized case label used by
    ``eval_harness._write_raw_result``. Existing artifacts are left untouched;
    the normal post-processing step rebuilds the aggregate scorecard from the
    union of old and newly completed results.
    """
    results_dir = output_dir / "results"
    result_paths = {
        path.name: path for path in results_dir.glob("*.json") if path.is_file()
    }
    retry_result_filenames = (
        {
            name
            for name, path in result_paths.items()
            if _persisted_result_has_error(path)
        }
        if retry_errors
        else set()
    )
    return _partition_resume_cases(
        cases,
        completed_result_filenames=set(result_paths),
        retry_result_filenames=retry_result_filenames,
    )


def _partition_resume_cases(
    cases: list[EvalCase],
    *,
    completed_result_filenames: set[str],
    retry_result_filenames: set[str] | None = None,
) -> tuple[list[EvalCase], int]:
    """Partition a frozen case sequence using already-validated result names.

    Keeping the set partition pure makes the 10k+ identity invariant cheap to
    verify.  ``_pending_cases`` remains the filesystem boundary and delegates
    here only after protocol/result validation has run.
    """

    retry_names = retry_result_filenames or set()
    pending: list[EvalCase] = []
    skipped = 0
    for case in cases:
        label = case.label or case.image_path.name
        result_filename = _result_filename(label)
        if result_filename not in completed_result_filenames:
            pending.append(case)
            continue
        if result_filename in retry_names:
            pending.append(case)
            continue
        skipped += 1
    return pending, skipped


def _persisted_result_has_error(path: Path) -> bool:
    """Return whether a validated resume artifact records an eval error."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(raw, dict):
        return False
    score = raw.get("score")
    return bool(raw.get("error") or (isinstance(score, dict) and score.get("error")))


def _result_filename(label: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)
    return f"{safe}.json"


def _validate_resume_results(
    cases: list[EvalCase],
    output_dir: Path,
    *,
    protocol_digest: str,
    require_protocol_metadata: bool,
) -> None:
    expected = {
        _result_filename(case.label or case.image_path.name): case for case in cases
    }
    expected_hashes: dict[str, str] = {}
    fingerprint_path = output_dir / _PROTOCOL_FINGERPRINT_NAME
    if fingerprint_path.is_file():
        expected_hashes = _fingerprint_image_hashes(
            _read_protocol_fingerprint(fingerprint_path)
        )

    seen_cases: set[str] = set()
    for path in sorted((output_dir / "results").glob("*.json")):
        case = expected.get(path.name)
        if case is None:
            raise ProtocolFingerprintError(
                f"resume result does not belong to selected manifest cases: {path.name}"
            )
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProtocolFingerprintError(
                f"resume result is not valid JSON: {path.name}: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise ProtocolFingerprintError(
                f"resume result must be a JSON object: {path.name}"
            )
        expected_label = case.label or case.image_path.name
        actual_label = raw.get("case")
        if actual_label != expected_label:
            raise ProtocolFingerprintError(
                f"resume result case mismatch in {path.name}: "
                f"{actual_label!r} != {expected_label!r}"
            )
        if expected_label in seen_cases:
            raise ProtocolFingerprintError(
                f"duplicate resume result case: {expected_label}"
            )
        seen_cases.add(expected_label)

        score = raw.get("score")
        score = score if isinstance(score, dict) else {}
        score_label = score.get("case_label")
        if score_label not in (None, "", expected_label):
            raise ProtocolFingerprintError(
                f"resume score case mismatch in {path.name}: {score_label!r}"
            )
        image_value = raw.get("image") or score.get("image")
        expected_image = case.image_path.name
        if not isinstance(image_value, str) or Path(image_value).name != expected_image:
            raise ProtocolFingerprintError(
                f"resume result image mismatch in {path.name}: "
                f"{image_value!r} != {expected_image!r}"
            )
        modality = raw.get("modality")
        if modality not in (None, "", case.modality.value):
            raise ProtocolFingerprintError(
                f"resume result modality mismatch in {path.name}: {modality!r}"
            )

        is_error = bool(raw.get("error") or score.get("error"))
        result_protocol = raw.get("protocol_digest")
        if result_protocol not in (None, "", protocol_digest):
            raise ProtocolFingerprintError(
                f"resume result protocol mismatch in {path.name}: {result_protocol!r}"
            )
        if require_protocol_metadata and not is_error:
            if result_protocol != protocol_digest:
                raise ProtocolFingerprintError(
                    f"resume result lacks matching protocol_digest: {path.name}"
                )
            expected_hash = expected_hashes.get(expected_label, "")
            if not expected_hash or raw.get("source_image_sha256") != expected_hash:
                raise ProtocolFingerprintError(
                    f"resume result lacks matching source_image_sha256: {path.name}"
                )


def _configure_eval_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(level))


def _rebuild_canonical_scorecard(
    *,
    output_dir: Path,
    manifest_path: Path,
    gateway_mode: str,
) -> tuple[int, str]:
    command = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "rebuild-eval-scorecard.py"),
        "--eval-dir",
        str(output_dir),
        "--manifest",
        str(manifest_path),
        "--output",
        str(output_dir / "scorecard.rebuilt.json"),
        "--gateway-mode",
        gateway_mode,
        "--promote-canonical",
        "--require-protocol-fingerprint",
    ]
    completed = subprocess.run(
        command,
        cwd=_REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        check=False,
    )
    return int(completed.returncode), completed.stdout


def _print_summary(
    report: EvalReport,
    output_dir: Path,
    *,
    case_print_limit: int = 50,
) -> None:
    print("\n" + "=" * 60)
    print(f"  RECOGNITION SCORECARD  (mode={report.gateway_mode})")
    print("=" * 60)
    print(
        f"  cases scored ........ {report.scored}/{report.total} "
        f"(errors={report.error_count})"
    )
    print(
        f"  formal references ... {report.clinical_scorable_count}/{report.total} "
        "(complete asserted labels only)"
    )
    print(
        f"  weak references ..... {report.weak_label_case_count}/{report.total} "
        "(exploratory positive-label recall only)"
    )
    print(
        f"  severity accuracy ... {report.severity_accuracy:.0%} (exact, "
        f"n={report.severity_scorable_count})"
    )
    print(
        f"  abnormal accuracy ... {report.severity_abnormal_accuracy:.0%} "
        f"(normal vs abnormal)"
    )
    print(f"  strict pass rate .... {report.strict_pass_rate:.0%}")
    print(f"  partial credit ...... {report.mean_partial_credit:.0%} (mean)")
    print(
        f"  known-label recall .. {report.mean_keyword_recall:.0%} "
        f"(n={report.keyword_scorable_count})"
    )
    if report.weak_label_keyword_scorable_count:
        print(
            f"  weak-label recall ... {report.mean_weak_label_keyword_recall:.0%} "
            f"(n={report.weak_label_keyword_scorable_count}, exploratory)"
        )
    print(
        f"  diagnosis exact set . {report.diagnosis_exact_set_accuracy:.0%} "
        f"(n={report.diagnosis_scorable_count})"
    )
    print(
        f"  diagnosis complete .. {report.diagnosis_complete_recall_rate:.0%} "
        f"(all referenced diagnoses found)"
    )
    print(
        f"  single-dx exact ..... {report.single_diagnosis_exact_set_accuracy:.0%} "
        f"(n={report.single_diagnosis_scorable_count})"
    )
    print(
        "  3-5 dx exact/recall . "
        f"{report.multi_diagnosis_3_to_5_exact_set_accuracy:.0%}/"
        f"{report.multi_diagnosis_3_to_5_complete_recall_rate:.0%} "
        f"(n={report.multi_diagnosis_3_to_5_scorable_count})"
    )
    print(
        f"  normal specificity .. {report.normal_control_specificity:.0%} "
        f"(n={report.normal_control_count})"
    )
    print(
        f"  normal clean read ... {report.normal_control_clean_read_rate:.0%} "
        f"(review burden {report.normal_control_review_burden_rate:.0%})"
    )
    print(
        f"  negative recall ..... {report.mean_negative_recall:.0%} "
        f"(n={report.negative_scorable_count})"
    )
    print(f"  schema pass rate .... {report.schema_pass_rate:.0%}")
    print(f"  bbox in-bounds ...... {report.bbox_in_bounds_rate:.0%}")
    print(f"  mean latency ........ {report.mean_latency_ms:.0f} ms")
    print("-" * 60)
    printable_cases, remaining_cases = _limited_cases(
        report.cases,
        limit=case_print_limit,
    )
    for case in printable_cases:
        flag = (
            "N/A"
            if not case.clinical_scorable
            else ("OK " if case.strict_pass else "MISS")
        )
        if case.error:
            flag = "ERR"
        print(
            f"  [{flag}] {case.case_label:<24} "
            f"exp={case.expected_severity:<8} got={case.actual_severity:<8} "
            f"partial={case.partial_credit:.0%} "
            f"recall={case.keyword_recall:.0%}"
        )
    if remaining_cases:
        print(
            f"      ... {remaining_cases} more case rows in scorecard.json "
            f"(use --case-print-limit 0 to print all)"
        )
    # Framework coverage matrix (Task B): which checklist axes were exercised
    # by at least one normal AND one abnormal case.
    if report.axis_coverage:
        print("-" * 60)
        print("  FRAMEWORK COVERAGE  (checklist axes exercised by the dataset)")
        for mod_key, cov in sorted(report.axis_coverage.items()):
            print(
                f"    {mod_key}: {cov['covered_axes']}/{cov['total_axes']} axes "
                f"touched ({cov['coverage_rate']:.0%}), "
                f"{cov['fully_covered_axes']} fully covered "
                f"(normal+abnormal, {cov['full_coverage_rate']:.0%})"
            )
            if cov["missing_axes"]:
                print(f"      untested axes: {', '.join(cov['missing_axes'])}")
    if report.target_axis_performance:
        print("-" * 60)
        print("  TARGET AXIS PERFORMANCE  (paired to manifest target_axes)")
        for axis, perf in sorted(report.target_axis_performance.items()):
            print(
                f"    {axis}: n={perf['case_count']} "
                f"strict={perf['strict_pass_rate']:.0%} "
                f"partial={perf['mean_partial_credit']:.0%} "
                f"keyword={perf['mean_keyword_recall']:.0%}"
            )
    # Can't-miss hard gate (Task C).
    print("-" * 60)
    if report.cant_miss_total == 0:
        print("  CAN'T-MISS GATE ..... (no can't-miss cases in dataset)")
    elif report.cant_miss_passed:
        print(
            f"  CAN'T-MISS GATE ..... PASS "
            f"({report.cant_miss_caught_count}/{report.cant_miss_total} caught)"
        )
    else:
        print(
            f"  CAN'T-MISS GATE ..... FAIL "
            f"({report.cant_miss_caught_count}/{report.cant_miss_total} caught)"
        )
        for miss in report.cant_miss_missed:
            print(f"      MISSED: {miss}")
    if report.urgent_concern_total == 0:
        print("  URGENT-CONCERN GATE . (no uncertain urgent cases in dataset)")
    elif report.urgent_concern_passed:
        print(
            f"  URGENT-CONCERN GATE . PASS "
            f"({report.urgent_concern_caught_count}/"
            f"{report.urgent_concern_total} safely surfaced)"
        )
    else:
        print(
            f"  URGENT-CONCERN GATE . FAIL "
            f"({report.urgent_concern_caught_count}/"
            f"{report.urgent_concern_total} safely surfaced)"
        )
        for miss in report.urgent_concern_missed:
            print(f"      MISSED: {miss}")
    strict_failures = report.perfect_failures()
    if strict_failures:
        print("-" * 60)
        print(f"  PERFECT GATE ........ FAIL ({len(strict_failures)} issue(s))")
        for failure in strict_failures[:20]:
            print(f"      {failure}")
        if len(strict_failures) > 20:
            print(f"      ... {len(strict_failures) - 20} more")
    else:
        print("-" * 60)
        print("  PERFECT GATE ........ PASS")
    print("=" * 60)
    print(f"  artifacts: {output_dir}")
    if report.gateway_mode == "mock":
        print(
            "  NOTE: mock mode verifies the SCORING PIPELINE only, not model "
            "accuracy.\n        Provide a token + real gateway for a real "
            "benchmark."
        )
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run recognition evaluation")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument(
        "--dataset",
        default="",
        help="Dataset directory under data/eval-datasets, e.g. 'meeti'.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Evaluate only the first N cases (0 = all).",
    )
    parser.add_argument(
        "--gateway", default="ws://127.0.0.1:18789", help="Real OpenClaw Gateway URL"
    )
    parser.add_argument(
        "--model-id",
        default="",
        help=(
            "Exact provider/model id used by the Gateway. It is recorded in the "
            "immutable protocol fingerprint."
        ),
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use in-process mock gateway (no token needed)",
    )
    parser.add_argument(
        "--require-perfect",
        action="store_true",
        help="Fail non-zero unless every case has perfect severity/recall/schema/bbox.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=_DEFAULT_TIMEOUT_SEC,
        help="Per-request Gateway/LLM timeout in seconds.",
    )
    parser.add_argument(
        "--multi-pass",
        action="store_true",
        help="Use app MultiPassAnalyzer: coarse read, crop abnormal bboxes, refine.",
    )
    parser.add_argument(
        "--analysis-prompt-profile",
        choices=("clinical", "minimal_control"),
        default="clinical",
        help=(
            "clinical uses the app skill/prompt harness; minimal_control keeps "
            "only a single-look JSON envelope for the no-harness control arm."
        ),
    )
    parser.add_argument(
        "--openclaw-thinking-level",
        choices=("unspecified", "off", "minimal", "low", "medium", "high"),
        default="unspecified",
        help=(
            "Effective OpenClaw embedded-agent thinking default, recorded as a "
            "shared protocol invariant."
        ),
    )
    parser.add_argument(
        "--multi-pass-max-targets",
        type=int,
        default=2,
        help="Maximum abnormal findings to crop/refine per image in --multi-pass mode.",
    )
    parser.add_argument(
        "--multi-pass-max-ekg-systematic-probes",
        type=int,
        default=DEFAULT_MAX_EKG_SYSTEMATIC_PROBES,
        help=(
            "Maximum layout-derived EKG discovery probes within the total "
            "--multi-pass-max-targets budget."
        ),
    )
    parser.add_argument(
        "--fast-mode",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Request OpenClaw fast mode on every chat.send turn. Enabled by "
            "default for the 60/100/180-second SLA; may use priority capacity."
        ),
    )
    parser.add_argument(
        "--initial-response-sla-sec",
        type=float,
        default=DEFAULT_INITIAL_RESPONSE_SLA_SEC,
        help="Absolute deadline for the initial whole-image read (default: 60).",
    )
    parser.add_argument(
        "--first-refinement-sla-sec",
        type=float,
        default=DEFAULT_FIRST_REFINEMENT_SLA_SEC,
        help="Absolute deadline for the first crop detail read (default: 100).",
    )
    parser.add_argument(
        "--total-analysis-sla-sec",
        type=float,
        default=DEFAULT_TOTAL_ANALYSIS_SLA_SEC,
        help="Absolute deadline for the complete question (default: 180).",
    )
    parser.add_argument(
        "--rhythm-strip-pass",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "For EKG, re-read the model-declared rhythm strip at higher "
            "resolution to recover rhythm/P-wave/AV-block misses (one bounded "
            "extra call; no-op unless Step 0 localized a rhythm-strip bbox). "
            "Defaults to enabled only with --multi-pass."
        ),
    )
    parser.add_argument(
        "--ecgfounder-waveform-evidence",
        action="store_true",
        help=(
            "Enable the paired ECGFounder waveform-evidence arm. Requires a "
            "configured sidecar and a waveform artifact id for every case."
        ),
    )
    parser.add_argument(
        "--case-print-limit",
        type=int,
        default=50,
        help="Max per-case rows to print to console (0 = print all).",
    )
    parser.add_argument(
        "--partial-scorecard-interval",
        type=int,
        default=50,
        help=("Refresh scorecard.partial.json every N cases (0 = final/abort only)."),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume only after the protocol fingerprint and every existing "
            "result identity validate."
        ),
    )
    parser.add_argument(
        "--defer-scoring",
        action="store_true",
        help=(
            "Persist blinded inference results without rebuilding against this "
            "manifest; an external runner must score later with the gold manifest."
        ),
    )
    parser.add_argument(
        "--resume-retry-errors",
        action="store_true",
        help=(
            "With --resume, retry persisted cases whose raw result records an "
            "error; successful artifacts remain untouched."
        ),
    )
    parser.add_argument(
        "--resume-legacy-policy",
        choices=("reject", "mark"),
        default="reject",
        help=(
            "Policy for legacy result directories without a fingerprint. "
            "'reject' fails closed; 'mark' permits continuation but permanently "
            "marks the run mixed and non-comparable."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable per-request structlog debug/info logs.",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if args.rhythm_strip_pass is None:
        args.rhythm_strip_pass = bool(args.multi_pass)
    if args.analysis_prompt_profile == "minimal_control" and args.multi_pass:
        parser.error("minimal_control cannot be combined with --multi-pass")
    if args.analysis_prompt_profile == "minimal_control" and args.rhythm_strip_pass:
        parser.error("minimal_control requires --no-rhythm-strip-pass")
    if args.ecgfounder_waveform_evidence and not args.multi_pass:
        parser.error("--ecgfounder-waveform-evidence requires --multi-pass")
    if not (
        0.0
        < args.initial_response_sla_sec
        < args.first_refinement_sla_sec
        < args.total_analysis_sla_sec
    ):
        parser.error(
            "SLA values must satisfy 0 < initial response < first refinement < total"
        )
    if args.resume_retry_errors and not args.resume:
        parser.error("--resume-retry-errors requires --resume")
    _configure_eval_logging(args.verbose)

    manifest_path = args.manifest or (
        _DATASET_DIR / args.dataset / "manifest.json"
        if args.dataset
        else _DATASET_DIR / "manifest.json"
    )

    if not manifest_path.exists():
        print(
            f"Manifest not found: {manifest_path}\n"
            f"Run: uv run python scripts/fetch-eval-datasets.py",
            file=sys.stderr,
        )
        return 2

    cases = _load_cases(manifest_path)
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("No cases in manifest.", file=sys.stderr)
        return 2

    mode = "mock" if args.mock else "real"
    ecgfounder_health: dict[str, object] = {}
    if args.ecgfounder_waveform_evidence:
        if mode != "real":
            print(
                "ERROR: ECGFounder waveform evidence is a real-model arm only.",
                file=sys.stderr,
            )
            return 2
        if not ecg_founder_tool_enabled(os.environ):
            print(
                "ERROR: ECGFounder evidence requires "
                "DICOM_ECGFOUNDER_ENDPOINT and DICOM_ECGFOUNDER_TOKEN.",
                file=sys.stderr,
            )
            return 2
        audit_path_text = os.environ.get("DICOM_ECGFOUNDER_AUDIT_PATH", "").strip()
        audit_path = Path(audit_path_text) if audit_path_text else None
        if (
            audit_path is None
            or not audit_path.is_absolute()
            or not audit_path.parent.is_dir()
            or not os.access(audit_path.parent, os.W_OK)
        ):
            print(
                "ERROR: ECGFounder evidence requires an absolute, writable "
                "DICOM_ECGFOUNDER_AUDIT_PATH shared with the Gateway plugin.",
                file=sys.stderr,
            )
            return 2
        missing_waveforms = [
            case.label or case.image_path.name
            for case in cases
            if not case.waveform_artifact_id
        ]
        if missing_waveforms:
            print(
                "ERROR: paired ECGFounder arm requires waveform_artifact_id "
                f"for every selected case; missing {len(missing_waveforms)}.",
                file=sys.stderr,
            )
            return 2
        health_payload, sidecar_reason = _probe_ecg_founder_deep_health(os.environ)
        if health_payload is None:
            print(
                "ERROR: ECGFounder deep health did not prove the pinned sidecar "
                f"ready ({sidecar_reason}).",
                file=sys.stderr,
            )
            return 2
        ecgfounder_health = health_payload
    model_id = args.model_id or (
        "mock-eval-gateway"
        if args.mock
        else os.environ.get("DICOM_OVERLAY_MODEL_ID", "unspecified")
    )
    if mode == "real":
        has_key = bool(
            os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
        )
        if not has_key:
            print(
                "WARNING: no ANTHROPIC_API_KEY/OPENAI_API_KEY in environment. "
                "Real gateway will likely fail; use --mock for a pipeline "
                "check.",
                file=sys.stderr,
            )

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output_dir = args.output or (_REPO_ROOT / "data" / "eval" / f"{mode}-{stamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        current_fingerprint = _build_protocol_fingerprint(
            manifest_path=manifest_path,
            cases=cases,
            model_id=model_id,
            mode=mode,
            flags={
                "limit": args.limit,
                "guardrail_hooks": _guardrail_hook_names(
                    analysis_prompt_profile=args.analysis_prompt_profile,
                    multi_pass=bool(args.multi_pass),
                ),
                "single_pass_bbox_calibrator": (
                    "calibrate_ekg_bboxes"
                    if args.analysis_prompt_profile == "clinical"
                    else "disabled"
                ),
                "max_image_edge_px": _MAX_IMAGE_EDGE_PX,
                "multi_pass": bool(args.multi_pass),
                "analysis_prompt_profile": args.analysis_prompt_profile,
                "openclaw_thinking_level": args.openclaw_thinking_level,
                "openclaw_fast_mode": bool(args.fast_mode),
                "multi_pass_max_targets": args.multi_pass_max_targets,
                "multi_pass_max_ekg_systematic_probes": (
                    args.multi_pass_max_ekg_systematic_probes
                ),
                "initial_response_sla_sec": args.initial_response_sla_sec,
                "first_refinement_sla_sec": args.first_refinement_sla_sec,
                "total_analysis_sla_sec": args.total_analysis_sla_sec,
                "multi_pass_bbox_calibrator": "calibrate_ekg_bboxes",
                "local_signal_candidates": (
                    "image_processor"
                    if args.analysis_prompt_profile == "clinical"
                    else "disabled"
                ),
                "refinement_crop_source": "original_roi",
                "partial_scorecard_interval": args.partial_scorecard_interval,
                "defer_scoring": bool(args.defer_scoring),
                "require_perfect": bool(args.require_perfect),
                "rhythm_strip_pass": bool(args.rhythm_strip_pass),
                "ecgfounder_waveform_evidence": bool(args.ecgfounder_waveform_evidence),
                "ecgfounder_paired_case_count": sum(
                    bool(case.waveform_artifact_id) for case in cases
                ),
                "ecgfounder_model_revision": str(
                    ecgfounder_health.get("model_revision") or ""
                ),
                "ecgfounder_checkpoint_sha256": str(
                    ecgfounder_health.get("checkpoint_sha256") or ""
                ),
                "ecgfounder_preprocessing_revision": str(
                    ecgfounder_health.get("preprocessing_revision") or ""
                ),
                "timeout_sec": args.timeout_sec,
            },
        )
        fingerprint = _prepare_protocol_fingerprint(
            output_dir=output_dir,
            current=current_fingerprint,
            cases=cases,
            resume=bool(args.resume),
            legacy_policy=args.resume_legacy_policy,
        )
    except ProtocolFingerprintError as exc:
        print(f"ERROR: protocol fingerprint validation failed: {exc}", file=sys.stderr)
        return 2

    protocol_digest = str(fingerprint["protocol_digest"])
    comparison = fingerprint.get("comparability")
    comparable = isinstance(comparison, dict) and comparison.get("comparable") is True
    print(
        f"Protocol fingerprint: {protocol_digest} "
        f"({'comparable' if comparable else 'mixed/non-comparable'})"
    )
    if args.resume:
        cases, skipped = _pending_cases(
            cases,
            output_dir,
            retry_errors=bool(args.resume_retry_errors),
        )
        print(
            f"Resume: skipped {skipped} existing result(s); "
            f"{len(cases)} case(s) remain"
            f"{' (including persisted errors)' if args.resume_retry_errors else ''}."
        )
        if not cases:
            if args.defer_scoring:
                print("Resume complete: no pending blinded inference cases.")
                return 0 if comparable else 6
            rebuild_exit, rebuild_output = _rebuild_canonical_scorecard(
                output_dir=output_dir,
                manifest_path=manifest_path,
                gateway_mode=mode,
            )
            if rebuild_exit != 0:
                print(rebuild_output, file=sys.stderr)
                return 5
            print("Resume complete: no pending cases; canonical scorecard rebuilt.")
            return 0 if comparable else 6

    start = time.monotonic()
    try:
        report = asyncio.run(
            _run(
                cases,
                args.gateway,
                mode,
                output_dir,
                args.timeout_sec,
                multi_pass=args.multi_pass,
                multi_pass_max_targets=args.multi_pass_max_targets,
                multi_pass_max_ekg_systematic_probes=(
                    args.multi_pass_max_ekg_systematic_probes
                ),
                initial_response_sla_sec=args.initial_response_sla_sec,
                first_refinement_sla_sec=args.first_refinement_sla_sec,
                total_analysis_sla_sec=args.total_analysis_sla_sec,
                analysis_prompt_profile=args.analysis_prompt_profile,
                openclaw_fast_mode=bool(args.fast_mode),
                partial_scorecard_interval=args.partial_scorecard_interval,
                rhythm_strip_pass=args.rhythm_strip_pass,
                ecg_founder_waveform_evidence=(args.ecgfounder_waveform_evidence),
                ecg_founder_preprocessing_revision=str(
                    ecgfounder_health.get("preprocessing_revision") or ""
                ),
                protocol_digest=protocol_digest,
                source_image_hashes=_fingerprint_image_hashes(fingerprint),
            )
        )
    except (ConnectionError, OSError) as exc:
        print(
            f"\nERROR: could not reach gateway at {args.gateway}: {exc}\n"
            f"Start the gateway (see REAL_TEST_RUNBOOK.md) or run with --mock.",
            file=sys.stderr,
        )
        return 1
    elapsed = time.monotonic() - start
    if not args.defer_scoring:
        rebuild_exit, rebuild_output = _rebuild_canonical_scorecard(
            output_dir=output_dir,
            manifest_path=manifest_path,
            gateway_mode=mode,
        )
        if rebuild_exit != 0:
            print(
                "\nERROR: could not atomically rebuild the full canonical scorecard:\n"
                + rebuild_output,
                file=sys.stderr,
            )
            return 5
    else:
        print("Blinded inference complete; formal scoring is deferred to the runner.")
    _print_summary(report, output_dir, case_print_limit=args.case_print_limit)
    print(f"  total run time: {elapsed:.1f}s")
    # A definitive can't-miss or an urgent uncertain differential that was not
    # safely surfaced fails CI. The latter accepts uncertainty; it does not
    # require the model to manufacture a diagnosis.
    if not args.defer_scoring and (
        report.cant_miss_missed or report.urgent_concern_missed
    ):
        missed_count = len(report.cant_miss_missed) + len(report.urgent_concern_missed)
        print(
            f"\nFAIL: {missed_count} critical diagnosis/urgent concern(s) "
            "were not safely surfaced. See gates above.",
            file=sys.stderr,
        )
        return 3
    if args.require_perfect and not args.defer_scoring:
        failures = report.perfect_failures()
        if failures:
            print(
                f"\nFAIL: {len(failures)} strict evaluation issue(s). "
                f"See PERFECT GATE above.",
                file=sys.stderr,
            )
            return 4
    if not comparable:
        print(
            "\nFAIL: run is explicitly marked mixed_protocol_legacy and is not "
            "comparable.",
            file=sys.stderr,
        )
        return 6
    return 0


if __name__ == "__main__":
    sys.exit(main())
