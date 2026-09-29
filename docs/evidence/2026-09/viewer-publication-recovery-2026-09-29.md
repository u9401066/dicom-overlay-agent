# Bounded publication recovery — 2026-09-29

Source-only follow-up to the two retained scientific batch failures. The old
App and its frozen cohort method are unchanged: 10 publications, 2 technical
failures, 108 pending. Neither failed case was retried or relabeled successful.

## Behavior and boundaries

After scientific preparation, a temporarily unavailable Viewer keeps the App
in ANALYZING, with an explicit restore-and-verify status. Recovery uses only the
remaining original 180-second analysis deadline, not a new timeout or model
request. The native handle/process/class must equal the original capture target;
geometry, protected ROI capture and exact decoded source pixels are then checked
before preview and again before final publication.

The App does not restore windows itself, capture minimized windows, select a
replacement target or widen the authorized ROI. Pause, stop, cancellation, ROI
reset, changed identity/pixels, occlusion and deadline expiry withhold the draft.
Older adapters without native identity still fail closed on target loss, now
explicitly clearing stale internal results rather than silently returning.

No Gateway schema, prompt, clinical rules, dependencies or bundle exclusions
changed. This preserves the domain boundary and the four maintenance cores.

## Checks and limits

- New recovery and identity units: 26 passed, including stale queued UI status.
- Existing agent/capture/window checks: 187 passed (overlapping focused groups
  are not added together as a full-suite total).
- Regional UI/geometry/question/history/writeback/export checks: 129 passed in
  1.22 seconds; separate integration directory: 61 passed in 0.45 seconds.
- Native Windows: 5 passed in 4.55 seconds. Four exercise actual blank-origin
  Mark drags, reverse direction, clipping and input pass-through. One minimizes
  and restores a uniquely owned synthetic window through Win32 and the actual
  recovery helper. No model calls or desktop screenshots occur in these tests.
- Initial full regression: 2450 passed, 27 failed, 103 errors, 13 skipped.
  A direct Node import reproduced missing repo-local `openclaw` in the new
  worktree. Installed the lockfile with the CI `npm ci --ignore-scripts` recipe;
  initial system Node 25 emitted engine warnings, so the subsequent suite uses
  existing pinned Node 24.18.0. This environment failure is retained, not hidden.
- Ruff passes. Targeted mypy passes with `import-untyped` disabled; a first run
  without that option reports the existing missing `win32process` type stubs.

The full regression rerun passed: **2585 passed, 12 skipped in 531.66 seconds**,
using Node24.18.0. The five native input/recovery checks above separately cover
their opt-in skips; other frozen/private/interactive skips remain explicit.
JUnit receipt: `data/tmp/publication-recovery-regression.xml` (local artifact).
A fresh actual App/subscription recovery acceptance remains pending.
The subsequent [actual source-App canary](viewer-recovery-desktop-2026-09-29.md)
observed recovery/publication and bound five real turns, but retains observer
failure and missing final export; it is partial, not full acceptance.
Native fixture success is not evidence of a
new paid full-App run, clinical improvement, rebuilt EXE or released binary.

## User-reported Mark and regional QA

The correct Mark surface is the entire authorized image ROI, not just AI boxes
and not the unrestricted desktop. Main `1c531a5` still has the reproduced alpha
hit-test hole; candidate fix `6be42cb` paints an almost-transparent ROI-only
input surface in Mark mode. The older installed EXE was not silently replaced.

The already completed [actual frozen EXE acceptance](frozen-regional-context-2026-09-29.md)
at `36dc3c6` covers blank-origin marking, two questions on the same manual region,
an independent existing-AI-region question, unchanged history on reopen without
inference, and invalidation after changing the source image. The retained
App-owned chat PNG was visually inspected again during this checkpoint.
Each question binds its selected crop plus the same original authorized ROI;
these are not new live screen captures. Full history is exported in JSON, while
model context is bounded to six pairs/12,000 characters. Restart-restorable
conversations and broad vendor/multi-monitor acceptance remain unfinished.
