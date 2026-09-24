# External-window selection and cautious headings — September 24, 2026

Source development checkpoint; not a refreshed executable or completed browser
clinical acceptance run. Previous regional-history checkpoint `402d539` has green
push/PR CI (35988586226 / 35988592311) and secret scans (35988586222 / 35988592327).

## Explicit window selection

Settings → **Choose image window** lists visible external top-level windows and
requires an explicit selection. The browser or other image application need not
contain “DICOM” or “Viewer” in its title. Discovery/identity checks stay in the
infrastructure layer; the application invalidates old review state and requires a
new ROI; presentation owns only the picker. Domain values import no GUI/network.

Selection is **session-local**. The App pins the handle, process and window class,
allows title changes, and never falls back to another keyword match while pinned.
Detected destruction/identity change latches a failure until the user reselects;
minimized/invisible windows are unavailable. A failed reselection leaves the old
valid binding intact. Desktop shells, App-owned windows and owned transient
popups cannot be selected as source image windows. Existing pre/post capture
geometry, client-boundary and occlusion checks remain mandatory. These checks do
not make desktop capture atomic or eliminate every compositor/handle-reuse race.

Selecting a window clears the old image/result/history and resets ROI to
unconfigured before any new screenshot can be transmitted. Explicitly selected
windows do not overwrite the old viewer's persisted calibration. Their fresh ROI
is memory-only, with a session-only status notice; restart requires reselection.
Both ROI setup and window selection close Settings before the next dialog, so
Settings does not remain over the image preview.

## Browser attempt: incomplete, not credited

The real source App was launched with its isolated runtime and a separate Edge
profile displaying a local research ECG. Actual Settings opened the new picker,
and the fixture browser appeared in its list. No configuration keywords were
manually edited. `ImageGrab(window=...)` returned Chromium's black window buffer;
a bounded visible-window capture confirmed the page, its translation popup, and
the actual picker. Raw screenshots remain private.

Before a selection/ROI/analysis could complete, the fixture Edge process,
Harness Viewer and picker were no longer present. The native input guard rejected
the stale target, with no click delivered to an unrelated process. There is no
evidence establishing why these windows closed. The remaining App was gracefully
quit. The user was asked whether desktop interaction should continue; meanwhile
only non-focus-taking implementation/testing was continued.

Consequently, browser ROI capture, model inference, browser overlays and browser
regional QA are **not passed** by this checkpoint. A live third-party/browser
workflow remains a required next acceptance task, along with current-model
>=100-case, vendor/legacy ECG and cross-monitor/DPI testing.

## NORMAL heading defect

Presentation no longer equates lack of a retained abnormal finding with a normal
assessment. Incomplete/review-required/validation-limited reports, and EKGs
without verified complete lead inventory, show `INDETERMINATE — review required`.
Unqualified informational findings show `REVIEW FINDINGS`. Structured warning or
critical findings/checklist status retain that higher heading, including an
incomplete-assessment suffix when applicable. Complete normal reports still show
`NORMAL`. This changes neither scientific schema nor stored result/severity.

The immutable real export `desktop-20260924-092539-313629/result.json` was replayed
through the current Qt widget **offscreen**, without a model request or desktop
focus. Source SHA-256 stays
`0b7c01e681a7df7d5b0ea80d19b624e7e6925a8078c4016bd1f63faddc833bf1`.
Its original `severity=normal` remains unchanged while the heading now correctly
indicates an indeterminate assessment. The first offscreen rendering lacked
fonts; a second replay explicitly loaded existing local Windows fonts and its
readable text was visually inspected. The small modality emoji lacks the normal
desktop font fallback in that offline rendering. This is not a fresh real-App
inference or proof of native desktop typography.

Private replay: `data/tmp/indeterminate-heading-replay-20260924-fonts/`.
Source presentation SHA-256:
`e744d084095fb1a9a5784edb275ab20ad8dfc89f6a9e5451037c3fd4ee5b43c1`.

## Verification boundaries

Tests cover manual selection, title changes, process/class change, destruction
and observed handle reuse, minimized/invisible windows, no keyword fallback,
own-window/shell/popup exclusion, picker refresh, closing Settings before the
next dialog, refusing selection during startup/analysis, and no inference until
a fresh ROI exists. Heading tests cover incomplete/review/validation/partial
inputs, informational status, normal controls, and critical/warning precedence.
No heavy dependency, OpenClaw protocol change or full-desktop capture path added.

Final local regression: **1,648 passed, six skipped in 234.53 seconds**
(`uv run pytest tests/unit tests/integration tests/smoke -q`, offscreen Qt).
The skips require private cohort artifacts, an explicitly refreshed frozen
bundle/Gateway, or opt-in native Windows capture/input; they are not passes.
Ruff, documentation-link checks and whitespace checks pass. This checkpoint
does not refresh the distributed executable.
