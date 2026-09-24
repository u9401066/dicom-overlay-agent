# Interaction bundle 6e6734e — September 24, 2026

This is a local development checkpoint, not a public binary release or clinical
acceptance. The original bd8f303 bundle remains unchanged.

## Build and executable checks

- Clean build source: `6e6734eb33b3d6331ccf0f82476a8c5b97bfe44b`.
  Output: `dist-interaction-6e6734e-upx/DICOMOverlayAgent`.
  This includes manual-region promotion history and conversation-to-outcome IDs,
  unlike the older bd8f303 executable.
- Frozen Python 3.13.12 build environment, Node 24.18.0, OpenClaw 2026.9.3,
  UPX 5.2.1. Locked dependency sync passes; no dependency/pin changes.
- Seven clinical rules pass generated-view and YAML/SQLite parity checks:
  `0d35360aa941f0fc4a532c6fc204fee32fae7fdab866376c4ac82925a1e612c1`.
  This is not a claim that seven rules cover a complete clinical workflow.
- Isolated build completed; all 90 native dependency sources approved.
  `win32-console-mode.node` and `python3.dll` report NotCompressibleException
  and remain uncompressed. CFG-bearing binaries are not forced through UPX.
  Optional OpenConsole `ext-ms-win-uiacore-l1-1-{0,1}.dll` warnings remain;
  terminal-helper execution is not covered by the image/Gateway checks below.
- EXE: **4,928,966 bytes**, SHA-256
  `671474add1136f21da34a39cbd56568c39d2fce1fc70f44750362eb6095e1d75`.
- Code-object comparison against exact git source passes for eight frozen modules:
  main, regional conversation, overlay agent, window picker, overlay window,
  settings dialog, screen monitor and desktop review exporter. Only code-object
  filenames are normalized; bytecode/constants are otherwise compared directly.
- **20 frozen packaging tests pass in 120.77 seconds**, with all three opt-in
  packaging gates enabled. They execute this EXE's self-check, codec/font/review
  runtime smoke and isolated loopback Gateway image/error contract. No real
  subscription credential or model request is used. They are not native mouse,
  browser capture, diagnostic accuracy or 100-case acceptance.
- Full bundle manifest/runtime inspection completed with status **ok**, no
  failures. Native plugin tools `dicom_bbox_validate` and
  `ecg_founder_analyze_waveform` load through the public runtime. Fabricated
  OAuth-only migration plan/apply passes; Codex runtime remains disabled,
  real-auth use is false and model requests are zero.
- Manifest: `dist-interaction-6e6734e-upx/DICOMOverlayAgent/bundle-manifest.json`.
  Its included source roots are clean at 6e6734e (`git_dirty=false`); this audit
  document was written subsequently and is not a compiled-source input.
  Source-tree SHA-256:
  `1dd80bf0e54c506f9b3db6cba0c9a9c497e90dea50d4ba552e7c3350a0f5709a`.
  Payload-tree SHA-256:
  `3bedb58a1b2f88bfb5ccee542d8ae6456d8691bfa73c92f504b8949e6701b397`.
- **18,771 files**: launcher 4,928,966 bytes (**4.70 MiB**), App/Python/Qt layer
  57,087,595 bytes (**54.44 MiB**), full folder 353,382,881 bytes (**337.01 MiB**).
  That is 2,135 bytes above bd8f303; no size-budget regression. The verifier
  observes 45 UPX-bearing App payloads. No standalone compression experiment
  or ZIP publication was performed.

Both source CI runs 35999009012 / 35999016462 and secret scans
35999008974 / 35999016440 succeeded on exact source 6e6734e.

## Newly reproduced geometry gap — not fixed in this EXE

A read-only synthetic diagnostic executed the current `_tick_displaying()` with
the existing `test_agent.py` mocks. It established a displayed snapshot at viewer
origin `(0, 0)`, then moved the mock viewer to `(300, 100)` without changing its
1920x1080 size or hash. The resulting observable state was:

```json
{"window_left":300,"snapshot_left":0,"state":"DISPLAYING","state_events":[],"model_calls":0}
```

The active target geometry updates, but the displayed snapshot keeps its original
screen rectangle and no presentation refresh is emitted. The main tick callback
only drives the agent; it does not independently reproject existing highlights.
This exposes a stale-projection path even when image content is unchanged.
It is a synthetic code-path reproduction, **not a newly completed native GUI
test**. Original acquisition coordinates must remain immutable provenance; a fix
must distinguish current display projection from original capture geometry,
handle resize/monitor/DPI transitions, and retain the ROI privacy boundary.

Viewer movement, native manual ADD/Apply/Inspect continuation and dismissal,
browser capture/QA, mixed-DPI monitors and >=100 current-model real-GUI cases
remain acceptance gates. No desktop focus was taken in this checkpoint; the
desktop-use preference question is still unanswered.

Subsequent [source projection correction](viewer-projection-followup-2026-09-24.md)
addresses this path, but is not contained in this preserved 6e6734e executable.
