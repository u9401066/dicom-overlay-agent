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

### v0.4.0 — 判讀強化與可攜帶封裝 (2026-05-30)

- [x] 多趟放大判讀（resolution-aware）：完整 ROI 解析度重讀異常區、4K 截圖無法數位放大時改提示醫師放大重截（`zoom_hints`）
- [x] CXR 10 軸系統性判讀 checklist + validator 強制
- [x] 辨識評分 harness：軸×嚴重度覆蓋率、pertinent-negative recall、can't-miss 硬性 CI gate
- [x] 評估 harness 真實資料解析容錯強化
- [x] 可攜帶 USB 即插即用：凍結時路徑錨定執行檔資料夾（`app_paths.py`）+ `--selfcheck` 自我檢查
- [x] `test-runner` agent 改用 GPT-5.5 mini

### v0.4.1 — 接線護欄與孤兒消除 (2026-05-30)

- [x] 跨輪註記去重（`AnnotationAccumulator`）：幾何 IoU 去重為純函式（永不降級嚴重度），臨床判斷走顯式 `FindingDelta`（ADD/REVISE/RETRACT）
- [x] 接線護欄（`tests/unit/test_wiring.py`）：列舉 application 層 orchestrator，強制每個「已接線（`__main__` 可達）或顯式登記為 DEFERRED（附原因）」，CI 自動攔截孤兒功能
- [x] 多趟放大判讀正式接線：`MultiPassAnalyzer` 作為 `VisionAnalyzerService` drop-in 包進 `OverlayAgent`，由 `analysis.multi_pass_enabled` 旗標啟用（目前預設開啟且可在 Settings 關閉）；新增 `ImageProcessor.crop_region_base64`（PIL，PHI-safe 子集裁剪）
- [x] 臨床一致性引擎（`ClinicalConsistencyEngine`）：以資料驅動、有醫學指引根據的規則檢查 AI 自身結構化輸出的「自我矛盾」與「不可漏診的低估」，僅升級嚴重度（永不降級）並標記人工複核；內建規則附指引引用（STEMI 未標記、高鉀尖 T 波、氣胸/縱膈擴大低估），可由 `clinical_rules/*.rules.yaml` 規則包依 id 覆寫或新增（指引更新時模組化抽換，免改程式碼）；接成 `ClinicalConsistencyHook` post-analyze 階段，overlay 以「🚨 需人工複核」紅字面板呈現
- [x] 臨床規則可審核性：`--explain-rules` CLI 輸出規則對照表（白話條件＋醫學依據＋命中行為，供臨床人員審核，不啟動 GUI）；命中時記錄實際比中的關鍵字證據（`audit_line` / hook log）；YAML 規則包強制 `description`（沒寫說明的規則不載入，把可審核性變成上線門檻）
- [x] `AnnotationAccumulator` 接線：區域 chat 產生受限 `FindingDelta`，經人工
  Apply、result-revision 與 local-signal gate 後才寫回 overlay/report/export。

### v0.4.2 MEETI 1000+ harness / OpenRouter refresh (2026-07-02)

- [x] Local OpenClaw runtime validated at `2026.6.11`; Gateway compatibility
  remains `connect` + `chat.send` protocol 3 image attachments.
- [x] Desktop AI Provider settings include OpenRouter (`OPENROUTER_API_KEY`,
  `https://openrouter.ai/api/v1`) and preserve secrets outside git.
- [x] Full MEETI source archive from Zenodo record `18523205` is supported via
  `scripts\build-meeti-eval.py --extractor tar`; local scan found 9922
  PNG-bearing studies.
- [x] 1000-case strict mock eval and artifact verifier passed, including
  schema, bbox, can't-miss, raw-result, review-export, and
  `local_preflight_artifacts` gates.
- [x] Added deterministic local image-quality preflight metadata so unreadable
  image detection does not depend entirely on MLLM calls.
- [x] Added deterministic `local_signal_candidates` bbox proposals and gated
  them as `model_assist_artifacts`, reducing dependence on MLLM-only localization
  before expert review.
- [x] Added `scripts\check-real-model-readiness.py` and `-ManifestPath` support
  in the MEETI experiment runner, so real-model 1000-case runs fail fast with a
  machine-readable blocked artifact when credentials/artifacts are missing.
- [ ] Next clinical iteration: run paired real-model baseline vs MultiPass on
  the same 1000-case manifest and use expert review to refine prompt/rules for
  recurrent misses.

### v0.4.3 Provider profiles + waveform evidence audit (2026-08-04)

- [x] Provider profiles cover GPT-5.4 Mini, Luna, OpenRouter, Anthropic, Azure,
  and compatible endpoints. The later v0.4.5 release default is
  `openai/gpt-5.4-mini`.
- [x] Settings reads the actually active model and exposes a secret-free
  ECGFounder configuration status; the report Process tab records crop/refine,
  OpenClaw tools, waveform status, prediction count, and calibration state.
- [x] Windows stale Gateway locks recover using Win32 process-state checks
  instead of unreliable `os.kill(pid, 0)` behavior.
- [x] ECGFounder offline runs can retain all 150 scores while the live agent
  tool remains capped at 20; protocol/source hashes and label metadata are
  preserved for audit.
- [x] Leakage-aware five-fold MEETI research evaluation completed: 23 supported
  concepts, macro BA 0.865, top-20 concept recall 0.837, and 3-5 diagnosis
  complete recall 0.479. Thresholds remain research-only.
- [x] Superseded the Platform API credit blocker with a verified
  ChatGPT/Codex-subscription transport owned by the OpenClaw embedded agent;
  historical blocked canaries remain unchanged as dated evidence.
- [ ] Perform clean-machine Windows 10 verification. The modern runtime remains
  unsupported on Windows 7; any Win7 target needs a separately maintained
  legacy bundle and security policy.

### v0.4.4 Interactive regional review writeback (2026-08-04)

- [x] AI-box click and reviewer-drawn regions use an exact-crop, JSON-only
  OpenClaw follow-up contract. The model cannot emit coordinates.
- [x] `ADD` / `REVISE` / `RETRACT` stay advisory until an explicit reviewer
  Apply; stale result revisions are rejected and report triage never silently
  downgrades.
- [x] Deterministic crop signal audit (blank field, edge density, robust dynamic
  range, and pixel-density checks) blocks low-signal `ADD`/`REVISE`
  while preserving QA, manual regions, export, and reviewer-controlled retract.
- [x] Report, Process trace, JSON, and annotated PNG retain
  `interactive_ai_review` provenance and confirmation receipts.
- [x] Geometric dedup requires matching labels as well as IoU, preserving
  multiple diagnoses that legitimately share one image region.
- [x] Monotonic chat request ids discard late same-image answers and errors, in
  addition to result-revision protection across image changes.

### v0.4.5 MultiPass experiment protocol and observable startup (2026-08-05)

- [x] Reviewer-confirmed `ADD` / `REVISE` / `RETRACT` now reconcile summary,
  triage, checklist freshness, safety floor, and before/after provenance.
- [x] One typed EKG lead-inventory parser is shared by MultiPass, bbox
  calibration, schema validation, and UI; it recognizes clinical names such as
  `I`, `II`, and `V1` and validates 12 unique visible leads.
- [x] Experiment harness separates `minimal_control`, `single_pass`,
  `multipass`, and `multipass_ecgfounder`; completion requires strict pass
  >=0.75 and mean partial credit >=0.85, while incompatible comparisons fail
  closed by default.
- [x] Current strict 1,000-case mock MultiPass protocol completed 4,869 analyzer
  calls, 2,869 crops, 2,000 systematic probes, 1,000 review PNGs, and 865 bbox
  projection audits with zero failures/clamps/drift. Perfect mock scores are
  explicitly protocol evidence, not model accuracy.
- [x] Formal scoring uses 299 asserted-reference cases while 701 weak-label
  cases remain exploratory; 49 explicit-normal controls verify that the harness
  does not force an abnormal answer.
- [x] ECGFounder v3 traversed 1,000 paired waveforms, retained 999 eligible, and
  explicitly excluded one all-zero V5. Eligibility-aware reports preserve
  99.9% coverage and the reason instead of forcing a prediction.
- [x] Desktop Gateway migration/startup moved off the Qt thread, has a separate
  180-second readiness budget, displays `AI starting` / `AI ready` /
  `AI offline`, and generates an authenticated loopback token on first launch.
- [x] Fresh frozen bundle passed 4/4 source/verifier/real-EXE self-check and
  isolated authenticated Gateway start/connect/clean-stop smoke: 363.94 MiB,
  15,226 files, EXE SHA-256
  `444b99d4614f1f5f4616118f1c0ac35f35f9a79c15b24bc8366f60a13170a24d`.
- [x] Replaced the provider-credit dependency with the OpenClaw-owned
  subscription route and completed frozen paired/unseen canaries. Full-cohort
  completion and clinician review remain tracked below.

### v0.4.6 OpenClaw MultiPass paired evidence (2026-08-09)

- [x] Pin OpenClaw `2026.7.1-2`, Node `v24.18.0` and harness/plugin `1.5.7`;
  stage the official Codex package as OAuth-migration-only and verify no Codex
  agent runtime or Platform API route is used for inference.
- [x] Complete a frozen 32-case baseline/MultiPass pair: weak-label partial
  credit 0.253 to 0.480 with paired bootstrap CI and random-sign test, while
  retaining normal regressions and urgent misses in the report.
- [x] Complete an 8-case unseen engineering gate with raw JSON, tool/crop
  trajectories, review PNGs, coordinate audit and 60/100/180-second SLA proof.
- [x] Expose subscription route, Priority inference, MultiPass controls,
  ECGFounder ranked labels/rhythm measurement and auditable Process events in
  the desktop UI; export self-contained expert-review packages.
- [x] Build and verify the 368.01 MiB portable bundle; source suite is
  `915 passed, 3 skipped`, packaged opt-ins are 4/4, and native capture smoke
  passes.
- [ ] Complete the authoritative 9,922-case post-publication baseline/candidate
  pair from one frozen commit, then perform clinician review of marked images,
  normal false positives, urgent misses and coordinate alignment.
- [ ] Decide whether a separate single-pass and MultiPass-without-ECGFounder
  ablation is required after the primary two-arm full cohort finishes.

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
