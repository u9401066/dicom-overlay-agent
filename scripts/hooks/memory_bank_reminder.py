"""Memory Bank Sync Reminder — 提醒開發者同步 Memory Bank。

規則：
- 當 src/ 有變更但 memory-bank/ 沒有變更時，發出警告
- 不阻擋 commit，僅提醒
"""

from __future__ import annotations

import subprocess
import sys


def get_staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
    )
    return [f for f in result.stdout.strip().splitlines() if f]


def main() -> int:
    staged = get_staged_files()
    if not staged:
        return 0

    has_src_changes = any(
        f.startswith(("src/", "tests/")) or f.endswith((".py", ".ts", ".js"))
        for f in staged
    )
    has_memory_changes = any(f.startswith("memory-bank/") for f in staged)

    if has_src_changes and not has_memory_changes:
        print("\n⚠️  Memory Bank 未同步！")
        print("   偵測到程式碼變更但 memory-bank/ 沒有更新。")
        print("   建議：使用 Copilot 執行「更新 memory bank」或「MB」")
        print("   （此提醒不會阻擋 commit）\n")

    return 0  # 永遠不阻擋


if __name__ == "__main__":
    sys.exit(main())
