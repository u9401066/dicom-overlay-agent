# 子法：Git 工作流規範

> 父法：CONSTITUTION.md 第三章

## 第 1 條：提交前檢查清單

依序執行以下步驟（可透過 `--skip-X` 跳過）：

| 順序 | 項目 | Skill | 可跳過 |
|------|------|-------|--------|
| 1 | Memory Bank 同步 | `memory-updater` | ❌ |
| 2 | README 更新 | `readme-updater` | ✅ |
| 3 | CHANGELOG 更新 | `changelog-updater` | ✅ |
| 4 | ROADMAP 標記 | `roadmap-updater` | ✅ |
| 5 | 架構文檔（如有變更） | `arch-updater` | ✅ |

## 第 1.1 條：Pre-commit Hooks（自動化守衛）

專案使用 `pre-commit` 框架自動化執行提交前檢查。

### 安裝方式

```bash
uv add --dev pre-commit
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
uv run pre-commit run --all-files  # 首次全量檢查
```

### Hook 清單

| Hook | 類型 | 說明 | 阻擋 |
| ------ | ------ | ------ | ------ |
| trailing-whitespace | 格式 | 移除行尾空白 | ✅ |
| end-of-file-fixer | 格式 | 確保檔案以換行結尾 | ✅ |
| check-yaml/toml/json | 格式 | 驗證設定檔格式 | ✅ |
| check-added-large-files | 安全 | 限制大檔案（>500KB） | ✅ |
| detect-private-key | 安全 | 偵測私鑰檔案 | ✅ |
| no-commit-to-branch | 流程 | 禁止直接提交到 main | ✅ |
| ruff (lint) | 品質 | Python linting + 自動修復 | ✅ |
| ruff-format | 品質 | Python 格式化 | ✅ |
| mypy | 品質 | Python 型別檢查 | ✅ |
| bandit | 安全 | Python 安全掃描 | ✅ |
| gitleaks | 安全 | Secrets 偵測 | ✅ |
| conventional-pre-commit | 流程 | Commit message 格式 | ✅ |
| commit-size-guard | 流程 | 限制 ≤ 30 檔案 | ✅ |
| memory-bank-reminder | 提醒 | Memory Bank 同步提醒 | ❌ |
| skill-freshness-check | 提醒 | Skill/Instruction 健康度 | ❌ |

### 自訂 Hook 腳本

位於 `scripts/hooks/`：

| 腳本 | 功能 |
| ------ | ------ |
| `commit_size_guard.py` | 計算暫存檔案數，超過 30 個阻擋提交 |
| `memory_bank_reminder.py` | 偵測程式碼變更但 Memory Bank 未更新 |
| `skill_freshness_check.py` | 檢查 Skill 結構完整性、過期、依賴、指令同步 |

### 豁免項目

以下不計入 commit size：`uv.lock`、`htmlcov/`、`memory-bank/`

### 緊急繞過

```bash
git commit --no-verify  # 跳過所有 hooks（慎用）
SKIP=mypy git commit    # 跳過特定 hook
```

## 第 2 條：Commit Message 格式

```text
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 類型

- `feat`: 新功能
- `fix`: 修復
- `docs`: 文檔
- `refactor`: 重構
- `test`: 測試
- `chore`: 雜項

## 第 3 條：分支策略

| 分支 | 用途 | 保護 |
| ------ | ------ | ------ |
| `main` | 穩定版本 | ✅ |
| `develop` | 開發整合 | ✅ |
| `feature/*` | 功能開發 | ❌ |
| `hotfix/*` | 緊急修復 | ❌ |
