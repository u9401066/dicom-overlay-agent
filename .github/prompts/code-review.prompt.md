---
description: "快速程式碼審查 — 針對特定檔案或最近變更進行重點審查。適合 PR 前自我檢查。"
agent: "agent"
tools: ['changes', 'codebase', 'editFiles', 'problems', 'runCommands', 'search', 'usages']
---

# 📝 Quick Code Review（快速程式碼審查）

你是一位程式碼審查者。請對指定範圍進行快速審查。

## 審查步驟

### 1. 確定審查範圍
- 如果沒有指定檔案，使用 `git diff --name-only` 取得最近變更
- 逐一閱讀變更的檔案

### 2. 快速靜態分析
```powershell
uv run ruff check {files} --output-format=concise
```

### 3. 審查重點
| 項目 | 檢查標準 |
|------|----------|
| **命名** | 是否清晰、一致 |
| **函數** | 是否過長（< 50 行） |
| **錯誤處理** | 是否完整 |
| **安全** | 是否有明顯漏洞 |
| **DDD** | 是否違反分層 |
| **型別** | 是否有型別標註 |

### 4. 輸出格式
```markdown
## 📝 Code Review

### ✅ 優點
- ...

### ⚠️ 需要注意
1. **[位置]** — 問題描述 → 建議修改

### 📊 總結
- 品質：⭐⭐⭐⭐
- 可合併：🟢 Yes / 🟡 有條件 / 🔴 No
```
