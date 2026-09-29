# Executable post-blind localization and challenge — 2026-09-25

This extends the opt-in scientific image session beyond intake/QC/blind reading.
It does **not** activate a new desktop analysis mode or replace the existing
working 16-key overlay/QA path. No paid model or new native GUI run occurred in
this checkpoint. The real partial-image GUI batch and original failed clinical
cohorts remain unchanged.

## Actual integration added

`ScientificImageSession.localize_and_reconcile()` continues a successful blind
pass through two new Gateway requests, wrapped by actual journal callbacks:

1. Native geometry checking, after—not during—the retained blind draft. The model
   may call only `dicom_bbox_validate`, using the exact immutable source image,
   current host nonce and image digest. Original visible tool text is collected
   from matching-run Gateway events. The independently read native audit snapshot
   is frozen under the client's send lock before another turn can reset it.
2. The existing source-evidence adapter validates those two observations against
   the exact attached bytes. Every observed call needs exactly one result/audit;
   wrong source, altered text, duplicated audit, missing result, unbound start or
   non-bbox tool events reject the stage. Up to eight native calls are allowed.
   Unavailable/rejected-only geometry remains without boxes; no static fallback
   is fabricated into scientific evidence.
3. Reconciliation reinspects the source with the blind draft and bound geometry.
   The model supplies four review inventories and a scientific draft plus explicit
   `confirm/revise/retract/add/unevaluable` decisions. All old and final findings
   must be accounted for exactly once. Confirm cannot change clinical wording,
   certainty, severity, claim type or linked observation content; changes require
   revise. Geometry/evidence links may be added without altering the blind record.

The independent-evidence stage currently means independent **native geometry
validation**, not independent diagnosis. No waveform classifier, prior-report
lookup, matched artifact resolver or medical ground truth was added. The model is
explicitly told not to claim classifier agreement from a bbox receipt.

The original reconciliation envelope bytes/hash are retained separately from its
decoded nested draft. Only the nested draft is JSON-projected for the existing
strict decoder. Localizations/reconciliation properties return deep copies; later
Gateway sends cannot erase previous receipts. Repeated or concurrent continuation
cannot rerun a paid request; failures/cancellation stay terminal for that session.
Non-diagnostic QC still prevents blind/localization/reconciliation inference.

These remain intermediate drafts. No completed second-look, contract-validation
or human-handoff events are manufactured; canonical serialization still rejects
the result. No clinical labels, certainty, normal axes or boxes are invented to
make that gate pass. Default Gateway/schema/plugin pins, ROI capture, DDD model
ownership, dependencies and executable packaging configuration are unchanged.

## Verification, including encountered failures

- Twenty new synthetic challenge tests cover all five decisions, complete finding
  coverage, duplicates, changed claims/observations, missing references, extra
  fields, strict JSON, immutable blind records and absence of canonical completion.
- Fifteen new smoke cases combine the actual repository JavaScript bbox producer
  and its native audit file with real client receive/journal/adapter code. Model
  and Gateway replies are synthetic, not live acceptance. They cover successful
  geometry binding, no-localization/rejected-only paths, wrong source, altered
  text, duplicate audits, unexpected/unbound/unfinished tools, missing decisions,
  QC mutation, malformed reconciliation, cancellation and concurrent continuation.
- One additional collector test bounds started-call tracking at 64 without
  retaining private arguments. Existing result-count behavior remains unchanged.
- Initial native fixture run: **9 failed / 2 passed** because the in-memory
  client's one-second timeout also covered real Node startup. The fixture was
  corrected to use 30 seconds; production timeouts/retry policy were untouched.
  A targeted type error was fixed by assigning the awaited reconciliation result
  to a local before the optional stored slot. Subsequent count-limit coverage
  caught a changed failure category; the original result-limit category was kept,
  with a separate bounded start-event category.
- Final focused collector/client/session/decoder/native-source checks:
  **206 passed in 18.71 s** under Node 24.18. Ruff/format and focused mypy on the
  session/reconciliation/collector pass. These are execution/contract regressions,
  not measured model accuracy, speed, calibration or clinical localization.
- Full suite: **2,241 passed / seven explicit skips in 405.22 s**. The opt-in
  packaged-runtime/native-GUI and local artifact skips remain skips, not acceptance.
  Twelve documentation/workflow checks pass. Staged secret scan: 66.49 KB, no
  leaks. Frozen 120-case seal/score and partial-batch audit hashes were rechecked
  unchanged. No dependency, public schema, active prompt, Gateway pin or bundle
  configuration changed; no package-size or refreshed EXE claim is made.

## Limits and next activation gates

Readable inputs use four model requests through reconciliation, before any
targeted second look. Request counts alone do not establish a speedup. Model
identity remains `openclaw-unverified` until a real usage receipt is bound.

The host verifies inventory/reference/decision consistency, not clinical semantics
of the model's agreement/conflict lists. Tool-event rejection is observational:
it cannot undo a tool or attest to silent provider operations. Audit snapshots
are canonical metadata, not original file lines, cryptographic signatures or
independent execution attestations. Live Gateway sanitization may prevent exact
tool-text hash agreement; such a failure must remain a failure, not be repaired.

Still required: trusted source/waveform matching and independent classification,
targeted source crops/revisits, truthful final validation/handoff assembly, durable
protected attempt archives, guarded App publication/QA/export wiring, and real
App/model/native-EXE verification across the requested image/device/DPI scope.
The complete goal remains open. The previous `e213fe9` CI and secret-scan runs
all completed successfully before this new source checkpoint.
