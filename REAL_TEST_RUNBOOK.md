# Real Test Runbook

## Goal

Run the project on Windows with a workspace-local OpenClaw Gateway and verify the real desktop stack:

1. OpenClaw installs inside the repo only.
2. OpenClaw Gateway starts from repo-local config/state.
3. Workspace skills are visible to OpenClaw.
4. The Python overlay agent launches and connects to the real gateway.
5. A real DICOM viewer can trigger ROI setup and analysis.

## Prerequisites

1. Windows 10/11.
2. Node.js 22+ available in `PATH`.
3. Python virtual environment already prepared:
   - `uv sync --all-extras`
4. At least one model credential available in the shell before launch:
   - `ANTHROPIC_API_KEY`
   - or `OPENAI_API_KEY`

## Repo-local portable layout

- OpenClaw package: `openclaw/node_modules/openclaw`
- OpenClaw config: `openclaw/openclaw.json`
- OpenClaw state/home: `openclaw-home/`
- Synced runtime workspace: `openclaw-home/.openclaw/workspace/`
- Source skills tracked in git: `openclaw/workspace/skills/`

## Fast path

Run:

```bat
scripts\test-real-stack.bat
```

This does the following:

1. Installs OpenClaw locally into `openclaw/node_modules`.
2. Syncs repo skills into `openclaw-home/.openclaw/workspace/skills`.
3. Validates OpenClaw config.
4. Starts the real OpenClaw Gateway.
5. Runs gateway health check.
6. Launches the DICOM Overlay Agent.

## Manual path

### 1. Install local OpenClaw

```bat
scripts\install-openclaw-local.bat
```

### 2. Sync skills into the runtime workspace

```bat
scripts\sync-openclaw-workspace.bat
```

### 3. Set repo-local OpenClaw environment

```bat
set OPENCLAW_STATE_DIR=%CD%\openclaw-home
set OPENCLAW_CONFIG_PATH=%CD%\openclaw\openclaw.json
set HOME=%CD%\openclaw-home
set USERPROFILE=%CD%\openclaw-home
```

### 4. Validate config

```bat
node openclaw\node_modules\openclaw\openclaw.mjs config validate
```

### 5. Start the gateway

```bat
node openclaw\node_modules\openclaw\openclaw.mjs gateway run --verbose
```

Expected success signal:

- `listening on ws://127.0.0.1:18789`

### 6. In a second terminal, verify health

```bat
node openclaw\node_modules\openclaw\openclaw.mjs gateway health
```

Expected result:

- `Gateway Health OK`

### 7. Start the overlay agent

```bat
.venv\Scripts\python.exe -m dicom_overlay --config config.yaml
```

## Real viewer test

1. Open your actual DICOM viewer.
2. Make sure its title includes one of the keywords from `config.yaml` under `monitor.window_title_keywords`.
3. If `phi_roi` is missing or if you click the control bar settings button, complete ROI setup.
4. Change image content or click retrigger on the control bar.
5. Watch for:
   - Gateway logs showing requests
   - Overlay panel appearing
   - Region highlights drawn on the viewer

## What is already truly tested

1. Repo-local OpenClaw install works.
2. OpenClaw CLI runs from `node openclaw/.../openclaw.mjs`.
3. Portable config validates.
4. Real Gateway starts and passes health check.
5. Python stack unit/smoke tests pass.

## What still requires your manual real-world check

1. Your actual DICOM viewer title is detectable.
2. ROI selection UX feels correct on your screen layout.
3. OpenClaw model credentials are valid.
4. Real model output matches the JSON structure expected by this project.
5. Overlay click-through behavior is acceptable on your workstation.
