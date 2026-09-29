# Waveform evidence must be checked before a later image prompt

September 25, 2026. Source correction `2dd4f9e`, based on `1b1f28c`; this is an evidence-boundary
correction, not desktop waveform activation, clinical acceptance or a new EXE.

## Integration findings

The desktop screenshot path does **not** call `use_waveform_artifact()`. Only the
evaluation runner supplies a paired waveform artifact. Settings already correctly
says `Evaluation sidecar configured`, with a tooltip explaining that configuration
does not prove readiness or screenshot matching. Nothing should infer a pairing
from a filename, patient label, similar-looking image or configured endpoint.

The old evaluation prompt asks for image-first reading and then ECGFounder inside
one model turn. That is an instruction, not an independently retained blind pass.
The newer [scientific session](../../architecture/scientific-image-session.md)
executes separate QC and blind requests, but independent evidence/reconciliation
and App activation are still incomplete. This patch does not bridge those gaps.

## Reproduced defect and correction

`OpenClawClient._supporting_waveform_evidence()` previously admitted one successful
nonce-matched receipt without checking its artifact, pinned model identity or
response integrity. It could forward mismatched labels into a crop/refine prompt
even when final evaluation would later reject the receipt. It also silently
discarded conflicting records with the same tool-call ID, and public receipt
snapshots exposed mutable nested prediction objects.

An initial set of 25 regression checks produced **23 failures / two passes** on
the old code. The runtime now checks evidence **before** constructing that prompt:

- Exactly one actual receipt, not merely one success among failures.
- Current nonce and host-bound opaque artifact digest; 12-lead mode.
- Pinned ECGFounder model, revision and checkpoint, source digest, preprocessing
  revision and calibration metadata consistent with the sanitized response.
- Complete, bounded predictions with nonempty unique labels and finite numeric
  scores in `[0, 1]`; booleans are not scores. No partial salvage of a bad list.
- Sanitized response digest and supporting-only/non-spatial policy. Waveform
  labels never become image boxes or confirmed diagnoses through this gate.
- Identical receipt replay is deduplicated. Conflicting same-ID contents remain
  visible and invalidate subsequent support, including after turn resets.
- Receipt and suppressed-attempt snapshots are independent deep copies.

Rejected records stay available for audit; the client does not repair them,
silently select a more convenient success or buy another model call. The existing
evaluation rejection rules and all frozen score/seal implementations are unchanged.

## Native number serialization

The App-owned JavaScript plugin adds `response_canonical_json` to its existing
schema-1 audit record. It preserves the exact sanitized string used to compute
`response_sha256`; tool arguments, public Gateway protocol and model output schema
are unchanged. This avoids guessing JavaScript number formatting in Python, notably
for tiny finite scores such as `1e-7`.

The host strictly parses that bounded string, compares its typed JSON projection
to `response_evidence`, and verifies its original byte digest. A present but invalid
string never falls back to old serialization. Older receipts without the field
remain usable only when their reconstructed digest actually matches; ambiguous
older numeric representations fail closed. Historical evaluation validators remain
frozen and do not gain the new byte-receipt support retroactively.

This is sanitized **local audit data**, not original Gateway tool text, a signature,
proof of clinical truth, or proof that the waveform matches the screenshot. The
trusted host still owns matching provenance; a fabricated coherent local receipt
is outside this integrity check's attestation capability.

## Verification and remaining scope

Tests cover the client send/receive path with synthetic Gateway responses, native
JavaScript plugin execution with a synthetic sidecar response, wrong artifacts,
model/checkpoint drift, altered/rehashed response fields, failed-plus-successful
calls, conflicts across turns, snapshot mutation, invalid labels/scores, bounded
native strings, and six native score-format cases from zero through one.
Valid EKG support is included in the actual constructed crop prompt; invalid
support and all CXR support are absent. Request accounting remains one send and
zero parse retries for each synthetic crop.

No paid inference or new native desktop run was performed for this boundary fix.
It cannot establish improved diagnosis recall, current-EXE usability or end-to-end
independent waveform assistance. The earlier regional Mark/QA native evidence and
the failed sealed 120-case clinical baseline are unchanged.

Final local verification, Python 3.13.12, Node 24.18 and offscreen Qt:

- **2,189 passed / seven explicit conditional skips in 377.36 s**, fresh complete
  run after all source/test changes (process session 22165, terminal exit 0).
- Focused client/native plugin checks: **135 passed in 17.11 s**, including 38
  new unit cases and six new native numerical-format cases.
- Documentation links, existing evaluation validator and scientific session:
  **65 passed in 2.25 s**. Targeted mypy, Ruff and formatting checks passed.
- Staged secret scan: 40.94 KB checked, no leaks. Both remote secret scans for
  `2dd4f9e` passed; all four Windows/Linux Python 3.11/3.12 compatibility jobs
  passed. Full remote CI was still running when this local result was recorded.

The seven skips remain the optional repo-local Node directory, private frozen
cohort, three packaged-runtime opt-ins and two native Windows capture/input
opt-ins. They are not new GUI or packaged acceptance. An oversized synthetic
pytest parameter initially exceeded Windows fixture-name constraints; a bounded
test ID fixed the runner without reducing the tested 512 KiB limit or payload.

Only standard-library host code was added; Torch/NumPy/SciPy remain in the optional
sidecar, outside the bundle. ROI, overlay mapping, clinical result schema and the
OpenClaw public protocol are unchanged. Packaging size has not been remeasured.

See [the integration contract](../../integrations/ecgfounder-tool.md) for setup and
the required trusted artifact boundary.
