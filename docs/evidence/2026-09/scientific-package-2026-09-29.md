# Scientific candidate package — 2026-09-29

Local development package of clean host commit
`575bcdc6db54c98b396b8c8042bd08007b8fcebd`, public harness gitlink
`d9798dae0cf4ac3e25578da127801bce6d4391b3`. This is the first package of the
current scientific host-assembly candidate, not a relabeling of the older
3029dfb shared-engine EXE. No public binary release or clinical approval.

## Included implementation and identity

The package includes the opt-in scientific intake/QC/blind/native-geometry/
reconciliation/second-look/validation/Qt-handoff path, source-pixel publication
guards, canonical export, ROI-wide manual Mark and separate regional histories.
It also includes journal-bound analysis timing and readable unverified-model
metadata. Scientific mode remains explicitly opt-in for deidentified input;
packaging does not activate it by default or bypass the ROI/privacy controls.

Isolated `uv sync --python 3.13.12 --frozen --no-dev --extra build` installed
25 packages. Locked PyInstaller 6.19.0, UPX 5.2.1, Node 24.18.0 and OpenClaw 2026.9.3
were used; no dependency or Gateway contract was changed. The official Node
download passed its checksum check. The retained UPX archive matched its
previously verified SHA256. Seven-rule YAML/generated-view/SQLite parity passes:
`8194933290c085ab81a1ab97d57154bb17d6d2e5835f2e28a327fe1cce312435`.

Native source inspection accepts 90 files from approved roots with ambient DLL
search paths removed. Archive inspection compares all 75 bundled App modules
(including entrypoint) and 11 public harness modules against their exact Git
sources using the same interpreter/optimization. All 86 match; only recursive
code filenames are normalized. This is code identity, not full dependency or
clinical attestation.

- EXE SHA256: `10d35be239888e3f3301969b75e96e18233fc72a9ec01cf6f46ce777dd01c4e9`.
- Payload-tree SHA256: `62aab6781eebbcbb3eb207f51d6ddf4278e5a078ce032c02cf6c914653090ffd`.
- Source-tree SHA256: `9e074f746f9ce99cec633f4c2e8b7e3d6dd5af95c2b2a1aec3125cc9c46749d9`.

## Frozen verification and measured sizes

All 20 opt-in packaged smoke tests passed in 126.37s: actual EXE selfcheck,
frozen codecs/logging/review export, public harness resources/shared engine and
isolated packaged Gateway image/error contract. The loopback provider's expected
authentication failure is a synthetic contract check, not subscription inference.
The separate full verifier passes CLI/plugin inspection, OAuth-only migration
provider checks, notices, source/payload hashes, clean runtime state and budgets.

| Layer | MiB |
| --- | ---: |
| Launcher EXE | 4.81 |
| App + Python/Qt, including launcher | 54.55 |
| OpenClaw | 260.17 |
| Node | 22.43 |
| Complete portable folder | 337.14 |

The 18,771-file folder is 353,521,579 bytes. App and launcher stay below 100/50 MiB.
The verifier observes 45 App-layer UPX payloads. CFG-protected binaries remain
uncompressed. `win32-console-mode.node` and `python3.dll` report
NotCompressibleException and retain their originals. Build warnings for
OpenConsole's `ext-ms-win-uiacore-l1-1-0.dll` and `ext-ms-win-uiacore-l1-1-1.dll`
remain recorded; the smoke checks do not prove every optional terminal path.
No OpenClaw internal `dist` chunks were removed to achieve these numbers.

## Compression comparison with complete round-trip verification

Both archives are create-only local artifacts of the same unchanged folder.
Every one of the 18,771 extracted entries matches its original size and SHA256;
all 53 UPX-bearing native payloads across App/Node/OpenClaw pass `upx -t`.

| Format | Bytes | MiB | Compression wall time |
| --- | ---: | ---: | ---: |
| ZIP, Deflate level 9 | 148,558,590 | 141.68 | 20.454s |
| 7z, LZMA2 | 110,306,585 | 105.20 | 81.703s |

7-Zip 23.00 used level9, 64MiB dictionary/solid blocks and two threads. Its
measured extraction took8.360s; ZIP extraction timing was not recorded, so no
comparative extraction-speed claim. The 7z archive is25.75% smaller than ZIP,
without removing runtime components or changing the extracted footprint. It is
an optional distribution format requiring a compatible extractor, not a smaller
installed App or a demonstrated inference-speed improvement.

- ZIP SHA256: `328ff55d094ba3c154364e884cefc5ffe644feb1ff22806304e89cfd552a2997`.
- 7z SHA256: `1363ef5d6837dc943e66a359c93bdc8838bbc1509fd1682fab607fbbf741b947`.
- Private receipts: `data/tmp/package-transfer-scientific-575bcdc/receipt.json`
  and `sevenzip-receipt.json`; the source folder remains unchanged afterward.

## Limits and retained artifacts

Subsequent [actual frozen desktop acceptance](frozen-regional-desktop-2026-09-29.md)
now covers subscription, scientific publication and regional QA on a fresh copy
of this exact executable. It retains one failed and one successful paid attempt.
The following paragraph records gates still open at the build-only checkpoint;
clinical and distribution-license gates remain open after the GUI follow-up.

The [actual source-App replay](scientific-regional-desktop-2026-09-29.md) does
not become frozen-GUI acceptance merely because this build matches its source.
New-EXE subscription/UI/clinical acceptance, broader vendor/DPI scenarios and
the existing binary-distribution license gate remain open. The120-case scored
baseline remains a clinical failure; no accuracy or controlled speedup claim.
Both 575bcdc CI runs 36542183127/36542176453 and both secret scans passed.

All paths below are private/ignored in the canonical-evidence worktree. Existing
packages and sealed runtimes were preserved. No new paid model request occurred.

- `dist-scientific-575bcdc-upx/DICOMOverlayAgent/DICOMOverlayAgent.exe`
- `data/tmp/package-scientific-575bcdc-build.log`
- `data/tmp/package-scientific-575bcdc-code-receipt.json`
- `data/tmp/package-scientific-575bcdc-tests.xml`
- `data/tmp/package-scientific-575bcdc-verifier.json`
- `data/tmp/verify-frozen-575bcdc.py`
- `data/tmp/verify-package-transfer-575bcdc.py`
- `data/tmp/compare-package-7z-575bcdc.py`
