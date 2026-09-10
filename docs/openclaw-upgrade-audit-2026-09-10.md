# OpenClaw upgrade audit — 2026-09-10

The current candidate is **2026.9.3**, not the September 2 candidate 2026.8.2.
The product remains pinned to **2026.7.1-2** while the real Astra-low GUI cohort
runs. This is a measured adoption audit, not an upgrade or clinical-pass claim.

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

The raw dependency tree contains 35,246 files. Installation used exact
`openclaw@2026.9.3` and `@openclaw/codex@2026.9.3` with lifecycle scripts
disabled for initial inspection. npm ran under the host Node 25.6.1 and emitted
an engine warning; **all candidate CLI/Gateway checks used supported portable
Node 24.18.0**, not that host runtime. A production build must use the supported
Node/npm route and complete the upstream-supported install lifecycle.

Compared with the historical pinned core measurement of 83.43 MiB, candidate
core growth is about **92.25 MiB**. Adding that difference to the historical
368.01 MiB portable bundle is only a risk estimate, not a newly built size.
Subtracting the Codex scope from the raw installation also does not establish
a working slim runtime. A clean staged bundle and actual EXE tests are required.

Candidate dependency lock SHA-256:
`e3daab9858ddaccbbc1c664510eb7c6a5baf3fdf6367dde6850afe6e77bb118b`.

## Concrete upgrade work still required

1. **Template relocation:** the staging script's pinned
   `src/agents/templates/HEARTBEAT.md` does not exist in the candidate. The other
   six checked `docs/reference/templates/` assets remain present. Select the
   candidate's supported template source and verify fresh-workspace startup;
   do not simply skip the missing template check.
2. **OAuth-only migration packaging:** the new migration plugin has a different
   dependency graph and requires its matching host API. The current staging
   script intentionally rejects any identity other than 2026.7.1-1. Validate a
   new exact, minimal migration-only staging recipe and prove it works without
   Codex agent binaries, supervision, or Platform API keys.
3. **Native clinical harness:** validate plugin registration and actual
   `dicom_bbox_validate` tool receipts, image/turn binding, final reconciliation,
   timeout/cancel paths, and absolute audit paths against the new Gateway.
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
