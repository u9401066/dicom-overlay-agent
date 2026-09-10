# Windows package audit — 2026-09-10

## Measured comparisons, not release approval

Both builds used clean UI repair revision `ea6601e`, CPython 3.13.12,
PyInstaller 6.19.0, Pillow 12.1.1, Qt 6.10.2, pinned OpenClaw 2026.7.1-2 and
portable Node 24.18.0. Separate output directories preserve both baselines.

| Layer | Without UPX (MiB) | UPX 5.2.1 (MiB) |
| --- | ---: | ---: |
| Launcher | 4.46 | 4.46 |
| App / Python / Qt | 84.92 | 55.67 |
| OpenClaw | 164.60 | 163.19 |
| Node | 88.25 | 22.43 |
| Total | 337.77 | 241.29 |

Both existing verifiers returned `status: ok`, with real EXE selfcheck,
font/JPEG/PNG/logging/review-export smoke, native harness tool registration,
OAuth-only provider loading, no banned payloads or runtime residue. No model
request was made. UPX was detected in actual PE payloads, including Node;
unsupported/CFG-enabled libraries were not forcibly compressed. A successful
CLI/plugin load does not replace packaged GUI, HTTPS/OAuth, startup timing or
endpoint-protection testing of compressed binaries.

The official UPX 5.2.1 Windows x64 archive SHA-256 matched GitHub metadata:
`eabc6792a347d45e945be7748423e7868fd01b0d2bcaa2f4b1031fd71ff69bda`.
No global installation or permanent PATH change was made.

## Ambient DLL source defect

Inspection of PyInstaller's `Analysis-00.toc` showed native files resolved from
the host's MiKTeX and TortoiseGit directories. The existing bundle verifier did
not detect this provenance defect. These measurements therefore remain
**ambient-PATH baselines**, not hermetic or approved release artifacts.

`scripts/build-windows-package.py` now runs the release build with only the
selected Python environment/runtime and Windows system directories on PATH.
Inherited Python/Qt/QML import paths are removed. UPX is selected by an explicit
tool directory without adding that directory to DLL lookup. After PyInstaller,
the wrapper parses its data-only TOC and rejects native sources outside the
build environment, selected Python runtime, staged OpenClaw, portable Node and
Windows roots. A source-classified, hashed native inventory accompanies a
passing bundle; local absolute user paths are not written into that inventory.

Regression checks cover mixed-case PATH pollution, unrelated Qt/Python paths,
unresolved Windows roots, sibling-prefix escapes, empty/malformed inventories
and protected output boundaries. Full regression: **1305 passed, 4 explicit
opt-in skips**; Ruff passed.

The isolated-PATH UPX rebuild at `8ba5ea8` passed the existing package verifier
and the new source audit: **84 native source files** (52 build environment,
24 Python runtime, 7 staged OpenClaw, 1 portable Node), none from ambient apps.
It measures **239.03 MiB total**: launcher 4.46, App/Python/Qt 53.41, OpenClaw
163.19, Node 22.43 MiB. The native inventory itself is included in that total.
The compressed Node executable successfully fetched official npm metadata over
HTTPS (Node 24.18.0, exact package 2026.9.3); no auth or model traffic was sent.
This does not close the real packaged GUI/OAuth/clinical or security gates.

## Publication blockers

### OpenClaw 2026.9.3 isolated candidate, fe0a612

The notice-preserving UPX candidate passed static package verification at
**336.43 MiB** (launcher 4.46; App/Python/Qt 53.84; OpenClaw 260.17; Node 22.43).
Its 89 native sources are within approved build/runtime roots; all 52 marked
UPX PE payloads, including `.pyd` / `.node`, pass `upx -t`. This is a local
candidate, **not an approved release**. The large difference from the old-pin
239.03 MiB baseline is chiefly the new upstream runtime; no internal `dist`
chunks were removed. App-layer and launcher budgets remain met.

Actual frozen Gateway smoke failed because `GatewayManager._port` was not
propagated to the CLI. The subsequent source-App check proved the corrected
random loopback port, public authentication, exact local provider request,
and explicit Codex plugin exclusion, but failed the previous assumption that
BOOTSTRAP.md must remain in a managed workspace. Tests now distinguish five
packaged templates from four persistent workspace files, consistent with the
[upstream workspace contract](https://docs.openclaw.ai/concepts/agent-workspace).
Fresh frozen rebuild and complete smoke must still pass.

### Corrected rebuild, f184258

The fresh `dist-9-3-portfix-upx` bundle passes static verification and **all 19
packaging smoke tests**. The actual windowed EXE starts its own Gateway on
port 56969, authenticates through public `connect`, sends the exact synthetic
PNG to the local fake provider, receives the pinned runtime's expected public
401 event, and stops its owned process. The test verifies four persistent
workspace files, keeps five template assets bundled, and rejects any Codex
runtime plugin load/command. No leftover test Gateway was observed; the
independent Astra cohort Gateway stayed running throughout.

The corrected tree measures 352,774,101 B before writing its verifier manifest;
the complete archive input, including that manifest, is 352,791,459 B / 18,721
files. App layer: 56,453,976 B; launcher: 4,681,490 B. All 89 native sources are
approved, and all 52 UPX-marked PE files pass integrity testing.

| Local archive method | Archive size | Creation time | Decompressed verification |
| --- | ---: | ---: | --- |
| ZIP Deflate 1 | 154.44 MiB (161,945,565 B) | 9.140 s | All file SHA-256 values match |
| ZIP Deflate 9 | 141.14 MiB (147,995,486 B) | 23.529 s | All file SHA-256 values match |

Deflate 9 reduces distribution bytes by about 58%, without pruning runtime
chunks or changing the installed footprint. Its local archive SHA-256 is
`efe1c86c36aa9a8b1627e27a4ee4ad609d1fffde8b6a6db0777fc4607fab5431`.
These are measurements on this host during the ongoing cohort, not a startup
speed comparison or a published download. Real candidate GUI/OAuth/model,
clinical/partial-image/DPI/rollback and license gates remain open.

Local regression: 1327 unit/smoke tests pass with 5 explicit opt-in skips;
55 mock integration tests additionally pass. CI 34483865336 passes (1379 tests,
8 platform/opt-in skips) and Secret scan 34483602372 passes.

Notice inventories preserve 324 npm notices plus 21 App/Python/Node/runtime
notices with hashes. Installed PyQt6 metadata is GPL-3.0-only; the project's
Apache-2.0 license does not establish binary distribution rights. Maintainer
decision on GPL-compatible distribution versus a commercial PyQt entitlement
is pending. No license change or binary release has been made.

Gitleaks' default rules exclude node_modules. A vendor-inclusive text scan
with that single path exclusion removed scanned 235,971,096 bytes and flagged
24 items. All match the locked installed source bytes: symbols/exports,
translation or schema text, database record names, OAuth public client ids,
WebSocket fixtures and an upstream TTS shared service constant. That constant
is retained as an upstream design risk, not misrepresented as a local account
credential leak or a guarantee of vendor safety. The initial default
513,562-byte scan is not a
vendor/binary clearance. Reports redact matches; do not blanket-allowlist
vendor code or call compressed binary contents scanned.

The old pinned lock has 11 affected production package entries (7 high / 4
moderate), all present in staging. See SECURITY.md and the September 10 upgrade
audit. Neither comparison may be published as a new binary release. Candidate
2026.9.3 upgrade, native ownership/clinical/GUI gates and final dependency audit
remain required. The ongoing Astra GUI cohort uses a separate frozen runtime
and is unaffected by these package experiments.
