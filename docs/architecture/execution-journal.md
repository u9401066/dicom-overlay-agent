# Host execution journal — isolated component

`application.execution_journal.ExecutionJournal` records callbacks as they run,
not a completed stage list inferred from the final model answer. It is a building
block for [host evidence assembly](host-evidence-assembly.md), **not yet wired into
the desktop or the active 120-case GUI cohort**. Existing results are not upgraded.

## Execution boundary

The caller supplies immutable source bytes and an explicit trusted
`deidentified=True` assertion. The journal binds a new host run ID and source
SHA-256 without retaining the image. This assertion does not detect burned-in PHI.

Stages run in this exact order: intake, quality gate, blind pass, optional
independent evidence, reconciliation, optional targeted second look, contract
validation, and human handoff. `execute(stage, operation)` invokes one async
callback exactly once and accepts a `StageOutput(value, artifacts)` receipt.
There is no import-completed-events method, implicit skip, automatic retry or
post-hoc relabeling of legacy coarse/final model turns.

- Intake artifacts must include the exact source bytes by hash.
- QC returns the pinned public `imageQuality` shape, not a duplicate local model.
  A `non_diagnostic` result blocks all interpretation callbacks before invocation;
  these stages require explicit `non_diagnostic_input` skips. Other required
  stages cannot be skipped. Optional stages use the fixed `not_requested` reason.
- An active record says `running`, never `completed`. Concurrent/reentrant,
  repeated and out-of-order execution fails before invoking the new callback.
- Failure and cancellation retain a terminal record and prevent continuation in
  that run. A callback that swallows a newly requested task cancellation cannot
  return an ordinary success receipt. Explicit host `uncancel()` manipulation is
  outside this trusted-callback boundary; this is not a sandbox.
- Every completed callback supplies original nonempty immutable artifact bytes:
  at most 128 artifacts, 32 MiB each, 64 MiB total per stage. The journal stores
  only their SHA-256 values; the caller separately preserves actual raw evidence.

Immutable snapshots contain host run/source identity, sequence, actual UTC start,
monotonic start/end, status, fixed outcome category, artifact hashes and the prior
record hash. A final record hash uses the public canonical JSON hashing helper,
with its own `record_sha256` field empty while hashing. Running records are not
sealed. No model prose, exception messages, paths, tool rationale, source bytes or
hidden reasoning are stored or logged by this component. Output receipt reprs
also hide values and raw bytes.

`workflow_events()` projects only recorded facts into the public event shape;
it does not fill, reorder or upgrade records. An active stage prevents projection.
The public vocabulary represents cancelled execution as `failed`; the private
record retains `cancelled`. Incomplete or failed event prefixes still fail full
canonical assembly.

## Integration and trust limits

A callback returning successfully proves its host execution returned, not that
the clinical interpretation is correct or that an opaque provider performed an
internal blind read. A trusted caller can still supply a no-op or false artifacts.
The hash chain is not a signature or an independent observer. Source-byte image
decoding and crop validation belong to the [source adapter](native-source-evidence.md);
visible response/call identity comes from [Gateway capture](gateway-evidence-capture.md).
Its `request_image_evidence()` API can now supply the exact response artifacts
directly to stage callbacks without the legacy parser. A synthetic QC integration
test exercises that connection; actual clinical stage prompts/App wiring remain.

Full public assembly requires completed contract-validation **and** human-handoff
events. Integration must therefore separate actual content/schema checks and
actual review availability, then call the unchanged full assembler with the
completed journal before exposing a canonical export. Do not invoke full assembly
inside an unfinished validation stage and fabricate future successful events to
make it pass. `human_handoff` means review availability, not physician approval,
report signing or a PACS writeback. A final assembly rejection remains a rejection.

Current tests use explicit synthetic callbacks, including the complete
journal-to-public-assembler path. They do not establish live clinical execution.
Default desktop requests, prompts, models, ROI, overlay mapping, Gateway protocol,
public schema/submodule, dependencies and packaged executable are unchanged.

## Verification

36 journal checks cover order, source identity, artifact limits, public QC,
non-diagnostic blocking, skips, active snapshots, actual and swallowed cancellation,
failure/replay prevention, hash chains, immutable outputs and assembly rejection
of incomplete history. Together with the 44 assembler tests: **80 passed in
0.99 s**. Ruff, formatting and focused journal mypy pass. Full regression is
recorded in the accompanying Memory Bank checkpoint after completion.

The first full run reported 2,075 passed, seven explicit skips and one failure:
the orphan-orchestrator guard correctly rejected an unregistered, unwired
`ExecutionJournal`. Its deferred registry now names the component and exact
activation prerequisites. The guard and its stale-entry/reason checks remain
enabled; no dummy entrypoint reference pretends that the component is active.
The corrected full run passed **2,076 tests / seven explicit skips in 205.77 s**
under Python 3.13.12 and child-process Node 24.18.0. Skips cover this worktree's
absent optional portable-Node directory, private frozen cohort, packaged runtime
opt-ins and native Windows capture/input opt-ins. Qt used offscreen mode; this
run did not open desktop windows or perform new real model acceptance.
