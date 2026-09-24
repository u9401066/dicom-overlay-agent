# MEETI OpenClaw Experiment Record (2026-08-09)

## Scope and claim boundary

This record covers real image transactions performed by the OpenClaw embedded
agent with `openai/gpt-5.4-mini` over the native
`openai-chatgpt-responses` transport. ChatGPT/Codex subscription OAuth was used
only as the transport credential. No Codex app-server or Codex agent performed
the ECG interpretation, and Platform API keys were disabled.

The completed evidence consists of a frozen 32-case paired pilot, a later
8-case unseen harness check, and a one-case exposed regression check. The full
9,922-case blind cohort has not been run to completion. A pre-publication launch
was intentionally interrupted at 289 baseline results so final source and
documentation commits could not change the fingerprint between paired arms.
At the observed 71.058 seconds per MultiPass case, a sequential candidate-only
run is about 196 hours before restart, quota, and post-processing overhead.

MEETI report-derived labels are weak and sometimes incomplete. The numbers
below are experiment agreement metrics, not medical diagnostic accuracy or a
deployment claim. Safety misses remain visible and are never converted into
artifact failures or forced abnormal answers.

## Frozen paired pilot

Artifact root:
`data/experiments/meeti-paired-pilot32-v152-unseen-v2`

The two arms shared a frozen source/scorer fingerprint and the same 32 cases.
The baseline was a minimal one-look image read. The candidate used the real
MultiPass crop/refine workflow and matched ECGFounder waveform evidence.

| Metric | Baseline | MultiPass | Delta |
|---|---:|---:|---:|
| Cases / errors | 32 / 0 | 32 / 0 | 0 |
| Strict pass | 0.000 | 0.094 | +0.094 |
| Mean partial credit | 0.253 | 0.480 | +0.227 |
| Keyword recall | 0.291 | 0.551 | +0.260 |
| Concept recall | 0.298 | 0.544 | +0.246 |
| Normal severity-safe | 8/8 | 6/8 | -2 cases |
| Normal, no false positive | 3/8 | 3/8 | 0 |
| Urgent concern caught | 0/10 | 3/10 | +3 cases |
| Raw JSON clean | 1.000 | 1.000 | 0 |

Partial credit improved in 23 cases, regressed in 4, and was unchanged in 5.
The paired sign-test p-value was `0.0003107488`. The paired mean partial-credit
delta was +0.227, with a 10,000-sample bootstrap 95% CI of `[+0.085, +0.368]`
and a two-sided random-sign p-value of `0.00449955`. This supports a significant
improvement in this weak-label composite metric only. It does not erase the
normal-severity regressions or the 7/10 urgent misses.

Candidate SLA compliance was 32/32 at every stage:

| Stage | Target | Mean | Maximum |
|---|---:|---:|---:|
| Initial/coarse read | 60 s | 16.245 s | 29.363 s |
| First crop/detail read | 100 s | 29.965 s | 55.718 s |
| Whole case | 180 s | 70.309 s | 98.459 s |

The full comparison is in
`comparison/comparison.md` and `comparison/comparison.json`. Each arm contains
raw case JSON, scorecards, provider logs, protocol fingerprints, transport
receipts, annotated review PNGs, and coordinate audits.

## Version 1.5.6 unseen check

Artifact root: `data/experiments/meeti-v156-unseen8-v1`

The eight identities were selected after applying a 1,220-case exposure
denylist. OpenClaw received the answer-free inference manifest; the gold
manifest was used only after inference. Runtime ownership verification found:

- agent loop owner `openclaw`;
- model route `openai/gpt-5.4-mini`;
- 74/74 provider requests through `openai-chatgpt-responses`;
- zero Codex app-server/handoff markers and zero Codex agent dependencies;
- Platform API key disabled;
- `fastMode=true` observed, but no provider priority tier was observed.

Engineering gates passed for 8/8 cases with zero errors: schema 1.000, bbox
in-bounds 1.000, raw JSON clean 1.000, MultiPass trace present, systematic
probes present, review export present, and coordinate projection audit passed.
There are 8 annotated review PNGs and 30 exported crop PNGs.

| Metric | Result |
|---|---:|
| Strict pass | 0.250 |
| Mean partial credit | 0.595 |
| Keyword recall | 0.631 |
| Asserted concept recall | 0.627 |
| Candidate concept recall | 0.107 |
| Weighted concept recall | 0.557 |
| Explicit-normal specificity | 2/2 (1.000) |
| Urgent concern caught | 1/3 |

All eight cases met the SLA. Initial response was 16.180 seconds mean and
23.850 seconds maximum; first crop/detail was 28.508 seconds mean and 37.678
seconds maximum; total was 71.058 seconds mean and 83.533 seconds maximum.

The artifact verifier was intentionally run with safety misses retained. This
proves artifact integrity, not a clinical safety gate. Manual review found
several plausible disagreements between the image and aggregated machine
report labels, including mild-looking tracings carrying urgent weak labels.
Those disagreements were left in the record instead of tuning the harness to
the answer key.

## Version 1.5.7 duplicate-finding regression

Artifact root: `data/experiments/meeti-v157-regression1-exposed-v1`

This one-case run deliberately reused an inspected case and is therefore a
regression check, not unseen accuracy evidence. The model followed the revised
prompt and emitted only two distinct findings: sinus bradycardia and a
nonspecific ST-T abnormality. The lead-II rhythm box aligned with the waveform;
the prior duplicate precordial rhythm boxes were absent. Deterministic exact
study-level rhythm deduplication is also covered by unit tests, while localized
ST morphology is explicitly not collapsed.

The case completed in 23.064 seconds to initial response, 35.498 seconds to
first crop/detail, and 63.682 seconds total. Schema, bbox, artifact validation,
and coordinate export all passed. The output includes one review PNG and three
crop PNGs.

## MultiPass execution and tools

For each image, the auditable workflow is:

1. Capture the original ROI, record exact source dimensions and digest, inspect
   image quality/layout, and produce a coarse structured read.
2. Run deterministic local image aids for ink/signal candidates and EKG row
   geometry. These propose review regions and validate layout; they do not set
   a diagnosis.
3. Validate proposed normalized boxes with the OpenClaw native
   `dicom_bbox_validate` tool, bind receipts to case/session/image/coordinates,
   and crop from the original pixels.
4. Perform bounded independent limb/rhythm-strip and precordial probes, then
   send each actual crop back through a separate OpenClaw image turn for
   refinement. A crop may adjudicate only evidence it really contains.
5. When the manifest has a cryptographically matched raw 12-lead waveform,
   OpenClaw may call `ecg_founder_analyze_waveform` once per case. ECGFounder
   supplies uncalibrated ranked labels plus deterministic lead-II rate and R-R
   regularity. It is supporting evidence only, has no image localization, and
   cannot independently create or remove a diagnosis.
6. Reconcile `ADD`, `REVISE`, `RETRACT`, and `KEEP` decisions, apply grounding,
   duplication, normal/negative, and deadline guards, then emit the final
   report and marked review image.

The Process tab and experiment traces expose prompts by stage, tool names,
inputs/receipts, crop coordinates, validation decisions, revisions, and concise
clinical rationale. They do not expose or claim access to private chain-of-
thought.

## Coordinate and export proof

All displayed and exported finding boxes are projected from the same captured
source frame. The audit records source size, normalized and pixel coordinates,
clamping, image digest, signal/ink evidence, lead semantics, and round-trip
projection. Analysis crops are exported separately and shown with dashed cyan
boxes so they cannot be mistaken for diagnostic annotations. Desktop review
exports now contain source, result JSON, marked image, crop directory, and the
coordinate audit as one self-contained review package.

## Scoring semantics

- Explicit normal/WNL references allow a normal answer. The harness never
  requires at least one abnormal finding.
- Strict, diagnosis, cannot-miss, and urgent metrics use asserted reference
  concepts only.
- For incomplete weak reports, a clearly uncertain differential may match a
  candidate concept at half weight. Candidate credit cannot satisfy strict,
  cannot-miss, or urgent gates.
- Explicitly negated concepts never receive asserted or candidate credit.
- Partial credit reports severity, keyword/concept coverage, false positives,
  schema, and bbox quality separately so a high composite cannot conceal a
  safety miss.

## Portable release verification

The source passed Ruff and the complete unit/smoke suite: `915 passed, 3
skipped`. The skips are explicit opt-ins for the freshly built bundle and
native Windows capture. After rebuilding, those checks were enabled separately:
packaged self-check/Gateway smoke `4 passed`, and native capture exclusion `1
passed`.

The new artifact is `dist/DICOMOverlayAgent/DICOMOverlayAgent.exe`:

- bundle status `ok`, 0 failures, 0 missing files, 0 banned components, and 0
  runtime residue;
- launcher 7,397,370 bytes (7.05 MiB), SHA-256
  `27fcb0fafecdb2285d9dc1aae1a51d6ca46a0930592400740abfbe6deb17984e`;
- payload tree SHA-256
  `814eadbf8cda0adf6adbc9512145524b0689da901f0cb44f6d21c5886062d2ff`;
- total 385,883,674 bytes (368.01 MiB), 16,188 files;
- OpenClaw `2026.7.1-2`, Node `v24.18.0`, harness/plugin `1.5.7`, and 51
  bundled skills;
- both native tools loaded with no diagnostics;
- Codex migration bundle marked `oauth_migration_only`, with no Codex agent
  dependencies and no platform binaries;
- no `.env`, MEETI data, waveform, SQLite, sidecar, Torch, or checkpoint/model
  data in the clean release.

An isolated full GUI launch remained responsive after 15 seconds, started one
bundled Node/OpenClaw process, generated first-run local state, and released
port 18789 after shutdown. No model request was made by release smoke tests.

The pinned npm tree reports 7 moderate and 4 high transitive advisories, with 0
critical. A breaking force upgrade was not applied; this remains tracked
upstream runtime debt.

## Full cohort execution status

The first full-cohort launch used artifact root
`data/experiments/meeti-paired-full9922-v157-20260809`. It proved real HTTP 200
image transactions through the OpenClaw embedded agent with
`provider=openai`, `api=openai-chatgpt-responses`,
`model=gpt-5.4-mini`, `fastMode=true`, and no Codex-agent route. Before final
source publication it was deliberately stopped with 289 baseline result JSONs.
Its final supervisor state is `interrupted`, active arm `baseline`, with failure
reason `baseline did not produce a complete, provenance-bound result set`.
Those rows are retained as launch/transport evidence only and must not be mixed
with a later candidate arm.

The authoritative post-publication root is reserved as:

`data/experiments/meeti-paired-full9922-v157-postpublish-v1`

It uses the same 9,922 ordered cases and manifest hashes:

- inference SHA-256
  `bfd64c7e2684049c8cce509460813aacea0c5c33c4d02f718b850ef2e3a9b29f`;
- gold SHA-256
  `803ad1b205dbc7c3dcdd88f4218872c7811e3510a8167ce058e70d1459a5ba8b`;
- `thinking=off`, per-turn `fastMode=true`, 180-second case timeout;
- baseline `minimal_control`, no MultiPass, ECGFounder, rhythm pass, or tools;
- candidate `clinical`, MultiPass with at most two crop targets plus one
  systematic probe, rhythm reconciliation, and matched-waveform ECGFounder.

This document intentionally does not mirror transient PID or case counts.
`paired-experiment.json` in that root is the only authoritative live/completion
state. The supervisor also writes `supervisor.log`, per-arm atomic metadata,
raw results and periodic scorecards. Restarting the same command activates
`--resume --resume-retry-errors` only when source, manifests, runtime, scorer and
protocol provenance still match. Any source change between arms invalidates the
comparison.

## Remaining work before a full-scale claim

The full blind experiment requires continuous machine uptime, AC power and
subscription-capacity monitoring. It must retain per-case logs, review images,
crop artifacts, provider receipts, trajectories and periodic scorecards. The
frozen paired pilot supports continued evaluation, but its normal-severity
regression and limited urgent recall do not justify describing the current
system as fully correct or clinically validated. Only an all-case completed
state plus clinician review can support a full-scale experiment claim.
