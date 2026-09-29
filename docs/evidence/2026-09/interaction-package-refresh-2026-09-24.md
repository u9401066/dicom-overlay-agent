# Interaction package refresh — 2026-09-24

This is a local development package, not a public binary release or clinical
acceptance. It refreshes the older 6e6734e EXE with the source fixes already tested
in the real desktop. The ongoing 120-case GUI cohort is not interrupted or moved
to this executable; its original source/config/driver and receipts stay unchanged.

## Exact scope

Clean source commit `3029dfb155d673b0002870ce570ee9e5c58b3d40`, built in the
`data/tmp/direct-harness-worktree-20260910` worktree. This is **not** a build of
the separate `agent/canonical-evidence-20260924` host-assembly candidate.

The refreshed package includes the source changes since 6e6734e:

- Viewer translation uses current screen projection while preserving the immutable
  captured source and regional history; geometry changes invalidate stale ROI.
- Native external-window picker selection uses the actually selected UI item.
- ROI preview keeps selected source pixels visible.
- Publication verifies that the source image is still current after inference;
  changed images cannot publish or export a stale report.

It also retains the earlier ROI-wide Mark interaction, separate per-region
conversation threads, manual-to-finding history promotion and turn-to-outcome IDs.
Actual source-App evidence is linked from the
[documentation index](../../README.md); those tests are not silently relabeled as
tests of this new frozen executable.

## Build and code identity

The isolated no-dev build uses locked CPython 3.13.12, PyInstaller 6.19.0,
Node 24.18.0, OpenClaw 2026.9.3 and UPX 5.2.1. No runtime dependency, public
Gateway protocol, model route, capture ROI or submodule pin changed.
The seven-rule clinical YAML/generated views/SQLite parity check passes with hash
`0d35360aa941f0fc4a532c6fc204fee32fae7fdab866376c4ac82925a1e612c1`.

Native dependency inspection accepts **90 files** from approved roots with the
ambient DLL search PATH removed. CFG-protected binaries remain uncompressed.
The small `win32-console-mode.node` and `python3.dll` UPX attempts report
NotCompressibleException; PyInstaller retains the original binaries. These are
preserved warnings, not blanket proof that all optional helper paths work.

The executable SHA-256 is
`b3323a77430e02897259a4a14a7d8114c4605dcf3e66fc077ab044f4208a8162`.
Archive inspection compares **all 60 bundled App code modules**, including the
entrypoint, against `git show` at that exact source commit. Only recursive code
filenames are normalized; compiled constants/code are not rewritten or executed.
All compare equal under the same Python version and optimization level.
This is App code identity, not independent attestation of all dependencies/data.

## Verification

The opt-in package smoke suite passes **20 tests in 94.48 seconds**. It runs the
actual EXE self-check, frozen image codecs/logging/export, and a copied isolated
bundled Gateway with a synthetic image and loopback provider. The provider's
intentional authentication failure proves the exact image/public error contract,
not real subscription/model inference. No live cohort window is manipulated.

General bundle verification also passes: **18,771 files**, launcher **4.71 MiB**,
App/Python/Qt **54.45 MiB**, OpenClaw **260.14 MiB**, Node **22.43 MiB**, total
**337.02 MiB** (353,388,697 bytes). The manifest records a clean inspection-time
source at the exact build commit, plus the independent code check above.
All 45 observed App-layer UPX payloads are present; the transfer audit checks
53 packed native payloads across the entire bundle with `upx -t`.
The general verifier took several minutes while file I/O counters advanced;
its original process finished successfully, without restarting or weakening checks.

The create-only Deflate-9 ZIP is **141.58 MiB** (148,453,797 bytes). Every one of
18,771 entries round-trips with the same size and SHA-256; the source bundle is
unchanged afterward. The first local transfer helper invocation hit Windows'
default cp950 decoding on the UTF-8 verifier report, before creating output.
Explicit UTF-8 fixed the helper; no receipt or archive was overwritten.

- Payload-tree SHA-256: `2b2230d9a2692fd99aba3553c1427f85eae42a5bab5832568c2a2299420e0706`.
- Source-tree SHA-256: `d52465831c8e61984c215c8e704342c1fc64ee484eaf3fee3e2542fc9aa7263d`.
- ZIP SHA-256: `0cf19881540a7f696e16ca187a61615f7912bc9fc366dc181c65f96913f3a8e6`.

Native GUI acceptance of this new EXE,
cross-monitor DPI, clinical cohort scoring, canonical desktop ledger integration
and the PyQt6 binary-distribution license gate remain open.

At September 24, approximately 16:01 UTC (September 25 in Taipei), the original
live GUI cohort independently verifies **35 / 120** cases, 85 pending, zero
invalid or technical-failure receipts. Gold remains unopened. The actual case-029
summary was visually inspected: critical-first refinement selects the high-priority
candidate and precordial support probe while deferring two info candidates;
unresolved checklist axes remain incomplete, not falsely normal. This describes
execution and presentation, not a gold-scored diagnosis or comparative speed gain.

## Private artifacts

All paths below are relative to the direct-harness worktree, not this documentation
candidate. Previous packages are retained, and no archive is publicly uploaded.

- `dist-interaction-3029dfb-upx/DICOMOverlayAgent/DICOMOverlayAgent.exe`
- `data/tmp/verify-frozen-3029.py`
- `data/tmp/package-interaction-3029dfb-code-receipt.json`
- `data/tmp/package-interaction-3029dfb-verifier.json`
- `data/tmp/verify-package-transfer-3029.py`
- `data/tmp/package-transfer-interaction-3029dfb/receipt.json`
- `data/tmp/package-transfer-interaction-3029dfb/DICOMOverlayAgent-3029dfb-deflate9.zip`
