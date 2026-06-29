from __future__ import annotations

from pathlib import Path


def test_ekg_skill_keeps_meeti_waveform_reading_contract() -> None:
    skill = Path("openclaw/workspace/skills/dicom-ekg-analysis/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "10-second rhythm strip" in skill
    assert "S in V1/V2 + R in V5/V6" in skill
    assert "ischemia` to `st_depression` or `t_wave_changes`" in skill
    assert "overall severity at least `warning`" in skill
