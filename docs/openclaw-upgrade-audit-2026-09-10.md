# OpenClaw upgrade audit — 2026-09-10

The current candidate is **2026.9.3**, not the September 2 candidate 2026.8.2.
The isolated candidate branch now pins **2026.9.3**. The real Astra-low GUI
cohort continues unchanged on **2026.7.1-2** in the primary worktree. This is a
measured adoption audit, not a released binary or clinical-pass claim.

## Verified candidate boundary

An isolated installation, disposable state/config, and the existing portable
Node **24.18.0** exercised the real candidate Gateway. No existing auth/state
was copied; a loopback-only fake provider received a synthetic 64×64 PNG.

| Check | Observed result |
| --- | --- |
| Public `connect`, client range 3–4 | `hello-ok`, protocol **4**, server **2026.9.3** |
| Existing `build_openclaw_chat_frame` | `chat.send` accepted with `fastMode: true` |
| `params.attachments[]` | `type` / `mimeType` / base64 `content` accepted |
| Image at local provider | PNG SHA-256 exactly matches the sent synthetic source |
| Correlated event stream | Accepted run ID persists through `chat final` |
| Process ownership | The exact probe-created process was stopped and exited |
| App-generated Astra subscription config | Public `config validate --json` returned valid with no warnings |

The provider was a local HTTP fixture, **not Astra**. There were **zero paid
model requests** in this protocol probe. It does not prove OAuth import, native
bbox-tool execution, cancellation behavior, graceful shutdown, desktop overlay,
clinical inference, or packaged startup. The first disposable config's legacy
`memorySearch` setting was migrated by the candidate; this was not a test of
the user's existing state. The first probe used OpenClaw's default shared
temporary log; subsequent probe configuration explicitly isolates that log too.

The config-only check used the actual `openai-codex-astra` profile generator,
an ephemeral Gateway credential, explicit isolated workspace, and read-only
config mode. It imported no subscription credential and sent no model request.
Config validity is not authentication evidence.

Two further isolated checks now have concrete receipts:

- **Native bbox tool execution:** a local fixture provider invoked the unchanged
  `dicom_bbox_validate` through the candidate Gateway. One valid box was retained,
  one boundary-crossing box was clipped, and an overly broad ECG box was rejected.
  Exact tool-call ID, image digest, per-turn nonce and canonical accepted-box
  digest matched the absolute-path audit. Run
  `53c98061226545b6834ec11d2cb22aa6` completed with correlated final events.
- **OAuth-only migration capability:** a separate candidate installation omitted
  both `@openai/codex` and its platform package/executable. Public
  `migrate plan/apply codex --item auth:openai` successfully imported fabricated,
  non-usable OAuth values; `models auth list --json` reported one `openai` OAuth
  profile. No real credentials were read and no model request was sent. The
  selected OpenClaw model stayed unchanged and the migration plugin was disabled
  afterward. Full `plugins inspect codex` still reports a missing native-runtime
  dependency; **that is not a full-plugin loading pass**. The migration-only
  capability was tested independently and succeeded without a Codex executable.

Both contracts were repeated against the **slim staged** 9.3 runtime, with the
native probe plugin resolved beneath that staged tree rather than the raw
installation. Native run `73d056b102e249a38eef9b5d5c82aa30` passed image/nonce/
tool-call/accepted-box audit checks. A fresh workspace materialized exactly five
templates: AGENTS, BOOTSTRAP, IDENTITY, SOUL and USER. HEARTBEAT is retired;
local tool notes belong in AGENTS. The App explicitly binds its workspace to
the directory where it synchronizes skills/plugins.

The actual App `ensure_openclaw_subscription_auth` helper also passed against
the slim runtime: fabricated OAuth import **8.440 s**, reuse **2.739 s**.
Temporary auth source and plugin activation were removed; Astra selection and
OpenClaw runtime ownership stayed unchanged. Public binary override points to
a missing owned temporary file, preventing optional Codex inventory discovery
from invoking a host-installed Codex runtime. No real auth was accessed.

These tests do not establish real subscription authentication, clinical accuracy,
state rollback, graceful shutdown, or readiness of a packaged candidate EXE.

Private receipts remain under `data/tmp/openclaw-upgrade-research-20260910/`.
Probe run ID: `661ed7803578461eac4f665aa533e378`. No private evaluation images,
credentials, or user session contents are published with this document.

## Package measurements

The official npm archive's SHA-512 integrity was checked against registry
metadata before use. Extracted size agrees exactly with npm's declared
`unpackedSize`: **184,216,899 bytes**, **9,997 files**, **175.683 MiB**.

| Layer | Measured size | Interpretation |
| --- | ---: | --- |
| OpenClaw core 2026.9.3 | 175.683 MiB | Extracted official package, not staged |
| Core `dist` | 162.663 MiB | Retain; do not prune internal chunks |
| Core docs | 12.063 MiB | Some templates are runtime-required |
| Raw candidate dependency installation | 799.055 MiB | Includes full migration-provider dependency closure; not a shippable bundle |
| Raw `@openai` scope | 377.406 MiB | Codex runtime/platform dependencies; must not ship or be enabled for this app |
| Slim staged candidate | 280.62 MiB / 18,533 files | Flat frozen dependency tree; internal `dist` preserved |
| Staged OAuth-only provider | 2.50 MiB | Included in the slim size; five hoisted helpers retained, no Codex executable |
| Slim stage with restored notices | 280.77 MiB / 18,581 files | Retains all 324 published npm notice files and their hash inventory |

An initial candidate EXE build was intentionally stopped after the notice
audit found 47 `.md`/`.txt` notices (72,988 B) omitted by the historical slimming
rule. All source notice files are now preserved byte-for-byte. Node's official
archive checksum is verified, its LICENSE retained, and the Python/bootloader/
runtime notices have a separate manifest. This is a preservation check, not
license clearance; the PyQt distribution decision remains open in
[Third-Party Notices](../THIRD_PARTY_NOTICES.md). No final 9.3 EXE measurement
is claimed by these staging sizes.

The raw dependency tree contains 35,246 files. Installation used exact
`openclaw@2026.9.3` and `@openclaw/codex@2026.9.3` with lifecycle scripts
disabled for initial inspection. npm ran under the host Node 25.6.1 and emitted
an engine warning; **all candidate CLI/Gateway checks used supported portable
Node 24.18.0**, not that host runtime. Subsequently the candidate worktree ran
the full `npm ci` lifecycle under portable Node 24.18.0 successfully. The
installer now puts portable Node on its process-local PATH so lifecycle scripts
do not accidentally use host Node 25. The production install audited 335
packages with zero advisory matches. Final packaging still requires a fresh
stage without probe artifacts and actual EXE checks.

Compared with the historical pinned core measurement of 83.43 MiB, candidate
core growth is about **92.25 MiB**. Adding that difference to the historical
368.01 MiB portable bundle is only a risk estimate, not a newly built size.
Subtracting the Codex scope from the raw installation also does not establish
a working slim runtime. A clean staged bundle and actual EXE tests are required.

Initial research dependency lock SHA-256:
`e3daab9858ddaccbbc1c664510eb7c6a5baf3fdf6367dde6850afe6e77bb118b`.
Candidate repository production lock SHA-256:
`b39410201107a1e4f3d5c2b07fd1d1bf19bdcf79b6959059b94bccf012b2cfd0`.

## Dependency security release gate

On September 10, `npm audit --omit=dev --json`, executed with portable Node
24.18.0, reported **11 affected package entries: 7 high, 4 moderate, 0 critical**
for a fresh install of the pinned lockfile. Each listed version was also found
in the newly staged slim runtime, not merely in a development installation:

| Staged package | Version | npm severity |
| --- | --- | --- |
| `@hono/node-server` | 1.19.14 | moderate |
| `@openclaw/fs-safe` | 0.4.1 | high (transitive) |
| `brace-expansion` | 5.0.7 | high |
| `fast-uri` | 3.1.2 | high |
| `hono` | 4.12.25 | moderate |
| `ip-address` | 10.2.0 | high |
| `openclaw` | 2026.7.1-2 | high (transitive) |
| `protobufjs` | 7.6.3 | moderate |
| `qs` | 6.15.2 | moderate |
| `tar` | 7.5.19 | high |
| `undici` | 8.5.0 | high |

Pinned lock SHA-256:
`2205ca87614d93fc1af901413db164d87e9dfc39baf32ec839524214bde31458`.
The candidate lock identified above reported **zero affected entries** in the
same day's audit. Counts describe npm's advisory matching, not proven App
exploits, independent vulnerability counts, or a guarantee of safety.

Representative public upstream advisories, with important reachability limits:

- [Hono Node adapter advisory](https://github.com/advisories/GHSA-frvp-7c67-39w9):
  affected Windows static serving can bypass prefix-mounted protection through
  an encoded backslash. Access remains within the configured static root;
  this is not an arbitrary filesystem escape.
- [undici cache advisory](https://github.com/advisories/GHSA-4cwx-7wf7-3272):
  malformed private-cache directives can disclose shared cached responses or
  fail parsing **when the affected cache interceptor is used**.
- [node-tar advisory](https://github.com/advisories/GHSA-r292-9mhp-454m):
  crafted long entry paths can exhaust the stack during archive member
  selection. Presence of the package alone does not establish that the image
  interpretation path accepts such archives.

App-specific reachability is not yet established for all advisories. Loopback
Gateway binding, token authentication, and restricted clinical tools remain
required controls, but do not prove these dependency issues unreachable.
**Do not publish the old-pin rebuilt binary as a new release.** Keep it only as
a measured functional/size baseline. Prioritize the exact-version upgrade and
the gates below; do not run `npm audit fix --force`, manually prune internal
`dist` chunks, or override transitive versions without compatibility evidence.
Re-audit the final candidate lock and shipped package inventory before release.

## Concrete upgrade work still required

1. **Published layout changes implemented in candidate:** preserve the flat
   locked dependency tree and five observed fresh-workspace templates. Real
   staged `agents add` and Gateway bootstrap pass; repeat after packaging.
2. **OAuth-only migration staged and App helper checked:** exact matching
   `@openclaw/codex@2026.9.3`, public `auth:openai` selection, disabled supervision/
   catalog/discovery and no Codex binary. Repeat with real subscription auth and
   the packaged App; never substitute a full Codex runtime or Platform key to
   satisfy the full-runtime inspector.
3. **Native clinical harness:** the basic native bbox/image/nonce/digest/absolute
   audit contract now passes. Final reconciliation, timeout/cancel paths and
   real clinical turns still require validation against the new Gateway.
4. **State and rollback:** test migration in explicit copies. Preserve the
   currently working old runtime/state; never use the newer state as an
   assumed backwards-compatible rollback.
5. **Real App and bundle gates:** run actual Viewer → App → Astra low → Export,
   partial ECG and bbox/DPI checks, clean portable build, banned-content scan,
   and layer-by-layer size measurement on a frozen candidate revision.

These are Core 2/3/4 adoption gates. The protocol result supports continuing the
upgrade work; it does not justify replacing the running cohort's fixed runtime.
The clinical target is **GPT-6 Astra low**, superseding the Luna wording in the
historical [September 2 decision](openclaw-2x-decision-2026-09-02.md).

## Primary sources

- [Official 2026.9.3 release](https://github.com/openclaw/openclaw/releases/tag/v2026.9.3)
  — published September 8; exact release and Node requirements checked September 10.
- [Official package metadata](https://registry.npmjs.org/openclaw/2026.9.3)
  — archive integrity, package version, dependencies, and unpacked size.
- [Gateway protocol/versioning](https://docs.openclaw.ai/gateway/protocol/versioning)
  — advertised current protocol 4 and client version range requirements.
- [Public config CLI](https://docs.openclaw.ai/cli/config)
  — read-only validation surface used above.
- [Official installation documentation](https://docs.openclaw.ai/install)
  — supported Node versions and package lifecycle requirements.
- [Public migration CLI](https://docs.openclaw.ai/cli/migrate)
  — exact-item plan/apply capability.
- [OpenAI provider](https://docs.openclaw.ai/providers/openai)
  — explicit OpenClaw agent runtime preserves native ChatGPT OAuth transport.
