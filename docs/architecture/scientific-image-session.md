# Executable scientific stages and review-availability boundary

`infrastructure.scientific_image_session.ScientificImageSession` connects actual
stage operations to the [execution journal](execution-journal.md),
[Gateway image request API](gateway-evidence-capture.md) and
[strict scientific decoder](scientific-model-draft.md), then optionally continues
through native geometry, explicit finding challenge and second-look turns. A
separate preflight and host review-availability callback permit final canonical
assembly. This is **not the default App pipeline**, clinical approval or a release.

## Implemented sequence

Construct with the opt-in connected `OpenClawClient`, immutable authorized ROI PNG
bytes, an explicit modality, and trusted `deidentified=True`. Call `read_blind()`.
It executes the following, not synthetic completed-stage labels:

1. **Intake:** decode the exact source, reject corrupt/non-PNG/multi-frame input,
   retain its SHA and actual dimensions in the journal's artifact hashes. Build
   an opaque single-asset public study manifest, with `complete=False` and explicit
   single-image limitations. The provenance kind is `screenshot`: callers must
   actually supply their authorized screenshot ROI, not mislabel other data.
2. **QC:** send the pixels in a fresh Gateway session with the pinned public
   `imageQuality` schema. Parse the exact original UTF-8 reply strictly; validate
   the public shape before completing the quality stage. No JSON repair, legacy
   16-key conversion or paid parse retry occurs.
3. **Blind pass:** only after a valid diagnostic/limited QC, send the same pixels
   in another fresh session with the scientific schema and source-frame evidence
   catalogue. Record actual model-led observations and checklist links. The output
   must preserve the completed QC object and explicit incomplete-study state.
   A single CT screenshot cannot produce diagnostic hypotheses or high-confidence
   findings, including at this intermediate boundary.

After successful `read_blind()`, `localize_and_reconcile()` now executes two more
fresh source-image turns. It does not repeat blind inference or replace its draft:

4. **Native source localization:** the `independent_evidence` journal stage runs
   `dicom_bbox_validate` only. This is independent **geometry checking**, not an
   independent diagnostic classifier. The actual Gateway tool text and local
   audit snapshot must bind source, nonce, call ID, count and digest through the
   native source adapter. No model-authored receipt or fallback box is accepted.
   At most eight tool calls; every observed bbox call needs one result and one
   audit. Other tools, unbound starts and started-but-unfinished calls reject the
   stage. Explicit unavailable/rejected-only localization stays without boxes.
5. **Reconciliation:** another source-image request receives the retained blind
   draft and verified geometry catalogue. It returns agreements, conflicts,
   unsupported claims, uninspected regions and a scientific draft, plus exactly
   one explicit challenge decision per old/new finding. Confirm/revise retain
   identity; retract/unevaluable remove the finding; add requires a new identity.
   Changed clinical wording, certainty or observations cannot masquerade as an
   unchanged confirmation. Original QC/partial-study and CT limits still apply.

No tool is permitted during reconciliation. This is post-observation rejection,
not remote execution sandboxing. The concise decision rationale is reviewable
visible-evidence text, not hidden reasoning or a proof of medical correctness.
The host checks decision coverage/identity and reference consistency, not the
clinical truth or semantic completeness of the four model-authored lists.

The original reconciliation envelope bytes/hash are retained separately from the
strictly decoded nested draft (whose bytes are a canonical JSON projection).
`localizations` and `reconciliation` return independent copies. The original
blind response remains immutable and box-free; a later client send cannot replace
the prior tool text/audit snapshot. Repeated/concurrent continuation, failure or
cancellation cannot silently start a paid retry. These stages make four model
requests before the separately invoked targeted second look;
this is request accounting, not a measured speed or accuracy improvement.

6. **Second look:** `targeted_second_look()` makes one new request against the same
   immutable full ROI, focusing on the reconciliation's conflicts, unsupported
   claims, uninspected regions and urgent/reviewer questions. Its decisions must
   cover the immediately preceding reconciled findings, including newly added
   identities. It is not a crop/zoom and cannot claim better resolution. The raw
   blind, reconciliation and second-look replies remain separate and immutable.
   This brings readable runs to five model requests, not a latency improvement.
7. **Content preflight:** `prepare_review()` binds actual host source/study/evidence
   and the executed six-stage prefix. The public preflight API checks scientific
   content without accepting or inventing future validation/handoff events. Only
   after that callback returns does the journal complete `contract_validation`.
   `PreparedReview.result` is a detached snapshot; full canonical serialization
   still rejects its deliberately incomplete workflow. A content SHA binds all
   canonical fields except the subsequently appended execution trace.
8. **Review availability:** `offer_review(presenter)` awaits the trusted host's
   actual presentation operation with a detached prepared snapshot. It requires
   UTF-8 JSON bytes (maximum 16 KiB) containing exactly `run_id`,
   `source_image_sha256`, `review_content_sha256`, `surface`, and `available`.
   The first three must match this session/content, `surface` is an opaque
   1–64-character ASCII alphanumeric/underscore/hyphen ID (not a window title),
   and `available` must be exactly true. Only a successfully checked callback
   completes `human_handoff`. The original full public assembler then validates
   actual completed events and unchanged content before setting `final_result`.

There is no default/no-op presenter. A trusted host can still lie about displaying
content; these receipts are bindings, not independent screen observation or human
approval. Tests using synthetic callbacks are not GUI acceptance. Cancellation,
duplicate/concurrent calls, malformed/mismatched receipts and presenter exceptions
cannot publish a canonical result or trigger paid retries. If final validation
fails after availability returned, the true handoff record remains intact but
`final_result` remains absent. The GUI must distinguish the prepared preview from
an export-enabled canonical result. It must never enable signing/clinical writeback.

A concrete [Qt review presenter](scientific-review-presentation.md) is now
implemented and natively exercised with synthetic content, including the actual
async-session/Qt handoff boundary. It is not yet connected to the App's default
analysis/publication route. Its source/revision guard and invalidation signal
must be bound to the existing image-change protection when that integration lands.

For `non_diagnostic` QC, `read_blind()` returns `None`, records an explicit skipped
blind pass and makes **no second model request**. `quality` remains inspectable;
this is not a normal report or a completed human handoff. Invalid QC/draft, transport
failure or cancellation stops the session. Calling it again cannot silently retry
or duplicate inference. Concurrent calls on one session cannot start another run.
Readable inputs currently require a separate paid QC turn before the blind turn;
this may increase their latency/cost versus the existing path. The non-diagnostic
short circuit is verified request accounting, not a measured overall speed or
accuracy improvement. Compare complete workflows after actual candidate activation.

## Source evidence and modality scope

The host-created `source-frame` evidence identifies exact source pixels only.
It has **no bbox, clinical label, lesion verification or fabricated observation**.
Consequently the blind draft has no host-verified localization to select: its
`bbox_evidence_ids` must remain empty. Native receipt-backed localization must be
added by the subsequent native stage above; the absence of blind-pass boxes is not a replacement
for the product's annotation requirement or its existing working overlay.

The prompts follow the pinned medical-image-reading skill:

- EKG quality checks visible lead labels, layout, clipping, artifacts, grid and
  calibration without guessing lead identity or numeric measurements.
- CXR quality checks projection, rotation, inspiration, exposure and coverage;
  one view remains a partial study.
- CT quality checks the visible frame/window; no implied series, phase or volume.

Required checklist axes come from the public modality schema. Potential urgent
observations are prioritized without upgrading uncertainty. Deferred axes must
remain explicitly unassessable/incomplete, never manufactured normal. Prompts
request concise specialist-facing findings and review questions, not boilerplate
refusal or hidden reasoning. These are execution instructions, not evidence of
medical correctness or live model compliance.

## Tool boundary and retained evidence

QC and blind prompts forbid tools/prior reports/external models. The collector now
retains a bounded **boolean** `tool_event_seen` for matching-run `agent/tool`
events, including starts and arbitrary tools whose content it otherwise ignores.
Either stage fails if such an event is observed. No arbitrary tool arguments,
outputs or names are added to the receipt. Other-run events do not taint this run.

This is **post-observation rejection**, not a remote tool-execution permission
policy: it cannot undo an already executed tool, or attest to unreported/internal
provider actions. Fresh sessions and absence of host-supplied expert/label data
do not replace live tool-event fidelity and runtime policy verification. The
native text/source adapter and independent-tool stages remain separate work.

`records`, `turns`, `quality`, `blind_draft`, `localizations`, `reconciliation`,
`second_look`, `prepared_review`, `final_result`, `review_artifacts`, `study`, `provenance` and
`source_evidence` expose immutable receipts or independent copies. Original
successful transport replies are kept before stage decoding, so invalid model
JSON is retained as a failed attempt rather than replaced by a repaired result.
Transport calls that never returned successfully remain in the client's
`transport_evidence()` slot, not falsely listed as returned session turns; the
caller must preserve that failed/nonterminal snapshot before any subsequent send.
There is no automatic disk archive or clinical export.

The intermediate draft uses `model_used="openclaw-unverified"`; a configured
provider or source label is not verified model usage. Actual usage identity must
be supplied by the eventual host usage-receipt path. No model is substituted here.

## Still required before desktop activation

The journal records actual intake/QC/blind operations and, when explicitly
continued, native-geometry and reconciliation operations. It never labels these
as independent waveform classification. Second look, content validation and
handoff are recorded only after their actual callbacks return. Intermediate
drafts continue to fail full serialization. The adapter is not injected into the
App's legacy hooks or exporters.

Next integration must add optional trusted matched external evidence, zoomed
revisits/crops, a real App review presenter and guarded scientific publication.
Non-diagnostic QC needs a truthful quality-only review presentation; this adapter
does not manufacture observations from QC to satisfy a final clinical ledger.
The current frozen cohort must remain on its original source. Actual candidate
GUI/model, legacy/vendor/truncated ECG, DPI and current-EXE acceptance remain open.

## Verification scope

Current checkpoint: [second look, preflight and handoff evidence](../evidence/2026-09/scientific-review-handoff-2026-09-25.md).
Continuation checkpoint: [native localization and reconciliation evidence](../evidence/2026-09/scientific-localization-reconciliation-2026-09-25.md).
The following counts describe the earlier intake/QC/blind-only checkpoint.

32 synthetic adapter tests exercise real client receive paths and journal callbacks,
including all three modality schemas, no second call for non-diagnostic input,
raw failed responses, unexpected tools, immutable snapshots, cancellation,
concurrency, invalid source, CT limits and rejection of incomplete canonical output.
Session/collector/request/journal checks: **150 passed in 1.88 s**. Focused mypy and
Ruff/format pass. Full regression: **2,136 passed / seven explicit conditional
skips in 208.94 s**, using Python 3.13.12, Node 24.18 and offscreen Qt. Skips
remain the optional local Node directory, private frozen cohort, packaged runtime
checks and native Windows capture/input opt-ins. Documentation links and staged
secret scanning also pass.
No test here claims actual native desktop or paid-model execution.
