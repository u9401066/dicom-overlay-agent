# Medium desktop batch: complete-image calibration and execution — 2026-09-24

Continuation of the [fresh 120-case selection](prospective-medium-cohort-2026-09-24.md).
Batch execution is in progress, not sealed or scored. No clinical pass is claimed.

## Actual complete-image ROI calibration

Clean source App `7eba45dd616d2b85f934f725768b5c234e01ef17` and the real frameless
Qt Viewer were launched with an isolated temporary config and the existing verified
OpenClaw 2026.9.3 subscription runtime. The desktop remains 2560×1600 at 150% scale.
The old interaction-test ROI/config was preserved, not silently widened.

Using the actual ROI dialog on the owned synthetic grid, native drag and Enter
selected the Viewer content. The first conservative drag left two physical pixels
on the right/bottom. A second Settings → Set ROI drag `(30,30)`–`(1530,1110)` saved
zero margins against a 1500×1080 reference. The resulting capture is exactly the
Viewer's image content, not the full desktop or another application's content.
Both bounded selection-preview screenshots and input receipts are retained.

An initial calibration file-open attempt failed: WScript activation plus Ctrl+O
did not open the frameless Viewer's dialog. No inference occurred. The failure
receipt remains. Owner-verified physical click, foreground check and native Ctrl+O
opened the real QFileDialog successfully; the existing dialog controls then opened
the exposed/de-identified case `meeti_44709848`. No programmatic Viewer image setter
or direct model upload replaced the UI action.

Actual Analyze/Export completed in **110.821 s** (model analysis 106.732 s). Exported
source is 1500×1080 with RGB MAE **0** against the pre-analysis visible ROI.
Comparison to the original file scaled bilinearly yields MAE **0.58394 / 255**;
the small difference is renderer resampling, not a claimed byte-identical file.
The actual summary was visually inspected: twelve-lead heading, INDETERMINATE,
review required, five findings. Four stages bind to Astra medium. This exposed
calibration case is excluded from the new batch and does not measure accuracy.

Calibration export in the isolated local runtime:
`data/exports/desktop-20260924-144954-635855`.

- Original input SHA-256: `35ef06c2d95a68889b960d91974a0e8fc9a9ecd467a4633bee1128322b679de0`.
- Captured source SHA-256: `a42ade2c22497908b48ed70e20267af3d94cd7b383572d8d4dc71ac3442d2b86`.
- Result SHA-256: `ee3393197d0d30027647b75b3e39f53ad5ce4afed5e2540a2e86b115f403d089`.
- Usage receipt SHA-256: `6a034257e547b3965bd1d4c3f1b2846a03a0343b6d597b4bc81fe6bbb396bf79`.

## New prospective run protocol

Only the answer-free inference manifest enters the driver. Its hash, all 120
ordered source-image hashes, source-code fingerprint, ROI config, driver/helper/
usage-collector hashes and owned process IDs are bound in `plan.json`. The script
does not read gold, call an analyzer directly, or substitute synthetic responses.

For each case it physically opens the Viewer file dialog, selects the real file,
checks window geometry/ownership and saves the bounded visible ROI. File-to-screen
bilinear MAE must be below 2 / 255 before Analyze. After actual Analyze/Export,
the exported source must match the recorded visible ROI at MAE **0**. Public
per-stage usage must bind to `gpt-6-astra` / `medium`; source, result, marked UI,
coordinate/tool audits and usage hashes are retained. Incomplete/review results
remain in the cohort; an export is not automatically a clinical pass.

Each attempt and final receipt is create-only. Existing successful cases are not
rerun on resume; an unresolved/failed attempt or changed binding stops the driver
for inspection. An observation deadline does not prove the App stopped: inspect
the same live process before any retry. Failed inference/usage checks are retained,
not dropped or reported as zero usage. Initial execution is a three-case tranche
before continuing the remaining fixed order.

### First-case checkpoint: September 24, 14:54 UTC

Case index 0 (`meeti_42918436`) completed: 110.420 s workflow / 98.593 s analysis,
file-to-visible MAE 0.53507, visible-to-export MAE 0, four verified medium stages.
The rendered summary was inspected: WARNING — incomplete assessment, review
required, two findings. These fields describe the preserved output, not agreement
with unopened gold. Case index 1 had started at this checkpoint; the rest are not
credited as completed. The live process/session and per-case receipts, not this
dated paragraph, are authoritative for later progress.

First export: `data/exports/desktop-20260924-145401-720536` under the isolated runtime.
Result SHA-256: `32922eca47535db7c37b2372273df011a926d6a06d650000ec0730c5972b224d`.
Source SHA-256: `592d3c0fec80cd88317870b2258fd0451d954104019ab49f3d974daaec95da85`.
Usage receipt SHA-256: `2b6ae34a8c4f6bcdf2de9ea9f9350fcaafd93a48cb584c5313a306315bab61c2`.

Private evidence root:
`C:/Users/Ericlab/AppData/Local/Temp/dicom-medium-batch-20260924/`.
It holds `config.yaml`, native calibration scripts/receipts/previews, the failed
`baseline-receipt.json`, successful `baseline-second-receipt.json`, `run-batch.py`
and `cohort-run-7eba45d/plan.json` plus per-case attempt/ROI/receipt directories.
Raw exports remain in the isolated App's existing local export directory.

No App code/dependency/schema/model-route change or EXE refresh occurred. Both
7eba45d CI runs and secret scans passed before the new batch. Clinical gold stays
sealed; diverse-device/legacy inputs, canonical host ledger integration, clinical
rule completeness and the overall >=100-case acceptance remain unfinished.
