"""Keep reorganized docs and the Pages links tied to real repository paths."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
REPO_URL = "https://github.com/u9401066/dicom-overlay-agent/blob/main/"


def _target(source: Path, reference: str) -> Path | None:
    reference = reference.strip("<>")
    if reference.startswith(REPO_URL):
        return ROOT / unquote(urlsplit(reference[len(REPO_URL) :]).path)
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    return (source.parent / unquote(parsed.path)).resolve()


def test_maintained_and_archived_markdown_links_exist() -> None:
    paths = [
        *ROOT.glob("*.md"),
        *(ROOT / "docs").rglob("*.md"),
        ROOT / "openclaw/README.md",
        ROOT / "clinical_knowledge/README.md",
    ]
    missing = []
    for path in paths:
        text = re.sub(r"(?ms)^```.*?^```[^\n]*$", "", path.read_text("utf-8"))
        for reference in re.findall(r"\]\((<[^>]+>|[^\s)]+)", text):
            target = _target(path, reference)
            if target is not None and (not target.is_relative_to(ROOT) or not target.exists()):
                missing.append(f"{path.relative_to(ROOT)}: {reference}")
    assert missing == []


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key == "href" and value and value.startswith(REPO_URL):
                self.references.append(value)


def test_pages_links_into_this_repository_exist() -> None:
    missing = []
    for path in (ROOT / "site").glob("*.html"):
        parser = _Links()
        parser.feed(path.read_text("utf-8"))
        for reference in parser.references:
            target = _target(path, reference)
            if target is None or not target.is_relative_to(ROOT) or not target.exists():
                missing.append(f"{path.name}: {reference}")
    assert missing == []


def test_dated_records_are_archived_and_entry_points_exist() -> None:
    assert not list((ROOT / "docs").glob("*-20??-??-??.md"))
    for relative in (
        "docs/README.md",
        "docs/architecture/components.md",
        "docs/architecture/overview.md",
        "docs/architecture/specification.md",
        "docs/operations/real-desktop-tests.md",
        "docs/evaluation/cohorts.md",
        "docs/integrations/ecgfounder-tool.md",
        "openclaw/README.md",
    ):
        assert (ROOT / relative).is_file(), relative
    for removed in ("ARCHITECTURE.md", "spec.md", "REAL_TEST_RUNBOOK.md"):
        assert not (ROOT / removed).exists(), "Do not restore compatibility copies"


def test_link_resolution_preserves_external_and_encoded_targets() -> None:
    source = ROOT / "docs/README.md"
    assert _target(source, "#archive-policy") is None
    assert _target(source, "https://example.org/manual.md") is None
    assert _target(source, "mailto:example@example.org") is None
    assert _target(source, "<../README.zh-TW.md#test>") == ROOT / "README.zh-TW.md"
    assert _target(source, "a%20b.md") == ROOT / "docs/a b.md"
    assert _target(source, REPO_URL + "docs/README.md#test") == source
