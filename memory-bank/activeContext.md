# Active Context

> 📌 此檔案記錄當前工作焦點，每次工作階段開始時檢視，結束時更新。

## 🎯 當前焦點

- 兼容性修正與 CI 重建已完成
- 目前已驗證：
  - Linux 可成功 `pip install -e '.[dev]'`
  - headless Qt 測試可執行（需系統套件 + `QT_QPA_PLATFORM=offscreen`）
  - 137 個 pytest 測試通過

## 📝 最近完成的變更 (2026-03-15)

| 檔案/目錄 | 變更內容 |
|-----------|----------|
| `src/dicom_overlay/infrastructure/gateway_manager.py` | 新增：Gateway 自動啟動/停止 |
| `src/dicom_overlay/infrastructure/dpi.py` | 新增：DPI 感知工具 |
| `start.bat` | 簡化啟動流程（Gateway 自動管理） |
| `src/dicom_overlay/infrastructure/logging_config.py` | Gateway stdout → gateway.log |
| `src/dicom_overlay/presentation/overlay_window.py` | DraggableWindowMixin + 智慧顯示 |
| `src/dicom_overlay/presentation/roi_setup.py` | DPI 修正 + 改善 |
| `src/dicom_overlay/domain/entities.py` | Finding.bboxes + MonitorConfig phash |
| `src/dicom_overlay/infrastructure/screen_monitor.py` | 可配置 hash 演算法 |
| `src/dicom_overlay/infrastructure/openclaw_client.py` | WS log 過濾 + bbox 解析 + prompt |
| `src/dicom_overlay/application/overlay_agent.py` | EKG 16 項 checklist |
| `src/dicom_overlay/infrastructure/hooks/output_validator.py` | 16 key schema |
| `src/dicom_overlay/__main__.py` | Gateway 整合 + hash config + bbox highlight |
| `config.yaml` | phash + threshold 5 |
| `openclaw/workspace/skills/dicom-ekg-analysis/SKILL.md` | bbox 指示 |
| `openclaw-home/workspace/skills/dicom-ekg-analysis/SKILL.md` | 同步 bbox 指示 |
| `tests/unit/test_display_pipeline.py` | 擴充 display pipeline 測試 |
| `tests/unit/test_hooks_and_mcp.py` | 新增 OutputValidator + hooks 測試 |
| `tests/unit/test_roi.py` | 新增 ROI 單元測試 |
| `tests/integration/test_openclaw_overlay.py` | _make_result 對齊 16 keys |

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
*Last updated: 2026-03-15*
