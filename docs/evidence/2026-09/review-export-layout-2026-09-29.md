# Review PNG text layout — 2026-09-29

Follow-up: [actual new EXE acceptance](frozen-regional-context-2026-09-29.md)
now verifies this renderer through real App Export with long Chinese answers.
The original offline-only checkpoint and its limitations below remain preserved.

The [actual regional-context replay](regional-context-desktop-2026-09-29.md)
exposed clipped Chinese annotation text in the saved `review.png`. The live chat
and JSON contained the answer, but the review side column did not display it all.

## Cause and source change

The renderer used character-count wrapping, which does not bound the pixel width
of mixed Chinese/English fonts. Its canvas height was fixed to the image height,
and the findings panel stopped after at most12 entries or after reaching the
bottom. A long entry could itself overflow before that check.

The candidate now measures each line using the actual font's glyph bounding box,
preserves paragraph breaks, and measures the complete side column before drawing.
Canvas height grows to fit the supported panel content: summary, all findings,
their details/regions/source labels and bbox audit text. This does not add fields
such as the full checklist or complete conversation history to the PNG; their
separate structured exports remain authoritative.

The image stays at its original pixel size and top-left origin. Additional blank
area below it is report padding, not newly captured anatomy or a larger ROI.
Bounding boxes and crop audits continue to use the original source dimensions.
No model/prompt/protocol, canonical schema, dependency or packaging pin changed.

Each text measurement is bounded near one line rather than repeatedly measuring
large remaining paragraphs. A40-million-pixel output limit fails explicitly
instead of silently cutting off text or allocating an unbounded report bitmap.
An oversized export is a failure, not a complete review bundle.

## Reproduction using preserved actual App output

This check used the renderer on an already-retained real export; it is **not a
fresh App Export click, new inference, or new frozen acceptance**. The source was
`Ctemp/dicom-regional-context-20260929/runtime/data/exports/desktop-20260929-094548-370934`.
Output was written to a separate ignored directory, never over the sealed files.

- Original source:1494x858. Old review:2014x858. New review:2014x1062.
- The entire annotated source rectangle is pixel-identical before/after.
- Original `result.json`, `source.png`, `review.png`, `bbox-audit.json` and
  `scientific-result.json` hashes are unchanged.
- New PNG SHA256:
  `13a1d4fdf5141405584ee0200474cbdaca7106786178aadc7cb4c8d1fab7d5d1`.
- New panel SHA256:
  `4c6cbfa780da17c24b58d7466e09029c4792abc1c79d3277e7a4edf06f773351`.
- Inspected the rendered panel: Chinese answer, paragraph separation, final
  no-change statement and final bbox line are visible inside the column.

Private reproduction script, receipt and rendered PNGs are under
`data/tmp/review-layout-20260929/`. No model request or old-runtime restart occurred.

Tests cover mixed CJK/Latin, unbroken identifiers, accents, paragraphs, multiple
font sizes, impossible widths,15 long findings without omission, every drawn
glyph inside the output bounds, unchanged source pixels, a10,000-character note
with bounded measurements, and explicit oversized-image failure. Fresh GUI and
frozen-package coverage of this layout change remain pending; do not reuse the
preceding crop-only or context-aware screenshots as new-renderer acceptance.

## Follow-up verification of the reported Mark/QA problem

The original main worktree at `1c531a5` does not contain the candidate's
alpha1 input surface. On Windows, alpha-zero layered-window pixels pass mouse
input through, even with input transparency disabled. The candidate paints a
near-transparent input surface over the approved ROI only while Mark is active.
Mark is not limited to AI boxes and does not authorize whole-desktop capture.

A fresh native Windows mouse run passed4 cases in3.97s: empty-ROI forward and
reverse drags, bottom-right/top-left clipping, outside-ROI hit-test exclusion,
and passive-mode click-through. These are real native input checks with owned
test windows, not fresh full-App inference or clinical acceptance.

The associated overlay, regional-thread/linkage, prompt, geometry, export,
Core2 and documentation suite passed168 tests in3.25s. Earlier layout/package
checks passed69 with3 opt-in skips in3.33s; skipped fresh-package gates remain
unverified. Ruff and targeted exporter mypy pass.

Full-App QA evidence remains the separately dated
[actual source-App replay](regional-context-desktop-2026-09-29.md): manual
two-turn conversation, separate existing-AI-box question, unchanged history on
reopen and rejection after image change. This follow-up inspected its preserved
chat screenshot and the new offline report panel; it made no model request.
Neither conversation restart restoration nor unlimited model memory is claimed:
model context is bounded to six recent turns/12,000 characters while full
visible/exported thread history is retained. Updated frozen delivery is pending.
