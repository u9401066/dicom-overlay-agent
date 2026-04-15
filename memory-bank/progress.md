# Progress (Updated: 2026-04-15)

## Done

- 修正 portable OpenClaw config 與 Windows 啟動腳本
- 將 OpenClaw client 從自訂 vision.analyze 改為真實 Gateway connect/chat.send RPC
- 更新 smoke test 為新協定並改用動態埠，測試通過
- 實際對真實 Gateway 發送帶 EKG 截圖的 chat.send 請求並驗證事件流
- GitHub Copilot device flow 認證完成，token 儲存於 `openclaw-home/credentials/`
- End-to-end 測試：真實 GPT-4o 分析截圖成功
- 修復 code fence JSON 解析 bug（`_strip_code_fence` regex）
- 新增 TTS 語音播報（Windows SAPI）+ toggle 開關
- 全模組 stdlib logging → structlog 25.5.0 遷移（10 模組）
- 修復 shutdown 錯誤、ROI persistence、reconnect UI freeze
- 新增 chat 功能（5 檔案）
- 修復 EKG rhythm_strip missing from config.yaml
- 系統審計 4 issues 全部修復（AsyncBridge、display timer、hotkeys、test mock）
- 模型從 gpt-4o 改為 gpt-5-mini
- WebSocket 自動重連（analyze + chat 包裝器）+ ping_interval=30, ping_timeout=60
- Code fence regex 改用 `re.search` 支援 `\r\n`
- 測試隔離修復（monkeypatch _DEFAULT_CONFIG_PATHS）
- Portable 架構審計完成：OpenClaw 本地安裝 ✅、HOME 隔離 ✅、credentials ✅、skills sync ✅
- **端到端測試 GPT-5-mini 成功** (2026-03-14)
- **Display Pipeline 深度審查 + 修復** (2026-03-14)
- **OpenClaw Overlay 完整整合測試** (2026-03-14)：42 個 mock WS 整合測試
- **Real Gateway 實際測試** (2026-03-14)：4/4 測試通過
- **Hook/Guardrail 系統** (2026-03-14)
- **MCP Adapter 對齊 OpenClaw** (2026-03-14)
- 初次 Git push 到私人 GitHub Repo ✅ (2026-03-14)

## Done (recent) — 2026-03-15

- **Gateway 自動啟動** (2026-03-15)：
  - `GatewayManager` 類：自動啟動/停止 Gateway subprocess
  - `dpi.py`：DPI 感知工具函式
  - `start.bat` 簡化：移除手動 Gateway 啟動步驟
  - `logging_config.py`：Gateway stdout 重導向至 `gateway.log`
- **Presentation 層重構** (2026-03-15)：
  - `DraggableWindowMixin`：SummaryPanel/ChatPanel 改為獨立可拖曳視窗
  - Smart Display：異常項優先、正常項摺疊為「✅ N items normal」
  - ROI 設定 DPI 修正
- **核心功能強化** (2026-03-15)：
  - EKG checklist 從 5 項擴展到 16 項系統性心臟病學項目
  - `OutputValidator` 對齊 16 key schema
  - 可配置 hash 演算法（phash/ahash/dhash/whash），預設 phash + threshold 5
  - WS frame log noise 修復（過濾 `type=event` 訊息）
  - 連線 log noise 修復（`logger.exception` → `logger.warning`）
- **AI 動態 Bounding Box** (2026-03-15)：
  - `Finding` 新增 `bboxes: list[RegionRect]` 欄位
  - AI prompt 改要求歸一化 0-1 座標 bounding box
  - `__main__.py` highlight 優先使用 AI bbox，fallback 到 static region maps
  - SKILL.md × 2 更新 bbox 指示
- **測試**：135 個 pytest 測試全部通過 (0.49s)

## Done (recent) — 2026-04-10

- **兼容性修正 + CI 重建** (2026-04-10)：
  - `pywin32` 改為 Windows-only 條件式依賴，修正 Linux/CI 安裝失敗
  - `OpenClawClient` 缺少本地 token 檔案時可無 token 建立，mock 測試不再依賴本機私有設定
  - `.github/workflows/ci.yml` 改為實際驗證跨平台安裝、`pip check` 與 pytest
  - 新增 gateway token fallback 測試
  - Linux headless 驗證通過：137 個 pytest 測試全部通過

## Done (recent) — 2026-04-15

- **PR 驗證補強** (2026-04-15)：
  - 修正 `mcp_bridge.py` 與 `screen_monitor.py` 的型別/介面錯配，`mypy src tests` 通過
  - 補齊 `gateway_manager.py`、`control_bar.py`、`overlay_window.py` 的 Qt/Windows 型別註記
  - 調整 `pyproject.toml` 讓 hook 腳本的中文文字不再觸發無關 Ruff ambiguous-unicode 警告
  - 修正手動 real-gateway 測試腳本與 `test_ecg_overlay_display.py` 的 lint/type 問題
  - 重新驗證 `pip check`、OpenClawClient import 與 headless pytest，138 個 pytest 全數通過

## Doing

（無）

## Next

- 替換 `_StubProvider` 為真正的 Python MCP SDK client（`mcp` package）
- 測試真實 MCP server 連接（如 pubmed-search-mcp via stdio）
- 下載 Node.js portable binary（zip 版）放入 `node/` 目錄
- 更新 `start.bat` 使用 `node\node.exe` 而非系統 `node`
- PyInstaller 打包 `overlay.exe` 單檔 (<50MB)
- 最終目標：<150MB USB 隨身碟可直接執行，零安裝
- Live 測試 AI bbox 精確度與 phash 偵測靈敏度
