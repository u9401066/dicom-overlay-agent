"""Build a deterministic MEETI case denylist from prior experiment artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_CASE_PATTERN = re.compile(r"(?<![A-Za-z0-9_])meeti_[0-9]+(?![A-Za-z0-9_])")
# Gateway verbose logs can span gigabytes and duplicate identities already
# persisted in result/protocol JSON. Keep the reproducible evidence sources.
_TEXT_SUFFIXES = frozenset({".json", ".jsonl", ".md", ".txt"})
_SKIP_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "openclaw-state",
        "__pycache__",
    }
)


def build_denylist(
    *, sources: list[Path], output_path: Path, report_path: Path
) -> dict[str, Any]:
    output_path = output_path.resolve()
    report_path = report_path.resolve()
    excluded = {output_path, report_path}
    files = sorted(
        {
            file.resolve()
            for source in sources
            for file in _source_files(source.resolve())
            if file.resolve() not in excluded
        },
        key=lambda path: path.as_posix().casefold(),
    )
    case_ids: set[str] = set()
    scanned_bytes = 0
    for path in files:
        scanned_bytes += path.stat().st_size
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                case_ids.update(_CASE_PATTERN.findall(line))

    ordered = sorted(case_ids)
    denylist_text = "".join(f"{case_id}\n" for case_id in ordered)
    _atomic_write_text(output_path, denylist_text)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "case_pattern": _CASE_PATTERN.pattern,
        "sources": [str(path.resolve()) for path in sources],
        "files_scanned": len(files),
        "bytes_scanned": scanned_bytes,
        "case_count": len(ordered),
        "case_identity_order_sha256": hashlib.sha256(
            "\n".join(ordered).encode("utf-8")
        ).hexdigest(),
        "denylist": str(output_path),
        "denylist_sha256": hashlib.sha256(denylist_text.encode("utf-8")).hexdigest(),
    }
    _atomic_write_text(
        report_path,
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
    )
    return report


def _source_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.casefold() in _TEXT_SUFFIXES else []
    if not path.is_dir():
        raise ValueError(f"exposure source does not exist: {path}")
    files: list[Path] = []
    for directory, directory_names, file_names in os.walk(path):
        directory_names[:] = [
            name for name in directory_names if name not in _SKIP_DIRECTORY_NAMES
        ]
        parent = Path(directory)
        files.extend(
            parent / name
            for name in file_names
            if Path(name).suffix.casefold() in _TEXT_SUFFIXES
        )
    return files


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_denylist(
            sources=args.source,
            output_path=args.output,
            report_path=args.report,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Wrote {report['case_count']} exposed case ids to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
