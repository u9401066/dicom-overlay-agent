# DICOM Overlay Agent

> 🩺 一個自主協同判讀（co-reading）agent：在背景監控 DICOM viewer，將截圖交給 OpenClaw 判讀，再將 AI 發現疊加在原始影像上——最終診斷永遠由醫師決定。

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

🌐 [English](README.md)

## 2026-07-02 real-model smoke 狀態

- `scripts/check-real-model-readiness.cmd --dotenv .env` 會讀取 repo-local
  credential presence，但不輸出或寫入 secret value。OpenRouter MiniMax M3
  readiness 已為 `ready`：`OPENROUTER_API_KEY` 存在、1000-case mock artifact
  gate 已通過、OpenClaw runtime 為 `2026.6.11`。真實跑批前請加
  `--probe-provider`，會先檢查 provider egress 與模型是否 advertised image
  input；目前 probed readiness 會因 OpenRouter 連線 reset 而 blocked。
- `scripts/run-meeti-openclaw-experiment.cmd` 是目前建議的非 PowerShell
  實驗入口；它直接使用既有 uv-managed `.venv\Scripts\python.exe` 呼叫
  `scripts/run-meeti-openclaw-experiment.py` 產生 experiment-local OpenClaw
  config、啟動 Gateway、跑 eval、重建 scorecard 並匯出 review artifacts。
  它也會拿 `data\tmp\meeti-run.lock`，避免同時啟動第二個實驗 runner。
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

## 2026-07-02 OOM-safe uv / 題目測試入口

- 建議本機完整預設測試改用
  `scripts\run-tests-safe.cmd -q`。
  這個入口直接使用既有 uv-managed `.venv\Scripts\python.exe`，並把 `TMP`/`TEMP` 與
  pytest `--basetemp` 放到 `data\tmp\pytest-safe`，避免 AppData cache、
  pytest cacheprovider、進度輸出或大型暫存樹造成 PowerShell/uv OOM。最新修正
  會透過 `scripts\run_pytest_safe.py` 把預設 unit+smoke suite 拆成每個
  `test_*.py` 一個短生命週期 pytest process；像 `-q` 這種純 pytest option
  會套用到每個 batch，明確指定 `tests\unit\test_agent.py -q` 時才維持單一
  targeted pytest session。若要診斷舊的一次性 session 行為，可設
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

- 本機 OpenClaw runtime 已更新並驗證到 `2026.6.11`；仍只透過 Gateway
  `connect` + `chat.send` 與 OpenClaw 溝通，不匯入 OpenClaw plugin SDK
  內部 API。
- 桌面版 Settings 的 AI Provider 分頁支援 OpenRouter：
  `OPENROUTER_API_KEY` + `https://openrouter.ai/api/v1`，預設模型為
  MiniMax M3（`openrouter/minimax/minimax-m3`）。設定會寫入 OpenClaw
  managed provider/model 區段，API key 留在環境變數或 `.env`，不進 git。
- MEETI 生產級評估 gate 使用 Zenodo record `18523205` 的 `MEETI.rar`
  公開資料來源；本機 manifest 已能從約 1 萬張 ECG 影像建立至少 1000
  case，並透過 `run-eval.py`、`export-eval-annotations.py`、
  `verify-eval-artifacts.py` 驗證 scorecard、raw result、review PNG、
  bbox audit/crops 與 local image preflight。
- `local_image_quality` 是第一層非 MLLM 輔助：在送模型前/評估時記錄影像尺寸、
  aspect ratio、ink density、bright-pixel ratio 與 low-signal flag，避免
  所有品質判斷都拖到多模態語言模型。
- `local_signal_candidates` 是第二層本機輔助：用低成本像素 threshold 先產生
  ECG-like waveform / signal bbox 候選，供 harness 與人工 review 對照；它不做
  診斷，只提供 MLLM 前的可審計候選框。`run-eval.py --multi-pass` 現在會在
  coarse MLLM 判讀為非正常但沒有 bbox 時，把這些本地候選框餵給 crop
  re-analysis，避免框格流程完全依賴第一輪 MLLM 座標。`multipass-trace.jsonl`
  也會記錄 `local_candidate_count` 與 normalized `local_candidate_regions`，
  方便 1000 張跑批後做審計；trace 存在時，
  `scripts/verify-eval-artifacts.py` 也會以 `multipass_trace_artifacts` gate
  檢查這些欄位。
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
| 4 | **最小化執行檔封裝** | 極小的 `.exe` 啟動器（<50 MB，現為 6.75 MB）加上精簡、可攜帶、零安裝 bundle |

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
  解析的 static `region_maps`。
- **內容** — 可拖曳的 [`SummaryPanel`](src/dicom_overlay/presentation/overlay_window.py)
  顯示系統性 checklist（EKG 共 16 鍵、CXR 為 10 軸判讀），異常項優先、正常項摺疊；
  [`ChatPanel`](src/dicom_overlay/presentation/overlay_window.py) 讓醫師針對同一張影像追問。
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

### 核心 3 — OpenClaw plugin 兼容性

App **只透過穩定的公開 Gateway 協定**（`connect` + `chat.send`）溝通，
不 import plugin SDK 內部，因此能跨 OpenClaw 版本可攜。

- [`openclaw_runtime.py`](src/dicom_overlay/infrastructure/openclaw_runtime.py)
  釘住 `MIN_SAFE_OPENCLAW_VERSION`（`2026.4.22`），並依文件化 schema
  建立 harness manifest / chat frame（protocol `3`，image 在
  `params.attachments[]`，含 `type` / `mimeType` / `content`）。
- [`openclaw/package.json`](openclaw/package.json) 追蹤 runtime 版本
  （`openclaw ^2026.5.27`）與最低安全版本下限。
- [`manifest.json`](openclaw/workspace/plugins/dicom-overlay-agent-harness/manifest.json)
  宣告 plugin 兼容區間。
- **規則：** 升級 OpenClaw 前先確認 `connect` / `chat.send` schema 與 image
  attachment 格式未變；只有發現真正不兼容時才拉高下限。

### 核心 4 — 最小化執行檔封裝

目標是一個極小的啟動器與精簡、可從 USB 隨身碟執行的可攜帶 bundle，
以 [`scripts/build-exe.bat`](scripts/build-exe.bat) 建置。

- [`dicom-overlay-agent.spec`](dicom-overlay-agent.spec) 排除未用的重量函式庫
  （`numpy`、`scipy`、`matplotlib`、`pandas`、`imagehash`），並修剪 overlay
  從不載入的 Qt 模組（WebEngine、Qml/Quick、Pdf、Multimedia、~20 MB 的
  `opengl32sw.dll` 軟體 GL fallback、qml/translations 資料），啟用 UPX，
  建為 windowed（`console=False`）。
- [`scripts/stage-openclaw-runtime.ps1`](scripts/stage-openclaw-runtime.ps1)
  化 *slim* OpenClaw runtime，移除非 Windows 原生載荷與停用的
  UI / browser / voice plugins，只保留 Gateway 面。
- [`scripts/fetch-node.ps1`](scripts/fetch-node.ps1) 下載可攜帶
  `node\node.exe`；存在時會被打包，且
  [`gateway_manager.py`](src/dicom_overlay/infrastructure/gateway_manager.py)
  會優先使用它而非系統 Node.js，達成真正零安裝。
- `pywin32` 為 Windows-only 條件依賴，保持 Linux/CI 安裝乾淨。
- **可攜帶即插即用** — 凍結（frozen）時，runtime 路徑透過
  [`app_paths.py`](src/dicom_overlay/infrastructure/app_paths.py) 錨定到
  執行檔所在資料夾（而非啟動 `cwd`，後者可能是 `System32`），因此 bundle 能在
  全新機器上從 USB 隨身碟原樣執行。執行 `DICOMOverlayAgent.exe --selfcheck`
  即可驗證 Node.js、OpenClaw runtime、可寫入 base 與 `config.yaml` 全部就緒——
  不啟動 GUI、不呼叫 LLM（exit 0 = 就緒）。

**體積預算（實測）：**

| 產物 | 預算 | 現況 |
| --- | --- | --- |
| `DICOMOverlayAgent.exe` 啟動器 | < 50 MB | **6.75 MB** ✅ |
| App + Python/Qt 層（不含 vendored OpenClaw） | < 100 MB | **~89 MB** ✅ |
| 含 vendored OpenClaw runtime 的完整 bundle | — | **~205 MB** |
| + opt-in 可攜帶 Node.js | — | + ~30 MB |

vendored OpenClaw runtime（~114 MB）刻意保持完整：修剪其內部 `dist`
chunks 會讓 app 耦合 OpenClaw 內部、跨版本破壞 **核心 3**。我們只修剪它
*周圍* 的一切。

## 📋 文檔

- [系統規格](spec.md) - 詳細系統規格書
- [架構說明](ARCHITECTURE.md) - 系統架構
- [憲法](CONSTITUTION.md) - 最高原則
- [變更日誌](CHANGELOG.md) - 版本歷史
- [路線圖](ROADMAP.md) - 功能規劃
- [真實測試 Runbook](REAL_TEST_RUNBOOK.md) - Live stack 測試
- [AGENTS.md](AGENTS.md) - 四大核心的 AI 維護守則

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

模板包含完整的測試配置：

- **靜態分析**：ruff、mypy、bandit
- **單元測試**：pytest，80% 覆蓋率要求
- **整合測試**：pytest-asyncio
- **E2E 測試**：Playwright
- **CI/CD**：GitHub Actions，6 個 jobs

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
