# Explicit lead inventory: real App replay — 2026-09-25

The [sealed 120-case medium batch](medium-desktop-batch-2026-09-24.md) remains
unchanged and failed clinical acceptance. This is an exposed development replay,
not a replacement prediction, fresh blinded case or improved accuracy score.
The subsequently observed startup/plugin-path gaps are addressed by the
[next native replay](portable-plugin-readiness-2026-09-25.md); the observations
below remain the historical record of this run.

## Observed failure and bounded change

All five legacy-schema failures had an empty `layout.leads` array. Their original
indices 24/26/33/41/94 had local detected-row counts 8/9/8/8/7 and consistent-gap
counts 6/7/4/4/4. The coarse prompt explicitly instructed a 12-row image to omit
per-lead geometry, promising that local pixels would supply it. The detector did
not establish that geometry, so the empty inventory survived to finalization.
This is one verified technical defect, not an explanation for every clinical miss.
All 120 original reports are incomplete/review-required; none still carries the
temporary `pending_multipass_review` reason.

The App prompt now requests each actually visible panel's name, boolean label
visibility and normalized geometry, including 12-row images. Unknown labels and
partial captures remain unknown/partial. It does not reduce the detector threshold,
invent missing leads, weaken validators, change medical labels or add a retry.
Explicit geometry can increase response tokens; no speed or cost saving is claimed.
The public harness, protocol, schema, dependencies and package are unchanged.

## Actual desktop replay

Candidate source based on `d5bb512`, with the recorded prompt change, ran through
the real App and QFileDialog/Analyze/Export controls on Windows 2560×1600 at 150%.
The existing host-cleared case at original index 24 was selected only after baseline
sealing/scoring. No answer was sent to the model. All tracked App-source file hashes
were captured before and checked after the replay (79 files, zero changes); the worktree was explicitly
recorded as dirty, not falsely represented as a clean release.

The authorized Viewer ROI stayed `(30,30,1500,1080)`. Original-file-to-visible
bilinear MAE was 0.490169/255; visible-to-export RGB MAE was **0**.

| Check | Original export | New actual App export |
| --- | --- | --- |
| Visible panel declarations | 0 | 12 |
| Local detector | Eight peaks, not confirmed | Eight peaks, not confirmed |
| Geometry recovery | No usable inventory | Model supplied explicit geometry; no layout-normalization event |
| Legacy validation warnings | Three | Zero |
| Clinical completion | Incomplete, review required | Still incomplete, review required |

Four stages independently bind to Astra medium. Coarse response took 29.349 s;
complete analysis took **98.191 s**. Total observation time was 273.431 s including
startup and an initially ineffective GUI click; it is not steady-state workflow
latency or a controlled comparison. Final report and review images were visually
inspected. The candidate's native report keeps crop limitations in the clinical
notes and exposes detailed coordinates through Process. This is one 150% source
App rendering, not all-DPI/current-EXE acceptance.

The review export still flags seven boxes as low-signal under its existing ink
metric. Their spatial bounds/rendering do not establish clinical localization
accuracy. Missing calibration and unresolved hypotheses remain explicit; the
diagnostic performance problem is not declared fixed.

## Startup and runtime limits retained

The original App/Gateway closed through Quit; its Viewer was retained. A separate
runtime directory preserved the original sealed Gateway log, since Gateway startup
opens that log in write mode. The copied public configuration still selected the
unchanged harness plugin through its old absolute path; the Gateway disclosed this
in its log. Therefore this replay does **not** prove fully relocated/independent
plugin installation. That portability defect needs a separate fix and acceptance.

The first Analyze click occurred during background startup, before Viewer discovery,
and was rejected with `No viewer window, cannot trigger manually`. After the same
App reported ready/MONITORING, a second physical UI action started the **only**
analysis. No in-flight request was repeated. The startup button readiness/feedback
gap remains open. Four actual stages and the original attempt/log are preserved.

## Evidence and tests

Private root: `C:/Users/Ericlab/AppData/Local/Temp/dicom-layout-replay-20260925/`.
It contains the native scripts, unchanged-ROI config, attempt/receipt/source hashes,
bounded visible screenshot, App log and separate runtime/export. Final export:
`runtime/data/exports/desktop-20260924-185138-394927`.

- Input SHA-256: `2fe049c9cf82fe8f6bf456d9ff5ef52ff207cf0bdc175687e73277a4214dd989`.
- Source SHA-256: `19706efc46260ddb280bf5ae9ba6a7cd3a15ffe564caef5b08af7e30d50c11cb`.
- Result SHA-256: `eb1cc804ec00c5dde5affca2813e02315e21387ebeac53df58394b02dc27269b`.
- Usage SHA-256: `bb7a5af9db282d29720b1b30e700b9dc469eb4fedda828e71d8c8f50feb84851`.

Prompt/layout tests: 45 passed; robustness/multipass tests: 262 passed. Three new
prompt regressions protect explicit inventory, unknown/partial inputs and the
deliberately unnamed partial-input scope. The first full suite had 2,162 passes,
seven skips and one staging failure because a mistaken PATH used global Node 25.6.1
instead of supported portable Node 24.18.0. The diagnostic explicitly rejected that
Node version; no dependency reinstall or test suppression was used. Corrected-Node
staging checks: two passed in 123.54 s. Corrected full unit/integration/smoke rerun:
**2,163 passed, seven explicit opt-in/private-environment skips in 386.34 s**.
Ruff, formatting, documentation links and diff whitespace checks passed.

The original 120-case seal/inventory/complete audit was reverified after the new
run, and the original scorecard digest remains
`6532f1ec79bd0fc95099a7014bc4ceb84e0d4bfeaea55df83b762055074f9046`.
The actually exercised prompt-module digest is
`4308e33f39a028f00269927dc32fa0ab136b4600a6acbb4c25e768c3809d6d97`.
Neither a new model-output repair nor a rewritten baseline was used to obtain
the new warning-free inventory.
