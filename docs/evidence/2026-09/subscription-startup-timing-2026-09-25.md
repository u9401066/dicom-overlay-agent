# Actual subscription startup timing — 2026-09-25

This follows the [relocation/readiness fix](portable-plugin-readiness-2026-09-25.md).
It identifies startup phases; it does **not** claim a new speed optimization,
clinical result, model comparison or executable release.

## Implementation

The two existing public OpenClaw CLI commands now emit credential-free paired
start/finish events: OAuth migration and profile listing. Monotonic timings,
outcome and exit code are logged; command arguments, environment, stdout/stderr,
credentials and exception text are not. Commands, timeouts, auth validation,
source-credential hash binding, temporary migration-plugin removal and Gateway
readiness checks are unchanged. No extra command or paid inference is added.

A pre-existing mypy narrowing error in migration-plugin cleanup is corrected by
explicitly requiring the containing load object to be a dictionary. The existing
conditional already produced `paths=None` for other types; behavior is unchanged.
No dependency, model, protocol, image schema or packaging change is included.

## Two actual App launches

Source was `20e17b90f9678cfeed4d7e238004542da9542345` plus the recorded local
instrumentation. The App was launched normally using its Qt desktop entry point,
portable Node 24.18 and OpenClaw 2026.9.3. No direct GatewayManager/auth helper
invocation stood in for App startup, and neither launch sent an analysis request.

| Observed stage | First import | Subsequent launch |
| --- | ---: | ---: |
| OAuth migration | 82.663 s | Not repeated |
| Public profile listing | 31.924 s | 11.328 s |
| Gateway process launch to actual App ready | 30.950 s | 14.405 s |
| Total App launch to ready | 148.789 s | 28.942 s |

The first runtime copy deliberately had no previous App import receipt. The
subsequent launch reused its now-verified import receipt and unchanged source
credential, but still listed the profile and waited for Gateway readiness. The
receipts independently report `reused_existing_profile=false` then `true`.
Neither enables a Codex agent runtime nor retains a Platform API key.

Do **not** interpret the total-time difference as a fivefold implementation
speedup: these are different startup conditions, first-import testing overlapped
local regression work, and OS/Node cache and machine load were uncontrolled.
The earlier approximately 136-second measurement is also not a matched baseline.
The current evidence identifies migration as the largest first-import phase;
it does not identify which upstream migration operation consumed those seconds.

Actual native accessibility observations in both launches show Analyze disabled
while `AI starting`, then enabled only after `AI ready`. Settings and Quit remained
enabled. Both Apps were closed through their own Quit button. App/Gateway processes
and the owned listener on port 18795 were absent afterward; the existing test
Viewer was retained. No new image capture, model turn or clinical claim was needed.

## Preserved private evidence

`C:/Users/Ericlab/AppData/Local/Temp/dicom-startup-profile-20260925/` holds the
launchers/configs, source receipts, four native UI observations, separate cold/warm
App and Gateway logs, private auth-import receipts, and a create-only audit.
The cold Gateway log was copied after shutdown **before** the second launch could
truncate the working log. Previous sealed batch and relocation logs were untouched.

All 79 tracked App source files were byte-identical from before the first launch
until after the second shutdown. A later formatter normalized three lines' newline
endings only; the exact executed auth module is preserved as
`codex_subscription_auth.native.py`, and newline-normalized text equality was
verified. This is not a claim that the recorded native bytes equal a later commit.

Audit SHA-256:
`7f38a522e1eae47046043830cccfa7f8488828142b386d8b05518274b090bec0`.
The audit binds logs, UI states, private auth receipts and before/after source
inventories; checks phase sequence, unchanged credential binding and zero analysis
requests; and separates first-import from subsequent startup.

## Checks and remaining work

- Eight new deterministic tests cover both commands' success, nonzero exit,
  timeout and launch failure; injected sensitive command/environment/output/error
  strings never enter timing events. Instrumentation never retries commands.
- Current full run: **2,145 passed, seven skipped in 366.26 s**. The seven skips
  remain explicit local-artifact/portable-Node/frozen-package/native-input opt-ins.
  Current collection is 2,152 tests; do not extrapolate from older dated counts.
- Final focused auth, marker, regional conversation, linkage, review and document
  checks: **105 passed in 0.99 s**. Ruff/format and auth-module mypy pass. Initial
  formatting/type checks exposed newline normalization and the narrowing issue
  described above; neither was suppressed.
- Both CI runs and secret scans for predecessor `20e17b9` completed successfully.
  This does not pre-approve this checkpoint's subsequent CI.

Next work needs controlled repeated launches and public-boundary optimization,
not bypassed authentication or a prematurely green status. Full clinical pipeline,
diagnostic accuracy, diverse inputs and current-EXE native acceptance remain open.
See [operator timing guidance](../../operations/real-desktop-tests.md#diagnose-subscription-startup-latency-without-exposing-credentials).
