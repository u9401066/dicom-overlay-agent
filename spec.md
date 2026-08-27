# DICOM Overlay Agent — 系統規格書

**Version:** 0.4.7
**Date:** 2026-08-28
**Author:** 寧寧 (AI Research Assistant, KMUH Anesthesiology)

---

## 0. Current Implementation Binding

### 0.1 2026-08-27 acceptance binding

本輪交付不得只以 mock、headless 或單元測試代替產品驗收，必須同時留下：

- Windows 封裝 GUI 實際啟動、OpenClaw Gateway ready、測試影像在 viewer 中
  可見，以及 overlay/report 實際渲染的桌面截圖證據。
- 精確模型路由 `openai/gpt-5.6-luna`（底層 model id
  `gpt-5.6-luna`）的真實影像交易、每階段延遲、request/token usage 與可重算成本；
  若外部帳號、訂閱或額度阻擋，必須保留 provider receipt 並明確標成 blocked，
  不得用 mock 結果替代。
- Smoke、ROI capture exclusion、16-key schema、Gateway event correlation、bbox
  邊界/投影、deadline degradation 與 interrupted/resume 的 edge regressions。
- 速度與正確率變更先通過未曝光 blinded canary；9,922 張正式 paired run 僅能在
  source fingerprint 凍結、驗證、commit 且 push 後啟動，並可原子續跑。任何小樣本、
  weak-label 或 waveform-only 結果不得宣稱為臨床正確率。
- 封裝瘦身必須維持四核心、公開 Gateway 邊界與現有 banned-content gate；不得刪除
  OpenClaw 內部 `dist` chunks。網站、雙語 README、runbook、release evidence 與實際
  bundle 數字需同步，並以分段 Conventional Commit、tag 與 GitHub Release 發布。

本長篇規格保留早期產品設計與 prior-art 背景；以下條款覆蓋後文仍存在的舊版
模型、延遲、封裝尺寸與自訂 WebSocket 範例：

- 桌面程式只透過 OpenClaw 公開 `connect` / `chat.send` protocol 3 傳送影像，
  agent loop 由 OpenClaw embedded agent 擁有；不提供繞過 Gateway 的 direct-API
  fallback。
- Release default 仍為 `openai/gpt-5.4-mini`；本輪真實桌面驗收透過顯式
  `openai-codex` model override 選擇 `openai/gpt-5.6-luna`，沒有改動全域預設。
  ChatGPT/Codex subscription OAuth 只作 transport credential；官方 Codex
  migration provider 不作影像判讀，bundle 亦不得包含或啟用 Codex agent runtime。
- 預設開啟 app `MultiPassAnalyzer`：完整圖 coarse read、原圖 crop/refine、EKG
  systematic/rhythm probe、選配 ECGFounder waveform evidence 及 final
  reconciliation。SLA 目標為首次概略 60 秒、首次 crop/detail 100 秒、整題
  180 秒，所有回合可顯式要求 OpenClaw `fastMode`。
- Bbox 必須綁定來源 digest/nonce/session/tool receipt，經 source-pixel crop、
  parent projection 與 physical/logical round-trip 校正；匯出包含 marked PNG、
  exact crops 與 coordinate audit。
- MEETI 的正式比較使用分離的 9,922-case inference/gold manifests，由 paired
  supervisor 在 frozen source fingerprint 上跑 minimal baseline 與完整 candidate。
  weak-label partial credit、strict、normal specificity、urgent/cannot-miss、schema、
  bbox 與 SLA 分開報告，不把正常 ECG 強迫判成異常。
- 2026-08-09 portable bundle 為 368.01 MiB，launcher 7.05 MiB，含 OpenClaw
  `2026.7.1-2`、Node `v24.18.0` 與 harness/plugin `1.5.7`。
- v0.4.7 產品 metadata 為 `0.4.7`、harness/plugin 為 `1.5.8`，OpenClaw pin
  維持 `2026.7.1-2`。已驗證 staged OpenClaw runtime 為 165.162 MiB，比先前
  stage 保守減少 19.804 MiB；最終完整 bundle 尚未乾淨重建，不預估總尺寸與 hash。
- 實機證據來自 2560×1600 / 150% DPI 桌面與 physical ROI
  `(19, 30, 1522, 1136)`：五個 Luna 影像回合耗時 146.915 秒、111,833 total
  tokens、subscription API charge US$0、API 等值約 US$0.017135；bbox 無 clamp，
  最大 edge drift ≤0.368 px，capture exclusion 正常。
- 此次模型把 reference 的 atrial fibrillation with slow ventricular response、
  prolonged QT、poor R-wave progression 與 inferior ST-T changes 判成 sinus
  rhythm／possible LVH。這是 accuracy miss，不得用 transport、UI 或座標成功
  包裝成醫療正確率成功；fresh unseen canary 尚待 final frozen source 完成後補值。
- 後續 answer-free 兩例 canary 以 1,222-ID denylist 通過 schema、bbox、SLA 且
  零 JSON repair，但 strict 只有 1/2、mean partial 0.522；warning 例漏掉弱標籤
  LVH 與 asserted sinus rhythm。該次 fingerprint 為 `dirty=true`，因此只算
  pre-release bounded evidence，不能取代 final frozen-source canary。

執行細節以 [`ARCHITECTURE.md`](ARCHITECTURE.md)、
[`REAL_TEST_RUNBOOK.md`](REAL_TEST_RUNBOOK.md) 與
[`docs/meeti-openclaw-experiments-2026-08-09.md`](docs/meeti-openclaw-experiments-2026-08-09.md)
為準。

---

## 1. 專案概述

### 1.1 背景與動機

醫師判讀醫學影像（EKG、CXR、CT）本身需要 30 秒至數分鐘。AI 介入的目的**不是取代判讀**，而是作為系統性 second-check，降低因疲勞、忙碌或注意力分散造成的遺漏率。

### 1.2 設計理念

**Autonomous Agent Co-reading Model**

Agent 不是被動等待醫師透過聊天觸發，而是**主動監控、主動識別、主動標注**。醫師只需要正常操作 DICOM viewer，Agent 在背景持續運作，影像一更新就自動分析並疊加報告。

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│   Agent 主動監控 + 主動標注 + 主動報告                │
│   醫師正常操作，無需觸發                              │
│                                                     │
│   • Agent 持續監控 DICOM viewer 影像變化              │
│   • 影像更新 → 自動截圖 → 自動分析 → 透明 Overlay     │
│   • 醫師看原始影像，AI 標注疊加在上方                  │
│   • 小型 Control Bar 提供暫停/設定/手動重觸發          │
│   • 最終診斷決定權永遠在醫師                          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 1.3 核心限制（Constraints）

| 限制 | 原因 | 因應方式 |
|------|------|---------|
| 無法直接存取 HIS | 安全協議封鎖 API 連線 | 螢幕截圖作為唯一輸入來源 |
| DICOM Viewer 為 DLL-based | 台灣廠商系統，無瀏覽器 DOM 可操作 | OS 層級視窗截圖 |
| PHI 保護 | 病人個資不可離開院內環境 | 使用者首次設定 ROI 截圖範圍，裁切已知 PHI 區域 |
| Vision model 量化限制 | 截圖非原始訊號，無法精確測量數值 | 輸出定性描述 + 區域標注，非精確數值 |

---

## 2. 系統架構

### 2.1 總覽

```
╔══════════════════════════════════════════════════════════════════════════╗
║                        醫師工作站（Windows）                              ║
║                                                                          ║
║  ┌───────────────────┐   ┌──────────────────────────────────────┐        ║
║  │  DICOM Viewer      │   │  DICOM Overlay Agent（Python）        │        ║
║  │  (DLL-based, HIS)  │   │  背景常駐，截圖+Overlay 渲染           │        ║
║  │                    │   │                                      │        ║
║  │  ┌──────────────┐  │   │  ┌──────────────────┐                │        ║
║  │  │ 影像顯示區域  │  │   │  │  螢幕監控模組     │                │        ║
║  │  │ (EKG/CXR/CT) │◄─┼───┼─►│ (自動偵測+debounce)│                │        ║
║  │  └──────────────┘  │   │  └────────┬─────────┘                │        ║
║  │                    │   │           │                           │        ║
║  └────────────────────┘   │           ▼                           │        ║
║           ▲                │  ┌──────────────────┐                │        ║
║           │ click-through  │  │  截圖 + ROI 裁切  │  ← 首次設定   │        ║
║           │ 完全穿透        │  └────────┬─────────┘                │        ║
║  ┌────────┴──────────┐    │           │ WS                       │        ║
║  │  透明 Overlay 圖層 │    │           ▼                           │        ║
║  │                    │    │  ┌──────────────────────────────┐    │        ║
║  │  ► 區域高亮標注    │◄───┼──│  RegionMapper                │    │        ║
║  │  ► 定性描述標籤    │    │  │  finding.regions[] → QRect  │    │        ║
║  │  ► 摘要側欄面板    │    │  └──────────────────────────────┘    │        ║
║  │                    │    │                                      │        ║
║  ├────────────────────┤    └──────────┬───────────────────────────┘        ║
║  │ [Control Bar]      │               │ WebSocket                         ║
║  │ ⏸ 暫停 │ ⚙ 設定   │               │ ws://127.0.0.1:18789              ║
║  │ 🔄 重觸發│ 📊 歷史 │               ▼                                   ║
║  └────────────────────┘    ┌──────────────────────────────────────┐        ║
║                            │  OpenClaw Gateway（Node.js 常駐）     │        ║
║                            │                                      │        ║
║                            │  ► Skills（DICOM 分析 prompts）       │        ║
║                            │  ► Model failover（Opus 4.6 → GPT-4o）│        ║
║                            │  ► Session 管理 + 用量追蹤             │        ║
║                            │  ► Hooks + Agent 進階處理              │        ║
║                            │  ► 連線 api.anthropic / api.openai    │        ║
║                            └──────────────────────────────────────┘        ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

### 2.2 資料流（全自動 Pipeline）

```
Step 1: 自主監控（持續運行）
  螢幕監控模組 持續監看 DICOM viewer 視窗
  偵測方式：
    a) 自動：影像區域 perceptual hash 變化（debounce 穩定後觸發）
    b) 手動：Control Bar 上的 🔄 按鈕 或 快捷鍵
  醫師無需任何操作，Agent 全自動運行

Step 2: 截圖與 ROI 裁切
  擷取影像顯示區域（pywin32 定位 + mss 截圖）
  依據使用者首次設定的 ROI 範圍，裁切已知 PHI 區域（上/下/左/右 N px）
  DICOM viewer 版面固定，PHI 位置可預測，一次設定即可
  輸出：去識別影像 PNG bytes（僅存在記憶體）

Step 3: 模態偵測 + 非同步分析（透過 OpenClaw Gateway）
  自動偵測影像模態（EKG / CXR / CT），或使用 Control Bar 手動切換
  透過 WebSocket 將去識別影像送至 OpenClaw Gateway
  OpenClaw 使用對應 Skill（modality-specific prompt）+ 內建 model failover
  附帶合法區域名稱清單（injected into system prompt）
  預期延遲：3–8 秒
  主執行緒不阻塞（醫師照常操作 viewer）

Step 4: Region 映射 + Overlay 渲染（主動疊加）
  OpenClaw 回傳 JSON（findings + 區域名稱）
  RegionMapper 查表將區域名稱轉換為螢幕座標
  Overlay 視窗自動繪製：
    - 區域高亮（highlight 問題區域，非精確箭頭）
    - 定性描述標籤（嚴重度色碼）
    - 固定側欄摘要面板（checklist 格式）
  Overlay 為 click-through（滑鼠完全穿透到 DICOM viewer）

Step 5: 持續循環
  標注顯示 30 秒後自動淡出
  Agent 繼續監控，下一張影像切換時自動重新分析
  Control Bar 提供：暫停/恢復、手動重觸發、設定調整
```

---

## 3. 模組規格

### 3.1 螢幕監控模組

**職責：** 自主偵測 DICOM viewer 視窗並判斷影像是否更新，無需醫師介入

```
輸入：
  - 目標視窗標題關鍵字（可設定）
  - 監控區域座標（可設定或自動偵測）
  - 觸發靈敏度（hash 差異閾值）

輸出：
  - 事件：ImageChanged(window_rect, timestamp)

視窗偵測：
  使用 pywin32 (win32gui) 遍歷視窗
  比 pygetwindow 更可靠，能處理 DLL-based MDI 視窗
  支援 FindWindow / EnumWindows 找到子視窗

觸發邏輯（Debounce 機制）：
  每 500ms 對影像區域取樣
  計算 average hash（ahash，比 phash 快，醫學影像不需過於敏感）
  若與上次 hash 差異 > 閾值：
    → 不立即觸發，等待 hash 穩定 1.5 秒（避免 progressive rendering 過程中多次觸發）
    → 穩定後才觸發截圖
  過濾：UI-only 變化（如捲軸、工具列點擊）不觸發

視窗位置追蹤：
  使用 SetWinEventHook 監聽 EVENT_OBJECT_LOCATIONCHANGE
  視窗移動/縮放時同步更新 Overlay 位置
```

### 3.2 截圖與 ROI 去識別模組

**職責：** 安全擷取純影像，依據使用者設定的 ROI 裁切 PHI

```
輸入：
  - window_rect（視窗位置與大小）
  - ROI 裁切設定（各邊 px 數，首次使用時設定）

輸出：
  - 去識別後影像（PNG bytes）

去識別流程（單層 ROI 裁切）：

  ┌─────────────────────────────┐
  │▓▓▓▓ 裁切區（患者資訊）▓▓▓▓▓│ ← crop_top px
  ├─────────────────────────────┤
  │                             │
  │     純醫學影像區域            │ ← 保留並送出
  │                             │
  ├─────────────────────────────┤
  │▓▓▓▓ 裁切區（狀態列）▓▓▓▓▓▓▓│ ← crop_bottom px
  └─────────────────────────────┘

  設計理由：
  - DICOM viewer 版面固定，PHI 位置可預測（姓名/病歷號始終在固定位置）
  - 使用者首次啟用時設定 ROI 範圍，後續自動套用
  - 比 OCR 方案更快、更可靠、更輕量
  - 首次設定時提供預覽畫面，讓使用者確認裁切範圍

首次 ROI 設定 UI 流程：

  Step 1: 啟動設定精靈
    程式偵測到尚無 phi_roi 設定（或使用者點選⚙設定）
    → 顯示半透明 overlay 覆蓋在 DICOM viewer 上

  Step 2: 拖曳框選安全區域
    ┌─────────────────────────────────────┐
    │▒▒▒▒▒▒▒▒ 紅色遮罩 ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒│
    │▒▒┌─────────────────────────────┐▒▒│
    │▒▒│                             │▒▒│
    │▒▒│   拖曳選擇安全區域（綠框）    │▒▒│ ← 此區域送出分析
    │▒▒│                             │▒▒│
    │▒▒└─────────────────────────────┘▒▒│
    │▒▒▒▒▒▒▒▒ 紅色遮罩 ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒│
    └─────────────────────────────────────┘
    紅色遮罩區 = 會被裁切（含 PHI）
    綠色框內 = 保留送出的影像區域

  Step 3: 預覽確認
    顯示裁切後結果預覽（去識別影像）
    讓使用者檢查是否還有殘留 PHI
    自動計算 top/bottom/left/right px 值

  Step 4: 儲存
    寫入 config.yaml 的 phi_roi 區塊
    顯示「設定完成，開始監控」

  重新設定：Control Bar ⚙ → 「調整裁切範圍」

設定範例（config.yaml）：
  phi_roi:
    top: 60      # px
    bottom: 30   # px
    left: 0      # px
    right: 0     # px
```

### 3.3 OpenClaw Gateway 整合模組

**職責：** 透過 OpenClaw Gateway 分析截圖並回傳結構化 findings

**運作方式：**
- Python Overlay Agent 透過 WebSocket 連線 OpenClaw Gateway（`ws://127.0.0.1:18789`）
- OpenClaw 提供 Skills 平台（DICOM 分析 prompts 定義為 workspace skills）
- OpenClaw 內建 model failover、session 管理、用量追蹤
- OpenClaw 支援 Hooks 前後處理、Agent 進階邏輯

**支援模型（由 OpenClaw 管理）：**
- Claude Opus 4.6（首選，推理能力最強）
- GPT-4o（自動 failover 備援）

**OpenClaw Skills 規劃：**
- `dicom-ekg-analysis` — EKG 12-lead 判讀 skill
- `dicom-cxr-analysis` — CXR PA/AP 判讀 skill
- `dicom-ct-brain-analysis` — CT Brain axial 判讀 skill
- 每個 skill 包含 modality-specific prompt + 合法區域名稱清單

**回傳 JSON 格式：**

```json
{
  "modality": "EKG",
  "analysis_time_ms": 4230,
  "summary": "Sinus rhythm with borderline QTc prolongation",
  "severity": "warning",
  "findings": [
    {
      "id": "f1",
      "regions": ["lead_V3", "lead_V4"],
      "label": "QTc borderline prolonged",
      "detail": "Precordial leads show borderline QTc prolongation. Review QT-prolonging medications.",
      "severity": "warning"
    },
    {
      "id": "f2",
      "regions": ["rhythm_strip"],
      "label": "Sinus Rhythm",
      "detail": "Regular rate ~72 bpm, normal P-wave morphology",
      "severity": "normal"
    }
  ],
  "checklist": {
    "rate": { "value": "~72 bpm", "status": "normal" },
    "rhythm": { "value": "Sinus", "status": "normal" },
    "pr_interval": { "value": "normal", "status": "normal" },
    "qrs_duration": { "value": "narrow", "status": "normal" },
    "qtc": { "value": "borderline prolonged", "status": "warning" },
    "axis": { "value": "normal", "status": "normal" },
    "st_changes": { "value": "none", "status": "normal" },
    "t_wave": { "value": "normal", "status": "normal" }
  }
}
```

**Region 映射機制：**
- Vision model 回傳語義區域名稱（如 `lead_V4`、`right_lower_lung`），不回傳座標
- 本地 RegionMapper 查表將名稱轉換為螢幕百分比矩形
- 區域定義在 config.yaml 的 `region_maps` 區塊，可客製化
- 未知區域名稱自動 fallback 到 `general`（僅顯示於 checklist，不高亮）

### 3.4 Overlay 渲染模組

**職責：** 在 DICOM viewer 上方自動疊加視覺標注 + 提供小型 Control Bar

**技術：** PyQt6 透明視窗

```
視窗屬性：
  - FramelessWindowHint（無邊框）
  - WindowStaysOnTopHint（永遠在最上層）
  - WA_TranslucentBackground（背景透明）
  - WA_TransparentForMouseEvents（滑鼠穿透，Overlay 區域）
  - Tool（不出現在工作列）
  注意：Control Bar 區域不穿透，允許點擊互動

元素 A：區域高亮標注（而非精確箭頭）

  將影像區域劃分為語義區塊（依模態）：
  ┌───────────────────────────────┐
  │ EKG 範例：                        │
  │                                 │
  │  ┌───────┐ ┌───────┐ ┌───────┐ │
  │  │ I  ✅  │ │ aVR ✅ │ │ V1 ✅  │ │  ← 每 lead 獨立區域
  │  └───────┘ └───────┘ └───────┘ │
  │  ┌───────┐ ┌───────┐ ┌───────┐ │
  │  │ II     │ │ aVL    │ │ V4 ⚠️ │ │  ← 異常區域黃色高亮
  │  └───────┘ └───────┘ └───────┘ │
  └───────────────────────────────┘

元素 B：固定側欄摘要面板（螢幕右側 300px）

    ┌──────────────────────────────┐
    │ 🫀 EKG Analysis              │
    │ ─────────────────────────── │
    │ Rate    ~normal         ✅     │
    │ Rhythm  Sinus           ✅     │
    │ PR      normal          ✅     │
    │ QRS     narrow          ✅     │
    │ QTc     borderline      ⚠️    │
    │ Axis    normal          ✅     │
    │ ST      no changes      ✅     │
    │ ─────────────────────────── │
    │ ⚠️ Review QT-prolonging drugs │
    └──────────────────────────────┘

元素 C：小型 Control Bar（Overlay 底部或右下角）

    ┌─────────────────────────────────────┐
    │  ⏸ 暫停  │  🔄 重分析  │  ⚙ 設定  │  📊  │
    │  EKG 模式 │  3.2s ago  │          │       │
    └─────────────────────────────────────┘
    ↑ 不穿透，可點擊
    功能：
      - ⏸/▶ 暫停/恢復自動監控
      - 🔄 手動重新觸發分析
      - 模態切換（EKG/CXR/CT/Auto）
      - ⚙ 開啟設定視窗（裁切區域、API key）
      - 📊 顯示最近分析歷史
      - 上次分析時間戳

嚴重度色碼：
  🔴 critical   — 紅色（STEMI、VF 等）
  🟡 warning    — 黃色（borderline、需注意）
  🟢 normal     — 綠色（正常）
  ⚪ info       — 灰色（描述性，非異常）

動畫：
  - 出現：0.3s fade-in
  - 消失：30s 後 2s fade-out（或 Control Bar 手動關閉）
  - critical finding 持續顯示，不自動淡出
```

### 3.5 Agent 狀態機

```
狀態定義：

  INIT ────────┬─ ROI 未設定 ──→ SETUP
                │                   │
                │              完成設定
                │                   │
                ▼                   ▼
  WAITING ─────────────────────── ←─ DICOM viewer 未開啟
     │
     │ viewer 偵測到
     ▼
  MONITORING ──┬─ hash 變化 + debounce 穩定 ─→ CAPTURING
              │                                    │
              │ 暫停按鈕                       截圖+裁切完成
              ▼                                    ▼
  PAUSED      │                              ANALYZING
     │        │                                    │
     │ 恢復    │                           API 回傳結果
     └────────┘                                    ▼
                                             DISPLAYING
                                                  │
                                             30s 淡出
                                                  ▼
                                      ──→ MONITORING

  錯誤轉換：
    任何狀態 + OpenClaw 斷線 ─→ RECONNECTING ─→ MONITORING
    任何狀態 + viewer 關閉 ─→ WAITING
    ANALYZING + timeout ─→ ERROR ─→ MONITORING

狀態屬性：
  - INIT: 程式啟動，檢查設定檔
  - SETUP: ROI 設定精靈（拖曳框選 + 預覽確認）
  - WAITING: 等待 DICOM viewer 出現（Control Bar 顯示「等待 viewer」）
  - MONITORING: 每 500ms 取樣、計算 hash、判斷是否變化
  - CAPTURING: 截圖 + ROI 裁切（< 100ms）
  - ANALYZING: 等待 OpenClaw MultiPass；SLA 為 coarse 60s、first crop 100s、total 180s
  - DISPLAYING: Overlay 顯示中（30s 後淡出，critical 不淡出）
  - PAUSED: 使用者手動暫停（Control Bar ⾂⾂）
  - ERROR: 錯誤狀態（5s 後自動回 MONITORING）
  - RECONNECTING: WebSocket 重連中
```

### 3.6 WebSocket 訊息協定（Overlay ↔ OpenClaw）

**通訊方式：** Python Overlay Agent 作為 WS client 連線至 OpenClaw Gateway

**訊息格式：** JSON over WebSocket（OpenClaw 原生協定）

```
→ Overlay → OpenClaw（分析請求）
{
  "type": "vision.analyze",
  "session": "dicom-overlay",
  "payload": {
    "image_base64": "<ROI裁切後 PNG base64>",
    "modality": "EKG",               // EKG | CXR | CT_BRAIN | auto
    "skill": "dicom-ekg-analysis",   // 對應 OpenClaw workspace skill
    "valid_regions": ["lead_I", "lead_II", ...],  // 注入合法區域清單
    "response_format": "json"
  }
}

← OpenClaw → Overlay（分析結果）
{
  "type": "vision.result",
  "session": "dicom-overlay",
  "payload": {
    "modality": "EKG",
    "analysis_time_ms": 4230,
    "summary": "Sinus rhythm with borderline QTc prolongation",
    "severity": "warning",
    "findings": [...],               // 同 §3.3 JSON 格式
    "checklist": {...},
    "model_used": "openai/gpt-5.4-mini", // release default；OpenClaw 回報實際模型
    "tokens": { "input": 1200, "output": 450 }
  }
}

← OpenClaw → Overlay（錯誤）
{
  "type": "vision.error",
  "session": "dicom-overlay",
  "error": {
    "code": "RATE_LIMITED",          // RATE_LIMITED | TIMEOUT | MODEL_ERROR
    "message": "API quota exceeded",
    "retryable": true,
    "retry_after_sec": 30
  }
}

← OpenClaw → Overlay（模型切換通知）
{
  "type": "model.failover",
  "session": "dicom-overlay",
  "payload": {
    "from": "claude-opus-4-6",
    "to": "gpt-4o",
    "reason": "primary_unavailable"
  }
}
```

**OpenClaw Skill 結構（workspace skill）：**

```
~/.openclaw/workspace/skills/dicom-ekg-analysis/
├── SKILL.md          # Skill 定義 + EKG 系統 prompt
└── schema.json       # 回傳 JSON schema（確保結構一致）
```

**連線管理：**
- 斷線自動重連（`reconnect_interval_sec`，指數退避，最大 30s）
- 心跳偵測（OpenClaw 內建 ping/pong）
- Session 持久化（OpenClaw 自動管理）

---

## 4. 各模態 Prompt 規格

### 4.1 EKG

```
系統 prompt：
你是心電圖判讀助理。分析這張 12-lead EKG 截圖。
回傳完整 JSON，包含 checklist 和區域標注。
重點 flag：STEMI/NSTEMI pattern、arrhythmia、
QTc prolongation、AV block、bundle branch block。

重要限制：
- 你看的是螢幕截圖，不是原始訊號，無法精確測量數值
- 使用定性描述（normal / borderline / prolonged）而非精確 ms
- 用區域名稱（lead_I, lead_V4, rhythm_strip）而非座標
- 專注 pattern 識別，不要捶造數值
```

### 4.2 CXR

```
系統 prompt：
你是胸部 X 光判讀助理。分析這張 PA/AP CXR。
回傳 JSON findings 和區域標注。
重點 flag：cardiomegaly、pleural effusion、
pneumothorax、consolidation、pneumomediastinum、
ETT/line 位置（若可見）。

用區域名稱標注：
right_upper_lung, right_lower_lung, left_upper_lung, left_lower_lung,
cardiac_silhouette, costophrenic_angle_R, costophrenic_angle_L,
mediastinum, trachea, diaphragm
```

### 4.3 CT Brain

```
系統 prompt：
你是頭部 CT 判讀助理。這是單張軸切面截圖。
回傳 JSON findings，使用區域標注。
重點 flag：hyperdense lesion（hemorrhage）、
midline shift、herniation sign、
hydrocephalus、mass effect。

重要限制：
- 單張截圖 context 有限，僅描述可見異常
- 不足以排除 subtle finding，請明確標註 confidence level
- 用區域名稱：midline, ventricles, sulci, posterior_fossa,
  frontal_lobe, temporal_lobe, basal_ganglia
```

---

## 5. 設定檔規格（config.yaml）

```yaml
# DICOM Overlay Agent Configuration

monitor:
  window_title_keywords:        # 視窗標題關鍵字（任一符合即監控）
    - "DICOM"
    - "影像"
    - "Viewer"
  polling_interval_ms: 500      # 監控頻率
  hash_algorithm: "ahash"       # ahash (快) | phash (精確)
  hash_threshold: 10            # hash 差異觸發閾值（0-64）
  debounce_stable_sec: 1.5      # hash 變化後等待穩定秒數
  window_backend: "pywin32"     # pywin32 | pygetwindow

phi_roi:                        # PHI ROI 裁切（首次使用時設定）
  top: 60
  bottom: 30
  left: 0
  right: 0

openclaw:                       # OpenClaw Gateway 設定
  gateway_url: "ws://127.0.0.1:18789"
  reconnect_interval_sec: 5     # 斷線重連間隔
  timeout_sec: 15               # 單次分析 timeout
  workspace: "~/.openclaw/workspace"  # Skills 路徑
  config_path: "openclaw/openclaw.json"  # Portable 用
  # OpenClaw 自行管理 model failover、API keys、retry
  # API keys 設定於 openclaw.json 或 .env

region_maps:                    # 區域映射表（百分比座標，相對於 ROI 裁切後影像）
  EKG:
    layout: standard_4x3
    regions:
      lead_I:        { x: 0.000, y: 0.000, w: 0.250, h: 0.270 }
      lead_aVR:      { x: 0.250, y: 0.000, w: 0.250, h: 0.270 }
      lead_V1:       { x: 0.500, y: 0.000, w: 0.250, h: 0.270 }
      lead_V4:       { x: 0.750, y: 0.000, w: 0.250, h: 0.270 }
      lead_II:       { x: 0.000, y: 0.270, w: 0.250, h: 0.270 }
      lead_aVL:      { x: 0.250, y: 0.270, w: 0.250, h: 0.270 }
      lead_V2:       { x: 0.500, y: 0.270, w: 0.250, h: 0.270 }
      lead_V5:       { x: 0.750, y: 0.270, w: 0.250, h: 0.270 }
      lead_III:      { x: 0.000, y: 0.540, w: 0.250, h: 0.270 }
      lead_aVF:      { x: 0.250, y: 0.540, w: 0.250, h: 0.270 }
      lead_V3:       { x: 0.500, y: 0.540, w: 0.250, h: 0.270 }
      lead_V6:       { x: 0.750, y: 0.540, w: 0.250, h: 0.270 }
      rhythm_strip:  { x: 0.000, y: 0.810, w: 1.000, h: 0.190 }
  CXR:
    layout: standard_pa
    regions:
      right_upper_lung:    { x: 0.05, y: 0.08, w: 0.30, h: 0.22 }
      right_middle_lung:   { x: 0.05, y: 0.30, w: 0.30, h: 0.25 }
      right_lower_lung:    { x: 0.05, y: 0.55, w: 0.30, h: 0.23 }
      left_upper_lung:     { x: 0.65, y: 0.08, w: 0.30, h: 0.22 }
      left_middle_lung:    { x: 0.65, y: 0.30, w: 0.30, h: 0.25 }
      left_lower_lung:     { x: 0.65, y: 0.55, w: 0.30, h: 0.23 }
      cardiac_silhouette:  { x: 0.30, y: 0.30, w: 0.40, h: 0.40 }
      mediastinum:         { x: 0.35, y: 0.05, w: 0.30, h: 0.35 }
      trachea:             { x: 0.40, y: 0.00, w: 0.20, h: 0.12 }
      right_cp_angle:      { x: 0.05, y: 0.72, w: 0.25, h: 0.15 }
      left_cp_angle:       { x: 0.70, y: 0.72, w: 0.25, h: 0.15 }
      diaphragm:           { x: 0.10, y: 0.75, w: 0.80, h: 0.12 }
  CT_BRAIN:
    layout: axial_standard
    regions:
      right_frontal:       { x: 0.10, y: 0.05, w: 0.35, h: 0.30 }
      left_frontal:        { x: 0.55, y: 0.05, w: 0.35, h: 0.30 }
      right_temporal:      { x: 0.05, y: 0.35, w: 0.25, h: 0.30 }
      left_temporal:       { x: 0.70, y: 0.35, w: 0.25, h: 0.30 }
      ventricles:          { x: 0.30, y: 0.30, w: 0.40, h: 0.25 }
      midline:             { x: 0.45, y: 0.10, w: 0.10, h: 0.70 }
      posterior_fossa:     { x: 0.25, y: 0.75, w: 0.50, h: 0.22 }
      right_basal_ganglia: { x: 0.25, y: 0.30, w: 0.20, h: 0.20 }
      left_basal_ganglia:  { x: 0.55, y: 0.30, w: 0.20, h: 0.20 }

overlay:
  position: "right"             # right | bottom
  summary_panel: true
  region_highlights: true       # 區域高亮（而非箭頭）
  display_duration_sec: 30
  critical_persist: true        # critical finding 不自動淡出
  fade_duration_ms: 500
  control_bar: true             # 顯示 Control Bar
  control_bar_position: "bottom_right"

hotkeys:
  trigger_manual: "ctrl+shift+a"   # 手動觸發分析
  dismiss_overlay: "ctrl+shift+d"  # 關閉 overlay
  toggle_enable: "ctrl+shift+e"    # 暫停/恢復監控

debug:
  save_screenshots: false       # 僅 debug 模式保存截圖
  log_level: "INFO"             # DEBUG | INFO | WARNING | ERROR
  log_file: "overlay_agent.log"
```

---

## 6. 隱私與安全設計

### 6.1 去識別化保證

```
截圖處理流程（ROI 裁切）：
  原始截圖（含 PHI）→ ROI 裁切（使用者設定的固定範圍）→ 去識別截圖
                                                       ↓
                                              透過 WS 送 OpenClaw
                                                       ↓
                                                  記憶體清除
  ✗ 原始截圖不寫入磁碟
  ✗ 去識別截圖不永久保留（30秒後清除）
  ✗ API 請求不含任何患者資訊
  ✓ DICOM viewer 版面固定，PHI 位置可預測，ROI 裁切即可有效移除
  ✓ 首次設定時提供預覽，讓使用者確認裁切範圍
  ✓ debug 模式可選擇性保存截圖（預設關閉）
```

### 6.2 網路連線

| 目的地 | 說明 | 必要性 |
|--------|------|--------|
| chatgpt.com | Subscription-backed GPT-5.4 Mini（經 OpenClaw Gateway） | 目前實驗必要 |
| api.openai.com / provider endpoint | 顯式 API-key profile（經 OpenClaw Gateway） | 選配 |
| localhost:18789 | OpenClaw Gateway（本機） | 必要 |
| 無其他外連 | - | - |

**院內防火牆考量：**
- 若無法直連，可設定 HTTP proxy
- 或未來評估使用院內部署的 local vision model（如 LLaVA-Med）

### 6.3 使用者確認機制（建議）

首次使用時，顯示確認對話框：
```
⚠️ 使用前確認

本工具將對 DICOM viewer 影像區域截圖，
裁切病患識別資訊後送至 AI 分析服務。

截圖區域：[顯示預覽]
裁切設定：上 60px / 下 30px

確認截圖不含任何病患識別資訊後，
請按「確認啟用」繼續。

[確認啟用]  [調整設定]  [取消]
```

---

## 7. 開發階段規劃

### Phase 0：OpenClaw 環境建置

- [x] 安裝並固定 OpenClaw Gateway（Node.js）
- [ ] 設定 API Keys（Anthropic / OpenAI）
- [ ] 建立 workspace skills（DICOM 分析 prompt）
- [ ] 驗證 WebSocket 連線與模型 failover

**驗收標準：** OpenClaw Gateway 啟動 → 可透過 WS 傳送圖片並獲得 Vision 分析結果

### Phase 1：核心 Pipeline（MVP）

- [ ] pywin32 視窗偵測 + mss 截圖
- [ ] ROI 裁切 PHI 去識別（首次設定 UI）
- [x] WebSocket Client 連線 OpenClaw Gateway
- [ ] 固定位置側欄摘要面板（純文字，無區域高亮）
- [ ] Click-through 透明視窗
- [ ] 小型 Control Bar（暫停/重觸發/模態切換）
- [ ] 手動快捷鍵觸發

**驗收標準：** EKG 開啟 → 5秒內出現分析結果，滑鼠可正常操作 viewer，Control Bar 可操作

### Phase 2：自主監控 + 視覺標注

- [ ] Debounce 自動監控（影像變更自動觸發）
- [ ] 區域高亮標注（依區域名稱對應螢幕位置）
- [ ] 嚴重度色碼 + critical 持續顯示
- [ ] Fade-in / fade-out 動畫

**驗收標準：** 影像切換自動觸發分析，異常區域正確高亮

### Phase 3：多模態與設定介面

- [ ] CXR prompt + 區域對應
- [ ] CT Brain prompt + 區域對應
- [ ] 模態自動偵測（或 Control Bar 手動切換）
- [ ] GUI 設定介面（裁切區域、API key、Gateway 設定）
- [ ] 視窗自動跟隨 DICOM viewer 移動/縮放
- [ ] 使用紀錄（本機，僅供品質追蹤）

### Phase 4：（未來評估）

- [ ] Local vision model（離線，無外連需求）
- [ ] 多螢幕支援
- [ ] 院內系統整合評估

---

## 8. 技術堆疊

| 層級 | 技術選型 | 備選 |
|------|---------|------|
| 語言 | Python 3.11+ | - |
| Agent Runtime | OpenClaw Gateway (Node.js) | - |
| GUI / Overlay | PyQt6 | PySide6 |
| 螢幕截圖 | mss（快速，支援多螢幕） | Pillow |
| 視窗偵測 | pywin32 (win32gui) | pygetwindow |
| 影像 hash | imagehash (ahash) | phash |
| WS 通訊 | websockets | - |
| Vision API | OpenClaw 管理（預設 `openai/gpt-5.4-mini`；可顯式 override） | v0.4.7 實測 `openai/gpt-5.6-luna` |
| 設定檔 | PyYAML (yaml.safe_load) | - |
| 打包 | PyInstaller（單一 exe） | - |
| 系統常駐 | system tray (pystray) | Windows Task Scheduler |

---

## 9. 錯誤處理與降級策略

| 場景 | 行為 | 使用者可見回饋 |
|------|------|----------------|
| API timeout / 5xx | 重試 max_retries 次，延遲遞增 | Control Bar 顯示 "分析中...重試" |
| API 配額耗盡 (429) | 暂停自動監控，保留手動觸發 | Control Bar 顯示 "配額不足，已暫停" |
| 網路斷線 | 靜默失敗，不顯示影像標注 | Control Bar 變灰 + "離線" badge |
| JSON 格式異常 | 嘗試宵鬆解析，失敗則顯示原始摘要 | 側欄顯示 "分析結果格式異常" |
| 視窗找不到 | 每 5 秒重試偵測，無限重試 | Control Bar 顯示 "等待 DICOM viewer..." |

| 快捷鍵衝突 | 在設定中提示衝突，允許自訂 | 設定界面顯示衝突警告 |
| Provider fallback | OpenClaw 自動管理 failover | Control Bar 顯示 "已切換備援模型" |
| OpenClaw 斷線 | 自動重連（reconnect_interval_sec） | Control Bar 顯示 "Gateway 離線中..." |

---

## 10. 效能預算

| 指標 | 目標 |
|------|------|
| 截圖 + 裁切 | < 100ms |
| MultiPass（經 OpenClaw） | coarse ≤60s、first crop ≤100s、total ≤180s 目標 |
| Overlay 渲染 | < 200ms |
| 端到端延遲 | < 10s（截圖到顯示標注） |
| 記憶體佔用 | < 150MB（常駐） |
| CPU 閒置時 | < 2% |
| CPU 分析中 | < 10% |

---

## 11. 已知限制與免責聲明

1. **AI 輸出非診斷**：本工具輸出為輔助參考，不構成醫療診斷，最終判斷由醫師負責。
2. **單張截圖限制**：CT/MRI 等三維影像，單張截圖僅能描述當前 slice，無法評估整體病灶。
3. **Vision model 幻覺風險**：AI 可能產生不準確描述，使用者需保持批判性評估。
4. **Window/Level 相依性**：影像呈現品質受 DICOM viewer 當下 W/L 設定影響，AI 看到的是顯示影像而非原始 DICOM 數值。
5. **PHI 裁切依賴設定**：ROI 裁切依賴使用者首次設定，DICOM viewer 版面固定時設定一次即可。
6. **定性而非定量**：本工具輸出定性描述（normal/borderline/abnormal），不提供精確數值測量，數值仍需醫師判讀。
7. **OpenClaw 依賴**：需要本機 OpenClaw Gateway；portable bundle 內含固定 Node，且不允許 direct API fallback 繞過 ownership/audit 邊界。

---

## 12. Portable 部署架構

### 12.1 設計目標

醫院工作站通常無法安裝軟體（無 admin 權限），因此採用 USB 隨插即用的 portable 部署。

### 12.2 目錄結構

```
dicom-overlay-portable/          # USB 根目錄
├── node/                        # Node.js portable (~30MB)
│   └── node.exe
├── openclaw/                    # OpenClaw + node_modules + workspace
│   ├── node_modules/
│   ├── workspace/               # skills, prompts, session DB
│   └── config.json
├── overlay.exe                  # PyInstaller single file (~50MB)
├── config.yaml                  # 使用者設定檔
├── .env                         # API keys（不納入版控）
└── start.bat                    # 一鍵啟動
```

### 12.3 啟動流程 (`start.bat`)

```bat
@echo off
REM 1. 啟動 OpenClaw Gateway
start "" /B node\node.exe openclaw\node_modules\.bin\openclaw --config openclaw\config.json

REM 2. 等待 Gateway ready
timeout /t 3 /nobreak >nul

REM 3. 啟動 Overlay Agent
overlay.exe --config config.yaml
```

### 12.4 大小預算（實測）

| 元件 | 大小 | 說明 |
|------|------|------|
| overlay 啟動器 exe | 7.05 MiB（2026-08-09） | 最近一次完整 PyInstaller launcher；v0.4.7 待重建 |
| App + Python/Qt 層 | 94.74 MiB（2026-08-09） | 最近一次完整 build；v0.4.7 待重建 |
| v0.4.7 staged OpenClaw runtime | 165.162 MiB | 保留 templates / dist / plugin surfaces；減少 19.804 MiB |
| Node.js portable | 88.25 MiB | Node `v24.18.0` |
| config / runtime state | 動態 | clean bundle 禁止 `.env`、token 與 SQLite state |
| 2026-08-09 完整 bundle | 368.01 MiB | 歷史實測值，非 v0.4.7 預估 |
| **v0.4.7 完整 bundle** | **待乾淨重建** | 不預估總尺寸、file count 或 hash |

### 12.5 限制

- Windows only（pywin32 依賴）
- 首次使用需 `codex login` subscription OAuth 或顯式 provider API profile
- 需要網路連線（Vision API 呼叫）
- 防火牆需開放所選 provider；目前 subscription route 使用 ChatGPT backend

---

## 13. 相關專案與先行技術（Prior Art）

本節列出與 DICOM Overlay Agent 概念相近或技術相關的開源專案，作為設計參考與生態系整合依據。

### 13.1 核心依賴

| 專案 | 連結 | 說明 | 與本專案關係 |
|------|------|------|-------------|
| **OpenClaw** | [openclaw/openclaw](https://github.com/openclaw/openclaw) | Personal AI assistant，WS Gateway 控制平面（`localhost:18789`），支援多模型 failover、Skills 系統、多通道整合。Node.js ≥22，MIT License | **直接依賴** — 本專案 §3.6 WS 協定即透過 OpenClaw Gateway 呼叫 Vision model 進行影像分析 |

### 13.2 最相似的參考架構

| 專案 | 連結 | 技術棧 | 說明 | 可借鏡之處 |
|------|------|--------|------|-----------|
| **CloudToLocalLLM** | [CloudToLocalLLM-online/CloudToLocalLLM](https://github.com/CloudToLocalLLM-online/CloudToLocalLLM) | Dart/Flutter, Node.js | OpenClaw Agent Manager — 5 大支柱（Chat、OpenClaw Manager、Avatar、Desktop Control、**Vision**）。Vision 系統具備 ScreenCaptureService、ScreenMonitorService、OCR Engine，透過 OpenClaw Gateway 分析截圖 | Vision System 架構（截圖→base64→Gateway→分析）與本專案幾乎相同；Desktop Control 的 GUI Automation 模式可參考 |
| **OAIT** | [raymondclowe/OAIT](https://github.com/raymondclowe/OAIT) | Python, FastAPI, WebSocket | Observational AI Tutor — 持續 OODA loop 監控白板 + 語音，僅在需要時介入指導。Local-first 架構，Faster-Whisper + Gemini 3 Pro (via OpenRouter) | **持續觀察 + 智慧靜默** 模式與本專案的 autonomous agent co-reading 理念一致；OODA loop 架構可對照本專案 §3.5 狀態機設計 |
| **ai-assistant** | [kaisinishe/ai-assistant](https://github.com/kaisinishe/ai-assistant) | Python | 輕量「snip and ask」桌面助手 — 全域熱鍵 → 拖曳選區 → 截圖 → LLM 分析 → always-on-top overlay 顯示結果 | 類似的 input 流程（截圖→LLM→overlay），但為手動觸發；本專案改為自動觸發 + 透明 click-through |

### 13.3 醫學影像 AI 相關

| 專案 | 連結 | 技術棧 | 說明 |
|------|------|--------|------|
| **X-ray-dental** | [Tashu22-hub/X-ray-dental](https://github.com/Tashu22-hub/X-ray-dental) | Python, GPT-4 | 牙科 X-ray DICOM 分析 — 自動化病理偵測 + 報告生成 |
| **RadiologyReportGen-AI** | [Kheem-Dh/RadiologyReportGen-AI](https://github.com/Kheem-Dh/RadiologyReportGen-AI) | Python, ViT + GPT-2 | CXR 報告自動生成 — Vision Transformer + GPT-2 |
| **Scanovich.ai** | [FUYOH666/Scanovich.ai-MRI_radiology_assistant](https://github.com/FUYOH666/Scanovich.ai-MRI_radiology_assistant) | Python (archived) | MRI + CT 放射科 AI 助手 |

### 13.4 OpenClaw 生態系（可參考整合模式）

| 專案 | Stars | 說明 |
|------|-------|------|
| [openclaw-mission-control](https://github.com/abhi1693/openclaw-mission-control) | 2086 | AI Agent 編排 Dashboard — 管理 agent、分派任務、多 agent 協調 |
| [openclaw-studio](https://github.com/grp06/openclaw-studio) | 1581 | Web Dashboard — 連接 Gateway、管理 agents |
| [openclaw-guardian](https://github.com/LeoYeAI/openclaw-guardian) | 935 | Guardian watchdog — 自動監控、self-repair、git-based rollback |
| [openclaw-hub](https://github.com/openclaw-community/openclaw-hub) | 5 | Multi-LLM 編排 Gateway + MCP 整合（Python, FastAPI） |

### 13.5 關鍵差異化

本專案與現有方案的**核心差異**：

1. **醫學影像專用**：所有現有的 screen overlay / vision agent 都是通用型；本專案針對 **EKG/CXR/CT** 的 systematic checklist review，具有模態感知的 Region Map + 專科 Prompt
2. **Autonomous co-reading**：不需醫師觸發（cf. ai-assistant 的手動 snip），Agent 自動偵測影像切換並分析
3. **PHI-safe 設計**：ROI 裁切 + 院內 LAN 部署（僅 API call 外出），符合醫療環境 HIPAA/台灣個資法要求
4. **透明 click-through overlay**：不遮擋醫師操作 DICOM viewer（cf. CloudToLocalLLM 的獨立窗口方式）
5. **Portable 部署**：USB 隨插即用，不需安裝（cf. 大多數方案需要 pip install 或 Docker）

### 13.6 技術借鏡摘要

| 借鏡來源 | 技術點 | 應用於本專案 |
|---------|--------|-------------|
| CloudToLocalLLM Vision System | `ScreenCaptureService` → base64 → OpenClaw Gateway → 分析結果 | §3.3 截圖服務 + §3.6 WS 協定的設計驗證 |
| OAIT OODA Loop | 持續觀察 → 判斷是否需介入 → 靜默或主動報告 | §3.5 Agent 狀態機的 debounce + 自動觸發邏輯 |
| OpenClaw 官方 | Skills 系統 + Model failover + WS 控制平面 | §3.6 WS 協定完全基於 OpenClaw Gateway 規範 |
| ai-assistant | 截圖 → LLM → always-on-top overlay 顯示 | §3.1 Overlay 視窗的 always-on-top + 結果顯示 |

---

*本規格書保留 v0.4.1 的產品設計與 prior-art 內容，並以 2026-08-27
v0.4.7 implementation binding 覆蓋目前 runtime、模型、MultiPass、評估與封裝
事實；明列為歷史日期的數字不代表 v0.4.7 最終封裝結果。*
