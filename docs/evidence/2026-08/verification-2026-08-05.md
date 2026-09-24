# Verification Record - 2026-08-05

> Historical ledger. Its dated Platform API blocker and bundle sizes are
> superseded by [the 2026-08-09 subscription/OpenClaw record](meeti-openclaw-experiments-2026-08-09.md);
> the original evidence below is intentionally preserved.

This is the dated evidence ledger for the 2026-08-05 MultiPass ECG harness and portable
desktop build. It deliberately separates protocol execution from real-model
accuracy: a perfect mock run proves the pipeline and gates, not that an LLM
answered the clinical cases correctly.

## Status Matrix

| Surface | Status | Evidence |
| --- | --- | --- |
| Unit + smoke suite | passed | 791 passed, 3 opt-in release/native skips |
| OpenClaw integration | passed | 55 passed |
| Native Windows capture exclusion | passed | rendered overlay excluded; underlay remained visible |
| Ruff, typing, and whitespace gates | passed | Ruff; mypy 63 source files; `git diff --check` |
| MEETI strict mock protocol | passed | 1,000/1,000, 0 errors, all strict artifact gates |
| MultiPass execution proof | passed | 4,869 analyze calls, 2,869 crops, 2,000 systematic probes |
| Expert-review exports | passed | 1,000 annotated PNGs and 1,000 bbox audit rows |
| Coordinate projection | passed | 865 boxes, 0 failures/clamps, 0 px max drift |
| Requested real model canary | blocked | `openai/gpt-5.4-mini` reached the provider and exhausted credits |
| ECGFounder waveform arm | passed with exclusion | 1,000 traversed; 999 eligible; one flat V5 rejected |
| Full real four-arm accuracy | not established | No model response is counted from a quota failure |
| Portable bundle | passed | self-check, native tools, authenticated Gateway smoke, clean stop |

## MEETI Protocol Proof

The current strict mock artifact is:

```text
data/eval/meeti-v2-1000-mock-multipass-evidencev3-20260805
```

It uses `manifest-v2.json`, the clinical prompt profile, `MultiPassAnalyzer`,
three bounded refinement targets, two EKG systematic probes, and the rhythm
strip pass. Results were 1,000 scored cases, zero errors, strict pass 1.0, mean
partial credit 1.0, schema pass 1.0, bbox in-bounds 1.0, and 32/32 urgent
concerns surfaced. Formal scoring uses the 299 asserted-reference cases;
the other 701 weak-label cases remain exploratory. The formal set includes 244
diagnosis-scorable cases, 14 single-diagnosis cases, 156 cases with 3-5
diagnoses, and 49 explicit-normal controls. Protocol digest:
`9408a14215dda71722bcc8418340b4a3c752dbb65908b1efc2ad0d0c50bd3dd4`.
Scorer digest:
`1eb15b36c6f6a08a9d326e71cd705b08b27463e2b956e11b468a104bbc017776`.
The source identity is commit `43c7fc7`, scoped to the code, skills, rules,
plugin, ECGFounder sidecar, and evaluation scripts that can affect the run;
both scoped status/diff hashes are empty and `source.dirty=false`.

The trace contains 2,000 rows for 1,000 cases:

- 1,000 coarse image reads.
- 3,869 follow-up/zoom reads.
- 2,869 source-ROI crop calls.
- 2,000 completed limb/precordial systematic discovery probes.
- 4,869 total analyzer calls.

The strict verifier passed 18 gates: protocol fingerprint, case completeness,
schema, bbox, can't-miss, urgent concern, mock-perfect, strict/partial
thresholds, local preflight, model assist, raw results, MultiPass trace and
refinement, systematic probes, review export, and coordinate projection.

This mock deliberately returns label-derived structured answers and synthetic
tool receipts marked `source=mock_protocol_selftest`. Its 1.0 scores are a
pipeline invariant. They are not GPT-5.4-mini accuracy and are never compared
as if they were a model arm.

## Normal ECG Handling

The harness does not require an abnormal finding. A reference case can be
normal or within normal limits, and a schema-valid result with no abnormal
findings is accepted. False-positive concepts on explicitly normal controls
are penalized separately. The scorer now suppresses only a shorter phrase that
is wholly contained in an expected longer phrase; an independent extra claim,
such as a T-wave abnormality, remains a false positive.

Quality and safety are separate gates. A completed real run requires at least
0.75 strict pass rate and 0.85 mean clinical partial credit. Transport,
provider, parser, and missing-artifact errors remain infrastructure failures
and cannot be converted into clinical misses or partial credit.

## Real GPT-5.4-mini State

Static readiness is recorded at:

```text
data/experiments/readiness-openai-gpt-5.4-mini-evidencev3-20260805.json
```

It confirms the 1,000-case manifest, all strict mock artifacts, OpenClaw
`2026.7.1-2`, credential presence, provider metadata, and advertised image
input. Static readiness explicitly records `provider_transaction_tested=false`.

The current real canary is:

```text
data/experiments/gpt54mini-multipass-canary-evidencev3-20260805
```

It records `openai/gpt-5.4-mini`, `experiment_arm=multipass`, clinical prompt,
rhythm-strip pass, three refinement targets, two systematic-probe slots, and
protocol digest
`8f5b2850b84fde9f251d91271d2a622aa5545b656e713469d7870cf9bb2d9f0f`.
The isolated Gateway became ready in 72.359 seconds and the model catalog
declared `text,image`. The first coarse call attached the case image and reached
OpenAI, which returned `provider_credit_exhausted`. The run therefore records
`status=blocked`, exit 20, one error artifact, one analyze attempt, zero crops,
and no scored model answer.

No full real MEETI result, accuracy percentage, or significant improvement is
claimed until provider credits permit all paired arms to finish.

## Controlled Experiment

The runner now distinguishes four paired arms:

1. `minimal_control`: one image look, minimal JSON envelope, no clinical skill,
   tool, crop, rhythm pass, or MultiPass behavior.
2. `single_pass`: the clinical harness and schema, exactly one image pass, no
   crop/refine or rhythm pass.
3. `multipass`: clinical coarse read, source-image crops, refinement,
   systematic lead probes, rhythm pass, and final report reconciliation.
4. `multipass_ecgfounder`: the same MultiPass path plus exactly one verified
   matched-waveform ECGFounder receipt per case.

The comparator rejects different manifests, case sets, scorer digests, or
non-comparable protocol fingerprints by default. `--allow-incompatible` is
available only for explicitly exploratory analysis. This separates prompt
benefit, MultiPass benefit, and waveform-tool benefit instead of calling every
difference a harness gain.

Clinical partial credit remains separate from strict correctness: 30% severity
group, 20% exact severity, 35% positive-concept recall, and 15% pertinent
negative recall when negatives exist. A missed can't-miss concept caps the
case at 0.40. Paired comparison reports exact wins/losses/ties, partial-credit
deltas, urgent recall, error counts, latency/call costs, and the two-sided
paired sign test.

## MultiPass and Tools

Per image, the app records the coarse read, local image-quality and signal
assist, typed 12-lead inventory, evidence-backed crops, layout-derived limb and
precordial probes, refinement results, bbox calibration, and final report
reconciliation. A completed refinement turn with no finding delta still runs
finalization, so a no-change crop cannot silently bypass report synthesis.

OpenClaw has a bounded tool surface. Web search/fetch are disabled for image
analysis. `dicom_bbox_validate` records coordinate/tool receipts.
`ecg_founder_analyze_waveform` is registered only when an authenticated
loopback sidecar is configured. Traces retain stages, decisions, tool names,
receipts, crop coordinates, and provenance; hidden chain-of-thought is neither
requested nor stored.

ECGFounder is an external waveform classifier, not an ECG screenshot model.
The official MIT-licensed repository supplies 1-lead and 12-lead PyTorch
checkpoints and requires its exact filtering and z-score preprocessing. The
Hugging Face repository is about 740 MB and has no hosted inference provider.
The app therefore keeps Torch/checkpoints outside the portable bundle and
passes only a registered opaque raw-waveform artifact id to the sidecar. It
cannot infer a waveform from a PNG or provide image bboxes.

The current pinned v3 batch is:

```text
data/eval-runs/ecgfounder-meeti-1000-v3-20260805
```

It traversed all 1,000 registered waveforms sequentially on CPU in 555.086
seconds. Input-quality gates accepted 999 (99.9%). Case `meeti_49913643` was
retained as `ineligible` because raw lead V5 is exactly flat (all zero); the
runner did not manufacture a prediction. The eligibility-aware evaluator is
opt-in (`--allow-ineligible`), validates complete cohort traversal and exact
status counts, and reports the exclusion instead of silently dropping it.

On the 999 eligible weak-label cases, 5-fold out-of-fold research evaluation
across 23 sufficiently supported mapped concepts produced macro balanced
accuracy 0.865, sensitivity 0.847, and explicit-normal-control specificity
0.883. Holdout top-20 mapped-concept recall was 0.837; complete recall for
3-5-diagnosis cases was 0.479. These values describe ECGFounder waveform
ranking only. They are not screenshot-agent accuracy, spatial localization, or
deployment calibration.

## Review and Coordinates

The export contains 1,000 `*.review.png` files (234,401,879 bytes). Its 1,000
audit rows cover 865
bboxes and 135 zero-bbox cases. All 865 normalized-to-pixel-to-normalized
round trips passed; none were clamped, invalid, or low-signal, and maximum edge
drift was 0 px. The
review panel includes finding descriptions, exact pixels, crop paths, local
signal audit, and reviewer question/answer text for manually drawn regions.

Reviewer-confirmed `ADD`, `REVISE`, and `RETRACT` now rebuild summary and
triage, retain the prior safety floor, mark the initial checklist as requiring
reconciliation, and preserve before/after provenance in JSON and the Process
view. Lead names such as `I`, `II`, and `V1` share one canonical parser across
MultiPass, bbox calibration, schema validation, and UI inventory reporting.

## Portable Bundle

Final artifact:

- Path: `dist/DICOMOverlayAgent/DICOMOverlayAgent.exe`
- Source commit: `1d73a9c911263a358ee1ccc05606c65e4b6a0350`
- Source dirty: false
- EXE SHA-256:
  `444b99d4614f1f5f4616118f1c0ac35f35f9a79c15b24bc8366f60a13170a24d`
- Payload-tree SHA-256:
  `cd879e9cd2ce2d204d8cd9178dfeba9517ac6139a7413f0d9b3a0ece633b1494`
- Source-tree SHA-256:
  `6a55715f5c774e285e3d6d145abedb01077662c830ebf7cde9b988781270769c`
- OpenClaw `2026.7.1-2`; Node `v24.18.0`
- 381,618,986 bytes, 363.94 MiB, 15,226 payload files
- Launcher 6.97 MiB; app layer 94.66 MiB; OpenClaw 181.04 MiB; Node 88.25 MiB

The manifest has zero missing, banned, residue, diagnostic, or failure rows.
Both native tools loaded at runtime. The frozen release tests passed 4/4:
source self-check, verifier self-check, real EXE self-check, and an isolated
authenticated Gateway smoke (4/4). The frozen smoke copied the bundle,
generated a local loopback token,
started OpenClaw, completed a WebSocket handshake, stopped it, and verified
port 18789 had no remaining listener. No model request was made.

The native harness plugin is version 1.2.0. Source and bundled `index.js` share
SHA-256 `01e1128c09f7d7e98c37e00dc56f6a37f840208824e98b7348ffd0b3fcf8c022`;
runtime inspection loaded `dicom_bbox_validate` and
`ecg_founder_analyze_waveform` with no diagnostics. Direct frozen-PYZ inspection
found `openai-vision`, `openai/gpt-5.4-mini`, `gpt-5.4-mini`, and the GPT-5.4
Mini UI label in `openclaw_settings`, plus the screen-selection and projection
modules. The shipped `config.yaml` has `phi_roi.configured=false`.

The desktop now displays `AI starting`, `AI ready`, or `AI offline` separately
from the clinical workflow state. First-run OpenClaw migration runs on the
AsyncBridge with a bounded 180-second budget, so the Qt UI appears immediately.
The token is generated at first runtime in `.env`; the clean release contains
no `.env`, logs, state database, waveform, MEETI data, Torch, sidecar, or model
checkpoint.

The pinned npm tree currently reports 7 moderate and 4 high transitive
advisories, 0 critical. No automatic breaking `npm audit fix --force` was
applied during this release build.

## Reproduction

```bat
uv run python scripts\run-eval.py ^
  --manifest data\eval-datasets\meeti-1000-all\manifest-v2.json ^
  --mock --multi-pass --multi-pass-max-targets 3 ^
  --multi-pass-max-ekg-systematic-probes 2 --rhythm-strip-pass ^
  --analysis-prompt-profile clinical --require-perfect ^
  --output data\eval\meeti-v2-1000-mock-multipass-evidencev3-20260805

uv run python scripts\evaluate-ecgfounder-meeti.py ^
  --run-dir data\eval-runs\ecgfounder-meeti-1000-v3-20260805 ^
  --allow-ineligible

scripts\run-meeti-openclaw-experiment.cmd ^
  --model-id openai/gpt-5.4-mini ^
  --manifest data\eval-datasets\meeti-1000-all\manifest-v2.json ^
  --multi-pass --multi-pass-max-targets 3 ^
  --multi-pass-max-ekg-systematic-probes 2
```

After credits are restored, run all four arms against the same manifest and
scorer digest, verify every artifact gate, export review PNGs, and then use
`scripts/compare-eval-runs.py` for the paired result.
