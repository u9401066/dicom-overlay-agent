# Real Test Runbook

## Goal

Run the project on Windows with a workspace-local OpenClaw Gateway and verify the real desktop stack:

1. OpenClaw installs inside the repo only.
2. OpenClaw Gateway starts from repo-local config/state.
3. Workspace skills are visible to OpenClaw.
4. The Python overlay agent launches and connects to the real gateway.
5. A real DICOM viewer can trigger ROI setup and analysis.

## Prerequisites

1. Windows 10/11.
2. Node.js 22+ available in `PATH`.
3. Python virtual environment already prepared:
   - `uv sync --all-extras`
4. For the current MEETI protocol, a local ChatGPT/Codex subscription sign-in:
   - run `codex login` once outside the repo;
   - the runner imports OAuth into its isolated OpenClaw state and disables
     `OPENAI_API_KEY` for the experiment;
   - Platform API-key profiles remain available for manual desktop use, but
     are not accepted by the authoritative paired runner.
5. For the production-scale MEETI ECG gate, the public `MEETI.rar` archive from
   Zenodo record `18523205` is present at the repository root. The archive is
   intentionally gitignored.

## Repo-local portable layout

- OpenClaw package: `openclaw/node_modules/openclaw`
- OpenClaw config: `openclaw/openclaw.json`
- OpenClaw state/home: `openclaw-home/`
- Synced runtime workspace: `openclaw-home/.openclaw/workspace/`
- Source skills tracked in git: `openclaw/workspace/skills/`

## Fast path

Run:

```bat
scripts\test-real-stack.bat
```

This does the following:

1. Installs OpenClaw locally into `openclaw/node_modules`.
2. Syncs repo skills into `openclaw-home/.openclaw/workspace/skills`.
3. Validates OpenClaw config.
4. Starts the real OpenClaw Gateway.
5. Runs gateway health check.
6. Launches the DICOM Overlay Agent.

For a subscription-backed desktop launch, open Settings and choose **OpenAI
Subscription via OpenClaw**. The route label must read `OpenClaw agent |
ChatGPT subscription OAuth`. The official Codex package is used only as an
OAuth migration provider; the live inference agent is OpenClaw.

## Manual path

### 1. Install local OpenClaw

```bat
scripts\install-openclaw-local.bat
```

`scripts\install-openclaw-local.bat` keeps repeat runs light: it skips npm when
an already-installed runtime is at or above `MIN_SAFE_OPENCLAW_VERSION`. To
force a fresh npm latest update during a release/maintenance pass, run:

```bat
set FORCE_OPENCLAW_INSTALL=1
set OPENCLAW_NPM_SPEC=openclaw@latest
scripts\install-openclaw-local.bat
```

### 2. Sync skills into the runtime workspace

```bat
scripts\sync-openclaw-workspace.bat
```

### 3. Set repo-local OpenClaw environment

```bat
set OPENCLAW_STATE_DIR=%CD%\openclaw-home
set OPENCLAW_CONFIG_PATH=%CD%\openclaw\openclaw.json
set HOME=%CD%\openclaw-home
set USERPROFILE=%CD%\openclaw-home
```

### 4. Validate config

```bat
node openclaw\node_modules\openclaw\openclaw.mjs config validate
```

### 5. Start the gateway

```bat
node openclaw\node_modules\openclaw\openclaw.mjs gateway run --verbose
```

Expected success signal:

- `listening on ws://127.0.0.1:18789`

### 6. In a second terminal, verify health

```bat
node openclaw\node_modules\openclaw\openclaw.mjs gateway health
```

Expected result:

- `Gateway Health OK`

### 7. Start the overlay agent

```bat
.venv\Scripts\python.exe -m dicom_overlay --config config.yaml
```

## Real viewer test

1. Open your actual DICOM viewer.
2. Make sure its title includes one of the keywords from `config.yaml` under `monitor.window_title_keywords`.
3. If `phi_roi` is missing or if you click the control bar settings button, complete ROI setup.
4. Change image content or click retrigger on the control bar.
5. Watch for:
   - Gateway logs showing requests
   - Overlay panel appearing
   - Region highlights drawn on the viewer

## What is already truly tested

1. Repo-local OpenClaw install works.
2. OpenClaw CLI runs from `node openclaw/.../openclaw.mjs`.
3. Portable config validates.
4. Real Gateway starts and passes health check.
5. Python stack unit/smoke tests pass.

## What still requires your manual real-world check

1. Your actual DICOM viewer title is detectable.
2. ROI selection UX feels correct on your screen layout.
3. OpenClaw model credentials are valid.
4. Real model output matches the JSON structure expected by this project.
5. Overlay click-through behavior is acceptable on your workstation.

## Recognition evaluation (how results are recorded)

The overlay never decides on raw pixels -- every interpretation is first a
structured `AnalysisResult`. The evaluation harness feeds *labeled* images
through the real interpretation/parsing path, scores each structured result
against the dataset ground truth, and writes a machine-readable scorecard. This
is how recognition outcomes are observed and recorded without "watching" the
screen.

### 1. Prepare the labeled dataset

```bat
uv run python scripts\fetch-eval-datasets.py
```

- With no arguments it generates a small **synthetic** labeled set
  (`data\eval-datasets\`) -- this verifies the measurement pipeline only, it is
  NOT a diagnostic-accuracy claim.
- For a real accuracy benchmark, supply openly licensed image URLs + labels:
  `uv run python scripts\fetch-eval-datasets.py --urls-from my-urls.json`
  (format documented at the top of the script).

### 2a. Pipeline check (no token required)

```bat
uv run python scripts\run-eval.py --mock
```

Uses an in-process mock gateway that echoes schema-valid payloads, exercising
the real frame-building / parsing / scoring path. Proves the scorecard
mechanism works end to end.

### 2b. Short real-model diagnostic

```bat
REM Configure the desired provider in desktop/OpenClaw Settings first.
REM Start the gateway, then use the existing environment directly.
.venv\Scripts\python.exe scripts\run-eval.py --gateway ws://127.0.0.1:18789
```

For the prepared MEETI ECG dataset, use the dataset selector and the strict
"all cases must pass" gate:

```bat
.venv\Scripts\python.exe scripts\run-eval.py --mock --dataset meeti --require-perfect
.venv\Scripts\python.exe scripts\run-eval.py --gateway ws://127.0.0.1:18789 --dataset meeti --timeout-sec 180
```

Use `--limit N` while iterating on prompts or scorer behavior, for example:

```bat
.venv\Scripts\python.exe scripts\run-eval.py --gateway ws://127.0.0.1:18789 --dataset meeti --limit 10 --timeout-sec 180
```

To test the real app multi-pass path (coarse read -> crop suspicious regions ->
refine), add `--multi-pass`. `--multi-pass-max-targets` caps the number of
crop/refine passes per image, controlling latency and cost:

```bat
.venv\Scripts\python.exe scripts\run-eval.py --mock --dataset meeti --multi-pass --multi-pass-max-targets 2 --require-perfect
.venv\Scripts\python.exe scripts\run-eval.py --gateway ws://127.0.0.1:18789 --dataset meeti --multi-pass --multi-pass-max-targets 2 --timeout-sec 180
```

Do not use a short diagnostic as the reported comparison. The authoritative
experiment must use the paired supervisor in section 2d so both arms share one
source fingerprint, blinded manifests, ownership checks and artifact gates.

Multi-pass runs write `multipass-trace.jsonl` beside `scorecard.json`. Each line
records the case id, image filename, `model_path=MultiPassAnalyzer`,
`openclaw_analyze_calls`, `coarse_passes`, `zoom_passes`, `crop_calls`, and
`max_zoom_targets`, so a real experiment can prove whether each image was
single-pass or actually crop/refined.

`MultiPassAnalyzer` also receives the downscaled image dimensions used for the
actual OpenClaw request. This keeps the resolution-aware manual-zoom guard live
in both the desktop app and `run-eval.py`: if a target is too small in captured
pixels for a useful digital crop, the result records a `zoom_hints[]` advisory
instead of pretending that a crop can recover detail that the screenshot never
contained.

### 2c. MEETI 1000+ artifact gate

Use this gate when validating production-harness completeness. It uses the
published MEETI archive from Zenodo record `18523205` under the source access
and derivative-data terms, and writes all derived
artifacts under `data\` (gitignored). The extractor can use Windows `tar`
(`bsdtar`) or 7-Zip; prefer `--extractor tar` on the current Windows setup.

```bat
uv run --with scipy --with numpy python scripts\build-meeti-eval.py ^
  --rar MEETI.rar ^
  --output data\eval-datasets\meeti-1000-all ^
  --selection all ^
  --max-cases 1000 ^
  --min-cases 1000 ^
  --scan-limit 1000 ^
  --chunk 1000 ^
  --extractor tar

uv run python scripts\run-eval.py ^
  --manifest data\eval-datasets\meeti-1000-all\manifest-v2.json ^
  --mock --multi-pass --multi-pass-max-targets 3 ^
  --multi-pass-max-ekg-systematic-probes 2 --rhythm-strip-pass ^
  --analysis-prompt-profile clinical ^
  --require-perfect ^
  --output data\eval\meeti-v2-1000-mock-multipass-YYYYMMDD

uv run python scripts\export-eval-annotations.py ^
  --eval-dir data\eval\meeti-v2-1000-mock-multipass-YYYYMMDD ^
  --manifest data\eval-datasets\meeti-1000-all\manifest-v2.json

uv run python scripts\verify-eval-artifacts.py ^
  --eval-dir data\eval\meeti-v2-1000-mock-multipass-YYYYMMDD ^
  --manifest data\eval-datasets\meeti-1000-all\manifest-v2.json ^
  --min-cases 1000 --require-multipass-trace ^
  --require-multipass-refinement --require-ekg-systematic-probes ^
  --require-projection-audit --min-strict-pass-rate 1 ^
  --min-mean-partial-credit 1

uv run python scripts\check-real-model-readiness.py ^
  --model-id openai/gpt-5.4-mini ^
  --manifest data\eval-datasets\meeti-1000-all\manifest-v2.json ^
  --eval-dir data\eval\meeti-v2-1000-mock-multipass-YYYYMMDD ^
  --min-cases 1000 ^
  --probe-provider ^
  --output data\experiments\readiness-openai-gpt-5.4-mini.json
```

`run-eval.py` keeps console output bounded by default (`--case-print-limit 50`).
Use `--verbose` only for a short diagnostic subset. Avoid raw `tar -tf
MEETI.rar` or broad recursive searches over generated data/OpenClaw internals in
normal maintenance shells; they can flood PowerShell and obscure the useful
signal.

The 1000-case artifact verifier now requires two local, non-MLLM assist fields
in every raw result: `local_image_quality` (blank/low-signal preflight) and
`local_signal_candidates` (a deterministic threshold/ink bbox proposal for
ECG-like signal regions). These are not diagnostic outputs; they make input
quality and first-pass localization auditable before the MLLM interpretation.

`check-real-model-readiness.py` is the handoff from mock artifact completeness
to a real-model benchmark. It never prints or writes secret values. If the
required provider credential is absent, it writes `status=blocked` with a
machine-readable blocker (for OpenRouter, `OPENROUTER_API_KEY`) and exits
non-zero. Treat the JSON `status` field as the authoritative state; direct
`python` execution returns the script's blocked code, while some `uv run`
wrappers collapse non-zero exits to `1`. Once the key is present, the same
command returns `status=ready` and records the exact command to start the real
Gateway-backed experiment.

The last completed 2026-08-09 bundle contains OpenClaw `2026.7.1-2` and Node
`v24.18.0`; v0.4.7 retains those pins but still requires a clean full rebuild.
The requested benchmark model is selected explicitly with
`--model-id openai/gpt-5.4-mini`; the generated experiment config records the
`openai-vision` profile and `text,image` input metadata without mutating the
repo config. The desktop Settings dialog can also save OpenAI/OpenRouter
profiles without storing the secret in git. Always rerun config validation,
the image harness smoke, and readiness after changing providers or OpenClaw.

The release default remains `openai/gpt-5.4-mini`. The 2026-08-27 desktop
acceptance did not change it: that run used an explicit `openai-codex` model
override to select `openai/gpt-5.6-luna` on the OpenClaw-owned subscription
transport. Record the default and the override separately in every artifact;
an OAuth migration source is not evidence that Codex owned the agent loop.

Current local evidence (2026-08-27 release candidate):

- The packaged GUI ran on a 2560×1600 Windows display at 150% DPI with a
  credentialed local MEETI evaluation ECG visible in the viewer. The configured
  physical ROI was exactly
  `(19, 30, 1522, 1136)`. The app reached `DISPLAYING` and exported four
  diagnostic bboxes plus two analysis-crop outlines. External Windows capture
  excluded the top-most app panels as designed.
- Five OpenClaw-owned `gpt-5.6-luna` image turns completed in 146.915 seconds
  and recorded 111,833 total tokens. Subscription metering reported US$0;
  applying the [published Luna token prices](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
  to the same traffic gives an
  API-equivalent estimate of about US$0.017135.
- All projected bboxes were in bounds, had no clamping, and had at most 0.368
  physical-pixel edge drift. This is geometry evidence only. The interpretation
  was wrong: it reported sinus rhythm/possible LVH while the reference described
  atrial fibrillation with slow ventricular response, prolonged QT, poor R-wave
  progression, and nonspecific inferior ST-T changes. Preserve this as an
  accuracy miss; never relabel it as a successful medical read.
- The 10,001-identity scale/resume gate proves completed/pending partition
  completeness, disjointness, fingerprint rejection, and a sampled atomic disk
  checkpoint. It is not evidence that 10,001 clinical images were interpreted.
- The staged OpenClaw runtime is verified at 165.162 MiB, 19.804 MiB below the
  prior stage while retaining seven required templates and all internal `dist`
  chunks. The v0.4.7 complete bundle has not yet been rebuilt, so do not publish
  an estimated total size, file count, launcher hash, or packaged pass count.
- A later answer-free canary used seed `20260828`, one normal and one warning
  case, and a 1,222-ID exposure denylist. Both cases passed schema/bbox and all
  60/100/180-second SLA gates with zero parse retry or JSON repair. Aggregate
  strict was 0.5, mean partial credit 0.522, normal specificity 1.0, and mean
  latency 129,713.5 ms. The warning case reported abnormal R-wave progression
  and prominent anterior T waves but missed the weak-label LVH and asserted
  sinus-rhythm terms. Fifteen subscription transport requests recorded 73,528
  input, 11,142 output, 82,432 cache-read, 5,272 reasoning, and 167,102 total
  tokens (about US$0.02972464 API-equivalent; not an actual subscription charge).
  The source fingerprint was `dirty=true` because release metadata was being
  synchronized, so this is a pre-release bounded canary only.
- A fresh unseen canary against the final frozen source is still pending. Fill
  its case identity, latency, model receipt, score, and miss analysis here only
  after the artifacts pass verification.

Historical local evidence (2026-08-09):

- A frozen 32-case paired run completed with OpenClaw ownership and native
  `openai-chatgpt-responses` subscription transport. MultiPass raised mean
  weak-label partial credit from 0.253 to 0.480; paired bootstrap 95% CI was
  `[+0.085,+0.368]` and random-sign `p=0.00449955`. It caught 3/10 urgent
  concerns, so this is not a clinical-accuracy or safety claim.
- An 8-case unseen harness run completed 8/8 with no errors and passed schema,
  bbox, crop, projection, review-export and 60/100/180-second SLA gates. It
  retained two urgent misses. The artifacts include 8 marked review PNGs and
  30 exact crop PNGs.
- Ruff and the complete unit/smoke suite passed (`915 passed, 3 skipped`). The
  clean 368.01 MiB bundle then passed 4/4 opt-in packaged checks, native Windows
  capture exclusion and an isolated responsive GUI launch.
- A pre-publication 9,922-case launch was deliberately stopped after 289
  baseline results before committing the final source. Its state is
  `interrupted`; those results are launch/provenance evidence only. The
  post-publication root in section 2d is the only authoritative full run.

Historical local evidence (2026-08-05, Platform API route):

- The strict `manifest-v2.json` mock completed 1,000/1,000 with 4,869 analyzer
  calls, 2,869 source-image crops, 2,000 systematic probes, and 1,000 review
  PNGs. Its perfect score proves protocol plumbing, not model accuracy.
- The bbox audit contains 865 model boxes and 135 zero-box cases; all projected
  boxes passed round-trip calibration with zero clamps and 0 px maximum drift.
- The then-requested GPT-5.4 Mini MultiPass canary reached the first real OpenAI
  image request and returned `provider_credit_exhausted`. It is recorded as
  `blocked`, not as a wrong clinical answer.
- Full source verification is 769 passed and 2 release-only skips. The rebuilt
  frozen bundle also passed an authenticated Gateway cold-start, WebSocket
  connection, and clean-stop smoke.

Historical local evidence (2026-07-02):

- `node openclaw\node_modules\openclaw\openclaw.mjs config validate` passed
  against local OpenClaw `2026.6.11`.
- A generated OpenRouter config also passed `config validate` with
  `OPENROUTER_API_KEY` represented as an environment SecretRef.
- `uv run python scripts\run-image-harness-smoke.py --output data\harness-smoke\latest-openclaw-20260702`
  followed by `uv run python scripts\verify-image-harness.py ...` passed the
  desktop viewer, Gateway contract, image payload proof, overlay annotation,
  and harness manifest checks.
- The full MEETI source archive exposed 9922 PNG-bearing studies locally. A
  1000-case manifest was built from `MEETI.rar` at
  `data\eval-datasets\meeti-1000-all\manifest.json`.
- `uv run python scripts\run-eval.py --manifest data\eval-datasets\meeti-1000-all\manifest.json --mock --require-perfect --output data\eval\meeti-1000-mock-20260630-assist`
  completed 1000/1000 cases. The artifact verifier passed `min_cases`,
  `scorecard_complete`, `schema_gate`, `bbox_gate`, `cant_miss_gate`,
  `mock_perfect_gate`, `results_artifacts`, `local_preflight_artifacts`,
  `model_assist_artifacts`, and `review_artifacts`.
- `uv run python scripts\run-eval.py --gateway ws://127.0.0.1:18789 --dataset meeti --limit 10 --timeout-sec 90`
  completed 10 real GPT-5.5 cases without timeout or parser crash. It still did
  not reach perfect accuracy: schema pass was 90%, bbox in-bounds 100%,
  severity exact 70%, abnormal/normal 90%, mean keyword recall 37%.
- Real analysis requests use an isolated `analysis-<uuid>` Gateway `sessionKey`
  per image so one MEETI case cannot leak context into the next. Free-text chat
  keeps the default session behavior.
- The harness repairs one narrow class of malformed model JSON (`"x": 0.17"` in
  bbox numeric fields) before parsing. Broader schema failures remain visible in
  the scorecard and should be treated as model/prompt failures, not silently
  accepted results.

### 2d. Full MEETI real experiment runner

Use the paired supervisor for the reportable 9,922-case experiment. It runs two
arms in order from the same source/protocol fingerprint:

- `baseline`: minimal one-look prompt, no clinical skill, MultiPass,
  ECGFounder, rhythm pass or tools;
- `candidate`: clinical coarse read, source-pixel crop/refine, one systematic
  EKG probe, rhythm reconciliation and one matched-waveform ECGFounder call.

Both use the OpenClaw embedded agent, `openai/gpt-5.4-mini`, ChatGPT/Codex
subscription OAuth, `thinking=off`, per-turn `fastMode=true`, and a 180-second
case timeout. The gold manifest is not opened until saved inference is scored.
Do not commit, switch branches, edit scorer/harness files or rebuild in place
while either arm is running; a source change makes the pair non-comparable.
Changing this full-run model to Luna would create a different protocol
fingerprint and cost profile; do so only as a new explicitly named experiment,
not as an undocumented continuation of the GPT-5.4 Mini pair.

Before launch, confirm `codex login` is valid, AC sleep is disabled, the desired
commit is pushed, no other Gateway owns port 18789, and the old pre-publication
run is not alive. Then run:

```powershell
.venv\Scripts\python.exe scripts\run-meeti-paired-experiment.py `
  --manifest data\eval-datasets\meeti-blind-v1\full-9922.inference.json `
  --scoring-manifest data\eval-datasets\meeti-blind-v1\full-9922.gold.json `
  --output-root data\experiments\meeti-paired-full9922-v157-postpublish-v1 `
  --model-id openai/gpt-5.4-mini `
  --thinking-level off `
  --timeout-sec 180 `
  --fast-mode `
  --artifact-min-cases 9922 `
  --multi-pass-max-targets 2 `
  --multi-pass-max-ekg-systematic-probes 1 `
  --random-seed 20260809
```

`paired-experiment.json` is the authoritative live state. Do not infer completion
from process presence or a few result files. Useful read-only checks are:

```powershell
Get-Content data\experiments\meeti-paired-full9922-v157-postpublish-v1\paired-experiment.json
(Get-ChildItem data\experiments\meeti-paired-full9922-v157-postpublish-v1\baseline\eval\results -Filter *.json).Count
Get-Content data\experiments\meeti-paired-full9922-v157-postpublish-v1\supervisor.log -Tail 40
```

Restarting the same command against the same fingerprint resumes existing raw
results with `--resume --resume-retry-errors`. Auth/quota/model-catalog failure,
ownership drift, source mismatch or incomplete provenance records an
`interrupted`/blocked state instead of substituting a model or scoring a fake
clinical miss. A completed run contains both arms, comparison JSON/Markdown,
scorecards, provider logs, trajectories, review PNGs, crop files and coordinate
audits. At the measured candidate mean of 71.058 seconds, the sequential
candidate arm alone is roughly 196 hours, before baseline and post-processing.

The old root `meeti-paired-full9922-v157-20260809` stopped at 289 baseline
results to create a clean publication boundary. Never merge those partial rows
into the post-publication pair.

### 3. Read the scorecard

Artifacts land in `data\eval\<mode>-<timestamp>\`:

- `scorecard.json` -- aggregate metrics: severity accuracy (exact + abnormal/normal
  binary), mean finding-keyword recall, schema pass rate (via `OutputValidator`),
  normalized-bbox in-bounds rate, mean latency, strict pass rate, clinical
  partial-credit score, per-target-axis performance, and per-case breakdown.
- `scorecard.partial.json` -- checkpoint scorecard rewritten after each case.
  It includes `manifest_total`, `result_count`, `is_partial`, `updated_at`, and
  `aborted_reason` when the run stops early. This is the live-progress artifact
  to inspect during long MEETI runs.
- `results\<case>.json` -- the full raw `AnalysisResult` for each image.
  Error cases also get a result artifact so raw-result counts stay auditable.
- `multipass-trace.jsonl` -- present only for `--multi-pass`; one JSON line per
  image proving how many OpenClaw `analyze` calls and crop/refine passes ran.

The console prints a per-case `OK/MISS/ERR` table and the aggregate summary.

Clinical partial credit is intentionally separate from parser/transport quality.
The current weights are:

- 30% abnormal-vs-normal severity group
- 20% exact severity
- 35% positive keyword recall
- 15% pertinent-negative recall

Asserted reference concepts drive strict, cannot-miss and urgent metrics. For
an incomplete weak report only, an explicitly uncertain, non-negated
differential can match a candidate concept at half weight. Candidate credit is
reported separately and can never satisfy a strict/safety gate. Explicit
normal/within-range cases may correctly produce zero abnormal findings; the
harness does not force a diagnosis merely to fill the schema.

The pertinent-negative component is included only when a case actually has
expected negatives, so abnormal cases without negatives no longer receive free
credit. Missed can't-miss labels cap partial credit at 0.40. Schema pass rate,
bbox in-bounds rate, bbox low-signal audit, latency, and OpenClaw call counts
remain separate operational/harness metrics.

Positive keyword recall is negation-aware: a statement such as `no ischemia`
does not satisfy an expected positive `ischemia` label. The eval schema gate also
treats `OutputValidator` warnings/incomplete results (for example missing EKG
16-key checklist entries) as `schema_ok=false`, so strict pass cannot be earned
with an incomplete structured read.

Gateway infrastructure failures fail fast after repeated consecutive connection
errors (default 5) instead of filling the remaining manifest with hundreds of
fake model failures. Such runs are marked partial/aborted and are rejected by
the comparator unless explicitly run with `--allow-incomplete`.

### 3b. Compare the four paired arms

The controlled experiment should use the same model, same MEETI manifest, same
OpenClaw runtime, same scoring code, and differ only by the app interpretation
path:

- No-harness control: `minimal_control`.
- Clinical prompt/schema effect: `single_pass` versus `minimal_control`.
- Crop/refine/tool effect: `multipass` versus `single_pass`.
- Waveform evidence effect: `multipass_ecgfounder` versus `multipass`.

After each pair has complete `scorecard.json` artifacts, compare case-by-case.
For example, isolate the MultiPass effect with:

```bat
uv run python scripts\compare-eval-runs.py ^
  --baseline data\experiments\gpt54mini-single-pass ^
  --candidate data\experiments\gpt54mini-multipass
```

By default the comparator rejects incomplete/error scorecards (`error_count > 0`,
`scored != total`, stale raw-result counts, or `is_partial=true`). For
in-progress exploratory checks only, add `--allow-incomplete`; the report will
exclude error cases and mark the comparison as incomplete. It also rejects
different manifests/case sets, scorer digests, or mixed protocol provenance;
`--allow-incompatible` is only for an explicitly exploratory report.

If a run was produced before the scorecard schema gained partial-credit fields,
or if you want a partial summary from already-written `results/*.json` while a
long run is still in progress, rebuild a scorecard without rerunning the model:

```bat
uv run python scripts\rebuild-eval-scorecard.py ^
  --eval-dir data\experiments\gpt54mini-multipass\eval ^
  --manifest data\eval-datasets\meeti-1000-all\manifest-v2.json
```

Then compare against the rebuilt JSON explicitly:

```bat
uv run python scripts\compare-eval-runs.py ^
  --baseline data\experiments\gpt54mini-single-pass\eval\scorecard.json ^
  --candidate data\experiments\gpt54mini-multipass\eval\scorecard.rebuilt.json
```

Outputs:

- `comparison\comparison.json` -- paired metrics, per-case deltas, cost, bbox QA
  summaries, and exact two-sided paired sign-test p-value.
- `comparison\comparison.md` -- human-readable top improvements/regressions.

Key comparison fields:

- `strict_pass_rate_delta`
- `partial_credit_delta` / `paired_mean_partial_credit_delta` (paired cases only)
- `aggregate_partial_credit_delta` (whole-scorecard means; only compare this when
  both runs cover the same case set)
- `keyword_recall_delta`
- `case_status_counts`
- `paired_sign_test.two_sided_p`
- candidate `mean_openclaw_analyze_calls`, `mean_zoom_passes`, `mean_crop_calls`

### 4. Export marked images for expert review

After any eval run has produced `results/*.json`, export annotated PNGs that
combine the source image, model bboxes, numbered markers, and a right-side
description panel:

```bat
uv run python scripts\export-eval-annotations.py ^
  --eval-dir data\experiments\gpt54mini-multipass\eval ^
  --manifest data\eval-datasets\meeti-1000-all\manifest-v2.json
```

Outputs:

- `review\<case>.review.png` -- original image plus AI bbox markers and finding
  descriptions. Low-signal boxes are cross-marked and listed in the side panel
  with pixel coordinates and ink ratio, so blank/irrelevant bboxes are visible
  during expert review.
- `review\bbox-audit.jsonl` -- one JSON line per bbox with normalized
  coordinates, clamped normalized coordinates, original-image pixel coordinates,
  crop path, ink-pixel ratio, `low_signal`, `was_clamped`, and
  `invalid_reason`.
- `review\crops\<case>-fNN-bNN.png` -- the exact image crop inside each bbox,
  upscaled only for review readability.
- analysis/probe regions are shown as dashed cyan boxes and exported separately
  from solid diagnostic finding boxes, preventing a crop target from being
  mistaken for a model diagnosis.
- `review\index.html` -- clickable table for manual review.

The exporter cleans generated review PNGs/crops by default before rewriting the
index, so stale review files do not masquerade as current results. Use
`--no-clean` only when intentionally preserving older generated artifacts. Use
`--limit N` while a long run is still in progress, then rerun without `--limit`
after the experiment completes.

### 5. Rebuild and verify the frozen desktop

```powershell
scripts\build-exe.bat
$env:RUN_BUNDLE_SMOKE = "1"
$env:RUN_GATEWAY_BUNDLE_SMOKE = "1"
uv run pytest tests\smoke\test_packaging_bundle.py -q
```

This runs the source self-check, the real frozen EXE self-check, and an isolated
Gateway smoke that creates a runtime-only loopback token, waits for first-run
migrations, authenticates over WebSocket, stops OpenClaw, and checks that port
18789 is closed. It does not send a model request. Desktop startup allows 180
seconds for Gateway readiness independently of the per-inference timeout.

For v0.4.7, do not copy the previous full-bundle numbers into release notes.
After the clean rebuild, require `bundle-manifest.json` to report `status=ok`,
the exact frozen release commit, `git_dirty=false`, OpenClaw `2026.7.1-2`,
harness/plugin `1.5.8`, seven non-empty hashed workspace templates, and empty
sensitive/residue/banned-content scans. Until that completes, the only current
packaging measurement is the verified 165.162 MiB staged OpenClaw runtime and
its conservative 19.804 MiB reduction.
