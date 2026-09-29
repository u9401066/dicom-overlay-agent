# Scientific desktop paired regression — 2026-09-29

**Preparation checkpoint: 120 planned, zero model cases run at this checkpoint.**
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
