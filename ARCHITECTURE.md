# Architecture

專案架構說明文檔。

## 系統概覽

```
┌─────────────────────────────────────────────────────────┐
│                    VS Code Editor                        │
├─────────────────────────────────────────────────────────┤
│                  GitHub Copilot Chat                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ Agent Mode  │  │Claude Skills│  │ Custom Instruct │  │
│  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │
│         │                │                   │           │
│         └────────────────┼───────────────────┘           │
│                          ▼                               │
│  ┌─────────────────────────────────────────────────────┐│
│  │                   Memory Bank                        ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            ││
│  │  │ Context  │ │ Progress │ │ Decisions│            ││
│  │  └──────────┘ └──────────┘ └──────────┘            ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

## 組件說明

### 1. Claude Skills (`.claude/skills/`)
自定義 AI 技能模組，可被 Copilot Chat 自動載入使用。

**目前技能：**
- `git-doc-updater` - Git 提交前文檔更新

### 2. Memory Bank (`memory-bank/`)
跨對話的專案記憶系統，保持上下文連續性。

| 文件 | 用途 |
|------|------|
| `activeContext.md` | 當前工作焦點 |
| `progress.md` | 進度追蹤 |
| `decisionLog.md` | 決策記錄 |
| `productContext.md` | 專案上下文 |
| `projectBrief.md` | 專案簡介 |
| `systemPatterns.md` | 系統模式 |
| `architect.md` | 架構設計 |

### 3. VS Code 設定 (`.vscode/`)
編輯器設定，包含 Copilot 相關配置。

## 資料流

1. 用戶在 Chat 中輸入請求
2. Copilot 檢測是否匹配 Skill
3. 載入相關 Skill 定義
4. 結合 Memory Bank 上下文
5. 執行操作並更新文檔

## 執行時醫療工具邊界

桌面程式只透過 OpenClaw Gateway 的公開 `connect` / `chat.send` 協定溝通。
Gateway 內的 `dicom-overlay-agent-harness` native plugin 提供受限工具面：

- `dicom_bbox_validate` 永遠啟用，負責裁切與正規化全圖座標。
- `ecg_founder_analyze_waveform` 只有在含 bearer token 的 loopback sidecar
  已設定時才啟用。它只處理 app 建立的不透明 waveform artifact id，沒有
  檔案系統權限，也不接受 screenshot-only 請求。

ECGFounder 的 Torch runtime 與 checkpoint 位於獨立程序，不進入 PyInstaller
主 bundle。它輸出的是波形分類證據，不是影像定位；畫布 bbox 仍須由影像
lead inventory、MultiPass crop/refine、座標校正與 `dicom_bbox_validate` 共同
建立。詳細輸入、provenance、校準與實驗契約見
[`docs/ecgfounder-tool.md`](docs/ecgfounder-tool.md)。

目前只有 evaluation runner 能從 manifest 取得可信任的 waveform artifact
binding；桌面 screenshot 流程沒有自行猜測 study 對應波形。每次 evaluation
binding 會產生隨機 evidence nonce，plugin receipt 必須與該 nonce、artifact
digest、固定 model revision 與 checkpoint 完全相符，且每 case 恰好一次成功，
否則該 case 記為 infrastructure failure，不進入有效 ECGFounder 比較。

MEETI 的 paired build 會為每張圖片建立一個 hash-derived waveform artifact
id；只有顯式啟用第三實驗組時，該 id 才綁進單一 case 的 OpenClaw context。
比較必須保持三組分離：single-pass image、MultiPass image、MultiPass 加
ECGFounder waveform evidence，避免把 crop/refine 的收益誤算成外部模型收益。

## 桌面截圖與 Overlay 座標邊界

截圖與 Qt overlay 不共用同一個原生座標系：Win32 / `mss` 使用 virtual
desktop 的實體像素，Qt widget 使用每一個 `QScreen` 的邏輯像素。因此所有
醫師可見的框都走下列單一資料流：

1. `ScreenMonitor.display_for_window()` 用 `MonitorFromRect` 找出 viewer 所在的
   Win32 monitor，保存實體 `DisplayFrame`、device id、index 與 primary flag。
2. `OverlayAgent` 在每次 viewer refresh 與正式 capture 前同步該 display，並把
   成功分析的絕對實體 `last_capture_rect` 保存為後續唯一影像 frame。
3. `presentation.screen_selection` 以 primary、device name、實體尺寸、index 與
   topology 選出對應 Qt `QScreen`。
4. `OverlayCoordinateFrame` 用完整 physical/logical display bounds 分別計算 X/Y
   比例；先扣除實體螢幕原點，再轉成 overlay-local logical edge。負座標螢幕與
   mixed-DPI 不使用 cached primary DPR。
5. AI bbox 與 static region 都投影到同一 frame，並在真正繪製前做 logical →
   physical edge round-trip。超過允許 drift 的框只留下 PHI-free audit row，
   不進入 overlay。
6. 點框 QA、人工框選與 desktop review export 都以同一個 `content_rect` 正規化
   回原始 ROI，避免畫面與匯出結果使用不同座標基準。

區域追問走第二條受限寫回路徑：app 先依上述 frame 裁出精確 crop，再執行
`ImageProcessor.image_quality_profile()` 的本地 signal audit（暗像素、邊緣密度、
robust dynamic range、entropy 與空白場檢查），最後才送入
JSON-only OpenClaw follow-up。模型沒有 bbox 欄位可填；`ADD` 使用人工框、
`REVISE`／`RETRACT` 綁定既有 finding id 與既有 bbox。低訊號或 audit error
會機械式阻擋 `ADD`／`REVISE`，但保留文字 QA、人工框與 `RETRACT` 建議。
通過後仍須使用者按下 Apply，`OverlayAgent` 才以 `FindingDelta` 寫回
`AnnotationAccumulator`。result revision 防止舊回覆套到新影像，單調 chat
request id 防止同一張影像內較慢的舊 QA 蓋掉較新的回覆；整體 triage
只可升級不可降級；Process trace、JSON 與 PNG 都記錄
`interactive_ai_review`、local signal audit 與 reviewer confirmation。

Accumulator 不再把 IoU 當作臨床同一性：不同 normalized label 即使框完全
重疊仍保留為不同診斷；只有相同 id，或相同 label 加高 IoU，才做結構性去重。

ECGFounder 只提供波形分類證據，沒有影像定位能力，因此不會進入這條 bbox
投影路徑。
