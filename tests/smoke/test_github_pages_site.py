from __future__ import annotations

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


def test_pages_site_reports_live_failure_evidence_without_broken_private_cta() -> None:
    index = (SITE_ROOT / "index.html").read_text(encoding="utf-8")

    for evidence in (
        "GPT-5.6 Luna",
        "146.9 s",
        "111,833",
        "0.10–0.37 px",
        "Accuracy miss recorded",
        "9,922 canonical MEETI images",
    ):
        assert evidence in index
    assert "github.com/u9401066/dicom-overlay-agent" not in index


def test_pages_public_setup_uses_real_subscription_and_harness_commands() -> None:
    docs = (SITE_ROOT / "docs.html").read_text(encoding="utf-8")

    assert "uv sync --all-extras" in docs
    assert "codex login" in docs
    assert "openai/gpt-5.6-luna" in docs
    assert "DICOMOverlayAgent.exe --selfcheck" in docs
    assert "run-image-harness-smoke.py" in docs
    assert "OpenClaw owns every image-analysis turn" in docs


def test_pages_workflow_uses_current_official_action_majors() -> None:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pages.yml").read_text("utf-8")
    )
    steps = workflow["jobs"]["deploy"]["steps"]
    uses = {step["uses"] for step in steps if "uses" in step}

    assert uses == {
        "actions/checkout@v7",
        "actions/configure-pages@v6",
        "actions/upload-pages-artifact@v5",
        "actions/deploy-pages@v5",
    }
