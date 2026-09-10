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

The old pinned lock has 11 affected production package entries (7 high / 4
moderate), all present in staging. See SECURITY.md and the September 10 upgrade
audit. Neither comparison may be published as a new binary release. Candidate
2026.9.3 upgrade, native ownership/clinical/GUI gates and final dependency audit
remain required. The ongoing Astra GUI cohort uses a separate frozen runtime
and is unaffected by these package experiments.
