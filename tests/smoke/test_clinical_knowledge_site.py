"""Exercise the actual YAML -> SQLite parity -> public catalogue build boundary."""

from __future__ import annotations

import importlib.util
from html import escape
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _site_builder():
    spec = importlib.util.spec_from_file_location(
        "clinical_site", ROOT / "scripts/build-clinical-knowledge-site.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_registry_build_contains_every_rule_and_both_step_sets(tmp_path):
    site = _site_builder()
    output = tmp_path / "clinical-rules.html"
    digest = site.build_site(output)
    rendered = output.read_text("utf-8")
    registry = site.load_builder()._load_validator().load_registry()
    assert digest in rendered
    assert "{{" not in rendered
    assert rendered.count('class="clinical-rule"') == len(registry["rules"])
    for rule in registry["rules"]:
        assert f'id="{rule["rule_id"]}"' in rendered
        for step in rule["human"]["workflow"]:
            assert escape(step["detail"]) in rendered
        for step in rule["agent"]["steps"]:
            assert escape(step["instruction"]) in rendered
    assert output.read_text("utf-8") == (ROOT / "site/clinical-rules.html").read_text(
        "utf-8"
    )


def test_failed_sqlite_parity_does_not_replace_existing_page(tmp_path, monkeypatch):
    site = _site_builder()
    builder = site.load_builder()
    monkeypatch.setattr(
        builder, "verify_quick_lookup_db", lambda *a, **kw: ["row mismatch"]
    )
    monkeypatch.setattr(site, "load_builder", lambda: builder)
    output = tmp_path / "existing.html"
    output.write_text("previous published page", encoding="utf-8")
    with pytest.raises(ValueError, match="row mismatch"):
        site.build_site(output)
    assert output.read_text("utf-8") == "previous published page"


def test_rule_render_treats_editor_content_as_text_not_html():
    site = _site_builder()
    rule = site.load_builder()._load_validator().load_registry()["rules"][0]
    rule["human"]["title"] = '<script>alert("unsafe")</script>'
    rendered = site.render_rule(rule, "rules/core.rule.yaml")
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "/edit/main/clinical_knowledge/rules/core.rule.yaml" in rendered
