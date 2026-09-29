# Scientific second look, content preflight and review handoff — 2026-09-25

## Actual implementation boundary

The public full contract requires completed validation and handoff events. It was
therefore unsuitable as the first content check before either operation had run.
This checkpoint adds a separately named public **preflight** API, not fabricated
future events or an optional bypass in the canonical serializer/CLI. It validates
all content/source/reference/study/review rules against the executed prefix and
rejects any future validation/handoff label. The canonical schema resource and
ordinary final-validation requirements are unchanged.

Public submodule `6152ab01d240c9b96698ff39e6a37ac35fa28275` contains the API, 16
new edge tests and shared method documentation. It was committed and pushed before
updating the host pin; no GUI/provider/auth implementation entered the public repo.

`ScientificImageSession` now explicitly executes a fifth Gateway request for a
second look after reconciliation. It focuses on conflicts, unsupported claims,
uninspected regions and urgent/reviewer questions, challenging the immediately
preceding finding inventory, not silently reverting to the blind draft. It uses
the **same full ROI**, not higher-resolution crops. Original replies are retained.

`prepare_review()` performs independent source/evidence binding and preflight,
then records the actual completed validation callback. Its snapshot remains an
intermediate result. `offer_review(presenter)` awaits a real host operation and
checks a bounded JSON availability receipt binding run, source, content and an
opaque surface ID. Only then does final assembly validate actual complete events
and unchanged content. Availability is not physician approval or clinical truth.

No default presenter is supplied. The existing desktop is still on its legacy
pipeline; these APIs are not a claim of new actual App inference. The host must
render a prepared draft before returning availability and withhold scientific
export until final validation succeeds. An unexpected final-gate failure preserves
true prior availability history but publishes no canonical result.

## Verification and failures retained

- Public full suite: **475 passed in 2.32 s**; compatibility/public-boundary checks
  and targeted Ruff pass. Staged public secret scan: no findings, 14.43 KB.
- Initial host focused run: **104 passed / two failed**. One new test used the
  wrong canonical field name (`report_status` instead of `result_status`); another
  reused a fixture whose confirm decision hardcoded `f1` after changing the
  preceding finding identity. Only those test expectations were corrected.
- Focused host run including actual native JavaScript geometry producer:
  **122 passed in 20.45 s**. Subsequent expanded handoff tests: **28 passed in
  2.43 s**, covering all three modalities, failed preflight and failed final gate.
- Full unit/smoke/integration suite: **2,332 passed / seven explicit skips in
  402.60 s**, session 41544 completed with exit 0. The skips are a local portable
  Node-directory check, private frozen cohort, three packaged runtime opt-ins and
  two native capture/input opt-ins. Native Windows Mark input was then separately
  enabled and passed **1/1 in 1.06 s**; it is not a new whole-App inference run.
- Documentation/clinical workflow links: **12 passed in 0.10 s**; changed-source
  Ruff/format and two-module mypy pass. Initial staged host scan: no findings,
  56.15 KB. Public CI runs 36062945672 and 36062941376 completed successfully.
- Gateway replies and presenters in these tests are **synthetic**. Native tool
  execution validates receipt transport/geometry, not medical localization truth.
  No new paid inference, GUI-model run, screenshot, package or clinical score.

New tests cover non-canonical preflight snapshots, independent content hashes,
future/failed event rejection, missing content/bindings, detached mutation,
source/run/content mismatch, duplicate JSON, invalid/oversized receipts, missing
presenters, exceptions, cancellation, concurrent/repeated calls, premature
handoff, second-look tool/QC/decision violations, prior-versus-blind identity,
non-diagnostic no-inference behavior, and native geometry surviving final assembly.

## Remaining end-state requirements

Actual GUI presenter/default pipeline integration and usage receipts, trustworthy
matched external-model evidence, zoomed crop revisits, quality-only non-diagnostic
handoff, vendor/old-ECG diversity, cross-DPI/current-EXE validation and clinical
acceptance remain incomplete. Five requests can cost more than the legacy route;
this checkpoint makes no measured speed or accuracy improvement claim. Original
sealed cohorts/scorers/runtime logs were not replayed, altered or relabeled.
