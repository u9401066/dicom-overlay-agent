# Progress (Updated: 2026-03-14)

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
- **端到端測試 GPT-5-mini 成功** (2026-03-14)：
  - Chat 連線測試 ✅（Reply: 'OK'，~7s）
  - 真實 ECG strip 圖片 analyze 測試 ✅（16.5s，正確辨識 Sinus rhythm + 5 項 checklist 全正常）
  - AnalysisResult 正確解析為 domain entity（Modality.EKG, Severity.INFO, findings, checklist）

## Doing

- 初次 Git push 到私人 GitHub Repo

## Done (recent)

- **Display Pipeline 深度審查 + 修復** (2026-03-14)：
  - 2 Critical fixes: highlight label 修正 + 未知 region 改用 warning
  - 21 個 display pipeline 測試
- **OpenClaw Overlay 完整整合測試** (2026-03-14)：
  - 42 個 mock WS 整合測試（parse helpers, HookedAnalyzer, e2e, error paths）
  - 125 個 pytest 測試全部通過 (0.85s)
- **Real Gateway 實際測試** (2026-03-14)：
  - Raw WS: connect ✅ → chat.send ✅ → 503 events → final JSON (2067 chars, 25s)
  - OpenClawClient: connect ✅ → chat ✅ → analyze_ekg ✅ → disconnect ✅ (4/4, 23s)
  - AI 正確回傳 EKG 分析：4 findings + 5 checklist items

- **Hook/Guardrail 系統** (2026-03-14)：
  - Domain 介面：`HookError`, `HookEventType`, `HookEvent`, `GatewayHookHandler`, `AnalyzeHook`, `AnalyzeRequest`
  - Infrastructure hooks：`InputGuard`（影像驗證）、`OutputValidator`（結果驗證）、`RateLimiter`（流量控制）
  - Application：`HookedVisionAnalyzer`（decorator pipeline：pre → analyze → post）
  - Gateway hook bridge：`OpenClawHookBridge`（event pub/sub，type:action 格式）
- **MCP Adapter 對齊 OpenClaw** (2026-03-14)：
  - 研究 OpenClaw `openclaw-mcp-adapter` 插件源碼（index.ts, mcp-client.ts, config.ts）
  - Domain：`MCPServerConfig`（stdio/http）、`MCPAdapterConfig`、`MCPToolProvider` ABC、`ToolDefinition`、`ToolCallResult`
  - Infrastructure：`McpAdapter`（鏡像 McpClientPool：start→discover→call→reconnect→stop）
  - `__main__.py` wiring：hooks pipeline + McpAdapter lifecycle
- **測試**：24 個新測試（InputGuard×6 + OutputValidator×3 + RateLimiter×2 + McpAdapter×8 + Config×3 + ToolCallResult×2）
- 全部 61 個單元測試通過

## Next

- 替換 `_StubProvider` 為真正的 Python MCP SDK client（`mcp` package）
- 測試真實 MCP server 連接（如 pubmed-search-mcp via stdio）
- 下載 Node.js portable binary（zip 版）放入 `node/` 目錄
- 更新 `start.bat` 使用 `node\node.exe` 而非系統 `node`
- PyInstaller 打包 `overlay.exe` 單檔 (<50MB)
- 最終目標：<150MB USB 隨身碟可直接執行，零安裝
