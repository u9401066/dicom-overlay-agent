# Active Context

> 📌 此檔案記錄當前工作焦點，每次工作階段開始時檢視，結束時更新。

## 🎯 當前焦點

- Pre-commit hooks 與 AI Agent 系統建設完成，準備提交

## 📝 進行中的變更

| 檔案/目錄 | 變更內容 |
|-----------|----------|
| `.pre-commit-config.yaml` | 新增 16+ hooks 配置 |
| `scripts/hooks/` | 4 個自訂 hook（commit-size-guard、memory-bank-reminder、skill/agent-freshness-check） |
| `.github/agents/` | 14 個 agent（含 test-runner、context-loader 免費模型 agent） |
| `.github/prompts/` | 5 個可重複使用 prompt |
| `.claude/skills/code-audit/` | 新增深度審計 skill |
| `.claude/skills/skill-health-check/` | 新增 skill 健康檢查 |
| `.github/copilot-instructions.md` | 全面更新（agents 表、免費模型策略、hook 表） |
| `.github/bylaws/git-workflow.md` | 新增 Pre-commit Hooks 章節 |

## ⚠️ 待解決

- `ask` agent 與內建 Ask 名稱衝突（功能有差異化，暫保留）

## 💡 重要決定

- 免費模型不當 fallback，獨立為專職 agent（test-runner、context-loader）
- 付費模型做推理/判斷，免費模型跑量/讀取
- 多模型審查委員會：Claude + GPT + Gemini 交叉審查
- chatmode 全面遷移到 .agent.md 格式
- agent-freshness-check hook 自動偵測退役模型

## 📁 相關檔案

```
.github/agents/*.agent.md
.github/prompts/*.prompt.md
.claude/skills/code-audit/
.claude/skills/skill-health-check/
scripts/hooks/
.pre-commit-config.yaml
```

## 🔜 下一步

1. Git commit + push（拆分為 2 個 commit）
2. 完整度審查 + 套件更新 hook

---
*Last updated: 2026-03-06*