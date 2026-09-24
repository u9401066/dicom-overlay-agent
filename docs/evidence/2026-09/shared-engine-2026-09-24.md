# Shared engine checkpoint — 2026-09-24

This is a development-source checkpoint, not clinical acceptance or a binary
release. Public harness PR #2 contains the current multi-pass engine extracted from
App source `e1ef13d87d90890bdba5d78918d2509ee01bc410`. The pinned public source is
`3c7645ec2c41364e8ae521416ae758ddb81ea7c3`.

## Direct ownership and deliberate boundaries

- Models, current bounded multi-pass engine, strict ECG layout parser, and analyzer
  lifecycle port have one public owner. All App consumers use direct imports.
  Deleted App files are not replaced with aliases or forwarding modules.
- The desktop and evaluation constructors explicitly inject App checklist axes
  and existing OpenClaw trace identities. This avoids silently replacing the App's
  10 CXR axes with the public profile's 11, or adding CT axes during a refactor.
- The source crop containment, critical-first policy, timeout budgets, original-ROI
  final dispositions and locked geometry remain intact. No new model calls,
  upstream SDK dependency, capture widening or runtime dependency is introduced.
- Public evidence protections remain: final output cannot replace host provenance,
  study scope, observations, evidence or workflow events. Reworded summary and
  revised claim semantics cannot inherit stale references. Host-bound human review
  cannot be silently cleared. These are explicit draft safety improvements, not a
  completed host evidence assembler or automatic promotion to a canonical result.

## Regression collection and source identity

Inspection found 38 parametrized cases nested inside another test function in the
existing App suite. They had not been collected by pytest. They now run in the
public suite and App environment; both have an AST guard against nested/shadowed
test definitions. Two stale expectations were corrected to the existing runtime:
a bounded candidate crop cannot confirm an unlocalized whole-source hypothesis,
and workflow timeout requires incomplete/review flags rather than invented clinical
severity. No clinical thresholds were relaxed to make these assertions pass.

The clinical registry initially failed six checks because its inventory referenced
the removed App path. Updating that mapping and mechanically regenerating views
fixes all 21 registry/SQLite checks. The seven clinical rules are unchanged; the
source-document digest is now
`0d35360aa941f0fc4a532c6fc204fee32fae7fdab866376c4ac82925a1e612c1`.

Parent Git inventories do not recurse into submodules. New evaluation fingerprints
therefore separately record the public commit, tracked diff and actual scoped
source contents, including dirty and untracked files. Missing/non-repository public
sources fail closed. Old sealed results and fingerprints are not rewritten.

The offline packaged-runtime smoke now actually runs coarse -> bounded crop ->
refine -> final through the public engine and checks unchanged coordinates. This
uses synthetic pixels and scripted responses, not a model or clinical case.

## Evidence and outstanding acceptance

Public verification: 445 synthetic tests pass, coverage 87.06%; Ruff, public import
boundary, canonical skill integrity and built wheel/sdist checks pass. The staged
secret scans detect no secrets. Full App regression passes **1,582 checks / five
explicit skips in 265.75 seconds**. Skips cover private frozen cohort artifacts,
opt-in frozen/Gateway smoke and rendered Windows capture; they are not passing
results. Final enum/public-pin targeted regression passes 297 / three explicit
frozen-bundle opt-in skips. Public PR #2 merged as
`13ef25ffb60ae0b343eed3744cca74b5b190bfe5` after both final CI runs passed; the App
pins its tested source ancestor. App commit
`128117b661c7d5a0c9a0d04ca09cf2cdac542a38` passes push CI 35974012472,
PR CI 35974017667 and both secret scans (35974012731 / 35974018025).
Prior 0e55a61/c3532d7 binary evidence must not be attributed to this engine.

## Fresh frozen checkpoint

A separately preserved, clean `128117b` build passes the full static/runtime
verifier, 90-file native dependency-source audit and **20 actual frozen packaging
smoke checks in 106.17 seconds**. This includes the newly wired public-engine
crop/refinement/finalization smoke, with scripted responses rather than a model.
The source and every one of the 18,771 files in the separate writable live copy
were hash-verified before startup; no auth/state was added to the preserved build.

| Component | Bytes | MiB |
| --- | ---: | ---: |
| Launcher | 4,910,311 | 4.68 |
| App / Python / Qt | 57,068,940 | 54.43 |
| OpenClaw | 272,805,439 | 260.17 |
| Portable Node | 23,515,464 | 22.43 |
| Whole folder | 353,389,843 | 337.02 |

The launcher is part of the App layer, not an additional subtotal. The folder
increase from 0e55a61 is 7,563 bytes. Node remains v24.18.0 and OpenClaw 2026.9.3.
No heavy dependency was added, upstream internal chunks were not pruned, and
DLLs protected by CFG remain uncompressed.

This build's separate Deflate-9 ZIP is **148,430,073 bytes (141.55 MiB)**, SHA-256
`d82484dc26476eea091d2cb6eb7166b85b1d8897b5e75078ba81c06cbcb325a6`.
All 18,771 decompressed entries match the original hashes; all 53 UPX-bearing
native files pass `upx -t`; the original directory is unchanged. Compression
took 21.702 s. The ZIP is local and unpublished, without live auth/state.

- Source-tree SHA-256: `b0014fee778ec6753db13da4c7f022984c804c39907c968ac5e6d5684aedf968`.
- Launcher SHA-256: `5cd11b6cff074cbfccd9f73d4c3f73776cbc97e51aa8ace6e0cffeb30e1d917d`.
- Payload-tree SHA-256: `8ac7c44df09db69fedfc7106f27212e6a7731a2ee01f92406ed3a16c5ff5361b`.

The verifier report and copy receipt remain outside the build. This is local
development evidence, not a public binary release or clinical acceptance.

## Actual desktop / Astra-low checkpoint

The new EXE was launched from its verified writable copy, with manual triggering.
Its actual Settings dialog selected Astra; the App was gracefully closed and
restarted to apply that provider. The official pinned OAuth-only migration
completed successfully: OpenClaw owns inference, Codex agent runtime is disabled,
and no Platform API key is retained. Gateway protocol 4 was negotiated and
retained in the result. This is separate from the offline packaging smoke.

One **already exposed development case** was opened through the real Viewer
QFileDialog, then the real App's Analyze and Export buttons. The previously
authorized narrow ROI `(150,81,1370,708)` deliberately contains eight rows with
their labels hidden. The exported source exactly matches the visible subrectangle
(pixel comparison MAE 0.0); no full-desktop image was sent. Source SHA-256 is
`cce82cb830055010eed9296e5c4cb7146e9b46ac2658c2e4ccf7603adc6f8e94`, the same input
as the historical hidden-label probe, not a new blind case.

- Export: `desktop-20260924-083531-047249`; result SHA-256:
  `12c9c9234c7fa75371345126b2f703d8f07ac952d15a93856b82f65384345b04`.
- Analysis: **90.980 s**; real open/analyze/export workflow: **98.577 s**.
  Four coarse/refine/refine/final sessions, zero parse retries; all four bound
  public session and runtime observations verify `gpt-6-astra`, low reasoning.
  Read-only usage collection made no extra model request and changed no result.
  Public token snapshots are not a monetary charge or a full billing ledger.
- All eight declared rows remain `unknown` / `label_visible=false`; no named
  finding regions or crop-lead map are invented. Finalization preserves the
  receipt-bound box despite small model decimal drift. One hypothesis is
  retracted during refinement; two low-confidence findings remain.
- Result is **incomplete, review_required=true**, not clinically accepted.
  The single rendered finding box has 0.7041 px coordinate back-projection drift,
  which is a mapping check, not clinical IoU. The export's independent pixel
  heuristic still marks it LOW-SIGNAL; anatomical box precision is not closed.
- Source, summary widget capture and rendered review were visually inspected.
  The App's capture-protected window returns a black external screenshot; its
  real Export widget capture provides the visible result, without disabling
  capture protection. It still incorrectly says `12-Lead EKG Analysis`, and the
  validator still combines valid hidden rows with malformed entries in a warning.
  These presentation/diagnostic edges remain open at this frozen checkpoint.

This single replay does not demonstrate improved speed or accuracy over the
failed primary cohort, and does not validate other vendors or legacy printouts.
Raw result, usage, driver snapshot, UI helper snapshot and transfer receipts are
retained privately; no clinical image or OAuth artifact is committed.

## Post-checkpoint title correction

The source UI now derives the ECG heading from the current inventory instead of
unconditionally using the modality capability label. Explicit partial captures
say `Partial EKG Analysis`; unknown, missing, duplicate, malformed or hidden-label
inventories say `EKG Analysis`. Only a complete valid visible inventory retains
the profile's 12-lead title. An explicitly partial format wins over a contradictory
12-name list. Other modalities retain their profile title. This does not change
model prompts, findings, evidence, crop geometry, completeness or review policy.

Eleven new title cases cover those boundaries and transitions; 73 targeted
presentation/geometry/profile/test-collection checks pass. Full App regression
passes **1,593 / five explicit skips in 218.15 s**; Ruff passes. The opt-in native
Windows capture-exclusion test is then run separately and passes (0.46 s), using
only its bounded test rectangle inside the previously authorized viewer ROI, not
a full-desktop capture. The owned App is paused then returned to manual monitoring;
no inference is triggered. This does not turn the remaining frozen/private-artifact
skips into passes for the new source. A separate **real
Windows Qt presentation replay** of the immutable desktop export was shown and
captured, then visually verified: the heading is `Partial EKG Analysis`. The
replay made zero model requests and preserved the original result bytes. This is
UI verification, not a new clinical interpretation or a rebuilt 128117b EXE.
The combined malformed-or-hidden diagnostic remains unresolved.

## Remaining gates

The following remain separate, unclosed gates:

- Broader EXE/App/Gateway/Astra-low, ROI/DPI mapping, overlay layers and canvas
  acceptance after direct engine wiring. The single real partial/hidden replay
  above does not close these groups.
- Full independent harness/host assembly/plugin and external-tool evidence binding.
  Importing the public model does not populate the canonical observation ledger.
- Clinical improvement against adjudicated references, including urgent misses.
  The failed sealed 121-case baseline remains failed; exposed reruns are not a new
  blind cohort, and synthetic regression counts are not patient/case counts.
- ECG generalization: full/partial and hidden-label input, alternative 3x4/6x2/row
  layouts, non-dataset vendor styles, and genuine de-identified legacy-device
  printouts. Track these groups separately with image-rights/source provenance,
  visible-label inventory and assessability. Rotation, faded grids or missing
  calibration must not be converted to invented leads or measurements. Synthetic
  style variants can check plumbing but cannot establish legacy-device accuracy.
- Recheck the current OpenClaw release against the public Gateway/plugin contract.
  The [official latest release](https://github.com/openclaw/openclaw/releases/tag/v2026.9.6)
  checked on September 24 is 2026.9.6 (published September 23, 23:21 UTC), not
  this candidate's 2026.9.3. Its macOS app warning does not establish a Windows
  Gateway failure; neither do release notes alone establish upgrade safety.
  Test Gateway negotiation, image attachments, subscription migration, plugin/MCP,
  dependency security and packaging separately before changing the runtime pin.
- Unresolved PyQt6 distribution-license decision before any public binary release.
