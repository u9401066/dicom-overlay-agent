# Active Context

> 📌 此檔案記錄當前工作焦點，每次工作階段開始時檢視，結束時更新。

## 🎯 當前焦點

- PR 驗證補強已完成，分支可進入送審
- 目前已驗證：
  - Linux 可成功 `pip install -e '.[dev]'`
  - headless Qt 測試可執行（需系統套件 + `QT_QPA_PLATFORM=offscreen`）
  - `python -m pip check` 通過
  - `python -m mypy src tests` 通過
  - 138 個 pytest 測試通過

## 📝 最近完成的變更 (2026-04-15)

| 檔案/目錄 | 變更內容 |
|-----------|----------|
| `src/dicom_overlay/infrastructure/mcp_bridge.py` | 對齊 `MCPToolProvider` 介面，修正同步/非同步工具列舉與錯誤回傳 |
| `src/dicom_overlay/infrastructure/screen_monitor.py` | 補強 hash function 型別註記，讓 mypy 通過 |
| `src/dicom_overlay/infrastructure/gateway_manager.py` | 補上 log file 與 Windows creationflags 型別處理 |
| `src/dicom_overlay/presentation/control_bar.py` | 補上拖曳座標的 `QPoint | None` 型別 |
| `src/dicom_overlay/presentation/overlay_window.py` | 補強 checklist 與拖曳視窗型別、清理 lint |
| `pyproject.toml` | 增加 mypy Windows 模組 ignore 與 hook 腳本 Ruff per-file ignore |
| `tests/integration/_run_real_test.py` | 清理 lint、保守化 token 型別判斷 |
| `tests/integration/test_real_gateway.py` | 保守化 token 型別判斷 |
| `tests/test_ecg_overlay_display.py` | 修正 lint/type 問題，改用 `Path.open()` |
| `scripts/hooks/agent_freshness_check.py` | 保留中文內容並由 Ruff 設定忽略 ambiguous-unicode 檢查 |

## ⚠️ 待解決

- MCP adapter `_StubProvider` 需替換為真正的 MCP SDK client
- Node.js portable binary 尚未下載
- PyInstaller 打包尚未實作
- Live 測試 AI bbox 精確度

## 🔧 Gateway 啟動要點

- 正確指令：`gateway run`（非 `gateway start`）
- Gateway port: 18789, auth token: `aa1d6c0c9ee5a36df1446e0dc0266bc0f7319ecb93fd82ba`
- 模型：`github-copilot/gpt-5-mini`
- 現在由 `GatewayManager` 自動管理啟動/停止

## 📁 Portable 架構狀態

| 元件 | 狀態 |
|------|------|
| OpenClaw 本地安裝 (`openclaw/node_modules/`) | ✅ 完成 |
| HOME 隔離 (`openclaw-home/`) | ✅ 完成 |
| Credentials (`github-copilot.token.json`) | ✅ 完成 |
| Skills 同步 (robocopy) | ✅ 完成 |
| `start.bat` 一鍵啟動 | ✅ 完成 |
| Gateway 自動啟動/停止 | ✅ 完成 |
| Node.js portable binary | 🔲 待做 |
| PyInstaller 打包 | 🔲 待做 |

---
*Last updated: 2026-04-15*
