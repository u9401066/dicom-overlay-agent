# Opt-in scientific desktop publication — 2026-09-25

The actual agent and main callback now connect the scientific session to the Qt
presenter. This checkpoint uses synthetic source pixels/Gateway replies, not a
new paid whole-App run or clinical acceptance. Default analysis is unchanged.
See [activation and limitations](../../architecture/scientific-review-presentation.md).

## Publication and manual review boundaries

- Both `--scientific-review --deidentified-input` are required; ROI stays bounded.
- One reader owns the original ROI and five sequential requests. No legacy
  decoder, automatic paid retry or fallback is invoked by this mode.
- Prepared content is unavailable to regional QA/Export. Geometry and exact
  pixels are checked before presentation and again after preview retirement.
- The queued Qt availability receipt binds run/source/content. Retirement is an
  ownership transfer, not approval; close, pause, cancellation, replaced content
  and stale scope cannot publish a final report.
- Full canonical validation and source SHA checks precede canonical export.
  Human edits retain review context but remove the canonical ledger claim until
  reconciliation. The immutable original scientific session remains retained.
- Non-diagnostic quality, timeout, connection and interpretation failures are
  reported truthfully, with manual retry only and no invented normal report.

## Checks

Focused publication/Qt/pixel tests: **54 passed in 7.13 s**. This includes the exact
`__main__` callback, actual AsyncBridge/Qt paint/retirement, actual reader/session/
agent, and synthetic Gateway responses. It is not an OAuth or live-model test.

The initial new tests had three fixture failures, not three production defects:
two changed white PNG encoding to white JPEG without changing pixels; another
omitted the required local-signal audit for explicit finding retraction. Changed
pixel fixtures now change one pixel; the retraction passes a synthetic accepted
audit rather than weakening the production gate.

For the user's manual-Mark report, the actual native Windows mouse smoke again
passed **1/1 in 1.08 s**, starting in a blank ROI with zero AI boxes and checking
outside-ROI/passive pass-through. Regional UI/geometry/QA/writeback/export:
**121 passed in 1.13 s**. An initial command used the wrong directory for the
export smoke and collected no tests; the corrected command produced this result.

Two additional native Mark runs used per-process `QT_SCALE_FACTOR` on the same
150% Windows desktop: `0.6666666667` reported effective Qt DPR 1.00000000005
(1 passed, 1.07 s), and `1.3333333333` reported DPR 1.99999999995 (1 passed, 1.05 s).
Both drove actual Win32 mouse input, checked the normalized new region and input
pass-through. No global display setting changed. These exercise Qt coordinate
scaling, not physical-monitor transitions or native OS 100%/200% acceptance.

The previously sealed three-turn manual promotion screenshot and audit were
reopened and inspected, not regenerated. See the [branch comparison](manual-mark-branch-comparison-2026-09-25.md)
and [actual promotion replay](native-marker-promotion-2026-09-24.md). Candidate
source, main and the older EXE are still distinct delivery states.

## Open gates

No new EXE, model-usage claim, speedup, clinical-score gain or whole-App acceptance.
Legacy clinical-rule hooks, independent waveform matching/classification,
quality-only review UI, durable raw-receipt export and current-model desktop
acceptance remain open. The unchanged sealed 120-case batch failed clinical
acceptance. The full source-image second look must not be described as a zoom.

Prior `edc75df` CI runs 36065643575/36065638623 and secret scans
36065643567/36065638624 were verified completed/success; these are prior-commit
checks, not evidence for this new implementation.

Native Windows 150% review plus exact App-callback handoff: **2 passed in 1.88 s**
(session 70294 terminal exit 0). Fresh private artifacts are in
`C:/Users/Ericlab/AppData/Local/Temp/dicom-scientific-publication-ui-20260925-062908`.
Only the owned synthetic widget was captured. The report was visually inspected;
all three screenshot hashes match the earlier component checkpoint. Actual native
close clears and revokes the preview. This is still not a whole-App/model test.

Initial full run: 2,373 passed / 8 skipped / 1 failed in 248.60 s. The staging
failure was the pinned OpenClaw CLI rejecting global Node 25.6.1; a diagnostic
smoke run (439 passed / 7 skipped / 1 failed, 247.96 s) used the same unsupported PATH.
A fresh final full run uses existing
portable Node 24.18.0. No global install, pinned-runtime change, test weakening or
sealed Gateway restart was used to address the environment failure.

Final full unit/smoke/integration rerun: **2,378 passed / 8 explicit skips in
417.97 s**, session 57401 terminal exit 0. Native input/review opt-ins were run
separately as recorded above; frozen bundle/capture/cohort gates remain skipped.
Ruff/format, six changed production modules' mypy (including main), documentation
12 tests and staged secret scan pass. No dependency or packaged-size change is
claimed; the current source has not been rebuilt into a new EXE.
