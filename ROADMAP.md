# Roadmap

專案發展路線圖與功能規劃。

## 已完成 ✅

### v0.1.0 (2025-12-15)

- [x] 專案初始化
- [x] Memory Bank 系統建立
- [x] Claude Skills 基礎架構
- [x] Git 文檔自動更新 Skill

### v0.2.0 (2026-03-06)

- [x] Pre-commit hooks 完整配置（16+ hooks）
- [x] 自訂 hook scripts（commit-size-guard、memory-bank-reminder、skill/agent-freshness-check）
- [x] Copilot Agents 系統（14 個 agent，含免費模型策略）
- [x] 多模型審查委員會（review-panel + 3 reviewer subagents）
- [x] Copilot Prompts（5 個可重複使用 prompt）
- [x] 新增 Skills（code-audit、skill-health-check）
- [x] chatmode → agent 遷移
- [x] 自訂 Agent 建立

### v0.3.0 — 四大核心 (2026-05-30)

- [x] Core 1：影像判讀圖層互動（AI bbox + region_maps fallback、SummaryPanel/ChatPanel、ROI PHI 裁剪）
- [x] Core 2：完整 OpenClaw 判讀 harness（smoke + validator + CI 合約、16-key schema）
- [x] Core 3：OpenClaw Gateway 協定相容（`MIN_SAFE_OPENCLAW_VERSION`、protocol 3 影像附件）
- [x] Core 4：最小執行檔封裝（PyInstaller spec、portable node、瘦身 OpenClaw runtime）
- [x] 多影像模態註冊表（ModalityRegistry，config 可擴充）
- [x] 設定 UI + 持久化、評估 harness、視覺探針
- [x] 6 組 Sonnet 平行查核 + 修正（多螢幕座標、modality fallback、config 防呆）

## 進行中 🚧

- [ ] 完善 Skills 觸發機制
- [ ] 套件更新自動檢查 hook

## 計劃中 📋

### 短期目標

- [ ] 新增更多實用 Skills
- [ ] 建立專案模板系統
- [ ] 整合 CI/CD 流程

### 長期目標

- [ ] Skills 分享與匯入機制
- [ ] 多專案 Memory Bank 同步
