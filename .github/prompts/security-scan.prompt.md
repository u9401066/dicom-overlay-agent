---
description: "安全性掃描 — 快速執行安全檢查（OWASP, secrets, 依賴漏洞）。"
agent: "agent"
tools: ['codebase', 'problems', 'runCommands', 'search']
---

# 🔒 Security Scan（安全掃描）

快速執行專案安全掃描。

## 掃描步驟

### 1. 靜態安全分析
```powershell
uv run bandit -r src/ -ll -f txt
```

### 2. 依賴漏洞檢查
```powershell
uv run pip-audit
```

### 3. Secrets 偵測
```powershell
# 搜尋硬編碼密碼/密鑰
grep -rn "password\|secret\|api_key\|token\|private_key" src/ --include="*.py" || echo "未偵測到硬編碼 secrets"
```

### 4. OWASP Top 10 快速檢查
掃描以下模式：
- SQL 拼接：`f"SELECT|f"INSERT|f"UPDATE|f"DELETE`
- 路徑遍歷：`open(user_input)` 或未驗證的檔案路徑
- 不安全反序列化：`pickle.loads|yaml.load(?!.*Loader)`
- 未驗證的 URL 請求：`requests.get(user_var)`

### 5. 輸出報告
```markdown
## 🔒 安全掃描報告

| 類別 | 狀態 | 發現數 |
|------|------|--------|
| Bandit | ✅/⚠️ | ? |
| 依賴漏洞 | ✅/⚠️ | ? |
| Secrets | ✅/⚠️ | ? |
| OWASP | ✅/⚠️ | ? |
```
