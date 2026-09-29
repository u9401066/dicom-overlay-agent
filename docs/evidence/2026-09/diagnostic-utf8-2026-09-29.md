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

## Remaining acceptance

Build a new source-bound candidate without modifying the old pristine bundle,
then run the strengthened frozen tests and complete package verifier on it.
Keep its source/EXE/payload receipts separate. Native history continuation,
subscription image/usage acceptance, clinical cohort completion and public
distribution/license gates remain open.
