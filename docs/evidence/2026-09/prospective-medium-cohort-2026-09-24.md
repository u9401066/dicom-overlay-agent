# Fresh medium desktop cohort construction — 2026-09-24

**At construction: selection complete, model execution not started.** This is not 120 GUI
passes, clinical accuracy evidence, or a replacement for the failed low cohort.
Subsequent [complete-image calibration and batch execution](medium-desktop-batch-2026-09-24.md)
are tracked separately; do not rewrite this construction receipt as an execution seal.

## Population, exposure and selection

The frozen usable source contains 9,922 MEETI images. This is the filtered usable
pool from the earlier >10,000-record intake, not a claim that 10,000 new images
have been tested. The existing source SHA-256 must match before selection.

The current exposure union includes the historical post-desktop list, every
non-full inference subset in the existing MEETI directory, and recorded Luna
canary denylists. It contains **1,366 identities**, including the old 128 reserved
cases. Previously unused reserved subsets are conservatively excluded as well.
Exact bytes and normalized reports from denied identities also block aliases.
Patient identifiers are unavailable: this establishes case/image/report separation,
not patient-level independence or cross-site generalization.

`scripts/build-prospective-desktop-cohort.py` reuses the existing canonical
diagnosis/important-tier rules and answer-free paired-manifest builders. Seed
20260924, canonical diagnosis minimum three, identical-report/image cap one,
canonical-signature cap four. Selection is deterministic and tier-interleaved;
constraints are not relaxed when a quota is infeasible.

| Stratum | Asserted | Partially uncertain | Total |
| --- | ---: | ---: | ---: |
| Acute-risk reference concern | 0 | 24 | 24 |
| Ischemic/infarct | 14 | 14 | 28 |
| Rhythm/ectopy | 14 | 14 | 28 |
| Conduction/QT | 12 | 12 | 24 |
| Structure/voltage | 6 | 10 | 16 |
| Total | 46 | 74 | 120 |

After exclusions, no asserted acute-risk cases meet the existing multi-diagnosis
eligibility. The 24 acute-risk cases therefore have uncertain reference concerns;
they must **not** be described as confirmed urgent diagnoses. There are zero
`cant_miss` references in this batch. A confirmed cannot-miss sensitivity estimate
cannot be computed from it. All 16 target axes appear; minimum observed coverage
is QTc at 10. This profile does not claim the old profile's >=12-per-axis quota.
Additional diverse/legacy/device cases remain necessary beyond this source pool.

## Immutable local pair

Private ignored directory:
`D:/workspace260530_dicom/dicom-overlay-agent/data/eval-datasets/prospective-medium-20260924/`.
`cohort-v1/inference.json` is answer-free; `gold.json` stays separate until the
declared run is sealed. Only input identifiers/images belong in the GUI driver.
The selection report is construction evidence, not an execution ledger.

- Pair ID: `e77a690a5c9cd4d72df05c7e93d877e987b0731605e62dde118d44702f81fda9`.
- Gold SHA-256: `cae03104d538fa7c38e5021e9a2620dc5e19636963b65fb8b6dd23c200503243`.
- Inference SHA-256: `4663a7e5053df6ff1652fb25a6d0f8127c09da396ae068679dcf1038303feeae`.
- Preselection denylist SHA-256: `e18b2f7071e5f9efbe9d1448e1e1abdc67276526fb76e346935a516f302e061d`.
- Selector SHA-256: `b981c60c12c2feb7ca5ecf5767d05fd29ecde9af083378a0c9b15cf4d26394fd`.

All 120 identities are already reserved. Future selections must use at least
`postselection-denylist.txt`: **1,486 identities**, SHA-256
`45f34f0be1a37277a6ff125daaccf4f135bd0d262acfd78bae27bd9129a99870`.
Do not overwrite this pair to cherry-pick cases after seeing results.

## Checks and next execution gate

Twelve new regressions cover deterministic order, answer isolation, exposure by
ID/image/report, duplicate IDs, signature/image/report caps, uncertain and generic
normal labels not satisfying diagnosis counts, frozen-source/overwrite rejection,
and complete paired-manifest construction. Combined old/new selector and exposure
tests: **27 passed in 0.45 s**. Ruff/format pass. The initial local construction
caught a mismatched pair-field name before writing any output; a full construction
regression now covers the exact shared contract. No failed selection was published.
Full explicit unit/integration/smoke run: **1,736 passed, six conditional skips in
228.33 s**; the private/frozen/native opt-in skips are not counted as passes.
All four documentation-link tests and staged secret scanning pass. Header-only
inspection confirms all 120 inputs are 1000×720 RGBA; this is not rendered-image QC.

Before the first case: use an exposed calibration image to set a **complete safe
image ROI through the real App**, bind the clean source/runtime/model profile and
verify exported source pixels. The prior interaction-test ROI intentionally cut
off labels/rows and must not be silently reused for the main complete-image cohort.
Then open each case through the real Viewer file dialog and actual Analyze/Export
controls. Retain failures, usage, source, geometry and marked screenshots per case;
do not replace this with direct file-to-model calls or a mock acceptance run.

Both CI runs and secret scans for the preceding 613b843 checkpoint succeeded.
This preparation changes no production inference, ROI boundary, schema, dependency
or packaged executable. Clinical scoring and >=100 actual current-model cases
remain unfinished.
