# DICOM Overlay Agent

> 🩺 一個自主協同判讀（co-reading）agent：在背景監控 DICOM viewer，將截圖交給 OpenClaw 判讀，再將 AI 發現疊加在原始影像上——最終診斷永遠由醫師決定。

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

🌐 [English](README.md)

網站：[u9401066.github.io/dicom-overlay-agent](https://u9401066.github.io/dicom-overlay-agent/)
（9 月 10 日已公開部署並完成瀏覽器驗證；屬開發證據，不是臨床正式版本）。

## 開發證據 — 2026-09-10（尚未發布）

目前實機驗收只使用 **GPT-6 Astra low**，在 Settings 選擇
`openai-codex-astra`；Luna 已不列為本輪驗收目標。真實 GUI 擷取已連通訂閱路由，
runtime 確認 `gpt-6-astra / low`。同一校準案例的第一次匯出在整合階段逾時
（179.252 秒），第二次完成整合（165.043 秒），但仍需複核。另一個不同案例在
140.481 秒完成四個影像階段，來源 ROI 與 Astra low runtime 已核對，臨床評分待做；
下一個 pilot 案例碰到首階段 60 秒逾時。這些不是已完成百例驗收。
另已核對 9 月 2–3 日的歷史 Luna 批次：103 次嘗試、60 份匯出、43 次逾時。
60 份來源影像均匹配預定案例，這只證明影像身分，並非診斷正確率。
詳見[9 月 10 日證據更新](docs/verification-2026-09-10.md)。

目前 working tree 的產品 metadata 是 `0.4.7`、harness/plugin 是 `1.5.8`，但
repository **沒有任何 Git tag，也沒有 GitHub Release**。在乾淨封裝、指定實機
批次、CI、tag 與 release artifacts 全部通過以前，所有 `0.4.7` 內容都屬於
Unreleased。

Luna 有兩條刻意分開的路由，避免把訂閱額度與 Platform API 計費混為一談；兩條
路由的多模態 agent loop 都仍由 OpenClaw 擁有：

| Settings profile | 認證／transport | 模型 | 計費證據 |
| --- | --- | --- | --- |
| `openai-codex-astra` — GPT-6 Astra via Codex Subscription | OpenClaw 原生 `openai-chatgpt-responses`、本機 Codex OAuth、`thinkingDefault=low`；不使用 Platform API key | `openai/gpt-6-astra` | 訂閱用量；中止或未回報的回合不能算零用量 |
| `openai-codex-luna` — GPT-5.6 Luna via Codex Subscription | 本機 ChatGPT/Codex OAuth 遷移到 OpenClaw 原生 `openai-chatgpt-responses`；不使用 `OPENAI_API_KEY`，也不啟用 Codex agent runtime | `openai/gpt-5.6-luna` | 訂閱用量；下列 token 成本只作 API 等值估算 |
| `openai-luna` — GPT-5.6 Luna Vision (API key) | `OPENAI_API_KEY` 經 OpenClaw `openai-responses` | `openai/gpt-5.6-luna` | 一般 Platform API 計費 |

2026-09-02 以真實桌面 App／viewer／subscription route 對第一個 frozen critical
ECG 進行三次嘗試。三次都是負面或不完整證據，不是驗收通過：

| Desktop export | 實耗 | 記錄用量 | 結果 |
| --- | ---: | ---: | --- |
| `desktop-20260902-082210-259256` | 139.4 秒 | total 74,786（input 48,789、cached 20,480、output 5,517、reasoning 3,217），API 等值 US$0.0167878 | `info`、0 findings；判讀錯誤 |
| `desktop-20260902-090424-024627` | 61.673 秒 | total 37,811（input 24,787、cached 10,752、output 2,272、reasoning 1,093），API 等值 US$0.00789884 | `info`、1 個 possible-LVH finding、僅 5 列 checklist；不完整 |
| `desktop-20260902-092532-259033` | 153.398 秒 | total 87,694（input 61,500、cached 20,480、output 5,714、reasoning 3,053），API 等值 US$0.0195664 | `info`、1 finding、`incomplete/review`；漏掉 critical reference |

估算採 [GPT-5.6 Luna 官方 API 價格](https://developers.openai.com/api/docs/models/gpt-5.6-luna)：
input US$0.20/M、cached input US$0.02/M、output US$1.20/M；它們不是訂閱扣款。
這些失敗揭露了 Gateway/bbox receipt 與 critical-first reconciliation 問題，仍在
修正中，不能據此宣稱臨床正確率、延遲 SLA 或發布就緒。

- 已凍結一組刻意 gold-enriched、答案隔離的 **128 張唯一多重診斷 ECG**（seed
  `1946247532`；24 critical/104 warning；48 asserted/80 partially uncertain；
  每例至少三個 canonical diagnoses；pair id `7bdc87f6…8a46e0`）。尚未完成指定的
  真實 App 批次，而且不是 prevalence-weighted 的母群準確率樣本。
- Partial-ECG v2 有八種 deterministic 變體（四邊裁切、中央／窄帶、遮住導極
  label、短邊 48 px）。目前 8/8 只證明 mock schema/bbox/partial-input plumbing；
  尚無真實 Luna 診斷分數。
- 七條 deterministic clinical-consistency rules 以 canonical YAML 為唯一人工
  維護來源，生成 human/agent views 與 application-owned SQLite；registry SHA-256
  為 `d22a03e037293636c86ca029452a8486f93f5625cb5655b3381088b8cc1fc22c`。
  Schema/parity 通過不等於專科臨床審查或來源授權完成；詳見
  [clinical knowledge governance](clinical_knowledge/README.md)。
- Managed Gateway 只有在原子、無 secret 的 ownership receipt 同時綁定 PID、port、
  token SHA-256、launch owner 與唯一 canonical absolute bbox audit path 時才可重用；
  健康但 receipt 不符的 listener 會被拒絕，不會被接管或終止。
- 最近一次完整乾淨 bundle 仍是 2026-08-09 的歷史 build：launcher 7.05 MiB、
  App+Python/Qt 94.74 MiB、full bundle 368.01 MiB。目前 `dist/` 受 runtime residue
  污染，不是 release evidence；已實作的安全 staging 減量與後續候選仍須乾淨實測。
  不會用刪除 OpenClaw `dist`、provider、Playwright、QuickJS、TypeScript 或 Node 的
  方式製造不可靠的小數字。
- OpenClaw `2026.8.2` 已通過隔離的公開 `connect`/`chat.send` protocol 檢查，仍
  暫緩全面升級：auth/config migration、state rollback，以及 core unpacked size
  由 83.43 增到 196.68 MiB 尚未解決。詳見
  [2.x 決策紀錄](docs/openclaw-2x-decision-2026-09-02.md)。

較早的 32-case frozen pair、8-case unseen engineering gate 與尚未完成的
9,922-case paired run 保留為歷史證據，詳見
[`docs/meeti-openclaw-experiments-2026-08-09.md`](docs/meeti-openclaw-experiments-2026-08-09.md)。

## 2026-07-02 real-model smoke 狀態

- `scripts/check-real-model-readiness.cmd --dotenv .env` 會讀取 repo-local
  credential presence，但不輸出或寫入 secret value。OpenRouter MiniMax M3
  readiness 已為 `ready`：`OPENROUTER_API_KEY` 存在、1000-case mock artifact
  gate 已通過、OpenClaw runtime 為 `2026.6.11`。真實跑批前請加
  `--probe-provider`，會先檢查 provider egress 與模型是否 advertised image
  input；目前 probed readiness 仍 blocked。最新 OOM-safe probe
  `data\experiments\real-model-readiness-20260702-openrouter-minimax-m3-current-probed.json`
  證明 key、OpenClaw runtime、1000-case manifest 與 mock artifacts 都存在，
  但在 Gateway 啟動前被 WinError 10013 socket 權限拒絕擋下。
- `scripts/run-meeti-openclaw-experiment.cmd` 是目前建議的非 PowerShell
  實驗入口；它直接使用既有 uv-managed `.venv\Scripts\python.exe` 呼叫
  `scripts/run-meeti-openclaw-experiment.py` 產生 experiment-local OpenClaw
  config、啟動 Gateway、跑 eval、重建 scorecard 並匯出 review artifacts。
  它也會拿 `data\tmp\meeti-run.lock`，避免同時啟動第二個實驗 runner。postprocess
  後會再跑 `scripts/verify-eval-artifacts.py`；bounded smoke run 以 `--limit`
  作為驗證張數，完整跑批預設要求 1000 cases，`--multi-pass` 會自動加上
  `--require-multipass-trace`；post-run artifact verifier 也會加上
  `--require-projection-audit`，要求 bbox audit row 含圖層投影 round-trip
  校正欄位，避免未經位置校正的框被視為 production-complete。
- `scripts/check-real-model-readiness.cmd` 也直接使用既有 uv-managed
  `.venv\Scripts\python.exe`，並持有 `data\tmp\readiness-run.lock`，
  避免 readiness probe 重新繞過 OOM-safe runner 而啟動第二個 runner。
- 最新 1 張 MEETI real smoke：
  `data/experiments/meeti-openrouter-minimax-m3-1case-cmd-wrapper-20260702`
  已使用 `openrouter/minimax/minimax-m3` 走到 OpenClaw Gateway
  `connect` + `chat.send`，並輸出 scorecard / raw result / review artifacts；
  但本機對 OpenRouter 的外網 fetch 被 reset（`ECONNRESET` / WinError 10054），
  OpenClaw 無法取得 OpenRouter model capabilities/pricing 或呼叫
  `minimax/minimax-m3`，所以 experiment 正確標為 `completed_with_failures`、
  exit 1。這不是 bbox/schema harness 通過，而是環境網路出口待處理。
- 2026-07-05 歷史 real-model 證據：在 OpenRouter 與 Anthropic 被防火牆 reset 的
  網路下，`api.openai.com` 可通且 `OPENAI_API_KEY` 有效。以 `openai/gpt-5.5`
  ＋ `openai-vision` provider profile 跑 MEETI 單題真實批次，走到 Gateway
  `connect` + `chat.send`、回傳 schema-valid 判讀，strict/schema/bbox 皆
  1.0（`gateway_mode: real`）。該次使用當時的模型設定；目前 runner 與
  Settings 與 runner 預設已改為 image-capable
  `openai/gpt-5.4-mini`，另保留 Luna 與其他 API profile。Copilot 訂閱模型
  （如 MAI Flash）走 OAuth device-token，不是 API key，無法當 API provider。
- 2026-07-05 臨床準確度強化：EKG skill 新增 **Step 0 導極定位**（保持通用，
  「宣告不假設」：讀印在圖上的導極標籤、只登記實際可見的導極、無標籤標
  `unknown`），並把 lead-dependent 結論（STEMI 定位／axis／R 波進展／腔室
  肥大）鎖在實際拍到的導極上，單一 rhythm strip 或局部／非標準截圖不會誤觸
  12-lead 專屬結論。辨識 scorer 會正規化連字號／複數並認可臨床同義詞／縮寫
  （RBBB、afib、LVH、PVC…），避免把正確判讀誤判為 miss，同時仍尊重否定與
  真實分歧。`scripts/analyze-eval-failures.py` 可聚合每次 run 的失敗模式以
  指引下一步 harness 增量。
- 2026-07-05 模型輔助精判：兩個 bounded 額外 pass 針對真漏診。**Empty-summary
  retry**——`run-eval.py` 在讀回空 summary 且無 findings（模型暫時性失誤）時
  自動重送一次，不再直接吞 0 分硬失敗。**Rhythm-strip 二次 pass**——
  `src/dicom_overlay/application/rhythm_strip.py` 把模型宣告的
  `layout.rhythm_strip_bbox` 從原解析度影像 crop 出來、只重讀 rhythm strip，
  找回 rate／rhythm／P 波／AV block，並以 escalate-only 合併（絕不降級）。保持
  layout 通用：除非 Step 0 定位到 rhythm strip 否則 no-op，單導極／局部／非標準
  截圖不會被猜位置 crop。可用 `--no-rhythm-strip-pass` 關閉。

## 2026-07-02 OOM-safe uv / 題目測試入口

- 建議本機完整預設測試改用
  `scripts\run-tests-safe.cmd -q`。
  這個入口直接使用既有 uv-managed `.venv\Scripts\python.exe`，並把 `TMP`/`TEMP` 與
  pytest `--basetemp` 放到 `data\tmp\pytest-safe`，避免 AppData cache、
  pytest cacheprovider、進度輸出或大型暫存樹造成 PowerShell/uv OOM。最新修正
  會透過 `scripts\run_pytest_safe.py` 把預設 unit+smoke suite 拆成每個
  `test_*.py` 一個短生命週期 pytest process；像 `-q` 這種純 pytest option
  會套用到每個 batch，明確指定 `tests\unit -q` 這種目錄 target 或多個
  test file 時也會展開成逐檔 batch；只有單一
  `tests\unit\test_agent.py -q` 會維持 targeted pytest session。若要診斷舊的一次性 session 行為，可設
  `DICOM_OVERLAY_TEST_SINGLE_SESSION=1`。目前已避免把 PowerShell 當作預設
  測試/實驗入口。runner 會使用
  `data\tmp\pytest-run.lock`，若另一個 pytest runner 已在跑，會直接 exit 75，
  不會再開第二個測試程序。
- 裸跑 `pytest` 的預設範圍現在只收 `tests/unit` + `tests/smoke`，並排除
  `data/`、`openclaw/`、`openclaw-home/`、`.uv-cache-codex/`、`node_modules/`
  等大型產物或 vendored runtime；需要整合測試時請明確指定
  `tests/integration`。
- `run-eval.py` 大型題目集已改成每 50 cases 更新一次
  `scorecard.partial.json`，不再每張圖重寫完整 partial scorecard；可用
  `--partial-scorecard-interval 0` 改成只在完成/中止時寫 checkpoint。
- 最新 OOM 修正驗證：
  `data\eval\meeti-1000-mock-oomfix-20260702` 完成 1000/1000 MEETI mock
  eval、匯出 1000 張 review 標框圖，且
  `scripts\verify-eval-artifacts.py --min-cases 1000` 通過
  `local_preflight_artifacts`、`model_assist_artifacts`、`review_artifacts`。

## 2026-07-02 維護狀態

- 2026-07-02 當時的本機 OpenClaw runtime 已驗證到 `2026.6.11`；目前封裝版為
  `2026.7.1-2`，仍只透過 Gateway
  `connect` + `chat.send` 與 OpenClaw 溝通，不匯入 OpenClaw plugin SDK
  內部 API。
- 桌面版 Settings 的 AI Provider 分頁可明確選擇 Platform API key 或
  ChatGPT/Codex subscription OAuth；兩者都由 OpenClaw embedded agent 擁有
  影像回合。Release default `openai/gpt-5.4-mini` 可走 `openai-vision` API 或
  `openai-codex` subscription。Luna 另分成 `openai-codex-luna`（無 API key、
  `openai-chatgpt-responses`）與 `openai-luna`（`OPENAI_API_KEY`、
  `openai-responses`），不可混用 auth/billing evidence。OpenRouter 等 API profile 仍可使用，設定只
  寫入 OpenClaw managed provider/model 區段，secret 留在環境變數、`.env` 或
  OpenClaw 私有 auth store，不進 git 與實驗紀錄。
- MEETI 生產級評估 gate 使用 Zenodo record `18523205` 的 `MEETI.rar`
  公開資料來源；本機 manifest 已能從約 1 萬張 ECG 影像建立至少 1000
  case，並透過 `run-eval.py`、`export-eval-annotations.py`、
  `verify-eval-artifacts.py` 驗證 scorecard、raw result、review PNG、
  bbox audit/crops 與 local image preflight。
- `local_image_quality` 是第一層非 MLLM 輔助：在送模型前/評估時記錄影像尺寸、
  aspect ratio、ink/bright-pixel density、entropy、edge density、robust dynamic
  range 與 low-signal flag，避免
  所有品質判斷都拖到多模態語言模型。
- `local_signal_candidates` 是第二層本機輔助：用低成本像素 threshold 先產生
  ECG-like waveform / signal bbox 候選，供 harness 與人工 review 對照；它不做
  診斷，只提供 MLLM 前的可審計候選框。`run-eval.py --multi-pass` 現在會在
  coarse MLLM 判讀為非正常但沒有 bbox 時，把這些本地候選框餵給 crop
  re-analysis，避免框格流程完全依賴第一輪 MLLM 座標。`multipass-trace.jsonl`
  也會記錄 `local_candidate_count` 與 normalized `local_candidate_regions`，
  方便 1000 張跑批後做審計；trace 存在時，
  `scripts/verify-eval-artifacts.py` 會以 `multipass_trace_artifacts` gate
  檢查這些欄位。生產級 multi-pass 跑批請加
  `--require-multipass-trace`，讓缺少 crop re-analysis trace 的 artifact
  直接 fail。
- `scripts/check-real-model-readiness.cmd` 會把真實模型 1000-case benchmark
  的先決條件寫成 `ready` 或 `blocked` JSON artifact；缺 OpenRouter/OpenAI
  key、manifest 不足 1000 case、mock artifact gate 未通過都會被機器可讀地
  擋下，而且不會輸出 secret 值。加上 `--probe-provider` 時，也會先擋下
  provider 連線 reset 或模型未 advertised image input 的情況。

Agent 不取代醫師，而是作為系統性的 *second-check*，降低因疲勞、忙碌或注意力分散造成的遺漏。由於無法直接存取 HIS API，**螢幕是唯一輸入來源**：使用者首次設定截圖 ROI（裁切已知 PHI），agent 在醫師正常操作時於背景截圖、分析、標註。

## 🎯 四大核心（維護重點）

本 repo 围繞以下 **四個產品核心** 維護，每次變更都必須保持這些核心對齊（維護守則見 [AGENTS.md](AGENTS.md)）。

| # | 核心 | 保證什麼 |
| --- | --- | --- |
| 1 | **影像判讀圖層互動**（位置 + 內容） | AI 發現出現在正確的 *位置*（bbox/region 疊在原圖上），並提供可讀的 *內容*（checklist + 追問 chat） |
| 2 | **OpenClaw 判讀完整 harness** | 一個可執行、CI 可驗證的合約，證明截圖 → 分析 → 疊加的迴圈確實可用 |
| 3 | **OpenClaw plugin 兼容性** | 只透過穩定的公開 Gateway 協定溝通，能跨 OpenClaw 版本存活 |
| 4 | **最小化執行檔封裝** | 小型 `.exe` 啟動器（<50 MiB；最近一次 2026-08-09 完整 build 為 7.05 MiB）加上含固定 Node/OpenClaw 的已驗證可攜 bundle |

每個核心詳見下方 [核心詳解](#-核心詳解)。

## 📁 專案結構

```text
dicom-overlay-agent/
├── src/dicom_overlay/             # 🩺 應用程式（DDD 分層）
│   ├── domain/                    #   entities、value objects、service 介面
│   ├── application/               #   overlay_agent.py（use-case 編排）
│   ├── infrastructure/            #   OpenClaw client、screen monitor、harness、runtime
│   └── presentation/              #   overlay_window、control_bar、roi_setup、settings
├── openclaw/                      # 🔌 repo 本地 OpenClaw runtime + plugin/skills
│   └── workspace/
│       ├── plugins/               #   dicom-overlay-agent-harness/manifest.json
│       └── skills/                #   dicom-{ekg,cxr,ct-brain}-analysis SKILL.md
├── scripts/                       # 🔧 build-exe.bat、stage-openclaw-runtime.ps1、harness runners
├── dicom-overlay-agent.spec       # 📦 PyInstaller spec（最小 exe）
├── config.yaml                    # ⚙️ ROI、region_maps、hash、gateway 設定
├── spec.md                        # 📜 系統規格書
├── memory-bank/                   # 🧠 專案記憶
├── .github/agents/ · .claude/skills/   # 🤖 AI 開發 harness（agents、skills、instructions）
├── README.md / README.zh-TW.md
└── CONSTITUTION.md · ARCHITECTURE.md · CHANGELOG.md · ROADMAP.md
```

## 🚀 快速開始

### 從原始碼執行（Windows）

```powershell
# 1. 同步 Python 環境（uv 優先）
uv sync --all-extras

# 2. 安裝 repo 本地 OpenClaw runtime（只需一次）
scripts\install-openclaw-local.bat

# 3. 啟動（Gateway 自動啟動/停止）
start.bat
```

首次啟動時設定截圖 **ROI**（裁切 PHI）並選擇 trigger 模式，之後 agent 即監控 DICOM viewer 並疊加發現。

若要使用 ChatGPT/Codex 訂閱額度而不是 Platform API key，先執行一次
`codex login`，再於 Settings 選擇 **OpenAI Subscription via OpenClaw**。
固定版本的官方 `@openclaw/codex` 套件只在把 OAuth 狀態匯入隔離的
OpenClaw home 時暫時啟用，推論前即從 live plugin config 移除。Agent loop
全程仍由 OpenClaw 擁有；bundle 不含 Codex agent runtime 或平台執行檔，
並在 `data/tmp/codex-auth-import.json` 留下不含 secret 的稽核紀錄。

### 建置可攜帶執行檔

```powershell
scripts\build-exe.bat        # PyInstaller → dist\DICOMOverlayAgent\
```

尺寸預算見 [核心 4](#核心-4--最小化執行檔封裝)。

## 🧩 核心詳解

### 核心 1 — 影像判讀圖層互動

醫師看原始影像；agent 把標註疊在原圖 *上方*。

- **位置** — AI 回傳歸一化 `0-1` 邊界框（`Finding.bboxes`）。
  [`__main__.py`](src/dicom_overlay/__main__.py) 優先用 AI bbox highlight，
  fallback 到 [`region_mapper.py`](src/dicom_overlay/infrastructure/region_mapper.py)
  解析的 static `region_maps`。AI bbox 會先經過
  [`overlay_highlight_builder.py`](src/dicom_overlay/infrastructure/overlay_highlight_builder.py)
  產生 PHI-free 投影 audit；若 round-trip drift calibration 失敗，該動態框不會
  畫回醫師圖層。
- **內容** — 可拖曳的 [`SummaryPanel`](src/dicom_overlay/presentation/overlay_window.py)
  顯示系統性 checklist（EKG 共 16 鍵、CXR 為 10 軸判讀），異常項優先、正常項摺疊；
  [`ChatPanel`](src/dicom_overlay/presentation/overlay_window.py) 讓醫師針對同一張影像追問。
- **區域問答寫回** — 點選 AI 框或自行框選時，桌面程式會把原始來源像素的
  精確 crop 先送進 bounded refine，再交給獨立的結構化 OpenClaw follow-up
  contract；兩輪都保留 session、run 與 tool receipts。模型只能提出 `ADD`、`REVISE`、
  `RETRACT`，不能回傳或移動座標，而且醫師按下 **Apply to report** 前不會修改
  報告。框內 deterministic signal gate 會合併暗像素、邊緣密度、robust dynamic
  range 與空白場檢查；若判為低訊號、audit 缺失或失敗，仍可保留 QA 與人工匯出，
  但不允許任何 `ADD`／`REVISE`／`RETRACT` 改動報告；成功套用會在報告、Process trace、
  JSON 與標框 PNG 保留 `interactive_ai_review` provenance。不同診斷即使框重疊，
  也不會再只因 IoU 高就被誤合併。
- **多趟放大** — [`multi_pass.py`](src/dicom_overlay/application/multi_pass.py)
  以完整 ROI 解析度重讀異常區域以精修 bbox。由於唯一輸入是螢幕截圖（≤4K），
  若某區域在截到的像素中太小，數位放大無意義；此時改以 `zoom_hints` 提示，
  請醫師在 DICOM viewer 內放大後重新截圖。
- **控制** — 小型 [`control_bar.py`](src/dicom_overlay/presentation/control_bar.py)
  提供 暖停 / 設定 / 手動重觸發；面板為 frameless、置頂、可拖曳
  （`_DraggableWindowMixin`）。
- **隱私** — [`roi_setup.py`](src/dicom_overlay/presentation/roi_setup.py)
  裁切截圖範圍，讓已知 PHI 不離開工作站。

### 核心 2 — OpenClaw 判讀完整 harness

判讀迴圈由一個可執行、CI 可驗證的合約支援。

- [`image_harness_smoke.py`](src/dicom_overlay/infrastructure/image_harness_smoke.py)
  驅動完整迴圈：合成影像 → 帶 image attachment 的 `chat.send` → Gateway 事件流 → result/log artifact。
- [`image_harness_validator.py`](src/dicom_overlay/infrastructure/image_harness_validator.py)
  （`verify_image_harness_artifacts`）驗證 **gateway contract**、
  **image payload proof**、以及（可選）desktop viewer 顯示。
- [`output_validator.py`](src/dicom_overlay/infrastructure/hooks/output_validator.py)
  在結果進入 overlay 前強制 16-key schema。
- [`openclaw/workspace/skills/`](openclaw/workspace/skills) 下的 skills 定義各
  modality prompt（`dicom-ekg-analysis`、`dicom-cxr-analysis`、
  `dicom-ct-brain-analysis`）含 bbox 指示。
- 執行器：[`scripts/run-image-harness-smoke.py`](scripts/run-image-harness-smoke.py)
  與 [`scripts/verify-image-harness.py`](scripts/verify-image-harness.py)。
- [`eval_harness.py`](src/dicom_overlay/infrastructure/eval_harness.py) +
  [`scripts/run-eval.py`](scripts/run-eval.py) 以標註資料集評分辨識能力：
  軸×嚴重度覆蓋率、pertinent-negative recall，以及 **can't-miss 硬性 gate**
  （漏掉 STEMI／張力性氣胸 等致命診斷時 CI 以非零碼失敗）。
- [`scripts/run-meeti-paired-experiment.py`](scripts/run-meeti-paired-experiment.py)
  會以同一個 frozen source fingerprint 依序執行 minimal one-look baseline 與
  clinical MultiPass candidate。無答案 inference manifest 與 gold manifest
  分離；OpenClaw ownership、subscription transport、manifest/scorer/source
  fingerprint 任一不符即 fail closed。每題保留原始 JSON、provider/tool receipt、
  crop trace、標記 PNG、座標 audit、scorecard 與 paired 統計。

### 核心 3 — OpenClaw plugin 兼容性

App **只透過穩定的公開 Gateway 協定**（`connect` + `chat.send`）溝通，
不 import plugin SDK 內部，因此能跨 OpenClaw 版本可攜。

- [`openclaw_runtime.py`](src/dicom_overlay/infrastructure/openclaw_runtime.py)
  釘住 `MIN_SAFE_OPENCLAW_VERSION`（`2026.4.22`），並依文件化 schema
  建立 harness manifest / chat frame。Client 明示 protocol `3..4`；pinned
  OpenClaw `2026.7.1-2` 必須回傳經驗證的 `hello-ok protocol=4` receipt。
  Image 仍放在 `params.attachments[]`，含 `type` / `mimeType` / `content`。
- [`openclaw/package.json`](openclaw/package.json) 追蹤 runtime 版本
  （封裝並驗證為 `openclaw 2026.7.1-2`）與最低安全版本下限。
- [`manifest.json`](openclaw/workspace/plugins/dicom-overlay-agent-harness/manifest.json)
  宣告 plugin 兼容區間。
- 同一個 native plugin 提供條件式
  `ecg_founder_analyze_waveform` 橋接，可把
  [PKUDigitalHealth/ECGFounder](https://huggingface.co/PKUDigitalHealth/ECGFounder)
  當成波形第二意見工具。只有設定含 token 的 loopback sidecar 時才會註冊；
  tool 只接收不透明的 waveform artifact id，不接任意路徑，也不會把 PNG
  當波形或把 150 類分數當作影像 bbox。Torch 與約 370 MB checkpoint 不會
  塞進可攜式主程式，完整契約見
  [`docs/ecgfounder-tool.md`](docs/ecgfounder-tool.md)。
  每個實驗 case 另綁定隨機 evidence nonce；只有 nonce、artifact digest、
  固定 model revision 與 checkpoint 全部相符的唯一成功 receipt 才算有效。
  桌面目前尚未實作可信任的 study-to-waveform resolver，因此設定頁只會顯示
  「evaluation sidecar configured」，不會暗示一般 screenshot 判讀已使用它。
  MEETI paired build 已保留 1,000 筆相符的原始 12 導程波形；固定官方
  checkpoint 的真實批次已完整遍歷 1,000 筆，其中 999 筆 eligible，1 筆全零
  V5 導程被安全閘門排除；有效結果都明確標記為未校準的 supporting evidence。
- **規則：** 升級 OpenClaw 前先確認 `connect` / `chat.send` schema、image
  attachment、OAuth/config migration、state rollback 與 clean package size。
  `2026.8.2` 的隔離 protocol probe 已通過，但 core unpacked size 由 83.43 增至
  196.68 MiB，其他 gate 未閉合，因此 audited pin 仍是 `2026.7.1-2`。

### 核心 4 — 最小化執行檔封裝

目標是一個極小的啟動器與精簡、可從 USB 隨身碟執行的可攜帶 bundle，
以 [`scripts/build-exe.bat`](scripts/build-exe.bat) 建置。

- [`dicom-overlay-agent.spec`](dicom-overlay-agent.spec) 排除未用的重量函式庫
  （`numpy`、`scipy`、`matplotlib`、`pandas`、`imagehash`），並修剪 overlay
  從不載入的 Qt 模組（WebEngine、Qml/Quick、Pdf、Multimedia、~20 MB 的
  `opengl32sw.dll` 軟體 GL fallback、qml/translations 資料），並建為 windowed
  （`console=False`）。Release build 透過 `uv` 固定 64-bit CPython 3.13.12，且把
  PyInstaller／Pillow／PyQt 的精確 toolchain receipt 封入 manifest。只有找到 UPX
  執行檔時才啟用；verifier 還必須在 PE 檔觀察到 UPX marker。找不到時則明確記錄
  可比較的 `no_upx_baseline`，不會宣稱其實未發生的壓縮。
- [`scripts/stage-openclaw-runtime.ps1`](scripts/stage-openclaw-runtime.ps1)
  化 *slim* OpenClaw runtime，移除非 Windows 原生載荷與停用的
  UI / browser / voice plugins，只保留 Gateway 面。現行 staging gate 另保留
  並雜湊七個必要 upstream templates，移除 PDB 與 tree-sitter C/H 開發檔，
  並明確保護 OpenClaw `dist`、`quickjs-wasi` 與 `playwright-core`。
- [`scripts/fetch-node.ps1`](scripts/fetch-node.ps1) 下載可攜帶
  `node\node.exe`；存在時會被打包，且
  [`gateway_manager.py`](src/dicom_overlay/infrastructure/gateway_manager.py)
  會優先使用它而非系統 Node.js，達成真正零安裝。
- `pywin32` 為 Windows-only 條件依賴，保持 Linux/CI 安裝乾淨。
- **可攜帶即插即用** — 凍結（frozen）時，runtime 路徑透過
  [`app_paths.py`](src/dicom_overlay/infrastructure/app_paths.py) 錨定到
  執行檔所在資料夾（而非啟動 `cwd`，後者可能是 `System32`），相對 log path 也會
  寫在 bundle 旁，因此能在全新機器上從 USB 隨身碟原樣執行。執行
  `DICOMOverlayAgent.exe --selfcheck`
  即可驗證 Node.js、OpenClaw runtime、可寫入 base 與 `config.yaml` 全部就緒——
  不啟動 GUI、不呼叫 LLM（exit 0 = 就緒）。

**體積預算與實測證據：**

| 產物 | 預算 | 已驗證數字 |
| --- | --- | --- |
| `DICOMOverlayAgent.exe` 啟動器 | < 50 MiB | 最近一次 2026-08-09 完整 build 為 **7.05 MiB** |
| App + Python/Qt 層 | < 100 MiB | 最近一次 2026-08-09 完整 build 為 **94.74 MiB** |
| Unreleased staged OpenClaw runtime | < 500 MiB | **165.162 MiB** |
| 保守 staging 減量 | - | **19.804 MiB** |
| 可攜 Node.js `v24.18.0` | - | **88.25 MiB** |
| 最近一次完整零安裝 bundle（2026-08-09） | < 650 MiB | **368.01 MiB** |
| Unreleased 完整零安裝 bundle | < 650 MiB | **待乾淨重建；不預估** |

歷史 clean manifest 記錄 launcher 7,397,370 B、App+Python/Qt 99,338,066 B、
OpenClaw 194,011,520 B、Node 92,534,088 B、總計 385,883,674 B。目前 `dist/`
是 378.18 MiB，但含 10.156 MiB runtime residue，因此不是 release evidence。

已驗證的 Unreleased stage 為 165.162 MiB，必要 templates、`dist` 與 plugin
surfaces 都保持完整。修剪內部 `dist` chunks 會讓 app 耦合 OpenClaw 內部並
跨版本破壞 **核心 3**。已實作的安全候選為 PDB/tree-sitter headers（19.804 MiB）、
foreign-native payload（0.642 MiB）與 Pillow AVIF（7.471 MiB）；約 340.3 MiB
只是算術推估，不是實測 bundle。下一批 gated 候選是 win32ui/MFC（6.41 MiB，
保留 pythoncom/win32com SAPI）、未用 Qt plugins（約 3.87 MiB）及未用 Pillow
codecs（約 0.70 MiB）。新數字只會在 clean rebuild 與 packaged verifier 通過後發布。

## 📋 文檔

- [系統規格](spec.md) - 詳細系統規格書
- [架構說明](ARCHITECTURE.md) - 系統架構
- [憲法](CONSTITUTION.md) - 最高原則
- [變更日誌](CHANGELOG.md) - 版本歷史
- [路線圖](ROADMAP.md) - 功能規劃
- [真實測試 Runbook](REAL_TEST_RUNBOOK.md) - Live stack 測試
- [2026-09-02 驗證紀錄](docs/verification-2026-09-02.md) - 當前證據、失敗與未完成 gates
- [Evaluation cohorts](docs/evaluation-cohorts.md) - 9,922／128／partial corpus 身分與宣稱邊界
- [OpenClaw 2.x 決策](docs/openclaw-2x-decision-2026-09-02.md) - 2026.8.2 隔離證據與暫緩升級 gates
- [Clinical knowledge governance](clinical_knowledge/README.md) - Canonical YAML、人／agent 步驟與 SQLite parity
- [AGENTS.md](AGENTS.md) - 四大核心的 AI 維護守則
- [影像 agent harness 參考稽核](docs/harness-reference-review-2026-08-28.md) - 採用公開設計模式但不增加封裝 runtime 依賴
- [ECGFounder 工具契約](docs/ecgfounder-tool.md) - 外部波形證據邊界
- [2026-08-09 MEETI/OpenClaw 實驗紀錄](docs/meeti-openclaw-experiments-2026-08-09.md) - 真實 paired/unseen 結果、工具、SLA 與宣稱邊界
- [2026-08-05 驗證紀錄](docs/verification-2026-08-05.md) - MultiPass、真實 canary、座標、bundle hash 與阻擋項
- [GitHub Pages 原始碼](site/index.html) - 公開產品與證據網站

## 🎯 Copilot 自訂 Agents

14 個自訂 agent，含模型成本優化策略：

| Agent | 角色 | 模型 |
|-------|------|------|
| `architect` | 系統架構 + DDD | Sonnet 4.6 → GPT-5.4 |
| `code` | 功能實作 | Sonnet 4.6 → GPT-5.4 |
| `debug` | 根因分析 | Sonnet 4.6 → GPT-5.4 |
| `audit` | 深度審計（5 維度） | Opus 4.6 → Sonnet 4.6 |
| `orchestrator` | 任務拆解 + 委派 | Opus 4.6 → GPT-5.4 |
| `deep-thinker` | 複雜推理 + 算法 | Opus 4.6 → GPT-5.4 |
| `researcher` | 唯讀 codebase 探索 | Gemini 3.1 Pro → Sonnet 4.6 |
| `test-runner` 🆓 | 跑測試 + 迭代修復 | GPT-5.5 mini → GPT-5 mini → GPT-4.1 |
| `context-loader` 🆓 | 載入 Memory Bank + 摘要 | GPT-4.1 → GPT-5 mini |
| `ask` 🆓 | 專案問答 | GPT-4.1 → Haiku 4.5 |
| `review-panel` | 多模型審查委員會 | Opus 4.6（3 AI 交叉審查） |

> 🆓 = 免費模型 agent，用於大量嘗試的重複性任務

## 🔒 Pre-commit Hooks

透過 `.pre-commit-config.yaml` 配置 16+ hooks：

- **程式碼品質**：ruff lint + format、mypy
- **安全性**：bandit、gitleaks
- **慣例**：conventional-commits、commit-size-guard（≤30 檔案）
- **AI 維護**：skill-freshness-check、agent-freshness-check、memory-bank-reminder

## 🧪 測試支援

目前 repo 的測試配置包含：

- **靜態分析**：ruff、mypy、bandit
- **單元與 smoke 測試**：pytest，coverage floor 60%
- **整合測試**：pytest-asyncio 與 OpenClaw 公開 Gateway contract
- **Windows 原生 smoke**：opt-in rendered capture-exclusion 驗證
- **CI/CD**：4 個 OS/Python compatibility executions、1 個 pytest job，另有
  GitHub Pages deployment workflow

## 📄 授權

[Apache License 2.0](LICENSE)
## 2026-07-02 OOM-safe lint 補充

- `scripts\run-ruff-safe.cmd check ...` 是目前建議的 lint 入口；它固定使用
  既有 `.venv\Scripts\ruff.exe` 與 `data\tmp\ruff-run.lock`，
  避免裸 `uv run ruff` 重新碰到 AppData cache 或啟動第二個 `uv.exe`。
- `scripts\run-tests-safe.cmd` 會設定
  `DICOM_OVERLAY_TEST_DISABLE_REAL_OPENCLAW=1`，測試期間若誤觸真實
  OpenClaw Gateway 啟動會 fail fast；只有明確 real Gateway integration
  run 才應設定 `DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS=1`。
- `GatewayManager` 會在 OpenClaw subprocess 存活期間持有
  `data\tmp\openclaw-gateway.lock`；`scripts\test-real-stack.bat` 也不再用
  `cmd /k` 啟動 Gateway，改用 `start /B` 並寫入 `gateway.log`，降低多個
  `conhost.exe` 造成 OOM 的風險。MEETI real-experiment Python runner 也會在
  spawn OpenClaw Gateway 前拿同一個 lock，避免 GUI/手動 run 與實驗 run
  靜默多開 Gateway。

## 2026-07-02 OpenClaw plugin 邊界補充

- 可以把 OpenClaw 端影像框選/識別特化做成
  `dicom-overlay-agent-harness` plugin / skills；目前 manifest 已宣告
  bbox crop 二次判讀、coordinate drift calibration 與 overlay annotation
  能力。但桌面端仍只透過 Gateway `connect` / `chat.send` 溝通，不 import
  OpenClaw plugin SDK 私有 API，這樣才比較能相容不同 OpenClaw 版本。
