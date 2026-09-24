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
pins its tested source ancestor. Fresh frozen/GUI evidence
is still pending; prior 0e55a61/c3532d7 binary evidence
must not be attributed to this extracted engine.

The following remain separate, unclosed gates:

- Fresh EXE/App/Gateway/Astra-low runs, ROI/DPI mapping, overlay layers and canvas
  interactions after direct engine wiring; current prior processes were absent
  when checked on September 24.
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
- Recheck the current OpenClaw release against the public Gateway/plugin contract;
  the existing candidate pin is 2026.9.3, not a claim of latest as of September 24.
- Fresh size/dependency audit and unresolved PyQt6 distribution-license decision
  before any public binary release.
