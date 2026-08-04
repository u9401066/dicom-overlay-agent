# ECGFounder External Tool Contract

## Decision

ECGFounder is integrated as an optional, local waveform-evidence tool for
OpenClaw. It is not an image model and its Torch runtime or checkpoints are not
bundled in `DICOMOverlayAgent.exe`.

The current trusted artifact binding exists in the evaluation runner, where a
manifest explicitly pairs one image with one registered waveform. The desktop
capture flow does not yet have a trusted study-to-waveform resolver and does
not invoke ECGFounder for screenshot-only analysis. Its Settings status is
therefore informational and says `Evaluation sidecar configured`.

The native harness plugin registers `ecg_founder_analyze_waveform` only when
both variables are present in the Gateway environment:

```text
DICOM_ECGFOUNDER_ENDPOINT=http://127.0.0.1:18790/v1/analyze
DICOM_ECGFOUNDER_TOKEN=<random local bearer token>
```

`DICOM_ECGFOUNDER_TIMEOUT_MS` optionally sets a 1,000-120,000 ms timeout.
`DICOM_ECGFOUNDER_AUDIT_PATH` controls the PHI-free JSONL receipt path.

The endpoint must be loopback HTTP. The plugin rejects remote hosts, URL
credentials, arbitrary file paths, oversized responses, unpinned checkpoints,
and image-only input claims.

## Why It Is Optional

The official artifacts are waveform classifiers:

- 12-lead and single-lead PyTorch checkpoints are about 370 MB each.
- The official 12-lead validation path uses a 10-second, 500 Hz input with
  5,000 points per lead and a 150-class sigmoid output.
- The local sidecar requires Torch, NumPy, and SciPy. Bundling that stack would
  violate the desktop bundle size target and make legacy Windows support much
  harder.
- Hugging Face does not currently expose this repository through a hosted
  inference provider.

Official sources:

- Model card and weights: <https://huggingface.co/PKUDigitalHealth/ECGFounder>
- Official code: <https://github.com/PKUDigitalHealth/ECGFounder>
- Published article: <https://pmc.ncbi.nlm.nih.gov/articles/PMC12327759/>
- Upstream software license: MIT

Pinned weight hashes visible in the official Hugging Face repository:

| Checkpoint | SHA-256 |
|---|---|
| `12_lead_ECGFounder.pth` | `ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997` |
| `1_lead_ECGFounder.pth` | `f863a38897fb49a27fec7e44008ea3c7bdbd29c77fa4a02ecbb8c56df4f37603` |

The upstream files are PyTorch pickle checkpoints. This sidecar verifies the
expected SHA-256 before loading, runs in a separate process, and uses
`torch.load(..., weights_only=True)`. The small set of globals reported by the
upstream checkpoint safety scan is temporarily allowlisted and cleared
immediately after loading; there is no unsafe pickle fallback.

## Reproducible Local Setup

The setup script creates an isolated Python 3.11 environment under ignored
`data/external/`. It tries the official Hugging Face endpoint first. A currently
working mirror address can be supplied as a transport fallback, but the file is
never installed unless the pinned SHA-256 matches.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/setup-ecgfounder-sidecar.ps1

$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$env:DICOM_ECGFOUNDER_TOKEN = [Convert]::ToBase64String($bytes)
$env:DICOM_ECGFOUNDER_ENDPOINT = "http://127.0.0.1:18790/v1/analyze"

scripts/start-ecgfounder-sidecar.cmd
```

Use the same endpoint and token in the shell that starts the desktop app or
OpenClaw experiment. The sidecar runs in the foreground so lifecycle and logs
remain visible.

`GET /health` reports `configured` without loading the model. Authenticated
`GET /health?deep=1` verifies and loads the pinned checkpoint and reports
`ready`; model-load failures return HTTP 503 with a bounded reason.

## Input Boundary

The agent sends only:

```json
{
  "schema_version": 1,
  "artifact_id": "opaque-artifact-id",
  "lead_mode": "12_lead",
  "evidence_nonce": "32-lowercase-hex-characters",
  "max_predictions": 10
}
```

The sidecar owns a trusted artifact registry and resolves the opaque id. The id
must not be a path and must not contain PHI.

`evidence_nonce` is generated afresh by the app for one analysis binding. It is
not clinical data and does not select a waveform; the plugin copies it into
every success/failure receipt so the app can reject records written by another
run or process. A valid experiment case requires exactly one `status=ok`
receipt matching the nonce, artifact digest, official model revision, and
12-lead checkpoint hash. Zero, duplicate, mismatched, or failed receipts make
that case an infrastructure failure rather than a scored model result.

The contract recognizes these eligible source classes:

1. `raw_waveform`: a waveform exported from WFDB, DICOM waveform, SCP-ECG,
   EDF, or another signal format with known leads and calibration.
2. `validated_digitized_waveform`: a screenshot-derived signal only after a
   separate digitizer has verified lead labels, paper speed, voltage scale,
   grid calibration, trace continuity, and reconstruction quality.

A PNG, crop, bbox, threshold/ink region, or MLLM visual impression is not an
eligible waveform. The current sidecar implementation accepts only registered
raw MATLAB waveforms; validated screenshot digitization remains a future input
class and is rejected by the registry today.

The local MEETI archive does contain raw signals matched to its rendered ECG
images. `scripts/build-meeti-eval.py --include-waveforms` retained 1,000 exact
12-lead, 500 Hz, 10-second records and generated
`data/eval-datasets/meeti-1000-all/waveform-registry.json`. Each manifest case
has one opaque hash-derived artifact id, so the image and waveform arms are
joined explicitly rather than inferred from model output.

## Response Boundary

The sidecar must return schema version 1 with:

- Exact model id, model revision, and checkpoint SHA-256.
- Source kind/hash and the actual lead inventory.
- Proof that model input is 500 Hz, 10 seconds, and 5,000 points per lead.
- Pinned preprocessing implementation/revision and ordered processing steps.
- Calibration status and calibration dataset revision.
- Ranked label probabilities and, only when locally validated, thresholds.
- Explicit limitations.

The plugin sanitizes this payload before OpenClaw sees it. Uncalibrated
probabilities are returned as `uncalibrated_score`, even if the sidecar supplied
a threshold. This matters because the official validation script derives
per-class thresholds from labeled evaluation data; it does not publish a fixed,
deployment-ready threshold table.

Every response is marked:

```json
{
  "use_policy": "supporting_evidence_only",
  "spatial_localization": "not_provided"
}
```

ECGFounder cannot create image bboxes. Overlay localization must still come
from the screenshot, lead inventory, crop/refine turns, coordinate calibration,
and `dicom_bbox_validate`.

## Standalone Waveform Run

The waveform-only arm can be run without an LLM provider. It is sequential,
resume-safe, and refuses to append to a directory whose protocol fingerprint
does not match.

```powershell
data\external\ecgfounder-runtime\.venv\Scripts\python.exe `
  scripts\run-ecgfounder-meeti-batch.py `
  --output-dir data\eval-runs\ecgfounder-meeti-1000-fullscores-20260804 `
  --max-predictions 150
```

It writes `protocol.json`, one line per case in `results.jsonl`, and an atomic
`summary.json`. The result rows contain only the opaque artifact id, report
hash/reference metadata, provenance, latency, and sanitized predictions; no
waveform path is emitted.

The full-score 2026-08-04 run completed 1,000/1,000 unique paired artifacts
with no failures in 605.847 seconds. Median inference latency was 547.202 ms
and p95 was 783.532 ms. Every row contains the complete 150-statement score
vector. Its protocol fingerprint is
`a7a55cca53031e799b678b43f9a6e4499c54342326e6f9d51facd95bffd7742b`.
All 1,000 rows are explicitly `uncalibrated`.

## Leakage-aware Research Evaluation

Run the hash-pinned evaluator after a complete 150-score batch:

```powershell
.venv\Scripts\python.exe scripts\evaluate-ecgfounder-meeti.py `
  --run-dir data\eval-runs\ecgfounder-meeti-1000-fullscores-20260804
```

The evaluator maps only exact ECGFounder statements, keeps uncertain concepts
out of both positive and negative classes, and never treats report silence as
a negative label. Abnormal concepts are compared only against explicit-normal
reports. Thresholds are selected independently inside deterministic five-fold
out-of-fold evaluation using ECGFounder's official 0.01-0.99 balanced-accuracy
grid; no learned threshold is installable in the sidecar.

The current research result (`0384ed02442200be8132943cf87210f8b52ac4ca8c9730de3a2237118c5dd40a`)
covers 33 of 38 observed reference concepts and 99.157% of asserted concept
instances. Across 23 concepts with enough fold support, macro balanced accuracy
is 0.865, sensitivity is 0.848, and explicit-normal-control specificity is
0.883; 15/23 concepts have point-estimate balanced accuracy at least 0.85.
Holdout top-20 mapped-concept recall is 0.837. For the 188 holdout cases with
3-5 mapped diagnoses, complete top-20 recall is only 0.479, so the requested
0.75 multi-diagnosis product target is not met by this waveform arm.

These numbers use weak report labels, lack patient identifiers for patient-level
splitting, and do not measure screenshot localization, report synthesis, or the
complete OpenClaw agent. Precision is intentionally not estimated because the
reports do not enumerate every absent diagnosis.

Two urgent canaries also show why this remains supporting evidence. One image
reference raised uncertain acute ST/STEMI concern while ECGFounder ranked
`NORMAL SINUS RHYTHM` at 0.9992. A second case strongly ranked atrial
fibrillation and low-voltage findings that agreed with the reference, but did
not directly recover its uncertain acute ST concern in the top ten.

## Experiment Rule

Do not compare a screenshot-only baseline against an ECGFounder arm unless the
same cases have eligible waveform artifacts. For a waveform-matched cohort,
record three paired arms:

1. Single-pass image model.
2. MultiPass image model with crop/refine.
3. MultiPass plus ECGFounder waveform evidence.

Start the third arm only after the sidecar endpoint and token are exported:

```powershell
scripts\run-meeti-openclaw-experiment.cmd `
  --model-id openai/gpt-5.6-luna `
  --manifest data\eval-datasets\meeti-1000-all\manifest.json `
  --multi-pass `
  --ecgfounder-waveform-evidence
```

The third arm tells OpenClaw to inspect the image independently first, call the
waveform tool exactly once, then reconcile agreement or disagreement. Provider
quota/authentication failures are experiment blockers, not negative model
results, and must remain recorded as such.

Persist sidecar receipts, input/checkpoint hashes, calibration revision, tool
calls, latency, failures, and disagreement cases. The waveform-only runner does
not compute diagnostic accuracy because no deployment thresholds are installed.
Accuracy and partial-credit comparison belong to the paired image experiment's
scorecard and still require clinician review; this integration is a co-reading
aid, not an autonomous diagnostic device.

The upstream MIT notice is retained in
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) and is included in the
portable bundle. The bundle verifier rejects Torch modules, sidecar source,
MEETI paths, waveform/model data suffixes, and checkpoint files anywhere in the
desktop bundle.
