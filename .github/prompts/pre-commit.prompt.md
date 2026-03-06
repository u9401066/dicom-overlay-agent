---
description: "Git 提交前完整工作流 — 同步 Memory Bank、檢查文檔、執行 pre-commit hooks、生成 commit message。"
agent: "agent"
tools: ['changes', 'codebase', 'editFiles', 'problems', 'runCommands', 'search']
---

# 🚀 Pre-commit Workflow（提交前工作流）

你是 Git 提交助手。請依序執行以下步驟協助準備 commit。

## 步驟

### Step 1: 收集變更
```powershell
git status --short
git diff --name-only --cached
```

### Step 2: Memory Bank 同步（必要）
- 更新 `memory-bank/activeContext.md`（當前焦點）
- 更新 `memory-bank/progress.md`（Done/Doing 狀態）

### Step 3: 文檔更新（條件性）
- 有新功能 → 更新 README.md
- 有功能性變更 → 更新 CHANGELOG.md
- 完成 ROADMAP 項目 → 更新 ROADMAP.md

### Step 4: Pre-commit Hooks 檢查
```powershell
uv run pre-commit run --all-files
```

### Step 5: 生成 Commit Message
依據 Conventional Commits：
```
<type>(<scope>): <description>
```

### Step 6: 執行提交
確認後執行：
```powershell
git add .
git commit -m "<message>"
```

如果用戶要求推送：
```powershell
git push origin <branch>
```
