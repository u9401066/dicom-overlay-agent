# DICOM Overlay Agent

> 🩺 An autonomous co-reading agent that watches a DICOM viewer, sends screenshots to OpenClaw for interpretation, and overlays AI findings on top of the original image — the physician keeps the final call.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

🌐 [繁體中文](README.zh-TW.md)

Website: [u9401066.github.io/dicom-overlay-agent](https://u9401066.github.io/dicom-overlay-agent/)
(published and browser-verified on September 10; development evidence, not a clinical release).

## Development evidence — 2026-09-10 (not a release)

The active desktop acceptance target is **GPT-6 Astra low**, selected through
Settings as `openai-codex-astra`. Luna is no longer the acceptance target.
Real GUI captures reached the subscription transport with observed
`gpt-6-astra / low`: the first calibration export timed out at finalization
(179.252 s); a second completed finalization (165.043 s), but still required
review. These are two attempts on one case. A second distinct case completed
all four image turns in 140.481 s with verified clean ROI and Astra low runtime
receipts; clinical scoring is pending. The next pilot case hit the 60 s initial
response deadline. This is not a completed 100-case cohort.
The historical September 2-3 Luna batch produced 60 exports and 43 timeouts
across 103 attempts; all 60 exported source images matched their intended
cases, which is identity evidence, not diagnostic accuracy.
See the [September 10 evidence update](docs/verification-2026-09-10.md).

The working tree identifies itself as `0.4.7` and the harness/plugin as `1.5.8`,
but this repository currently has **no Git tag and no GitHub Release**. Treat all
`0.4.7` entries as Unreleased until a clean build, the required live runs, CI,
tag, and release artifacts have passed.

Explicit provider profiles avoid conflating subscription allowance with API
billing. All keep the multimodal agent loop inside OpenClaw:

| Settings profile | Authentication / transport | Model | Billing evidence |
| --- | --- | --- | --- |
| `openai-codex-astra` — GPT-6 Astra via Codex Subscription | native OpenClaw `openai-chatgpt-responses`; local Codex sign-in; low reasoning effort; no Platform API key | `openai/gpt-6-astra` | subscription usage; cancelled/unreported turns are not zero usage |
| `openai-codex-luna` — GPT-5.6 Luna via Codex Subscription | local ChatGPT/Codex OAuth migrated into native OpenClaw `openai-chatgpt-responses`; no `OPENAI_API_KEY`, no Codex agent runtime | `openai/gpt-5.6-luna` | subscription usage; token cost below is only an API-equivalent estimate |
| `openai-luna` — GPT-5.6 Luna Vision (API key) | `OPENAI_API_KEY` through OpenClaw `openai-responses` | `openai/gpt-5.6-luna` | normal Platform API billing |

On 2026-09-02 the real desktop App/viewer/subscription route was attempted three
times on the first frozen critical ECG. These are negative/incomplete evidence,
not acceptance results:

| Desktop export | Wall time | Recorded usage | Outcome |
| --- | ---: | ---: | --- |
| `desktop-20260902-082210-259256` | 139.4 s | 74,786 total (48,789 input; 20,480 cached; 5,517 output; 3,217 reasoning), US$0.0167878 API-equivalent | `info`, 0 findings; incorrect |
| `desktop-20260902-090424-024627` | 61.673 s | 37,811 total (24,787 input; 10,752 cached; 2,272 output; 1,093 reasoning), US$0.00789884 API-equivalent | `info`, 1 possible-LVH finding and only 5 checklist rows; incomplete |
| `desktop-20260902-092532-259033` | 153.398 s | 87,694 total (61,500 input; 20,480 cached; 5,714 output; 3,053 reasoning), US$0.0195664 API-equivalent | `info`, 1 finding, `incomplete/review`; missed the critical reference |

The estimates use the [official GPT-5.6 Luna API rates](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
of US$0.20/M input, US$0.02/M cached input, and US$1.20/M output. They are not
subscription charges. The failed runs exposed Gateway/bbox-receipt and
critical-first reconciliation issues now under repair; none establishes medical
accuracy, latency acceptance, or release readiness.

- A purposefully gold-enriched, blinded pair of **128 unique multi-diagnosis
  ECGs** is frozen (seed `1946247532`, 24 critical/104 warning, 48 asserted/80
  partially uncertain, at least three canonical diagnoses each; pair id
  `7bdc87f6…8a46e0`). It has **not** completed the required real App run and is
  not prevalence-weighted population evidence.
- The partial-ECG v2 corpus contains eight deterministic variants (edge crops,
  central/narrow bands, hidden lead labels, and 48 px downsampling). Its 8/8
  result is **mock schema/bbox/partial-input plumbing only**; no real Luna
  diagnostic score is claimed.
- Seven deterministic clinical-consistency rules now come from canonical YAML,
  with generated human/agent views and an application-owned SQLite projection
  bound to registry SHA-256
  `d22a03e037293636c86ca029452a8486f93f5625cb5655b3381088b8cc1fc22c`.
  Schema/parity checks do not substitute for specialist clinical review or
  source licensing review; see [clinical knowledge governance](clinical_knowledge/README.md).
- Managed Gateway reuse now requires an atomic, secret-free ownership receipt
  binding PID, port, token SHA-256, launch owner, and one canonical absolute bbox
  audit path. A healthy listener without that exact receipt is refused, not
  adopted or killed.
- The latest complete clean bundle remains the historical 2026-08-09 build:
  7.05 MiB launcher, 94.74 MiB App+Python/Qt, and 368.01 MiB full bundle. Current
  `dist/` is runtime-polluted and is not release evidence. Implemented safe
  staging reductions and further candidates still require a clean measured
  rebuild; OpenClaw internal `dist`, provider, Playwright, QuickJS, TypeScript,
  and Node payloads are not candidates for unsupported pruning.
- Latest candidate OpenClaw `2026.9.3` passed isolated public protocol 4,
  exact synthetic PNG transport, final-event, and generated Astra-config checks.
  Core size is 175.683 MiB; OAuth-only staging, relocated templates, native bbox
  tools, state rollback, and a clean bundle still need proof. The active cohort
  keeps the existing pin. See the [September 10 audit](docs/openclaw-upgrade-audit-2026-09-10.md).

The earlier frozen 32-case pair, 8-case unseen engineering gate, and incomplete
9,922-case paired run remain historical evidence in the
[MEETI/OpenClaw evidence record](docs/meeti-openclaw-experiments-2026-08-09.md).

The agent never replaces the physician. It acts as a systematic *second-check*
to reduce omissions caused by fatigue, workload, or distraction. It cannot reach
the HIS API, so the screen is the only input: the user defines a screenshot ROI
(cropping known PHI), and the agent captures, analyzes, and annotates in the
background while the physician works normally.

## 🎯 Four Maintained Cores

This repository is maintained around **four product cores**. Every change must
keep these aligned (see [AGENTS.md](AGENTS.md) for the maintenance guardrails).

| # | Core | What it guarantees |
| --- | --- | --- |
| 1 | **Image-reading overlay interaction** (position + content) | AI findings land in the right *position* (bbox/region over the original image) with readable *content* (checklist + chat follow-up) |
| 2 | **Complete OpenClaw interpretation harness** | An executable, CI-verifiable contract proving the screenshot → analysis → overlay loop actually works |
| 3 | **OpenClaw plugin compatibility** | Talks to OpenClaw only through the stable public Gateway protocol, so it survives across OpenClaw releases |
| 4 | **Minimal packaged executable** | A tiny `.exe` launcher (<50 MB; the last complete 2026-08-09 build was 7.05 MiB) plus a verified portable bundle with pinned Node/OpenClaw |

Each core is detailed in the [Core Details](#-core-details) section below.

## 📁 Project Structure

```text
dicom-overlay-agent/
├── src/dicom_overlay/             # 🩺 Application (DDD layered)
│   ├── domain/                    #   entities, value objects, service interfaces
│   ├── application/               #   overlay_agent.py (use-case orchestration)
│   ├── infrastructure/            #   OpenClaw client, screen monitor, harness, runtime
│   └── presentation/              #   overlay_window, control_bar, roi_setup, settings
├── openclaw/                      # 🔌 Repo-local OpenClaw runtime + plugin/skills
│   └── workspace/
│       ├── plugins/               #   dicom-overlay-agent-harness/manifest.json
│       └── skills/                #   dicom-{ekg,cxr,ct-brain}-analysis SKILL.md
├── scripts/                       # 🔧 build-exe.bat, stage-openclaw-runtime.ps1, harness runners
├── dicom-overlay-agent.spec       # 📦 PyInstaller spec (minimal exe)
├── config.yaml                    # ⚙️ ROI, region_maps, hash, gateway settings
├── spec.md                        # 📜 System specification
├── memory-bank/                   # 🧠 Project memory
├── .github/agents/ · .claude/skills/   # 🤖 AI dev harness (agents, skills, instructions)
├── README.md / README.zh-TW.md
└── CONSTITUTION.md · ARCHITECTURE.md · CHANGELOG.md · ROADMAP.md
```

## 🚀 Quick Start

### Run from source (Windows)

```powershell
# 1. Sync the Python environment (uv-first)
uv sync --all-extras

# 2. Install the repo-local OpenClaw runtime once
scripts\install-openclaw-local.bat

# 3. Launch (the Gateway is started/stopped automatically)
start.bat
```

On first launch you define the screenshot **ROI** (cropping PHI) and pick the
trigger mode. The agent then monitors the DICOM viewer and overlays findings.

To use ChatGPT/Codex subscription allowance instead of a Platform API key, run
`codex login` once, then select **OpenAI Subscription via OpenClaw** in Settings.
The pinned official `@openclaw/codex` package is enabled only long enough to
import OAuth state into the isolated OpenClaw home and is removed from live
plugin config before inference. OpenClaw remains the agent-loop owner; the
bundle contains no Codex agent runtime or platform binaries. A secret-free
audit is written to `data/tmp/codex-auth-import.json`.

### Build the portable executable

```powershell
scripts\build-exe.bat        # PyInstaller → dist\DICOMOverlayAgent\
```

See [Core 4](#core-4--minimal-packaged-executable) for the size budget.

## 🧩 Core Details

### Core 1 — Image-reading overlay interaction

The physician reads the original image; the agent annotates *on top* of it.

- **Position** — AI returns normalized `0-1` bounding boxes (`Finding.bboxes`).
  [`__main__.py`](src/dicom_overlay/__main__.py) highlights AI bboxes first and
  falls back to static `region_maps` resolved by
  [`region_mapper.py`](src/dicom_overlay/infrastructure/region_mapper.py). AI
  bboxes now pass through
  [`overlay_highlight_builder.py`](src/dicom_overlay/infrastructure/overlay_highlight_builder.py),
  which records PHI-free projection audit rows and withholds any dynamic bbox
  whose round-trip drift calibration fails before it reaches the physician
  overlay.
  The capture/display path is monitor-bound: Win32 supplies the exact physical
  display frame, Qt supplies that display's logical frame, and
  [`overlay_geometry.py`](src/dicom_overlay/infrastructure/overlay_geometry.py)
  converts physical edges into overlay-local coordinates. Negative monitor
  origins and mixed-DPI layouts therefore use the same saved capture rectangle
  for drawing, click QA, user annotation, and review export.
- **Content** — a draggable [`SummaryPanel`](src/dicom_overlay/presentation/overlay_window.py)
  shows a systematic checklist (16 keys for EKG, a 10-axis read for CXR);
  abnormal items surface first, normal ones collapse. A
  [`ChatPanel`](src/dicom_overlay/presentation/overlay_window.py)
  lets the physician ask follow-up questions about the same image.
- **Reviewer-confirmed regional writeback** — clicking an AI box or drawing a
  reviewer region sends the exact source-pixel crop through a bounded refine
  turn and then a separate structured OpenClaw follow-up contract. Both turns
  retain their session, run, and tool receipts. The model may propose `ADD`,
  `REVISE`, or `RETRACT`, but
  it cannot return or move coordinates and nothing changes until the reviewer
  clicks **Apply to report**. A deterministic local signal gate combines dark
  pixels, edge density, robust dynamic range, and blank-field checks to block
  every report-changing proposal when the crop is low-signal or its audit is
  missing/failed; accepted changes retain
  `interactive_ai_review` provenance in the report, Process trace, JSON, and
  annotated PNG export. Overlapping boxes with different diagnostic labels are
  preserved as separate findings.
- **Multi-pass review** — [`multi_pass.py`](src/dicom_overlay/application/multi_pass.py)
  re-reads abnormal regions at full ROI resolution and reserves part of the
  bounded crop budget for layout-derived EKG limb/precordial discovery probes,
  so later turns can find an omission that had no coarse-pass bbox. Because the
  only input is a screen capture (≤4K), a region too small in captured pixels
  cannot be digitally enlarged usefully; instead it surfaces a `zoom_hints`
  prompt asking the physician to zoom in the DICOM viewer and re-capture.
- **Controls** — a small [`control_bar.py`](src/dicom_overlay/presentation/control_bar.py)
  offers pause / settings / manual re-trigger; panels are frameless,
  stay-on-top, and drag-to-move (`_DraggableWindowMixin`).
- **Privacy** — [`roi_setup.py`](src/dicom_overlay/presentation/roi_setup.py)
  crops the capture region so known PHI never leaves the workstation.

### Core 2 — Complete OpenClaw interpretation harness

The interpretation loop is backed by an executable, CI-verifiable contract.

- [`image_harness_smoke.py`](src/dicom_overlay/infrastructure/image_harness_smoke.py)
  drives the full loop: synthetic image → `chat.send` with image attachment →
  Gateway event stream → result/log artifacts.
- [`image_harness_validator.py`](src/dicom_overlay/infrastructure/image_harness_validator.py)
  (`verify_image_harness_artifacts`) asserts the **gateway contract**, the
  **image payload proof**, and (optionally) the desktop viewer display.
- [`output_validator.py`](src/dicom_overlay/infrastructure/hooks/output_validator.py)
  enforces the 16-key result schema before anything reaches the overlay.
- Skills under [`openclaw/workspace/skills/`](openclaw/workspace/skills) define
  the per-modality prompts (`dicom-ekg-analysis`, `dicom-cxr-analysis`,
  `dicom-ct-brain-analysis`) including the bounding-box instructions.
- Runners: [`scripts/run-image-harness-smoke.py`](scripts/run-image-harness-smoke.py)
  and [`scripts/verify-image-harness.py`](scripts/verify-image-harness.py).
- [`eval_harness.py`](src/dicom_overlay/infrastructure/eval_harness.py) +
  [`scripts/run-eval.py`](scripts/run-eval.py) score recognition against a
  labeled dataset: axis×severity coverage, pertinent-negative recall, and a
  **can't-miss hard gate** (missing a STEMI / tension pneumothorax / etc. fails
  CI with a non-zero exit code).
- [`scripts/run-meeti-paired-experiment.py`](scripts/run-meeti-paired-experiment.py)
  runs a resumable blinded pair from one frozen source fingerprint: a minimal
  one-look baseline followed by the clinical MultiPass candidate. The answer-free
  inference manifest is kept separate from the gold manifest, runtime ownership
  must resolve to OpenClaw, and any Codex agent route, Platform API key route,
  manifest mismatch, or source/scorer drift fails closed. It preserves raw JSON,
  provider and tool receipts, crop traces, review PNGs, coordinate audits,
  scorecards, paired bootstrap/sign tests, and atomic supervisor state.
- Production-scale ECG evaluation uses the published MEETI source dataset
  (Zenodo record `18523205`, `MEETI.rar`, about 10k ECG images) under its access
  and derivative-data terms. The local gate
  builds a minimum 1000-case manifest with
  [`scripts/build-meeti-eval.py`](scripts/build-meeti-eval.py), runs
  [`scripts/run-eval.py`](scripts/run-eval.py), exports expert-review images
  with [`scripts/export-eval-annotations.py`](scripts/export-eval-annotations.py),
  then rejects incomplete artifacts through
  [`scripts/verify-eval-artifacts.py`](scripts/verify-eval-artifacts.py).
  Large runs are OOM-hardened: `run-eval.py` refreshes
  `scorecard.partial.json` every 50 cases by default instead of rewriting the
  full partial scorecard after every image (`--partial-scorecard-interval 0`
  writes only final/abort checkpoints).
- Clinical accuracy hardening (2026-07-05): the EKG skill runs a **Step 0
  lead-localization** pass that stays general ("declare, don't assume") — it
  reads the printed lead labels, inventories only the leads actually visible,
  marks unlabeled panels `unknown`, and gates lead-dependent conclusions
  (STEMI territory, axis, R-wave progression, chamber enlargement) on the
  captured leads, so a single rhythm strip or a partial/non-standard capture
  never triggers a 12-lead-only claim. The recognition scorer folds hyphen/
  plural variants and credits clinical synonyms/abbreviations (RBBB, afib, LVH,
  PVC…) so a correct read is not scored as a miss, while negation and genuine
  disagreements still count as misses.
  [`scripts/analyze-eval-failures.py`](scripts/analyze-eval-failures.py)
  aggregates per-run failure modes (severity confusion, missed keywords, schema
  failures, per-axis fail rates) to steer the next harness increment.
- Model-assisted refinement (2026-07-05): two bounded extra passes attack the
  genuine misses the mining surfaced. **Empty-summary retry** —
  [`run-eval.py`](scripts/run-eval.py) re-sends once when a read comes back with
  a blank summary and no findings (a transient model glitch), instead of banking
  a 0-score hard failure. **Rhythm-strip second pass** —
  [`rhythm_strip.py`](src/dicom_overlay/application/rhythm_strip.py) crops the
  model-declared `layout.rhythm_strip_bbox` out of the full-resolution image and
  re-reads just the strip to recover rate / rhythm / P-wave / AV-block findings,
  merging them escalate-only (never downgrades). It stays layout-general: a no-op
  unless Step 0 localized a rhythm strip, so single-strip / partial / non-standard
  captures are never cropped on a guess. Toggle with `--no-rhythm-strip-pass`.
- Local test runs should use
  [`scripts/run-tests-safe.cmd`](scripts/run-tests-safe.cmd). It runs pytest
  through the existing uv-managed `.venv\Scripts\python.exe` instead of
  `uv run`, routes temp files under `data/tmp/pytest-safe`, disables the pytest
  cache provider, and defaults to the unit+smoke suite. To avoid one long-lived
  pytest process OOMing on Windows, the `.cmd` wrapper delegates to
  [`scripts/run_pytest_safe.py`](scripts/run_pytest_safe.py), which runs each
  default `test_*.py` file in its own short pytest process. Pure pytest options
  such as `-q` are applied to every batch; explicit directories such as
  `tests/unit -q` and multiple explicit test files are now expanded into
  per-file batches too. A single explicit test file such as
  `tests/unit/test_agent.py -q` stays in one targeted pytest session. Full
  integration tests remain available by passing explicit paths. Prefer this
  over PowerShell on memory-constrained Windows sessions. The runner takes a repo-local
  `data/tmp/pytest-run.lock`, so a second pytest command exits before spawning
  more Python processes. During this guarded test path it also sets
  `DICOM_OVERLAY_TEST_DISABLE_REAL_OPENCLAW=1`, so accidental real Gateway /
  OpenClaw launches fail fast unless an explicit integration run opts in. For a
  deliberate diagnostic run of the old one-session behavior, set
  `DICOM_OVERLAY_TEST_SINGLE_SESSION=1`.
- The desktop Gateway launcher uses a repo-local
  `data/tmp/openclaw-gateway.lock` while the OpenClaw subprocess is alive, and
  Windows launches use `CREATE_NO_WINDOW`. The legacy real-stack batch launcher
  no longer uses `cmd /k` for the Gateway path; it starts the Gateway with
  `start /B` and redirects output to `gateway.log` to reduce stray
  `conhost.exe` windows. The MEETI real-experiment Python runner uses the same
  Gateway lock before spawning OpenClaw, so GUI/manual runs and experiment runs
  cannot silently launch multiple Gateways at once.
- Local lint runs should use
  [`scripts/run-ruff-safe.cmd`](scripts/run-ruff-safe.cmd) for the same reason:
  it calls `.venv\Scripts\ruff.exe` directly, takes
  `data/tmp/ruff-run.lock`, and avoids both AppData cache failures and
  concurrent `uv.exe` launches.
- Each raw eval result includes deterministic `local_image_quality` metadata
  from [`screen_monitor.py`](src/dicom_overlay/infrastructure/screen_monitor.py):
  image size, aspect ratio, ink/bright-pixel density, entropy, edge density,
  robust dynamic range, and low-signal flag. This cheap local preflight is the
  harness can detect unreadable/blank/low-signal inputs without spending every
  decision on an MLLM.
- Each raw eval result also includes deterministic `local_signal_candidates`:
  a local threshold/ink bounding-box proposal for ECG-like line images. This is
  intentionally non-diagnostic, but it gives the reviewer and harness a cheap
  local candidate box before the MLLM read. In multi-pass eval runs, those
  local candidate boxes now act as a fallback crop target when the coarse MLLM
  read is non-normal but omitted bboxes, so bbox crop re-analysis no longer
  depends entirely on the model's first-pass coordinates. The
  `multipass-trace.jsonl` artifact records `local_candidate_count` and
  normalized `local_candidate_regions`, EKG systematic probe targets, and
  planned/completed counts per case for audit. When that trace
  exists, `scripts/verify-eval-artifacts.py` validates those fields via
  `multipass_trace_artifacts`; production multi-pass runs should add
  `--require-multipass-trace` so missing crop re-analysis trace artifacts fail
  the gate. Current EKG experiments also use
  `--require-ekg-systematic-probes`, which rejects legacy runs that only refine
  findings already proposed by the coarse pass.
- [`scripts/check-real-model-readiness.cmd`](scripts/check-real-model-readiness.cmd)
  is the OOM-safe readiness launcher that bridges the mock artifact gate to
  real-model benchmarking. It calls the existing uv-managed
  `.venv\Scripts\python.exe`, takes `data/tmp/readiness-run.lock`, and then calls
  [`scripts/check-real-model-readiness.py`](scripts/check-real-model-readiness.py).
  It writes a
  `ready` or `blocked` JSON artifact for the selected OpenClaw/OpenRouter model,
  checking credentials, manifest size, OpenClaw runtime evidence, and the
  completed 1000-case artifact gate without exposing secret values. Pass
  `--dotenv .env` to include repo-local credentials in the check without
  printing or serializing their values. Add `--probe-provider` before real
  runs to verify provider egress and advertised image-input support; provider
  probe failures block the readiness report before the Gateway/eval harness
  spends time on a doomed run.
- [`scripts/run-meeti-openclaw-experiment.cmd`](scripts/run-meeti-openclaw-experiment.cmd)
  is the preferred non-PowerShell launcher for reproducible real
  Gateway-backed MEETI experiments. It calls the existing uv-managed
  `.venv\Scripts\python.exe`, takes `data/tmp/meeti-run.lock`, then calls
  [`scripts/run-meeti-openclaw-experiment.py`](scripts/run-meeti-openclaw-experiment.py).
  The Python runner supports `--provider-profile openai-luna` /
  `openai-vision` / `openrouter`,
  generates an experiment-local OpenClaw config before model-catalog checks,
  takes `data/tmp/openclaw-gateway.lock` before spawning the Gateway, retries
  the eval if the Gateway is still starting, exports review artifacts, and marks
  the experiment failed when `scorecard.json.error_count > 0` even if the
  underlying eval command exits 0. It also runs
  `scripts/verify-eval-artifacts.py` after review export; bounded smoke runs use
  `--limit` as the verification minimum, full runs default to 1000 cases, and
  `--multi-pass` automatically adds `--require-multipass-trace`,
  `--require-multipass-refinement`, and
  `--require-ekg-systematic-probes`.
- Latest OOM-fix verification:
  `data/eval/meeti-1000-mock-oomfix-20260702` ran 1000/1000 MEETI cases,
  exported review artifacts, and passed `scripts/verify-eval-artifacts.py
  --min-cases 1000` including `local_preflight_artifacts`,
  `model_assist_artifacts`, and `review_artifacts`. Future MEETI experiment
  verifier runs add `--require-projection-audit`, requiring bbox audit rows
  with model boxes to include overlay projection round-trip calibration
  fields before a production run is considered artifact-complete.

### Core 3 — OpenClaw plugin compatibility

The app talks to OpenClaw **only through the stable public Gateway protocol**
(`connect` + `chat.send`), never importing plugin SDK internals, so it stays
portable across OpenClaw releases.

- [`openclaw_runtime.py`](src/dicom_overlay/infrastructure/openclaw_runtime.py)
  pins `MIN_SAFE_OPENCLAW_VERSION` (`2026.4.22`) and builds the harness
  manifest / chat frame against the documented schema. The client advertises
  protocol `3..4`; pinned OpenClaw `2026.7.1-2` must return a validated
  `hello-ok` protocol `4` receipt. Images remain in `params.attachments[]`
  with `type` / `mimeType` / `content`.
- [`openclaw/package.json`](openclaw/package.json) tracks the runtime version
  (packaged and validated as `openclaw 2026.7.1-2`) and the minimum-safe floor.
- [`manifest.json`](openclaw/workspace/plugins/dicom-overlay-agent-harness/manifest.json)
  declares the plugin compatibility window.
- The OpenClaw-side specialization is intentionally plugin-shaped:
  `dicom-overlay-agent-harness` advertises medical-image interpretation,
  bbox crop re-analysis, coordinate drift calibration, and overlay annotation
  capabilities. The desktop app still treats it as a Gateway-only integration,
  so compatibility is tested through `connect` / `chat.send` artifacts instead
  of private OpenClaw plugin SDK imports.
- The same native plugin has an opt-in
  `ecg_founder_analyze_waveform` bridge for
  [PKUDigitalHealth/ECGFounder](https://huggingface.co/PKUDigitalHealth/ECGFounder).
  It is registered only when an authenticated loopback sidecar is configured,
  accepts opaque waveform artifact ids rather than paths, and never treats a
  screenshot as a waveform or its class scores as image bboxes. Torch and the
  370 MB checkpoint stay outside the portable app. See
  [the external tool contract](docs/ecgfounder-tool.md).
  Each evaluation binding also carries a random per-case evidence nonce; only
  one successful receipt matching that nonce, artifact digest, pinned model
  revision, and checkpoint is accepted. The current desktop has no trusted
  study-to-waveform resolver, so Settings reports this integration as an
  evaluation sidecar rather than implying that screenshot reads use it.
  The paired MEETI build now includes 1,000 matched raw 12-lead waveforms; a
  real pinned-checkpoint batch traversed all 1,000: 999 were eligible and one
  all-zero V5 lead was explicitly rejected. Each accepted result remains
  uncalibrated supporting evidence. A separate full-150-score evaluator uses
  deterministic five-fold out-of-fold threshold selection and never treats
  report silence as a negative label. Across 23 sufficiently supported mapped
  concepts it measured macro balanced accuracy 0.865, sensitivity 0.847, and
  specificity 0.883 against explicit-normal controls. Holdout top-20 mapped
  concept recall was 0.837, but complete recall for cases with 3-5 mapped
  diagnoses was only 0.479, below the 0.75 product target. These are
  waveform-only weak-label research metrics, not screenshot-agent accuracy or
  deployment calibration.
- **Rule:** before bumping OpenClaw, confirm the `connect` / `chat.send` schema,
  image attachment, OAuth/config migration, state rollback, and clean packaged
  size. The latest `2026.9.3` candidate passes the isolated protocol/config
  checks, but migration-only staging, native clinical tools, and the other gates
  remain open; the active pin stays `2026.7.1-2`.
- The desktop Settings dialog exposes AI Provider profiles and selects the
  model and transport currently active in OpenClaw. The release-default
  `openai-vision` profile uses a Platform API key; **OpenAI Subscription via
  OpenClaw** uses local ChatGPT/Codex OAuth and native
  `openai-chatgpt-responses` for `openai/gpt-5.4-mini`. Luna is separately
  explicit: `openai-codex-luna` uses that subscription transport with no API
  key, while `openai-luna` requires `OPENAI_API_KEY` and uses
  `openai-responses`. All image turns remain owned by the OpenClaw embedded
  agent. OpenRouter is also available through
  `OPENROUTER_API_KEY` and `https://openrouter.ai/api/v1`. Saving a profile
  writes only app-managed OpenClaw provider/model sections and keeps secrets in
  environment variables or `.env`, not in git or experiment logs.
- Long medical-image inference uses the app's explicit inference timeout rather
  than client-side WebSocket keepalive pings, preventing false 1011/keepalive
  failures while OpenClaw is waiting on a model response.
- Latest real-model smoke evidence (2026-07-02):
  `data/experiments/meeti-openrouter-minimax-m3-1case-cmd-wrapper-20260702`
  reached Gateway `connect` + `chat.send` with one MEETI image using
  `openrouter/minimax/minimax-m3` and recorded scorecard/raw/review artifacts.
  It failed as `completed_with_failures` because local network egress to
  OpenRouter was reset (`ECONNRESET` / WinError 10054); OpenClaw could not fetch
  OpenRouter model capabilities/pricing or call `minimax/minimax-m3`. This is
  an environment/network blocker, not a schema/bbox harness pass. The offline
  readiness artifact
  `data/experiments/real-model-readiness-20260702-openrouter-minimax-m3.json`
  is `ready` with `OPENROUTER_API_KEY` present and the 1000-case mock artifact
  gate already verified, while
  `data/experiments/real-model-readiness-20260702-openrouter-minimax-m3-probed.json`
  and
  `data/experiments/real-model-readiness-20260702-openrouter-minimax-m3-cmd-probed.json`
  are `blocked` by the provider egress probe; the newer artifact also proves
  the readiness path itself now uses the OOM-safe `.cmd` wrapper. The latest
  OOM-safe probe
  `data/experiments/real-model-readiness-20260702-openrouter-minimax-m3-current-probed.json`
  still has the key, OpenClaw runtime, 1000-case manifest, and mock artifacts
  ready, but blocks before Gateway startup with WinError 10013 socket permission
  denial.
- Historical real-model evidence (2026-07-05): on a network where OpenRouter and Anthropic
  are firewall-reset, `api.openai.com` is reachable and `OPENAI_API_KEY` is
  valid. A MEETI single-case real run with `openai/gpt-5.5` + the
  `openai-vision` provider profile reached Gateway `connect` + `chat.send`,
  returned a schema-valid read, and passed strict/schema/bbox at 1.0
  (`gateway_mode: real`). That dated run used the then-current model profile;
  the runner and Settings default are now `openai/gpt-5.4-mini`. Copilot
  subscription models (e.g. MAI Flash) remain unusable as an API provider
  because they use an OAuth device-token flow, not an API key.
- Historical experiment status (2026-08-05, superseded by the subscription
  evidence above): the requested
  `openai/gpt-5.4-mini` MultiPass canary used the full `manifest-v2` protocol,
  clinical prompt, rhythm pass, three refinement slots, and two systematic
  EKG probes. The catalog declared `text,image`; the Gateway became ready in
  72.359 seconds and the first image request reached OpenAI. The provider then
  returned `provider_credit_exhausted`, so the run is `blocked` and no answer
  is scored. No full four-arm accuracy claim is made until minimal-control,
  clinical single-pass, MultiPass, and MultiPass+ECGFounder all finish. The
  independent ECGFounder waveform batch traversed 1,000/1,000 paired cases,
  with 999 eligible and one flat-lead exclusion.
  See [`docs/verification-2026-08-05.md`](docs/verification-2026-08-05.md).

### Core 4 — Minimal packaged executable

The goal is a tiny launcher and a lean, portable bundle that runs from a USB
stick. The bundle is built with [`scripts/build-exe.bat`](scripts/build-exe.bat).

- [`dicom-overlay-agent.spec`](dicom-overlay-agent.spec) excludes heavy,
  unused libraries (`numpy`, `scipy`, `matplotlib`, `pandas`, `imagehash`),
  prunes Qt modules the overlay never loads (WebEngine, Qml/Quick, Pdf,
  Multimedia, the ~20 MB `opengl32sw.dll` software GL fallback, qml/translations
  data), and builds a windowed (`console=False`) app. The release build pins
  64-bit CPython 3.13.12 through `uv` and bundles an exact PyInstaller/Pillow/
  PyQt toolchain receipt. UPX is enabled only when the executable is present;
  verification then requires an observable UPX-marked PE payload. Otherwise
  the manifest explicitly records a comparable `no_upx_baseline` instead of
  claiming compression that did not occur.
- [`scripts/stage-openclaw-runtime.ps1`](scripts/stage-openclaw-runtime.ps1)
  stages a *slim* OpenClaw runtime, dropping non-Windows native payloads and the
  disabled UI / browser / voice plugins so only the Gateway surface ships. It
  also removes npm-package `.env*` development files; the packaged verifier
  rejects any environment file that reaches the final bundle. The current
  staging gate also preserves and hashes seven required upstream templates,
  removes PDB and tree-sitter C/H development files, and explicitly protects
  OpenClaw `dist`, `quickjs-wasi`, and `playwright-core`.
- [`scripts/fetch-node.ps1`](scripts/fetch-node.ps1) downloads a portable
  `node\node.exe`; when present it is bundled and
  [`gateway_manager.py`](src/dicom_overlay/infrastructure/gateway_manager.py)
  prefers it over system Node.js, giving a true zero-install bundle.
- `pywin32` is a Windows-only conditional dependency to keep Linux/CI installs
  clean.
- **Portable plug-and-play** — when frozen, runtime paths anchor to the
  executable's folder (not the launch `cwd`, which may be `System32`) via
  [`app_paths.py`](src/dicom_overlay/infrastructure/app_paths.py), so the bundle
  also writes a relative configured log beside the bundle. Run
  `DICOMOverlayAgent.exe --selfcheck` to verify Node.js, the OpenClaw runtime, a
  writable base, and `config.yaml` all resolve — without launching the GUI or
  contacting an LLM (exit 0 = ready).

**Size budget and measured evidence:**

| Artifact | Budget | Verified measurement |
| --- | --- | --- |
| `DICOMOverlayAgent.exe` launcher | < 50 MiB | **7.05 MiB** in the last complete 2026-08-09 build |
| App + Python/Qt layer | < 100 MiB | **94.74 MiB** in the last complete 2026-08-09 build |
| Unreleased staged OpenClaw runtime | < 500 MiB | **165.162 MiB** |
| Conservative staging reduction | - | **19.804 MiB** |
| Portable Node.js `v24.18.0` | - | **88.25 MiB** |
| Last complete zero-install bundle (2026-08-09) | < 650 MiB | **368.01 MiB** |
| Unreleased full zero-install bundle | < 650 MiB | **Pending clean rebuild; no estimate** |

The historical clean manifest records 7,397,370 B for the launcher, 99,338,066 B
for App+Python/Qt, 194,011,520 B for OpenClaw, 92,534,088 B for Node, and
385,883,674 B total. Current `dist/` is 378.18 MiB but includes 10.156 MiB of
runtime residue, so it is not release evidence.

The verified Unreleased stage is 165.162 MiB and keeps required templates, `dist`,
and plugin surfaces intact on purpose. Pruning internal `dist` chunks would
couple the app to OpenClaw internals and break **Core 3** across releases, so
implemented safe reductions trim PDB/tree-sitter headers (19.804 MiB), foreign
native payloads (0.642 MiB), and Pillow AVIF (7.471 MiB) around the runtime.
The resulting ~340.3 MiB arithmetic is not a measured build. Next gated
candidates are win32ui/MFC (6.41 MiB while preserving pythoncom/win32com SAPI),
unused Qt plugins (~3.87 MiB), and unused Pillow codecs (~0.70 MiB). A new total
will be published only after a clean rebuild and packaged verification.

## 📋 Documentation

- [System Spec](spec.md) - Detailed system specification
- [Architecture](ARCHITECTURE.md) - System architecture
- [Constitution](CONSTITUTION.md) - Highest principles
- [Changelog](CHANGELOG.md) - Version history
- [Roadmap](ROADMAP.md) - Feature planning
- [Real Test Runbook](REAL_TEST_RUNBOOK.md) - Live stack testing
- [2026-09-02 Verification Record](docs/verification-2026-09-02.md) - Current evidence, failures, and unfinished gates
- [Evaluation Cohorts](docs/evaluation-cohorts.md) - 9,922/128/partial corpus identities and claim boundaries
- [OpenClaw 2.x Decision](docs/openclaw-2x-decision-2026-09-02.md) - Isolated 2026.8.2 evidence and deferred-upgrade gates
- [Latest OpenClaw Audit](docs/openclaw-upgrade-audit-2026-09-10.md) - 2026.9.3 protocol/config proof and measured adoption work
- [Clinical Knowledge Governance](clinical_knowledge/README.md) - Canonical YAML, human/agent steps, and SQLite parity
- [AGENTS.md](AGENTS.md) - AI maintenance guardrails for the four cores
- [Image-agent harness reference review](docs/harness-reference-review-2026-08-28.md) - Public patterns adopted without adding a packaged runtime dependency
- [MEETI/OpenClaw Experiment Record](docs/meeti-openclaw-experiments-2026-08-09.md) - Real paired/unseen results, tools, SLA, and claim boundaries
- [ECGFounder Tool Contract](docs/ecgfounder-tool.md) - External waveform evidence boundary
- [2026-08-05 Verification Record](docs/verification-2026-08-05.md) - MultiPass, real canary, coordinates, bundle hashes, and blockers
- [GitHub Pages source](site/index.html) - Public product/evidence site

## 🎯 Copilot Custom Agents

14 custom agents with a model cost optimization strategy:

| Agent | Role | Model |
|-------|------|-------|
| `architect` | System architecture + DDD | Sonnet 4.6 → GPT-5.4 |
| `code` | Feature implementation | Sonnet 4.6 → GPT-5.4 |
| `debug` | Root cause analysis | Sonnet 4.6 → GPT-5.4 |
| `audit` | Deep code audit (5 dimensions) | Opus 4.6 → Sonnet 4.6 |
| `orchestrator` | Task decomposition + delegation | Opus 4.6 → GPT-5.4 |
| `deep-thinker` | Complex reasoning + algorithms | Opus 4.6 → GPT-5.4 |
| `researcher` | Read-only codebase exploration | Gemini 3.1 Pro → Sonnet 4.6 |
| `test-runner` 🆓 | Run tests + iterate fixes | GPT-5.5 mini → GPT-5 mini → GPT-4.1 |
| `context-loader` 🆓 | Load Memory Bank + summarize | GPT-4.1 → GPT-5 mini |
| `ask` 🆓 | Project Q&A | GPT-4.1 → Haiku 4.5 |
| `review-panel` | Multi-model review committee | Opus 4.6 (3 AI cross-review) |

> 🆓 = Free model agents for high-volume, repetitive tasks

## 🔒 Pre-commit Hooks

16+ hooks via `.pre-commit-config.yaml`:

- **Code Quality**: ruff lint + format, mypy
- **Security**: bandit, gitleaks
- **Conventions**: conventional-commits, commit-size-guard (≤30 files)
- **AI Maintenance**: skill-freshness-check, agent-freshness-check, memory-bank-reminder

## 🧪 Testing Support

The repository's current testing configuration includes:

- **Static Analysis**: ruff, mypy, bandit
- **Unit + Smoke Tests**: pytest with a 60% coverage floor
- **Integration Tests**: pytest-asyncio plus the public OpenClaw Gateway contract
- **Native Windows Smoke**: opt-in rendered capture-exclusion verification
- **CI/CD**: four OS/Python compatibility executions, one pytest job, and a
  separate GitHub Pages deployment workflow

## 📄 License

[Apache License 2.0](LICENSE)
