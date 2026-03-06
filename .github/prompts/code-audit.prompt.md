---
description: "深度程式碼審計 — 系統性地掃描整個程式庫的品質、安全、架構合規性。比 code-review 更全面，適合定期健檢。"
agent: "agent"
tools: ['changes', 'codebase', 'editFiles', 'problems', 'runCommands', 'search', 'usages']
---

# 🔬 Code Audit（深度程式碼審計）

你是一位資深程式碼審計師。請對專案進行系統性的全面審計。

## 審計範圍

依序執行以下審計維度：

### 1. 架構合規性審計
- 檢查 DDD 分層是否正確（Domain → Application → Infrastructure → Presentation）
- 驗證依賴方向：Domain 層不得 import 外部套件
- Repository Pattern 是否正確實作
- 檢查循環依賴

### 2. 程式碼品質審計
```powershell
# 執行靜態分析
uv run ruff check src/ --output-format=concise
uv run ruff format --check src/
uv run mypy src/ --ignore-missing-imports
```
- 函數長度（< 50 行）
- 類別大小（< 300 行）
- 圈複雜度（McCabe < 10）
- 死碼偵測：`uv run vulture src/ --min-confidence 80`
- 命名一致性

### 3. 安全性審計
```powershell
uv run bandit -r src/ -ll
```
- OWASP Top 10 逐項檢查
- 硬編碼 secrets 偵測
- SQL 注入、XSS、CSRF 風險
- 依賴漏洞：`uv run pip-audit` 或 `uv run safety check`

### 4. 測試覆蓋率審計
```powershell
uv run pytest tests/ --cov=src --cov-report=term-missing -q
```
- 覆蓋率是否 ≥ 80%
- 是否覆蓋關鍵路徑
- 邊界條件測試
- 錯誤處理測試

### 5. 文檔同步審計
- README 是否反映當前功能
- CHANGELOG 是否有未記錄的變更
- Memory Bank 是否為最新
- API 文檔是否完整

## 輸出格式

```markdown
# 🔬 程式碼審計報告

📅 日期：{date}
📁 範圍：{scope}

## 評分總覽

| 維度 | 分數 | 等級 |
|------|------|------|
| 架構合規 | ?/10 | 🟢/🟡/🔴 |
| 程式碼品質 | ?/10 | 🟢/🟡/🔴 |
| 安全性 | ?/10 | 🟢/🟡/🔴 |
| 測試覆蓋 | ?/10 | 🟢/🟡/🔴 |
| 文檔同步 | ?/10 | 🟢/🟡/🔴 |
| **總分** | **?/50** | |

## 🔴 Critical Issues（必須修復）
...

## 🟠 High Issues（應該修復）
...

## 🟡 Medium Issues（建議改進）
...

## 🟢 優點
...

## 📋 改進行動計畫
1. [ ] ...
```

完成審計後，建議更新 Memory Bank 記錄審計結果。
