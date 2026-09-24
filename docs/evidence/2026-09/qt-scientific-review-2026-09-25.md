# Qt scientific review component — 2026-09-25

## Implemented and actually exercised

The new [Qt presenter](../../architecture/scientific-review-presentation.md) bridges
the existing async worker to a concrete frameless/top-most/draggable report panel.
It adds observation/evidence tabs and returns a bound availability receipt only
after painting, visibility/exposure and current run/source/content checks.
The full scientific session now has a test using this real queued presenter, not
a callback that simply returns a synthetic availability object. Its Gateway model
replies are still synthetic; this is not a new paid App inference run.

At native Windows **150% scaling**, the component was shown and its Report,
Observations and Evidence tabs were captured from the owned widget only. A real
Win32 mouse click on its close button hid the window, cleared the clinical text
and source binding and emitted exactly one invalidation. The cursor/DPI context
were restored and the owned window/worker closed afterward. No unrestricted
desktop capture or model submission occurred.

The first native run passed 1/1 in 2.65 s. All three screenshots were visually
inspected and exposed raw JSON quality text. Presentation was then improved to
human-readable adequacy/detail/limitations/view inventory without changing the
canonical data. The second native run passed **1/1 in 0.74 s**; its new Report
screenshot was inspected, and unchanged observation/evidence hashes checked.

Private artifacts are retained separately, without overwriting the first run:

- `C:/Users/Ericlab/AppData/Local/Temp/dicom-scientific-review-ui-20260925-055639/`
- `C:/Users/Ericlab/AppData/Local/Temp/dicom-scientific-review-ui-20260925-055931/`

Second-run widget screenshot SHA-256:

| View | SHA-256 |
| --- | --- |
| Report | `196731921defc9d1eb39a4e76e01f97e811194d46f8f4fac16eef4e8178a75c7` |
| Observations | `84a894fd47ad462353664432b89001e54da8af24129f3719d1c9b9dd1874f87a` |
| Evidence | `93984e89d0b541ef270105d939a3c5bda324a133379937e5c01786d42569a65e` |

All displayed content and source identifiers in this component test are synthetic.
The receipt explicitly records `whole_app_or_model_acceptance=false`.

## Edge tests and encountered defects

Focused presenter/overlay/geometry checks: **74 passed in 2.73 s**. Coverage
includes actual background-thread/queued-Qt operation, paint-before-acknowledge,
missing paint, timeout, cancellation before dispatch and while pending, stale
scope before/during/after rendering, rendering exceptions, changed content,
overlapping requests, thread-affinity construction, malformed digest, plain-text
injection handling, source detachment and session-to-final-contract integration.

The first run exposed a real Qt teardown event accessing cleared Python wrapper
attributes. The event filter now tolerates that lifecycle phase. Other initial
failures were test assumptions: the summary also includes the intentional
INDETERMINATE heading; a no-paint stub initially also omitted the content binding;
and Process displays title-cased stage names. Those expectations/fixtures were
corrected without weakening paint, content or scope checks.

Scientific workflow records now display their actual stages rather than an
uninstrumented zero model-usage count. Missing scientific layout metadata is not
reported as proof that all twelve ECG leads are absent. Legacy free-text quality
and its existing overlay/region behavior remain supported.

Changed-file Ruff/format and presenter mypy pass. Previous d7bd172's two CI and
two secret scans completed successfully before this checkpoint.

Full unit/smoke/integration regression completed **2,354 passed / eight explicit
skips in 408.18 s** (session 8481, exit 0). The extra skip is this new native-review
opt-in, exercised separately above; other skips retain the private-cohort,
portable-directory, packaged runtime and native capture/input conditions.
After that run, a final two-line lifecycle guard prevented restarting the scope
timer if a synchronous close had already revoked the window during rendering.
A new regression plus the presenter/overlay/geometry set then passed **75/75 in
2.92 s**, with presenter mypy and Ruff passing. The 2,354 count describes the
full run before that final focused follow-up, not an invented 2,355-test full run.
Documentation checks passed 12/12 in 0.10 s; initial staged secret scan was clean
over 47.33 KB. Original source/clinical artifacts and unrelated main edits remain.

## What this does not prove

This component is not yet wired into the default `__main__` analysis/publication
path. Actual complete App/OpenClaw staged inference, correct usage binding,
fresh-source checks before/after presentation, quality-only non-diagnostic UI,
matched external models, cross-monitor/DPI transitions, current EXE and clinical
acceptance remain open. A visibility receipt is not human review or approval.
Existing sealed clinical cohorts and their failures remain unchanged.
