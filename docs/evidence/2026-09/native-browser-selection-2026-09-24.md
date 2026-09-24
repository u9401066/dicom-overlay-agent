# Native browser capture, picker accessibility fix and regional QA

## Finding and correction

The actual Windows UIA `SelectionItem.Select()` operation selected the Edge row
without moving Qt's keyboard-current row. `WindowPickerDialog.selected_window()`
used `currentItem()`, so it could bind an unrelated focused row instead. The
first browser attempt's ROI was rejected as outside that target; **no capture or
model analysis was submitted in that attempt**. A helper's successful Select/Use
receipt alone did not prove the intended window was bound. The early DPI
hypothesis was not supported by the subsequent reproduction.

Three new real-Qt regression tests failed before the change: selected/current
row mismatch, current-row focus without selection, and selection cleared while
current item remained. The picker now reads exactly one `selectedItems()` entry
and updates Use from `itemSelectionChanged`. Zero or ambiguous selection returns
no target. No window title is logged by this change.

After restarting the real App, **the same UIA selection path** correctly bound
the owned Edge window, proven by its live 1640×1450 geometry at `(40,30)`, the
accepted native ROI drag, and subsequent capture pixels. The fix is not merely
an automation workaround. Mark and ROI drag use actual Win32 mouse input.

## Environment and target flow

- Source base `9e631538144b1467b6207a9c19b1a01b82492f33`, with this picker/test
  patch; the launch was intentionally dirty and recorded as such. Runtime picker
  SHA-256: `b17a998f3b3e737134db57d393dcbdad500daa0a9e6975770ae6448bcfcffae4`.
- Actual Qt App, App-managed isolated OpenClaw on port 18795, existing subscription
  profile. No direct driver inference or source-file image submission.
- Isolated visible Microsoft Edge profile, Playwright 1.62.1. **Browser plugin
  not available**, so the frontend-testing skill required the Playwright fallback.
  No new browser dependency. Only the owned test browser/App were operated.
- URL: local `data/tmp/browser-capture-fixture.html`, title
  `Overlay browser capture fixture`. The file renders the already exposed,
  de-identified MEETI case 44709848; it is not a new blind case.
- Physical display 2560×1600; Qt scale 150%. Browser CSS viewport 829×613 with
  reported devicePixelRatio approximately 1.935. This is a desktop viewport,
  not mobile acceptance; fixed-width ECG content is deliberately clipped.
- Flow: visible browser image → App Settings / Choose image window → select Edge
  → physical ROI drag / Enter → App Analyze / Export → Mark / regional question
  → browser scroll → old review invalidation / stale Export rejection.

## Rendered QA

| Check | Result and evidence |
| --- | --- |
| Page identity | PASS: intended local URL/title and decoded 1000×720 image |
| Nonblank | PASS: fixture header and visible waveform image |
| Framework overlay | PASS: static fixture, no framework error overlay |
| Console health | PASS: no page errors or console warnings/errors before/after scroll |
| Native screenshot | PASS: browser chrome/popup were inspected separately; no chrome enters ROI |
| ROI/capture | PASS: requested drag `(100,440)`–`(1400,1200)`; actual inward-rounded `(101,440,1297,759)` |
| Pixel match | PASS: RGB mean absolute difference **0** against actual pre-analysis screen subrectangle |
| Manual region, zero AI boxes | PASS: no AI findings; real drag `(500,700)`–`(800,900)` opens question and receives answer |
| Scroll invalidation | PASS: page scroll y≈201.5504; Overlay/Summary/Chat disappear and stale Export creates no directory |

The initial analysis took **89.355 s**; Analyze/Export observation **91.714 s**.
The source App rendered **INDETERMINATE**, not NORMAL, despite zero findings and
the raw model's `severity=normal`. It retained missing-label/coverage, interference
and clipping limitations. This verifies UI/completeness handling, **not** the
medical correctness of the model's observations or clinical performance.

The new manual-region answer was observed in actual Qt controls. Conversation
export has one independent manual thread, unchanged source hash, and host turn
`ada24a7930b647c7b755c21c2515f4c4` joins to one `interactive_review`
`no_change` / user_confirmed=false event. No finding was added or revised.

All **six original/regional model stages** bind public usage to runtime
`gpt-6-astra`, thinking `medium`. Existing subscription route, no API-key/model
substitution. These snapshots are not a complete monetary billing ledger.
After scrolling, the App transitions DISPLAYING → MONITORING with manual analysis
pending; it does not launch another App analysis. App, owned Gateway and isolated
browser are closed after evidence collection.

## Evidence and failures retained

Browser scripts, screenshots, commands and JSON receipts are outside the repo:
`C:/Users/Ericlab/AppData/Local/Temp/dicom-browser-native-20260924/`.
Important artifacts: `native-browser-before.png`, `roi-rejected.png`,
`browser-pre-analysis.png`, `analysis-start-page.json`, `scrolled.json`,
`app-case-receipt.json`, `regional-answer.json`, `final-receipt.json`,
`browser-region-chat.png`, `browser-summary.png`.
Screenshots were inspected; no generic full-desktop capture was submitted.

App exports in the direct worktree's ignored isolated runtime:
`data/tmp/live-interaction-74d6ee9/DICOMOverlayAgent/data/exports/`:
initial `desktop-20260924-134436-548084`, final `desktop-20260924-134616-337596`.

| Final artifact | SHA-256 |
| --- | --- |
| Source PNG | `ebd627a9012d94fd386319abfe1a3689bcd340527ba2db91eb5daa85e3eaa603` |
| Result JSON | `d8057289ff571c9ddab7fa53ed3abebbfcb27d91d3a79e3a7b13de578fbb3d07` |
| Conversations | `2025eabb7ac26e718d7fc07a080230377253afe278fe5e13b8c185302f2980f4` |
| Usage receipt | `bc44eb7fb03a7a8191683051fa563622d2f56f938d3e2caa7abf878ae3fe0b2d` |

Other driver issues retained: non-TTY stdin closed, followed by Windows refusing
TTY process creation. The first owned browser was explicitly closed and its
process observed terminal before relaunching with a file-command loop; no timeout
was treated as terminal. Browser Ctrl+0 did not change its observed DPR. A native
translation prompt was dismissed, not submitted to a translation service.
The browser's automation-flag warning is chrome, not an application console error.

## Regression and remaining work

- Picker tests: **19 passed**, including the three previously failing cases.
- Default unit/smoke suite: **1,636 passed, six skipped**, 208.12 s.
- Explicit integration suite: **55 passed**, 0.32 s. Combined **1,691 passes**;
  default pytest configuration does not include `tests/integration`.
- Ruff/format and diff checks pass. All previous 9e63153 CI/secrets jobs pass.
- No dependency, Gateway contract, model pin, scientific schema, public harness
  submodule, domain layering or packaging change. ROI is not widened.

One browser and one exposed image are not broad browser/clinical acceptance.
Still open: third-party DICOM viewers, physical mixed-DPI transitions,
mid-analysis image replacement, native ADD promotion/dismissal, canonical evidence
assembly and >=100 current-model blind multi/urgent cases. Current patch is absent
from the preserved EXE. A separate native ROI-preview screenshot shows the
selected area turning black while dragging; inspect the selector paint path in
follow-up rather than crediting that preview as fully usable.
Follow-up now [fixes and natively verifies the selected preview pixels](roi-preview-pixels-2026-09-24.md)
without changing ROI bounds or sending a model request.
