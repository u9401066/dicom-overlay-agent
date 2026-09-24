# Scientific review availability on the Qt thread

`presentation.scientific_review` supplies the concrete Qt presentation adapter for
`ScientificImageSession.offer_review()`. It does not yet replace the default App
analysis path or wire itself into `__main__`.

## Thread and content boundary

Create `ScientificReviewPanel` and `QtReviewPresenter` on the QApplication thread.
Call the presenter from the existing background `AsyncBridge`; it queues a Qt
signal carrying a detached preflight snapshot and a concurrent future. It never
touches a QWidget from the worker thread or blocks the GUI on a future result.

The panel inherits the App's frameless, top-most, draggable `SummaryPanel` and its
capture protection. It adds read-only Observations/Evidence tabs and an explicit
draft/review state. The existing Report/Checklist/Process tabs remain available.
Clinical/model text remains plain text, never HTML or executable instructions.
The panel checks preflight validity and content SHA before rendering. Replacing
its result through the inherited API clears its content binding.

Availability is returned only after a native Qt paint event, a visible/exposed
window, matching rendered-content binding and a second live-scope check. This
proves that the component was made available, not that a physician read, understood
or approved it, nor that another window cannot later obscure it.

The callback returns the existing bounded run/source/content/surface JSON receipt.
Only the session's subsequent full canonical validation permits `final_result`.
The presenter has no signing, clinical writeback or export controls.

## Host responsibilities that cannot be omitted

The required `is_current(run_id, source_sha256)` callback executes on the Qt
thread. It must bind the request to the active analysis revision and approved ROI
source. An unconditional true callback is appropriate only in an explicitly
synthetic test, never production. The host still owns geometry and exact-pixel
revalidation before initial display and final publication.

The presenter checks scope before display, before acknowledgement and every
100 ms while visible. Scope expiry, changed content, window hiding/closing or
explicit `invalidate()` clears the displayed text/binding and emits
`invalidated(run_id)`. The eventual App wiring must use that signal to withhold
its associated publication/export too; clearing this panel alone cannot revoke
an already copied result held elsewhere.

Queued cancellation cannot open a late window. Cancellation during presentation,
timeout (15 s default), failed rendering, malformed prepared content and failed
scope checks cannot acknowledge availability. A second request cannot replace an
active surface. Late cancellation of another request cannot close its owner.

The host must retain the presenter for its UI lifetime and revoke it before
shutdown/source changes. Qt teardown events tolerate cleared Python attributes.
The previous runtime evidence and sealed Gateway logs must not be restarted or
overwritten to test this adapter.

## Readability and next integration

Structured quality is rendered as adequacy, detail, limitations and view inventory,
not a raw JSON dictionary. The original quality record is unchanged. A scientific
draft without layout metadata no longer claims all twelve leads are absent.
Its Process tab shows actual workflow records and explicitly requires separate
model-usage receipts instead of displaying an inferred zero model-call count.

Next, connect this presenter at the existing agent's post-analysis
geometry/pixel-validation boundary, with distinct prepared versus final states.
Do not render directly inside `analyze()` before that boundary or feed prepared
scientific content through legacy normalization that can mutate its bindings.
Preserve canvas QA, bbox mapping/fallback, capture exclusion, stale-image
invalidation and explicit approval for report edits. Non-diagnostic QC still
needs a truthful quality-only presentation, not fabricated observations.

See [native component evidence](../evidence/2026-09/qt-scientific-review-2026-09-25.md).
