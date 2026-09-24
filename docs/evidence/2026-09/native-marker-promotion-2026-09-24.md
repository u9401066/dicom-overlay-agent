# Actual manual marker promotion, dismissal and follow-up — 2026-09-24

This closes the specific native interaction gap left by the
[promotion-history source fix](interaction-package-and-promotion-2026-09-24.md).
It is an exposed development replay, not a clinical accuracy/acceptance case.

## Environment and real actions

Clean source App `243f2efcddfdd8c5c85fc6963a4abc30b98ea65f`, actual Qt Viewer,
2560×1600 Windows desktop at 150% scaling, existing isolated OpenClaw 2026.9.3
subscription runtime. No source edits or direct analyzer calls during the run.
All inference began through actual App controls. Existing exposed/de-identified
case `meeti_44709848` was opened through the real file dialog.

Authorized capture was `(150,81,1370,708)` inside the owned Viewer. Baseline source
matched the bounded visible ROI at RGB MAE **0**. Baseline workflow took 86.482 s
(reported inference 82.243 s). Partial/unlabeled input remained INDETERMINATE.
Neither this timing nor these answers prove improved clinical accuracy.

Actual Mark plus native mouse drag `(1100,170)`–`(1380,420)` started outside both
existing AI boxes. The question requested an addition only if supported, with no
invented lead or diagnosis. OpenClaw produced a real ADD suggestion; no model
response or proposal was injected to force the tested path.

| Step | Actual GUI action | Verified result |
| --- | --- | --- |
| First proposal | Ask through Reviewer annotation dialog | ADD suggestion; original AI finding unchanged; separate manual marker retained |
| Reject | Dismiss | Same findings and conversation; `dismissed/add` audit event |
| Second proposal | Inline follow-up Send | Second ADD suggestion; both turns retained |
| Accept | Apply to report | New `review-3a1672872360` finding; manual marker consumed; original finding unchanged |
| Reopen | Inspect + physical click `(1240,300)` | Same two-turn history under new finding ID; no new analysis-trace entry |
| Continue | Third inline question | Third answer, `no_change/none`; no duplicate or altered finding |

The new finding keeps exactly the manually selected normalized source rectangle:
`x=0.6925601750547046, y=0.125, w=0.20459518599562362, h=0.3538135593220339`.
This is a reviewer-selected region, not a claim that the model independently
localized a precise lesion. Rendered overlay and final chat-panel images were
visually inspected. History remains review context, not verified clinical evidence.

Three conversation IDs join, in order, to the final report's interaction audit:

- `434e55dac5f6466aa9ee0e2a86fb4cfb`: dismissed ADD, not applied.
- `fa9813e15e9d45379f31b37eac3ce113`: applied ADD to the new finding.
- `743502763d094100b6d1e78c4438b719`: no change after promotion.

Ten stages (four initial and two per regional turn) bind to Astra medium through
runtime observations/public usage receipts. No API key, provider substitution,
full-desktop transmission, PACS writeback or clinical report signing was involved.
The local draft exports are development test artifacts, not clinical handoffs.

## Audit details and limits

Each stage was exported using the real Export button. Before approval, exports
contain one AI finding **plus** a `source=user` manual annotation; after approval,
they contain the original finding plus the promoted finding. A total count of two
alone would not prove that a proposal had been applied; IDs, source, geometry,
history and audit events were compared explicitly.

The first local audit incorrectly expected the manual annotation's latest
question/answer/detail to stay unchanged after a second question. Inspection found
only those three expected context fields changed; original AI finding and manual
identity/geometry did not. The audit was corrected to assert that exact difference,
without changing any exported artifact. The initial automation helper also missed
the owned dialog because it was nested under the control window; traversing that
owned tree submitted the existing dialog, without repeating the model request.

All seven exports share identical source bytes. Promotion preserves the first two
turns exactly, reopening preserves the complete history/analysis trace, and the
third turn stays bound to the promoted ID. The independently computed audit passes.
This does not prove that every model response, cancellation, multi-monitor or
cross-DPI scenario behaves identically. The canonical medical evidence ledger and
>=100 diverse current-model GUI cases remain incomplete.

## Preserved evidence

Outside repository: `C:/Users/Ericlab/AppData/Local/Temp/dicom-promotion-20260924/`
contains the baseline script/ROI/receipt, dialog and export helpers, stage pointers
with hashes, and `audit.py` / `audit.json`. UI accessibility observations are in
ignored `data/tmp/regional-ui-promotion243{first,second,reopened,third}.json`.

Final local isolated-runtime export:
`data/tmp/live-interaction-74d6ee9/DICOMOverlayAgent/data/exports/desktop-20260924-142735-097445`.

- Input file SHA-256: `35ef06c2d95a68889b960d91974a0e8fc9a9ecd467a4633bee1128322b679de0`.
- Captured source SHA-256: `cce82cb830055010eed9296e5c4cb7146e9b46ac2658c2e4ccf7603adc6f8e94`.
- Final result SHA-256: `f32afb936bc81fe7e9c7bcfd309a613580295b6eab942eda564ff0f2ed2c8369`.
- Conversation SHA-256: `d631fd86554579e1976f361a0fdb3285c026dae9b6296206590c881e42927063`.
- Usage receipt SHA-256: `4f54a341b0d07257f2ce5bab1d711f16e1c4717fcb60862e0a331b845d2d12b3`.

Both 243f2ef CI runs (36011990145, 36011999995) and both secret scans completed
successfully. Its full local suite was 1,724 passed / six explicit skips. This
checkpoint adds real-GUI evidence, not a new App implementation or binary release.
Documentation links and regional callback/history/turn-linkage checks: **33 passed
in 0.34 s**. Owned App and Viewer closed through their UI; App/Viewer/Gateway PIDs
and the owned port listener were absent afterward.
The preserved 6e6734e EXE has not been refreshed or natively tested by this run.
