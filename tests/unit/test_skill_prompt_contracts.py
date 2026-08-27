from __future__ import annotations

from pathlib import Path


def test_ekg_skill_keeps_meeti_waveform_reading_contract() -> None:
    skill = Path("openclaw/workspace/skills/dicom-ekg-analysis/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "10-second rhythm strip" in skill
    assert "Assess voltage in both directions" in skill
    assert "low-voltage criteria with high-voltage" in skill
    assert "Deep S in V1/V2" in skill
    assert "Do not let voltage assessment displace Q/QS morphology" in skill
    assert "Irregular R-R timing alone cannot diagnose atrial fibrillation" in skill
    assert "Regular R-R timing alone cannot diagnose sinus rhythm" in skill
    assert "stable P-QRS" in skill
    assert "otherwise normal ECG` label is not negative evidence" in skill
    assert "omission from a top-k list is not evidence of absence" in skill
    assert "ischemia` to `st_depression` or `t_wave_changes`" in skill
    assert "overall severity at least `warning`" in skill
    assert "unrounded `heart_rate_bpm_from_median_rr`" in skill
    assert "Three or more consecutive broad QRS complexes" in skill
    assert "NSVT/VT-versus-artifact" in skill
    assert 'format: "12lead_12x1"' in skill
    assert "Do not invent a 3x4 layout for a 12-row image" in skill
    assert '"model_used": "unknown"' in skill
    assert "openai/gpt-5.4-mini" not in skill
    assert "openai/gpt-5.6-luna" not in skill
