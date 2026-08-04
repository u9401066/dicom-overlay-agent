#!/usr/bin/env python
"""Build a curated MEETI evaluation manifest from ``MEETI.rar``.

The MEETI archive holds a large ECG corpus with rendered 12-lead ``.png`` files
plus sibling ``.mat`` files whose ``report`` field is the ground truth. This
script streams the archive, classifies each report via
:func:`dicom_overlay.infrastructure.meeti_dataset.classify_report`, keeps a
subset, extracts the chosen ``.png`` images into
``data/eval-datasets/meeti/ekg/`` and writes a ``manifest.json`` in the schema
``scripts/run-eval.py`` consumes.

With ``--include-waveforms``, the matching raw ``signal`` matrices are retained
under ``waveforms/`` and indexed by an opaque artifact id in
``waveform-registry.json``. OpenClaw sees only that id; the ECGFounder sidecar
owns path resolution and verifies the source hash before inference.

Design notes:
* ``data/`` is fully gitignored -- images and manifest stay out of version control.
* scipy is a dev/eval-only dependency (never bundled in the runtime). Run with
  ``uv run --with scipy --with numpy python scripts/build-meeti-eval.py``.
* The default is a 1000-case balanced production gate. Use ``--selection all``
  with a higher ``--max-cases``/``--min-cases`` to build a full-size manifest.

Usage:
    uv run --with scipy --with numpy python scripts/build-meeti-eval.py \
        --rar MEETI.rar --per-concept 100 --max-cases 1000 --min-cases 1000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dicom_overlay.infrastructure.meeti_dataset import (  # noqa: E402
    REPORT_LABEL_SCHEMA_VERSION,
    ReportLabels,
    classify_report,
    read_mat_report,
)

_SEVENZIP_CANDIDATES = (
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
    "7z",
)
_TAR_CANDIDATES = ("tar", "bsdtar")
_MEETI_SOURCE_LEADS = (
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
_ECGFOUNDER_MODEL_LEADS = (
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


def _find_first(candidates: tuple[str, ...]) -> str | None:
    for cand in candidates:
        if Path(cand).exists() or shutil.which(cand):
            return cand
    return None


def _find_archive_tool(kind: str, explicit_path: str = "") -> tuple[str, str]:
    """Return ``(kind, executable)`` for archive listing/extraction."""

    if explicit_path:
        path = Path(explicit_path)
        if path.exists() or shutil.which(explicit_path):
            return kind, explicit_path
        raise SystemExit(f"{kind} executable not found: {explicit_path}")

    if kind == "7z":
        exe = _find_first(_SEVENZIP_CANDIDATES)
        if exe:
            return "7z", exe
        raise SystemExit("7-Zip (7z) not found; install it or pass --sevenzip.")

    if kind == "tar":
        exe = _find_first(_TAR_CANDIDATES)
        if exe:
            return "tar", exe
        raise SystemExit("bsdtar/tar not found; install it or pass --extractor 7z.")

    sevenzip = _find_first(_SEVENZIP_CANDIDATES)
    if sevenzip:
        return "7z", sevenzip
    tar = _find_first(_TAR_CANDIDATES)
    if tar:
        return "tar", tar
    raise SystemExit("No RAR-capable extractor found; install 7-Zip or bsdtar.")


def _parse_7z_png_listing(output: str) -> list[str]:
    """Return archive-internal paths of every ``.png`` (one per usable study)."""

    paths: list[str] = []
    for line in output.splitlines():
        line = line.rstrip()
        if not line.lower().endswith(".png"):
            continue
        # bare format: "date time attr size compressed name"; name is the rest
        # after the 5th whitespace-delimited column.
        parts = line.split(None, 5)
        if len(parts) == 6:
            paths.append(parts[5])
    return paths


def _parse_tar_png_listing(output: str) -> list[str]:
    """Return ``.png`` members from a ``tar -tf`` style listing."""

    return [
        line.strip()
        for line in output.splitlines()
        if line.strip().lower().endswith(".png")
    ]


def _list_png_entries(tool_kind: str, exe: str, rar: Path) -> list[str]:
    if tool_kind == "7z":
        proc = subprocess.run(
            [exe, "l", "-ba", str(rar), "*.png", "-r"],
            capture_output=True,
            text=True,
            check=True,
        )
        return _parse_7z_png_listing(proc.stdout)

    proc = subprocess.run(
        [exe, "-tf", str(rar)],
        capture_output=True,
        text=True,
        check=True,
    )
    return _parse_tar_png_listing(proc.stdout)


def _mat_for_png(png_path: str) -> str:
    return png_path[:-4] + ".mat"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _waveform_artifact_id(source_sha256: str) -> str:
    """Derive a stable non-path id from the trusted waveform content hash."""

    digest = hashlib.sha256(
        b"meeti-ecgfounder-artifact-v1\0" + bytes.fromhex(source_sha256)
    ).hexdigest()
    return f"wf-{digest[:32]}"


def _waveform_registry_entry(
    *,
    waveform_path: Path,
    registry_dir: Path,
    source_sha256: str,
) -> dict[str, object]:
    return {
        "path": waveform_path.relative_to(registry_dir).as_posix(),
        "source_kind": "raw_waveform",
        "source_sha256": source_sha256,
        "source_sample_rate_hz": 500,
        "source_duration_sec": 10,
        "source_points_per_lead": 5000,
        "source_lead_names": list(_MEETI_SOURCE_LEADS),
        "model_lead_names": list(_ECGFOUNDER_MODEL_LEADS),
        "lead_mode": "12_lead",
        "dataset": "MEETI",
    }


def _extract_many(
    tool_kind: str,
    exe: str,
    rar: Path,
    members: list[str],
    dest_dir: Path,
) -> None:
    """Batch-extract many archive members *flat* into ``dest_dir``.

    Uses a list file so a single process handles the whole chunk -- the 5.7 GB
    central directory is read once per call instead of once per member, which is
    the difference between minutes and hours.
    """

    if not members:
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    list_file = dest_dir / "_members.lst"
    list_file.write_text("\n".join(members), encoding="utf-8")
    try:
        if tool_kind == "7z":
            subprocess.run(
                [exe, "e", str(rar), f"@{list_file}", f"-o{dest_dir}", "-y"],
                capture_output=True,
                text=True,
                check=True,
            )
            return

        staging = dest_dir / "_tar_extract"
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [exe, "-xf", str(rar), "-C", str(staging), "-T", str(list_file)],
            capture_output=True,
            text=True,
            check=True,
        )
        for member in members:
            source = staging / member
            if source.exists():
                shutil.copy2(source, dest_dir / Path(member).name)
        shutil.rmtree(staging, ignore_errors=True)
    finally:
        list_file.unlink(missing_ok=True)


def _all_flat_members_exist(dest_dir: Path, members: list[str]) -> bool:
    """True when every archive member already exists by basename in ``dest_dir``."""

    return bool(members) and all(
        (dest_dir / Path(member).name).exists() for member in members
    )


def _primary_concept(labels: ReportLabels) -> str:
    """Return an explicit sampling stratum without polluting diagnoses."""

    if labels.concepts:
        return labels.concepts[0]
    if labels.uncertain_concepts:
        return f"uncertain:{labels.uncertain_concepts[0]}"
    return f"status:{labels.label_status}"


def _candidate_slice(png_entries: list[str], scan_limit: int) -> list[str]:
    """Return the entries to inspect; ``scan_limit <= 0`` means all."""

    return png_entries if scan_limit <= 0 else png_entries[:scan_limit]


def _under_case_limit(current: int, pending: int, max_cases: int) -> bool:
    """True while another selected image may be added."""

    return max_cases <= 0 or current + pending < max_cases


def _enforce_min_cases(cases: list[dict[str, object]], min_cases: int) -> None:
    if min_cases > 0 and len(cases) < min_cases:
        raise SystemExit(
            f"min-cases gate failed: kept {len(cases)} case(s), "
            f"required at least {min_cases}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rar", default=str(_REPO_ROOT / "MEETI.rar"))
    parser.add_argument(
        "--output",
        default=str(_REPO_ROOT / "data" / "eval-datasets" / "meeti"),
        help="Destination dataset dir (manifest + ekg/ images).",
    )
    parser.add_argument("--per-concept", type=int, default=100)
    parser.add_argument(
        "--max-cases",
        type=int,
        default=1000,
        help="Maximum cases to keep (0 = no cap).",
    )
    parser.add_argument(
        "--min-cases",
        type=int,
        default=1000,
        help="Fail if fewer cases are written (0 disables the gate).",
    )
    parser.add_argument(
        "--scan-limit",
        type=int,
        default=0,
        help="Max PNG-bearing studies to inspect before stopping (0 = all).",
    )
    parser.add_argument(
        "--chunk",
        type=int,
        default=400,
        help="Studies per batch 7z extraction (one process per chunk).",
    )
    parser.add_argument(
        "--selection",
        choices=("balanced", "all"),
        default="balanced",
        help="balanced caps each diagnostic concept; all keeps every readable image.",
    )
    parser.add_argument(
        "--extractor",
        choices=("auto", "7z", "tar"),
        default="auto",
        help="Archive backend. Windows bsdtar can read the MEETI RAR.",
    )
    parser.add_argument("--sevenzip", default="", help="Explicit 7z executable path.")
    parser.add_argument(
        "--tar", default="", help="Explicit tar/bsdtar executable path."
    )
    parser.add_argument(
        "--include-waveforms",
        action="store_true",
        help=(
            "Retain selected .mat signals and emit waveform-registry.json for "
            "the optional ECGFounder sidecar."
        ),
    )
    args = parser.parse_args()

    rar = Path(args.rar)
    if not rar.exists():
        raise SystemExit(f"archive not found: {rar}")

    explicit = args.sevenzip if args.extractor == "7z" else args.tar
    tool_kind, exe = _find_archive_tool(args.extractor, explicit_path=explicit)
    out_dir = Path(args.output)
    img_dir = out_dir / "ekg"
    waveform_dir = out_dir / "waveforms"
    tmp_dir = out_dir / "_tmp"
    img_dir.mkdir(parents=True, exist_ok=True)
    if args.include_waveforms:
        waveform_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[meeti] listing png entries in {rar.name} via {tool_kind} ...",
        flush=True,
    )
    png_entries = _list_png_entries(tool_kind, exe, rar)
    print(f"[meeti] {len(png_entries)} png-bearing studies found", flush=True)

    per_concept: Counter[str] = Counter()
    cant_miss_have: Counter[str] = Counter()
    urgent_concerns_have: Counter[str] = Counter()
    cases: list[dict[str, object]] = []
    waveform_artifacts: dict[str, dict[str, object]] = {}
    scanned = 0

    candidates = _candidate_slice(png_entries, args.scan_limit)
    for start in range(0, len(candidates), args.chunk):
        if args.max_cases > 0 and len(cases) >= args.max_cases:
            break
        chunk = candidates[start : start + args.chunk]

        # Batch-extract this chunk's .mat siblings in one archive process. The
        # flat cache makes interrupted 1000+ builds resumable.
        mat_members = [_mat_for_png(p) for p in chunk]
        if tmp_dir.exists() and _all_flat_members_exist(tmp_dir, mat_members):
            print(
                f"[meeti] reusing {len(mat_members)} cached .mat file(s)",
                flush=True,
            )
        elif tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
            _extract_many(tool_kind, exe, rar, mat_members, tmp_dir)
        else:
            _extract_many(tool_kind, exe, rar, mat_members, tmp_dir)

        keep_png: list[str] = []  # png members chosen from this chunk
        keep_meta: dict[
            str, tuple[str, ReportLabels]
        ] = {}  # study_id -> (report, labels)

        for png_member in chunk:
            scanned += 1
            study_id = Path(png_member).stem
            mat_path = tmp_dir / f"{study_id}.mat"
            if not mat_path.exists():
                continue
            try:
                report = read_mat_report(str(mat_path))
            except Exception as exc:  # skip unreadable mats
                print(f"[meeti] skip {study_id}: {exc}", flush=True)
                continue

            labels = classify_report(report)
            concept = _primary_concept(labels)

            if not _under_case_limit(len(cases), len(keep_png), args.max_cases):
                continue

            if args.selection == "all":
                keep = True
            else:
                # Balance: keep if (a) it carries a not-yet-saturated can't-miss,
                # or (b) its primary concept is under the per-concept cap.
                keep = False
                if labels.cant_miss and any(
                    cant_miss_have[cm] < args.per_concept for cm in labels.cant_miss
                ):
                    keep = True
                if per_concept[concept] < args.per_concept:
                    keep = True
            if not keep:
                continue

            per_concept[concept] += 1
            for cm in labels.cant_miss:
                cant_miss_have[cm] += 1
            for concern in labels.urgent_concerns:
                urgent_concerns_have[concern] += 1
            keep_png.append(png_member)
            keep_meta[study_id] = (report, labels)

        # Batch-extract only the chosen .png images for this chunk. Reuse prior
        # output if an interrupted run already copied every selected image.
        missing_png = [
            member for member in keep_png if not (img_dir / Path(member).name).exists()
        ]
        if missing_png:
            _extract_many(tool_kind, exe, rar, missing_png, img_dir)

        for png_member in keep_png:
            study_id = Path(png_member).stem
            png_out = img_dir / f"{study_id}.png"
            if not png_out.exists():
                continue
            report, labels = keep_meta[study_id]
            case: dict[str, object] = {
                "image": f"ekg/{png_out.name}",
                "modality": "EKG",
                "label": f"meeti_{study_id}",
                "source": "meeti",
                "report": report,
                **labels.manifest_fields(),
            }
            if args.include_waveforms:
                mat_source = tmp_dir / f"{study_id}.mat"
                waveform_out = waveform_dir / mat_source.name
                if not waveform_out.exists() or (
                    waveform_out.stat().st_size != mat_source.stat().st_size
                ):
                    shutil.copy2(mat_source, waveform_out)
                source_sha256 = _sha256_file(waveform_out)
                artifact_id = _waveform_artifact_id(source_sha256)
                waveform_artifacts[artifact_id] = _waveform_registry_entry(
                    waveform_path=waveform_out,
                    registry_dir=out_dir,
                    source_sha256=source_sha256,
                )
                case.update(
                    {
                        "waveform_artifact_id": artifact_id,
                        "waveform_lead_mode": "12_lead",
                    }
                )
            cases.append(case)

        print(
            f"[meeti] kept {len(cases)} (scanned {scanned}) "
            f"concepts={dict(per_concept)}",
            flush=True,
        )

    # Tidy temp dir.
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    by_severity = dict(Counter(str(c["expected_severity"]) for c in cases))
    by_label_status = dict(Counter(str(c["label_status"]) for c in cases))
    classifier_path = (
        _REPO_ROOT / "src" / "dicom_overlay" / "infrastructure" / "meeti_dataset.py"
    )
    artifact_index_payload = json.dumps(
        waveform_artifacts,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    artifact_index_sha256 = hashlib.sha256(artifact_index_payload).hexdigest()
    manifest = {
        "dataset": "MEETI",
        "modality": "EKG",
        "source_record": "https://zenodo.org/records/18523205",
        "selection": {
            "mode": args.selection,
            "max_cases": args.max_cases,
            "min_cases": args.min_cases,
            "scan_limit": args.scan_limit,
            "per_concept": args.per_concept,
            "extractor": tool_kind,
            "png_entries": len(png_entries),
            "scanned": scanned,
        },
        "note": (
            "Ground truth derived from MEETI .mat 'report' field via "
            "classify_report(). Images are rendered 12-lead ECGs. Matching raw "
            "waveforms are retained only when include_waveforms is true."
        ),
        "labeling": {
            "schema_version": REPORT_LABEL_SCHEMA_VERSION,
            "classifier": "classify_report",
            "classifier_sha256": hashlib.sha256(
                classifier_path.read_bytes()
            ).hexdigest(),
        },
        "counts": {
            "cases": len(cases),
            "by_selection_stratum": dict(per_concept),
            "cant_miss": dict(cant_miss_have),
            "urgent_concerns": dict(urgent_concerns_have),
            "by_severity": by_severity,
            "by_label_status": by_label_status,
        },
        "waveform_registry": (
            {
                "path": "waveform-registry.json",
                "artifact_count": len(waveform_artifacts),
                "artifact_index_sha256": artifact_index_sha256,
            }
            if args.include_waveforms
            else None
        ),
        "cases": cases,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if args.include_waveforms:
        registry = {
            "schema_version": 1,
            "dataset": "MEETI",
            "artifact_index_sha256": artifact_index_sha256,
            "artifacts": waveform_artifacts,
        }
        registry_path = out_dir / "waveform-registry.json"
        registry_path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    _enforce_min_cases(cases, args.min_cases)

    print("\n[meeti] DONE", flush=True)
    print(f"[meeti] cases: {len(cases)} (scanned {scanned})", flush=True)
    print(f"[meeti] severity: {by_severity}", flush=True)
    print(f"[meeti] cant_miss: {dict(cant_miss_have)}", flush=True)
    if args.include_waveforms:
        print(
            f"[meeti] waveform artifacts: {len(waveform_artifacts)}",
            flush=True,
        )
    print(f"[meeti] manifest: {manifest_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
