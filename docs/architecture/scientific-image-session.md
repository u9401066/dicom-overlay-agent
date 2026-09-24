# Executable image intake, quality gate and blind pass

`infrastructure.scientific_image_session.ScientificImageSession` connects actual
stage operations to the [execution journal](execution-journal.md),
[Gateway image request API](gateway-evidence-capture.md) and
[strict scientific decoder](scientific-model-draft.md). This is an **intermediate
pipeline**, not a completed report, default App mode or clinical release.

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
added in subsequent stages; the absence of blind-pass boxes is not a replacement
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

`records`, `turns`, `quality`, `blind_draft`, `study`, `provenance` and
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

The journal contains only real intake/QC/blind facts. There are no invented
independent-evidence, reconciliation, targeted second look, full validation or
human-handoff completions. `to_contract_payload()` still rejects this unassembled
draft. The adapter is not injected into the App's legacy hooks or exporters.

Next integration must add native source-bound localization and optional matched
external evidence after blind reading, explicit hypothesis reconciliation and
targeted revisits, full public assembly, review availability and guarded App
publication. Non-diagnostic QC needs a truthful quality-only review presentation.
The current frozen cohort must remain on its original source. Actual candidate
GUI/model, legacy/vendor/truncated ECG, DPI and current-EXE acceptance remain open.

## Verification scope

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
