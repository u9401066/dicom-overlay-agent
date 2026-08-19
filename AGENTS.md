# DICOM Overlay Agent — AI Maintenance Harness

These are the workspace instructions for any AI agent (Copilot, Codex, Claude
Code) maintaining this repository. The product is a Windows desktop **co-reading
agent**: it watches a DICOM viewer, sends screenshots to OpenClaw for
interpretation, and overlays AI findings on the original image. The physician
always keeps the final diagnostic call.

## Working Style

- Reply in Traditional Chinese unless the user asks otherwise.
- Follow DDD layering: `domain → application → infrastructure / presentation`.
  `domain/` must not import GUI, network, or OpenClaw code.
- Use `uv` for the Python environment; never install globally.
- Sync the Memory Bank (`memory-bank/`) after meaningful changes.
- Keep PHI out of code, logs, tests, and fixtures.

## The Four Cores (maintenance charter)

Every change must keep these four cores aligned. If a change weakens any core,
call it out and propose mitigation before proceeding.

### Core 1 — Image-reading overlay interaction (position + content)

- **Position:** AI returns normalized `0-1` `Finding.bboxes`. `__main__.py`
  highlights AI bboxes first, falling back to static `region_maps` via
  `infrastructure/region_mapper.py`. Do not break the bbox → screen-coordinate
  mapping or the fallback path.
- **Content:** `presentation/overlay_window.py` (`SummaryPanel`, `ChatPanel`,
  `_DraggableWindowMixin`) renders the systematic checklist and follow-up chat.
  Panels stay frameless, top-most, drag-to-move. `presentation/control_bar.py`
  keeps pause / settings / manual re-trigger.
- **Privacy:** `presentation/roi_setup.py` defines the capture ROI that crops
  PHI. Never widen capture beyond the user-defined ROI.

### Core 2 — Complete OpenClaw interpretation harness

- The loop must stay executable and CI-verifiable:
  `infrastructure/image_harness_smoke.py` (drives screenshot → `chat.send` →
  event stream → artifacts) and `infrastructure/image_harness_validator.py`
  (`verify_image_harness_artifacts`: gateway contract, image payload proof,
  optional viewer).
- The pinned public submodule under `third_party/medical-image-agent-harness`
  owns the provider-neutral scientific method, typed contracts, draft validator,
  and canonical `.agents/skills/medical-image-reading` skill.
- The private product may adapt that method to OpenClaw tools, but must not make
  public code depend on the overlay, Gateway, plugin, or screen-capture layers.
- Run `python scripts/sync-medical-image-harness.py --write` after advancing the
  submodule and commit the generated `.agents` thin adapter. CI runs `--check` so Codex
  and Copilot discovery cannot silently drift from the pinned public source.
- `openclaw/workspace/skills/dicom-*-analysis/` remains a private OpenClaw
  runtime adapter; it is not the scientific source of truth. Runners:
  `scripts/run-image-harness-smoke.py`, `scripts/verify-image-harness.py`.

### Core 3 — OpenClaw plugin compatibility

- Talk to OpenClaw **only through the stable public Gateway protocol**
  (`connect` + `chat.send`). Never import OpenClaw plugin SDK internals.
- `infrastructure/openclaw_runtime.py` owns `MIN_SAFE_OPENCLAW_VERSION`
  (`2026.4.22`), `build_harness_manifest`, and `build_openclaw_chat_frame`
  (protocol `3`; image in `params.attachments[]` with `type` / `mimeType` /
  `content`, `image/png`).
- Before bumping OpenClaw (`openclaw/package.json`, currently `2026.7.1-2`),
  confirm the `connect` / `chat.send` schema and attachment format are
  unchanged. Raise the version floor only for a real, verified incompatibility,
  and keep `manifest.json` in sync.

### Core 4 — Minimal packaged executable

- `dicom-overlay-agent.spec` must keep excluding heavy unused libs (`numpy`,
  `scipy`, `matplotlib`, `pandas`, `imagehash`), keep pruning unused Qt modules
  (WebEngine, Qml/Quick, Pdf, Multimedia, `opengl32sw.dll`, qml/translations),
  keep UPX on, and stay windowed (`console=False`). Do not add heavy runtime
  dependencies casually.
- `scripts/stage-openclaw-runtime.ps1` stages a *slim* OpenClaw runtime; keep it
  minimal. `scripts/fetch-node.ps1` provides the opt-in portable `node\node.exe`
  that `gateway_manager._find_node()` prefers for zero-install. `pywin32` stays a
  Windows-only conditional dependency.
- **Measured budget:** launcher `.exe` < 50 MiB (currently ~6.97 MiB); app +
  Python/Qt layer < 100 MiB (currently ~94.66 MiB); full zero-install bundle
  including pinned Node/OpenClaw is ~363.94 MiB. Do NOT prune OpenClaw's internal `dist`
  chunks to hit a smaller number — that couples to OpenClaw internals and breaks
  Core 3. Trim only *around* the vendored runtime, and re-check sizes after any
  dependency change.

## Guardrails

- Do not bypass the ROI crop or send full-screen captures.
- Do not couple to OpenClaw internals; keep the Gateway protocol boundary.
- Do not let `domain/` depend on infrastructure/presentation.
- Do not add dependencies that blow the packaging size budget without flagging it.
- Keep harness smoke + validator green; treat them as the contract for Core 2.
- Never use `openclaw-home/` as a source tree; it contains ignored runtime state.

## Related Files

- `spec.md` — system specification
- `README.md` / `README.zh-TW.md` — four-core overview
- `config.yaml` — ROI, `region_maps`, hash, gateway settings
- `memory-bank/` — project memory
- `docs/public-harness-boundary.md` — public/private ownership and promotion rules
