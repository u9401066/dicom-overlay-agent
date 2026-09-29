# Scientific desktop and regional QA — 2026-09-29

## Actual source-App scope

Clean `e9e1346d7964d1659c2c2d100d652fbc43092e3b`, public harness pin d9798da,
Windows150%/2560x1600, App6444, Viewer29948, Gateway6768/18796. Fresh private
`C:/Users/Ericlab/AppData/Local/Temp/dicom-scientific-desktop-20260929-publication`
copied static runtime assets only, not old auth/logs/sessions. Explicit flags:
`--scientific-review --deidentified-input`. This is source App, not a new EXE.

The existing exposed `crop_top_20` ECG is one deidentified source, not a new blind
case or clinical acceptance cohort. The real Viewer file dialog, App Analyze,
mouse interactions and App Export were used. No driver sent model requests.
The initial attempt stopped in foreground-window preflight before inference;
its failed receipt is retained. A separately named pre-inference retry completed.
An observer first failed under PowerShell5's UTF-8 parsing; invoking it with
PowerShell7 read the existing answer without another inference request.

## Five-stage result, publication and export

Actual open/analyze/export wall time: **147.516s**, unchanged total analysis
budget180s. Cold OAuth88.873s/profile37.394s and Gateway startup are separate;
this single replay is not a controlled speed or accuracy comparison.

| Stage | Actual run ID | Elapsed ms |
| --- | --- | ---: |
| QC | d16324b9-e6e0-4bea-a995-317e64558a23 | 15874 |
| Blind | b1a8afbc-0c9b-44bf-8ad8-4fb8c67029e1 | 47681 |
| Native geometry | e491c07e-864a-4112-8f99-5d997b227682 | 15472 |
| Reconcile | ed32d4ab-72a4-423a-afb5-593e00999182 | 29264 |
| Second look | 18c54a96-12dd-45bf-a1c6-76faa568cea8 | 29525 |

The exported canonical result passes the unchanged public validator and contains
the actual ordered intake/QC/blind/native/reconcile/second-look/validation/handoff
events. Qt availability, both publication pixel checks, DISPLAYING, and real
Export completed. Human handoff means review availability, not clinician approval.
Five boxes render across2 findings, with reported projection drift below1px;
that does not establish clinical localization accuracy.

Authorized ROI `(30,30)-(1530,894)` is1500x864. File-to-visible MAE0.4756584362;
visible-to-export MAE0. Source SHA256:
`ddea0ab61ffb49c055d2f083c8f9aee1cf58233d63780162e36715eefe8b6532`.
Canonical SHA256:
`6ca10fe53147fb6b02fc6b8ebf232ead435ad02c27076490917122d8da53cf60`.
Original export: `runtime/data/exports/desktop-20260929-075636-394540`.
Actual summary/chat widget renders were visually inspected; capture exclusion
remained enabled, and no unrestricted desktop screenshot was taken.

## Manual and existing-region conversation

1. Clicked Mark, physically dragged `(950,710)` to `(1200,865)`, starting outside
   every AI box. Real Reviewer annotation opened and submitted the question.
2. Read the actual ChatPanel answer; submitted a second question through its
   inline field/Send. The answer continued that manual region's context.
3. Selected existing f1 through Inspect at `(525,400)` and asked a separate
   question. Its71x24 source crop skipped low-resolution refinement explicitly;
   the answer described the visible deflection and limits without claiming the
   crop independently proves the full finding.
4. Re-selected the manual region at `(1075,790)`. Its two-turn history reopened
   immediately; the chat rendering is byte-identical to the earlier second answer.
   Both threads and report interaction trace remain unchanged on reopening.
5. Opened `crop_bottom_20` through the actual Viewer file dialog. Old overlay,
   summary and chat disappeared. Export produced no stale artifact. No model
   request was made for the replacement image.

Manual normalized rectangle `(0.613,0.7864583333,0.167,0.1805555556)` maps back
within0.5 physical pixel of every commanded edge. Mark covers the authorized
image ROI, not unrestricted desktop pixels. The two conversations remain
separate with lengths2 and1. All3 review-turn IDs join to `no_change`,
`user_confirmed=false`; original AI findings and canonical result are unchanged:

- `786c4c5b186647abafb73c5db04149b9`
- `2a6dc719ef8f405f81e407b42b7659ab`
- `e00538f5f04c489aac3b5c767e7033e4`

Final reopened export: `desktop-20260929-075952-989305`; regional conversation
SHA256 `6131bb4d6988f454711afaf20a0ec9f0689966d458aa6e09b5a24507d1b85ea6`.
Offline `regional-audit.json` revalidates source/code/artifact hashes, full
canonical contract, geometry, separate history, turn joins and unchanged report.
Audit SHA256 `ddc7e750ab3c504639a01ac8bf82415b52b7e74ac71d9870429b5bad39fa59b2`.

## Usage, cleanup and limits

Read-only public session/history queries completed before shutdown and bind all
10 actual model sessions (5 scientific plus5 regional) to `openai/gpt-6-astra`,
reasoning medium. No API key or model substitution. Private usage receipt:
`public-evidence-20260929-080018/receipt.json`, SHA256
`9c555214d60db27e30a152177fa858d0d06f6a28a212f0b76dc3d00312c226b7`.
Snapshots are not an additive billing ledger; never publish query credentials.

App Quit and owned Viewer close were invoked. WebSocket graceful close hit its
bounded2s timeout, then the owned Gateway stopped. App/Viewer/launcher processes
and18796 listener are absent. Runtime is sealed; never restart it.

Local publication/guard/docs39pass4.51s, mypy/Ruff and secret scan passed. Both
remote e9e1346 CI runs and secret scans passed. No visible Qt regression suite
ran alongside this acceptance. The earlier generic publication failure is not
retroactively attributed to a proven cause; new logs retain fixed safe categories.

Still open: updated packaged EXE and Pages publication; current-model >=100-case
clinical acceptance; waveform matching/external classifier integration; broader
vendor/DPI scenarios. Tiny selected boxes can lose lead/beat context and cannot
support a full regional diagnosis. The report header still displays the last
model-stage duration (29525ms), not total workflow time, and `openclaw-unverified`
until separate runtime usage binding; both need clearer UI treatment. Conversation
context is bounded to the last6 turns/12000 characters although full visible/export
history is retained; no automatic session restoration is implemented.
