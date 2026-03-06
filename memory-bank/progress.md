# Progress (Updated: 2026-03-06)

## Done

- 建立完整專案模板 (48 檔案)
- 發布到 GitHub: u9401066/template-is-all-you-need
- 啟用 Template Repository 功能
- 新增 8 個主題標籤
- **2026-01-15: Skills 品質審查**
  - 增強 8 個過短 Skills（memory-updater, roadmap-updater, changelog-updater, code-reviewer, readme-updater, project-init, git-precommit）
  - 每個 skill 從 55-98 行增強至 194-255 行
  - 新增 Agent 友善內容：操作步驟、檔案範例、工具使用指引
  - 確認無 Skills 職責重疊問題
  - test-generator (729行) 保留不拆分（內容完整）
- **2026-03-06: Pre-commit hooks 與 AI Agent 建設**
  - 新增 `.pre-commit-config.yaml`（16+ hooks：ruff、mypy、bandit、gitleaks 等）
  - 新增 4 個自訂 hook 腳本（commit-size-guard、memory-bank-reminder、skill-freshness-check、agent-freshness-check）
  - 新增 5 個 Copilot Prompts（code-audit、code-review、pre-commit、security-scan、skill-health-check）
  - 新增 2 個 Skills（code-audit、skill-health-check）
  - 遷移 4 個 chatmode → 14 個 `.agent.md`
  - 建立多模型審查委員會（review-panel + 3 reviewer subagents）
  - 建立免費模型專職 agent（test-runner、context-loader）
  - 設計模型成本策略：付費模型做推理、免費模型跑量
  - 更新 copilot-instructions.md 和 git-workflow.md bylaws

## Doing

（無）

## Next

- 測試從模板建立新專案
- 新增更多語言專屬 Skills
- 考慮建立文件網站
- 完整度審查（套件更新 hook 等）
