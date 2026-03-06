# Copilot 自定義指令

此文件為 VS Code GitHub Copilot 及 Claude Code 提供專案上下文與操作規範。

---

## 專案概述

這是一個 **AI 輔助開發專案模板**，整合了：
- 憲法-子法層級規則系統
- Claude Skills 模組化技能
- Memory Bank 專案記憶
- DDD + DAL 獨立架構（前後端通用）

---

## 開發哲學 💡

> **「想要寫文件的時候，就更新 Memory Bank 吧！」**
> 
> **「想要零散測試的時候，就寫測試檔案進 tests/ 資料夾吧！」**

- 不要另開檔案寫筆記，直接寫進 Memory Bank
- 今天的零散測試，就是明天的回歸測試

---

## 法規層級

```
CONSTITUTION.md          ← 最高原則（不可違反）
  │
  ├── .github/bylaws/    ← 子法（細則規範）
  │     ├── ddd-architecture.md
  │     ├── git-workflow.md
  │     ├── python-environment.md
  │     └── memory-bank.md
  │
  └── .claude/skills/    ← 實施細則（操作程序）
```

你必須遵守以下法規層級：
1. **憲法**：`CONSTITUTION.md` - 最高原則，不可違反
2. **子法**：`.github/bylaws/*.md` - 細則規範
3. **技能**：`.claude/skills/*/SKILL.md` - 操作程序

---

## 架構原則

### DDD (Domain-Driven Design)
- **Domain Layer 不依賴外部**
- **DAL (Data Access Layer) 必須獨立**
- 使用 Repository Pattern
- 依賴方向：`Presentation → Application → Domain ← Infrastructure`

詳見：`.github/bylaws/ddd-architecture.md`

### 目錄結構約定

#### 後端 (Python/Go/Rust)
```
src/
├── Domain/           # 核心領域（無外部依賴）
├── Application/      # 應用層（用例編排）
├── Infrastructure/   # 基礎設施（DAL、外部服務）
└── Presentation/     # 呈現層（API、CLI）
```

#### 前端 (React/Vue)
```
src/
├── domain/           # 型別定義、業務規則
├── application/      # Hooks、Stores、Services
├── infrastructure/   # API Client、Storage
└── presentation/     # Components、Pages、Layouts
```

---

## Python 環境（uv 優先）

- **優先使用 uv** 管理套件和虛擬環境
- 新專案必須建立 `pyproject.toml` + `uv.lock`
- 禁止全域安裝套件

```bash
# 初始化環境
uv venv
uv sync --all-extras

# 安裝依賴
uv add package-name
uv add --dev pytest ruff mypy bandit vulture
```

詳見：`.github/bylaws/python-environment.md`

---

## Memory Bank 同步

每次重要操作必須更新 Memory Bank：

| 操作 | 更新文件 |
|------|----------|
| 完成任務 | `progress.md` (Done) |
| 開始任務 | `progress.md` (Doing), `activeContext.md` |
| 重大決策 | `decisionLog.md` |
| 架構變更 | `architect.md` |

詳見：`.github/bylaws/memory-bank.md`

---

## Git 工作流

提交前必須執行檢查清單：
1. ✅ Memory Bank 同步（必要）
2. 📖 README 更新（如需要）
3. 📋 CHANGELOG 更新（如需要）
4. 🗺️ ROADMAP 標記（如需要）

### Pre-commit Hooks

專案使用 `pre-commit` 框架管理 Git hooks（見 `.pre-commit-config.yaml`）：

```bash
# 安裝 hooks
uv add --dev pre-commit
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
```

| Hook | 描述 |
|------|------|
| ruff (lint+format) | Python 程式碼品質 |
| mypy | 型別檢查 |
| bandit | 安全掃描 |
| gitleaks | Secrets 偵測 |
| conventional-pre-commit | Commit message 格式 |
| commit-size-guard | 限制每次 commit ≤ 30 檔案 |
| memory-bank-reminder | 提醒同步 Memory Bank |
| skill-freshness-check | 檢查 Skill/Instruction 健康度 |
| agent-freshness-check | 檢查 Agent 模型/工具是否過時 |

詳見：`.github/bylaws/git-workflow.md`

---

## 可用 Skills

位於 `.claude/skills/` 目錄：

### 核心技能
| Skill | 用途 | 觸發詞 |
|-------|------|--------|
| **git-precommit** | Git 提交前編排器 | GIT, gc, commit, push, 提交, 推送 |
| **ddd-architect** | DDD 架構輔助（前後端） | DDD, arch, 架構, 新功能, scaffold |
| **code-refactor** | 主動重構與模組化 | RF, refactor, 重構, 拆分, 模組化 |
| **code-reviewer** | 程式碼審查 | CR, review, 審查, 檢查, PR |
| **test-generator** | 測試生成 + 靜態分析 | TG, test, 測試, coverage, pytest |
| **security-reviewer** | 安全性審查 (OWASP) | SEC, security, 安全, OWASP, 漏洞 |

### 記憶管理
| Skill | 用途 | 觸發詞 |
|-------|------|--------|
| **memory-updater** | Memory Bank 同步 | MB, memory, 記憶, 進度, 更新記憶 |
| **memory-checkpoint** | 記憶檢查點 | CP, checkpoint, 存檔, 保存, dump |

### 文檔管理
| Skill | 用途 | 觸發詞 |
|-------|------|--------|
| **readme-updater** | README 智能更新 | readme, 說明, 文檔同步 |
| **readme-i18n** | 多語言 README | i18n, 翻譯, 多語言, bilingual |
| **changelog-updater** | CHANGELOG 更新 | CL, changelog, 變更, 版本 |
| **roadmap-updater** | ROADMAP 狀態追蹤 | RM, roadmap, 路線, 里程碑 |
| **git-doc-updater** | Git 提交前文檔檢查 | docs, 文檔, sync docs, release |

### 品質與審計
| Skill | 用途 | 觸發詞 |
|-------|------|--------|
| **code-audit** | 深度程式碼審計（5 維度） | AUDIT, 審計, 全面審查, deep review, 健檢 |
| **skill-health-check** | Skill 與 Instruction 健康檢查 | SHC, health, 翻新, 過期, audit skills |

### 專案管理
| Skill | 用途 | 觸發詞 |
|-------|------|--------|
| **project-init** | 專案初始化 | init, new, 新專案, bootstrap |
| **skill-generator** | 生成新 Skill | SG, new skill, 建立技能 |

### 工作流 Skills（組合多個 Skills）
| Skill | 用途 | 觸發詞 |
|-------|------|--------|
| **feature-development** | 完整功能開發流程 | FD, 新功能, 開發功能, feature |
| **bug-fix** | 結構化 Bug 修復 | BF, 修 bug, fix bug, debug |
| **code-review-workflow** | 完整程式碼審查 | PRW, 審查流程, review workflow |
| **release** | 版本發布準備 | REL, release, 發布, 版本發布 |

---

## 💸 Memory Checkpoint 規則

為避免對話被 Summarize 壓縮時遺失重要上下文：

### 主動觸發時機
1. 對話超過 **10 輪**
2. 累積修改超過 **5 個檔案**
3. 完成一個 **重要功能/修復**
4. 使用者說要 **離開/等等**

### 執行指令
- 「記憶檢查點」「checkpoint」「存檔」
- 「保存記憶」「sync memory」

### 必須記錄
- 當前工作焦點
- 變更的檔案列表（完整路徑）
- 待解決事項
- 下一步計畫

---

## 常用指令

```
「準備 commit」       → 執行完整提交流程
「快速 commit」       → 只同步 Memory Bank
「建立新功能 X」      → 生成 DDD 結構
「review 程式碼」     → 程式碼審查
「更新 memory bank」  → 同步專案記憶
「checkpoint」        → 記憶檢查點
「新功能開發」        → 完整功能開發流程
「修 bug」            → 結構化 Bug 修復
「審計」              → 深度程式碼審計
「檢查 skill 健康」   → Skill & Instruction 健康檢查
```

---

## 📎 Copilot Prompts（可重複使用）

位於 `.github/prompts/` 目錄：

| Prompt | 用途 | 使用方式 |
|--------|------|----------|
| `code-audit.prompt.md` | 深度程式碼審計 | Agent 面板中選擇 |
| `code-review.prompt.md` | 快速程式碼審查 | Agent 面板中選擇 |
| `skill-health-check.prompt.md` | Skill 翻新檢查 | Agent 面板中選擇 |
| `pre-commit.prompt.md` | 提交前工作流 | Agent 面板中選擇 |
| `security-scan.prompt.md` | 安全掃描 | Agent 面板中選擇 |

---

## 🤖 Copilot Agents / Chat Modes

位於 `.github/agents/`：

| Agent/Mode | 用途 | 預設模型 |
|------------|------|----------|
| `architect` | 系統架構設計 + Memory Bank | Claude Sonnet 4.6 → GPT-5.4 |
| `code` | 實作功能 + 程式碼編寫 | Claude Sonnet 4.6 → GPT-5.4 |
| `ask` | 專案問答 + 知識查詢 | GPT-4.1 → Claude Haiku 4.5 |
| `debug` | 除錯分析 + 問題修復 | Claude Sonnet 4.6 → GPT-5.4 |
| `audit` | 深度程式碼審計（5 維度） | Claude Opus 4.6 → Claude Sonnet 4.6 |
| `orchestrator` | 總指揮 — 拆解需求、委派、追蹤 | Claude Opus 4.6 → GPT-5.4 |
| `deep-thinker` | 深度推理 — 算法、根因、架構權衡 | Claude Opus 4.6 → GPT-5.4 |
| `researcher` | 只讀探索 — codebase 調查、依賴分析 | Gemini 3.1 Pro → Claude Sonnet 4.6 → GPT-5.4 |
| `test-runner` | 🏃 跑測試 + 迭代修復（免費跑量） | GPT-5 mini → GPT-4.1 |
| `context-loader` | 📥 讀取 Memory Bank + codebase 摘要（免費讀取） | GPT-4.1 → GPT-5 mini |
| `review-panel` | 🏛️ 多模型審查委員會（3 AI 交叉審查） | Claude Opus 4.6 → GPT-5.4 |

> 💡 每個 agent 的 `model` 欄位使用優先陣列，若第一個模型不可用會自動 fallback。

### 免費模型策略

GPT-5 mini (0x) 和 GPT-4.1 (0x) 等免費模型**不作為 fallback**，而是獨立為專職 agent：

| Agent | 模型 | 定位 |
|-------|------|------|
| `test-runner` | GPT-5 mini / GPT-4.1 | 反覆跑測試、嘗試修復，不浪費昂貴 token |
| `context-loader` | GPT-4.1 / GPT-5 mini | 批量讀取 Memory Bank 和 codebase，整理摘要 |
| `ask` | GPT-4.1 / GPT-5 mini / Haiku 4.5 | 全免費/低成本問答 |

> **原則**：重複性高、嘗試次數多的工作用免費模型；需要推理和判斷的工作用付費模型。

### 多模型審查委員會（Review Panel）

`review-panel` agent 實現**多 AI 模型交叉審查**：

| Subagent | 模型 | 審查重點 |
|----------|------|----------|
| `reviewer-anthropic` | Claude Sonnet 4.6 | 安全性、型別正確性、邊界條件 |
| `reviewer-openai` | GPT-5.4 | 效能、可讀性、設計模式 |
| `reviewer-google` | Gemini 3.1 Pro | 架構合規、測試品質、文件一致性 |

流程：review-panel 委派 3 個 reviewer → 收集報告 → 分析共識/分歧 → 產出最終報告 → 可 handoff 給 `code` 或 `architect` 修正

---

## 回應風格

- 使用**繁體中文**
- 提供清晰的步驟說明
- 引用相關法規條文
- 執行操作後更新 Memory Bank

---

## 注意事項

- 修改程式碼前先更新規格文檔
- 程式碼是文檔的「編譯產物」
- 遵循 Conventional Commits 格式
- 前後端都採用 DDD 架構
