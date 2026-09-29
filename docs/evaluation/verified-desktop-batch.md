# Seal and score the actual Astra-medium desktop batch

The current [prospective GUI batch](../evidence/2026-09/medium-desktop-batch-2026-09-24.md)
uses per-case create-only receipts, unlike the historical Astra-low ledger/seal.
Do not rewrite either format or relabel old low runs as medium.

`scripts/score-verified-desktop-batch.py` adds separate **seal** and **score** steps.
It makes no GUI, Gateway, model, session-query or network calls. Original predictions
and artifacts remain unchanged; derived outputs are create-only and cannot be
placed inside the primary run/export trees.

## Preconditions and sealing

First observe the **original driver's successful terminal result**. A timeout,
stale lock file or merely seeing many receipts is not proof that the process ended.
Do not restart an apparently quiet batch or rerun completed cases. The
`--driver-completed` flag records the operator's actual observation; it is not an
independent process monitor, signature or substitute for that observation.

```powershell
uv run --frozen python scripts/score-verified-desktop-batch.py seal `
  --run PATH_TO_ORIGINAL_RUN `
  --manifest PATH_TO_ANSWER_FREE_INFERENCE_JSON `
  --exports-root PATH_TO_ISOLATED_EXPORTS `
  --gateway-log PATH_TO_ORIGINAL_GATEWAY_LOG `
  --plan-sha256 PREVIOUSLY_PRESERVED_PLAN_SHA256 `
  --expected-cases 120 --driver-completed `
  --output PATH_OUTSIDE_PRIMARY_TREES/sealed-batch.json
```

The existing independent batch auditor must verify every planned distinct case
(at least 100), with no pending, invalid or technical-failure cases. Failures remain
in the original evidence; they are not dropped to manufacture a passing denominator.
Use the auditor's report to inspect failures, not this scorer to bypass them.

The seal binds the exact plan, inference manifest, original input images, per-case
attempt/visible-ROI/receipt files and all export files **including recursive crop
subdirectories**. Crop files are first inventoried here, not retroactively attested
by the original top-level export receipts. The Gateway log binds its exact existing
byte prefix; subsequent append-only status text is permitted, but changing or
truncating the sealed prefix fails. The current audit is still rerun against the
original log, including any subsequently appended identity records.

Coverage, pixels, usage identity and inventory are checked again before the seal
is written. Its output SHA-256 must be preserved independently for the score step.
The source plan digest for the current cohort was first independently captured
mid-run; neither that fact nor a local seal is a trusted pre-run timestamp.

## Gold access and scoring

Only after sealing, invoke score with the independently preserved seal digest and
the gold digest recorded **before inference**. Never replace either with a fresh
digest just to make changed evidence pass.

```powershell
uv run --frozen python scripts/score-verified-desktop-batch.py score `
  --seal-path PATH_TO_SEALED_BATCH_JSON `
  --expected-seal-sha256 PRESERVED_SEAL_SHA256 `
  --gold-path PATH_TO_PAIRED_GOLD_JSON `
  --expected-gold-sha256 PREINFERENCE_GOLD_SHA256 `
  --output PATH_OUTSIDE_PRIMARY_TREES/scorecard.json
```

The scorer rechecks the seal digest, verifier/sealer implementation identities,
all artifacts, recursive inventory and complete independent audit **before opening
gold**. It then verifies the paired manifest identity, exact case order, modality,
source paths and gold hash. The existing concept/scoring implementation is reused;
no guardrails are replayed, no model output is repaired, and no inference is run.
Seal/artifact/audit/gold checks are repeated before the derived scorecard is created.

This is a versioned automated score, not clinical acceptance:

- Asserted complete references and partially uncertain references keep separate
  denominators. Incomplete predictions stay in the cohort.
- Case-level Wilson intervals include numerator and denominator. With zero eligible
  `cant_miss` cases, the corresponding rate/interval is **null (unmeasured)**, not
  proof of either 0% or 100% sensitivity. Legacy aggregate defaults should not be
  interpreted without these denominators.
- The schema metric is the existing App-draft check, **not** canonical observation/
  evidence-ledger validation. `canonical_ledger_validated` remains false.
- Concept matching needs specialist adjudication. Box containment is not clinical
  localization accuracy without reference boxes.
- Selection is gold-enriched, not population prevalence. Patient independence is
  not established. Concurrent engineering work prevents controlled speed claims.
- No result is signed, sent to PACS or declared a clinical release.

Keep raw images, model replies, gold and full scorecards private. Public checkpoints
may report aggregate counts/hashes, scope and limitations without publishing PHI.

## Verification

24 synthetic tests exercise 100-case fixtures through the real independent auditor,
including evidence mutations, added/changed crops, log-prefix mutation versus safe
append, wrong gold pairing/digests/order, gold changes during scoring, non-overwrite
and output-tree protections: **24 passed in 138.79 s**. These tests do not open the
private cohort or establish real-GUI/model acceptance. Full unit/integration/smoke
regression: **2,160 passed, seven explicit opt-in/private-environment skips in
353.94 s**. This excludes native-input and frozen-binary opt-in checks.
