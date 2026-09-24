# Actual scientific desktop startup and Gateway identity — 2026-09-25

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

## Second actual App run: public canonical session identity

Clean `53a32a8` ran in a second fresh runtime at
`C:/Users/Ericlab/AppData/Local/Temp/dicom-scientific-desktop-20260925-receipts-fix`.
App9468/launcher14048/Gateway24572 used the same owned Viewer and input, through
its actual file dialog and Analyze control. The private attempt ended after
18.583 s with no final report/export: `gateway_session_identity_changed`.

This time there was **one actual Astra-medium request**. The public session query
and read-only `chat.history` agree on
`agent:main:image-evidence-b06e76fe-6964-44bf-87b6-79bf22c9af01`, session ID
`0892cf26-6846-4599-af23-84152f026632`. Runtime log line56 independently records
the same session, `openai/gpt-6-astra` and `thinking=medium`; its run finished
without abort. This is not a five-stage success or clinical-accuracy claim.

The returned quality JSON is `limited`. Its visible-label inventory includes
the clipped III trace and aVR/aVL/aVF/V1–V6, with missing I/II and unavailable
calibration/speed/gain recorded as limitations. The stored visible ROI was opened
and visually inspected. The JSON separately passes the public quality schema
post hoc; the App had rejected its transport receipt before advancing QC.

- Raw visible model-text SHA-256:
  `16080d941a97dcb0a47c4d5968667db25fbe7760f43f39cddcaa6ece82a6e1ef`.
- Public user-message source binding:
  `ddea0ab61ffb49c055d2f083c8f9aee1cf58233d63780162e36715eefe8b6532`.
  Public history did not expose a standalone image attachment in the inspected
  user fields; this alone is not complete image-payload/export-identity proof.
- Attempt receipt SHA-256:
  `4b2abcc00d929db3e3411127ea1674846a3b7d217ee5eefab6f53fbf6abaccd9`.
- Public usage receipt SHA-256:
  `92abeb338e93a9641eb1410f424eef68bb575873b5e3c32bdf77855b42acb9fc`.
  Snapshot fields were inputTokens6733, outputTokens193, totalTokens6733. They
  are preserved literally, not added together or represented as monetary charges.

The initial read-only history CLI probe rejected `--url` without explicit
credentials. A private query-only configuration set the correct port instead,
without changing the running App or exposing a token in process arguments. The
second query succeeded; neither query sent a model request. Thinking/reasoning
blocks are excluded from the saved visible-history projection. Private query
configuration/auth artifacts must never be published.

The scientific sender now names `agent:main:` explicitly instead of asking the
Gateway to canonicalize a short key. Collector equality is unchanged; foreign,
case-changed and whitespace-altered agent identities still fail. Canonical-key
regression before fix:1 failed/3 passed. After correction:195 focused tests passed
in9.35s; client mypy/Ruff pass. The previous receipt-option source full run was
2380passed/8skipped394.75s; the new full run remains pending.

App Quit was invoked through its real control; App/launcher/Gateway and18796
listener were confirmed absent afterward. Do not restart this sealed runtime.
Corrected live five-stage execution is still pending in a third isolated runtime.
