# Architecture

本文件描述 v0.4.7（2026-08-27）的桌面程式、OpenClaw agent、MultiPass
影像工具、座標投影與 MEETI 評估邊界。歷史 paired 結果以
[`docs/meeti-openclaw-experiments-2026-08-09.md`](docs/meeti-openclaw-experiments-2026-08-09.md)
為準；本輪實機驗收與尚待完成項目以 [`REAL_TEST_RUNBOOK.md`](REAL_TEST_RUNBOOK.md)
及實驗目錄內的機器可讀 state 為準。

## Runtime Overview

```text
DICOM viewer
    |
    | Win32 physical-pixel ROI capture
    v
ScreenMonitor + local image-quality/signal/layout aids
    |
    v
OverlayAgent -> MultiPassAnalyzer
    |              | coarse image turn
    |              | validated source-pixel crops
    |              | systematic EKG probes / rhythm strip
    |              | final reconciliation
    v              v
OpenClawClient -- public WebSocket connect/chat.send --> OpenClaw Gateway
                                                        | embedded agent
                                                        | modality skill
                                                        | dicom_bbox_validate
                                                        | optional ECGFounder tool
                                                        v
                                  release default: openai/gpt-5.4-mini
                          explicit acceptance override: openai/gpt-5.6-luna
                                      openai-chatgpt-responses transport
    ^
    | structured result, tool receipts, timing, provenance
    |
OutputValidator -> AnnotationAccumulator -> overlay / Process tab / review export
```

Python 桌面程式不匯入 OpenClaw plugin SDK 私有 API，只使用公開 Gateway
`connect` 與 `chat.send` 協定。OpenClaw embedded agent 擁有每一個影像回合、
工具呼叫與回覆；Codex app-server 或 Codex agent 不參與 ECG 判讀。

## Layer Boundaries

| Layer | Responsibility |
|---|---|
| `domain/` | `AnalysisResult`、finding/bbox、EKG layout、delta 與純規則；不依賴 GUI、網路或 OpenClaw |
| `application/` | `OverlayAgent`、MultiPass、rhythm-strip、hook 與人工確認寫回流程 |
| `infrastructure/` | capture、影像處理、Gateway client/runtime、subscription auth、validator、評分與 export |
| `presentation/` | Control bar、Settings、Summary/Process/Chat、overlay 與人工框選 |
| `openclaw/workspace/` | modality skills 與 native bounded tools；不擁有桌面座標或報告套用權限 |
| `scripts/` | build、release verification、MEETI manifest/eval/supervisor 與 artifact tooling |

## Authentication And Agent Ownership

Subscription-backed inference follows a deliberately narrow path:

1. The user signs in once with `codex login`; native `~/.codex/auth.json` is an
   authentication source, not an agent handoff target.
2. The pinned official `@openclaw/codex` `2026.7.1-1` migration provider is
   staged into the OpenClaw runtime as `oauth_migration_only`.
3. [`codex_subscription_auth.py`](src/dicom_overlay/infrastructure/codex_subscription_auth.py)
   copies only auth/model-cache inputs to a temporary directory, invokes the
   OpenClaw migration command, removes the temporary plugin configuration and
   deletes the temporary source.
4. The live provider is native OpenClaw `openai` with
   `api=openai-chatgpt-responses`. `OPENAI_API_KEY`, `CODEX_HOME`, Codex agent
   dependencies and platform binaries are excluded from this route.
5. A secret-free audit records `billing_route=chatgpt_codex_subscription`,
   `agent_runtime=openclaw`, and `codex_agent_runtime_enabled=false`.

The release default remains `openai/gpt-5.4-mini`. The 2026-08-27 Luna run used
an explicit `openai-codex` model override; it did not change the default and did
not transfer the agent loop from OpenClaw to Codex.

## 2026-08-27 Desktop Acceptance Boundary

The packaged app was exercised on a 2560×1600 Windows display at 150% DPI. The
viewer capture remained exactly `(19, 30, 1522, 1136)` in physical pixels, the
app reached `DISPLAYING`, and the export contained four diagnostic boxes, two
analysis-crop outlines, and a coordinate audit. All boxes stayed in bounds with
no clamping and no more than 0.368 px physical-edge drift. External Windows
capture correctly excluded the app's top-most panels.

Five OpenClaw-owned `gpt-5.6-luna` image turns took 146.915 seconds and recorded
111,833 total tokens. Subscription metering was US$0; the same traffic is about
US$0.017135 at published API token prices. These facts establish transport,
rendering, privacy, and geometry behavior—not diagnostic accuracy. The result
reported sinus rhythm/possible LVH while the reference described atrial
fibrillation with slow ventricular response, prolonged QT, poor R-wave
progression, and inferior ST-T changes. It is an explicit accuracy miss. A
two-case answer-free follow-up passed schema/bbox/SLA with zero JSON repair but
scored only 1/2 strict and 0.522 mean partial credit; its warning case missed
weak-label LVH and sinus rhythm. That run's source fingerprint was dirty while
release metadata was being synchronized, so a fresh unseen canary against the
final frozen release source remains pending.

The desktop Settings page identifies the route as either **OpenClaw agent |
ChatGPT subscription OAuth** or **OpenClaw agent | Provider API key**. MEETI
real-experiment runners require the subscription route and fail closed if the
effective config, provider logs or trajectory show another owner/transport.

## MultiPass Image Workflow

MultiPass is the product's core interpretation path, not a prompt-only wrapper:

1. Preserve the exact source ROI dimensions and digest; compute deterministic
   image-quality, ink/signal candidates, EKG row geometry and lead inventory.
2. Ask OpenClaw for a compact coarse read of the whole image. Normal/WNL is a
   valid result; no rule requires an abnormal finding.
3. Build a bounded target plan from grounded coarse findings, local signal
   candidates and layout-derived limb/precordial/rhythm regions. Targets that
   overlap existing evidence are deduplicated.
4. Validate every proposed normalized bbox with the native
   `dicom_bbox_validate` tool. A receipt is bound to source digest, nonce,
   session/run and the exact coordinate multiset; rejected boxes are retracted.
5. Crop from the original source pixels, never from a previously scaled preview,
   and send each crop back as an independent OpenClaw image turn. Crop-local
   boxes are epsilon-clamped and projected back through the parent transform.
6. Run the bounded rhythm-strip pass when a trusted strip is available. A broad
   synchronized QRS run is reviewed as VT/NSVT versus artifact/conduction before
   secondary ST-T attribution.
7. When a manifest provides a cryptographically matched raw waveform, call
   `ecg_founder_analyze_waveform` at most once. It contributes uncalibrated
   ranked labels plus deterministic lead-II rate/R-R regularity only; it has no
   screenshot localization and cannot independently create a bbox.
8. Perform a final OpenClaw reconciliation over `KEEP`, `ADD`, `REVISE`, and
   `RETRACT`, then apply grounding, uncertainty, negative/normal, deadline and
   exact rhythm-duplicate guards before returning the structured report.

The target service levels are initial/coarse response within 60 seconds, first
crop/detail response within 100 seconds, and complete case within 180 seconds.
`fastMode` is requested on every whole-image, crop and finalization turn when
Priority inference is enabled. Timeouts and aborts are written to the trajectory;
the harness does not manufacture a fallback diagnosis.

## Tool Boundary

The live medical-image tool allowlist is intentionally small:

- `dicom_bbox_validate` is the normal image-analysis tool. It validates and
  normalizes boxes but does not diagnose pixels.
- `ecg_founder_analyze_waveform` is registered only with an authenticated
  loopback sidecar. It accepts an opaque artifact id, not a path or screenshot.
- Web search/fetch, shell, filesystem and general-purpose agent tools are denied
  during image analysis. The minimal-control experiment arm uses an explicit
  wildcard deny because OpenClaw treats an empty allowlist as unspecified.

ECGFounder Torch/checkpoint files stay outside the portable bundle. The full
contract, pinned hashes, eligibility rules and research metrics are in
[`docs/ecgfounder-tool.md`](docs/ecgfounder-tool.md).

## Coordinates And Review Export

Win32/`mss` capture uses virtual-desktop physical pixels while Qt renders in a
monitor's logical coordinates. Every displayed or exported box follows one
frame-bound path:

1. `ScreenMonitor.display_for_window()` resolves the viewer's physical monitor
   and stores its origin, bounds, device id and topology.
2. `OverlayAgent` retains the exact absolute `last_capture_rect` associated with
   the result.
3. `OverlayCoordinateFrame` maps physical edges to the selected Qt screen's
   logical frame using independent X/Y scales, including negative origins and
   mixed DPI.
4. Dynamic boxes undergo logical-to-physical round-trip calibration before
   drawing. Failed or excessive-drift projections remain audit rows and are not
   shown as valid annotations.
5. Click QA, reviewer-drawn regions and review export normalize against the same
   source `content_rect` and image digest.

Review packages include source image, structured result JSON, marked PNG,
exact crop files and coordinate audit. Diagnostic finding boxes are visually
distinct from dashed cyan analysis/probe crops. Audit rows retain normalized,
pixel and projected coordinates, clamp/invalid state, local signal evidence,
lead semantics and source digest so an expert can inspect alignment directly.

## Reviewer-Controlled Writeback

Clicking an AI box or drawing a region creates an exact source-pixel crop. A
local signal audit runs before a separate JSON-only OpenClaw follow-up. The model
cannot choose coordinates: `ADD` uses the reviewer region, while `REVISE` and
`RETRACT` stay bound to an existing finding id/bbox. Low-signal or failed audits
block report-changing additions/revisions; text QA remains visible.

Nothing changes until the reviewer clicks Apply. Result revision and monotonic
chat request ids reject stale responses, triage can only escalate, and accepted
changes retain `interactive_ai_review`, local-signal and confirmation provenance
in the report, Process tab, JSON and marked PNG.

## Blinded MEETI Evaluation

The full cohort has 9,922 ordered image cases. Evaluation uses two manifests:

- `full-9922.inference.json`: image/runtime inputs only, with no reference answer
  fields available during inference;
- `full-9922.gold.json`: opened only after inference to score the saved result.

[`run-meeti-paired-experiment.py`](scripts/run-meeti-paired-experiment.py) runs a
minimal one-look baseline and then a clinical MultiPass+matched-ECGFounder
candidate. Both arms must share manifest hashes, case order, model, OpenClaw
runtime, source/scorer/protocol fingerprint and agent ownership. State is written
atomically to `paired-experiment.json`; existing result sets resume only when
their provenance matches. Source changes between arms invalidate comparison.

Each case retains raw result/error JSON, provider/transport ownership evidence,
prompt-stage and tool trajectory, crop/probe files, bbox projection audit,
review PNG and timing. Aggregate scorecards separate asserted, candidate and
explicit-negative concepts, normal specificity, urgent/cannot-miss recall,
schema/bbox quality and partial credit. Paired comparison reports per-case
deltas, bootstrap confidence intervals and random-sign/sign-test p-values.
Weak report agreement is not medical diagnostic accuracy.

The authoritative status and completed results are documented in
[`docs/meeti-openclaw-experiments-2026-08-09.md`](docs/meeti-openclaw-experiments-2026-08-09.md).

## Portable Runtime

The portable directory contains the PyInstaller launcher, Python/Qt payload,
Node `v24.18.0`, slim OpenClaw `2026.7.1-2`, harness/plugin `1.5.8`, modality
skills and the OAuth-only migration provider. Runtime paths anchor to the EXE
directory rather than the launch working directory. Verification rejects `.env`,
MEETI images, waveform/checkpoint data, SQLite state, Torch, Codex agent runtime
dependencies and platform binaries.

The current v0.4.7 staged OpenClaw runtime is verified at 165.162 MiB, a
conservative 19.804 MiB reduction that retains seven required upstream
templates, internal `dist` chunks, `quickjs-wasi`, and `playwright-core`. The
last complete 2026-08-09 bundle was 368.01 MiB with a 7.05 MiB launcher; those
are historical values, not an estimate for v0.4.7. The final v0.4.7 bundle size,
file count, hash, and packaged smoke result remain pending a clean rebuild.

## Development Context

`memory-bank/` preserves active context, progress and decisions across coding
sessions. `.github/agents/`, `.github/hooks/` and `.claude/skills/` are developer
automation surfaces; they are not part of the medical-image runtime or inference
ownership chain.
