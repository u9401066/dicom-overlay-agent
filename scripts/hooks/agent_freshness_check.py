"""Agent Freshness Check — 檢查 Custom Agent 檔案中的模型和工具是否過時。

檢查項目：
1. model 是否使用已退役的模型
2. tools 中是否有已廢棄的工具名稱
3. agent 檔案是否超過 90 天未更新
4. agents + tools 搭配是否正確（需要 agent tool）
5. subagent 引用是否存在
"""

from __future__ import annotations

import re
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = PROJECT_ROOT / ".github" / "agents"
STALE_DAYS = 90

# ============================================================
# 已退役模型清單（根據 GitHub Copilot 官方文件）
# 新模型上線或舊模型退役時，更新此清單
# 最後更新: 2026-03-06
# ============================================================
RETIRED_MODELS: dict[str, str] = {
    "Claude Opus 4": "Claude Opus 4.6",
    "Claude Opus 4.1": "Claude Opus 4.6",
    "Claude Opus 4.5": "Claude Opus 4.6",
    "Claude Sonnet 3.5": "Claude Haiku 4.5",
    "Claude Sonnet 3.7": "Claude Sonnet 4.6",
    "Claude Sonnet 3.7 Thinking": "Claude Sonnet 4.6",
    "Claude Sonnet 4": "Claude Sonnet 4.6",
    "Claude Sonnet 4.5": "Claude Sonnet 4.6",
    "GPT-4o": "GPT-4.1",
    "GPT-5": "GPT-5.4",
    "GPT-5-Codex": "GPT-5.2-Codex",
    "GPT-5.1": "GPT-5.4",
    "GPT-5.2": "GPT-5.4",
    "o1-mini": "GPT-5 mini",
    "o3": "GPT-5.4",
    "o3-mini": "GPT-5 mini",
    "o4-mini": "GPT-5 mini",
    "Gemini 2.0 Flash": "Gemini 2.5 Pro",
    "Gemini 2.5 Pro": "Gemini 3.1 Pro",
}

# 已廢棄的 tools
DEPRECATED_TOOLS: dict[str, str] = {
    "findTestFiles": "search",
    "githubRepo": "fetch",
    "openSimpleBrowser": "fetch",
    "searchResults": "search",
    "updateMemoryBank": "updateProgress + updateContext",
}


def parse_frontmatter(content: str) -> dict[str, str]:
    """簡單解析 YAML frontmatter，回傳原始文字區塊。"""
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    return {"raw": match.group(1)}


def extract_models(raw_frontmatter: str) -> list[str]:
    """從 frontmatter 中提取 model 欄位的值。"""
    models = []
    in_model = False
    for line in raw_frontmatter.split("\n"):
        stripped = line.strip()
        if stripped.startswith("model:"):
            value = stripped[len("model:"):].strip()
            if value and not value.startswith("-"):
                # 單一 model（字串值）
                models.append(value.strip('"').strip("'"))
            in_model = True
            continue
        if in_model:
            if stripped.startswith("- "):
                model_name = stripped[2:].strip().strip('"').strip("'")
                models.append(model_name)
            elif stripped and not stripped.startswith("#"):
                in_model = False
    return models


def extract_tools(raw_frontmatter: str) -> list[str]:
    """從 frontmatter 中提取 tools 欄位的值。"""
    match = re.search(r"tools:\s*\[([^\]]*)\]", raw_frontmatter)
    if match:
        raw = match.group(1)
        return [t.strip().strip("'\"") for t in raw.split(",") if t.strip()]
    return []


def extract_agents_field(raw_frontmatter: str) -> list[str]:
    """從 frontmatter 中提取 agents 欄位的值。"""
    # 陣列格式 agents: ['*'] 或 agents: ['a', 'b']
    match = re.search(r"agents:\s*\[([^\]]*)\]", raw_frontmatter)
    if match:
        raw = match.group(1)
        return [a.strip().strip("'\"") for a in raw.split(",") if a.strip()]
    # 列表格式
    agents = []
    in_agents = False
    for line in raw_frontmatter.split("\n"):
        stripped = line.strip()
        if stripped.startswith("agents:"):
            in_agents = True
            continue
        if in_agents:
            if stripped.startswith("- "):
                agents.append(stripped[2:].strip().strip('"').strip("'"))
            elif stripped and not stripped.startswith("#"):
                in_agents = False
    return agents


def check_retired_models(
    agent_name: str, models: list[str]
) -> list[str]:
    """檢查是否使用了已退役的模型。"""
    warnings = []
    for model in models:
        # 去掉 (copilot) / (Preview) 後綴來比對
        base_name = re.sub(r"\s*\(.*?\)\s*$", "", model)
        if base_name in RETIRED_MODELS:
            replacement = RETIRED_MODELS[base_name]
            warnings.append(
                f"⚠️  [{agent_name}] 模型 '{model}' 已退役 → 建議改用 '{replacement}'"
            )
    return warnings


def check_deprecated_tools(
    agent_name: str, tools: list[str]
) -> list[str]:
    """檢查是否使用了已廢棄的工具。"""
    warnings = []
    for tool in tools:
        if tool in DEPRECATED_TOOLS:
            replacement = DEPRECATED_TOOLS[tool]
            warnings.append(
                f"⚠️  [{agent_name}] 工具 '{tool}' 已廢棄 → 改用 '{replacement}'"
            )
    return warnings


def check_agents_tool_consistency(
    agent_name: str, agents_field: list[str], tools: list[str]
) -> list[str]:
    """如果有 agents 欄位，tools 必須包含 'agent'。"""
    warnings = []
    if agents_field and "agent" not in tools:
        warnings.append(
            f"❌ [{agent_name}] 有 agents 欄位但 tools 缺少 'agent'"
        )
    return warnings


def check_subagent_references(
    agent_name: str,
    agents_field: list[str],
    all_agent_names: set[str],
) -> list[str]:
    """檢查 agents 欄位引用的 subagent 是否存在。"""
    warnings = []
    for ref in agents_field:
        if ref == "*":
            continue
        if ref not in all_agent_names:
            warnings.append(
                f"⚠️  [{agent_name}] 引用的 subagent '{ref}' 不存在"
            )
    return warnings


def check_staleness(agent_name: str, filepath: Path) -> list[str]:
    """檢查檔案是否超過 STALE_DAYS 天未更新。"""
    warnings = []
    mtime = filepath.stat().st_mtime
    age_days = (time.time() - mtime) / 86400
    if age_days > STALE_DAYS:
        warnings.append(
            f"⏰ [{agent_name}] 已 {int(age_days)} 天未更新（閾值: {STALE_DAYS} 天）"
        )
    return warnings


def main() -> int:
    """主要檢查流程。"""
    if not AGENTS_DIR.exists():
        print("ℹ️  .github/agents/ 目錄不存在，跳過 agent 檢查")
        return 0

    agent_files = sorted(AGENTS_DIR.glob("*.agent.md"))
    if not agent_files:
        print("ℹ️  沒有找到 .agent.md 檔案")
        return 0

    # 蒐集所有 agent 名稱（用於 subagent 引用檢查）
    all_agent_names: set[str] = set()
    for f in agent_files:
        all_agent_names.add(f.stem.replace(".agent", ""))
    # 也處理 .md 檔案（不含 .agent 後綴的）
    for f in sorted(AGENTS_DIR.glob("*.md")):
        name = f.stem.replace(".agent", "")
        all_agent_names.add(name)

    all_warnings: list[str] = []
    checked = 0

    for filepath in agent_files:
        agent_name = filepath.stem.replace(".agent", "")
        content = filepath.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)

        if not fm:
            all_warnings.append(f"⚠️  [{agent_name}] 缺少 YAML frontmatter")
            continue

        raw = fm["raw"]
        models = extract_models(raw)
        tools = extract_tools(raw)
        agents_field = extract_agents_field(raw)

        all_warnings.extend(check_retired_models(agent_name, models))
        all_warnings.extend(check_deprecated_tools(agent_name, tools))
        all_warnings.extend(
            check_agents_tool_consistency(agent_name, agents_field, tools)
        )
        all_warnings.extend(
            check_subagent_references(agent_name, agents_field, all_agent_names)
        )
        all_warnings.extend(check_staleness(agent_name, filepath))
        checked += 1

    # 輸出結果
    if all_warnings:
        print(f"🤖 Agent Freshness Check — 檢查 {checked} 個 agent")
        print("=" * 60)
        for w in all_warnings:
            print(f"  {w}")
        print("=" * 60)
        print(
            "💡 提示: 更新 scripts/hooks/agent_freshness_check.py 中的"
        )
        print(
            "   RETIRED_MODELS / DEPRECATED_TOOLS 清單來維護最新狀態"
        )
        # 警告但不阻擋 commit（exit 0）
        return 0
    else:
        print(f"✅ Agent Freshness Check — {checked} 個 agent 全部健康")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
