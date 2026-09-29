# Two-crop EKG lead-group coverage — 2026-09-25

The [sealed 120-case batch](medium-desktop-batch-2026-09-24.md) remains unchanged
and failed clinical acceptance. Its mean concept recall is 0.091; its 0/46
complete-diagnosis recall means no complete-reference case recovered **all**
expected concepts, not that no concept was ever identified.

Inspection found a scheduling limitation worth testing: a two-crop budget could
spend one turn on a small known finding and the other on a broad different lead
group. In the first exposed baseline case, the actual crops were a narrow V4–V6
region and the limb group, leaving other precordial panels without a detailed
group pass. Final reconciliation cannot invent new finding IDs or coordinates;
new localized findings must instead enter through an evidence-bound refinement.
This is a plausible recovery limitation, not proof of the cause of every miss.

## Policy change and boundaries

The App explicitly enables public
`MultiPassInterpreter(prefer_ekg_group_coverage=True)` from harness commit
`f0f486229cd057c291dd2a66f036f1ce796a42b6`.
The option defaults off for other consumers. With a two-turn refinement budget,
it uses both observed precordial and limb group crops, pairing existing hypotheses
where spatially supported and permitting the existing ADD/refinement path.
It adds no model turn and does not change prompts, diagnosis rules, bbox receipt
validation, final-ID restrictions, calibration requirements or deadlines.

Eligibility requires all twelve named lead entries to be explicit, valid and
nonduplicated **before** layout normalization, both group unions to be bounded,
and at least two systematic probes allowed. Recovered/missing/unknown lead identity
does not satisfy this gate. No fixed 12-row coordinates are substituted. Existing
critical-first, waveform/local attention, other modalities and other budgets keep
their prior routes. Planning coverage is explicitly not diagnostic completeness;
the subsequent trace must prove each planned crop actually executed.

The initial new tests caught three issues: expected group order differed from the
existing precordial-first order; a missing-lead test could become eligible after
legacy layout repair; and a synthetic critical fixture lacked the concrete detail
required by the established critical gate. The implementation now checks original
inventory before repair, and test expectations/critical fixture were corrected.
No critical gate was weakened. An initial public test invocation omitted its dev
extra and found a global pytest; rerunning with `uv run --extra dev python -m pytest`
used the isolated environment. No global package was installed.

## Verification

Public harness: fourteen new synthetic regressions; **459 tests pass in 2.48 s**,
Ruff/format and public compatibility checks pass. Both public CI runs for the pin
completed successfully. The first App full run found only the stale hard-coded
submodule pin (2,144 passed, one failed, seven skipped); the binding was updated,
and all nineteen boundary checks passed. The fresh complete App run then passed:
**2,145 passed / seven explicit opt-in skips in 381.89 s**. Final focused
boundary/multipass/prompt/document checks passed **218 tests in 2.76 s**.
App Ruff/format and document-link checks also passed.

Completed actual GUI replays and their limits are recorded below.
They are exposed development examples, not a new blind accuracy cohort. The
canonical scientific pipeline remains incomplete and no new EXE is being claimed.

## Actual native replays

One source App, native Qt Viewer at 150% desktop scaling, and a separate private
Node/OpenClaw runtime were used. Both cases were opened through the real file
dialog, Analyze and Export. No analyzer helper or injected response replaced
those actions. All 103 tracked App/public-engine source files were hash-bound
and unchanged during each run; App source was dirty on `b40f841`, with the exact
committed public-engine pin above. Prior sealed batch artifacts were not rewritten.

| Observation | Exposed case index 0 | Exposed case index 1 |
| --- | --- | --- |
| Actual path | Existing critical-first route | New two-group coverage route |
| Executed refinements | Candidate + mechanism-support limb crop | Precordial + limb group crops |
| Verified Astra-medium stages | 4 | 4 |
| Analysis time | 100.898 s | 103.686 s |
| GUI workflow time | 132.448 s | 117.596 s |
| Named lead inventory / schema warnings | 12 / 0 | 12 / 0 |
| Visible ROI versus exported source | Exact RGB pixels | Exact RGB pixels |
| Candidate asserted-concept hits | 1/4 | 0/4 |
| Original frozen asserted-concept hits | 0/4 | 0/4 |

The first replay raised a specific critical candidate during coarse reading, so
the new policy correctly did **not** activate. It retained urgent-review wording
and explicit deferred axes. An automated urgent-concern check changed from missed
to caught, but the case is already exposed, stochastic, and on a different source
revision; this cannot be attributed to the new policy or called clinical success.

The second replay actually executed
`ekg_systematic_precordial_leads` at `[0,0.425,1,0.575]` and
`ekg_systematic_limb_leads` at `[0,0,1,0.575]`. These padded source crops contain
all final preserved, explicitly named lead rectangles. Neither is a diagnostic
bbox. The frozen case-1 run instead used `[0,0,0.362,1]` plus the precordial group,
so most of the limb strips' horizontal extent had no detailed crop review. Broader
coverage trades away a narrow target's magnification; this needs quality evaluation,
not an assumption that every broader crop improves subtle waveform recognition.
Three cautious findings remained; the automated **asserted** reference
concept recall stayed 0/4. A possible conduction-delay label is not the same as
an asserted diagnosis and was not awarded affirmative credit. Coverage alone did
not resolve diagnostic uncertainty or prove improved accuracy.

Both results remained incomplete/review-required. Both review images and the
second actual Qt summary capture were visually inspected. One second-case bbox
still has a mechanical low-signal flag; the routing change does not solve bbox
clinical precision. Timings are individual exposed runs with concurrent engineering
work, not a controlled speed comparison. No extra inference was used for scoring.

## Private evidence

`C:/Users/Ericlab/AppData/Local/Temp/dicom-group-coverage-20260925/` contains the
actual launcher/config, case-0 attempt/receipt/ROI/audit, preserved per-case App
logs and `case-001/` for case 1. Native exports are under its `runtime/data/exports/`:

- Case 0: `desktop-20260924-194518-912633`;
  audit SHA `36a83a53565898b59b86b4178582d06bc5db3ab5930505cf5b14674932d14b66`.
- Case 1: `desktop-20260924-194901-118072`;
  audit SHA `ddfe6f4ccb749b6709172586b1ab03abb3098db4d98bbc138bc4dd7babc0510a`.

Audits rehash recursive export artifacts and source files, verify original/candidate
source equality, actual stage count, usage receipts and executed crop containment,
and compare with the existing scorer after GUI completion. Original sealed score
and seal hashes are unchanged; original predictions are neither repaired nor
rescored in place. This is development evidence, not a replacement sealed cohort.
The owned App and Gateway were closed through Quit after both runs; their process
and port checks were empty. The test Viewer was retained.

Further diagnostic work must distinguish a true recognition miss from an image
that cannot support the reference report's measurement/etiology. Neither an
asserted source report nor a successful automated label extraction proves that
every corresponding diagnosis is observable in an uncalibrated rendered screenshot.
Independent matched evidence and specialist adjudication are still required;
do not fabricate calibration or change these frozen scores to disguise the gap.
