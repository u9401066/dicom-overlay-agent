from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE_ROOT = REPO_ROOT / "site"


class _SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self.section_ids: set[str] = set()
        self.h1_text: list[str] = []
        self._in_h1 = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        if tag in {"a", "link"} and values.get("href"):
            self.references.append(values["href"] or "")
        if tag in {"img", "script"} and values.get("src"):
            self.references.append(values["src"] or "")
        if tag == "section" and values.get("id"):
            self.section_ids.add(values["id"] or "")
        if tag == "h1":
            self._in_h1 = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self._in_h1 = False

    def handle_data(self, data: str) -> None:
        if self._in_h1 and data.strip():
            self.h1_text.append(data.strip())


def _parse_site(filename: str = "index.html") -> _SiteParser:
    parser = _SiteParser()
    parser.feed((SITE_ROOT / filename).read_text(encoding="utf-8"))
    return parser


def test_pages_site_has_one_literal_product_h1_and_required_sections() -> None:
    parser = _parse_site()

    assert parser.h1_text == ["Co-reading that stays accountable to the image."]
    assert {"overview", "workflow", "evidence", "safety", "install"} <= (
        parser.section_ids
    )


def test_pages_site_local_references_exist() -> None:
    missing: list[str] = []
    for filename in ("index.html", "docs.html"):
        parser = _parse_site(filename)
        for reference in parser.references:
            parsed = urlparse(reference)
            if parsed.scheme or parsed.netloc or reference.startswith("#"):
                continue
            path = SITE_ROOT / parsed.path
            if not path.is_file():
                missing.append(f"{filename}: {reference}")

    assert missing == []
    assert (SITE_ROOT / ".nojekyll").is_file()


def test_pages_site_uses_only_synthetic_ecg_media() -> None:
    image_references = [
        item
        for filename in ("index.html", "docs.html")
        for item in _parse_site(filename).references
        if item.endswith(".png")
    ]

    assert set(image_references) == {"assets/synthetic-ecg.png"}
    assert (SITE_ROOT / "assets" / "synthetic-ecg.png").stat().st_size > 1_000


def test_pages_site_separates_historical_and_current_failure_evidence() -> None:
    index = (SITE_ROOT / "index.html").read_text(encoding="utf-8")

    for evidence in (
        "GPT-5.6 Luna",
        "GPT-6 Astra low",
        "2 distinct Astra cases",
        "desktop-20260910-102218-658881",
        "140.481 s",
        "desktop-20260910-095926-407907",
        "165.043 s",
        "desktop-20260910-094636-035106",
        "179.252 s",
        "103 attempts · 60 exports · 43 timeouts",
        "2026-08-27",
        "historical baseline",
        "146.915 s",
        "111,833",
        "0.10–0.37 px",
        "desktop-20260902-082210-259256",
        "139.407 s · 74,786 total tokens",
        "desktop-20260902-090424-024627",
        "61.673 s · 37,811 total tokens",
        "desktop-20260902-092532-259033",
        "153.398 s · 87,694 total tokens",
        "No new accuracy pass",
        "missed critical reference findings",
    ):
        assert evidence in index


def test_pages_site_labels_frozen_mock_and_governance_status_truthfully() -> None:
    index = (SITE_ROOT / "index.html").read_text(encoding="utf-8")

    for evidence in (
        "128 important multi-diagnosis cases",
        "Frozen from 9,922 canonical MEETI images · full Astra cohort pending",
        "Mock plumbing only",
        "This is not a clinical pass.",
        "Canonical 7-rule registry",
        "OpenClaw 2.x candidate",
        "Candidate under verification",
        "stays pinned to 2026.7.1-2",
        "Latest candidate 2026.9.3",
        "fabricated OAuth migration checks",
    ):
        assert evidence in index


def test_pages_separates_candidate_contract_checks_from_release_evidence() -> None:
    docs = (SITE_ROOT / "docs.html").read_text(encoding="utf-8")
    assert "including\n                the App's own auth helper" in docs
    assert "do not prove real subscription authentication or clinical accuracy" in docs
    assert "No candidate binary is released" in docs


def test_pages_site_reports_public_repository_and_absent_release() -> None:
    pages = "\n".join(
        (SITE_ROOT / filename).read_text(encoding="utf-8")
        for filename in ("index.html", "docs.html")
    )

    assert "https://github.com/u9401066/dicom-overlay-agent" in pages
    assert "No GitHub Release is published as of 2026-09-10" in pages
    assert "repository is private" not in pages


def test_pages_public_setup_uses_real_subscription_and_harness_commands() -> None:
    docs = (SITE_ROOT / "docs.html").read_text(encoding="utf-8")

    assert "uv sync --all-extras" in docs
    assert "codex login" in docs
    assert "OpenAI GPT-6 Astra via Codex Subscription" in docs
    assert "openai/gpt-6-astra" in docs
    assert "thinking=low" in docs
    assert "openai-chatgpt-responses" in docs
    assert "DICOMOverlayAgent.exe --selfcheck" in docs
    assert "run-image-harness-smoke.py" in docs
    assert "OpenClaw owns every image-analysis turn" in docs
    assert "openclaw-upgrade-audit-2026-09-10.md" in docs
    assert "These checks made no paid model requests" in docs


def test_pages_docs_explain_canonical_rules_sqlite_and_package_status() -> None:
    docs = (SITE_ROOT / "docs.html").read_text(encoding="utf-8")

    for evidence in (
        "Seven deterministic consistency rules",
        "canonical YAML",
        "human-catalogue.md + agent-steps.md",
        "clinical-knowledge.sqlite",
        "validate-clinical-knowledge.py --check-generated",
        "build-clinical-knowledge-sqlite.py",
        "Professional-output contract",
        "Historical actual · 2026-08-09",
        "7.05 MiB launcher",
        "94.74 MiB app + Python/Qt",
        "368.01 MiB full zero-install bundle",
        "Pending release gate",
        "OpenClaw 2.x upgrade status: isolated candidate validation.",
    ):
        assert evidence in docs


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def test_pages_focus_media_and_synthetic_mockup_are_accessible() -> None:
    index = (SITE_ROOT / "index.html").read_text(encoding="utf-8")
    styles = (SITE_ROOT / "styles.css").read_text(encoding="utf-8")
    match = re.search(r"--focus-ring:\s*(#[0-9a-fA-F]{6})", styles)

    assert match is not None
    dark = _relative_luminance(match.group(1))
    white = _relative_luminance("#ffffff")
    assert (white + 0.05) / (dark + 0.05) >= 3
    assert "outline: 3px solid var(--focus-ring)" in styles
    assert "box-shadow: 0 0 0 6px #ffffff" in styles
    assert re.search(r"\.ecg-canvas img\s*\{[^}]*object-fit: contain", styles, re.S)
    assert "Synthetic UI mockup." in index
    assert "not a patient image or a successful" in index


def test_mobile_menu_is_progressive_and_keyboard_dismissible() -> None:
    index = (SITE_ROOT / "index.html").read_text(encoding="utf-8")
    script = (SITE_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (SITE_ROOT / "styles.css").read_text(encoding="utf-8")

    assert '<nav id="site-navigation" class="site-navigation"' in index
    assert "document.documentElement.classList.add(\"js\")" in script
    assert ".js .site-navigation" in styles
    assert ".js .site-navigation.is-open" in styles
    assert 'event.key === "Escape"' in script
    assert "menuButton.focus()" in script
    assert 'addEventListener("pointerdown"' in script
    assert 'matchMedia("(max-width: 760px)")' in script
    assert 'addEventListener("change", closeAtDesktopWidth)' in script


def test_pages_workflow_uses_current_official_action_majors() -> None:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pages.yml").read_text("utf-8")
    )
    steps = workflow["jobs"]["deploy"]["steps"]
    uses = {step["uses"] for step in steps if "uses" in step}

    assert uses == {
        "actions/checkout@v7",
        "actions/setup-python@v6",
        "astral-sh/setup-uv@v7",
        "actions/configure-pages@v6",
        "actions/upload-pages-artifact@v5",
        "actions/deploy-pages@v5",
    }

    commands = [step.get("run", "") for step in steps]
    validation_index = next(
        index for index, step in enumerate(steps) if step.get("name") == "Validate Pages source"
    )
    upload_index = next(
        index for index, step in enumerate(steps) if step.get("name") == "Upload site"
    )

    assert any(
        "uv run --frozen python -m pytest -q tests/smoke/test_github_pages_site.py"
        in command
        for command in commands
    )
    assert validation_index < upload_index
    assert "-p no:pytest-qt" in steps[validation_index]["run"]
