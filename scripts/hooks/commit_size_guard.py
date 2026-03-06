"""Commit Size Guard — 限制每次 commit 的檔案數量。

規則：
- 最多 30 個檔案（豁免 uv.lock、htmlcov/、memory-bank/）
- 超過限制時阻擋 commit，提示拆分
- 緊急繞過：git commit --no-verify
"""

from __future__ import annotations

import subprocess
import sys

MAX_FILES = 30
EXEMPT_PATTERNS = [
    "uv.lock",
    "htmlcov/",
    "memory-bank/",
    ".pre-commit-config.yaml",
]


def get_staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
    )
    return [f for f in result.stdout.strip().splitlines() if f]


def is_exempt(filepath: str) -> bool:
    return any(filepath.startswith(p) or filepath == p for p in EXEMPT_PATTERNS)


def main() -> int:
    staged = get_staged_files()
    counted = [f for f in staged if not is_exempt(f)]

    if len(counted) > MAX_FILES:
        print(f"\n❌ Commit 包含 {len(counted)} 個檔案（上限 {MAX_FILES}）")
        print("   豁免項目不計入：uv.lock, htmlcov/, memory-bank/")
        print("\n📋 建議：")
        print("   1. 拆分為多個 focused commits")
        print("   2. 使用 git add -p 部分暫存")
        print(f"   3. 緊急繞過：git commit --no-verify\n")
        return 1

    if counted:
        print(f"✅ Commit 大小合規：{len(counted)}/{MAX_FILES} 檔案")
    return 0


if __name__ == "__main__":
    sys.exit(main())
