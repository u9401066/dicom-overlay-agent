# Direct public-harness integration — development checkpoint

This branch starts a direct dependency migration; it is not a completed extraction
or a new binary release. The active real-GUI cohort and verified `f7e3347` package
remain separate and unchanged.

## One owner for image-reading models

The public [medical-image-agent-harness](https://github.com/u9401066/medical-image-agent-harness)
is pinned as a submodule at `efeff23d8dc07c74e90cb9900cad5bdb45875c4b`.
Application, infrastructure, presentation, scripts and tests now import
`AnalysisResult`, `ChecklistItem`, `Finding`, `Modality`, `RegionRect`, `Severity`
and `UserRegionAnnotation` directly from `medical_image_harness.models`.

Their duplicate definitions are removed from `dicom_overlay.domain.entities`.
There is no local class alias, forwarding function, re-export or fallback import;
old imports fail rather than silently using a compatibility layer. Product-owned
window/display geometry, configuration, lifecycle and overlay edit operations stay
in the App domain. Pure public models do not load GUI, capture, network or App code.

This does **not** swap in the older public multi-pass engine, replace current
OpenClaw prompts, alter the 16-key Gateway draft payload, or send additional images.
The current crop-scope fix, physical-pixel ROI guards, native bbox receipts,
critical-first routing, and final reconciliation remain in the App implementation.
Those behaviors must be migrated with parity evidence before the engine can have
one public owner. Old draft PR #4's compatibility exports are not reused.

## Draft versus canonical evidence contract

The public model has additional source-bound bbox, observation, study and evidence
fields. Importing its class does not invent those fields' provenance. An App draft
without a trusted study manifest, observation/evidence ledger and ordered workflow
events still fails `to_contract_payload()`; current review exports must not be
relabeled as validated canonical clinical contracts.

The host assembler and model-led observation ledger remain implementation work.
They must preserve raw predictions, exact ROI/crop hashes, native receipt bindings,
the user's assessment scope, and incomplete-input limitations. Neither filling
default placeholders nor replaying current guardrails over old results can close
that gate. A model/classifier label alone is not source-coordinate evidence.

## Installation, CI and packaging

Initialize the pinned submodule before installing with `uv`:

```powershell
git submodule update --init --recursive
uv sync --locked --all-extras
uv run pytest tests/unit tests/smoke tests/integration
```

CI and Pages checkout the submodule; Python installation uses the frozen uv source
mapping. There is no implicit PyPI fallback for this dependency. No global Python
packages, model weights or GUI automation are added to the public harness.

The package spec includes the pinned canonical schema and method resources.
Verification requires their files, inventories the public source/resources/license,
and its offline runtime smoke loads the real schema, rejects an empty draft and
checks method availability. Missing resources fail the smoke, not an optional skip.

The existing Pillow/PyYAML/structlog versions are retained. New schema dependencies
are attrs 26.1.0, jsonschema 4.26.0, jsonschema-specifications 2025.9.1,
referencing 0.37.0 and rpds-py 2026.6.3. Their installed non-pyc files total
**1,499,877 bytes (1.43 MiB)** on this Windows environment, including distribution
metadata. This is not the future EXE/ZIP delta. A fresh isolated build, dependency
notice inventory, UPX integrity, actual packaged GUI/model checks and size audit
remain required. The older f7e3347 size/smoke measurements do not cover this branch.

## Current evidence and remaining work

- Direct-model baseline: 1,127 existing unit/selected smoke checks passed, one
  explicit missing portable-Node skip.
- New ownership/boundary plus package-verifier checks: 56 passed.
- Package smoke plus direct-boundary checks after adding the contract-resource
  gate: 32 passed, three explicit frozen-bundle opt-in skips.
- Pinned public harness in its own uv environment: 222 passed; public-boundary,
  Codex/Copilot method-integrity and built wheel/sdist resource checks passed.
  Public PR #1 adds the missing `py.typed` distribution marker only, not a
  model/API/schema or scientific-method change. Both public CI runs passed.
  App mypy checks for entities, region mapping and highlight construction pass;
  this is not a claim that the whole repository passes strict type checking.
  These tests use synthetic fixtures.
- Full App regression initially exposed a fresh-install OpenClaw staging failure;
  1,420 passed / six explicit skips / one failure. It remains a recorded failure,
  not a clinical result or evidence that extraction is complete.
- The lifecycle-order correction passes 9 helper/real-staging checks directly
  after another locked `npm ci --ignore-scripts`; full App regression then passes
  **1,429 checks / six explicit skips (186.95 s)**. See the dated
  [preparation audit](../memory-bank/openclaw-package-preparation-2026-09-10.md).
- Public repository history scan examined 573,122 bytes with no detected secret;
  the new metadata-only patch scan also found none. This is not proof that all
  dependencies or future runtime artifacts are free of sensitive data.

Further stages must move the current scientific engine without behavior drift,
assemble the canonical evidence contract, bind the OpenClaw plugin and external
tools to it, then repeat actual ROI/partial-image/DPI/canvas and model acceptance.
Public scientific-method changes require their own tests and pinned review.
