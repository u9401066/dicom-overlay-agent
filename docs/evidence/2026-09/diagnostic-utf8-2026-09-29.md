# Diagnostic UTF-8 regression — September 29, 2026

Source fix following the actual
[69683fa package audit](history-package-2026-09-29.md). This does not replace or
retroactively repair that package. No desktop input, screenshot or model request
was performed for this diagnostic investigation.

## Reproduced failure

The App's diagnostic printer inherited the Windows redirected stream encoding.
The package verifier decoded output as UTF-8 with replacement enabled, so a
successful process exit could mask a damaged heading. New tests first failed
under CP1252, CP950 and ASCII: invalid UTF-8 or lost Chinese/em-dash characters.

The real pristine69683fa EXE was then invoked only with `--selfcheck` by the
stricter verifier. It returned the expected controlled verification failure:
`exit_code: -1`, `process output is not valid UTF-8`. This is the verifier result,
not a claim that the App itself exited with -1. No App log or live OpenClaw state
directory was created. Private create-only receipt:
`data/tmp/legacy-package-output-69683fa.json`.

The earlier21 frozen checks and full package audit accurately describe their
then-current tests, but are not sufficient for this newly strengthened output
contract. Do not approve69683fa for release under the new criteria.

## Fix and regression coverage

- CLI-only printing reconfigures a real `TextIOWrapper` to strict UTF-8. The
  windowed `stdout=None` path remains a no-op; `StringIO` capture still works.
  This does not alter GUI rendering, ROI, image payloads or Gateway contracts.
- The verifier receives raw stdout/stderr bytes and decodes both strictly in
  the calling thread before truncating retained text. Invalid bytes produce a
  controlled failure without echoing offending process content.
- An intermediate direct `subprocess.run(text=True, errors="strict")` attempt
  exposed a Windows reader-thread failure: decoding raised in the background,
  leaving `None` in the result. That implementation was replaced, not suppressed.
- Frozen selfcheck now requires an exact readable heading and `RESULT: OK`;
  frozen runtime smoke strictly decodes its JSON and requires `status: ok`.
- Nine new printer tests cover four stream encodings, missing stdout, in-memory
  capture, and three real Python subprocesses with forced legacy pipe encodings.
  Four verifier tests cover malformed stdout/stderr without payload echo and
  preservation of valid Chinese output plus zero/nonzero child exit codes.

Final focused run:72 passed,3 opt-in frozen tests skipped,13.03s. Ruff and mypy
for the affected source/verifier pass. These source tests and the negative test
on the old EXE do not establish a successful fixed frozen build.

## Actual Windows60911e7 candidate acceptance

The separate source-bound60911e75da4be2fb6aa526180302285b8c8c19bc build completed
in106.694s with90 approved native files. All78 App/11 public-harness code objects
match exact Git sources. This is not a controlled build-speed comparison.

All21 strengthened frozen packaging tests passed in136.30s, including strict
UTF-8 selfcheck and isolated Gateway synthetic image transport. The complete
package verifier finished successfully with no failures. Source provenance was
captured clean before the subsequent Linux fix below.

- EXE:5,061,764 bytes; App layer:57,223,011 bytes; full18,771-file folder:
  353,518,671 bytes (337.14MiB). OpenClaw/Node unchanged;127 bytes more than69683fa.
- EXE SHA256: `ea48de76de831af4d90b82abe8c2fdd82a911a333c47f71c292008743d7366ea`.
- Payload tree: `7b7e2b6395f0434345c15c0a0c43ec53c1a2d2dcbac13af066e4e35c112268ea`.
- Source tree: `e1e7751c7e69f2eec105d9ee4b6d11ddf2d01c112e93b5e5a9a87a02f918d93f`.
- Actual EXE `--explain-rules` under three requested legacy pipe encodings
  returned the same70-line/6,604-byte strict UTF-8 output with exact Chinese
  heading. Output SHA256:
  `e151c4878faee20df8cc4755c4100c8c30f250f20ccd2f664ac04661dcb6fce3`.
- Artifacts: `dist-utf8-60911e7-upx/DICOMOverlayAgent` and private
  `data/tmp/package-utf8-60911e7-{build.log,code-receipt.json,chinese-audit.json,tests.xml,verifier.json}`.

OpenConsole API-set warnings, two incompressible binaries and intentional CFG
UPX skips remain recorded. The earlier ZIP/7z sizes belong to69683fa, not this
new binary. No installed EXE replacement, new public binary or paid inference.

## Linux CI follow-up

CI36584151373 Linux job109460132959 failed with3 failed/2707 passed/20 skipped
in149.89s. All failures were the new real-subprocess encoding tests. The job log
was obtained through the existing GitHub connector after local signed-download
connections failed; the failed run is retained, not replaced by a blind retry.
That run is terminal failed; Windows and all four compatibility jobs passed.

Without pywin32, `screen_monitor` logged a non-ASCII warning at import, before
the diagnostic printer could configure UTF-8. Forced missing-Win32 imports in
Windows subprocesses reproduced the same byte offsets and ASCII exception.
The warning is now deferred until actual `ScreenMonitor` construction, after
the App's normal logging setup. It is not silenced or replaced by a test skip.

Three added missing-Win32 subprocess cases plus a constructor-warning check
first failed, then passed. Expanded focused run:143 passed/3 frozen opt-ins
skipped in16.83s. The targeted type check also exposed a missing `win32process`
untyped-library override; it now matches the other optional pywin32 modules,
without changing runtime dependencies. This follow-up needs its own green CI
and is not included in the60911e7 frozen payload.
Ruff and nonincremental mypy with the explicit current-worktree configuration
pass;31 documentation/CLI checks also pass (overlapping the143-test run).

## Remaining acceptance

Follow-up source3e94a77d2f23cb25e91aa337d4eab6099e540370 now passes all Windows,
Linux and compatibility jobs in CI36585937279; secret36585937389 passes. Linux
records2714 passed/20 skipped149.60s, including all13 CLI tests.

Its separate new EXE passes21 frozen checks in138.51s and the complete package
verifier, with clean source provenance and no failures. All89 App/harness modules
match Git. Chinese CLI output matches the same70-line hash recorded above.
The83.482s build retains90 approved native sources and the same recorded warnings.

- EXE:5,061,754 bytes; App layer:57,223,001 bytes; full18,771-file folder:
  353,518,661 bytes (337.14MiB). No runtime dependency or pruning change.
- EXE SHA256: `65d1925d93a8f292edaca2aaa46c7b42e5778e2d73099e447297ed1010ac64ff`.
- Payload tree: `d13ae9fd6c68c93f989b643515d6e2b5ad9e0b1967ae1d169178fa79c14581c2`.
- Source tree: `5cf074b385ef1b0949a0f36a2a2c2a5fe30ada4ab307a2424bf4f3194dc088e2`.
- Artifacts: `dist-cli-3e94a77-upx/DICOMOverlayAgent` and private
  `data/tmp/package-cli-3e94a77-{build.log,code-receipt.json,chinese-audit.json,tests.xml,verifier.json}`.

This resolves the diagnostic/frozen/CI checks, not native history continuation,
subscription image/usage acceptance, clinical cohort completion and public
distribution/license gates. Those remain open; the installed EXE is untouched.
