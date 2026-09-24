# Native regional QA and Viewer translation — 2026-09-24

## Scope and provenance

Actual source App at clean `55ec9c92b1d62d3ca567345bfd223fb0beb39420`,
real Qt Viewer, Win32 mouse input, QFileDialog opening, App Analyze/Export,
and App-managed OpenClaw on isolated loopback port 18795. This is **not** an
offscreen test or the preserved 6e6734e EXE. No direct driver inference request.
Runtime assets came from the existing verified isolated runtime copy; source
assets were synchronized by the App. Existing user windows were not manipulated.

One already exposed development case, `meeti_44709848` (old index 119), with
the previously calibrated partial ROI `(150,81,1370,708)`. This is not a new
blind case or clinical accuracy pass. The medical-image-reading protocol keeps
missing labels/calibration explicit; no inferred standard lead layout is credited.
Desktop scale remained 150%, physical display 2560×1600. No OS DPI change.

## Actual interactions

1. Opened the case through the Viewer's real file dialog and clicked Analyze.
   Analysis took **91.064 s**; open/analyze/export workflow **99.939 s**.
   Exported source matches the specified visible ROI with thumbnail MAE **0**.
   Partial/unlabeled input rendered **INDETERMINATE**, not NORMAL.
2. Clicked Mark and physically dragged `(800,350)` to `(1000,600)`, starting
   outside the only AI box (its rendered fill was x=1215..1307, y=255..336).
   The real Reviewer annotation dialog opened. Submitted a region question
   through its edit/OK controls; the actual ChatPanel displayed the answer.
3. Moved the owned Viewer from `(19,30)` to `(219,150)`, without resizing or
   changing display. Exported before/after App widget renderings show both boxes
   following the Viewer. The source image, regional-conversations JSON, summary
   screenshot and chat screenshot are byte-identical across this move.
   Result JSON differs only in export `case` and `created_at`, not findings/trace.
4. Submitted an inline second question for the manual region. Then clicked the
   moved existing f1 box at `(1460,400)` and submitted a separate question.
   Clicking the moved manual box at `(1100,570)` reopened its own two-turn
   history immediately, without another model request. f1 has its own one turn.
5. Shrunk only the test Viewer from 1522×1136 to 1422×1036. Actual state changed
   DISPLAYING → SETUP; old Overlay/Summary/Chat disappeared and ROISetup appeared.
   Clicking Export created no new stale export. No fresh ROI was accepted and
   no subsequent image was submitted. App and Viewer were closed via their UI;
   their PIDs and the owned Gateway listener were subsequently absent.

Pixel audit of the **actual exported overlay layer**, not an expected-box mock:

| Rendered fill | Before, inclusive px | After, inclusive px | Edge delta |
| --- | --- | --- | --- |
| Manual | 801,351–998,597 | 1001,471–1197,717 | 200,120,199,120 |
| AI f1 | 1215,255–1307,336 | 1416,375–1508,456 | 201,120,201,120 |

Every edge is within one physical pixel of the commanded `(200,120)` translation.
This allows the actual 150% Qt rounding; it does not claim subpixel exactness.
The overlay-layer export contains App-rendered pixels only, not desktop capture.
Capture exclusion remained enabled throughout.

All three regional answers requested no finding change. Their distinct host turn
IDs join exactly to `interactive_review` status `no_change`, user_confirmed=false:
`db5e4f5e5df242689dd5bb001ebbab65`,
`63ec7016816e43459346cc5469dce8c4`,
`0d6ff70dc9b24c4b997d762d4ac16913`.
The model explicitly did not treat its crop as proof of Viewer movement;
movement is proven by host geometry and screenshots instead.

## Preserved local evidence

Under the direct worktree's ignored `data/tmp/`:

- `interaction-74d6ee9-gui-case-119-projection55a/receipt.json` and driver snapshot.
- `native-projection55-audit.json`: before/after pixel and byte comparisons.
- `native-projection55-final.json`: actual clean git status, thread/outcome joins,
  resize invalidation, stale-export rejection and artifact hashes.
- `regional-ui-projection55manual1.json`, `regional-ui-projection55manual2.json`,
  `regional-ui-projection55existing.json`, `regional-ui-projection55reopen.json`:
  actual Qt accessibility answers; expected-question matching, zero observer calls.
- `live-interaction-74d6ee9/DICOMOverlayAgent/data/exports/`:
  initial `desktop-20260924-132319-925004`, pre-move `...-132447-861635`,
  post-move `...-132457-632133`, final reopened history `...-132750-579706`.

Final source SHA-256:
`cce82cb830055010eed9296e5c4cb7146e9b46ac2658c2e4ccf7603adc6f8e94`.
Final result SHA-256:
`e91d0334f75cdc27b5123e7b83d789141ce1a1d2d20e146c5ea881601c9a1336`.
Final conversation SHA-256:
`ed49a1569d6adf766358493f279df26649d4d0697d5d51b9a30d791d08c05578`.
Final usage receipt SHA-256:
`2b1d50e5f29561e93948e0cf0fcc43a1df87a8aab2180c3bed9a3a3c82bf420c`.

**10 original/regional model stages** bind public session usage to runtime
observations as `gpt-6-astra`, reasoning `medium`, through the existing subscription
route. No API key or model substitution. Public usage is not a complete billing
ledger; missing usage must not be called zero.

## Failures and remaining gates

The first local question helper searched only top-level UIA windows and missed
Qt's nested input dialog; the dialog itself had opened correctly. The helper was
corrected to search descendants only of the owned process before submission.
A read-only JSON audit initially used Windows' default encoding and failed on
Unicode; rerun explicitly with UTF-8. Neither attempt triggered extra inference.
The older driver hardcodes `source_dirty=true`; its original receipt was retained.
The separate sealing receipt records actual clean git status at 55ec9c9.

Both push/PR CI runs and both secret scans at 55ec9c9 completed successfully.
The prior 1,688-pass/six-skip source suite is unchanged by this documentation-only
checkpoint. This native evidence adds no package or clinical-accuracy claim.

Still open: actual cross-monitor/DPI transitions, browser and third-party DICOM
viewers, mid-analysis image replacement, native manual-ADD promotion/dismissal,
canonical observation/evidence host assembly, and >=100 current-model blind
multi/urgent clinical cases. The regional workflow is tested, not universally
complete. Manual Mark covers the safe image ROI, never the unrestricted desktop.
