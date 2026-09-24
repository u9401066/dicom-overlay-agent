# Component ownership and repository map

The desktop App, neutral image harness and OpenClaw plugin are separate owners.
This map documents the current implementation, including unfinished boundaries;
it is not a claim that full plugin extraction or canonical assembly is complete.

| Location | Owns | Must not own |
| --- | --- | --- |
| `src/dicom_overlay/domain/` | App state, capture/configuration value types, ports | Qt, network or OpenClaw implementations |
| `src/dicom_overlay/application/` | ROI capture workflow, App scheduling, review/canvas use cases, host prompt adapters | A duplicate neutral multipass engine or scientific entity hierarchy |
| `src/dicom_overlay/infrastructure/` | Windows capture, public Gateway client, runtime lifecycle, provider settings, MCP adapters, exports | OpenClaw private SDK imports or broadening the authorized ROI |
| `src/dicom_overlay/presentation/` | Qt controls, draggable overlay, report/checklist/process, ROI and settings dialogs | Clinical truth, invented labels or source evidence |
| `third_party/medical-image-agent-harness/` | Pinned independent repository: scientific models, current multipass engine, lead parsing, schemas and method | Desktop UI, OpenClaw, account credentials, private datasets |
| `openclaw/workspace/plugins/dicom-overlay-agent-harness/` | Runtime plugin registration, bbox receipt tool, optional trusted-waveform ECGFounder tool | Desktop capture or authority to diagnose from tool labels alone |
| `openclaw/workspace/skills/dicom-*-analysis/` | Modality-specific Gateway instructions and output contracts | A second independent scientific implementation |
| `clinical_knowledge/` | Human-editable YAML, clinical references, generated human/agent steps and SQLite index | Model-created clinical rules silently treated as reviewed knowledge |
| `scripts/`, `tests/` | Build/staging/evaluation commands and test evidence | Production medical image fixtures without redistribution/privacy review |
| `site/`, `docs/`, `memory-bank/` | Public introduction, maintained documentation, dated maintenance context respectively | Credentials, PHI or replacing raw evidence with a success narrative |

Paths in the table are repository-relative. The public submodule has its own
license, CI, `AGENTS.md` and medical-image-reading method. Import its classes and
engine directly; do not add forwarding modules or duplicate implementations.
See [direct integration scope](direct-harness-integration.md).

## Runtime and generated files

`openclaw/package.json` and its lockfile pin the runtime. The App uses public
Gateway `connect` / `chat.send`; the plugin uses OpenClaw's public registration
surface. [OpenClaw ownership](../../openclaw/README.md) explains the distinction.
`build/` stages runtime assets; `dist*/` holds frozen packages. Local writable
`openclaw-home/`, provider configuration, session logs and `data/` artifacts are
runtime state, not plugin source. Never commit OAuth/session artifacts or edit
vendored OpenClaw `dist` chunks to shrink the bundle.

The clinical registry's canonical YAML and reviewed source references produce
the documented catalogue and SQLite cache. Generated parity checks must remain
green after source/path changes. Do not hand-edit SQLite to diverge from YAML.

## Remaining extraction work

The App parser still omits canonical observation/evidence-ledger fields. Full
host assembly needs actual model observations plus source/transform/study/workflow
bindings; adding a neutral dataclass or moving a file does not accomplish that.
The neutral engine and App-specific prompt/capture/receipt adapters need a jointly
tested protocol change. Existing results must not receive fabricated observations.

The September 24 documentation move leaves runtime/package paths unchanged. A
future plugin directory move must atomically update discovery, workspace sync,
staging, PyInstaller inclusion, verifier, manifests and tests, then repeat real
Gateway/plugin and desktop checks. General MCP and external-model integration
acceptance remains separate from the working bbox tool.
