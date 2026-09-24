# ROI preview preserves the selected source — 2026-09-24

Follow-up to the black selection observed during
[native browser acceptance](native-browser-selection-2026-09-24.md).

## Cause and change

`ROISetupDialog.paintEvent()` drew a frozen screenshot, dimmed it, then used
`CompositionMode_Clear` to erase the selected rectangle. On the opaque Windows
dialog, this produced a black area instead of revealing the source.

The presentation-only fix retains the frozen screenshot and clips the dimming
paint to the region **outside** the selection. It does not recapture while dragging,
modify image bytes, change selection/confirmation math, alter ROI containment,
disable capture exclusion, or widen the model's input. The blue target guide and
green selection outline remain. No dependency or Gateway/schema change.

## Regression tests

All **25 new pixel tests failed before** the change and pass after it. They cover
forward/reverse selections, an existing ROI, screenshot DPR 1/1.25/1.5/2, positive
and negative screen origins, and reset. Assertions check original interior colors,
dimmed opaque exterior, unchanged screenshot bytes and identical confirmed margins.
The DPR/origin matrix is synthetic, not a physical monitor-switch acceptance.

Combined ROI suite: **43 passed**. Full explicit unit/integration/smoke run with
Qt offscreen: **1,716 passed, six skipped in 212.63 s**. The six private/frozen/native
opt-in skips are not credited as passes. Ruff/format checks pass.
The preceding ca34f73 push/PR CI and both secret scans completed successfully.

## Actual Windows App verification

Launched the real source App and owned Viewer with a code-drawn synthetic
1000×720 two-color grid. No medical input and **zero model requests**. The desktop
was 2560×1600 at 150% scaling. Source base was clean `ca34f73` plus this ROI
paint/test patch, recorded as dirty rather than claiming a clean packaged build.
Runtime `roi_setup.py` SHA-256:
`36576a275c30a078428b3081479821af144f34a189c1212f9ddc97788f4fb3b5`.

Actual Settings → Set ROI displayed the existing selection correctly. Native mouse
drag `(300,300)`–`(1000,650)`, R reset, reverse drag and Enter confirmation were
performed. Bounded screen captures were limited to the owned synthetic Viewer
content. Three sample locations were checked against actual window ownership.

| Native state | Left interior RGB | Right interior RGB | Excluded sample RGB |
| --- | --- | --- | --- |
| Original Viewer | 240,180,100 | 90,150,220 | 90,150,220 |
| Existing / new / reverse selection | 240,180,100 | 90,150,220 | 62,103,151 |
| After R reset | 165,124,69 | 62,103,151 | 62,103,151 |
| After confirmation | 240,180,100 | 90,150,220 | 90,150,220 |

Forward/reverse preview PNGs are byte-identical. The selected area is visibly
intact, not black. Saving changes only an isolated temporary test config, not the
existing runtime config. Its derived capture rectangle is `(300,300,699,348)`,
fully inside the dragged bounds after existing conservative rounding. That
rectangle was **computed from saved margins**, not submitted as a new capture.
App logs confirm no CAPTURING transition or analysis request in this session.
App, Viewer and owned Gateway shut down; their PIDs/listener were absent afterward.

## Local evidence

Outside repo: `C:/Users/Ericlab/AppData/Local/Temp/dicom-roi-preview-20260924/`.
The directory preserves the synthetic fixture, launch/input/probe scripts,
`before`, `existing`, `selected`, `reset`, `reverse`, `confirm` PNG/JSON pairs,
isolated config and `receipt.json` with source/probe/hash provenance.

- Synthetic fixture SHA-256:
  `a63d9a11262bbeee913f03f6dcf8231bbe143470486732aded811730db8daf58`.
- Selected/reverse preview SHA-256:
  `cb81ba0a5c7f583dac9230cfbcb20cd89ba5f486481f04266d8d286e17c08d3a`.

This closes the observed black-preview defect for the actual tested display.
It is source-only, absent from the preserved 6e6734e EXE. Physical mixed-DPI changes,
other DICOM viewers, mid-analysis image replacement, native ADD/dismissal, canonical
host evidence assembly and >=100 current-model clinical cases remain separate gates.
