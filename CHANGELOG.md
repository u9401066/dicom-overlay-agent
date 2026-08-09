# Changelog

所有重要變更都會記錄在此檔案中。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/)，
專案遵循 [語義化版本](https://semver.org/lang/zh-TW/)。

## [Unreleased]

### Added

- **OpenClaw-owned subscription route**：新增 `OpenAI Subscription via OpenClaw`
  profile；以固定版官方 `@openclaw/codex` 只做 OAuth migration，live inference
  使用 `openai-chatgpt-responses`，並驗證/記錄 OpenClaw ownership、停用 Platform
  API key、排除 Codex agent runtime 與平台執行檔
- **9,922 例 blinded paired supervisor**：答案分離的 inference/gold manifests、
  baseline→candidate 原子狀態、來源/manifest/scorer/protocol fingerprint、resume、
  ownership gate、paired bootstrap/random-sign 統計及完整 raw/tool/crop/review
  artifact；發布前 289 筆 run 明確中止，正式 run 只接受發布後 frozen commit
- **MultiPass 影像判讀時間軸**：compact coarse read、原圖 crop/refine、deterministic
  EKG row/lead probes、rhythm pass、ECGFounder reconciliation、final disposition，
  每個 OpenClaw turn 可要求 `fastMode` 並記錄 60/100/180 秒 SLA
- **專家 review package**：桌面與 eval 匯出 source/result/marked PNG/exact crops/
  coordinate audit；diagnostic finding 與 dashed-cyan analysis crop 分開呈現
- **ECGFounder deterministic rhythm evidence**：sidecar 輸出 lead-II R-R interval、
  median-RR heart rate、CV/RMSSD/range 與 regularity，明確限制為 supporting-only
  rhythm measurement，不推論 P wave/AF、不提供影像定位
- **四臂 MEETI 實驗協定**：明確分離 minimal control、clinical single-pass、
  MultiPass、MultiPass+ECGFounder，保存 manifest/case/scorer/protocol digest、
  tool/crop/probe trace、bbox audit、review PNG 與 provider blocker；真實完成門檻
  為 strict pass 0.75、mean partial credit 0.85
- **凍結 Gateway 啟動 smoke**：`--gateway-smoke` 會在隔離副本產生 runtime-only
  loopback token，等待 bundled OpenClaw migration、完成 authenticated WebSocket
  connect、乾淨停止並確認無殘留 listener
- **人工確認的區域問答寫回**：AI 框與人工框可送出 exact crop 結構化追問；OpenClaw 只能建議 `ADD`／`REVISE`／`RETRACT`，不能控制座標，須按 Apply 才寫回 report/overlay/export，並保留 `interactive_ai_review`、result revision、chat request id、local signal 與 reviewer confirmation audit
- **ECGFounder 全分數研究評估**：offline runner 可保留完整 150 statement scores，新增 exact ontology mapping、protocol/hash 完整性檢查、deterministic five-fold out-of-fold evaluator 與 JSON/Markdown evidence；live OpenClaw tool 仍限制最多 20 筆 supporting predictions
- **Eligibility-aware waveform coverage**：完整遍歷的 ECGFounder cohort 可在顯式
  `--allow-ineligible` 下排除被 pinned 品質閘門拒絕的波形，報告仍保留 coverage、
  artifact id 與原因；預設模式維持 fail-closed
- **工具證據 UI**：Settings 顯示 secret-free waveform assist 配置狀態，Report 的 Process tab 顯示 ECGFounder status、prediction count 與 calibration state
- **多趟放大判讀（resolution-aware）**：`application/multi_pass.py`（`MultiPassInterpreter`）以完整 ROI 解析度重讀異常區域精修 bbox；當區域在截到的像素中太小（≤4K 截圖無法有意義數位放大）時，改以 `domain/entities.py` 新增的 `AnalysisResult.zoom_hints` 提示醫師在 viewer 內放大重截，`presentation/overlay_window.py` 以藍色 hint 標籤呈現
- **CXR 10 軸系統性判讀**：`domain/modality_profile.py` 擴充 CXR checklist 與 validator 強制；skills（`dicom-cxr-analysis`、`dicom-ekg-analysis`）prompt 強化
- **辨識評分與 can't-miss gate**：`infrastructure/eval_harness.py` + `scripts/run-eval.py` 以標註資料集計算 軸×嚴重度覆蓋率、pertinent-negative recall，並對漏掉致命診斷（STEMI／張力性氣胸等）以非零碼讓 CI 失敗；對真實資料強化解析容錯（list 形式 checklist、WS 16 MiB、downscale、User-Agent）
- **可攜帶 USB 即插即用 + 自我檢查**：`infrastructure/app_paths.py`（凍結時 runtime 路徑錨定執行檔資料夾而非 `cwd`）、`__main__.py` `--selfcheck` 旗標、`gateway_manager.py` `verify_runtime()`（檢查 Node.js／OpenClaw runtime／可寫 base／config.yaml，不啟 GUI、不呼叫 LLM），`tests/smoke/test_packaging_bundle.py` 驗證
- **四大核心維護章程**：`AGENTS.md` 定義 Core 1 圖層互動、Core 2 OpenClaw harness、Core 3 Gateway 協定相容、Core 4 最小封裝；README 同步章節
- **Core 2 完整判讀 harness**：`image_harness_smoke.py`（截圖 → `chat.send` 影像附件 → event stream → artifacts）、`image_harness_validator.py`（gateway 合約 + 影像 payload 驗證）、`scripts/run-image-harness-smoke.py`、`scripts/verify-image-harness.py`
- **多影像模態註冊表**：`domain/modality_profile.py`（`ModalityRegistry` + `build_registry`），支援 config 擴充模態（EKG/CXR/CT_BRAIN 內建），16-key 結果 schema 驗證
- **OpenClaw runtime 管理**：`infrastructure/openclaw_runtime.py`（`MIN_SAFE_OPENCLAW_VERSION`、manifest、protocol 3 影像附件 frame）、`scripts/stage-openclaw-runtime.ps1`、`scripts/fetch-node.ps1`（portable node）
- **設定 UI 與持久化**：`presentation/settings_dialog.py`、`infrastructure/desktop_settings_store.py`、`infrastructure/openclaw_settings.py`、`infrastructure/env_file.py`
- **評估 harness 與視覺探針**：`infrastructure/eval_harness.py`、`infrastructure/vision_probe.py`、`scripts/run-eval.py`、`scripts/fetch-eval-datasets.py`
- **PyInstaller 最小封裝**：`dicom-overlay-agent.spec`（排除 numpy/scipy/matplotlib、裁剪 Qt 模組、UPX、windowed）、`scripts/build-exe.bat`
- **Pre-commit Hooks**: 新增 `.pre-commit-config.yaml`（16+ hooks）
  - ruff lint + format、mypy、bandit、gitleaks、conventional-commits
  - 4 個自訂 hook：commit-size-guard、memory-bank-reminder、skill-freshness-check、agent-freshness-check
- **Copilot Agents**: 14 個 `.agent.md` 自訂 agent
  - 付費 agent：architect、code、debug、audit、orchestrator、deep-thinker、researcher
  - 免費 agent：test-runner（GPT-5 mini）、context-loader（GPT-4.1）、ask
  - 審查委員會：review-panel + 3 reviewer subagents（Claude + GPT + Gemini 交叉審查）
- **Copilot Prompts**: 5 個可重複使用 prompt（code-audit、code-review、pre-commit、security-scan、skill-health-check）
- **新 Skills**: code-audit（深度審計）、skill-health-check（健康檢查）

### Fixed

- **Crop/bbox 對位與 evidence binding**：crop-local bbox 先做 epsilon-safe 正規化
  再投影回 source frame；validator receipt 綁定最終 bbox multiset，低訊號、錯誤
  lead、越界、round-trip drift 或 rejected coarse box 均 fail closed
- **EKG 重複 finding**：study-level dedupe 只合併 exact-normalized rate/rhythm
  重複，優先保留真 rhythm strip/lead II grounded bbox；局部 ST morphology 永不
  因幾何重疊被折疊，並留下 retraction trace
- **真實模型 JSON 邊界**：新增有限、可稽核的 delimiter repair 與 parse retry，
  不完整 schema、無法復原 payload 與 timeout 仍保存為錯誤而非偽造判讀
- **MultiPass 報告一致性與 lead inventory**：no-delta refine 仍進行 final
  reconciliation；人工寫回同步 summary/triage/checklist；共用 typed parser
  正確辨認 `I`／`II`／`V1` 等 12-lead 名稱，避免 parser/UI/bbox 規則漂移
- **BBox evidence binding**：production receipt 改綁 exact source-image SHA、case
  nonce、turn/session 與 canonical coordinate digest；座標投影在進 overlay 前完成
  physical/logical round-trip，無效框 fail-closed
- **桌面首次 Gateway 啟動**：把 migration/startup 移出 Qt main thread，將
  180 秒 readiness budget 與推論 timeout 分離，並呈現 AI starting/ready/offline
  狀態；首次啟動自動建立本機 token，乾淨 bundle 不含 secret
- **空白區互動標註與多診斷誤合併**：低訊號 crop 不再能透過模型 `ADD`／`REVISE` 變成 finding；不同診斷標籤即使 bbox IoU 高也保持分離，不再只憑幾何位置合併
- **Windows stale Gateway lock**：改以 Win32 `OpenProcess/GetExitCodeProcess` 判斷 PID 存活，桌面程式與 MEETI runner 共用同一實作，修正異常中止後永遠誤判舊 PID 存活
- **多螢幕座標錯位（潛在 PHI 風險）**：主螢幕不在原點時 mss 截圖會擷取錯誤螢幕；新增螢幕原點 offset 貫穿 capture 與 control bar
- **modality 解析 fallback**：未知/缺漏 modality 改回退「請求時的 modality」並 log warning（不再靜默寫死 EKG）
- **config 字串防呆**：`checklist_keys`/`aliases` 單一字串不再被逐字元拆解

### Changed

- **弱標籤計分**：asserted concepts 才可進 strict/cannot-miss/urgent；未否定的
  uncertain candidate 只在 incomplete weak report 取得半權重並獨立呈現，explicit
  normal/WNL 可輸出零異常 finding
- **最新真實證據**：32-case paired weak-label partial credit 0.253→0.480
  （bootstrap 95% CI `[+0.085,+0.368]`，random-sign `p=0.00449955`）；8-case
  unseen 通過 schema/bbox/crop/projection/artifact/SLA，但保留 2 個 urgent miss，
  因此不宣稱醫療準確率或臨床安全
- **Portable release**：harness/plugin `1.5.7`、OpenClaw `2026.7.1-2`、Node
  `v24.18.0`；完整 bundle 368.01 MiB、launcher 7.05 MiB，source suite
  `915 passed, 3 skipped`，另通過 4/4 packaged smoke 與 native capture smoke
- mock perfect gate 現在明確只驗證 label-derived protocol self-test；真實 provider
  quota/auth/parser 失敗保留為 infrastructure blocker，不轉成病例答錯或部分分數
- 正式臨床分數只使用 asserted references；weak/partial references 另列探索性
  recall，明確 normal/within-range ECG 不被強迫產生異常 finding
- OpenClaw 影像分析停用 web search/fetch；臨床影像只使用有界的 app-native
  bbox 工具與選配、驗證過的 ECGFounder waveform tool
- 桌面程式、Gateway seed 與 MEETI runner 預設模型統一為
  `openai/gpt-5.4-mini`；Luna 與其他 API provider 保留為顯式 profile
- `test-runner` agent 模型優先序改為 `GPT-5.5 mini → GPT-5 mini → GPT-4.1`
- ruff 設定忽略 `RUF001`/`RUF003`（zh-TW 全形標點為正確排版，非錯字）
- 遷移 4 個 `.chatmode.md` 至 `.agent.md` 格式
- 更新 `copilot-instructions.md`（agents 表、免費模型策略、hook 表）
- 更新 `git-workflow.md` bylaws（Pre-commit Hooks 章節）
- `pywin32` 改為 Windows-only 條件式依賴，修正 Linux/CI 安裝失敗
- `OpenClawClient` 在缺少本地 token 檔案時允許無 token 建立，用於 mock 測試與 CI
- GitHub Actions `ci.yml` 改為實際驗證跨平台安裝相容性、依賴完整性與 pytest

### Removed

- 移除已 deprecated 的 `.chatmode.md` 檔案（architect、ask、code、debug）

## [0.1.0] - 2025-12-15

### Added
- 初始化專案結構
- 新增 Claude Skills 支援
  - `git-doc-updater` - Git 提交前自動更新文檔技能
- 新增 Memory Bank 系統
  - `activeContext.md` - 當前工作焦點
  - `productContext.md` - 專案上下文
  - `progress.md` - 進度追蹤
  - `decisionLog.md` - 決策記錄
  - `projectBrief.md` - 專案簡介
  - `systemPatterns.md` - 系統模式
  - `architect.md` - 架構文檔
- 新增 VS Code 設定
  - 啟用 Claude Skills
  - 啟用 Agent 模式
  - 啟用自定義指令檔案
