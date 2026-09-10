## 變更描述
簡要描述此 PR 做了什麼變更。

> 請勿附上 PHI、credentialed MEETI 影像、OAuth/API key、`openclaw-home` state
> 或未遮蔽的 home path。醫療影像證據只可使用已核准、去識別的 artifact。

## 變更類型
- [ ] 🐛 Bug 修復 (非破壞性變更，修復問題)
- [ ] ✨ 新功能 (非破壞性變更，新增功能)
- [ ] 💥 破壞性變更 (會導致現有功能無法正常運作)
- [ ] 📝 文檔更新
- [ ] 🔧 重構 (不影響功能的程式碼變更)
- [ ] 🩺 Clinical-safety／判讀 harness 變更
- [ ] 📦 封裝／release 變更

## 相關 Issue
關聯的 Issue 編號：#

## 檢查清單
- [ ] 我的程式碼遵循專案的 DDD 架構規範
- [ ] 我已更新相關文檔
- [ ] 我已新增必要的測試
- [ ] 我已列出實際執行的測試與結果；未執行項目明確標為 pending
- [ ] 若涉及 UI/判讀，我已區分 real viewer+App 證據、headless/CLI 與 mock
- [ ] 若涉及 Luna，我已區分 `openai-codex-luna` subscription route 與
      `openai-luna` Platform API-key route，並保留 OpenClaw ownership
- [ ] 若涉及 bbox/Gateway，我已驗證 source/nonce/receipt、canonical audit path
      與 ownership receipt，而非只檢查 JSON in-bounds
- [ ] 若涉及 clinical rules，我只修改 canonical YAML/schema，已重生 views/SQLite，
      並記錄 registry digest、專科 review 與授權狀態
- [ ] 若涉及封裝，我使用 clean worktree 實測尺寸/hash/residue；沒有以算術估計、
      polluted `dist/` 或刪除 OpenClaw internals 當 release evidence
- [ ] 若宣稱發布，我已確認 CI、Pages、Git tag 與 GitHub Release 實際存在；單純
      修改 version metadata 不算發布
- [ ] 相關測試均通過，或下方逐項說明 blocker／failure
- [ ] Memory Bank 已同步更新

## 測試說明
請分開列出：source unit/smoke、mock artifact、real Gateway、real viewer+App、
packaged EXE，以及未執行項目。附 commit SHA、模型／auth route、case/cohort identity、
wall time、token usage、artifact path 與 pass/fail；不要把 transport/UI 成功寫成
diagnostic accuracy。

## 截圖（如適用）
新功能或 UI 變更的去識別截圖。判讀／bbox 變更需包含 viewer+overlay 與 export
audit；若只有 mock/headless 圖，必須明示。

## 額外備註
審查者需要知道的其他資訊。
