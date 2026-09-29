# Source-bound history candidate package — September 29, 2026

Actual new local frozen build from clean source
`69683fa3f769709fdd90918b324fcdd06c6c307c`, public harness gitlink
`d9798dae0cf4ac3e25578da127801bce6d4391b3`. This is not a public binary release,
replacement of the installed EXE, or new clinical acceptance evidence.

It includes [regional history import/continuation](../../architecture/regional-history-import.md),
the earlier ROI-wide Mark and separate current-region conversations, and the
[bounded publication recovery](viewer-publication-recovery-2026-09-29.md).
Historical context cannot select a current finding or apply an old report proposal.

## Build identity and actual frozen checks

- Frozen no-dev environment: Python3.13.12,25 packages, PyInstaller6.19.0,
  UPX5.2.1; pinned Node24.18.0/OpenClaw2026.9.3. Official Node archive checksum
  verified. No new runtime dependency added.
- Seven-rule YAML/generated/SQLite parity:
  `8194933290c085ab81a1ab97d57154bb17d6d2e5835f2e28a327fe1cce312435`.
- PyInstaller completed in627.035s. It spent substantial time classifying18,787
  data/binary entries; the original process continued and was not restarted.
  This is not a build-speed improvement claim.
- Native source audit:90 files from approved roots, with ambient DLL search paths
  removed. All78 bundled App and11 public-harness code objects match exact Git
  sources after recursive code-filename normalization only.
- All21 opt-in packaging tests passed in140.70s on this exact EXE. These include
  frozen selfcheck, logging/codecs/fonts/review rendering, public-harness resources,
  and an isolated Gateway synthetic PNG turn with the exact expected loopback
  authentication failure. This is not subscription inference or a clinical case.
- Actual EXE runtime smoke reports all eight checks true, including the new
  `regional_history` check: v2→import→continue→v3→reimport, separate past/current
  turn IDs, wrong-source rejection and stale-thread rejection after invalidation.
- Complete package verifier passes payload/source/toolchain/notices/budgets,
  native plugin tool loading, public CLI and fabricated OAuth migration plan/apply.
  Migration-only boundary retained: no Codex runtime, no real auth, zero model
  requests. The pristine bundle contains no live `openclaw-home` or App log.
- Code CI36577926415 and secret36577926458 passed. Earlier history feature
  CI36575857832 and documentation CI36576547618 also passed.

| Layer | Bytes | MiB |
| --- | ---: | ---: |
| Launcher EXE | 5,061,637 | 4.83 |
| App + Python/Qt, including launcher | 57,222,884 | 54.57 |
| OpenClaw | 272,780,196 | 260.14 |
| Node | 23,515,464 | 22.43 |
| Entire18,771-file folder | 353,518,544 | 337.14 |

Launcher/App remain below50/100MiB budgets. Compared with the earlier36dc3c6
package, App grows20,084 bytes, while the overall folder is5,521 bytes smaller.
This apparent overall reduction is formatting, not a new runtime-pruning result:
OpenClaw notice-inventory JSON changes82,294→56,677 bytes with all324
`(path, bytes, sha256)` records identical; the plugin JS changes34,363→34,375
bytes with identical LF-normalized text and no Git content difference. OpenClaw
internal `dist` chunks were not removed to reach the budget.

- EXE SHA256: `74636ce2a0188190d9649802f0206118e6cf6d947f02013d109874ecb3be49c1`.
- Payload tree: `acef62f6573b41c2088cafc6a61fc0be3571621a295695989da71707aba8b971`.
- Source tree: `375871bc922ed99f85632ee4d7cdd7e547169f18297347a44d4cdc269cbd2a26`.

## Transfer compression

Create-only ZIP Deflate9 is148,580,906 bytes (141.70MiB), produced in21.331s.
SHA256: `3d9db0a635fcff2ab094c36e4f9168258b38832346741fb0e2c6d75b80fbdc1c`.
Every18,771 entry was independently size/hash checked; all53 UPX-bearing native
files passed integrity checks; source contents and file count remained unchanged.
The separate 7-Zip23.00 LZMA2 comparison is110,342,461 bytes (105.23MiB),
SHA256 `b0e70d75381c36a582321e23c85c56f35ca2cb4e0b0e3feb515fc61db156ac1c`.
Settings: mx9,64MiB dictionary,64MiB solid blocks,two threads. Compression took
133.570s and extraction11.439s; subsequent independent size/SHA256 verification
of all18,771 extracted files passed, and the pristine source remained unchanged.
It saves38,238,445 bytes (25.74%) against ZIP at the cost of longer compression.
The timing numbers exclude the independent inventory/hash verification phase.

Compression affects download/storage size, not installed footprint, model latency
or clinical correctness. No package was uploaded or published as a release.

## Preserved warnings and remaining gates

- Two OpenConsole UI Automation API-set warnings remain recorded in the build
  log. `win32-console-mode.node` and `python3.dll` are not compressible; CFG-marked
  runtime DLLs are intentionally not UPX-compressed. They are retained, not dropped.
- The selfcheck's non-ASCII console heading contains a replacement character in
  the captured report. Structured runtime JSON parses correctly and all checks
  return success. Diagnostic output encoding still needs a dedicated fix; do not
  interpret this package result as elimination of every smoke/UX issue.
- No native desktop history load→Send→Export→restart→reimport acceptance or new
  subscription image/usage audit has been performed on this package. Previous
  real36dc3c6 Mark/QA evidence does not attest this new functionality.
- The scientific cohort remains10 publications/2 technical failures/108 pending;
  the earlier120-case clinical baseline remains failed. No new clinical result,
  measured answer-speedup, external-model clinical validation or public-distribution
  license approval is implied.

Private retained artifacts in the `regional-history-import-20260929` worktree:

- `dist-history-69683fa-upx/DICOMOverlayAgent/` (pristine; never run as a live App).
- `data/tmp/package-history-69683fa-{build.log,code-receipt.json,tests.xml,verifier.json}`.
- `data/tmp/package-transfer-history-69683fa/`.
- Gateway test copy: `Ctemp/dicom-package-history-69683fa-test-20260929/`.

The installed old EXE, previous pristine bundle, sealed runtimes and MAIN user
edits are untouched. Any real-App acceptance must use a fresh separate copy.
