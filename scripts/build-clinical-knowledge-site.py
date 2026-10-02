"""Generate the public clinical catalogue from validated YAML and SQLite parity."""

from __future__ import annotations

import argparse
import importlib.util
import json
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


def render_rule(rule: dict[str, Any], source_path: str) -> str:
    human = rule["human"]
    rule_id = text(rule["rule_id"])
    source = quote("clinical_knowledge/" + source_path, safe="/")
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
<p class="rule-actions"><a href="{REPOSITORY}/blob/main/{source}">檢視 canonical YAML</a>
<a href="{REPOSITORY}/edit/main/{source}">在 GitHub 網頁編輯此來源檔</a></p>
</article>'''


def build_site(output: Path) -> str:
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
        render_rule(rule, source_by_id[rule["rule_id"]]) for rule in rules
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
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8", newline="\n")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "site/clinical-rules.html"
    )
    args = parser.parse_args()
    try:
        digest = build_site(args.output)
    except (OSError, ValueError) as exc:
        print(f"Clinical site build FAILED: {exc}")
        return 1
    print(f"Clinical site built; YAML/generated views/SQLite parity OK: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
