# Mid-analysis image replacement — 2026-09-24

## Reproduced defect

The real source App at clean `7f6214e` captured exposed development case
`meeti_44709848` through the owned Qt Viewer. While OpenClaw was interpreting A,
the actual file dialog loaded a same-size synthetic grid B. Window geometry
remained unchanged. The App nevertheless entered DISPLAYING and exported A's
findings while B was visible. Exported source RGB MAE was **0 against A**, but
**78.2869 against visible B**. Geometry validation alone cannot establish identity.

The failed run and its unmodified report/source remain preserved. Its four model
stages bind to Astra medium through the existing public usage/runtime collector.
This is an exposed partial-image UI regression case, not a clinical accuracy
measurement or a new blind-cohort case.

## Fix and boundaries

Before entering DISPLAYING, hide owned panels, revalidate target/projection and
capture **only the same authorized ROI**, translated with the Viewer if needed.
Compare exact decoded RGBA pixels and dimensions against the acquisition image.
PNG metadata may differ; even one changed pixel fails. A perceptual hash is not
used as identity proof. The additional capture stays local and is not sent to
OpenClaw. No extra model call, new dependency, Gateway change or schema change.

A changed, occluded, unacquirable or undecodable final image withholds the result:
no current-image report, regional QA or export. The App requests a fresh Analyze.
The last withheld snapshot/source/reason is retained as **one bounded in-memory
record**, replaced by the next rejection and lost at exit. It is not a durable
clinical audit or the still-incomplete canonical host evidence ledger.

This conservative check can reject a moving/blinking image even if clinically
equivalent. It adds a local ROI capture and a 0.4 s panel-hide beat, not a speed
improvement. It does not cancel model work early. Windows does not provide an
atomic capture-to-Qt-paint transaction; a change after the final check remains
subject to the existing display monitor. No universal race-free claim is made.

## Verification

Eight new regressions cover unchanged/changed images at identical geometry and
hash, pre/post ownership failure, capture/decode failure, pause during final hide,
PNG metadata and one-pixel changes. Related agent tests: **71 passed**. Full
explicit unit/integration/smoke: **1,724 passed, six conditional skips, 212.89 s**.
The skips are private/frozen/native opt-in checks, not credited as passes.

The actual Windows App was restarted with base `7f6214e` plus this source patch
(recorded dirty, not a frozen binary). At 150% scaling, the real file dialog again
changed A to B during analysis with unchanged window geometry. The result was
withheld, only ControlBar remained visible, and actual Export produced no stale
directory. Workflow time was 102.076 s.

A subsequent **unchanged-image** real GUI run published normally and actual
Export succeeded (95.601 s workflow). Exported source matched both the initial
and final visible ROI at RGB MAE **0**. The rendered summary was inspected and
showed Partial EKG Analysis / INDETERMINATE, not an unsupported normal result.
All four stages bind to Astra medium. This paired development check validates
publication behavior, not diagnostic accuracy or latency improvement.
Owned App/Viewer were closed through their UI; their PIDs and the owned Gateway
PID/listener were absent afterward. Ruff/format and all four documentation-link
checks pass. The preceding 7f6214e CI and secret-scan runs succeeded.

Runtime source SHA-256 before commit:

- `application/overlay_agent.py`: `3724f2435942b26ddfdfef22c577a8bd628d99f41f82b99e2f25774ddc4052e9`.
- `domain/services.py`: `c66f0c24da9a245237fd827f973b3d144c341b7d309391481e0e6b5b478839f4`.
- `infrastructure/screen_monitor.py`: `bfd38389686d777fc3a168ee3b3bf5884def415e58e9e42a260a653cad9db388`.

## Preserved local evidence

Outside repository:
`C:/Users/Ericlab/AppData/Local/Temp/dicom-image-race-20260924/` contains the original
`reproduce.py`, `before-fix-receipt.json`, bounded A/B screen captures, reusable
`verify.py`, `after-swap/receipt.json` and `after-same/receipt.json` plus captures.
The helper's `swap_utc` / `source-b-*` field names in the unchanged run mean the
control observation time/image; B was **not** loaded in that run.

- A input SHA-256: `35ef06c2d95a68889b960d91974a0e8fc9a9ecd467a4633bee1128322b679de0`.
- Synthetic B SHA-256: `a63d9a11262bbeee913f03f6dcf8231bbe143470486732aded811730db8daf58`.
- Failed report SHA-256: `5226e114559bff57c0bb92e244b91c5839add8123fdf02d7de69e8c25ff2de06`.
- Failed export: local isolated runtime `data/exports/desktop-20260924-140534-297609`.
- Positive report SHA-256: `eb1bf6a2b3bae015fd704777ae5a7820e2d25d421a7845537d06a5205f389fde`.
- Positive export: same runtime `data/exports/desktop-20260924-141718-768334`,
  including source, UI widgets and its public usage receipt. The withheld run
  intentionally has no current-image export/usage join; its runtime trace remains
  preserved, without claiming the in-memory rejected draft is a durable ledger.

No full-desktop image was transmitted. The preserved 6e6734e executable does not
contain this fix. Other DICOM viewers, physical mixed-DPI changes, native
ADD/dismissal, canonical evidence assembly and >=100 current-model clinical cases
remain separate acceptance gates.
