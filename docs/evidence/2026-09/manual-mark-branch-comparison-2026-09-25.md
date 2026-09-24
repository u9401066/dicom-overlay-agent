# Manual Mark and regional QA: branch comparison — 2026-09-25

## Reproduced defect and scope

The same native Windows hit-test smoke fails against main `1c531a5` and passes
against candidate `5b6ccf3`. On main, `WindowFromPoint` at an unmarked point
inside the authorized ROI returns a different window, before any drag begins.
The candidate paints an almost-transparent input surface only inside that ROI
while Mark is active. Its original fix is `6be42cb`.

The correct scope is the entire authorized image ROI, not only AI boxes and not
the unrestricted desktop. Outside-ROI and passive-mode input must pass through.
No ROI was enlarged and no desktop image was sent to a model for this comparison.

Both runs used the candidate's existing native test and Python environment.
For the baseline only, `PYTHONPATH` selected main's `src`; the imported overlay
file path was printed and verified first. Main's own `uv run --no-sync pytest`
launcher initially failed to resolve its script; that environment failure is
not counted as the reproduced overlay failure. No main dependency sync occurred.

| Check | Result |
| --- | --- |
| Main overlay, native Windows input | 1 failed in 0.41 s at blank-ROI hit test |
| Candidate overlay, native Windows input | 1 passed in 1.08 s |
| Candidate regional UI, geometry, QA, writeback and export checks | 121 passed in 1.09 s |

The 121 checks cover `test_overlay_interaction`, `test_overlay_geometry`,
`test_review_chat`, `test_regional_conversation`, `test_regional_turn_linkage`,
`test_review_writeback_presentation`, `test_review_geometry_presentation`,
`test_desktop_review_exporter`, and `test_interactive_review_export`.
These use offscreen Qt/synthetic responses; they are not new live inference.

## Regional conversation evidence

Previously retained real App/OpenClaw evidence was re-read, and the final
three-turn chat screenshot was visually inspected again:

- [Existing and manual region QA](native-regional-projection-2026-09-24.md):
  separate threads, inline follow-up, reopening without another inference,
  viewer translation, and invalidation after viewer resizing.
- [Manual promotion and dismissal](native-marker-promotion-2026-09-24.md):
  actual ADD suggestion, rejection, subsequent explicit approval, and a third
  question on the promoted finding without duplication or lost history.

Visible/exported history is retained; model context is bounded to the latest
six question/answer pairs within a 12,000-character budget. Conversation history
is review context, not validated clinical evidence or automatic report approval.

## Limits and delivery status

This is a branch diagnosis and regression checkpoint, not a fresh whole-App
model run, new EXE, clinical-accuracy pass, or proof of all cross-monitor/DPI cases.
The correction and richer conversation workflow remain on the candidate branch;
main and an older installed EXE must not be described as already updated.
Unrelated main edits and in-progress scientific preflight changes were untouched.
