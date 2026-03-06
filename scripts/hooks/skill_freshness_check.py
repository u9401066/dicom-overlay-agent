"""Skill & Instruction Freshness Check — 檢查 Skills 和 Copilot 指令的健康度。

檢查項目：
1. Skill 檔案結構完整性（必須有 SKILL.md + frontmatter）
2. copilot-instructions.md 與 Skills 目錄一致性
3. 過期偵測：如果 skill 超過 90 天未更新，發出警告
4. 依賴完整性：skill 宣告的 dependencies 是否都存在
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

# 調整這些路徑以匹配你的專案結構
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"
INSTRUCTIONS_FILE = PROJECT_ROOT / ".github" / "copilot-instructions.md"
STALE_DAYS = 90


def check_skill_structure(skills_dir: Path) -> list[str]:
    """檢查每個 skill 目錄是否有 SKILL.md。"""
    warnings = []
    if not skills_dir.exists():
        return ["⚠️  Skills 目錄不存在: .claude/skills/"]

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            warnings.append(f"❌ 缺少 SKILL.md: {skill_dir.name}/")
            continue

        content = skill_file.read_text(encoding="utf-8")
        # 檢查 frontmatter
        if not content.startswith("---"):
            warnings.append(f"⚠️  缺少 YAML frontmatter: {skill_dir.name}/SKILL.md")
            continue

        # 檢查必要欄位
        required_fields = ["name:", "description:", "version:"]
        for field in required_fields:
            if field not in content.split("---")[1]:
                warnings.append(
                    f"⚠️  frontmatter 缺少 {field} {skill_dir.name}/SKILL.md"
                )

    return warnings


def check_skill_freshness(skills_dir: Path) -> list[str]:
    """檢查 skill 檔案修改時間，超過閾值發出警告。"""
    warnings = []
    if not skills_dir.exists():
        return []

    now = time.time()

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        mtime = skill_file.stat().st_mtime
        age_days = int((now - mtime) / 86400)
        if age_days > STALE_DAYS:
            warnings.append(
                f"🕐 過期警告: {skill_dir.name}/SKILL.md "
                f"({age_days} 天未更新，閾值 {STALE_DAYS} 天)"
            )

    return warnings


def check_instruction_sync(skills_dir: Path, instructions_file: Path) -> list[str]:
    """檢查 copilot-instructions.md 是否列出所有 skills。"""
    warnings = []
    if not instructions_file.exists():
        return ["⚠️  copilot-instructions.md 不存在"]
    if not skills_dir.exists():
        return []

    instructions_content = instructions_file.read_text(encoding="utf-8").lower()
    skill_names = [
        d.name for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()
    ]

    for name in skill_names:
        # 將 skill 名稱中的 - 轉為多種可能的格式來搜尋
        variants = [name, name.replace("-", " "), name.replace("-", "_")]
        if not any(v in instructions_content for v in variants):
            warnings.append(
                f"⚠️  copilot-instructions.md 未提及 skill: {name}"
            )

    return warnings


def check_skill_dependencies(skills_dir: Path) -> list[str]:
    """檢查 skill 宣告的 dependencies 是否都存在。"""
    warnings = []
    if not skills_dir.exists():
        return []

    existing_skills = {
        d.name for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()
    }

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        content = skill_file.read_text(encoding="utf-8")
        # 從 frontmatter 中提取 dependencies
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not frontmatter_match:
            continue

        frontmatter = frontmatter_match.group(1)
        # 簡單解析 YAML list
        in_deps = False
        in_orchestrates = False
        for line in frontmatter.splitlines():
            if line.strip().startswith("dependencies:"):
                in_deps = True
                in_orchestrates = False
                continue
            if line.strip().startswith("orchestrates:"):
                in_orchestrates = True
                in_deps = False
                continue
            if in_deps or in_orchestrates:
                if line.strip().startswith("- "):
                    dep = line.strip()[2:].strip()
                    if dep and dep not in existing_skills:
                        label = "dependency" if in_deps else "orchestrated skill"
                        warnings.append(
                            f"❌ {skill_dir.name} 的 {label} 不存在: {dep}"
                        )
                elif not line.startswith(" ") and not line.startswith("\t"):
                    in_deps = False
                    in_orchestrates = False

    return warnings


def main() -> int:
    all_warnings: list[str] = []

    all_warnings.extend(check_skill_structure(SKILLS_DIR))
    all_warnings.extend(check_skill_freshness(SKILLS_DIR))
    all_warnings.extend(check_instruction_sync(SKILLS_DIR, INSTRUCTIONS_FILE))
    all_warnings.extend(check_skill_dependencies(SKILLS_DIR))

    if all_warnings:
        print(f"\n🔍 Skill & Instruction 健康檢查（{len(all_warnings)} 項提醒）：")
        for w in all_warnings:
            print(f"   {w}")
        print()
        # 不阻擋 commit，僅提醒
        # 如果要阻擋，將 return 0 改為 return 1
        return 0

    print("✅ Skills & Instructions 健康度良好")
    return 0


if __name__ == "__main__":
    sys.exit(main())
