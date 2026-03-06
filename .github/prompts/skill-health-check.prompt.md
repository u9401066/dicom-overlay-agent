---
description: "Skill 與 Instruction 健康檢查 — 掃描所有 Skills、copilot-instructions.md、chatmode 的一致性與新鮮度。"
agent: "agent"
tools: ['codebase', 'problems', 'runCommands', 'search']
---

# 🏥 Skill & Instruction Health Check（技能健康檢查）

你是一位專案維護專家。請全面檢查 Skills 和 Copilot 設定的健康度。

## 檢查維度

### 1. Skill 結構完整性
掃描 `.claude/skills/` 每個子目錄：
- [ ] 是否有 `SKILL.md`
- [ ] frontmatter 是否完整（name, description, version, category, compatibility）
- [ ] 是否有 `allowed-tools` 或 `tools` 宣告
- [ ] description 中是否有觸發詞

### 2. copilot-instructions.md 同步性
比對 `.github/copilot-instructions.md` 與 `.claude/skills/`：
- [ ] 所有 skill 是否都在 instructions 的表格中列出
- [ ] 觸發詞是否一致
- [ ] 版本號是否對應
- [ ] 是否有 instructions 中提到但不存在的 skill

### 3. Chatmode 一致性
檢查 `.github/*.chatmode.md`：
- [ ] frontmatter 格式是否正確
- [ ] tools 列表是否使用有效的工具名稱
- [ ] 是否有重複的功能定義

### 4. 版本與新鮮度
- 列出所有 skill 的版本號
- 標記超過 90 天未更新的 skill
- 建議需要翻新的 skill（根據 VS Code / Copilot API 演進）

### 5. 依賴圖完整性
- 繪製 skill 之間的依賴關係圖
- 檢查是否有斷裂的依賴（宣告了但不存在的 skill）
- 檢查循環依賴

### 6. 與 bylaws 的一致性
- `.github/bylaws/` 中的規範是否與 skill 行為一致
- CONSTITUTION.md 中的原則是否被 skill 正確遵守

## 輸出格式

```markdown
# 🏥 Skill & Instruction 健康報告

📅 日期：{date}

## 📊 總覽

| 指標 | 狀態 |
|------|------|
| Skills 數量 | ? |
| 結構完整 | ?/? |
| 指令同步 | ✅/⚠️/❌ |
| 版本新鮮 | ?/? 過期 |
| 依賴完整 | ✅/❌ |

## ✅ 健康的 Skills
- skill-name (v1.0.0) — 上次更新: YYYY-MM-DD

## ⚠️ 需要關注
- skill-name — 原因

## ❌ 需要修復
- skill-name — 問題描述

## 📋 建議行動
1. [ ] ...

## 🔗 依賴圖
skill-a → skill-b → skill-c
```
