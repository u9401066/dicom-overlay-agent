# Host evidence assembly boundary — isolated development candidate

This implements one required part of the
[direct public-harness integration](direct-harness-integration.md), not the full
model-ledger pipeline. It is deliberately developed separately from the ongoing
frozen 120-case GUI run. No prior result is converted or relabeled as a canonical
clinical contract. No App main merge, binary rebuild or medical-accuracy claim.

## Implemented boundary

`application.contract_assembly.assemble_review_contract` accepts an existing
public `AnalysisResult` draft plus explicitly host-owned inputs:

| Input | Ownership and verification |
| --- | --- |
| `provenance` | Public `InputProvenance`; primary SHA/kind must match exactly one supplied study asset; de-identification must be explicitly true |
| `study` / `assessment_scope` | Host study inventory and declared scope, never inferred from an image title or fabricated by the model; arbitrary metadata rejected |
| `asset_bytes` | Immutable, nonempty bytes for exactly every manifest asset ID; SHA and modality checked |
| `transform_bytes` | Exact bytes keyed by transform output SHA; complete inventory, ordered parent lineage, unique outputs and hashes checked |
| `trusted_evidence` | Host receipt-validated public `Evidence` records; IDs/content must exactly match the model-led ledger; missing/extra/changed records reject |
| `workflow_events` | Real host journal in execution order; never synthesized or sorted from the final prediction |

The assembler deep-copies the draft and host collections, binds only the host
fields, and calls the pinned public `AnalysisResult.to_contract_payload()`
validator. Missing axes, observation references, source-bound boxes, ordered
required events, truthful partial-study scope or review state fail closed.
The original draft/trace/inputs remain unchanged and do not alias the result.
Validation exceptions expose fixed categories, not source/model text in logs.

Model-supplied or previously assembled host fields are rejected, not overwritten.
There is no code path that manufactures observations from finding prose, adds
normal checklist entries, sets a model box's `verified` flag, guesses study
completeness or appends completed workflow events merely to make validation pass.

Retained overlay boxes must refer to the primary source image. A source-region/
frame evidence record must match its manifest asset, not just any known hash.
Tool evidence requires a recorded independent-evidence stage after the blind
pass. Tool boxes need matching independently bound, verified source-evidence
geometry; a classifier label alone cannot supply a box. This permits source-backed
localization rather than banning every spatial tool result.

## Trust limits that remain explicit

- The caller must actually collect host inputs. Copying model output into the
  argument named `trusted_evidence` does not establish trust. This function is
  not an independent execution observer or a clinical evidence reviewer.
- Hashing bytes/lineage does not decode images or prove a crop/resampling operation
  produced them. The capture/crop adapter still must preserve and verify the real
  operation, parent rectangle and source-coordinate remapping.
- The public validator checks declared event sequence, not whether a model really
  performed a blind pass. Only instrumented execution can support that claim.
- A metadata-free study manifest and de-identification assertion do not themselves
  prove absence of burned-in patient data. The trusted input workflow owns that gate.
- `verified` geometry is source/receipt binding, not proof of medical truth.
  Public-contract validity is neither clinical accuracy nor specialist approval.

The default Gateway parser still produces the 16-key App draft and does not
populate the atomic observation ledger. A regression invokes that actual parser
with synthetic input and confirms assembly rejects it rather than inventing the
missing ledger. The desktop entrypoint does **not** call this assembler yet.
The separate [scientific model draft protocol](scientific-model-draft.md) now
provides a prompt/schema and strict ledger decoder; the legacy parser rejects
that version marker instead of dropping its observations. This does not activate
the new protocol or supply the still-missing host journal/native receipt adapters.

## Required next integration, in order

1. Wire the new model-led draft protocol/decoder into actual instrumented requests,
   with the matching prompt/schema tests and existing public skill invariants.
   Atomic observations, claim type, assessability, evidence and summary/checklist/
   finding links are now represented. Keep host provenance outside model authority;
   preserve original response bodies and request/run IDs at the transport boundary.
2. Instrument actual intake, QC, blind observation, optional independent evidence,
   reconciliation/second look, validation and review availability. Record stages
   where they happen; do not reclassify an old coarse/final trace after execution.
3. Build the host adapter from the existing exact native bbox/tool receipts and
   immutable capture/crop bytes, with nonce/run/source checks and round-trip
   source geometry. Clinical observation text still needs model/reader challenge.
4. Supply trusted study scope and de-identification facts from the capture workflow.
   A configured ROI alone is not a fabricated de-identification certificate.
5. Call the assembler before making a new scientific export available; preserve the
   ordinary draft and explicit rejection category if the canonical gate fails.
   Do not silently label an incomplete scientific assembly as completed.
6. Verify the connected path with synthetic contract/edge cases and new real App
   cases after the current cohort is sealed. Measure latency and clinical errors
   with explicit denominators; do not claim improvement from unit tests.

The submodule pin, public schema, transport protocol, active prompts, dependencies
and four-core behavior remain unchanged in this component checkpoint.

## Verification and environment failures

- 44 new synthetic assembly checks, including actual Gateway-parser rejection,
  immutable snapshots, source/transform/evidence identity, host-field injection,
  tool provenance, study scope and public-contract failures.
- Ruff/format and focused mypy pass; the focused module is not a claim that every
  repository module passes strict type checking.
- Fresh-worktree first full run: 1,760 passed, eight skips, five failures and 51
  setup errors. Native plugin imports could not find the uninstalled local
  `openclaw` package. This is retained as environment-failure evidence.
- Locked `npm ci --prefix openclaw --ignore-scripts` was first invoked with the
  machine's existing Node 25.6.1, which emitted unsupported-engine warnings.
  It was rerun with the existing portable Node **24.18.0**, using only this new
  worktree's dependency directory. No global install, lockfile edit or live runtime
  replacement occurred. npm reported zero vulnerabilities in that install audit;
  that is not a broad dependency-security guarantee.
- Native bbox/plugin and public ownership/Core 2 targeted checks then passed
  **93 tests** under Node 24.18. Full corrected-environment regression completed:
  **1,820 passed / seven explicit skips in 183.19 s**. The additional skip versus
  the live worktree is its own optional portable-Node-directory test; native
  plugin tests used the verified Node 24.18 on the child process PATH. The other
  skips cover private cohort artifacts, frozen binaries and native GUI opt-ins.
  Documentation links also pass (four checks). The actual GUI batch remains on
  its unchanged source; none of these unit/smoke results are new model acceptance.
