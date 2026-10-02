"""Generate the public clinical catalogue from validated YAML and SQLite parity."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import tempfile
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/u9401066/dicom-overlay-agent"


def load_builder() -> Any:
    path = ROOT / "scripts/build-clinical-knowledge-sqlite.py"
    spec = importlib.util.spec_from_file_location("clinical_site_sqlite", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def text(value: object) -> str:
    return escape(str(value), quote=True)


def items(values: list[Any]) -> str:
    return "<ul>" + "".join(f"<li>{text(value)}</li>" for value in values) + "</ul>"


def steps(values: list[dict[str, Any]], field: str) -> str:
    return (
        "<ol>"
        + "".join(
            f"<li><code>{text(step['id'])}</code><p>{text(step[field])}</p></li>"
            for step in values
        )
        + "</ol>"
    )


def source_links(path: str, source_ref: str | None, edit_ref: str | None) -> str:
    encoded_path = quote("clinical_knowledge/" + path, safe="/")
    links = [f"<code>clinical_knowledge/{text(path)}</code>"]
    for ref, action, label in (
        (source_ref, "blob", "檢視本次建置來源"),
        (edit_ref, "edit", "在 GitHub 網頁編輯此來源檔"),
    ):
        if ref is not None:
            if (
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", ref)
                or ".." in ref
            ):
                raise ValueError("Invalid Git source/edit reference")
            links.append(
                f'<a href="{REPOSITORY}/{action}/{quote(ref, safe="")}/{encoded_path}">{label}</a>'
            )
    return '<p class="rule-actions">' + " ".join(links) + "</p>"


def render_reading_contract(
    contract: dict[str, Any], source_ref: str | None, edit_ref: str | None
) -> str:
    cards = []
    for index, stage in enumerate(contract["stages"], 1):
        pairs = "".join(
            f'<li><code>{text(step["id"])}</code><div class="reading-step-pair">'
            f"<div><h4>人用說明</h4><p>{text(step['human'])}</p></div>"
            f'<div><h4>Agent 實際指令</h4><p lang="en">{text(step["agent"])}</p></div>'
            "</div></li>"
            for step in stage["steps"]
        )
        cards.append(
            f'<details class="reading-stage" id="stage-{text(stage["id"])}">'
            f"<summary>{index:02d} · {text(stage['human_title'])} <code>{text(stage['id'])}</code></summary>"
            f"<ol>{pairs}</ol></details>"
        )
    focuses = "".join(
        f"<div><h3>{text(modality)}</h3><p>{text(focus['human'])}</p>"
        f'<p lang="en">{text(focus["agent"])}</p></div>'
        for modality, focus in contract["quality_focus"].items()
    )
    raw = json.dumps(contract, ensure_ascii=False, indent=2)
    return (
        f'<p>Contract version：<code id="reading-version">{text(contract["contract_version"])}</code>'
        f" · scope：<code>{text(contract['scope'])}</code></p>"
        + "".join(cards)
        + f'<details class="reading-focus"><summary>三種模態的品質檢查重點</summary>{focuses}</details>'
        + f'<details class="reading-raw"><summary>完整結構化判讀 contract</summary><pre>{text(raw)}</pre></details>'
        + source_links("workflows/reading.workflow.yaml", source_ref, edit_ref)
    )


def render_rule(
    rule: dict[str, Any],
    source_path: str,
    source_ref: str | None = None,
    edit_ref: str | None = None,
) -> str:
    human = rule["human"]
    rule_id = text(rule["rule_id"])
    sources = []
    for citation in human["sources"]:
        url = str(citation["url"])
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Clinical source must be an absolute HTTPS URL")
        sources.append(
            f'<li><a href="{text(url)}" rel="noreferrer">{text(citation["title"])}</a>'
            f" — {text(citation['authority'])} · {text(citation['version'])}"
            f" · {text(citation['effective_date'])}<p>{text(citation['locator'])}</p></li>"
        )
    # JSON is displayed as escaped text, never executable HTML or inline script.
    raw = json.dumps(rule, ensure_ascii=False, indent=2, default=str)
    return f'''<article class="clinical-rule" id="{rule_id}" data-modality="{text(rule["modality"])}">
<header><p class="rule-meta">{text(rule["modality"])} · {text(rule["status"])} · v{text(rule["version"])}</p>
<h2>{text(human["title"])}</h2><code>{rule_id}</code></header>
<p>{text(human["rationale"])}</p>
<p>來源登錄複核日：{text(human["reviewed_on"])}；下次複核期限：{text(human["review_due"])}</p>
<details><summary>完整人用判讀與鑑別步驟</summary>{steps(human["workflow"], "detail")}</details>
<details><summary>Agent 精簡執行步驟（相同 step ID）</summary>{steps(rule["agent"]["steps"], "instruction")}</details>
<details><summary>適用條件、證據與排除條件</summary>
<h3>適用條件</h3>{items(rule["preconditions"])}<h3>所需證據</h3>{items(rule["evidence"])}
<h3>排除條件</h3>{items(rule["exclusions"])}</details>
<details><summary>引用來源與定位</summary><ul>{"".join(sources)}</ul></details>
<details><summary>完整結構化規則（含 priority、runtime、tests、legacy）</summary><pre>{text(raw)}</pre></details>
{source_links(source_path, source_ref, edit_ref)}
</article>'''


def build_site(
    output: Path, *, source_ref: str | None = None, edit_ref: str | None = None
) -> str:
    if edit_ref and not source_ref:
        raise ValueError("An edit reference requires an attributed source reference")
    builder = load_builder()
    validator = builder._load_validator()
    registry = validator.load_registry()
    errors = validator.validate_registry(registry)
    if not errors:
        errors.extend(validator.write_or_check_views(registry, check=True))
    if errors:
        raise ValueError("\n".join(errors))
    digest = validator.registry_digest(registry)
    # Verify every table, column and row, not just a self-reported DB digest.
    with tempfile.TemporaryDirectory(prefix="clinical-site-") as directory:
        database = Path(directory) / "clinical-knowledge.sqlite"
        builder.build_quick_lookup_db(registry, database, registry_digest=digest)
        errors = builder.verify_quick_lookup_db(
            registry, database, registry_digest=digest
        )
        if errors:
            raise ValueError("\n".join(errors))
    source_by_id = {
        rule["rule_id"]: document["path"]
        for document in registry["rule_documents"]
        for rule in document["document"]["rules"]
    }
    rules = sorted(registry["rules"], key=lambda rule: rule["rule_id"])
    cards = "\n".join(
        render_rule(rule, source_by_id[rule["rule_id"]], source_ref, edit_ref)
        for rule in rules
    )
    toc = "".join(
        f'<li><a href="#{text(rule["rule_id"])}">{text(rule["human"]["title"])}</a></li>'
        for rule in rules
    )
    template = (ROOT / "site/clinical-rules.template.html").read_text(encoding="utf-8")
    page = (
        template.replace("{{DIGEST}}", digest)
        .replace("{{COUNT}}", str(len(rules)))
        .replace("{{SCOPE}}", text(validator.REGISTRY_DIGEST_SCOPE))
        .replace("{{TOC}}", toc)
        .replace("{{RULES}}", cards)
        .replace(
            "{{READING_CONTRACT}}",
            render_reading_contract(registry["reading_contract"], source_ref, edit_ref),
        )
        .replace("{{DB_VERSION}}", text(builder.DB_SCHEMA_VERSION))
        .replace("{{GOVERNANCE_LINK}}", source_links("README.md", source_ref, edit_ref))
        .replace(
            "{{SOURCE_RECEIPT}}",
            (
                f'網站建置來源：<code id="source-ref">{text(source_ref)}</code>。此頁描述來源候選，並非已發布 EXE。'
                if source_ref
                else "本機預覽：未指定 Git 建置來源，編輯連結停用；下方 digest 對應目前工作目錄。"
            ),
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8", newline="\n")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "site/clinical-rules.html"
    )
    parser.add_argument("--source-ref", help="Exact Git revision used for this build")
    parser.add_argument("--edit-ref", help="Branch to open for manual YAML editing")
    args = parser.parse_args()
    try:
        digest = build_site(
            args.output, source_ref=args.source_ref, edit_ref=args.edit_ref
        )
    except (OSError, ValueError) as exc:
        print(f"Clinical site build FAILED: {exc}")
        return 1
    print(f"Clinical site built; YAML/generated views/SQLite parity OK: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
