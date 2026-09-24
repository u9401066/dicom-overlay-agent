# Interaction package and marker promotion — September 24, 2026

Two distinct checkpoints are recorded here. Neither is a new clinical cohort or
proof of the external-browser end-to-end workflow.

## Frozen interaction checkpoint: bd8f303

The clean `bd8f3036c164d4dab23fa4bc8569f5454c292a72` source was built into a new
isolated `dist-interaction-bd8f303-upx/DICOMOverlayAgent/` folder. Previous bundles
were retained. Frozen Python 3.13.12, locked build dependencies, portable Node
24.18.0 and pinned OpenClaw 2026.9.3 were used; no provider/model migration was
performed. The clinical YAML/generated views and SQLite content hash match:
`0d35360aa941f0fc4a532c6fc204fee32fae7fdab866376c4ac82925a1e612c1`.

The executable SHA-256 is
`451673935c3627127a97e9de9a477c55d29e8478f492559fbf37fa1451bfcf0c`.
Archive inspection compared the actual frozen code objects with `git show` at
that exact commit, normalizing code filenames only. All seven compared modules
match: entrypoint, regional conversations, overlay agent, window picker, overlay
window, settings dialog and screen monitor. This directly establishes that the
package contains the ROI-wide Mark fix, regional history, external-window picker
and cautious heading; it does not exercise native GUI interaction.

The build's native-source audit accepted 90 files with ambient DLL search paths
removed. UPX was enabled; CFG-protected binaries were deliberately left intact.
Two small binaries (`win32-console-mode.node`, `python3.dll`) reported
NotCompressibleException and were retained uncompressed by PyInstaller. Missing
Windows API-set names reported for the optional OpenConsole helper are build
warnings, not evidence that every terminal/helper path works.

Private code-comparison receipt:
`data/tmp/package-interaction-bd8f303-code-receipt.json`.
The opt-in frozen suite passes **20 tests in 147.77 seconds**, including EXE
self-check, codecs/logging/review export and isolated bundled-Gateway synthetic
image transmission to a loopback provider. That provider deliberately returns an
authentication failure; the test verifies the exact image and public error/usage
contract, not a real provider/model inference. General package verification also
passes: 18,771 files, launcher 4.70 MiB, App layer 54.44 MiB, OpenClaw 260.14 MiB,
Node 22.43 MiB, total 337.01 MiB. Forty-five App-layer UPX payloads were observed.
The bundled plugin publicly registers `dicom_bbox_validate` and
`ecg_founder_analyze_waveform`; the fabricated OAuth-only migration fixture passes
without a Codex agent runtime, real authentication or model requests.

Manifest payload-tree SHA-256:
`bc2ce25e79fd1a690f47c0c012c87ffb5e83064f8faca431772975a7e3499407`.
The verifier's `source_provenance` describes the **inspection-time** worktree,
which already includes the subsequent patch below and therefore correctly says
`git_dirty=true`. It is not a clean build-source attestation. The clean build
preceded those edits; the independent frozen-code comparison above binds the
seven relevant modules to bd8f303. Both receipts are retained without rewriting.
No public binary release or refreshed native/browser acceptance is claimed.

## Subsequent source fix: preserve a promoted marker's conversation

Before this fix, confirming ADD consumed the manual marker, but conversation
history remained keyed under the manual identity. Inspecting the new finding
looked up its new ID and opened an empty thread. Same-image manual and finding
histories correctly remained separate in general, but the explicit transition
after user approval was missing.

The source now moves the exact manual-region thread to the newly confirmed
finding ID after successful writeback on the currently displayed source. It
preserves completed questions, answers and proposal text. It never merges by
overlap, overwrites an existing target thread, or migrates across source hashes.
Another manual mark at the former coordinates starts a separate thread.
Conversation text remains review context, not confirmed scientific evidence;
the existing report audit records the actual user confirmation.

The queued apply-result GUI callback also checks that its result is still the
displayed snapshot. A late callback after image invalidation or a newer result
must not resurrect old boxes, summaries or history.

Targeted verification: 85 tests pass, including current ADD/REVISE callback wiring,
late callback rejection, identity conflicts, source mismatch, exact-region
matching and detached-history rejection. Callback tests execute the actual
nested callback extracted from source with mocked UI dependencies; they are not
actual desktop interaction. Full source regression: **1,658 passed, six skipped
in 213.17 seconds**. The six skips are private-cohort, frozen opt-in and native
Windows opt-in gates, not passes. The separate frozen suite above exercises its
three packaging gates against bd8f303, not this later source patch.

This subsequent source fix is **not inside the bd8f303 executable**. Actual
manual ADD → Apply → Inspect → follow-up, proposal rejection, cross-DPI/monitor
selection, browser capture/QA and >=100 current-model real-GUI cases remain
required. Desktop focus was not taken during this checkpoint.
