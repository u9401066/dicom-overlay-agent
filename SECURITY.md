# 安全政策

## 支援狀態

本 repo 目前沒有 Git tag 或 GitHub Release；`0.4.7` 是 Unreleased 開發狀態。
安全修正只會套用到目前維護中的預設分支，不承諾尚未發布的版本支援期間。

## 私密回報漏洞

請勿把漏洞細節、token、OAuth state、API key、患者資料、MEETI credentialed
artifact 或未去識別截圖貼到公開 Issue、Discussion 或 PR。

優先使用 repository 的 **Security → Report a vulnerability** 私密流程：
[Private vulnerability report](https://github.com/u9401066/dicom-overlay-agent/security/advisories/new)。
若 GitHub 未顯示該功能，請先透過 maintainer 的 GitHub profile 要求一個私密聯絡
管道；在私密管道建立前只描述「需要安全聯絡」，不要公開 exploit 或敏感內容。
本專案沒有已驗證的公開 security email，因此不提供假的聯絡地址或固定回應 SLA。

回報請盡量包含：

- 受影響的 commit SHA、OS、Python/Node/OpenClaw 版本與 App 啟動方式。
- 最小化、去識別的重現步驟與預期／實際結果。
- 可能的影響範圍，以及是否涉及 ROI 外擷取、PHI、credential、Gateway ownership、
  bbox/source 綁定、外部 listener、封裝污染或任意程式執行。
- 安全可分享的 log 摘要。請遮蔽 home path、token、case 原始檔名及影像內容；
  不要附 `openclaw-home`、`.env`、auth store 或真實患者資料。
- 若已知，可提出緩解方式，但不需要先公開 patch。

## 本產品特有的安全邊界

- Capture 必須嚴格限制在使用者設定的 ROI，不得退回全螢幕擷取。
- 桌面程式只能透過 OpenClaw 公開 `connect`/`chat.send` Gateway boundary；不得以
  direct API fallback 繞過 ownership、audit 或 tool policy。
- Managed Gateway reuse 必須有 matching `ownership.json`，綁定 PID、port、token
  SHA-256、launch owner 與 canonical absolute bbox audit path；receipt 不存 token
  原值。未知 listener 不接管也不終止。
- Subscription route 不得保留 Platform API key，也不得讓 Codex agent runtime
  取得影像判讀 ownership。API-key route 與 subscription route 的 artifact 必須分開。
- Bbox/tool receipt 必須綁定 exact source digest、nonce、session/run 與座標集合；
  缺漏／不符時 fail closed，不能把未驗證框畫到醫療影像上。
- Release bundle 必須排除 `.env`、OAuth/auth state、SQLite runtime state、MEETI
  images/gold、waveform/checkpoint、log residue 與 PHI，並從 clean worktree 生成。

## Credential scanning（2026-09-10）

- GitHub secret scanning 與 push protection 已啟用；CI 以固定版本、SHA-256
  驗證的 Gitleaks 掃描完整 fetched history，所有輸出使用 `--redact=100`。
- 舊 commit `08581ba` 的 Memory Bank 曾暴露 local Gateway token。該值已不在
  目前文件，也不同於現行 config、`.env` 與 parent process credential。
  `.gitleaksignore` 僅列此筆 exact fingerprint；不得擴大為路徑或規則豁免。
  歷史仍保留該 disclosure，沒有宣稱已從 Git 歷史移除；亦未 force-push。
- OAuth 匯入只暫存 OAuth fields，source 指紋變更時重新透過 pinned migration
  provider 匯入；audit 只記 SHA-256，不記 token。`openclaw-home` 的 migration、
  skill-workshop、memory 及其他 runtime state 不得加入 commit 或 bundle。

## 已知依賴發布阻擋項（2026-09-10）

以 portable Node 24.18.0 執行 `npm audit --omit=dev --json`，目前固定的
OpenClaw 2026.7.1-2 lockfile 回報 **11 個受影響套件項目（7 high、4 moderate）**。
11 個對應版本皆確認存在於重新產生的 slim runtime；不能以「只有開發依賴」
或「已裁剪」排除。這是套件公告命中數，不是 11 個已證實可利用的 App 漏洞。

**此固定版的重建包僅用作大小／功能基準，不得直接發布為新版二進位。**
9.3 隔離候選 lockfile 在同日掃描為零項，但這不是無漏洞保證，也不能代替
OAuth-only migration、native bbox tool、真實 App、封裝與狀態回復驗證。
不對執行中的 runtime 做 `npm audit fix --force` 或未驗證的相依版本覆寫。
完整套件／版本、公告連結與升級門檻見
[September 10 upgrade audit](docs/openclaw-upgrade-audit-2026-09-10.md#dependency-security-release-gate)。

## Clinical safety 與一般 bug 的分流

漏診、錯誤嚴重度、錯 lead、框位錯誤、generic refusal 或不必要免責詞屬於重要的
clinical-safety defect，即使不一定是資訊安全漏洞，也必須保留去識別 artifact 並
在 bug template 標記 `clinical-safety`。若問題同時能造成 ROI 外洩、credential
暴露、未授權 Gateway 接管或供應鏈執行，請改走上述私密漏洞流程。

程式 schema、mock、SQLite parity 或單一實機畫面通過都不是臨床認證。任何
diagnostic accuracy、部署安全或 release-ready 宣稱都必須有對應的真實 App、
blinded evaluation、專科審查與 release evidence。
