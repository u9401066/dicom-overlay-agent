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


def _parse_site() -> _SiteParser:
    parser = _SiteParser()
    parser.feed((SITE_ROOT / "index.html").read_text(encoding="utf-8"))
    return parser


def test_pages_site_has_one_literal_product_h1_and_required_sections() -> None:
    parser = _parse_site()

    assert parser.h1_text == ["DICOM Overlay Agent"]
    assert {"overview", "workflow", "evidence", "safety"} <= parser.section_ids


def test_pages_site_local_references_exist() -> None:
    parser = _parse_site()
    missing: list[str] = []
    for reference in parser.references:
        parsed = urlparse(reference)
        if parsed.scheme or parsed.netloc or reference.startswith("#"):
            continue
        path = SITE_ROOT / parsed.path
        if not path.is_file():
            missing.append(reference)

    assert missing == []
    assert (SITE_ROOT / ".nojekyll").is_file()


def test_pages_site_uses_only_synthetic_ecg_media() -> None:
    parser = _parse_site()
    image_references = [item for item in parser.references if item.endswith(".png")]

    assert set(image_references) == {"assets/synthetic-ecg.png"}
    assert (SITE_ROOT / "assets" / "synthetic-ecg.png").stat().st_size > 1_000


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
