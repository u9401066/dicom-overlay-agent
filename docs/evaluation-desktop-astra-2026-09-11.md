# Astra low real-desktop baseline — 2026-09-11

This baseline **does not meet clinical acceptance**. The real App/Viewer/model
path works, but operational completion must not be reported as diagnostic
correctness. No binary or clinical release is approved by these measurements.

## Cohort and immutable evidence

The completed primary cohort comprises 121 distinct selected multi-diagnosis
ECG cases (planned indices 7..127). Six earlier pilots are excluded, not added
to the denominator. Selection was enriched for important diagnoses from the
10,001-row / 9,922-canonical-image local dataset; it is not population sampling.
Of these 121 references, 46 have complete labels and 75 are weak/uncertain labels.
Patient-level independence and specialist adjudication are not established.

Every included case was opened through the real Viewer's QFileDialog, analyzed
and exported through the App controls. Exported source identity, image hashes,
public Gateway receipt and recorded model observations were checked. The primary
seal inventories 1,991 files before paired gold was opened. Its SHA-256 is
`2de49ad479ddeef43b4e47fb1539e78161d4c4654d4ffc13c37ea63fb5e43657`.
The pre-recorded gold digest is
`10be5cf206fdfe097b757c0754f17356932992e144b230bfe05d0784bd077cf1`.
First scorecard SHA-256:
`be438ce403a9f14adc263ab9a0995ae97184ba27e0176563b676fead6adebe1d`.

Raw results, screenshots and original failure receipts remain unchanged under
ignored local evidence. Scoring used the recorded candidate `a7d8fb4` scorer,
without replaying new clinical guardrails or the later bbox correction. There
was a documented checkout/line-ending boundary during the run, so this is
explicitly **not byte-identical frozen-release evidence**. The main runtime
remained OpenClaw 2026.7.1-2, not the separately packaged 2026.9.3 candidate.

## Preliminary automated results

| Measure | Result | Interpretation |
| --- | --- | --- |
| Strict complete-reference match | 0/46 | Wilson 95%: 0–7.7%; not a clinical sensitivity estimate |
| All annotated urgent concerns caught | 2/21 | Wilson 95%: 2.7–28.9%; requires specialist adjudication |
| Strong-reference can't-miss caught | 0/1 | Only one applicable case; do not generalize |
| Exact severity category | 8/121 | Dataset/category agreement, not diagnosis accuracy |
| Schema pass | 113/121 | Structural/parser contract, not clinical correctness |
| Bbox in bounds | 121/121 cases | No reference boxes: does not establish localization accuracy |
| Completed finalization | 109/121 | Remaining 12 timed out after receipt mismatch and retry |
| Incomplete / review required | 121/121 | All results retain limitations; not equivalent to normal |

Mean concept recall is 0.063 over 121 scorable cases; complete-reference concept
F1 is 0.072 over 46 cases. Mean candidate-concept recall is 0.147 over 75 weak
references. These automated concept matches are provisional, not specialist
adjudication. In particular, bbox serialization failure explains only 12 failed
finalizations, not the generally poor diagnosis agreement in completed reports.

There are **zero normal controls**, zero negative-reference scorable cases and
zero dedicated partial-input-contract cases in this primary set. Aggregate
sentinel values such as negative recall or partial-contract rate `1.0` have no
applicable denominator and must not be displayed as 100% specificity or a passed
partial-ECG experiment. Separate deliberately cropped/missing-lead trials remain
required. The original source rasters may themselves clip leads or omit scale.

## Time, attempts and subscription observations

Completed-case analysis time: mean 136.662 s, median 134.759 s, p95 166.171 s,
maximum 175.805 s. These exclude file-open/export overhead and failed attempts.
Concurrent engineering workloads prevent a controlled performance comparison.
The apparent 121/121 successful-case initial SLA rate does not erase the retained
initial-timeout attempt.

Six primary technical failures remain: early file opening, checkout guard,
stale Viewer preflight, usage collection after UUID masking, an initial model
timeout and a pre-send ROI obstruction. Successful retries are linked to the
same cases, not counted as new patients. The masked-UUID usage recovery used a
separate receipt and no new inference. The obstruction occurred while packaged
tests were active; a causal window was not captured, so that cause is unproven.

There are 446 recorded stage-session snapshots; all bind to observed
`gpt-6-astra / low` and have public session usage fields. This is **not a complete
billing ledger**: nested rejected attempts and the initial-timeout attempt are
not represented in those 446 stage snapshots. Missing or aborted usage is not
zero consumption. No currency charge, priority service tier or complete token
total is inferred from these receipts.

A separate, read-only post-seal supplement includes 14 nested rejected attempts:
**460 unique sessions have public usage fields and bound Astra-low observations**.
It makes no model requests and verifies the primary seal before and after.
Binding requires both exact run/session identities, or one exact identity plus
one uniquely matching masked identity with at least 16 visible prefix characters;
two masked identities are rejected. Thirteen synthetic binding checks pass.
Supplement SHA-256:
`0684cbfb65d0bb7fcba56d46821d38c34220728b184bb278f415f4e26c45a045`.
This does not replace the 446 original stage snapshots. Failed attempts without
an exported identity, including the initial timeout, remain unbound and unknown.

The entire 128-case selected cohort is now conservatively excluded from future
blind selection. The cumulative exposure denylist contains **1,358 identities**,
SHA-256 `8f9b67034a2d577ecad8cab80d32d6551a2e26fd39f1fce3a7c82cb76cd212ad`.
Subsequent work on these cases is exposed development, not a new blind benchmark.

## Next acceptance work

1. Preserve this baseline and enforce the new exposure denylist for future blind
   evaluation. Do not rewrite the baseline with current rules.
2. Validate plugin 1.5.9's producer/consumer rounding correction in a new actual
   GUI/model candidate; establish retry and timing changes, not just unit passes.
3. Review source readability, lead/layout grounding, diagnostic omissions,
   severity handling and cautious-label scoring separately. Do not weaken
   abstention or force gold labels into the agent to improve a metric.
4. Run deliberately incomplete ECG, DPI/resize, bbox and canvas interactions;
   obtain specialist review of important discordances and use a fresh holdout
   for any claimed accuracy improvement.
5. Keep the binary distribution-license decision, clean package/CI and actual
   candidate acceptance gates open.
