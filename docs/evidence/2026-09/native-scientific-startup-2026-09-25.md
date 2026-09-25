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

## Third actual run: quality accepted, checklist reference gate stops blind pass

Clean `88556d2` used a third isolated runtime,
`C:/Users/Ericlab/AppData/Local/Temp/dicom-scientific-desktop-20260925-session-key`.
App19576/launcher28316/Gateway6688 again used Viewer7832, actual Open dialog and
Analyze. This time the quality reply passed transport and QC, and the App sent
the blind-pass request. The run stopped after57.040s at
`unsupported_checklist_observation`, before localization, reconciliation,
second look, Qt handoff or report export.

Public usage/history and matching runtime session IDs verify two Astra-medium
turns, not five: QC `a48c13f5-6e87-4d89-8aa4-cb359c2c3d4f` (log55) and blind
`94d03518-0173-4be6-970f-fe9ea0d2d0d3` (log208). Snapshots preserve QC
inputTokens6728/outputTokens203/totalTokens6728 and blind
inputTokens8978/outputTokens2095/totalTokens8978 literally; these are not a billing
ledger or additive monetary charges. No optional classifier was run.

The visible blind response links several checklist entries using comma-separated
IDs: ischemia and t_wave use `o5, o6`, qrs_duration and st_segment use `o3, o7`,
rhythm uses `o1, o2`. Those are not single existing observation IDs. Both the
current public canonical validator and App draft decoder require a single ID in
`ChecklistItem.evidence`, although its JSON Schema only describes a string. This
is a reference-representation mismatch, not evidence of clinical correctness or
of a clinically false observation.

The public history truncates the longer blind text (the returned string ends
midway through next_steps and includes a truncation marker). It cannot replay
the complete original JSON; it was not repaired or credited as a complete raw
receipt. Exact full output persistence remains an integration gap. The shown
checklist fields and the actual App exception support the narrower diagnosis.

Next work must explicitly model multi-observation references across public types,
schema, semantic validation, prompt and App adapter, while retaining strict
resolved/supported-observation checks and legacy compatibility. Existing receipts
must remain unchanged; acceptance needs a fresh real App run. Full five-stage,
native localization, report UI and regional QA under this mode remain unverified.

The public receipt query sent zero additional model requests. App Quit used its
actual UI, and App/launcher/Gateway and18796 listener were confirmed absent.
Viewer was retained. Never restart this third sealed runtime either.

- Attempt receipt SHA-256:
  `f2f0397d241caac25b33059ccdee6780f51c37aa9f1576a71b09b0435ca131b8`.
- Public usage receipt SHA-256:
  `cc158d978af905c879fe2ebc19216c460c22eb565674c557ac5e0ce056167d34`.
- Private public-query directory: `public-evidence-20260924-230743` under the
  third runtime's parent. It contains a visible-history projection, not the full
  original Gateway stream, and must not be published with its private config.

Final canonical-session source full suite: **2384 passed /8 skipped in417.52s**,
session91342 terminal0. Documentation12pass0.10s, client mypy/Ruff and staged
10.32KB secret scan pass. Earlier53a32a8 both CI+secret runs completed success.
Canonical-session88556d2 CI36070777879/36070773640 and secret scans
36070777815/36070773698 also completed successfully. Final documentation-only
checkpoint recheck:12 passed in0.09s; `git diff --check` clean.
No new EXE, clinical-score improvement or completed five-stage App claim.
