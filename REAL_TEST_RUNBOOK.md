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
4. At least one model credential available in the shell before launch:
   - `ANTHROPIC_API_KEY`
   - or `OPENAI_API_KEY`
   - or `OPENROUTER_API_KEY`
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

### 2b. Real model benchmark (token required)

```bat
set ANTHROPIC_API_KEY=...        REM in your shell, never in code or git
REM start the gateway first (see "Start the gateway" above)
uv run python scripts\run-eval.py --gateway ws://127.0.0.1:18789
```

For the prepared MEETI ECG dataset, use the dataset selector and the strict
"all cases must pass" gate:

```bat
uv run python scripts\run-eval.py --mock --dataset meeti --require-perfect
uv run python scripts\run-eval.py --gateway ws://127.0.0.1:18789 --dataset meeti --timeout-sec 90 --require-perfect
```

Use `--limit N` while iterating on prompts or scorer behavior, for example:

```bat
uv run python scripts\run-eval.py --gateway ws://127.0.0.1:18789 --dataset meeti --limit 10 --timeout-sec 90 --require-perfect
```

To test the real app multi-pass path (coarse read -> crop suspicious regions ->
refine), add `--multi-pass`. `--multi-pass-max-targets` caps the number of
crop/refine passes per image, controlling latency and cost:

```bat
uv run python scripts\run-eval.py --mock --dataset meeti --multi-pass --multi-pass-max-targets 2 --require-perfect
uv run python scripts\run-eval.py --gateway ws://127.0.0.1:18789 --dataset meeti --multi-pass --multi-pass-max-targets 2 --timeout-sec 90 --require-perfect
```

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
public MEETI archive from Zenodo record `18523205` and writes all derived
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

The clean bundle currently contains OpenClaw `2026.7.1-2` and Node `v24.18.0`.
The requested benchmark model is selected explicitly with
`--model-id openai/gpt-5.4-mini`; the generated experiment config records the
`openai-vision` profile and `text,image` input metadata without mutating the
repo config. The desktop Settings dialog can also save OpenAI/OpenRouter
profiles without storing the secret in git. Always rerun config validation,
the image harness smoke, and readiness after changing providers or OpenClaw.

Current local evidence (2026-08-05):

- The strict `manifest-v2.json` mock completed 1,000/1,000 with 4,869 analyzer
  calls, 2,869 source-image crops, 2,000 systematic probes, and 1,000 review
  PNGs. Its perfect score proves protocol plumbing, not model accuracy.
- The bbox audit contains 865 model boxes and 135 zero-box cases; all projected
  boxes passed round-trip calibration with zero clamps and 0 px maximum drift.
- The requested GPT-5.4 Mini MultiPass canary reached the first real OpenAI
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

Use this wrapper when the goal is to leave a reproducible experiment record. It
does not mutate `openclaw\openclaw.json`; instead it writes an experiment-local
OpenClaw config, starts the Gateway with that config, runs `run-eval.py`, then
stores the console logs, model catalog, config, scorecard, raw per-case results,
review PNGs, bbox audit/crops, rebuilt scorecard, and `experiment.json` under
`data\experiments\`. New runs write `experiment.json` with `status=running`
before model evaluation starts, then update it in `finally`.

Run all four arms with the same model and immutable `manifest-v2.json`. Use
distinct output directories and do not use `-RequirePerfect` for a real-model
study; the runner's default completion gates are strict pass >= 0.75 and mean
partial credit >= 0.85.

```powershell
# Arm 1: one-look minimal control, no clinical harness or tools
powershell -ExecutionPolicy Bypass -File scripts\run-meeti-openclaw-experiment.ps1 `
  -ModelId openai/gpt-5.4-mini `
  -ManifestPath data\eval-datasets\meeti-1000-all\manifest-v2.json `
  -ExperimentDir data\experiments\gpt54mini-minimal-control `
  -TimeoutSec 180 `
  -AnalysisPromptProfile minimal_control

# Arm 2: clinical prompt/schema, exactly one image pass
powershell -ExecutionPolicy Bypass -File scripts\run-meeti-openclaw-experiment.ps1 `
  -ModelId openai/gpt-5.4-mini `
  -ManifestPath data\eval-datasets\meeti-1000-all\manifest-v2.json `
  -ExperimentDir data\experiments\gpt54mini-single-pass `
  -TimeoutSec 180

# Arm 3: clinical MultiPass with crops, probes, rhythm pass, reconciliation
powershell -ExecutionPolicy Bypass -File scripts\run-meeti-openclaw-experiment.ps1 `
  -ModelId openai/gpt-5.4-mini `
  -ManifestPath data\eval-datasets\meeti-1000-all\manifest-v2.json `
  -ExperimentDir data\experiments\gpt54mini-multipass `
  -TimeoutSec 180 `
  -MultiPass `
  -MultiPassMaxTargets 3 `
  -MultiPassMaxEkgSystematicProbes 2

# Arm 4: identical MultiPass path plus matched ECGFounder waveform evidence
powershell -ExecutionPolicy Bypass -File scripts\run-meeti-openclaw-experiment.ps1 `
  -ModelId openai/gpt-5.4-mini `
  -ManifestPath data\eval-datasets\meeti-1000-all\manifest-v2.json `
  -ExperimentDir data\experiments\gpt54mini-multipass-ecgfounder `
  -TimeoutSec 180 `
  -MultiPass `
  -MultiPassMaxTargets 3 `
  -MultiPassMaxEkgSystematicProbes 2 `
  -EcgFounderWaveformEvidence
```

If a requested model id is absent from the effective OpenClaw catalog, or the
provider rejects authentication/quota, the runner records a blocked experiment
instead of silently substituting a model or scoring an infrastructure failure.
Every arm records `experiment_arm`, prompt profile, tool policy, protocol/scorer
digests, raw results, traces, review PNGs, bbox audits, logs, and timing.

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
