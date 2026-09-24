# Actual scientific desktop startup: missing receipt collection — 2026-09-25

This is a real App failure, not a successful model read. Clean source `be27473`
was launched with both scientific development flags in a fresh isolated runtime,
with the actual Viewer and an existing host-cleared partial ECG. No baseline or
sealed runtime was restarted or changed.

## Actual actions and result

- Actual App PID 10612, launcher 35696, Gateway 16428, Viewer 7832, loopback 18796.
- Fresh pinned OAuth migration succeeded in 97.846 s, public profile check in
  37.532 s; Gateway readiness was separately observed. These are cold-start
  measurements, not inference timings or a controlled speed comparison.
- The real file dialog opened `crop_top_20` from the answer-free partial ECG v2
  corpus. Input SHA-256:
  `8a8da6c8e2eafc621fbd2735181e9430069d296cbf5421a046a6df51d2f668bd`.
- The authorized viewer-relative ROI was `(30,30,1500,864)` on the 150% Windows
  desktop; file-to-visible resampling MAE was 0.475658. This does not prove
  export identity, because no final result/export was produced.
- Actual Analyze captured the ROI and connected to Gateway, then failed before
  the first `chat.send` with `gateway_evidence_collection_required`.
  UI accessibility reported the expected unpublished-result error and AI ready.
- The missing production option was `collect_transport_evidence=scientific_mode`
  in `__main__`'s actual OpenClawClient construction. Synthetic fixtures had
  enabled it independently and therefore concealed the integration omission.
- There were zero embedded-run-start log entries. The observed exception occurs
  before frame creation/send. No paid inference was repeated or claimed.
- The owned control-bar PrintWindow capture was entirely black; it is retained
  as a failed screenshot, not visual evidence that its text was readable.
- Quit was invoked through the real UI. App/launcher/Gateway processes and the
  owned listener were subsequently absent. Viewer was retained.

Private immutable attempt artifacts:
`C:/Users/Ericlab/AppData/Local/Temp/dicom-scientific-desktop-20260925-be27473`.
Do not restart this runtime: Gateway startup truncates its log.

## Correction and stronger regression

The App now explicitly enables transport receipt collection only in scientific
mode. The strict requirement remains; no parser/schema/safety gate is relaxed.
The new test executes the actual main constructor AST with the real client and
then uses that constructed client throughout the existing scientific tests.
Before correction: one pass / one failure, specifically enabled mode. After the
one-line production correction: 74 focused tests passed in 5.94 s; Ruff/mypy pass.

A fresh second runtime is prepared separately. Full tests and the corrected live
attempt are pending at this checkpoint; no scientific model acceptance is claimed.
The previous `be27473` two CI runs and both secret scans completed successfully,
illustrating why those checks alone did not prove actual desktop integration.
