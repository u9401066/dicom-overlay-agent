# Direct public-harness integration — development checkpoint

This report describes candidate branch `agent/direct-harness-models-20260910`,
not the code currently merged into main. It starts a direct dependency migration;
it is not a completed extraction or a new binary release. The sealed real-GUI
cohort and earlier verified packages remain separate and unchanged.

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

## First direct-model packaged checkpoint

Clean source `7abc36467dabfca3cc8cac6947244dad3b5a5024` now has a separately
preserved local build: static/runtime verifier passes, 90 native dependency
sources are approved, and 20 actual frozen packaging smoke checks pass in
126.76 seconds. Launcher: 4,901,372 bytes (4.67 MiB); App layer: 57,059,847 bytes
(54.42 MiB); full directory: 353,379,972 bytes (337.01 MiB), 18,771 files. The App
increase over f7e3347 is 605,059 bytes (0.58 MiB), within the existing budget.
Source-tree SHA-256 is `487d0c514bc2359d39fb36050d73024ea744dfad9f81211208e6a8afecdf3ce2`;
payload-tree SHA-256 is `315b5495c3f87c07c06ea14fdef1a924a9da4dfc300ac3a295f17152c79a34be`.
The verifier report is outside the bundle. This is not a published release, a
real-model check or clinical acceptance. It contains plugin 1.5.8 and does not
cover the later [bbox producer correction](bbox-receipt-canonicalization.md).

## Corrected-receipt packaged checkpoint

Clean source `c3532d73c9f564a6fa9b6f90a625392b68a2bfb6` includes plugin 1.5.9 and
the shared exact coordinate canonicalizer. Static/runtime verification passes;
20 actual frozen packaging checks pass in 103.22 s. Launcher: 4,902,108 bytes
(4.68 MiB); App: 57,060,583 bytes (54.42 MiB); folder: 353,381,486 bytes
(337.01 MiB), 18,771 files. All 90 native dependency sources are approved.
Source SHA-256: `38d62c0ac15e95d3bba3df89340aad0b16b6eba9485f28ff4d4d8caef500a427`.
Payload SHA-256: `0ea7cf8b1c55652717858d5bb676156d20a6e07efe2bb0801e37c8d39859545b`.
Push CI 34501374911 and PR CI 34501380408, plus both secret scans, pass.
The verified bundle is preserved separately from any writable live-test copy.
This does not close the GUI/OAuth/clinical or distribution-license gates.

The corresponding local Deflate-9 ZIP is 148,419,324 bytes (141.54 MiB), SHA-256
`f07c63a9c4463819a47c1c168c167429f68e565451d14b8881dc23bb24216a9f`.
All 18,771 decompressed entries and the separate live copy match the verified
payload; 53 UPX-bearing native files pass `upx -t` without mutation. The ZIP is
not published and contains no live auth/state or local verifier report.

The separate actual EXE now imports subscription OAuth successfully through the
pinned migration provider, with Codex agent runtime and Platform key disabled.
Settings was selected through the real GUI. One exposed development case
completed all four Astra-low stages under negotiated Gateway protocol 4 /
OpenClaw 2026.9.3. See the [candidate desktop checkpoint](candidate-desktop-2026-09-11.md).

## Partial-format corrected package

Clean source `0e55a61197fadd8eaea97e3fcf5712b6a8afe87c` passes static/runtime
verification and 20 frozen packaging smoke checks (100.62 s), with 90 approved
native sources. Its 18,771 files total 353,382,280 bytes (337.01 MiB): launcher
4,902,902 bytes (4.68 MiB), App layer 57,061,377 bytes (54.42 MiB), OpenClaw
272,805,439 bytes, Node 23,515,464 bytes. This is 794 bytes above c3532d7.
Source SHA-256: `1fe722db0755b6c9a118c511261ba16f9f9f56ab935ef8f38867a5761c1a2414`.
Launcher SHA-256: `4fcf83c79bdf2de1a839b16c6601c56abadc015ed2667c079f0810a37240e179`.
Payload SHA-256: `6ed7bf05c8d2a39d9b0a58de0aa865793148af2642c5b77ca36ce8d2c7a7ef5a`.
Every source/live-copy file hash matches; original package remains unchanged.
Push CI 34505422499 and PR CI 34505426574, and both secret scans, pass.
The corrected actual partial-input run completes in 96.990 s with four
Astra-low sessions and valid lead declarations/crop mapping. It remains incomplete
and is not clinical acceptance. The c3532d7 ZIP/UPX transfer experiment above
must not be relabeled as a 0e55a61 ZIP verification; no binary is published.
