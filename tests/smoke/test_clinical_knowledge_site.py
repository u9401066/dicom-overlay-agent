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
    assert rendered.count('class="reading-stage"') == 5
    for stage in registry["reading_contract"]["stages"]:
        assert f'id="stage-{stage["id"]}"' in rendered
        for step in stage["steps"]:
            assert escape(step["human"]) in rendered
            assert escape(step["agent"]) in rendered
    for focus in registry["reading_contract"]["quality_focus"].values():
        assert escape(focus["human"]) in rendered
        assert escape(focus["agent"]) in rendered
    assert "/edit/" not in rendered  # Unattributed local preview has no edit target.
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
    rendered = site.render_rule(
        rule, "rules/core.rule.yaml", "a" * 40, "agent/candidate"
    )
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "/edit/agent%2Fcandidate/clinical_knowledge/rules/core.rule.yaml" in rendered
    assert f"/blob/{'a' * 40}/clinical_knowledge/rules/core.rule.yaml" in rendered


def test_published_build_binds_workflow_rule_and_governance_links(tmp_path):
    site = _site_builder()
    output = tmp_path / "published.html"
    site.build_site(output, source_ref="b" * 40, edit_ref="agent/candidate")
    rendered = output.read_text("utf-8")
    for path in (
        "rules/core.rule.yaml",
        "workflows/reading.workflow.yaml",
        "README.md",
    ):
        assert f"/blob/{'b' * 40}/clinical_knowledge/{path}" in rendered
        assert f"/edit/agent%2Fcandidate/clinical_knowledge/{path}" in rendered
    assert f'<code id="source-ref">{"b" * 40}</code>' in rendered
    before = output.read_bytes()
    with pytest.raises(ValueError, match="Invalid Git"):
        site.build_site(output, source_ref='main" onclick="unsafe')
    assert output.read_bytes() == before


def test_workflow_editor_content_is_escaped():
    site = _site_builder()
    contract = site.load_builder()._load_validator().load_registry()["reading_contract"]
    contract["stages"][0]["steps"][0]["human"] = '<img src=x onerror="unsafe">'
    rendered = site.render_reading_contract(contract, None, None)
    assert "<img" not in rendered
    assert "&lt;img" in rendered
