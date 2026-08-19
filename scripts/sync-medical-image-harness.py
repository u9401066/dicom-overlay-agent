#!/usr/bin/env python3
"""Generate a thin private-host adapter for the pinned public agent skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMODULE_REL = Path("third_party/medical-image-agent-harness")
SUBMODULE_ROOT = REPO_ROOT / SUBMODULE_REL
SOURCE_SKILL = SUBMODULE_ROOT / ".agents" / "skills" / "medical-image-reading"
TARGET_SKILL = REPO_ROOT / ".agents" / "skills" / "medical-image-reading"
LOCK_PATH = REPO_ROOT / ".agents" / "medical-image-harness.lock.json"
GENERATOR_VERSION = 2

CANONICAL_SKILL_REL = (
    SUBMODULE_REL / ".agents" / "skills" / "medical-image-reading" / "SKILL.md"
)
CANONICAL_SKILL_LINK = Path("../../..") / CANONICAL_SKILL_REL
ADAPTER_BODY = f"""
# Medical Image Reading (pinned adapter)

This file only makes the public harness discoverable from the private product root.
Before taking any medical-image task action, load and follow the pinned canonical
[medical-image-reading skill][canonical-skill]. Treat that file and its relative
references as the sole source of the scientific method and output contract.

If the canonical file or any required reference cannot be read, stop and report
that the submodule is not initialized. Product-specific OpenClaw, overlay, screen
capture, or plugin behavior must not be added to this adapter.

[canonical-skill]: {CANONICAL_SKILL_LINK.as_posix()}
""".lstrip()


class SyncError(RuntimeError):
    """The pinned public source or generated private copy is invalid."""


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SyncError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _validated_submodule_commit() -> str:
    if not SOURCE_SKILL.is_dir():
        raise SyncError(
            "public harness submodule is not initialized; run "
            "git submodule update --init --recursive"
        )
    stage = _git("ls-files", "--stage", "--", SUBMODULE_REL.as_posix())
    fields = stage.split()
    if len(fields) < 4 or fields[0] != "160000":
        raise SyncError("public harness path is not a pinned git submodule")
    pinned_commit = fields[1]
    checked_out_commit = _git("rev-parse", "HEAD", cwd=SUBMODULE_ROOT)
    if checked_out_commit != pinned_commit:
        raise SyncError(
            "public harness checkout does not match the pinned gitlink: "
            f"{checked_out_commit} != {pinned_commit}"
        )
    dirty = _git("status", "--porcelain", cwd=SUBMODULE_ROOT)
    if dirty:
        raise SyncError("public harness submodule has tracked local changes")
    return pinned_commit


def _file_map(root: Path) -> dict[str, bytes]:
    if root.is_symlink():
        raise SyncError(f"skill tree must not be a symlink: {root}")
    if not root.is_dir():
        return {}
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise SyncError(f"skill tree must not contain symlinks: {path}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def _adapter_files(source_files: dict[str, bytes]) -> dict[str, bytes]:
    source_skill = source_files.get("SKILL.md")
    if source_skill is None:
        raise SyncError("canonical public skill is missing SKILL.md")
    delimiter = b"---\n"
    if not source_skill.startswith(delimiter):
        raise SyncError("canonical public SKILL.md is missing YAML front matter")
    front_matter_end = source_skill.find(b"\n---\n", len(delimiter))
    if front_matter_end < 0:
        raise SyncError("canonical public SKILL.md has invalid YAML front matter")
    front_matter = source_skill[: front_matter_end + len(b"\n---\n")]
    return {"SKILL.md": front_matter + b"\n" + ADAPTER_BODY.encode()}


def _digests(files: dict[str, bytes]) -> dict[str, str]:
    return {
        name: hashlib.sha256(content).hexdigest()
        for name, content in sorted(files.items())
    }


def _lock_bytes(
    commit: str,
    source_files: dict[str, bytes],
    generated_files: dict[str, bytes],
) -> bytes:
    payload = {
        "generator_version": GENERATOR_VERSION,
        "source": f"{SUBMODULE_REL.as_posix()}/.agents/skills/medical-image-reading",
        "submodule_commit": commit,
        "source_files": _digests(source_files),
        "generated_files": _digests(generated_files),
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _check(expected: dict[str, bytes], lock: bytes) -> None:
    actual = _file_map(TARGET_SKILL)
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    changed = sorted(
        name
        for name in expected.keys() & actual.keys()
        if expected[name] != actual[name]
    )
    lock_matches = LOCK_PATH.is_file() and LOCK_PATH.read_bytes() == lock
    if missing or extra or changed or not lock_matches:
        details = []
        if missing:
            details.append(f"missing={missing}")
        if extra:
            details.append(f"extra={extra}")
        if changed:
            details.append(f"changed={changed}")
        if not lock_matches:
            details.append("lockfile=stale-or-missing")
        raise SyncError(
            "materialized medical-image skill is stale ("
            + "; ".join(details)
            + "); run scripts/sync-medical-image-harness.py --write"
        )


def _write(expected: dict[str, bytes], lock: bytes) -> None:
    if TARGET_SKILL.is_symlink():
        raise SyncError(f"skill target must not be a symlink: {TARGET_SKILL}")
    if TARGET_SKILL.exists():
        shutil.rmtree(TARGET_SKILL)
    for relative, content in expected.items():
        destination = TARGET_SKILL / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_bytes(lock)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        commit = _validated_submodule_commit()
        source_files = _file_map(SOURCE_SKILL)
        if not source_files:
            raise SyncError("canonical public skill tree is empty")
        expected = _adapter_files(source_files)
        lock = _lock_bytes(commit, source_files, expected)
        if args.check:
            _check(expected, lock)
            print(f"medical-image skill is synchronized at {commit}")
        else:
            _write(expected, lock)
            print(f"materialized medical-image skill from {commit}")
    except SyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
