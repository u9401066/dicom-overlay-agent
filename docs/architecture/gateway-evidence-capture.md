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

Final local verification: **56 collector tests plus one new native-producer smoke**;
collector/recovery targeted suite **99 passed in 0.73 s**. Final full regression
after the buffered-binary-frame fix: **2,012 passed / seven explicit conditional
skips in 194.59 s** under Node 24.18. Skips remain the optional candidate-local
Node directory, private cohort, three frozen-package opt-ins and two native GUI
opt-ins. Ruff/format, focused collector mypy, documentation links and staged
secret scan pass. The preceding pre-binary-fix full run also passed 2,011 tests;
it is not substituted for this final-source run.
