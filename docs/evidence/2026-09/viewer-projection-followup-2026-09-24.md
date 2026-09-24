# Viewer movement projection follow-up — September 24, 2026

Source follow-up to the [6e6734e bundle's reproduced geometry gap](interaction-bundle-6e6734e-2026-09-24.md).
This patch is **not present in that preserved executable**.

## Behavior

- `ReviewSnapshot.capture_rect` remains the immutable acquisition rectangle.
  Separate `display_rect`, `display_window` and `display_frame` describe current
  presentation. A same-size, same-display translation moves only that projection,
  without changing source pixels, finding boxes, report revision or conversation
  IDs and without another model call. Updates occur on the existing monitor tick,
  not an OS-level continuous-movement hook.
- A translation tick does not sample for image changes before Qt can apply the
  queued projection. Hash monitoring resumes on a subsequent stationary tick,
  preserving the existing baseline and clearing any old debounce interval.
  This avoids interpreting a transient old capture-exclusion overlay as a new
  image; native repaint timing and movement latency still require verification.
- The Qt geometry callback reprojects dynamic AI boxes, static region-map
  fallbacks and normalized manual marks through the same current coordinate
  frame. It keeps regional history, a pending proposal, unsent follow-up text and
  dragged panel positions. An unfinished mouse drag is cancelled because its
  old screen coordinates no longer identify the intended region. Translation
  does not speak the report again or trigger automatic export.
- Resize, monitor/frame changes, unavailable previously-known display geometry,
  or a translated ROI spanning/outside its display invalidate the active review
  and require fresh ROI confirmation. Arbitrary browser/Viewer reflow is not
  assumed to be a uniform rescale of old pixels. Qt display-geometry and logical
  DPI signals, plus monitor addition/removal, also invalidate the ROI; old panels
  are hidden immediately, including while paused. Resume requires ROI if needed.
- The viewer is rechecked after a long analysis and before publishing its first
  result. Safe translation updates presentation before publication; missing or
  resized targets do not receive the old overlay. Invalidation during the
  pre-capture UI-hide interval stops capture before any image/model request.
- Active stale results are cleared, but previously obtained snapshot objects and
  exported acquisition evidence are not rewritten. AUTO mode can start a fresh
  read only after the user has confirmed the new ROI. Late initial-result or
  geometry callbacks cannot restore an invalidated image; same-image geometry
  refresh uses the current report, not an older queued report object.

## Verification and scope

**147 targeted tests pass**, covering positive/negative desktop origins,
repeated translation, no-op geometry, unchanged source bytes/revision, resize,
monitor change, display lookup loss, off-display ROI, long-running analysis,
capture-time invalidation, paused resume and fresh-ROI AUTO restart. Real Qt
widgets and exact nested App callbacks verify AI/fallback/manual box coordinates
at a synthetic 1.25 physical/logical scale and preservation of conversation and
panel state. Qt signals are emitted in the test only; no OS display or DPI setting
is changed. These checks use synthetic data and offline model doubles.

Test-authoring errors (an incorrect helper import, expecting manual boxes in a
separate list, and omitting the WAITING-to-MONITORING tick) were corrected before
the credited targeted run. The intermediate source suite passed 1,687 checks /
six skips before the final active-result clearing/AUTO restart follow-up. That
earlier run is not the final-code regression receipt.
The next intermediate run passed 1,688 / six skips in 230.34 seconds before the
translation-tick sampling guard; the final-code suite is rerun separately.

**Final-code full regression: 1,688 passed, six skipped in 235.31 seconds.**
The skips are the private frozen cohort, three opt-in packaged-EXE gates and
two native Windows capture/input gates. They are not passes. Four documentation
link tests, Ruff/format checks and the staged secret scan also pass. The 20
earlier frozen-EXE checks remain evidence for 6e6734e, not this source patch.

No new dependency, Gateway draft/schema, clinical rule, model pin, source ROI
expansion or public-harness submodule change. The four-core boundary remains:
application owns snapshot lifecycle; presentation owns Qt projection; domain
types do not import GUI/network code; interpretation stays with OpenClaw.

Follow-up: [actual native regional QA and same-display Viewer movement](native-regional-projection-2026-09-24.md)
now verifies the source App at 150% scaling, including resize invalidation.
Native browser movement, actual mixed-DPI monitor behavior, visual latency,
fresh source-App/model acceptance and >=100 current-model real-GUI clinical cases
remain required. These source tests are not new clinical cases or a binary release.
