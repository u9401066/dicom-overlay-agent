# Evaluation cohorts and claim boundaries

本文件說明目前各 cohort 的用途、答案隔離、實際執行狀態與可宣稱範圍。資料集
存在、manifest 通過或 mock 8/8 都不等於真實 App 已判讀影像。

## Cohort inventory

| Cohort | Cases | Purpose | Current state | Valid claim |
| --- | ---: | --- | --- | --- |
| `full-9922` | 9,922 | MEETI ordered full-cohort paired evaluation | manifests/tooling exist; authoritative new pair not complete | evaluation capacity only; historical partial/paired results remain dated |
| `important-multi-128-v1` | 128 | historical important multi-diagnosis stress cohort | 121-case Astra-low primary sealed and scored; six earlier pilots separate | failed acceptance: strict 0/46, annotated urgent concerns 2/21; not medium coverage |
| `prospective-desktop-important-multi-120-v1` | 120 | Astra-medium GUI stress cohort | sealed/scored; 120 verified exports, 482 stages | failed clinical acceptance: strict 0/46, all urgent concerns 5/24; now exposed |
| `incomplete-ecg-20260902-v2` | 8 variants / 1 source | deliberately incomplete/cropped/low-resolution ECG behavior | 8/8 historical mock; six native exports / 23 medium stages, two blocked before inference | exact ROI/export binding and partial behavior for six variants; not diagnosis or vendor acceptance |
| 10,001-identity scale fixture | 10,001 identities | atomic resume/checkpoint set behavior | source smoke complete | resumability scale, not 10,001 medical images |
| Historical 32/8 sets | 32 paired + 8 unseen | 2026-08-09 engineering evidence | complete under their recorded protocol | only the dated metrics in their evidence record |

## 9,922-case source

The canonical full MEETI image cohort contains 9,922 ordered cases. Inference
and gold manifests are separate:

- `full-9922.inference.json` contains only the inputs available to the model;
- `full-9922.gold.json` remains sealed until saved inference is complete;
- source, case order, scorer, runtime, model, prompt, OpenClaw, and ownership
  fingerprints must match before paired comparisons are valid.

A previous full run stopped after 289 baseline results and is intentionally not
merged into a later frozen pair. Presence of 9,922 images or a resumable runner
does not prove that a current 9,922-case model evaluation completed.

## Important multi-diagnosis 128

### Selection contract

`important-multi-128-v1` was deterministically selected with seed `1946247532`
from the 9,922-case source. It is intentionally enriched for important and
multi-finding ECGs:

- every case has at least three canonical diagnoses after removing generic
  normal/sinus labels and resolving defined aliases;
- every case belongs to an important-diagnosis tier;
- exact image hashes and normalized reports are unique;
- canonical diagnosis signatures are diversity-capped;
- 24 cases are critical and 104 warning;
- label status is 48 asserted and 80 partially uncertain;
- allocation is 24 acute-risk, 28 ischemic/infarct, 28 rhythm/ectopy, 32
  conduction/QT, and 16 structure/voltage;
- each of the 16 target EKG axes appears in at least 12 cases.

Binding values:

| Field | Value |
| --- | --- |
| Pair id | `7bdc87f6d184b321938a09e4f02335692fbda75a378127305742b6f41e8a46e0` |
| Ordered image SHA-256 | `38bcf5b0bd4008ac3bb6a39da3cb7f430278c55aff4c818d0a08a1fd2348c7ca` |
| Ordered case-identity SHA-256 | `6e4a8de82a686601b72e08037300ac8d0a23556f570782a5dd167919271224f9` |
| Gold manifest SHA-256 | `10be5cf206fdfe097b757c0754f17356932992e144b230bfe05d0784bd077cf1` |
| Inference manifest SHA-256 | `edad516b2659d5174c926890b19caa67186de8631efdd8f01862039ff9c3dfaf` |

### Exposure and execution status

The selected cases are now `exposed_reserved`: all 128 identities must enter
the exposure denylist before selecting a future prospective batch. Construction
metadata originally recorded `model_execution_status=not_run`; it describes
construction, not the current execution ledger. September 2–3 subsequently
recorded 60 source-matched Luna exports and 43 timeouts across 103 attempts.
September 10 switched to Astra low. The 121-case primary was subsequently sealed
and scored; six earlier pilots remain separate, and the primary failed acceptance.
See the [sealed evidence](../evidence/2026-09/evaluation-desktop-astra-2026-09-11.md).
It does not establish the current medium model's accuracy. A new 120-case batch
has a [frozen selection](../evidence/2026-09/prospective-medium-cohort-2026-09-24.md),
with 46 asserted / 74 partially uncertain references and a refreshed exposure union.
Its 24 acute-risk references are uncertain concerns, not confirmed urgent diagnoses.
The [actual medium desktop batch](../evidence/2026-09/medium-desktop-batch-2026-09-24.md)
is now sealed/scored after full-image ROI calibration and failed clinical acceptance.

The full run must be performed in order through the real viewer and desktop App,
not by replacing viewer interaction with a direct script/client call. For each
case retain the source digest, configured ROI, App-managed Gateway ownership,
model/auth route, token categories, wall time, raw result, incomplete/review
state, screenshot, marked export, bbox/tool receipt, and coordinate audit.

Only after a run is frozen may the gold manifest be opened for scoring. Report
asserted and partially uncertain concepts separately, retain every critical miss,
and explicitly label the estimand as a stress-cohort result. Because sampling is
purposefully enriched, its score is not prevalence-weighted accuracy and must
not be generalized to a clinical population.

## Partial-ECG v2

`data/eval-datasets/incomplete-ecg-20260902-v2/manifest.json` is answer-free and
PHI-cleared. It derives eight deterministic variants from one source:

| Variant | Transformation | Intended edge |
| --- | --- | --- |
| `crop_top_20` | remove top 20% | top rows/leads missing |
| `crop_bottom_20` | remove bottom 20% | lower rows/rhythm strip missing |
| `crop_left_20` | remove left 20% | lead labels/onsets missing |
| `crop_right_20` | remove right 20% | later time segments missing |
| `crop_vertical_middle_50` | retain central horizontal band | partial rows without full layout |
| `mask_labels_left_12` | white-mask left 12% | waveforms visible but labels untrusted |
| `crop_horizontal_band_06_of_12` | retain a 60 px band | one-row-like fragment |
| `tiny_short_edge_48px` | downsample to 67×48 | morphology unassessable from resolution |

Manifest SHA-256:
`e61b5fc6ede4047640d4204c9c9a557661c615549d86435632e5c69966f85d50`.

The 8/8 mock run establishes only that the exact variant bytes, transform
metadata, `incomplete/review` requirements, schema, bbox binding, and artifact
validator agree. It has no diagnostic gold and cannot prove the model recognized
rhythm, missing leads, or pathology.

September 25 [actual App evidence](../evidence/2026-09/native-partial-ecg-2026-09-25.md)
now records six completed variants and two tiny-window discovery blocks before
inference. All six are incomplete/review-required, their declared visible labels
match a separate manual inventory, and visible/export pixels match exactly.
Original false-positive rule warnings and unsuccessful attempts remain preserved.
The right crop retains all twelve printed labels: the old blanket ban on any
twelve-lead inventory is too broad. This documentation clarification is not a
change to a frozen scorer or a retrospective diagnostic pass.

For the real App gate, open each variant in the actual viewer, let the App capture
only the configured ROI, and verify:

- `incomplete=true` and `review_required=true`;
- an explicit case-specific limitation, not a generic medical refusal or boilerplate;
- no named lead claim outside verified visibility; distinguish twelve surviving
  labels from a complete, calibrated study;
- context-dependent axes are `not_assessable` or cautiously abnormal, never
  fabricated as normal from invisible content;
- any bbox is bound to the exact variant SHA-256 and remains within the visible image;
- real viewer+overlay screenshots and export audits are saved for all eight cases.

## Scoring and reporting rules

### Sealed desktop export scoring

`scripts/score-desktop-cohort.py` scores existing real-UI export files without
calling an analyzer or applying current production guardrails. It requires a
complete primary hash inventory with at least 100 distinct planned cases, excludes
earlier pilots, and verifies every recorded artifact and the original append-only
ledger before opening gold. Recovered usage receipts remain separate files and
must bind the exact source and observed Astra-low turns. The original failed
attempts remain in the derived report; they are not additional patients.

The historical primary run used indices 7..127 (121 cases); the six earlier pilots
are intentionally separate because they have different implementation provenance.
Only after that primary run is complete and its source/GUI/model receipts are
sealed may the following post-hoc command be used (paths are local, not public
artifacts):

```powershell
uv run python scripts/score-desktop-cohort.py `
  --workspace <evidence-workspace> `
  --seal <completed-primary-seal.json> `
  --inference <important-multi-128-v1.inference.json> `
  --gold <important-multi-128-v1.gold.json> `
  --gold-sha256 10be5cf206fdfe097b757c0754f17356932992e144b230bfe05d0784bd077cf1 `
  --output <new-scorecard.json>
```

The gold digest must be the value recorded before inference. Pair id, case order,
source paths and sealed image hashes must agree. Existing output paths are refused;
source/gold hashes are checked again after scoring. Original exports are not
rewritten to resemble eval-runner artifacts. The scorecard records its scorer
hash, source seal, separate complete/weak-label denominators, all cannot-miss and
urgent-concern outcomes, and descriptive case-level Wilson intervals. The boundary
case of zero or all successes has an exact 0 or 1 interval endpoint.

Neither these intervals nor bbox containment establish population accuracy,
clinical localization accuracy, patient-level independence or release readiness.
Concurrent engineering work also prevents a controlled runtime-speed comparison.
Synthetic regression covers incomplete cohorts before gold access, wrong/changed
gold, duplicate cases, mismatched source/model/effort, missing evidence, negative
attempt indices, traversal paths, post-score mutation and overwrite protection.
The historical primary score now exists and fails the gate; see the sealed evidence
above. The separate medium cohort now has its own failed sealed score in the
[medium evidence](../evidence/2026-09/medium-desktop-batch-2026-09-24.md). The low-specific
scorer must not silently relabel medium receipts as low or merge the two cohorts.

- Schema, bbox in-bounds, tool receipt, coordinate projection, latency, strict
  score, partial credit, normal specificity, urgent recall, and cannot-miss recall
  are separate metrics.
- A completed provider turn with a wrong report is a clinical miss, not a
  transport pass converted into overall success.
- `incomplete/review` is a useful safety state but does not grant diagnostic credit.
- Uncertain reference concepts may receive only the explicitly defined candidate
  credit; they cannot satisfy strict/cannot-miss gates.
- Mock-derived answers and label echoes are plumbing self-tests only.
- Never publish a denominator larger than the count of durable, verified real
  results for the declared protocol.

## Related evidence

- [Current verification record](../evidence/2026-09/verification-2026-09-02.md)
- [Real desktop runbook](../operations/real-desktop-tests.md)
- [Historical MEETI/OpenClaw experiment record](../evidence/2026-08/meeti-openclaw-experiments-2026-08-09.md)
- [Clinical knowledge governance](../../clinical_knowledge/README.md)
