from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_materialized_medical_image_skill_matches_pinned_submodule() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "sync-medical-image-harness.py"),
            "--check",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "is synchronized" in result.stdout

    target = repo_root / ".agents" / "skills" / "medical-image-reading"
    assert [
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file()
    ] == ["SKILL.md"]
    adapter = (target / "SKILL.md").read_text(encoding="utf-8")
    assert "pinned adapter" in adapter
    assert (
        "third_party/medical-image-agent-harness/.agents/skills/medical-image-reading/SKILL.md"
        in adapter
    )

    lock = json.loads(
        (repo_root / ".agents" / "medical-image-harness.lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert lock["generator_version"] == 2
    assert set(lock["generated_files"]) == {"SKILL.md"}
    assert "references/core-protocol.md" in lock["source_files"]
