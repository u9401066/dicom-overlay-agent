# Scientific desktop paired regression — 2026-09-29

**Latest checkpoint: two actual cases published; case0's original collector failure
is retained and bound by a supplement, case1 completes with the new collector.
Case2 is running; remaining118 cases are not credited as completed.**
The preparation sections below describe the pre-inference state at their timestamp.
This is a paired regression of the previously exposed
[120-case medium cohort](medium-desktop-batch-2026-09-24.md), not120 new blind
images or evidence of improved clinical accuracy. The old failed score remains
unchanged. Its46 asserted/74 partially uncertain cases and absence of confirmed
acute cannot-miss references remain limitations of this cohort.

## Frozen execution plan

- Source App `9a8484746d57f8c81f2797e5336369b15559af35`, scientific-review mode,
  Astra subscription/medium verified through actual Settings. Not a frozen EXE.
- New private root `Ctemp/dicom-scientific-cohort-9a84847-20260929`; all18,771
  copied runtime files matched the pristine36dc3c6 payload before configuration.
  Earlier runtimes remain sealed. App32116/launcher25400 owns Gateway7204 on18796;
  actual Viewer33040/launcher33368 is a separate process.
- Reuse only the answer-free inference manifest, unchanged SHA256
  `4663a7e5053df6ff1652fb25a6d0f8127c09da396ae068679dcf1038303feeae`.
  All120 ordered input hashes were recomputed and match its frozen identity digest.
  Gold is not opened by preparation/driver. Its previously declared SHA256 remains
  `cae03104d538fa7c38e5021e9a2620dc5e19636963b65fb8b6dd23c200503243`.
- Before inference, create-only `cohort-run-9a84847/plan.json` was written with
  input/config/driver/UI-helper/collector hashes, App/plugin/public-harness source
  fingerprint, actual process IDs and ROI. Its independently observed SHA256 is
  `85c87eef90a809e041a6d32fafe42a00372c7f88a636a19d4483b65815422c7f`.

## Actual ROI setup, not a config-only enlargement

The initial config deliberately had `configured=false`. The new App remained in
SETUP while the owned synthetic-grid Viewer was minimized. The first calibration
helper failed its window-rectangle preflight **before mouse input or inference**;
that failure is retained in `viewer-restored.json`. Only the owned Viewer was
restored, not foreign windows. This does not establish what minimized it.

The App then discovered the Viewer and opened its actual ROI dialog. Native drag
from(30,30) to(1530,1110), followed by Enter, saved zero crop margins against a
1500x1080 physical Viewer. The bounded preview was visually inspected: complete
synthetic image rectangle and selection border at150% DPI. Captures remain inside
this image window, not the2560x1600 desktop. No model analyzed the synthetic grid.

## First tranche and acceptance limits

Run the first three cases through actual file dialog, Analyze and Export before
continuing the fixed order. The driver independently compares file-to-visible
pixels (bilinear MAE<2), then visible-to-export pixels (MAE0), validates the public
scientific contract, and binds its source hash and all model-stage usage. Top-level
and recursive artifact inventories are retained separately.

An unresolved timeout, unsafe capture, failed contract or usage mismatch stops
the driver for inspection. Keep every failed attempt; never overwrite it, skip it
from denominators or rerun completed cases. A still-running App/driver must be
inspected through its original process handle, not restarted because output is quiet.
The existing legacy batch auditor checks execution evidence, **not** independent
scientific-ledger adjudication; broader scientific audit/scoring still needs work.

Source9a84847 full regression:2435 passed,10 conditional skips in437.41s.
Both remote CI runs and both secret scans passed. These tests do not prove any
new case completed. Original120-case clinical acceptance remains failed; no new
clinical score or packaged release is claimed.

## First case: actual publication, collector failure and read-only recovery

Case0 completed actual Analyze/Export at11:10:34UTC. Analysis124685ms; driver
wall138.138s includes the failed collector. Source pixels match its pre-analysis
ROI at MAE0; file-to-screen resampling MAE0.5350714. All eight scientific workflow
events reached handoff. One warning finding, two boxes, incomplete/review required;
maximum observed projection error0.4411px. The actual exported summary was visually
inspected. These are execution/UI observations, not clinical correctness.

Export: `desktop-20260929-111034-531785`. Canonical SHA256:
`8e67b24d8753713a0ff0b352fe68c4b76951fcb99ceb2bcd38f48dd2d3f99d42`.
The initial driver stopped with `technical_failure`: its inherited legacy usage
collector searched the projection's `analysis_trace`, which contains a Gateway
receipt rather than the five scientific model turns. Its zero-turn, unverified
usage output is retained. No image was resent and the original failed receipt
SHA256 remains `6e12334822ff9939661ab890ec6cddcd140d43801d8c2c58e7237f3da6e0e1d4`.

New `scripts/collect-scientific-desktop-usage.py` validates the public scientific
contract, source identity, host-run association, immutable turn artifacts and
all five stage/session/run identities against public sessions and Gateway logs.
It checks source/receipt stability before and after its read-only query, records
the log-prefix hash and collector hash, and writes outside the runtime using
create-only output. It does not enable a different model/runtime or use API keys.
Unknown/stale/ambiguous counts fail rather than becoming zero. Public snapshots
are not a monetary bill or proof of clinical correctness/remote image bytes.

Supplemental five-turn receipt `case-000-scientific-usage-v2.json` SHA256:
`a3f193a6621d581f58d13c2113260362d993d0a9f56741164bb3c151895abc4e`.
The earlier prototype supplement remains separately retained. Neither supplement
changes the original driver status or any export bytes.34 new collector tests and
33 existing batch-verifier tests pass (67 total); Ruff/format pass. Local source
regression2435pass belongs to the preceding App code, not these new collector tests.

Resume requires a new, explicitly linked continuation plan/driver: preserve the
original plan and failed receipt, bind this usage supplement, and verify App code,
input order, ROI/config and live process identities are unchanged. Only the
driver/collector changes. Do not rerun case0. Independent scientific batch auditing
and clinical scoring are still pending; the legacy complete-batch seal cannot be
used unchanged to claim acceptance of this recovered scientific run.

## Linked continuation checkpoint

`run-batch-v2.py` froze create-only `plan-v2.json` before starting case1. Plan SHA256:
`b960a9a5f3526c8f636134af25ff5d08e507ec83fbaabb1046d59182b912d029`.
It binds the original plan, original case0 failure and supplemental usage by their
exact hashes. App/plugin/public-harness source fingerprint, inputs, config/ROI and
App/Viewer identities match the first plan; only driver/collector differ. It skips
case0 only after checking that exact recovery, not through a generic ignore-error
switch. The original plan/driver/receipts remain untouched.

Case1 began actual capture11:19:56UTC. The idle transport was interrupted before
acceptance; the App reconnected and replayed the unaccepted frame once with the
same idempotency key. Subsequent receipts must establish the actual model turns;
this log alone is not proof of no duplicate inference. At this checkpoint case1
is running and case2 is not credited. Same owned App/Gateway remain live.

Four additional CLI tests cover create-only output, stripping inherited API keys,
read-only session command arguments, public-query failure and artifact/turn
mutation during the query. All38 collector tests,33 legacy verifier tests and four
documentation checks pass (75 total). See the
[collector operation and limits](../../operations/scientific-usage.md).

### Case1 publication checkpoint:11:22UTC

Actual Export `desktop-20260929-112204-936657` completed with two warning findings,
incomplete/review required; its saved summary was visually inspected. Analysis
125886ms, complete GUI/usage workflow141.270s; source-to-visible MAE0.5002786 and
visible-to-export MAE0. Five scientific turns match Astra medium. The Gateway log
contains exactly those five distinct run starts during this case's recorded time
interval, with no extra recorded inference from the earlier unaccepted-frame replay.
This is an observed log boundary, not a general exactly-once network guarantee.

- Canonical SHA256: `37169cc0bfd0e3590bc2165df3e38992a2d6bdd5ebf68f5ecc28cc68c7f914bd`.
- Source SHA256: `9dbef6e095909509e2a34f3e7d894ebd46f0b13cfa435c7351bd6a4022b309c5`.
- Scientific usage SHA256: `d38f882d6727ef05b9b46a77e0cec4f1062a5bad7958beb7ef66c91b38c7448a`.

The same continuation driver started case2 at11:22:17UTC. It is not completed at
this checkpoint; inspect its existing live process before any further action.
Neither published case is a clinical pass or a new blind sample.
