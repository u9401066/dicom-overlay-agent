from __future__ import annotations

from pathlib import Path


def test_cxr_skill_does_not_make_all_mediastinal_widening_critical() -> None:
    skill = Path("openclaw/workspace/skills/dicom-cxr-analysis/SKILL.md").read_text(
        encoding="utf-8"
    )
    critical_section = skill.split(
        "Can't-miss diagnoses (escalate severity to critical and state explicitly):",
        maxsplit=1,
    )[1].split("Widened-mediastinum severity contract:", maxsplit=1)[0]

    assert "mediastinal widening or suspicion warrants at least warning" in skill
    assert "widening alone is not sufficient" in skill
    assert "time-critical acute aortic syndrome" in skill
    assert "Pneumomediastinum is a can't-miss" in skill
    assert "Pneumomediastinum and a widened mediastinum are can't-miss" not in skill
    assert "widened mediastinum" not in critical_section.lower()
