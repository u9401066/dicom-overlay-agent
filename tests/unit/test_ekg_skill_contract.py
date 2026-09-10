from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parents[2]
    / "openclaw"
    / "workspace"
    / "skills"
    / "dicom-ekg-analysis"
    / "SKILL.md"
)


def test_ekg_skill_distinguishes_unique_wide_beats_and_intermediate_differential() -> (
    None
):
    skill = SKILL_PATH.read_text(encoding="utf-8")
    prose = " ".join(skill.split())

    assert "Count unique horizontal timestamps" in prose
    assert "same simultaneous beat" in prose
    assert "at least three consecutive broad beats" in prose
    assert "One or two abnormal broad beats" in prose
    assert "demand pacing, PVC, aberrant conduction, fusion, and artifact" in prose
    assert "normal intrinsic beats do not exclude demand/intermittent pacing" in prose
    assert "pacing-spike" in prose


def test_ekg_skill_bbox_contract_matches_runtime_limits() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "`w <= 0.35`, `h <= 0.30`, and `w*h <= 0.08`" in skill
    assert "never use a full-height time band or full-width lead row" in skill
