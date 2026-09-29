# Regional-context and readable-note package — 2026-09-29

Clean build source `36dc3c6850d9948b12941f22822beef528c60d9e`, public harness
gitlink `d9798dae0cf4ac3e25578da127801bce6d4391b3`. This is a new local candidate,
not a public binary release or clinical approval.

It includes the [dual-image regional QA](../../architecture/regional-image-context.md)
and [pixel-width report layout](review-export-layout-2026-09-29.md), as well as
the existing ROI-wide Mark input surface and separate regional conversations.
The previous575bcdc EXE is preserved and is not relabeled as this build.

## Build and frozen checks

- Isolated frozen no-dev environment: Python3.13.12,25 packages,
  PyInstaller6.19.0, UPX5.2.1; Node24.18.0 and OpenClaw2026.9.3 unchanged.
- Clinical registry's seven-rule YAML/generated/SQLite parity remains
  `8194933290c085ab81a1ab97d57154bb17d6d2e5835f2e28a327fe1cce312435`.
- Native dependency audit accepts90 files from approved roots; ambient DLL
  search paths are removed. All75 App and11 public-harness compiled modules
  equal their exact Git source with recursive code filenames normalized only.
- All20 opt-in frozen tests passed in135.15s: real EXE selfcheck, codecs/logging/
  review export, harness resources and isolated packaged Gateway contract.
  The loopback provider's expected auth failure is not subscription inference.
- Full package verifier passes source/payload hashes, notices, OAuth-only
  migration boundary, public plugin/CLI inspection, clean runtime and budgets.
- Both source CI runs36553158115/36553151886 and both secret scans passed.

| Layer | Bytes | MiB |
| --- | ---: | ---: |
| Launcher EXE | 5,041,562 | 4.81 |
| App + Python/Qt, including launcher | 57,202,800 | 54.55 |
| OpenClaw | 272,805,801 | 260.17 |
| Node | 23,515,464 | 22.43 |
| Entire18,771-file folder | 353,524,065 | 337.15 |

The folder increased2,486 bytes relative to575bcdc. No dependencies were added,
no OpenClaw internal chunks were pruned, and the100/50MiB App/launcher budgets
remain satisfied. Optional OpenConsole UI Automation API-set warnings and the
two uncompressible small binaries remain recorded, not silently suppressed.

- EXE SHA256: `ae30034779281ecaa3cb653a963ba458b66c085f3a27080d8bbb080d7664e6b3`.
- Payload tree: `e57232cd23d040cfcabb3a7e018a680e3dbfbf6ad2761ef479888491629a7f2c`.
- Source tree: `877c6d35c75940be46011f449acf92a1d157dd5f5b2d473ee19adbd8dbcc5402`.

## Transfer and desktop acceptance scope

Create-only ZIP Deflate9 is148,560,997 bytes, SHA256
`79f9e8a359db9a4885e031cdfae45da711698fc1b09bf6bf7f9c54b11548a27f`.
Compression took23.869s; every18,771 entry round-tripped with matching size/hash,
all53 UPX-bearing native payloads passed integrity tests, and the source bundle
was unchanged.

Optional7z LZMA2 is110,323,778 bytes (105.21MiB),25.74% smaller than ZIP,
SHA256 `1a8f1e9b774bc87180b50010fd718eba6464843544a36ecbf0a557b5c3c9063a`.
Compression took99.456s and extraction11.193s with7-Zip23.00, level9,
64MiB dictionary/solid blocks and two threads. Every18,771 extracted file
matched its original size/hash, and the pristine source stayed unchanged.
This reduces download size, not installed size or model inference latency.

At the build-only checkpoint, fresh EXE subscription/Mark/QA/Export acceptance
was still pending. A new owned
Viewer has opened the approved deidentified partial ECG through its actual
file dialog; that action alone does not validate the App or add a clinical case.
No paid model request occurred in the packaging checks. A subsequent full-App
run uses separate evidence and must not be confused with the package smoke. Existing
sealed runtimes were not restarted. The older120-case clinical baseline remains
a failure; broader scientific clinical evaluation and distribution-license gates
remain open.

The subsequent [actual frozen replay](frozen-regional-context-2026-09-29.md)
now passes on this exact EXE: five-stage publication, manual/AI-box QA, history,
actual long-Chinese PNG export and image invalidation. Ten Astra-medium sessions
and all three dual-image payloads are independently bound. The runtime is sealed;
a two-second shutdown WebSocket timeout and broader release gates remain open.

Private retained artifacts in the candidate worktree:

- `dist-regional-36dc3c6-upx/DICOMOverlayAgent/`
- `data/tmp/package-regional-36dc3c6-{build.log,code-receipt.json,tests.xml,verifier.json}`
- `data/tmp/package-transfer-regional-36dc3c6/`
- `data/tmp/verify-frozen-36dc3c6.py`

The new desktop copy is separately located at
`Ctemp/dicom-frozen-regional-36dc3c6-20260929`; the pristine bundle is never used
as a live OAuth/runtime directory.
