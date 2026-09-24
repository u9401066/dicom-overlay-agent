# OpenClaw 2.x decision — 2026-09-02

## Decision

Do **not** upgrade the product/runtime pin from OpenClaw `2026.7.1-2` to
`2026.8.2` yet. `2026.8.2` is a viable candidate, not rejected permanently: an
isolated copy passed the public Gateway contract probe, but portable-size,
OAuth/config migration, state rollback, and full App evidence are incomplete.

The phrase “OpenClaw 2.0” in planning refers to this newer generation; the
audited package version is `2026.8.2`. Release decisions must use the exact
package version, lockfile, and digest rather than a marketing nickname.

## Evidence collected

### Public protocol

The isolated `2026.8.2` runtime successfully exercised the boundary this project
is allowed to depend on:

- Gateway startup in isolated config/state;
- authenticated public `connect` negotiation;
- public `chat.send` with the expected image attachment shape;
- returned event/result flow through the protocol surface.

This is positive Core 3 evidence: the basic public protocol is not the current
blocker. It is not proof that the desktop App, subscription auth migration,
native bbox tool receipt, complete MultiPass workflow, or packaged EXE works on
the new version.

### Size

The tested unpacked OpenClaw core changed as follows:

| Runtime | Core unpacked size |
| --- | ---: |
| Pinned baseline (`2026.7.1-2`) | 83.43 MiB |
| Candidate (`2026.8.2`) | 196.68 MiB |
| Increase | 113.25 MiB |

Adding that delta to the historical 368.01 MiB clean bundle yields at least
481.26 MiB before any other dependency or staging differences. This is an
arithmetic risk estimate, not a built candidate bundle and not a release size.
The candidate must be staged and measured from a clean worktree before adoption.

### Migration and rollback

The subscription route relies on a pinned OAuth-migration-only provider and
native OpenClaw `openai-chatgpt-responses`. The newer runtime changes enough
config/migration surface that the existing staged provider and generated config
cannot be assumed compatible merely because `connect` succeeds.

OpenClaw state is runtime-owned. Starting a newer runtime may migrate its schema;
reusing that directory with the old pin is not a proven rollback. Testing must
therefore clone sanitized state into an isolated directory and preserve a
known-good old-version state path. Product code must not couple to or rewrite
OpenClaw internal tables/files to force compatibility.

## Why the pin stays

Adopting `2026.8.2` now would weaken at least three maintained cores:

- **Core 2:** no complete real viewer+App+Luna+native bbox receipt run exists on
  the candidate.
- **Core 3:** public protocol works, but auth/config/state migration and rollback
  are still unverified; depending on internals to patch them is prohibited.
- **Core 4:** measured unpacked growth is large, while no clean staged/full
  bundle or residue scan exists.

The current pin is therefore `2026.7.1-2`. `MIN_SAFE_OPENCLAW_VERSION` remains a
compatibility floor, not permission to silently install any newer package.

## Adoption gates

Upgrade only after all of the following pass on one frozen candidate commit:

1. Pin exact OpenClaw and migration-provider versions in package manifests and
   lockfiles; never use `latest` in evidence.
2. Install into an isolated clean directory and record package/tree digests,
   file count, license inventory, and unpacked/staged sizes.
3. Validate generated config and subscription OAuth import without retaining
   Codex source auth, Platform API keys, Codex agent runtime, or platform binaries.
4. Prove first-run and existing-state migration in copies; prove the old pin can
   still start from its untouched state and document an explicit rollback path.
5. Run authenticated public `connect`/`chat.send`, protocol receipt, image
   attachment, event-correlation, cancellation, and clean-stop tests.
6. Run the native harness plugin and verify the same canonical absolute bbox
   audit path and Gateway ownership receipt from launcher through client.
7. Run source unit/smoke/integration suites, frozen self-check, Gateway bundle
   smoke, and residue/banned-content/license checks.
8. Run the actual Windows viewer + desktop App + GPT-5.6 Luna subscription path,
   including the first frozen critical case, all eight partial ECG variants, and
   a bounded blinded cohort. Inspect overlay positions and exports on the real
   display rather than accepting headless output alone.
9. Build the complete portable bundle from a clean worktree and compare each
   layer against the established budget. Document any justified budget change.
10. Update docs/site, pass CI, deploy Pages, tag, and publish a GitHub Release
    only after the above evidence is immutable.

## Protected runtime content

Do not offset candidate growth by deleting OpenClaw internal `dist` chunks,
TypeScript, Playwright, provider dependencies, `quickjs-wasi`, or Node without an
upstream-supported staging contract and complete regression proof. Such pruning
would turn an upgrade into an undocumented fork of OpenClaw internals and break
the stable Gateway compatibility strategy.

## Revisit condition

Re-evaluate when the candidate can close all adoption gates, or when a verified
bug/security incompatibility makes the current pin untenable. A newer version
number alone is not sufficient; conversely, once the evidence closes, the
upgrade should be direct because this project is still pre-release and does not
need to preserve an obsolete internal compatibility layer.
