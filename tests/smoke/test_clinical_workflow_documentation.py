"""Documentation consistency only; not clinical or runtime acceptance."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs/clinical/ekg-reading-workflow.md"
AXES = ROOT / "clinical_knowledge/axes/ekg.axes.yaml"


def validate_document(text, axes):
    human = re.findall(r"^### \d{2} ([a-z_]+) —", text, re.MULTILINE)
    agent_text = text.split("## Agent 精簡步驟\n", 1)[1].split("\n## ", 1)[0]
    agent = re.findall(r"^\| `([a-z_]+)` \|", agent_text, re.MULTILINE)
    assert len(human) == 10 and len(set(human)) == 10
    assert agent == human, "Human and agent step IDs/order differ"
    axis_text = text.split("## 十六軸覆蓋對照\n", 1)[1].split("\n## ", 1)[0]
    axis_rows = re.findall(
        r"^\| `([a-z_]+)` \| ([a-z_]+) \| (.+) \|$", axis_text, re.MULTILINE
    )
    assert Counter(row[0] for row in axis_rows) == Counter(axes), (
        "Axis inventory differs"
    )
    assert all(row[1] in human and row[2].strip() for row in axis_rows)
    assert "尚未完整接入 runtime" in text
    assert "不驗證臨床正確性、引用授權或 runtime 已執行本流程" in text


def inputs():
    text = DOCUMENT.read_text(encoding="utf-8")
    axes = yaml.safe_load(AXES.read_text(encoding="utf-8"))["axes"]
    return text, axes


def test_workflow_has_ordered_human_agent_parity_and_all_canonical_axes():
    validate_document(*inputs())


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_axis",
        "duplicate_axis",
        "wrong_step",
        "agent_order",
        "missing_human",
        "false_runtime_claim",
        "removed_limit",
    ],
)
def test_documentation_guard_detects_drift(mutation):
    text, axes = inputs()
    if mutation == "missing_axis":
        text = re.sub(r"^\| `heart_rate`.*\n", "", text, flags=re.MULTILINE)
    elif mutation == "duplicate_axis":
        text = text.replace("| `qtc_interval` |", "| `heart_rate` |")
    elif mutation == "wrong_step":
        text = text.replace("| `heart_rate` | rhythm |", "| `heart_rate` | unknown |")
    elif mutation == "agent_order":
        text = text.replace("| `intake` | Bind", "| `quality` | Bind")
    elif mutation == "missing_human":
        text = text.replace("### 01 intake —", "### Missing —")
    elif mutation == "false_runtime_claim":
        text = text.replace("尚未完整接入 runtime", "已完成")
    else:
        text = text.replace("不驗證臨床正確性、引用授權或 runtime 已執行本流程", "")
    with pytest.raises(AssertionError):
        validate_document(text, axes)
