# Verification Record - 2026-08-05

This is the current evidence ledger for the MultiPass ECG harness and portable
desktop build. It deliberately separates protocol execution from real-model
accuracy: a perfect mock run proves the pipeline and gates, not that an LLM
answered the clinical cases correctly.

## Status Matrix

| Surface | Status | Evidence |
| --- | --- | --- |
| Unit + smoke suite | passed | 769 passed, 2 release-only skips |
| Ruff and whitespace gates | passed | `ruff check .`, `git diff --check` |
| MEETI strict mock protocol | passed | 1,000/1,000, 0 errors, all strict artifact gates |
| MultiPass execution proof | passed | 4,869 analyze calls, 2,869 crops, 2,000 systematic probes |
| Expert-review exports | passed | 1,000 annotated PNGs and 1,000 bbox audit rows |
| Coordinate projection | passed | 865 boxes, 0 failures/clamps, 0 px max drift |
| Requested real model canary | blocked | `openai/gpt-5.4-mini` reached the provider and exhausted credits |
| Full real four-arm accuracy | not established | No model response is counted from a quota failure |
| Portable bundle | passed | self-check, native tools, authenticated Gateway smoke, clean stop |

## MEETI Protocol Proof

The current strict mock artifact is:

```text
data/eval/meeti-v2-1000-mock-multipass-protocolfix-20260805
```

It uses `manifest-v2.json`, the clinical prompt profile, `MultiPassAnalyzer`,
three bounded refinement targets, two EKG systematic probes, and the rhythm
strip pass. Results were 1,000 scored cases, zero errors, strict pass 1.0, mean
partial credit 1.0, schema pass 1.0, bbox in-bounds 1.0, and 32/32 urgent
concerns surfaced. Protocol digest:
`f739e19bdc3cbb9b2528edaca08234cbd9e204dd4d3bd33af84a3df252b9d0f9`.
Scorer digest:
`4a49fc0dac92ed74d433e45c26a7f5a9deb8b735c312afcb9a4aebdac2994d69`.

The trace contains 2,000 rows for 1,000 cases:

- 1,000 coarse image reads.
- 3,869 follow-up/zoom reads.
- 2,869 source-ROI crop calls.
- 2,000 completed limb/precordial systematic discovery probes.
- 4,869 total analyzer calls.

The strict verifier passed protocol fingerprint, completeness, schema, bbox,
urgent concern, mock-perfect, strict/partial thresholds, local preflight,
model assist, raw results, MultiPass trace/refinement, systematic probes,
review export, and coordinate projection gates.

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
data/experiments/readiness-openai-gpt-5.4-mini-protocolfix-20260805.json
```

It confirms the 1,000-case manifest, all strict mock artifacts, OpenClaw
`2026.7.1-2`, credential presence, provider metadata, and advertised image
input. Static readiness explicitly records `provider_transaction_tested=false`.

The current real canary is:

```text
data/experiments/gpt54mini-multipass-canary-protocolfix-20260805
```

It records `openai/gpt-5.4-mini`, `experiment_arm=multipass`, clinical prompt,
rhythm-strip pass, three refinement targets, two systematic-probe slots, and
protocol digest
`713db3b705373f3684f906aae01e21e0e367e036bc4f6df34ad9057ef401a86f`.
The isolated Gateway became ready in 88.384 seconds and the model catalog
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

## Review and Coordinates

The export contains 1,000 `*.review.png` files. Its 1,000 audit rows cover 865
bboxes and 135 zero-bbox cases. All 865 normalized-to-pixel-to-normalized
round trips passed, none were clamped, and maximum edge drift was 0 px. The
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
- Source commit: `6debf5997861a3396a5fe1cac92fede71b8c1dd3`
- Source dirty: false
- EXE SHA-256:
  `aa6d9284df7ef6738319e853495cca537014269f62a1f424f371f61a0342e43b`
- Payload-tree SHA-256:
  `1ec551a132ebe6ed078c6735b2589e37632b54d85a301a899349946fb3917370`
- Source-tree SHA-256:
  `028094520b9c7d612111c780096bc6d5ff77761cfb7d806dfb44332ae91930b4`
- OpenClaw `2026.7.1-2`; Node `v24.18.0`
- 381,596,178 bytes, 363.92 MiB, 15,226 payload files
- Launcher 6.96 MiB; app layer 94.64 MiB; OpenClaw 181.03 MiB; Node 88.25 MiB

The manifest has zero missing, banned, residue, diagnostic, or failure rows.
Both native tools loaded at runtime. The frozen release tests passed 3/3:
source self-check, real EXE self-check, and an isolated authenticated Gateway
smoke. The frozen smoke copied the bundle, generated a local loopback token,
started OpenClaw, completed a WebSocket handshake, stopped it, and verified
port 18789 had no remaining listener. No model request was made.

The desktop now displays `AI starting`, `AI ready`, or `AI offline` separately
from the clinical workflow state. First-run OpenClaw migration runs on the
AsyncBridge with a bounded 180-second budget, so the Qt UI appears immediately.
The token is generated at first runtime in `.env`; the clean release contains
no `.env`, logs, state database, waveform, MEETI data, Torch, sidecar, or model
checkpoint.

## Reproduction

```bat
uv run python scripts\run-eval.py ^
  --manifest data\eval-datasets\meeti-1000-all\manifest-v2.json ^
  --mock --multi-pass --multi-pass-max-targets 3 ^
  --multi-pass-max-ekg-systematic-probes 2 --rhythm-strip-pass ^
  --analysis-prompt-profile clinical --require-perfect ^
  --output data\eval\meeti-v2-1000-mock-multipass-protocolfix-20260805

scripts\run-meeti-openclaw-experiment.cmd ^
  --model-id openai/gpt-5.4-mini ^
  --manifest data\eval-datasets\meeti-1000-all\manifest-v2.json ^
  --multi-pass --multi-pass-max-targets 3 ^
  --multi-pass-max-ekg-systematic-probes 2
```

After credits are restored, run all four arms against the same manifest and
scorer digest, verify every artifact gate, export review PNGs, and then use
`scripts/compare-eval-runs.py` for the paired result.
