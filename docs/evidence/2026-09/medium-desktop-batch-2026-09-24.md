# Medium desktop batch: complete-image calibration and execution — 2026-09-24

Continuation of the [fresh 120-case selection](prospective-medium-cohort-2026-09-24.md).
**Current status, September 25 Taipei:** all 120 actual GUI cases completed,
independently verified, sealed and scored. **Clinical acceptance failed.** The
historical checkpoints below remain unchanged; they describe progress at their
stated times, not the final outcome.

## Completed batch and post-seal score

The original continuation driver terminated with exit code 0 and reported
117 newly verified cases, preserving the initial three without rerunning them.
The last receipt finished at `2026-09-24T18:30:30.531254+00:00`. The independent
auditor verifies **120/120**, zero pending/invalid/technical failures and **482**
distinct Astra-medium model stages. All exported sources match their pre-analysis
visible ROI at RGB MAE 0; maximum file-to-visible resampling MAE is 0.585651/255.
Execution correctness is not diagnosis correctness.

The [separate seal/score procedure](../../evaluation/verified-desktop-batch.md)
inventoried 2,519 files/log-prefix records, including recursive crops, and reran
the complete audit before sealing. Only afterward was gold opened with its
pre-inference digest. Scoring made **zero model calls**, replayed no guardrail
pipeline, and changed no original output. Existing draft schema validation is
part of scoring; it is not canonical medical-ledger validation.

| Automated endpoint | Result | Descriptive 95% Wilson interval |
| --- | --- | --- |
| Strict complete-reference case pass | 0/46 (0%) | 0–7.71% |
| Exact severity | 13/120 (10.83%) | 6.44–17.66% |
| All urgent concerns caught | 5/24 (20.83%) | 9.24–40.47% |
| Asserted acute `cant_miss` cases | 0 eligible; unmeasured | Not applicable |
| Legacy App-draft schema | 115/120 (95.83%) | Technical check, not clinical accuracy |

All 46 complete-reference cases also fail complete diagnosis recall. The 74
partially uncertain references are not promoted into complete-reference cases.
Five schema failures cite findings referencing leads absent from the visible lead
inventory; original results and diagnostics remain preserved for investigation.
Actual severity distribution is 21 critical, four warning and 95 info; the latter
must not be read as 95 normal studies. These automated mismatches require source/
report/concept-matcher adjudication, not post-hoc relaxation of scoring rules.

Mean stored analysis time is **93.993 s**, mean actual per-case GUI workflow time
**106.485 s** (77.098–141.858 s). Concurrent engineering workloads and a different
cohort mean neither timing nor score is a controlled comparison with historical
Astra-low results. No reference boxes, patient-independent split or representative
device distribution is established. Normal controls, confirmed acute sensitivity
and partial-input subgroup performance have zero eligible denominators here and
are **unmeasured**, regardless of legacy aggregate default values.

Private seal: `sealed-medium-batch-20260925.json`; private scorecard:
`scorecard-medium-batch-20260925.json`, both under the private evidence root below.
Raw gold/images/model output are not published.

- Seal SHA-256: `57aeb9d03c9d79346e09bcd65bc09d51e716ec981a77be4857bdf95a1bd346de`.
- Scorecard SHA-256: `6532f1ec79bd0fc95099a7014bc4ceb84e0d4bfeaea55df83b762055074f9046`.
- Pre-inference gold SHA-256: `cae03104d538fa7c38e5021e9a2620dc5e19636963b65fb8b6dd23c200503243`.
- Scorer provenance digest: `c6ab4272865066db7f40de2bc345c167c3fc49cbcb52e0ec596d834872ea22e2`.

The existing scorer implementation has no Git changes from the frozen source
branch. Its rebuild-script byte digest differs across worktrees solely because
of line endings; normalized text equality was checked, and the actual executed
byte digests remain in the scorecard. The plan digest was first independently
captured mid-run, not independently timestamped before execution. A local seal
is not a signature or independent GUI-event attestation.

New seal/score protection tests: 24 synthetic casesets passed in 138.79 s. Full
unit/integration/smoke regression: **2,160 passed, seven explicit skips in 353.94 s**.
No new App runtime, prompt, dependency or packaged executable was introduced by
this checkpoint. Localization/reconciliation integration, diverse real-input
coverage, clinical improvement and current-binary GUI/DPI acceptance remain open.

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

### Independent audit checkpoint: September 24, 15:08 UTC

The initial three-case tranche finished. Cases 1 and 2 completed in 133.349 s and
107.969 s respectively; their actual rendered summaries were also inspected.
Both remained INDETERMINATE/incomplete/review-required, not clinical passes.
The same App/Viewer and frozen driver resumed from case 3 without repeating cases
0–2. The run is ongoing; do not start replacement windows or a second driver.

At this checkpoint, **6 / 120** cases (indices 0–5) independently verify, **114**
are pending, and no completed case has a technical failure or invalid evidence.
All 24 recorded model stages match the original Gateway log as Astra medium.
Every exported source exactly matches the pre-analysis visible ROI (RGB MAE 0).
File-to-screen bilinear MAE ranges from 0.50028 to 0.53508 / 255. These are pixel
and execution checks, not evidence that any diagnosis agrees with the unopened gold.

The new repository tool [verify-desktop-batch.py](../../../scripts/verify-desktop-batch.py)
reads only the frozen inference plan, inputs, local exports, receipts and original
Gateway log. It makes no inference, GUI, network or public-session requests, and
does not mutate artifacts. Supply the independently preserved plan digest, not a
fresh digest silently substituted after edits:

`ba0351ab71dcf3972dd69666694c8e5ca3540fc93ba1e9aae2523386fe184fd6`.

```powershell
uv run --frozen python scripts/verify-desktop-batch.py `
  --run PATH_TO_COHORT_RUN `
  --manifest PATH_TO_ANSWER_FREE_INFERENCE_JSON `
  --exports-root PATH_TO_ISOLATED_APP_EXPORTS `
  --gateway-log PATH_TO_ORIGINAL_GATEWAY_LOG `
  --plan-sha256 ba0351ab71dcf3972dd69666694c8e5ca3540fc93ba1e9aae2523386fe184fd6 `
  --allow-partial
```

The tool independently hashes ordered input images and the recorded top-level
export inventory (crop subdirectories are not sealed by this version); checks
case/attempt identity, chronology, source geometry and pixels;
joins every trace stage/retry to its public usage snapshot and unique original
runtime identity; rejects cross-input session reuse and out-of-root export paths.
It does not trust receipt success flags or recorded pixel-error values alone.
Masked log identities require one exact identity and a unique >=16-character
prefix for the other, never two masks. Missing/stale token counts remain unknown,
not zero; token snapshots are not a monetary billing ledger.

Default exit status is nonzero until all 120 cases verify. `--allow-partial` only
permits pending cases, never technical failures or invalid completed evidence.
An in-flight attempt remains pending. A concurrent/changed/unreadable receipt must
be inspected and audited again, not treated as permission to rerun inference.
Recorded GUI actions and source/config/process provenance are not independently
reattested by this artifact verifier. It neither validates the canonical medical
evidence ledger nor scores clinical accuracy. Synthetic mutation tests cover these
boundaries without accessing private images or gold.

At 15:14 UTC a repeat independent audit verified **10 / 120** cases and 40
distinct model stages, with 110 pending and zero invalid/technical failures.
The real CLI without `--allow-partial` correctly exited 1 for this incomplete run.
The dedicated verifier suite has **33 synthetic tests**; together with current
documentation-link checks, **37 passed**. These tests do not replace native cases.
The final explicit unit/integration/smoke suite completed with **1,769 passed /
six opt-in/private-fixture skips in 201.71 s**. Ruff, formatting and staged secret
scan passed. This excludes frozen-binary and native-input opt-in gates; it is not
a new packaged-executable test.

### Continued execution and critical-first observation: 15:25 UTC

The same live batch now has **16 / 120 independently verified cases**, 104 pending,
64 distinct verified medium stages and no completed invalid/technical failures.
Gold remains unopened. Neither this checkpoint nor the new clinical workflow
documentation changed the App, runtime rules, model prompts, config or driver.

Case index 12 (`meeti_42323817`) provides an actual critical-first execution sample,
not a diagnosis-accuracy pass. Export `desktop-20260924-152002-843586` has
`critical_triage/activated`: f2 selected, a limb-lead support probe scheduled, f1/f3
lower-priority refinements deferred. The two actual refine entries target f2 and
that support probe. Before finalization, deferred normal entries were marked
unassessed; the final deferred-axis guard retained incomplete/review state.
The actual rendered summary was inspected and shows CRITICAL — incomplete
assessment, not a falsely complete report. Four model stages remain bound to
Astra medium. Analysis took 94.218 s / workflow 106.717 s; without a matched
non-prioritized comparator this is not proof of a speed improvement.

- Source SHA-256: `0acfe082206e17ae09914e585489b94aaac910746d834446e31df4564753f818`.
- Result SHA-256: `4e04e896206654cea29f2b32d79c84098325ae9728770a806aca03db327a1f29`.
- Usage SHA-256: `c863dd2ee06e945b015bfdc00be7738cfe5270eb08c22fef4197764b7f8d4bf9`.

The source/image binding is independently verified; clinical hypothesis accuracy,
localization accuracy and calibration remain unscored. Both ea94429 CI runs and
their secret scans passed; the live GUI driver continues, with no replay of
already completed cases.

No App code/dependency/schema/model-route change or EXE refresh occurred. Both
7eba45d CI runs and secret scans passed before the new batch. Clinical gold stays
sealed; diverse-device/legacy inputs, canonical host ledger integration, clinical
rule completeness and the overall >=100-case acceptance remain unfinished.
