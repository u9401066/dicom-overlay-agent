"""Preserve installed Python/runtime notices without adding runtime dependencies."""

from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import re
import shutil
import sys
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

NOTICE_NAME = re.compile(r"^(LICENSE|LICENCE|COPYING|NOTICE|COPYRIGHT)([.-].*)?$", re.I)


def runtime_distributions():
    """Resolve the installed runtime closure; exclude optional development extras."""
    pending = [
        "dicom-overlay-agent",
        "pyinstaller",
    ]  # Includes frozen bootloader notice.
    seen = set()
    distributions = []
    while pending:
        name = canonicalize_name(pending.pop())
        if name in seen:
            continue
        seen.add(name)
        dist = metadata.distribution(name)
        if name != "dicom-overlay-agent":
            distributions.append(dist)
        # PyInstaller's build dependencies are not shipped with its bootloader.
        if name == "pyinstaller":
            continue
        for raw in dist.requires or ():
            requirement = Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return sorted(distributions, key=lambda dist: dist.metadata["Name"].casefold())


def stage(repo: Path, output: Path) -> dict:
    repo = repo.resolve()
    output = output.resolve()
    if not output.is_relative_to(repo / "build") or output == repo / "build":
        raise ValueError("Notice output must be a child of repository build directory")
    records = []
    for dist in runtime_distributions():
        name = canonicalize_name(dist.metadata["Name"])
        notices = [entry for entry in dist.files or () if NOTICE_NAME.match(entry.name)]
        if not notices:
            raise ValueError(f"No installed upstream notice found for {name}")
        for entry in notices:
            source = Path(dist.locate_file(entry)).resolve(strict=True)
            # Include full wheel-relative path to retain nested third-party notices.
            relative = Path("python") / name / str(entry)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Notice path escapes its package")
            records.append(_copy_notice(source, output, relative, dist.version))
    for relative, source in (
        (Path("python-runtime/LICENSE.txt"), Path(sys.base_prefix) / "LICENSE.txt"),
        (Path("node/LICENSE"), repo / "node/LICENSE"),
        (Path("application/LICENSE"), repo / "LICENSE"),
    ):
        records.append(_copy_notice(source, output, relative, ""))
    inventory = {"schema_version": 1, "files": records}
    (output / "notice-inventory.json").write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )
    return inventory


def _copy_notice(source: Path, output: Path, relative: Path, version: str) -> dict:
    content = source.read_bytes()
    if not content.strip():
        raise ValueError(f"Empty upstream notice: {relative}")
    target = (output / relative).resolve()
    if not target.is_relative_to(output):
        raise ValueError("Notice path escapes output")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return {
        "path": relative.as_posix(),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "version": version,
    }


if __name__ == "__main__":
    repository = Path(__file__).resolve().parents[1]
    result = stage(repository, repository / "build/package-notices")
    print(f"Preserved {len(result['files'])} Python/Node/application notices")
