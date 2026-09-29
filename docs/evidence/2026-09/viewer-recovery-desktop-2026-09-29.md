# Actual source-App Viewer recovery: partial acceptance — 2026-09-29

App source `b3b4c1fb544573deaafb35a30ae74e9ca93b1d1b`. One previously exposed
deidentified image from the fixed 120-case manifest, not a new clinical case,
blind trial, accuracy result or rebuilt EXE. The earlier cohort remains
**10 publications, 2 technical failures, 108 pending**.

## Isolation and actual desktop actions

The prior App32116 was closed through its actual Quit button; its owned
Gateway7204, Viewer33040 and launchers were confirmed absent. The old runtime
is sealed and must not be restarted. Its final App log hash is
`3bb977307bb75ef0f684e3f6c077f5a1d9c761be03826293ebf914f0c6f5824c`.
Normal shutdown drained one queued Gateway message without the earlier timeout.

Fresh runtime `Ctemp/dicom-publication-recovery-b3b4c1f-20260929` copied the
pristine36dc3c6 payload and matched all18,771 files/tree hash before config/auth
writes. Python source was explicitly selected from the new worktree; no old
runtime hotpatching. New App15940, Viewer15016, Gateway8012, port18796.

- App-owned OAuth migration14.017s and profile check30.897s succeeded. Actual
  Settings showed the Astra subscription preset and medium reasoning. The
  observer did not read credentials, save the profile or request inference.
- The initial ROI setup was canceled before the automation's drag; the drag's
  ownership assertion therefore failed before any input/capture/model request.
  Settings > Set ROI reopened calibration. Native drag/Enter selected the same
  owned synthetic Viewer `(30,30)-(1530,1110)`,1500x1080 at150% DPI. The retained
  ROI preview was visually inspected. No whole-desktop screenshot or PHI.
- A real file dialog opened the predeclared exposed image. File-to-visible
  bilinear MAE0.5350713992. Actual Analyze captured this authorized ROI.
- At12:45:33.323439UTC the helper minimized only the bound owned Viewer, after
  App entered ANALYZING. No hidden-window pixels were captured.

Official [authentication](https://learn.chatgpt.com/docs/auth) and
[Astra model](https://developers.openai.com/api/docs/models/gpt-6-astra) pages
were checked using OpenAI Docs. They are background references, not proof of
account access or a guarantee about this third-party integration. The actual
App/public Gateway receipts establish the observed model route below.

## Observed recovery and retained observer failure

| App log event | UTC |
| --- | --- |
| CAPTURING to ANALYZING | 12:45:33.243158 |
| publication_waiting_for_viewer | 12:47:51.307665 |
| publication_viewer_restored | 12:47:52.341418 |
| ANALYZING to DISPLAYING | 12:47:53.707395 |
| DISPLAYING to PAUSED | 12:48:11.556439 |
| User dismissed / shutdown | 12:48:25.211987 |

The helper reached the wait event, but decoding its PowerShell UI-listing bytes
as UTF-8 failed on Chinese text (`UnicodeDecodeError`). Its failure cleanup
restored the same owned Viewer. The App then completed its existing pixel and
publication checks and displayed the result. The next real UI Automation query
observed the report, one finding, three rendered boxes, and Displaying result.
Recorded maximum box edge drift was0.696 physical pixels. This is coordinate
projection evidence, not validation of the clinical localization.

The immutable helper failure receipt remains a technical failure:
`c886215b8605bc34506c1904e6f48224d56a7feccfb22d749ba849255a725012`.
Plan hash: `266f8e5b7958af13e63cfa35f6385cb064eb437a4ccde517b668e269b4857711`.

Before the separate Export-only recovery helper could act, the App was paused
and closed through its UI. The App and Gateway processes were confirmed absent;
the helper could not find Export. The initiating actor is not established by
the log, and an asynchronous user question was sent. No automatic restart or
paid retry followed. The Viewer remained available at this checkpoint.

Therefore **full canary acceptance remains incomplete**: no waiting-state
screenshot and no final actual GUI Export/canonical artifact were retained.
The retained UI observation/logs prove more than an offline test, but cannot
substitute for those missing deliverables. The prepared report is not relabeled
as a fully verified export. Clinical content was not scored.

## Offline preservation and public usage

Host attempt `d14aec3b96a843e9a114888c0522a6e4` retains source pixels and all five
ordered terminal turns. After shutdown, the read-only public sessions CLI plus
retained runtime log bound all five to `openai/gpt-6-astra`, medium reasoning.
No sixth analysis turn, new inference or Gateway restart was used by collectors.

The retained source pixels equal the pre-inference visible ROI exactly. Hashes
of every retained turn/artifact were checked and unchanged after audit. An
offline replay of those five original bytes completed contract preflight; it
does not create a new GUI handoff or replace the missing original export.

Audit SHA256:
`f7fd7303009860555d8059e2e932ce6e4c6b89074f352a23ec36b5646b2bf6c4`.
Session counters remain usage snapshots, not a monetary bill.

## CI follow-up

Run36569163748 passed all four Windows/Linux Python3.11/3.12 compatibility jobs
and Linux tests, but Windows reported1failed/2645passed/12skipped. The failure
was the new deadline test: real10ms asyncio sleep can wake before the absolute
deadline on Windows, legitimately allowing the already-restored window.

The test now controls only this module's clock/sleep and explicitly tests exact
deadline and overshoot. Production deadline/identity/pixel logic is unchanged.
The first deterministic test revision over-asserted a withheld-snapshot object
when its fixture had no snapshot; corrected to observe the real withhold reason
while preserving the original implementation. The resulting55 focused tests
pass; Ruff passes. Original secret-scan run36569163761 passed. New CI results
must be checked separately rather than treating the original failed run as green.
