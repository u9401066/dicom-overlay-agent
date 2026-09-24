# Model-led scientific draft protocol — isolated candidate

`infrastructure.scientific_draft` supplies a request prompt/schema and strict
decoder for real atomic observations. It is the next component after the
[host assembler](host-evidence-assembly.md), **not an active desktop protocol**.
The frozen GUI cohort, old results and preserved 3029dfb executable are unchanged.

The current legacy Gateway parser now rejects any response carrying `draft_version`
instead of silently discarding its ledger. This routing error is not a malformed-
JSON retry: tests of the actual coarse/analysis/final retry wrappers prove that it
does not launch a second request. No automatic fallback or schema migration occurs.

## Ownership

| Field or operation | Owner |
| --- | --- |
| Atomic observations, polarity, assessability, claim type, uncertainty and reviewer questions | Model-led draft, challenged by subsequent reading and human review |
| Summary/checklist/finding observation references | Model; decoder validates the reference graph without inventing observations |
| Evidence catalogue | Host, from independently validated source/tool receipts; descriptions remain untrusted data |
| `bbox_evidence_ids` | Model selects applicable source-evidence IDs; host supplies their exact previously verified geometry |
| Source SHA, study/scope/de-identification, transformations, workflow journal | Host assembler only; forbidden in the model draft |
| Model identity and elapsed time | Host request/runtime observations, never model-authored fields |

The public package remains the sole owner of scientific dataclasses and canonical
schema. Claim definitions are derived from its pinned schema, not copied into a
second local schema file. `draft_version: "1"` is a transport version, not the
canonical schema/protocol version. The sole changed finding representation is
`bbox_evidence_ids` in place of model-authored `bboxes`. Every other finding,
observation, checklist and quality definition retains the public constraints.
Required modality axes come from the public profile registry.

The model may select no box when localization is unavailable. It cannot invent a
box, hash, verification flag or evidence record. Tool probabilities/class labels
cannot provide source geometry: select the separately validated source-region or
source-frame evidence when a spatial tool has such corroboration. Non-spatial
tool evidence may still support an observation through ordinary `evidence_ids`.
Selection only proves which host geometry is referenced, not that the model chose
the medically correct location. That requires localization/reader evaluation.

## Request and decode path

1. Collect a PHI-free host evidence catalogue from the actual source and native
   tool receipts. Validate nonce/run/source/coordinate provenance upstream. Do not
   relabel a model assertion as a trusted host record.
2. Preserve a snapshot of the catalogue actually supplied to the request. Generate
   `build_scientific_draft_prompt(modality, trusted_evidence)` and attach the correct
   source image through the ordinary public OpenClaw Gateway image contract.
   The prompt is a protocol suffix; it neither supplies image pixels nor proves
   intake/QC/blind read/tool ordering. Those must be instrumented where they happen.
3. Pass the exact UTF-8 JSON response-body bytes to `decode_scientific_draft`, with
   the same host catalogue, observed model identity and elapsed time. Do not first
   round-trip through the legacy dict parser: duplicate JSON keys and original
   byte identity would already be lost.
4. Keep the returned `DecodedScientificDraft.response_bytes` and SHA in the
   protected local run record. This retains the supplied JSON body, **not** a full
   Gateway/WebSocket transcript, event authenticity proof or automatic disk store.
   No response content is logged by the decoder.
5. Resolve the referenced evidence IDs against the original trusted host snapshot
   and pass precisely that subset to `assemble_review_contract`, together with
   actual source/transform bytes, manifest and journal. The decoder omits unused
   catalogue entries; do not copy its output into a `trusted_evidence` argument
   merely to make equality checks pass.
6. Expose a canonical draft only after the unchanged public validator passes.
   Retain ordinary failed/incomplete attempts without upgrading them to acceptance.

This protocol is intended to replace the corresponding model-response format in
an instrumented pipeline, not add a post-hoc model call that invents a ledger from
an already published prose report. Transport capture, real stage journal, native
text collector, source/ROI intake and desktop/export wiring are still required.
The [native source-evidence adapter](native-source-evidence.md) now verifies exact
tool receipts and App crop bytes in isolation; it does not collect them from the
live Gateway or activate this model protocol.
The current active 16-key skills/schemas and default inference route are unchanged.

## Failure behavior and limits

- Reject duplicate JSON keys at every depth, non-finite numbers (including numeric
  overflow), invalid UTF-8/surrogates, trailing prose/Markdown, empty/oversized
  responses and excessive JSON depth/node count. No delimiter repair or type coercion.
- Maximum response size is 512 KiB; depth 32 and 50,000 nodes. These are parser
  resource limits, not clinical exclusions or a limit on the cohort size.
- Reject missing axes, duplicate claim IDs, dangling references, unsupported
  summary/checklist claims, normal/absent/contradicted retained findings, malformed
  host evidence, unverified geometry and unsupported localization references.
- Non-diagnostic quality cannot retain findings, diagnostic hypotheses or
  assessable clinical checklist axes. Descriptive quality observations may explain
  what was visibly unreadable; the decoder cannot establish medical truth from text.
- Only pinned schemas/validators are cached. Each returned schema and decoded
  result is a private snapshot; source evidence and model responses are not cached.
- Fixed error categories omit response text. Declared catalogue provenance and
  workflow are not independently attested here. A deliberately wrong-source but
  internally consistent catalogue can decode, and must fail host assembly against
  the actual source bytes; a test preserves this distinction explicitly.

The remaining public contract/study semantics are not waived. Successful decoding
alone is not canonical contract validation, clinical accuracy or image interpretation.

## Verification checkpoint

82 new synthetic tests cover strict parsing, host-field injection, all three
modality schemas, reference graphs, exact geometry, no aliasing, byte retention,
non-diagnostic behavior and actual Gateway routing/retry guards. With host-assembly
and public-model-ownership checks, **145 tests pass in 2.87 seconds**. Ruff,
formatting and focused module mypy pass; the untyped jsonschema import is explicitly
annotated because the installed runtime wheel has no stubs, not because behavior
checks were disabled. No runtime dependency or lockfile was added.

Test-authoring failures were retained: pytest rejected a fixture named `request`;
the first corrected run then reported 116 passes and two setup errors with huge
automatically generated malformed-byte parameter IDs. Short SHA-based IDs avoid
raw input in test names and allow the intended oversized/deep JSON cases to run.
The fixture also stopped rebuilding the identical schema for every payload field.
The corrected combined parser/assembler run passed 117 tests in 1.15 seconds before
the additional routing/non-diagnostic/cache checks. These timings are test/helper
performance, not evidence of faster or more accurate model inference.

Full unit/integration/smoke regression passes **1,902 tests**, with **seven explicit
conditional skips**, in **206.80 seconds** under portable Node 24.18. The skips are
the candidate's own optional portable-Node directory, private frozen cohort data,
three opt-in frozen-package tests and two native GUI opt-ins. Four documentation
link tests also pass. No new actual scientific-protocol model run, EXE rebuild or
public binary release is claimed. The prior 3029dfb EXE remains independently
verified but does not contain this candidate implementation.
