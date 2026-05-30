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
  [`region_mapper.py`](src/dicom_overlay/infrastructure/region_mapper.py).
- **Content** — a draggable [`SummaryPanel`](src/dicom_overlay/presentation/overlay_window.py)
  shows a systematic checklist (16 items for EKG); abnormal items surface first,
  normal ones collapse. A [`ChatPanel`](src/dicom_overlay/presentation/overlay_window.py)
  lets the physician ask follow-up questions about the same image.
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

### Core 3 — OpenClaw plugin compatibility

The app talks to OpenClaw **only through the stable public Gateway protocol**
(`connect` + `chat.send`), never importing plugin SDK internals, so it stays
portable across OpenClaw releases.

- [`openclaw_runtime.py`](src/dicom_overlay/infrastructure/openclaw_runtime.py)
  pins `MIN_SAFE_OPENCLAW_VERSION` (`2026.4.22`) and builds the harness
  manifest / chat frame against the documented schema (protocol `3`, image in
  `params.attachments[]` with `type` / `mimeType` / `content`).
- [`openclaw/package.json`](openclaw/package.json) tracks the runtime version
  (`openclaw ^2026.5.27`) and the minimum-safe floor.
- [`manifest.json`](openclaw/workspace/plugins/dicom-overlay-agent-harness/manifest.json)
  declares the plugin compatibility window.
- **Rule:** before bumping OpenClaw, confirm the `connect` / `chat.send` schema
  and the image attachment format are unchanged; raise the floor only when a
  real incompatibility is found.

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
| `test-runner` 🆓 | Run tests + iterate fixes | GPT-5 mini → GPT-4.1 |
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
