# Portable plugin binding and Analyze readiness — 2026-09-25

This fixes the two integration gaps observed during the
[explicit lead-inventory replay](explicit-lead-inventory-2026-09-25.md).
It does not replace the failed clinical cohort, validate diagnoses or constitute
a new frozen-executable release.

## Changes

`GatewayManager` previously appended the current harness path to public
`plugins.load.paths`, retaining the previous installation's path. If the old copy
still existed, OpenClaw could select its plugin. Startup now replaces only absolute
entries matching the App-owned
`openclaw-home/.openclaw/workspace/plugins/dicom-overlay-agent-harness` layout
(directory or `index.js`) with the current path. It normalizes separators and dot
segments, is idempotent, and preserves unrelated/custom plugin paths and settings.
It neither imports OpenClaw internals nor deletes files from the old installation.
Relative/custom paths are deliberately not treated as ownership proof.

Analyze now requires startup to finish and an actionable agent state. INIT,
waiting-for-Viewer, ROI setup, capture, analysis and reconnect states disable it
with a reason. Settings and Quit remain available. A completed startup that is
offline still permits manual recovery from monitoring/error/display/paused states;
this is not a permanent offline lockout. The App shortcut checks the same reason.
An application-layer guard also ignores a second manual trigger while capture or
analysis is already active, covering queued-input/UI-render timing gaps.

These changes preserve the ROI boundary, finding/fallback coordinate mapping,
public Gateway protocol, 16-key result schema and dependency/package budgets.
No image reinterpretation, paid retry or auth-key route was added by either fix.

## Actual Windows App run

Candidate `a2e44f7` plus the recorded changes ran from a newly copied runtime;
the prior replay App/Gateway were closed through Quit first. Viewer PID 7832 and
its exact authorized `(30,30,1500,1080)` ROI were retained on the 2560×1600,
150%-scale desktop. No original batch/export/log was reused for writing.

| Actual observation/action | Verified behavior |
| --- | --- |
| Initial owned control bar | Analyze disabled; AI starting; Settings/Quit enabled |
| Physical Ctrl+Shift+A during startup | Visible wait reason, zero analysis requests |
| Same App reaches ready/MONITORING | Analyze enabled |
| Real QFileDialog then Analyze | One normal image-analysis workflow starts |
| Physical Ctrl+Shift+A during analysis | Busy reason; button disabled; no additional coarse request |
| Result and actual Export | Analyze re-enabled; four total medium stages; source ROI pixels unchanged |

Readiness snapshots are native Windows UI Automation observations, not mocked
widgets. Keyboard input was sent only after physical owner/focus verification.
The final exported control-bar image was visually inspected. App-source hashes
for all 79 tracked files stayed unchanged throughout the run. A subsequent single
formatter change to `gateway_manager.py` is explicitly recorded: the original file
was preserved, its receipt hash checked, and both versions have identical ASTs.
The source worktree was dirty during the run, not falsely described as a clean EXE.

The new public config contains only the current managed plugin path for this
fixture. The actual Gateway's two harness-load observations both point to the new
runtime; there is no old-path duplicate-plugin warning. Public per-stage usage
joins to the actual runtime identities as **four Astra-medium stages**.
This verifies this App-owned moved-runtime case, not arbitrary custom overrides.

The same exposed development case at baseline index 24 produced 12 lead entries,
zero legacy validation warnings, and still incomplete/review-required output.
Analysis took **97.545 s**, complete GUI workflow **111.916 s**. Source-to-visible
bilinear MAE was 0.490169/255 and visible-to-export MAE was **0**. No accuracy,
localization or speed improvement is inferred from this replay. Cold AI startup
still took about **136 s**; the UI is responsive during it, but startup latency
itself remains a performance issue.

## Evidence and verification

Private root: `C:/Users/Ericlab/AppData/Local/Temp/dicom-relocation-ready-20260925/`.
It contains startup/ready/busy/finished UI receipts, native keyboard scripts,
attempt/source fingerprints, ROI screenshot, runtime logs, result/usage exports
and an independent read-only `audit.py` / create-only `audit.json`.
Final export: `runtime/data/exports/desktop-20260924-190928-490683`.

- Audit SHA-256: `6fd8b4bfc40d402215651a51c7d613d695df50ac1f4306c2b2b32a1924473c89`.
- Source SHA-256: `19706efc46260ddb280bf5ae9ba6a7cd3a15ffe564caef5b08af7e30d50c11cb`.
- Result SHA-256: `86dd08b637f8eabd842aff1eb81975d60a8bfd2c894d4aa4bb760ad05b96ad07`.
- Usage SHA-256: `50b452890473e4987362aa1b55f5a37522cb2ee130986f82dae7a6b708eb093d`.

The auditor rehashes exported artifacts, verifies the native state transitions,
matches current config to actual plugin-load lines, checks original ROI pixels,
and confirms one coarse request/four bound stages. It does not score medicine.

29 new regressions cover old Windows/UNC/POSIX paths, case/separator/dot-segment
handling, custom-path preservation, idempotence, startup ordering, all blocked
states, offline recovery and duplicate manual triggers. The first focused run
caught Python 3.13's `ntpath.isabs('/...')` behavior; explicit POSIX-root recognition
fixed that cross-platform case. Focused suite: **165 passed**, including after the
formatter-only change. Full unit/integration/smoke suite: **2,192 passed, seven
explicit opt-in/private-environment skips in 358.30 s**. Ruff/format and focused
Gateway/control-bar mypy pass. Frozen binary, cross-monitor/DPI, broader device
coverage and clinical improvement remain open.
