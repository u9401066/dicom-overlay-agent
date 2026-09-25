# Scientific review availability on the Qt thread

`presentation.scientific_review` supplies the concrete Qt presentation adapter for
`ScientificImageSession.offer_review()`. The default App analysis path is unchanged.
An explicit development mode now wires this adapter into `__main__` and the actual
agent publication boundary; live model acceptance of that mode remains pending.

## Explicit development activation

```powershell
uv run python -m dicom_overlay --scientific-review --deidentified-input
```

Both flags are required together. The second is the operator's assertion that the
selected test input is already de-identified, not an automatic de-identification
service or permission to capture outside the authorized ROI. Use only trusted,
de-identified development images. Normal window selection and ROI checks still apply.
Do not enable this mode for clinical care: it uses strict scientific stage parsing
but does not yet run the legacy clinical-consistency hook chain. Legacy multi-pass
Settings do not select its stages; the shared client's fast-mode setting still applies.
It makes five sequential Gateway requests on a complete run, with no automatic
paid retry or legacy fallback. Non-diagnostic QC stops after the first request.

The agent performs geometry/exact-pixel validation, keeps the prepared snapshot
unavailable to Export and regional QA, then requests Qt presentation. The exact
App callback retires the acknowledged preview before a second unoccluded ROI
pixel check. Only then can the final validated contract enter DISPLAYING and the
normal report/QA/export path. Availability is not physician approval. Failed,
cancelled or stale attempts require an explicit new Analyze action.

Canonical export adds `scientific-result.json` only after full contract and source
SHA validation. Manual annotations remain separate context. Applying a regional
finding edit clears the canonical ledger claim and exports a draft marked
`requires_reconciliation`; it never silently represents a human edit as a newly
validated scientific run. The original session remains in memory, not yet a
durable raw-receipt archive.

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
`invalidated(run_id)`. The opt-in App wiring uses that signal to withhold
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

## Readability and remaining integration

Structured quality is rendered as adequacy, detail, limitations and view inventory,
not a raw JSON dictionary. The original quality record is unchanged. A scientific
draft without layout metadata no longer claims all twelve leads are absent.
Its Process tab shows actual workflow records and explicitly requires separate
model-usage receipts instead of displaying an inferred zero model-call count.

Whole-App/model acceptance, independent waveform matching/classification, legacy
clinical-rule integration, raw-receipt persistence and default activation remain
open. Non-diagnostic QC currently shows a specific control-bar error, not a full
quality-only review panel. The second look uses the full source ROI, not a zoom.
Do not feed prepared content through legacy normalization that mutates bindings.

See [native component evidence](../evidence/2026-09/qt-scientific-review-2026-09-25.md).
See [desktop publication tests](../evidence/2026-09/scientific-desktop-publication-2026-09-25.md).
