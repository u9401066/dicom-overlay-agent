# Changelog

所有重要變更都會記錄在此檔案中。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/)，
專案遵循 [語義化版本](https://semver.org/lang/zh-TW/)。

## [Unreleased]

### Added

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

- **多螢幕座標錯位（潛在 PHI 風險）**：主螢幕不在原點時 mss 截圖會擷取錯誤螢幕；新增螢幕原點 offset 貫穿 capture 與 control bar
- **modality 解析 fallback**：未知/缺漏 modality 改回退「請求時的 modality」並 log warning（不再靜默寫死 EKG）
- **config 字串防呆**：`checklist_keys`/`aliases` 單一字串不再被逐字元拆解

### Changed

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
