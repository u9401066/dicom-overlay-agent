# Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-12-15 | 採用憲法-子法層級架構 | 類似 speckit 的規則層級，可擴展且清晰 |
| 2025-12-15 | DDD + DAL 獨立架構 | 業務邏輯與資料存取分離，提高可測試性 |
| 2025-12-15 | Skills 模組化拆分 | 單一職責，可組合使用，易於維護 |
| 2025-12-15 | Memory Bank 與操作綁定 | 確保專案記憶即時更新，不遺漏 |
| 2026-03-06 | chatmode 遷移至 .agent.md | chatmode 已 deprecated，統一用 agent 格式 |
| 2026-03-06 | 免費模型獨立為專職 agent | GPT-5 mini/4.1 不當 fallback，跑量用獨立 agent（test-runner、context-loader） |
| 2026-03-06 | 多模型審查委員會 | Claude + GPT + Gemini 交叉審查，減少單一模型盲區 |
| 2026-03-06 | agent-freshness-check hook | 自動偵測退役模型、deprecated tools，維持 agent 配置健康 |
| 2026-03-12 | OpenClaw Gateway 作為 Agent Runtime | 管理 Vision API 呼叫、模型 failover、session memory，Python 只做 Eyes+Hands |
| 2026-03-12 | PHI 簡化為 ROI 設定 | DICOM viewer 版面固定，PHI 位置可預測，一次設定即可，移除 EasyOCR |
| 2026-03-12 | WebSocket 雙向通訊 | 非傳統MCP等待被呼叫，而是 local→agent→local 雙向流 |
| 2026-03-12 | Portable 部署模式 | Node.js portable + PyInstaller exe，USB 隨插即用 <150MB，不需 admin 安裝 |
| 2026-03-12 | 透明 Overlay（非 Side Panel） | 醫師判讀中無法切換視窗，必須疊在 DICOM viewer 上方且 click-through |
| 2026-03-12 | 自寫 PyQt6 Overlay | 市面無工具同時支援透明+click-through+部分互動區，~300 行即可實現 |
| 2026-03-12 | Region 語義名稱映射 | Vision LLM 回傳語義區域名（lead_V4、right_lower_lung），本地 RegionMapper 查表轉換為螢幕座標 |
| 2026-03-12 | 百分比矩形座標系 | 區域用 {x, y, w, h} 百分比表示，相對於 ROI 裁切後影像，定義在 config.yaml region_maps |
| 2026-03-12 | 新增 WS 訊息協定 | 定義 vision.analyze/result/error + model.failover 四種訊息類型 |
| 2026-03-12 | OpenClaw Skills 規劃 | 三個模態專用 skill（dicom-ekg/cxr/ct-brain-analysis），每個包含 prompt + 合法區域清單 |
| 2026-03-12 | 先用 mock OpenClaw 驗證 MVP | smoke test 採本地 websocket server 模擬 Gateway，先驗證 Python pipeline 與狀態機，再對接真實 OpenClaw |
| 2026-03-12 | debounce=0 視為即時觸發 | 便於 smoke test 與手動觸發場景，避免多一個 tick 才能送出分析請求 |
| 2026-03-12 | ROI wizard 先採單步拖曳式設計 | 優先落地 PHI-safe 設定流程，先不做多頁精靈，降低實作與測試成本 |
| 2026-03-12 | skills 先存放於 repo 內 openclaw/workspace | 便於版本控管與 portable 部署，之後再視實際 Gateway 安裝方式調整同步策略 |
| 2026-03-12 | OpenClaw 採 workspace-local 安裝 | 避免 `npm install -g` 汙染系統，CLI 改由 `openclaw/node_modules/.bin/openclaw.cmd` 啟動，並將 `HOME/USERPROFILE` 指向 repo 內 `openclaw-home` |
| 2026-03-14 | Hook/Guardrail 系統（類 MCP 防呆）| OpenClaw 操作軟體時沒有 MCP 強制驗證，自建 AnalyzeHook pipeline（pre/post）作為防呆層 |
| 2026-03-14 | MCP Adapter 對齊 openclaw-mcp-adapter | Python 側 McpAdapter 鏡像 OpenClaw 的 McpClientPool 架構（同 config schema、同 lifecycle、同 reconnect），確保與 gateway 插件一致 |
| 2026-03-14 | ToolCallResult 改為 content[] 格式 | 對齊 MCP 協議標準回傳格式（content blocks），而非自訂 success/data/error |
| 2026-03-15 | Gateway 自動啟動由 GatewayManager 管理 | 避免使用者手動啟動 Gateway subprocess，簡化 start.bat |
| 2026-03-15 | 獨立可拖曳 Panel（非固定在 Overlay） | SummaryPanel/ChatPanel 需要可移動到不遮擋閱讀的位置 |
| 2026-03-15 | EKG checklist 擴展到 16 項 | 5 項太少，16 項涵蓋系統性心臟病學評估（Rate/Rhythm/Axis/Intervals/ST/Chamber/Conduction/Artifact） |
| 2026-03-15 | 預設 phash + threshold 5 取代 ahash + 10 | ahash (8x8 brightness) 無法區分結構相似的 EKG 圖（相同 grid/label），phash (DCT) 對空間頻率更敏感 |
| 2026-03-15 | AI 動態 bounding box 取代固定 region map | 固定 4x3 grid 對不準實際 EKG 佈局，AI 回傳歸一化 0-1 座標更精確、更靈活 |
| 2026-04-10 | CI 以「可安裝 + 可測試」為主 | 先修正跨平台安裝與 mock token 問題，再讓 workflow 真正阻擋失敗 |
| 2026-07-05 | 真模型供應商改走 OpenAI 直連（gpt-5.5） | 本網路防火牆 reset openrouter.ai / api.anthropic.com；api.openai.com 可通且 key 有效，單題實測 strict_pass 1.0。Copilot 訂閱模型（MAI Flash）為 OAuth token 流，無法作 API 供應商 |
| 2026-07-05 | EKG harness 採「宣告，不要假設」lead-awareness | 25 題 strict_pass 0.24，漏題全是 lead-dependent。不硬塞 config standard_4x3 座標（會在非標準/局部/單導極圖災難性錯歸極）；改由模型讀印刷導極標籤建 inventory，結論鎖在實際導極上，保持通用。config standard_4x3 降級為可選先驗 |
| 2026-08-04 | ECGFounder 採條件式 loopback sidecar tool，不進主 bundle | 官方模型吃 500 Hz/10 秒 waveform、checkpoint 約 370 MB 且需要 Torch；MEETI 圖片有相符 raw waveform，可做明確配對。主 plugin 只傳 opaque artifact id，要求 hash/preprocessing/calibration provenance，禁止 screenshot-only 與 bbox 推導，保住封裝尺寸、OOM 與臨床可追溯性。 |
| 2026-08-04 | ECGFounder 桌面標示 evaluation-only，receipt 以 per-case nonce 歸因 | 目前只有 eval manifest 能可信任地配對圖片與 raw waveform；桌面不能從 screenshot 猜 artifact。每 case 需恰好一筆 nonce、artifact digest、官方 model revision/checkpoint 全相符的成功 receipt，否則記 infrastructure failure，避免跨程序 audit 或零/多次呼叫被誤算。 |
| 2026-08-04 | ECGFounder 未校準輸出只作 supporting evidence | 官方驗證程式會從有標註資料動態求各類 threshold，沒有發布可直接部署的固定 threshold；真實 canary 也出現與影像急性 ST concern 強烈分歧。因此分數只能做排序與分歧提示，不得覆寫影像結論或自行宣告陰性。 |
| 2026-08-04 | Overlay 座標改用 monitor-bound physical/logical frame | Win32/mss 與 Qt 使用不同座標系，primary DPR 無法處理負座標或 mixed-DPI。保存實際 `last_capture_rect`，以完整 Win32/Qt display bounds 做 X/Y edge 映射及 round-trip audit；bbox、static region、點框 QA、人工框選共用同一 original ROI frame。 |
| 2026-08-04 | 公開網站只用 synthetic ECG 與已驗證數字 | 不把 MEETI 病例衍生圖直接發布，也不以未完成的 MLLM JSON 宣稱準確率。GitHub Pages 明列 quota blocker、ECGFounder 未校準邊界與人工最終決策。 |
| 2026-08-04 | 現行 bundle 不宣稱 Windows 7 相容 | Python 3.13、PyQt6、Node 24 與最新 OpenClaw 無可信 Windows 7 支援路徑。Win7 若成為硬需求，必須是獨立 legacy runtime/bundle 與安全維護策略，不能假裝目前 EXE 已驗證。 |
| 2026-08-04 | MultiPass EKG 必須保留系統化 discovery turns | 只 crop coarse pass 已找到的 bbox 無法改善漏診；在 bounded budget 內固定從 original ROI 探查 limb/precordial 區，並以 trace/artifact gate 證明實際有跑，才符合 repo 的多輪核心。 |
| 2026-08-04 | GPT-5.4 Mini readiness 與 provider transaction 分開記錄 | model metadata/key/manifest 可證明可設定，但不能證明付費 API 真能回答。`openai-vision` 明確宣告 `text+image`；只有送出真圖並取得 provider response 才算 canary，額度失敗必須標 blocked。 |
| 2026-08-04 | Portable build 剔除並禁止所有 `.env*` | npm 相依可能夾帶開發用環境檔；即使內容無 secret 也不應出貨。staging 主動移除，packaged verifier 再 fail-closed，避免使用人工清單判斷。 |
| 2026-08-04 | Luna 成為預設但保留多 provider profile | 使用者指定 `openai/gpt-5.6-luna` 作為實戰多模態主路徑；桌面、Gateway seed、Python/PowerShell runner 統一預設，GPT-5.4 Mini/OpenRouter/Anthropic/Azure/compatible 仍可顯式選擇。catalog 能證明 image capability，額度 canary 失敗仍只能算 blocked。 |
| 2026-08-04 | ECGFounder threshold 只做 out-of-fold 研究評估 | MEETI 是弱報告標籤且沒有 patient id；只用 affirmative concepts，uncertain 不當正/負，abnormal 只對明確正常 control，五折門檻永不寫回 sidecar。避免同資料調參後宣稱 deployment accuracy。 |
| 2026-08-04 | Windows PID 存活檢查走 Win32 API | 本機證實 `os.kill(pid, 0)` 對已結束 PID 仍可能成功，造成 Gateway stale lock 永遠卡住。桌面與 runner 共用 `OpenProcess/GetExitCodeProcess`，access denied 保守視為存活。 |
| 2026-08-04 | 區域 AI 追問只能提案，人工 Apply 才能寫回 | 自由文字不能安全地改寫醫療 overlay。JSON-only contract 不接受模型座標，`ADD` 綁人工框、`REVISE/RETRACT` 綁既有 id/bbox；result revision 防舊回覆套錯影像，report triage 不因追問降級，所有套用保留 provenance 與 confirmation receipt。 |
| 2026-08-04 | 互動 finding 寫回採 deterministic local-signal gate | 座標正確不代表框內有影像證據。原始來源像素 crop 若低訊號、audit 缺失或失敗，仍允許 QA/人工匯出，但禁止任何 `ADD/REVISE/RETRACT`；不同診斷也不能只因 IoU 重疊就合併。 |
| 2026-08-05 | GPT-5.4 Mini 取代 Luna 成為 release default | 依使用者最後指定，桌面、Gateway seed、Python/PowerShell runner 統一為 `openai/gpt-5.4-mini`；Luna 保留為顯式 profile。catalog/image capability 與真實 provider transaction 分開記錄，額度失敗仍是 blocked。 |
| 2026-08-05 | 正式準確率只計 asserted references | MEETI 701 筆 weak/partial labels 只回報探索性 recall，299 筆 asserted references 才進 strict、partial、diagnosis 與 normal-specificity 正式分母，避免把報告沉默或不確定概念當成完整 ground truth。 |
| 2026-08-05 | Bbox receipt 綁定精確原圖與座標 payload | production receipt 必須同時吻合原圖 SHA-256、case nonce、turn/session 與 canonical exact-coordinate digest；舊 receipt 或只驗證範圍不再足以讓框進 overlay/export。 |
| 2026-08-05 | 壞波形以可見 coverage 排除，不強迫 ECGFounder 作答 | held-out evaluator 預設仍拒絕 non-ok；只有明確 `--allow-ineligible` 才能在確認 1,000 筆完整遍歷、status counts 與排除原因後計算 999 eligible metrics，並在 protocol/report 中保留 99.9% coverage 與全零 V5 exclusion。 |
| 2026-08-06 | Codex OAuth 只作 OpenClaw 訂閱 transport | 每張影像必須由 OpenClaw embedded agent 執行模型 turn、MultiPass 與工具；Codex app-server 不得代判。官方 Codex plugin 只暫時遷移 OAuth，live config 隨即移除，並以 runtime log 與 bundle verifier證明。 |
| 2026-08-06 | 正式 A/B 必須共享凍結來源指紋 | baseline 與 candidate 之間若修改 harness、prompt、scorer 或 UI，結果只能算探索性，不能做 paired improvement 宣稱。正式 supervisor 依序執行兩臂並記錄相同 shared invariants。 |
| 2026-08-06 | Safety miss 是實驗結果，不是 artifact corruption | 非 perfect 模式仍完整記錄 urgent/cant-miss 漏診與 verifier failure detail，但不強迫模型輸出異常；只有 release acceptance/perfect gate 才要求零 safety misses。 |
| 2026-08-06 | Codex extension discovery 不等於 Codex agent ownership | OpenClaw 會自動 discover bundled extension；正式證據必須是 embedded route 為 OpenAI model、subscription transport、零 app-server handoff marker，且磁碟上沒有 `@openai/codex` 或 `codex.exe`。只宣稱 plugin 未載入會與真實 log 不符。 |
| 2026-08-07 | 臨床多輪採 60/100/180 秒 hard SLA | coarse、首 crop/refine、整題各自有絕對 deadline；逾時保留最佳已完成結果並要求覆核，不讓 provider latency 無限延長，也不為趕時限強迫異常答案。 |
| 2026-08-07 | R-R timing 是節律規則性工具，不是 AF 診斷器 | 只有 deterministic irregular timing 加上 ECGFounder top-3 AF/flutter 才能觸發衝突覆核；若已有 lead-II finding 就升級合併，避免重複無框 finding。 |
| 2026-08-07 | 缺漏 EKG lead layout 必須有影像幾何佐證才修復 | 使用 RGB black-ink row periodicity 排除紅格線並確認 12 橫列；沒有 12-row 證據時保留 partial/3x4 狀態，禁止憑標準版型補座標。 |
| 2026-08-07 | 正式 scorer 必須區分否定、不確定與確診 | 被 `no/without/excludes/not confirmed` 約束的概念不算陽性；cautious finding 若只是重述 expected concept，也不能再製造 free-form false positive。原始 result JSON 不因 scorer 更新而改寫。 |
| 2026-08-07 | OpenClaw fastMode 不等同 provider priority tier | `chat.send.fastMode=true` 可由 trajectory 證明 Gateway 已接受，但 ChatGPT subscription native transport 會移除不支援的 `service_tier`。實驗只記 fast request；priority 必須由 verbose transport receipt 實際觀察，禁止由設定值推論。 |
| 2026-08-07 | Crop 只能裁決其實際涵蓋的證據 | 節律/ectopy/AV block 需連續 beats，傳導/缺血等需 declared multi-lead context；若實際 padded crop 未涵蓋 coarse finding 的全部 bboxes，局部 normal read 不得 RETRACT 整項，只能保留並記錄 coverage guard。 |
| 2026-08-07 | 修 prompt 後必須換未曝光 paired gate | 已人工檢視的 64 例只能作開發診斷，不能再證明 `1.4.9` 提升。新 gate 排除既有 1,080 與當前 64 identities，OpenClaw 只取得 answer-free inference manifest，gold 只供 run 後 scorer。 |
| 2026-08-07 | ECGFounder 每個 nonce 只允許一次 acquisition | 真實 coarse timeout 顯示 agent 可能違反 prompt 重複叫 tool。Plugin 以 bounded nonce cache 保證 sidecar 只執行一次；duplicate 取 cached compact result 並另記 suppression audit，成功 evidence receipt 仍恰好一筆。 |
| 2026-08-09 | 弱標籤 candidate concept 只給半權重且不進 safety gate | MEETI 報告可能只列候選診斷。明確不確定但未否定的概念可在 incomplete weak-label case 得 0.5 recall 權重；strict、cant-miss、urgent 仍只接受 asserted evidence，避免把試探性鑑別當成答對。 |
| 2026-08-09 | EKG study-level 節律重複採窄範圍 deterministic dedupe | 只處理 exact-normalized 的 rate/rhythm duplicate，優先保留 lead II 或真 rhythm strip 且有有效 bbox 的 finding；ST elevation 等局部 morphology 不合併，並留下 retraction trace，避免為了畫面整潔改動診斷內容。 |
| 2026-08-09 | 全量 MEETI 完成與小型真實證據嚴格分開 | 32-case paired pilot 顯示 weak-label partial score 顯著提升，8-case unseen 只證明新版工具鏈/SLA並揭露漏診；9,922 例未完成前不得宣稱完整資料集已跑完或醫療準確率已驗證。 |
| 2026-08-09 | 全量 paired run 只從發布後 frozen commit 起算 | 發布前 run 已有 289 baseline rows，但 commit 會改變 source fingerprint；因此主動中止並保留為 launch audit，正式 baseline/candidate 改用 `meeti-paired-full9922-v157-postpublish-v1`，兩臂完成前不再修改 scoped source。 |
| 2026-08-27 | Luna 實機驗收採顯式 override，不改 release default | v0.4.7 實機以 `openai-codex` model override 選 `openai/gpt-5.6-luna`，但產品、Gateway seed 與 paired runner 預設仍是 `openai/gpt-5.4-mini`；OAuth 只作 transport credential，OpenClaw 保持 agent ownership。 |
| 2026-08-27 | Transport/座標成功不得遮蔽判讀 miss | 2560×1600 / 150% DPI、ROI `(19,30,1522,1136)`、capture exclusion、≤0.368 px drift 與完整 Luna receipt 只證明工程路徑；錯判 AF/slow response、QT、R progression 與 inferior ST-T 必須明列 accuracy miss，fresh canary 前不作醫療準確率宣稱。 |
| 2026-08-27 | Gateway recovery 必須 acceptance-aware 且 charge-safe | 只重用通過公開 `connect` 的 Gateway，不終止未知 PID；只有尚未收到 acceptance 才可 bounded replay，避免 subscription 重複請求與不明程序破壞。 |
| 2026-08-27 | 10,001 scale gate 與臨床 cohort 分開 | 10,001 identities 僅驗證 completed/pending partition、fingerprint fail-closed 與 resume plumbing；canonical MEETI 仍是 9,922，禁止把規模測試寫成超過一萬張真實判讀成果。 |
| 2026-08-27 | OpenClaw 瘦身只修剪 runtime 周圍 | v0.4.7 保留並雜湊七個必要 upstream templates，禁止刪 `dist` chunks、`quickjs-wasi` 或 `playwright-core`；只移除 PDB、tree-sitter C/H 與 foreign native payload，已驗證 stage 165.162 MiB、減少 19.804 MiB，完整 bundle 待重建。 |
| 2026-08-27 | 產品 v0.4.7 與 harness/plugin 1.5.8 分版 | Python/product metadata 與 release tag 使用 v0.4.7；native harness manifest 使用 1.5.8；OpenClaw runtime pin 保持 2026.7.1-2，避免把產品、plugin 與上游 runtime 版本混為一談。 |
| 2026-08-28 | Refinement bbox receipt 需容忍 native append 可見性競態但仍 fail closed | Gateway final event 與 Windows JSONL 可見順序不保證；讀取器不得越過半行，boxed turn 最多等 0.5 秒再做 exact nonce/source/coordinate digest 驗證。`confirm` 也能更新/保留 bbox，因此不能再略過 receipt。等待只處理本機證據，不新增模型 turn。 |
| 2026-08-28 | 所有可信 precordial crop 都做平衡複核 | hypothesis id 不能決定是否檢查 R/S transition 與 ST-T。只改 prompt routing、不增加 turn；V1/V2 深 S 不足以判 PRWP，V3/V4 R dominance 需撤回，V2-V4 T/ST-T 需跨相鄰 beat/lead 重現並排除 noise。 |

---

## [2025-12-15] 採用憲法-子法層級架構

### 背景
需要一個清晰的規則層級系統，類似 speckit 但可擴展。

### 選項
1. 單一 copilot-instructions.md - 簡單但不夠靈活
2. 憲法 + 子法層級 - 清晰層級，可擴展
3. 全部放在 Skills 內 - 分散，難以管理

### 決定
採用選項 2：憲法-子法層級

### 理由
- 最高原則集中在 CONSTITUTION.md
- 細則可在 bylaws/ 擴展
- Skills 專注於操作程序
- 符合現實法律體系，易理解

### 影響
- 新增 CONSTITUTION.md
- 新增 .github/bylaws/ 目錄
- Skills 需引用相關法規
