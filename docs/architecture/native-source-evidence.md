# Native source-evidence binding — isolated candidate

`infrastructure.source_evidence.bind_native_bbox_evidence` supplies the geometry
adapter between the actual native bbox producer and the
[scientific draft decoder](scientific-model-draft.md) /
[host assembler](host-evidence-assembly.md). It is not connected to the desktop
inference path yet. The opt-in [scientific image session](scientific-image-session.md)
now calls it between retained blind reading and reconciliation, with original
Gateway tool bytes and separately collected audit snapshots. This is not live
App activation. It does not change the sealed 120-case GUI cohort,
default 16-key inference schema, public harness pin or OpenClaw Gateway protocol.

## What is bound

The caller supplies the immutable authorized ROI image bytes, exact image bytes
used for this tool turn, independently collected native audit record and exact
UTF-8 `content[0].text` bytes, host nonce, observed tool-call ID, modality and opaque
study asset ID. An explicit host de-identification assertion is required; the
adapter does not detect patient information or authorize wider screen capture.

- Whole-image turns require identical source and tool-image bytes.
- Crop turns reproduce the existing App's floor/ceil pixel crop and short-edge
  Lanczos resizing, and require byte-for-byte equality with the tool image. The
  resampled pixel count is bounded before allocation. No alternate public crop
  implementation is substituted: its rounding/encoding would differ from the App.
- Remapping uses that actual integer pixel rectangle, not the nominal floating
  request. A public transformation record retains parent/output hashes, source
  dimensions, pixel rectangle and output dimensions.
- The native audit's source hash, nonce, call ID, accepted/rejected counts, exact
  text hash and four-decimal coordinate multiset digest must all match. Strict
  bounded JSON rejects duplicate keys and non-finite values. A nearby coordinate
  with the same rounded digest is rejected unless it is itself canonical.
- Only accepted boxes become public `Evidence(kind="source_region")`, bound to
  the primary source and asset. Rejected-only receipts produce no evidence, not
  an invented broad fallback. Raw tool reasons are not promoted to observations,
  instructions or evidence descriptions.

The returned frozen transport receipt keeps exact tool text bytes (excluded from
its repr), their hash, the audit-record hash, public evidence and transformations.
It does not write these bytes to disk. The host must retain protected originals
and pass only the referenced evidence subset to assembly. Scientific data types
remain owned by the pinned public harness; this is not a duplicate model schema.

## Scope and trust limits

`verified=True` means source/receipt/geometry agreement, **not** medically correct
localization or diagnosis. A hostile caller controlling both audit and tool text
can forge agreement; these hashes are not signatures or an independent execution
observer. The actual host must collect both outside the final model JSON and
bind the observed call to its real run journal. `recorded_at` is not a verified
timestamp. A model-supplied receipt is not accepted as independent evidence merely
because it has the right shape.

The Gateway client now has an opt-in [visible-output collector](gateway-evidence-capture.md)
connected to its receive loops. Its exact native text projection still needs live
acceptance; default desktop inference does not enable it. A complete canonical
execution journal, intake/study-scope and desktop export wiring remain required.
No old prose report or model bbox is retroactively
upgraded to canonical evidence. The effective-pixel remap applies to this new
adapter; it is not a claim that every legacy multipass/DPI path has been changed.

## Reproducible verification

`tests/smoke/test_native_source_evidence.py` invokes the repository's actual native
JavaScript bbox tool with synthetic pixels under Node 24.18. It collects the
producer's text and isolated audit file, then tests whole-image, crop, clipped and
rejected-only receipts. This exercises the real producer, **not** a live Gateway,
GUI or model. Positive decoder/assembler paths still use explicitly synthetic
clinical claims and host event journals.

The synthetic 151 × 113 source requests `(0.111, 0.17, 0.49, 0.52)`, producing
pixel rectangle `(16, 19, 91, 78)`, a 75 × 59 crop and 651 × 512 tool image. Tests
check source-coordinate round trips to 1e-12 and distinguish actual pixel bounds
from nominal float bounds. Negative cases cover swapped sources/crops, nonce/call
binding, counts, text changes, duplicate/non-finite JSON, malformed geometry,
canonicalization collisions, resource limits and untrusted tool text.

The adapter reuses extracted App crop bounds, native digest/record helpers and
bounded JSON ingestion. Existing callers retain their behavior; no dependency,
runtime package, subscription setup, prompt or scientific schema was added.

The 53 new native-source checks pass in 0.65 seconds with portable Node 24.18;
focused mypy passes for four modules, Ruff/format passes for seven changed Python
files, and all four documentation-link checks pass. These are component-test
measurements, not model latency or diagnostic accuracy evidence.

Full unit/integration/smoke regression: **1,955 passed / seven explicit skips in
201.18 seconds**. Skips remain the candidate-local portable Node directory,
private cohort artifacts, three opt-in frozen-package checks and two native GUI
checks. Native producer tests used the existing supported Node 24.18 on PATH.
No new EXE or scientific-protocol GUI acceptance is implied by this run.
