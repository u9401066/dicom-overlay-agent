# Regional history and actual desktop QA — September 24, 2026

This follows the [Mark interaction checkpoint](regional-interaction-2026-09-24.md).
It is source-App development evidence, not a new frozen release or blind clinical
acceptance. No source images, transcripts containing patient data, or credentials
are committed.

## Behavior implemented

- Same-image, same-region conversation threads for both manual and existing AI
  markers; different findings/regions do not share history.
- Inline **Send** continues the selected region. Existing history reopens on
  **Inspect**, without a new inference request. **Hide** hides the panel only.
- Regional answers/history persist instead of expiring after 30 seconds. New
  image/analysis invalidates old context and late replies cannot attach to it.
- The model receives up to six recent pairs within a 12,000-character history
  budget; full completed turns remain readable and exportable. Omitted context
  is explicitly counted. Old model text is untrusted context, not new evidence
  or permission to modify the report.
- Explicit **Export** includes `regional-conversations.json`, source-image
  SHA-256, normalized ROI coordinates, finding identity, completed questions and
  answers, timestamps, and proposed-change text. Proposal text is not approval;
  `result.json` retains the actual Apply/dismiss audit. Cross-image history export
  fails before creating an output folder. Nothing is persisted automatically.
- User questions are no longer logged by the general chat submission handler.

The [OpenAI conversation-state guidance](https://developers.openai.com/api/docs/guides/conversation-state)
informed explicit history management, and the
[agent safety guidance](https://developers.openai.com/api/docs/guides/agent-builder-safety)
informed treating past text as untrusted context. These principles are implemented
through the existing public OpenClaw Gateway. No direct OpenAI API, API key,
Codex runtime, or new provider SDK was introduced.

## Actual source-App sequence

Source at `6be42cb` plus the recorded history patch ran as real Qt windows, with
an isolated verified Node/OpenClaw runtime on port 18795. This is **not** the
frozen `9a27b61` executable. The private GUI receipt records hashes of all seven
changed production files at execution time.

The exposed hidden-label case 119 was opened with the real QFileDialog, analyzed
by the App, then exported with its button. Analysis took **110.874 s**; workflow
**117.571 s**. Exported source pixels match the authorized ROI exactly (MAE 0.0).
The result remains incomplete, with three uncertain findings; this is not a
correctness or latency-improvement claim.

1. Actual Win32 drag `(800,350) → (1000,600)` started outside all AI boxes and
   opened the reviewer question dialog. The App received the blank-area pointer.
2. A question was submitted in that dialog and the real ChatPanel answer read.
3. A second question used the new inline field and Send button. Its answer
   recalled the earlier three-row polarity description and distinguished that
   description from full QRS polarity. Both turns are in the same manual thread.
4. Existing AI marker `f1` was selected at `(1250,290)` and separately questioned.
   Its answer proposed a cautious revision. Actual **Apply to report** changed
   the label to “Altered complex of uncertain origin,” retained its original
   bbox, and recorded `user_confirmed=true`, `operation=revise`. Retained
   checklist items remain explicitly pending reconciliation.
5. Selecting the manual marker again reopened its original two-turn history
   without an extra model request. The existing-finding thread remained separate.
6. The two ChatPanel screenshots were opened and visually inspected. Question,
   answer, scrollable history and inline controls are readable at 150% scaling.

The first observation immediately after inline Send read the prior answer before
Qt processed the click. That receipt is retained but **not** credited as second-turn
success. The observer now requires the expected current question; the corrected
observation verified the second answer. Observation itself sends no model requests.

## Immutable local receipts

Private root: `data/tmp/live-interaction-74d6ee9/DICOMOverlayAgent/data/exports/`.

| Export | Evidence |
| --- | --- |
| `desktop-20260924-102930-239967` | Actual initial analysis; result SHA-256 `85dc50671869cd8bfa1528b0019d18de936cae6547a9021a1a38f38b75eef1ba` |
| `desktop-20260924-103016-110641` | First manual question, answer and ChatPanel image |
| `desktop-20260924-103058-548785` | Verified second manual answer, two-turn history and ChatPanel image |
| `desktop-20260924-103244-754285` | Actual Apply audit; two manual turns and one existing-finding turn |
| `desktop-20260924-103246-547403` | Manual history reopened after Apply; final usage supplement |

Final result SHA-256:
`4e2d4833ecfb28dd50182d7574edf86a039c78e1900fd2c2b06b079b9edfd972`.
Conversation SHA-256:
`8a4a58dffa8862203a1838c1aea254c6f5c506a2eef120eca578d6a1059d1210`.
Both bind source SHA-256:
`cce82cb830055010eed9296e5c4cb7146e9b46ac2658c2e4ccf7603adc6f8e94`.

All **10** original analysis and regional turns have public session-usage plus
runtime identity bindings to **GPT-6 Astra medium**. The six regional turns are
included, not just the original analysis. Missing/aborted usage is never treated
as zero, and these public snapshots are not a monetary billing ledger. Earlier
two coarse timeouts remain failed attempts; this success does not erase them.

## Discovered safety issue and remaining acceptance

Changing the real Viewer image invalidated the chat and review snapshot, but
left the old summary visibly next to the new image. The source now silently
clears/hides the old report, boxes, annotation input and conversation on image
invalidation, without starting another analysis. The fresh actual-window retest
passed: displayed SummaryPanel/Overlay became invisible after opening case 0 in
the real Viewer; stale Export was refused and extra model requests were zero.
Private receipt: `data/tmp/live-regional-image-invalidation.json` (10:38:26 UTC).
The prerequisite source-App analysis completed in 96.451 s, source MAE 0.0,
with four separately bound Astra-medium turns. Export
`desktop-20260924-103700-706167` has result SHA-256
`50d7caedf231c7c1fcf3dffe54bf3c6b4654c8091e7d0356b767236a7242c8ea`.
Only displayed-state behavior is credited here, not clinical improvement.

Final local regression: **1,620 passed, six explicit skips** in 203.00 s.
The native Windows physical-drag test separately passed (1.06 s), as did Ruff
and documentation-link checks. Runtime dependencies and scientific result schema
are unchanged. The App was gracefully closed after saving the real evidence.

Remaining: refreshed frozen build, explicit proposal-rejection live test,
cross-DPI/monitor history selection, manual-marker promotion identity, imported
history/resume across restarts, third-party/browser viewer selection, diverse
vendor/legacy ECG, corrected indeterminate NORMAL heading, canonical evidence
integration, and at least 100 current-model real-GUI acceptance cases. This
single exposed image is not that cohort.
