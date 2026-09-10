---
name: 🐛 Bug 回報
about: 回報一個問題
title: '[Bug] '
labels: bug
assignees: ''
---

## 問題描述
簡要描述這個 bug。

> 不要附上 PHI、token、OAuth/API key、`openclaw-home`、credentialed dataset
> 影像或未遮蔽路徑。可能造成資料外洩、未授權 Gateway 接管或任意執行時，請改用
> [private vulnerability reporting](https://github.com/u9401066/dicom-overlay-agent/security/advisories/new)，不要公開細節。

## 影響分類

- [ ] Clinical-safety（漏診／錯嚴重度／錯 lead／錯 bbox／不當拒答）
- [ ] ROI／PHI／credential security
- [ ] Gateway／provider／subscription ownership
- [ ] UI／多螢幕／DPI／座標投影
- [ ] Package／portable runtime
- [ ] Evaluation／scorer／artifact

## 重現步驟
1. 前往 '...'
2. 點擊 '...'
3. 滾動到 '...'
4. 看到錯誤

## 預期行為
描述你預期會發生什麼。

## 實際行為
描述實際發生了什麼。

## 截圖
只附去識別截圖。若是 overlay 問題，請同時提供 viewer+overlay 與 export 中的
bbox audit（可遮蔽 case id）；請註明是 real App、headless 還是 mock。

## 環境資訊
- OS: [例如 Windows 11]
- Commit SHA／tag（目前可能只有 commit，沒有 release）:
- App：source / packaged EXE
- OpenClaw／Node／Python 版本:
- Provider profile／reasoning effort：`openai-codex-astra` low subscription / `openai-codex-luna` subscription / `openai-luna` API / 其他
- 顯示器解析度、DPI scaling、monitor origin/topology:
- ROI 與來源影像尺寸（不得含 PHI）:
- 其他相關資訊:

## 證據與結果

- Case/cohort opaque id:
- Wall time 與 token usage（若有）:
- Gateway ownership／bbox receipt 狀態:
- Result/export 路徑或最小去識別附件:
- 這是 real viewer+App、real Gateway headless，或 mock？

## 額外備註
其他關於這個問題的資訊。
