"""Rebuild a scorecard from saved eval raw results.

This is useful after the scorer changes: it lets old or in-progress experiments
gain new aggregate metrics (for example partial credit) without rerunning the
model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dicom_overlay.domain.entities import (  # noqa: E402
    AnalysisResult,
    ChecklistItem,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.domain.modality_profile import get_active_registry  # noqa: E402
from dicom_overlay.infrastructure.eval_harness import (  # noqa: E402
    EvalCase,
    _aggregate,
    _error_score,
    score_case,
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
_PROTOCOL_FINGERPRINT_NAME = "protocol-fingerprint.json"
_PROTOCOL_FINGERPRINT_SCHEMA_VERSION = 1


def rebuild_scorecard(
    *,
    eval_dir: Path,
    manifest_path: Path,
    output_path: Path | None = None,
    gateway_mode: str | None = None,
    promote_canonical: bool = False,
    require_protocol_fingerprint: bool = False,
) -> Path:
    """Score saved ``results/*.json`` files and write a rebuilt scorecard."""
    eval_dir = Path(eval_dir)
    output_path = output_path or (eval_dir / "scorecard.rebuilt.json")
    manifest_path = Path(manifest_path).resolve()
    fingerprint = _load_protocol_fingerprint(
        eval_dir,
        required=require_protocol_fingerprint,
    )
    cases = _select_fingerprinted_cases(
        _load_cases(manifest_path),
        manifest_path=manifest_path,
        fingerprint=fingerprint,
    )
    result_paths = sorted((eval_dir / "results").glob("*.json"))
    raw_by_case = _load_result_artifacts(
        result_paths,
        cases=cases,
        fingerprint=fingerprint,
    )
    scores = []
    scored_cases = []
    scored_labels: set[str] = set()
    for case in cases:
        label = case.label or case.image_path.name
        raw = raw_by_case.get(label)
        if raw is None:
            continue
        latency_ms = int(raw.get("score", {}).get("latency_ms") or 0)
        error = raw.get("error") or raw.get("score", {}).get("error")
        if error:
            scores.append(_error_score(case, str(error)))
        else:
            result = _analysis_result_from_raw(raw, fallback_modality=case.modality)
            scores.append(score_case(case, result, latency_ms=latency_ms))
        scored_cases.append(case)
        scored_labels.add(label)

    mode = gateway_mode or _read_gateway_mode(eval_dir) or "rebuilt"
    report = _aggregate(mode, scores, scored_cases, get_active_registry())
    payload = json.loads(report.to_json())
    missing = [
        case.label or case.image_path.name
        for case in cases
        if (case.label or case.image_path.name) not in scored_labels
    ]
    payload.update(
        {
            "manifest_total": len(cases),
            "result_count": len(scores),
            "missing_cases": missing,
            "is_partial": bool(missing),
            "scorecard_kind": "full_rebuild",
            "protocol_digest": (
                str(fingerprint.get("protocol_digest")) if fingerprint else ""
            ),
            "protocol_comparability": (
                fingerprint.get("comparability")
                if fingerprint
                else {
                    "status": "legacy_unfingerprinted",
                    "comparable": False,
                    "reasons": ["protocol-fingerprint.json is missing"],
                }
            ),
        }
    )
    _atomic_write_json(output_path, payload)
    if promote_canonical:
        canonical_path = eval_dir / "scorecard.json"
        if canonical_path.resolve() != output_path.resolve():
            _atomic_write_json(canonical_path, payload)
    return output_path


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


def _load_protocol_fingerprint(
    eval_dir: Path,
    *,
    required: bool,
) -> dict[str, Any] | None:
    path = eval_dir / _PROTOCOL_FINGERPRINT_NAME
    if not path.is_file():
        if required:
            raise ValueError(f"missing required protocol fingerprint: {path}")
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("protocol fingerprint must be a JSON object")
    if payload.get("schema_version") != _PROTOCOL_FINGERPRINT_SCHEMA_VERSION:
        raise ValueError(
            "unsupported protocol fingerprint schema: "
            f"{payload.get('schema_version')!r}"
        )
    protocol = payload.get("protocol")
    if not isinstance(protocol, dict):
        raise ValueError("protocol fingerprint is missing protocol data")
    if payload.get("protocol_digest") != _protocol_digest(protocol):
        raise ValueError("protocol fingerprint digest does not match payload")
    return payload


def _select_fingerprinted_cases(
    cases: list[EvalCase],
    *,
    manifest_path: Path,
    fingerprint: dict[str, Any] | None,
) -> list[EvalCase]:
    if fingerprint is None:
        return cases
    protocol = fingerprint["protocol"]
    manifest_identity = protocol.get("manifest")
    if not isinstance(manifest_identity, dict):
        raise ValueError("protocol fingerprint is missing manifest identity")
    if manifest_identity.get("sha256") != _sha256_file(manifest_path):
        raise ValueError("manifest hash does not match protocol fingerprint")
    selected_rows = manifest_identity.get("cases")
    if not isinstance(selected_rows, list) or not selected_rows:
        raise ValueError("protocol fingerprint has no selected manifest cases")
    by_label = {case.label or case.image_path.name: case for case in cases}
    selected: list[EvalCase] = []
    seen: set[str] = set()
    for row in selected_rows:
        if not isinstance(row, dict) or not isinstance(row.get("case"), str):
            raise ValueError("protocol fingerprint contains an invalid case identity")
        label = str(row["case"])
        if label in seen:
            raise ValueError(f"duplicate fingerprint case: {label}")
        seen.add(label)
        case = by_label.get(label)
        if case is None:
            raise ValueError(f"fingerprint case is absent from manifest: {label}")
        image_path = case.image_path.resolve()
        if (
            row.get("image_name") != image_path.name
            or row.get("size_bytes") != image_path.stat().st_size
            or row.get("sha256") != _sha256_file(image_path)
        ):
            raise ValueError(f"image identity mismatch for fingerprint case: {label}")
        selected.append(case)
    if manifest_identity.get("selected_case_count") != len(selected):
        raise ValueError(
            "fingerprint selected_case_count does not match case identities"
        )
    return selected


def _result_filename(label: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in label)
    return f"{safe}.json"


def _load_result_artifacts(
    result_paths: list[Path],
    *,
    cases: list[EvalCase],
    fingerprint: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    expected_by_filename = {
        _result_filename(case.label or case.image_path.name): case for case in cases
    }
    protocol_digest = str(fingerprint.get("protocol_digest")) if fingerprint else ""
    comparison = fingerprint.get("comparability") if fingerprint else None
    comparable = isinstance(comparison, dict) and comparison.get("comparable") is True
    image_hashes: dict[str, str] = {}
    if fingerprint:
        rows = fingerprint["protocol"]["manifest"]["cases"]
        image_hashes = {str(row["case"]): str(row["sha256"]) for row in rows}

    raw_by_case: dict[str, dict[str, Any]] = {}
    for path in result_paths:
        case = expected_by_filename.get(path.name)
        if case is None:
            raise ValueError(
                f"result artifact is not in the selected manifest: {path.name}"
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"result artifact is not an object: {path.name}")
        label = case.label or case.image_path.name
        if raw.get("case") != label:
            raise ValueError(f"result case mismatch in {path.name}")
        if label in raw_by_case:
            raise ValueError(f"duplicate result case: {label}")
        score = raw.get("score")
        score = score if isinstance(score, dict) else {}
        image = raw.get("image") or score.get("image")
        if not isinstance(image, str) or Path(image).name != case.image_path.name:
            raise ValueError(f"result image mismatch in {path.name}")
        is_error = bool(raw.get("error") or score.get("error"))
        if comparable and not is_error:
            if raw.get("protocol_digest") != protocol_digest:
                raise ValueError(f"result protocol digest mismatch in {path.name}")
            if raw.get("source_image_sha256") != image_hashes[label]:
                raise ValueError(f"result image hash mismatch in {path.name}")
        raw_by_case[label] = raw
    return raw_by_case


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_cases(manifest_path: Path) -> list[EvalCase]:
    spec = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    root = Path(manifest_path).parent
    cases: list[EvalCase] = []
    for entry in spec["cases"]:
        modality = Modality(entry["modality"])
        cases.append(
            EvalCase(
                image_path=root / entry["image"],
                modality=modality,
                expected_severity=Severity(entry["expected_severity"]),
                expected_keywords=tuple(entry.get("keywords", [])),
                expected_negatives=tuple(entry.get("negatives", [])),
                target_axes=tuple(entry.get("target_axes", [])),
                cant_miss=tuple(entry.get("cant_miss", [])),
                urgent_concerns=tuple(entry.get("urgent_concerns", [])),
                label_status=str(entry.get("label_status") or "asserted"),
                uncertain_concepts=tuple(entry.get("uncertain_concepts", [])),
                ungradable_reasons=tuple(entry.get("ungradable_reasons", [])),
                label=entry.get("label", ""),
                valid_regions=tuple(
                    entry.get("valid_regions")
                    or _DEFAULT_VALID_REGIONS.get(modality, ())
                ),
            )
        )
    return cases


def _analysis_result_from_raw(
    raw: dict[str, Any],
    *,
    fallback_modality: Modality,
) -> AnalysisResult:
    modality = _enum_or_default(Modality, raw.get("modality"), fallback_modality)
    severity = _enum_or_default(Severity, raw.get("severity"), Severity.INFO)
    findings = [
        Finding(
            id=str(item.get("id") or ""),
            label=str(item.get("label") or "finding"),
            detail=str(item.get("detail") or ""),
            severity=_enum_or_default(Severity, item.get("severity"), severity),
            regions=[str(region) for region in item.get("regions") or []],
            bboxes=[
                RegionRect(
                    x=float(box.get("x", 0.0)),
                    y=float(box.get("y", 0.0)),
                    w=float(box.get("w", 0.0)),
                    h=float(box.get("h", 0.0)),
                )
                for box in item.get("bboxes") or []
            ],
            notes=[str(note) for note in item.get("notes") or []],
            confidence=str(item.get("confidence") or ""),
            question=str(item.get("question") or ""),
        )
        for item in raw.get("findings") or []
        if isinstance(item, dict)
    ]
    checklist = {
        str(key): ChecklistItem(
            value=str(value.get("value") or ""),
            status=_enum_or_default(Severity, value.get("status"), Severity.NORMAL),
        )
        for key, value in (raw.get("checklist") or {}).items()
        if isinstance(value, dict)
    }
    return AnalysisResult(
        modality=modality,
        summary=str(raw.get("summary") or ""),
        severity=severity,
        findings=findings,
        checklist=checklist,
        analysis_time_ms=int(raw.get("analysis_time_ms") or 0),
        model_used=str(raw.get("model_used") or ""),
        image_quality=raw.get("image_quality") or "",
        next_steps=[str(item) for item in raw.get("next_steps") or []],
        incomplete=bool(raw.get("incomplete", False)),
        incomplete_reasons=[str(item) for item in raw.get("incomplete_reasons") or []],
        validation_warnings=[
            str(item) for item in raw.get("validation_warnings") or []
        ],
        zoom_hints=[str(item) for item in raw.get("zoom_hints") or []],
        review_required=bool(raw.get("review_required", False)),
        review_reasons=[str(item) for item in raw.get("review_reasons") or []],
        layout=dict(raw.get("layout") or {}),
        analysis_trace=[
            dict(item)
            for item in raw.get("analysis_trace") or []
            if isinstance(item, dict)
        ],
    )


def _enum_or_default(enum_type: Any, value: Any, default: Any) -> Any:
    try:
        return enum_type(str(value))
    except (TypeError, ValueError):
        return default


def _read_gateway_mode(eval_dir: Path) -> str | None:
    path = eval_dir / "scorecard.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    mode = data.get("gateway_mode")
    return str(mode) if mode else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-dir", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_REPO_ROOT / "data" / "eval-datasets" / "meeti" / "manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Defaults to <eval-dir>/scorecard.rebuilt.json.",
    )
    parser.add_argument("--gateway-mode", default=None)
    parser.add_argument(
        "--promote-canonical",
        action="store_true",
        help="Atomically replace <eval-dir>/scorecard.json with the full rebuild.",
    )
    parser.add_argument(
        "--require-protocol-fingerprint",
        action="store_true",
        help="Fail if protocol-fingerprint.json is missing or invalid.",
    )
    args = parser.parse_args()

    try:
        output = rebuild_scorecard(
            eval_dir=args.eval_dir,
            manifest_path=args.manifest,
            output_path=args.output,
            gateway_mode=args.gateway_mode,
            promote_canonical=args.promote_canonical,
            require_protocol_fingerprint=args.require_protocol_fingerprint,
        )
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Rebuilt scorecard: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
