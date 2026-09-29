# Regional history import and continuation

Source candidate, September 29, 2026. This is not in the installed EXE or the
previously tested frozen `36dc3c6` package. Synthetic Qt/callback checks are not
substitutes for a fresh real App/OpenClaw acceptance run.

## Reviewer workflow

1. On the original review, use **Export**. Preserve `source.png` and the separate
   `regional-conversations.json` in the export directory securely. There is no
   automatic background conversation persistence.
2. After restarting, display and analyze the same original ROI image. A currently
   published review is required. The import does not restore an old report or
   bypass current image validation, and it does not start analysis automatically.
3. Open **Settings → Trigger → 區域對話歷史 / Regional history…**. Choose **Load**
   and explicitly select the exported `regional-conversations.json`.
4. Select a conversation. The dialog displays its normalized ROI location on a
   preview of the current source and shows the full plain-text transcript. The
   orange preview outline is historical, not a current diagnostic finding.
5. **Open conversation** restores the selected history into the chat panel.
   Opening/reopening is local-only; press **Send** to explicitly request a new
   answer. New answers use the selected source crop plus the same original ROI,
   through the existing OpenClaw Gateway review route.
6. Use **Export** again to retain the continuation. Reopen already loaded histories
   through the same Settings entry without reimporting. Closing without Export
   does not persist the new turns.

The byte-level SHA256 of the encoded source PNG must match, not merely a filename,
dimensions, similar pixels or an overlapping box. A different rendering, scale,
ROI or PNG encoding may therefore be rejected. Do not loosen this check or widen
capture just to accept an old file. Cancel leaves current review/history unchanged.
Image/report revision is checked again after the modal selection dialog closes.

## What continuation can and cannot do

Imported conversations are clearly labeled unverified past-run context. They are
kept separately from both current AI-finding threads and current manual-region
threads, even when IDs and coordinates coincide. An old `f1` is not proof that
the new analysis's `f1` refers to the same observation. No overlap matching or
automatic merging is performed.

Historical continuation is Q&A only: imported finding IDs never select a current
finding, and ADD/REVISE/RETRACT are blocked by the existing structured response
parser. To change the current report, select its current marker with **Inspect**
or draw a current **Mark**, then explicitly review the new proposal. Historical
suggestions are never automatically applied or inserted into scientific evidence.

The Q&A-only path skips the otherwise optional refinement call and records
`regional_refine: skipped / imported_history_qa_only`; it still sends the actual
crop and original ROI to the structured question turn. This removes one model
call when multi-pass is enabled; no measured latency or accuracy improvement is
claimed. Context remains bounded to the last six Q/A pairs and a 12,000-character
pair budget. Full imported/current history remains visible and exportable.

New-image/new-analysis invalidation drops all active archives and rejects late
responses. Identical reimports reuse the existing archive object without erasing
new turns. A re-export containing additional turns is a distinct historical
snapshot when imported again; it is not silently merged with an earlier snapshot.

## File contract and resource/privacy boundaries

- Existing schema-v2 exports remain accepted. Without imports, exports remain v2.
- With imports, export schema v3 adds `archived_threads`. Each entry separates
  `history` (source hash, old finding ID, region, historical turns) from `turns`
  (new host-ID-linked turns in this run). Ordinary live threads remain in
  `threads`, unchanged.
- On reimport, both past history and that export's new turns become historical.
  Old review-turn IDs are retained for provenance, never relabeled as current
  Gateway receipts or linked automatically to current canonical evidence.
- All file records are validated before any selectable result is returned.
  Unknown fields/versions/roles/spaces, duplicate JSON keys/turn IDs within a
  thread, invalid timestamps, nonfinite/bool/out-of-ROI coordinates, malformed
  UTF-8/JSON and oversized text are rejected. Only explicit `.json` selection is
  read; payload contents cannot name files to load.
- Limits: 4 MiB per file and imported collection, 64 conversations, 512 historical
  turns; per turn 8,000 question / 64,000 answer / 16,000 proposal characters.
  JSON parsing is bounded and all text is rendered as plain text, never HTML.
- No PHI detection/anonymization is implied. The reviewer's deliberate local file
  selection/export remains their responsibility. File contents/paths are not
  added to error logs; the dialog participates in existing Windows capture
  exclusion. No new network operation occurs until Send. No new dependencies,
  wider captures, model transport changes or 16-key result-schema changes.

## Verification scope

Code checkpoint `50a5c868323be92a1d0fd75fa3027bc08c8efe1a`:
after locked dependency setup, local unit/integration/smoke run on Node24.18.0
passed2,697 tests, skipped12 opt-in/private/portable-runtime checks in487.21s.
Seven additional edge/export cases were added during that run and covered by a
subsequent63-pass focused run; counts overlap and must not be added together.
Ruff, targeted mypy, Bandit and staged secret scan passed. CI run36575857832
tracks the complete committed test set; real desktop/frozen gates remain separate.

Focused tests cover v2/v3 round-trip, strict image match, independent same-box
threads, repeated import, stale response invalidation, parsing/resource edges,
real Qt buttons/preview/plain text, cancel/error preservation, modal revision
races, inline Send and callback-to-current-evidence turn linkage. Inference is
synthetic in these tests. The existing real frozen Mark/regional QA evidence
remains separate; no new paid clinical case is claimed for this source change.

Remaining acceptance: real source App load → select → Send → Export → restart
and reimport, an actual OpenClaw attachment/usage audit, then rebuild/frozen
verification before replacing or publishing any EXE. Broader clinical/100-case
and distribution-license gates remain open.
