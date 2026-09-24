# OpenClaw package lifecycle preparation — 2026-09-10

## Reproduced defect

A fresh locked `npm ci --ignore-scripts` install was staged before its package
lifecycle had completed. Staging removed the package-only `scripts` directory.
The resulting public `gateway --help` invocation failed with
`MODULE_NOT_FOUND` for `scripts/preinstall-package-manager-warning.mjs`, followed
by OpenClaw's explicit "package lifecycle is incomplete" error. This is real
fresh-install evidence, not a model/provider authentication failure.

Calling the public CLI on the unprepared source afterwards ran upstream-owned
cleanup and removed the OAuth migration provider that had already been relocated
into `dist/extensions/codex`. Its original package had been pruned by the staging
step, so a subsequent migration-stage attempt correctly reported that neither
source nor staged provider remained. Only regenerable locked dependencies in the
isolated worktree were affected. They were restored with `npm ci`; no App source,
user credential, active Gateway or real-GUI evidence was deleted.

The older `f7e3347` verified bundle came from an already-prepared installation.
Its 19 passing packaged tests remain valid for that artifact; they did not cover
this fresh-install order defect.

## Corrected boundary

`scripts/prepare-openclaw-runtime.ps1` verifies the pinned installed package
identity and runs its **public `gateway --help`** before migration-provider
relocation and runtime slimming. OpenClaw owns its initialization; the App does
not copy, patch or guess lifecycle markers or internal dist chunks.

The helper uses its own hidden child process, a newly created state/CWD directory,
and a cleared environment with only the required Windows execution variables.
No API key, Gateway token, Codex source auth, NODE_OPTIONS or unrelated secret is
inherited. The user's HOME and live OpenClaw/Codex state are not changed. Local
stdout/stderr plus hashes and a public-command receipt are retained under ignored
`data/tmp`; nonzero exit, wrong help, missing entry/version mismatch or timeout
stops staging. Timeout termination targets only the helper's newly owned tree.

Two Windows host details were caught during implementation: `Get-Command node`
can return multiple applications, so only the first selected executable is used;
the Windows PowerShell module environment may not expose `Get-FileHash`, so receipt
hashing uses .NET SHA-256 directly. There is no fallback to an unverified package.

## Evidence

- Seven helper/boundary tests exercise credential/state isolation, multiple Node
  candidates, wrong version, missing entry, nonzero exit and wrong help.
- Helper plus real slim staging/workspace tests: **9 passed in 123.09 s**.
- The initial direct-model full suite retained its real staging failure:
  1,420 passed, six explicit skips, one failure.
- A new locked `npm ci --ignore-scripts` followed immediately by the same helper
  and real staging/workspace checks also passes: **9 passed in 117.93 s**.
  Complete App regression then passes **1,429 tests / six explicit skips in
  186.95 s** in the separate direct-model worktree. Candidate preparation fix
  `a7d8fb4` also passes CI 34496955373 and its associated secret scans.

This changes install/build preparation only, not image prompts, ROI, diagnosis,
model selection or the OpenClaw-owned inference loop. It is not real candidate
OAuth/model/clinical acceptance or binary release approval.
