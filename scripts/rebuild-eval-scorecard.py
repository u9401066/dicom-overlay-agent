"""Rebuild a scorecard from saved eval raw results.

This is useful after the scorer changes: it lets old or in-progress experiments
gain new aggregate metrics (for example partial credit) without rerunning the
model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

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
    "lead_I", "lead_II", "lead_III",
    "lead_aVR", "lead_aVL", "lead_aVF",
    "lead_V1", "lead_V2", "lead_V3", "lead_V4", "lead_V5", "lead_V6",
    "rhythm_strip",
)
_CXR_VALID_REGIONS = (
    "trachea", "right_upper_lung", "right_middle_lung", "right_lower_lung",
    "left_upper_lung", "left_middle_lung", "left_lower_lung",
    "right_cp_angle", "left_cp_angle", "cardiac_silhouette", "mediastinum",
    "diaphragm",
)
_CT_BRAIN_VALID_REGIONS = (
    "right_frontal", "left_frontal", "right_temporal", "left_temporal",
    "right_basal_ganglia", "left_basal_ganglia", "ventricles", "midline",
    "posterior_fossa",
)
_DEFAULT_VALID_REGIONS = {
    Modality.EKG: _EKG_VALID_REGIONS,
    Modality.CXR: _CXR_VALID_REGIONS,
    Modality.CT_BRAIN: _CT_BRAIN_VALID_REGIONS,
}


def rebuild_scorecard(
    *,
    eval_dir: Path,
    manifest_path: Path,
    output_path: Path | None = None,
    gateway_mode: str | None = None,
) -> Path:
    """Score saved ``results/*.json`` files and write a rebuilt scorecard."""
    eval_dir = Path(eval_dir)
    output_path = output_path or (eval_dir / "scorecard.rebuilt.json")
    cases = _load_cases(manifest_path)
    result_paths = sorted((eval_dir / "results").glob("*.json"))
    raw_by_case = {
        str(raw.get("case") or path.stem): raw
        for path in result_paths
        for raw in [json.loads(path.read_text(encoding="utf-8"))]
    }
    scores = []
    scored_cases = []
    scored_labels: set[str] = set()
    for case in cases:
        label = case.label or case.image_path.stem
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
        case.label or case.image_path.stem
        for case in cases
        if (case.label or case.image_path.stem) not in scored_labels
    ]
    payload.update(
        {
            "manifest_total": len(cases),
            "result_count": len(scores),
            "missing_cases": missing,
            "is_partial": bool(missing),
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


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
                label=entry.get("label", ""),
                valid_regions=tuple(
                    entry.get("valid_regions") or _DEFAULT_VALID_REGIONS.get(modality, ())
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
        )
        for item in raw.get("findings") or []
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
        model_used=str(raw.get("model_used") or ""),
        zoom_hints=[str(item) for item in raw.get("zoom_hints") or []],
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
    args = parser.parse_args()

    try:
        output = rebuild_scorecard(
            eval_dir=args.eval_dir,
            manifest_path=args.manifest,
            output_path=args.output,
            gateway_mode=args.gateway_mode,
        )
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Rebuilt scorecard: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
