# Regional conversation-to-outcome linkage — September 24, 2026

Source-only follow-up to the [promotion checkpoint](interaction-package-and-promotion-2026-09-24.md).
The desktop already recorded Apply, dismissal, blocked proposals and no-change
reviews in `result.json`'s `analysis_trace`. Its separate conversation export
contained questions, answers and proposal text, but no exact turn-to-outcome key.
Matching these by label, time, box overlap or list position would be ambiguous.

## Change and interpretation

- The host creates one opaque UUID hex `review_turn_id` before each regional
  request. The same ID crosses the real Qt response signal into conversation
  history and any completed `interactive_review` outcome. The model does not
  supply it. Manual ADD promotion preserves the immutable turn and its ID.
- `regional-conversations.json` is now schema version **2**. Each completed turn
  has `review_turn_id`; use it to join that export to `result.json.analysis_trace`
  within the **same source-image SHA-256-bound export**, selecting entries whose
  stage is `interactive_review`. Existing version-1 exports are unchanged and
  cannot be retroactively linked by guessing. No automatic history import exists.
- Only successful existing host writeback/audit paths record a terminal outcome:
  `applied`, `dismissed`, `blocked` or `no_change`. The corresponding
  `user_confirmed` and operation retain their previous meanings. A conversation
  with no matching event is **not a confirmed update or a recorded dismissal**;
  a proposal may still be pending or have been superseded. Failed requests do not
  create a completed conversation turn.
- Duplicate IDs across current conversation threads are rejected before append.
  Report writeback rejects invalid/reused IDs under the review lock before
  mutation, even if a duplicate caller has obtained the newer report revision.
  Existing non-conversation callers may omit the ID; that creates no invented
  link. IDs are not sent as clinical evidence or added to model history context.

This is review-process correlation, **not** a canonical observation/evidence
ledger, diagnostic validation, proof that all raw model outputs are preserved,
or a signed/cryptographic authenticity claim. The canonical host assembler gate
remains open. Source ROI boundaries, image/crop bytes, prompts, 16-key Gateway
draft schema, subscription ownership, public submodule pin and dependencies are
unchanged. No capture-area expansion or new runtime dependency was introduced.

## Verification scope

- Targeted state/export/writeback tests: 77 pass before the signal-wiring tests.
- Four additional tests execute the actual nested submit/response/Apply/dismiss
  functions and real Qt signal, using offline synthetic model responses and a
  synchronous bridge. They verify the generated ID reaches history and the
  matching no-change/blocked/applied/dismissed API call. They are **not native
  desktop interaction or live model calls**.
- Existing stale image/revision guards and source-image export mismatch tests
  remain required; promotion never invents a new ID for past turns.
- Combined targeted suite: **81 passed**. Full source regression: **1,669 passed,
  six skipped in 241.12 seconds**. Skips are the private frozen cohort, three
  opt-in frozen-package checks and two native Windows capture/input checks;
  none is counted as a pass. Four documentation-link tests, Ruff and staged
  secret scan also pass. Existing frozen-package results remain tied to bd8f303.

The preserved bd8f303 EXE does not contain this change. Native promotion and
dismissal, browser capture/QA, cross-monitor DPI, and 100 current-model real-GUI
clinical cases remain outstanding. No desktop focus was taken here.
