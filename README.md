# DICOM Overlay Agent

> 🩺 An autonomous co-reading agent that watches a DICOM viewer, sends screenshots to OpenClaw for interpretation, and overlays AI findings on top of the original image — the physician keeps the final call.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

🌐 [繁體中文](README.zh-TW.md)

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
| 4 | **Minimal packaged executable** | A tiny `.exe` launcher (<50 MB, currently 6.75 MB) plus a lean, portable, zero-install bundle |

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
- **Content** — a draggable [`SummaryPanel`](src/dicom_overlay/presentation/overlay_window.py)
  shows a systematic checklist (16 keys for EKG, a 10-axis read for CXR);
  abnormal items surface first, normal ones collapse. A
  [`ChatPanel`](src/dicom_overlay/presentation/overlay_window.py)
  lets the physician ask follow-up questions about the same image.
- **Multi-pass zoom** — [`multi_pass.py`](src/dicom_overlay/application/multi_pass.py)
  re-reads abnormal regions at full ROI resolution to refine bboxes. Because the
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
- Production-scale ECG evaluation uses the public MEETI source dataset
  (Zenodo record `18523205`, `MEETI.rar`, about 10k ECG images). The local gate
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
  image size, aspect ratio, ink density, bright-pixel ratio, and low-signal
  flag. This cheap local preflight is the first model-assist layer, so the
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
  normalized `local_candidate_regions` per case for audit. When that trace
  exists, `scripts/verify-eval-artifacts.py` validates those fields via
  `multipass_trace_artifacts`; production multi-pass runs should add
  `--require-multipass-trace` so missing crop re-analysis trace artifacts fail
  the gate.
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
  The Python runner supports `--provider-profile openrouter` / `openai-vision`,
  generates an experiment-local OpenClaw config before model-catalog checks,
  takes `data/tmp/openclaw-gateway.lock` before spawning the Gateway, retries
  the eval if the Gateway is still starting, exports review artifacts, and marks
  the experiment failed when `scorecard.json.error_count > 0` even if the
  underlying eval command exits 0. It also runs
  `scripts/verify-eval-artifacts.py` after review export; bounded smoke runs use
  `--limit` as the verification minimum, full runs default to 1000 cases, and
  `--multi-pass` automatically adds `--require-multipass-trace`.
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
  manifest / chat frame against the documented schema (protocol `3`, image in
  `params.attachments[]` with `type` / `mimeType` / `content`).
- [`openclaw/package.json`](openclaw/package.json) tracks the runtime version
  (locally validated against `openclaw ^2026.6.11`) and the minimum-safe floor.
- [`manifest.json`](openclaw/workspace/plugins/dicom-overlay-agent-harness/manifest.json)
  declares the plugin compatibility window.
- The OpenClaw-side specialization is intentionally plugin-shaped:
  `dicom-overlay-agent-harness` advertises medical-image interpretation,
  bbox crop re-analysis, coordinate drift calibration, and overlay annotation
  capabilities. The desktop app still treats it as a Gateway-only integration,
  so compatibility is tested through `connect` / `chat.send` artifacts instead
  of private OpenClaw plugin SDK imports.
- **Rule:** before bumping OpenClaw, confirm the `connect` / `chat.send` schema
  and the image attachment format are unchanged; raise the floor only when a
  real incompatibility is found.
- The desktop Settings dialog exposes AI Provider profiles, including
  OpenRouter (`OPENROUTER_API_KEY`, `https://openrouter.ai/api/v1`) with
  MiniMax M3 as the default OpenRouter model
  (`openrouter/minimax/minimax-m3`). Saving a profile writes only the
  app-managed OpenClaw provider/model sections and keeps secrets in environment
  variables or `.env`, not in git.
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

### Core 4 — Minimal packaged executable

The goal is a tiny launcher and a lean, portable bundle that runs from a USB
stick. The bundle is built with [`scripts/build-exe.bat`](scripts/build-exe.bat).

- [`dicom-overlay-agent.spec`](dicom-overlay-agent.spec) excludes heavy,
  unused libraries (`numpy`, `scipy`, `matplotlib`, `pandas`, `imagehash`),
  prunes Qt modules the overlay never loads (WebEngine, Qml/Quick, Pdf,
  Multimedia, the ~20 MB `opengl32sw.dll` software GL fallback, qml/translations
  data), enables UPX, and builds a windowed (`console=False`) app.
- [`scripts/stage-openclaw-runtime.ps1`](scripts/stage-openclaw-runtime.ps1)
  stages a *slim* OpenClaw runtime, dropping non-Windows native payloads and the
  disabled UI / browser / voice plugins so only the Gateway surface ships.
- [`scripts/fetch-node.ps1`](scripts/fetch-node.ps1) downloads a portable
  `node\node.exe`; when present it is bundled and
  [`gateway_manager.py`](src/dicom_overlay/infrastructure/gateway_manager.py)
  prefers it over system Node.js, giving a true zero-install bundle.
- `pywin32` is a Windows-only conditional dependency to keep Linux/CI installs
  clean.
- **Portable plug-and-play** — when frozen, runtime paths anchor to the
  executable's folder (not the launch `cwd`, which may be `System32`) via
  [`app_paths.py`](src/dicom_overlay/infrastructure/app_paths.py), so the bundle
  runs unchanged from a USB stick on a fresh machine. Run
  `DICOMOverlayAgent.exe --selfcheck` to verify Node.js, the OpenClaw runtime, a
  writable base, and `config.yaml` all resolve — without launching the GUI or
  contacting an LLM (exit 0 = ready).

**Size budget (measured):**

| Artifact | Budget | Current |
| --- | --- | --- |
| `DICOMOverlayAgent.exe` launcher | < 50 MB | **6.75 MB** ✅ |
| App + Python/Qt layer (no vendored OpenClaw) | < 100 MB | **~89 MB** ✅ |
| Full bundle incl. vendored OpenClaw runtime | — | **~205 MB** |
| + opt-in portable Node.js | — | + ~30 MB |

The vendored OpenClaw runtime (~114 MB) is kept intact on purpose: pruning its
internal `dist` chunks would couple the app to OpenClaw internals and break
**Core 3** across releases. We trim everything *around* it instead.

## 📋 Documentation

- [System Spec](spec.md) - Detailed system specification
- [Architecture](ARCHITECTURE.md) - System architecture
- [Constitution](CONSTITUTION.md) - Highest principles
- [Changelog](CHANGELOG.md) - Version history
- [Roadmap](ROADMAP.md) - Feature planning
- [Real Test Runbook](REAL_TEST_RUNBOOK.md) - Live stack testing
- [AGENTS.md](AGENTS.md) - AI maintenance guardrails for the four cores

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

The template includes comprehensive testing configuration:

- **Static Analysis**: ruff, mypy, bandit
- **Unit Tests**: pytest with 80% coverage requirement
- **Integration Tests**: pytest-asyncio
- **E2E Tests**: Playwright
- **CI/CD**: GitHub Actions with 6 jobs

## 📄 License

[Apache License 2.0](LICENSE)
