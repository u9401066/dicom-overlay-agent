# Opt-in Gateway visible-output capture

This candidate connects a bounded evidence collector to both existing
`OpenClawClient` receive loops, **before** the legacy JSON/text parser. It is a
transport component, not activation of the scientific inference protocol or a
replacement for the real execution journal.

## Enable and consume

Construct the client with `collect_transport_evidence=True`. The default is false;
current desktop construction and the ongoing frozen GUI cohort are unchanged.
When enabled, the ordinary public `connect` request advertises `tool-events`.
No OpenClaw SDK internals, direct model API or additional inference request is used.

After each send, read `client.transport_evidence()` before starting another turn:

1. Keep the frozen snapshot associated with that actual request/session/run.
2. `require_model_text()` returns the exact UTF-8 bytes of the decoded visible
   text field, without trimming, joining multiple blocks, stripping fences,
   repairing JSON or serializing an already parsed object. Feed those bytes to
   the [scientific decoder](scientific-model-draft.md), not the legacy parser.
3. For every expected native bbox call, use `require_native_tool_text(call_id)`.
   Bind its exact bytes to the separately collected native audit record through
   the [source adapter](native-source-evidence.md). A result's presence alone is
   not source verification. Missing/truncated/sanitized results cannot be filled
   in from final prose, model JSON or a matching tool name.
4. Preserve failed/incomplete snapshots separately. A collector failure prevents
   the `require_*` methods from treating them as usable evidence. If a later final
   message actually arrives, its body is still retained for the failed attempt.
   A disconnected/timed-out turn without a final remains nonterminal evidence.

Only the latest send is owned by the client. Callers must retain snapshots before
the next turn or any outer parse retry replaces that slot. This is not automatic
durable storage, a complete attempt archive or scientific export wiring.

## Instrumented image request API

`await client.request_image_evidence(prompt, image_bytes=roi_png,
deidentified=True)` now connects a new stage request directly to the collector.
It uses the existing public `connect` / `chat.send` transport and recovery paths;
it does not route through the legacy 16-key result decoder or add a parse retry.
Collection must be enabled before connect, and a negotiated supported protocol
must exist. Each request gets a fresh session, idempotency key and host bbox nonce.

The caller supplies the already-authorized immutable ROI PNG bytes and complete
stage prompt/schema. De-identification must be explicitly asserted. Empty,
mutable, corrupt, non-PNG and multi-frame input is rejected before sending; the
public image decoder supplies its pixel safety bound. No silent transcoding,
new capture or ROI expansion occurs. Source bytes are at most 32 MiB, prompt
UTF-8 at most 512 KiB, and the serialized request at most 16 MiB. These checks
are transport/resource gates, not medical image quality assessment.

The method prepends host image SHA-256 and bbox nonce, then returns a frozen
`ImageEvidenceTurn` with exact attached-image SHA, sent-prompt SHA, nonce, elapsed
time and `GatewayTurnEvidence`. The snapshot is captured while holding the send
lock: concurrent or subsequent requests cannot replace another caller's returned
receipt. If the attachment is a crop, this image SHA is the **crop** SHA; the
caller must separately retain its immutable parent and effective crop transform.
Body whitespace, malformed JSON and duplicate keys remain intact for the strict
[scientific decoder](scientific-model-draft.md). Missing original text, identity
conflicts or collection failures cannot become successful request receipts.

The same lock now also freezes `native_bbox_audit_json`: at most 16 independently
collected current-image/current-nonce audit metadata objects serialized to immutable
bytes. These are **not** original audit-file lines. Extra metadata fields reject
the request rather than leaking into the snapshot. The session's native source
adapter still checks each record against the original tool text; an audit record
alone is not proof. Missing or late receipts fail continuation, without a paid
retry. This does not enable the API in the default desktop path.

Cancellation uses the existing abort path; accepted reconnects observe the same
run without another send. Pre-acceptance recovery may replay the exact frame once
with the same idempotency key. Failed/nonterminal evidence stays available via
`transport_evidence()` until the next send, so the caller must snapshot it in its
failure handler. There is still no automatic durable attempt archive.

This API does **not** itself perform QC/blind/reconciliation, verify clinical
claims, establish model usage identity, or assemble a canonical result. The
[execution journal](execution-journal.md) must wrap actual stage operations, and
the native audit/source adapter must independently validate any tool output. The
default desktop has not activated this API. Real tool-event fidelity, staged
prompts, trusted intake/scope and complete App wiring remain open.
The [scientific image session](scientific-image-session.md) now connects real
intake/QC/blind operations to this API; it is an intermediate, unassembled draft
path and does not activate the default App.

## Accepted projection and identity

The collector observes matching `res` acceptance and a known nonempty `runId`.
It ignores pre-acceptance events, other requests/runs, chat deltas, arbitrary tools
and reasoning streams. A supplied session identity must match. Repeated acceptance
may resume the same run, not replace its identity.

The final projection is `event="chat"`, `state="final"`, with one visible text
block in an assistant message. An explicit direct `result.text` is also preserved
if its run identity is known. A structured result with no original text is rejected
as unavailable; it is not reserialized and relabeled as a model response.

For native tools, the supported projection is an `agent` event with `stream="tool"`,
`data.phase="result"`, `data.name="dicom_bbox_validate"`, `data.toolCallId` and one
text block in `data.result.content`. Identical call-result replay is deduplicated;
different content for the same call is a failure. Error results fail. Unknown
projections are not guessed, and missing expected calls fail at consumption.
The collector also retains bounded observed bbox call IDs and boolean flags for
unbound bbox events and non-bbox tools. The continuation stage uses these to
reject a missing result even if another call succeeded. Arbitrary tool arguments,
outputs and names are still not retained. This detects observed events only;
silent provider actions cannot be attested by this collector.

The public [client guidance](https://docs.openclaw.ai/gateway/clients) documents
that `tool-events` gates delivery. The public
[agent-loop guidance](https://docs.openclaw.ai/concepts/agent-loop) also warns that
tool results are sanitized before emission. The pinned 2026.9.3 distribution's
bundled documentation states both. This component's supported nested projection
has replay tests, **not yet live Gateway acceptance**. Actual event fidelity and
native text-hash parity must be checked through the App after the frozen cohort
is sealed; documentation alone does not prove receipt completeness.

## Privacy, resources and trust

- No outbound prompt, image, auth token or raw wire transcript is retained.
  Accompanying thinking blocks and reasoning streams are not copied.
- Exact body bytes are decoded field contents, **not** original WebSocket JSON
  escaping, a full transcript, hidden reasoning or a signed server receipt.
- Body bytes and session keys are excluded from receipt repr. No new logging,
  disk persistence or ordinary export field is added. Protected caller storage
  and trusted de-identified input handling remain mandatory.
- Strict frame ingestion uses the existing 512 KiB / depth 32 / 50,000-node
  bounds. Retained visible text is bounded to 4 MiB per turn and 64 native results;
  individual text blocks are at most 512 KiB, and run/tool-call IDs at most 256
  characters. A bound failure is explicit, never silently truncated into success.
- Public Gateway data is not an independent observer. Native audit/source binding,
  ordered host stages, study scope and clinical validation remain separate gates.

Recovery keeps the same collector. A pre-acceptance reconnect reuses the existing
request and idempotency key; a post-acceptance reconnect observes the same run
without another `chat.send`. These are the existing charge-safe recovery semantics,
now tested with retained evidence across the connection boundary.

## Verification scope

Tests replay public frames through the actual client receive/recovery/handshake
methods, covering opt-in/off, original UTF-8 text, duplicate JSON keys, unrelated
events, identities, missing/malformed/sanitized content, bounds, snapshots and
reconnects. An additional smoke invokes the actual native JavaScript producer,
passes its original text through a **synthetic** Gateway replay and validates
the source/crop binding. No live Gateway, GUI, paid model call, new scientific
workflow stage, clinical correctness or new packaged EXE is claimed by these tests.

Original collector checkpoint: **56 collector tests plus one native-producer smoke**;
collector/recovery targeted suite **99 passed in 0.73 s**. Final full regression
after the buffered-binary-frame fix: **2,012 passed / seven explicit conditional
skips in 194.59 s** under Node 24.18. Skips remain the optional candidate-local
Node directory, private cohort, three frozen-package opt-ins and two native GUI
opt-ins. Ruff/format, focused collector mypy, documentation links and staged
secret scan pass. The preceding pre-binary-fix full run also passed 2,011 tests;
it is not substituted for this final-source run.

The image-request follow-up adds **26 synthetic client tests plus two actual
native-producer/synthetic-Gateway source-binding cases**, including whole-image
and crop attachments. Client/collector/recovery/source checks total **181 passed
in 1.75 s**. Journal integration consumes actual received synthetic QC bytes and
blocks the next callback for non-diagnostic input; the strict draft decoder consumes
the original visible response without a legacy round-trip. No live inference is
credited. Focused mypy now passes both client and collector: three existing typing
errors were corrected by narrowing the already-checked rejection count and typing
the mixed refinement-context mapping, without changing runtime policy.
Final image-request full regression: **2,104 passed / seven explicit conditional
skips in 202.92 s** (Python 3.13.12, Node 24.18, offscreen Qt). Ruff/format, focused
client/collector mypy, documentation links and staged secret scanning pass. These
results do not replace native input/capture, current EXE or real-model acceptance.
