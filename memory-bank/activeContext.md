# Active Context

## Current Eval Harness Focus (2026-07-02)

- Active goal: keep the local desktop OpenClaw co-reading app up to date,
  configurable for OpenRouter, clinically useful for image-assisted
  recognition/report/bbox review, and backed by a production-scale harness with
  at least 1000 verified images.
- Local OpenClaw runtime is updated and validated at `2026.6.11`; the app still
  uses only the stable public Gateway boundary (`connect` + `chat.send`,
  protocol 3 image attachments). `MIN_SAFE_OPENCLAW_VERSION` remains
  `2026.4.22` because no verified Gateway incompatibility was found.
- The desktop Settings dialog exposes AI Provider profiles including OpenRouter
  (`OPENROUTER_API_KEY`, `https://openrouter.ai/api/v1`). Saving a profile
  writes only app-managed provider/model config and keeps secrets in env/.env.
  Both the normal OpenClaw config and a generated OpenRouter config validated
  with the OpenClaw CLI.
- MEETI source: local `MEETI.rar` from Zenodo record `18523205` is available but
  gitignored. The builder can scan the full archive via Windows `tar`/`bsdtar`;
  current local scan found 9922 PNG-bearing studies.
- Production artifact gate: `data\eval-datasets\meeti-1000-all\manifest.json`
  was built with 1000 cases from the full MEETI archive. The mock strict eval at
  `data\eval\meeti-1000-mock-20260630-assist` completed 1000/1000 cases and
  `scripts\verify-eval-artifacts.py --min-cases 1000` passed:
  `min_cases`, `scorecard_complete`, `schema_gate`, `bbox_gate`,
  `cant_miss_gate`, `mock_perfect_gate`, `results_artifacts`,
  `local_preflight_artifacts`, `model_assist_artifacts`, and `review_artifacts`.
- Non-MLLM/model-assisted layers: `ImageProcessor.image_quality_profile()`
  records deterministic `local_image_quality` per eval result (size, aspect
  ratio, ink density, bright-pixel ratio, low-signal flag), and
  `ImageProcessor.local_signal_candidates()` records deterministic
  `local_signal_candidates` waveform/signal bbox proposals. These make
  blank/unreadable input detection and first-pass candidate boxes auditable
  without forcing every quality decision through an MLLM.
- Expert-review export now audits no-bbox cases at case level, so 1000-case
  review completeness is not inflated by bbox count alone. Review artifacts
  include PNG overlays, `bbox-audit.jsonl`, crop thumbnails, and `index.html`.
- Console-output hygiene: `run-eval.py` now bounds default per-case printing with
  `--case-print-limit 50`; use `--verbose` only for small diagnostic subsets.
  Avoid raw `tar -tf MEETI.rar` and broad recursive searches over generated data
  or OpenClaw internals in normal PowerShell sessions.
- Fresh checks on 2026-07-02: npm latest reports OpenClaw `2026.6.11`, local
  runtime is `2026.6.11`, 1000-case assist verifier passed, and targeted
  unit/smoke tests for the local assist gate passed.
- Real-model 1000-case accuracy gate is still credential-gated. Added
  `scripts\check-real-model-readiness.py` so this gap is now auditable: it
  checks provider key presence (e.g. `OPENROUTER_API_KEY` for
  `openrouter/...` models), 1000-case manifest size, completed mock artifact
  gate, and local OpenClaw runtime evidence, then writes `status=ready` or
  `status=blocked` without serializing secret values. Current local env is
  missing provider keys, so the readiness artifact should block until a key is
  supplied.
- `scripts\run-meeti-openclaw-experiment.ps1` now accepts `-ManifestPath` and
  passes `--manifest` to `run-eval.py`, so the real Gateway-backed experiment can
  run the same `data\eval-datasets\meeti-1000-all\manifest.json` used by the
  artifact gate instead of falling back to an older dataset selector.

## Current Eval Harness Focus (2026-05-30)

- Current user-directed run: full MEETI `openai/gpt-5.4-mini` strict MultiPass
  experiment is running under
  `data\experiments\meeti-full-multipass-20260530-221551-openai_gpt-5.4-mini`.
  It uses `-MultiPass -MultiPassMaxTargets 2 -RequirePerfect`; progress is
  observable via `eval\multipass-trace.jsonl`, raw `eval\results\*.json`,
  rebuilt partial scorecards, review PNGs, and Gateway/eval logs. This process
  was started before the newest checkpoint/postprocess wrapper changes, so it
  will not itself write `experiment.json` or `scorecard.partial.json` until a
  future run uses the updated wrapper.
- MultiPass eval is now testable from `scripts\run-eval.py` with
  `--multi-pass --multi-pass-max-targets N`. The harness wraps the real
  `MultiPassAnalyzer` and records per-image `openclaw_analyze_calls`,
  `zoom_passes`, and `crop_calls` in `multipass-trace.jsonl`.
- Scorecards now include clinical partial-credit scoring, strict pass rate, and
  per-target-axis performance. Partial credit weights are 30% abnormal-vs-normal
  severity, 20% exact severity, 35% positive keyword recall, and 15%
  pertinent-negative recall, but the negative component only counts when the
  case has expected negatives, and missed can't-miss labels cap partial credit
  at 0.40. Schema/bbox/cost/safety metrics remain separate.
- Paired baseline-vs-MultiPass comparison is available via
  `uv run python scripts\compare-eval-runs.py --baseline <single-pass experiment-or-eval> --candidate <multipass experiment-or-eval>`.
  It writes `comparison.json`/`comparison.md`, counts improved/regressed cases,
  reports partial-credit and strict-pass deltas, includes MultiPass call/crop
  cost, optional bbox low-signal summaries, and an exact paired sign-test
  p-value. It now rejects incomplete/error scorecards by default; use
  `--allow-incomplete` only for exploratory comparison of non-error shared cases.
- Existing raw `results/*.json` can be rescored without rerunning the model via
  `uv run python scripts\rebuild-eval-scorecard.py --eval-dir <eval> --manifest data\eval-datasets\meeti\manifest.json`;
  this is useful because the current long-running process started before the
  partial-credit/schema-gate/checkpoint changes.
- `scripts\run-meeti-openclaw-experiment.ps1` now writes `experiment.json` with
  `status=running` before the eval process starts, and after `run-eval.py`
  returns it postprocesses `scorecard.rebuilt.json` plus expert-review PNGs /
  bbox audit artifacts. Future `run-eval.py` executions also write
  `scorecard.partial.json` after each case and fail fast on repeated Gateway
  infrastructure errors.
- Eval scoring has been tightened: positive keyword recall is negation-aware
  (`no ischemia` no longer counts as an ischemia hit), incomplete
  `OutputValidator` results set `schema_ok=false`, can't-miss detection uses
  positive evidence only, and WNL / within-normal-range MEETI reports map to an
  explicit normal concept.
- The desktop app and eval path now pass the downscaled image size into
  `MultiPassAnalyzer` when available, so the resolution-aware manual-zoom guard
  is actually active instead of always digitally cropping.
- `MultiPassAnalyzer` target selection now includes `info` findings with bboxes
  after warning/critical findings, so a first pass that under-calls a suspicious
  ECG change as `info` still gets crop/refine attention.
- EKG skill prompt was tightened for waveform-only MEETI screenshots: 10-second
  rhythm-strip rate estimation, LVH voltage/strain checks, ST-T/ischemia axis
  consistency, and warning severity floor for clinically meaningful ST-T/LVH/rate
  abnormalities.
- Real 1-case `openai/gpt-5.4-mini` MultiPass smoke after prompt update produced
  3 OpenClaw `analyze` calls (coarse + 2 crop/refine), fixed severity/LVH/ischemia
  for `meeti_43522917`, but still missed bradycardia. This is now recorded as
  model/prompt diagnostic miss, not a Gateway/MultiPass harness failure.
- Expert review images can be exported from any eval directory with
  `uv run python scripts\export-eval-annotations.py --eval-dir <eval> --manifest data\eval-datasets\meeti\manifest.json`.
  The exporter now also writes `review\bbox-audit.jsonl` and `review\crops\*`
  with original-image pixel coordinates, clamped normalized coordinates, crop
  thumbnails, ink-pixel ratios, `low_signal`, `was_clamped`, and
  `invalid_reason`; low-signal bboxes are cross-marked in review PNGs so
  blank/irrelevant boxes can be separated from coordinate-pipeline errors. The
  exporter cleans generated review PNGs/crops by default to avoid stale expert
  review artifacts.
  Current partial full-run review output lives under
  `data\experiments\meeti-full-multipass-20260530-221551-openai_gpt-5.4-mini\eval\review`.
- OpenClaw runtime is local `2026.5.27`; model catalog has `openai/gpt-5.5` and `openai/gpt-5.4-mini`, but no `openai/gpt-5.5-mini`.
- `openclaw/openclaw.json` now defaults to `openai/gpt-5.5`.
- MEETI eval entry point: `uv run python scripts\run-eval.py --gateway ws://127.0.0.1:18789 --dataset meeti --timeout-sec 90 --require-perfect`.
- `--mock --dataset meeti --require-perfect` passes all 400 cases and proves scoring/artifact flow.
- Real GPT-5.5 MEETI 10-case probe completed with no timeout/parser crashes after per-image `analysis-<uuid>` session isolation and narrow bbox JSON repair. Current real metrics: schema 90%, bbox 100%, severity exact 70%, abnormal/normal 90%, mean keyword recall 37%; GPT-5.5 still does not meet PERFECT GATE.
- Remaining real misses are model/read-label/prompt issues (e.g. LVH/bradycardia/low-voltage keyword misses and one malformed/empty-summary schema failure), not OpenClaw Gateway protocol failures.
- Full real experiment wrapper: `powershell -ExecutionPolicy Bypass -File scripts\run-meeti-openclaw-experiment.ps1 -ModelId openai/gpt-5.5-mini -TimeoutSec 90 -RequirePerfect`. It writes `data\experiments\...\experiment.json` and blocks if the requested model is not in the OpenClaw catalog.
- Experiment records from wrapper validation:
  - `data\experiments\meeti-20260530-214839-openai_gpt-5.5-mini\experiment.json`: blocked because OpenClaw catalog does not expose `openai/gpt-5.5-mini`.
  - `data\experiments\meeti-20260530-214859-openai_gpt-5.4-mini\experiment.json`: completed 1-case runner smoke with experiment-local config/logs/eval artifacts.

> 📌 此檔案記錄當前工作焦點，每次工作階段開始時檢視，結束時更新。

## 🎯 當前焦點

- **四大核心維護章程已文件化 (2026-05-30)**：
  - README.md / README.zh-TW.md 改寫為 DICOM Overlay Agent 內容（移除 template 殘留），新增「四大核心」章節
  - AGENTS.md 改寫為四大核心 AI 維護 harness（取代過時的 Zotero/PubMed 內容）
  - 四核心：1) 影像判讀圖層互動（位置+內容）2) OpenClaw 判讀完整 harness 3) plugin 兼容穩定版本 4) 執行檔最小封裝
- 兼容性修正與 CI 重建已完成
- **6 組 Sonnet 平行查核 + 自主修正 (2026-05-30)**：修正多螢幕座標錯位（潛在 PHI 風險）、modality fallback、config 字串防呆；補 9 測試
- 目前已驗證：
  - Linux 可成功 `pip install -e '.[dev]'`
  - headless Qt 測試可執行（需系統套件 + `QT_QPA_PLATFORM=offscreen`）
  - **231 個 pytest 測試通過**

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
- enum→str modality 全面解耦（目前新增全新模態仍需在 `Modality` enum 加一行）
- 6 個既有 ruff 警告（eval_harness ARG001、overlay_window 全形標點等，與本次無關）
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
| Node.js portable binary | ✅ 完成（fetch-node.ps1） |
| PyInstaller 打包 | ✅ 完成（dicom-overlay-agent.spec） |

---
*Last updated: 2026-05-30*
