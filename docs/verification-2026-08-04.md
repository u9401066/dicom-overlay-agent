# Verification Record - 2026-08-04

This file is the release-facing evidence ledger for the current desktop MVP.
It separates completed execution from blocked experiments so a local JSON file
or a schema-valid response is never mistaken for clinical accuracy evidence.

## Status Matrix

| Surface | Status | Evidence |
| --- | --- | --- |
| Source self-check | passed | Node, OpenClaw, 51 bundled skills, native plugin, rules, writable base |
| Unit + smoke suite | 647 passed, 1 release-only skip | `scripts/run-tests-safe.cmd -q` |
| OpenClaw overlay integration | 54 passed | `tests/integration/test_openclaw_overlay.py` |
| Fresh bundle smoke | 2 passed | `RUN_BUNDLE_SMOKE=1`, real frozen EXE self-check |
| Real Win32/Qt coordinate probe | passed | Win32 window `1222x836`; mss capture `1222x836`; physical display `2560x1600`; Qt frame `1707x1067` |
| ECGFounder paired waveform arm | 1,000/1,000 completed | `data/eval-runs/ecgfounder-meeti-1000-20260804` |
| New three-arm MLLM image comparison | blocked | OpenAI `credit_balance_exhausted` / `insufficient_quota` |
| Clinical accuracy target | not established | No complete paired MLLM comparison is available yet |

## What Runs Per Image

The auditable MultiPass flow is:

1. Capture the configured PHI-safe ROI in physical screen pixels.
2. Record source dimensions and run deterministic local image-assist candidate
   extraction when the image processor supports it.
3. Run the coarse OpenClaw image read with lead/layout inventory and image
   quality gates.
4. Select a bounded number of evidence-backed targets. The cropper creates only
   strict subregions of the original ROI and may upscale them for legibility.
5. Run refine reads for those crops, map every accepted box back to
   `normalized_original_roi`, and reconcile a final report without silently
   downgrading urgent evidence.
6. Apply input, schema, clinical-consistency, and bbox-calibration guardrails.
7. Project physical bbox edges through the target display's Qt logical frame;
   draw only boxes whose edge round-trip audit passes.
8. Keep a reviewer-safe `analysis_trace` with stages, registered tools, crop
   coordinates, decisions, and provenance. Hidden chain-of-thought is neither
   requested nor stored.

OpenClaw's native plugin always exposes `dicom_bbox_validate`. The conditional
`ecg_founder_analyze_waveform` tool is usable only with an authenticated
loopback sidecar and an app-supplied opaque waveform artifact id. It cannot read
arbitrary paths, cannot treat a PNG as a waveform, and cannot create image
boxes. See [the ECGFounder tool contract](ecgfounder-tool.md).

## ECGFounder Waveform Run

- Dataset build: 1,000 MEETI images paired to their raw 12-lead waveforms.
- Checkpoint: official `12_lead_ECGFounder.pth`, kept outside git and the app.
- Protocol fingerprint:
  `2b79fb8caffed0eabe1467fa3aba4c5a8287e753d7dcdcae1fa308fc7ca2d933`.
- Completed: 1,000 successful results, 0 failed results.
- Observed wall time: 691.182 seconds.
- Recorded inference time: 690,996.751 ms total, 756.491 ms median,
  794.734 ms p95.
- Interpretation boundary: all class scores are explicitly uncalibrated
  supporting evidence. No fixed diagnostic threshold or image bbox is inferred.

The run artifacts and checkpoint are intentionally ignored because they are
large external data. Reproduction commands and hashes are in
[ecgfounder-tool.md](ecgfounder-tool.md).

## MLLM Comparison Blocker

The planned paired comparison remains:

1. Single-pass image baseline.
2. MultiPass image analysis.
3. MultiPass plus ECGFounder waveform evidence.

The requested `openai/gpt-5.4-mini` rerun reached the provider boundary but the
account returned `credit_balance_exhausted` / `insufficient_quota`. Existing
JSON outputs are retained as attempt records, but there is no completed paired
scorecard and no accuracy improvement claim. Once quota is available, all
three arms must use the same case order, labels, scorer version, and image
inputs; arm 3 additionally receives only the matching waveform artifact id.

## Coordinate Evidence

The previous primary-screen-only path was replaced with a monitor-bound frame:

- Win32 `MonitorFromRect` resolves the display containing the viewer.
- The exact successful `last_capture_rect` is saved by `OverlayAgent`.
- Qt screen selection accounts for primary status, device name, physical size,
  monitor index, and desktop topology.
- Physical edges are mapped to overlay-local logical pixels using independent
  X/Y ratios and display origins, including negative-origin secondary screens.
- AI boxes and static region fallbacks share the same conversion.
- `Severity.INFO` boxes are now drawn for uncertain reviewer questions; only
  normal findings are omitted from the canvas.

Focused coordinate tests cover negative origins, mixed scaling, physical-edge
round-trip, exact capture preservation, display lookup, and uncertainty boxes.
The real local GUI probe also proved that mss returned exactly the Win32 window
dimensions on the current 150% display.

## Portable Bundle

Fresh artifact:

- Path: `dist/DICOMOverlayAgent/DICOMOverlayAgent.exe`
- SHA-256:
  `C44DA431AA5D1BFC72D943B3835BFC6A403BD426B483F9661B5FA17266383F66`
- Launcher: 6.90 MiB
- App/Python/Qt layer: 94.58 MiB
- OpenClaw: 181.03 MiB, version `2026.7.1-2`
- Node.js: 88.25 MiB, version `v24.18.0`
- Total: 363.86 MiB, 15,226 files
- Manifest: `dist/DICOMOverlayAgent/bundle-manifest.json`, status `ok`
- Frozen module proof: PyInstaller `PYZ-00.toc` contains
  `dicom_overlay.presentation.screen_selection` and
  `dicom_overlay.infrastructure.overlay_geometry`.

Bundled surfaces include the executable, config, portable Node, slim pinned
OpenClaw runtime, native harness plugin, EKG/CXR/CT skills, and clinical rules.
The verifier found no banned components. Torch, ECGFounder environments,
checkpoints, MEETI images/waveforms, experiment SQLite files, API secrets, and
sidecar processes are not bundled.

The pinned OpenClaw dependency audit currently reports 7 moderate and 4 high
transitive vulnerabilities, 0 critical. A force upgrade was not applied because
it can break the runtime compatibility contract; this remains release debt.

## Website QA

The static GitHub Pages source is under `site/` and deploys through
`.github/workflows/pages.yml`. It uses only the repository's synthetic ECG
asset. Playwright verified 1440x900 and 390x844 viewports, image loading,
desktop/mobile overflow, first-viewport continuation, evidence navigation,
mobile menu state, four complete trace stages, and zero console warnings/errors.

## Platform Boundary

This artifact was built and exercised on Windows 11. The current Python 3.13,
PyQt6, Node 24, and current OpenClaw stack does not provide a credible Windows 7
compatibility claim. Windows 10 also requires a separate clean-machine test.
Do not label the current bundle Windows 7 compatible; supporting it would need
a separately pinned legacy runtime architecture and its own security policy.
