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
| 2026-08-04 | ECGFounder 未校準輸出只作 supporting evidence | 官方驗證程式會從有標註資料動態求各類 threshold，沒有發布可直接部署的固定 threshold；真實 canary 也出現與影像急性 ST concern 強烈分歧。因此分數只能做排序與分歧提示，不得覆寫影像結論或自行宣告陰性。 |
| 2026-08-04 | Overlay 座標改用 monitor-bound physical/logical frame | Win32/mss 與 Qt 使用不同座標系，primary DPR 無法處理負座標或 mixed-DPI。保存實際 `last_capture_rect`，以完整 Win32/Qt display bounds 做 X/Y edge 映射及 round-trip audit；bbox、static region、點框 QA、人工框選共用同一 original ROI frame。 |
| 2026-08-04 | 公開網站只用 synthetic ECG 與已驗證數字 | 不把 MEETI 病例衍生圖直接發布，也不以未完成的 MLLM JSON 宣稱準確率。GitHub Pages 明列 quota blocker、ECGFounder 未校準邊界與人工最終決策。 |
| 2026-08-04 | 現行 bundle 不宣稱 Windows 7 相容 | Python 3.13、PyQt6、Node 24 與最新 OpenClaw 無可信 Windows 7 支援路徑。Win7 若成為硬需求，必須是獨立 legacy runtime/bundle 與安全維護策略，不能假裝目前 EXE 已驗證。 |

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
