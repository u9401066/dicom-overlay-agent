# Changelog

所有重要變更都會記錄在此檔案中。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/)，
專案遵循 [語義化版本](https://semver.org/lang/zh-TW/)。

## [Unreleased]

### Added

- **Pre-commit Hooks**: 新增 `.pre-commit-config.yaml`（16+ hooks）
  - ruff lint + format、mypy、bandit、gitleaks、conventional-commits
  - 4 個自訂 hook：commit-size-guard、memory-bank-reminder、skill-freshness-check、agent-freshness-check
- **Copilot Agents**: 14 個 `.agent.md` 自訂 agent
  - 付費 agent：architect、code、debug、audit、orchestrator、deep-thinker、researcher
  - 免費 agent：test-runner（GPT-5 mini）、context-loader（GPT-4.1）、ask
  - 審查委員會：review-panel + 3 reviewer subagents（Claude + GPT + Gemini 交叉審查）
- **Copilot Prompts**: 5 個可重複使用 prompt（code-audit、code-review、pre-commit、security-scan、skill-health-check）
- **新 Skills**: code-audit（深度審計）、skill-health-check（健康檢查）

### Changed

- 遷移 4 個 `.chatmode.md` 至 `.agent.md` 格式
- 更新 `copilot-instructions.md`（agents 表、免費模型策略、hook 表）
- 更新 `git-workflow.md` bylaws（Pre-commit Hooks 章節）
- `pywin32` 改為 Windows-only 條件式依賴，修正 Linux/CI 安裝失敗
- `OpenClawClient` 在缺少本地 token 檔案時允許無 token 建立，用於 mock 測試與 CI
- GitHub Actions `ci.yml` 改為實際驗證 Ruff、跨平台安裝相容性與 pytest

### Removed

- 移除已 deprecated 的 `.chatmode.md` 檔案（architect、ask、code、debug）

## [0.1.0] - 2025-12-15

### Added
- 初始化專案結構
- 新增 Claude Skills 支援
  - `git-doc-updater` - Git 提交前自動更新文檔技能
- 新增 Memory Bank 系統
  - `activeContext.md` - 當前工作焦點
  - `productContext.md` - 專案上下文
  - `progress.md` - 進度追蹤
  - `decisionLog.md` - 決策記錄
  - `projectBrief.md` - 專案簡介
  - `systemPatterns.md` - 系統模式
  - `architect.md` - 架構文檔
- 新增 VS Code 設定
  - 啟用 Claude Skills
  - 啟用 Agent 模式
  - 啟用自定義指令檔案
