# Frozen scientific desktop and regional QA — 2026-09-29

## Scope and executable identity

Actual Windows EXE acceptance on one already-exposed, deidentified partial ECG.
This is not a blind clinical evaluation or a public binary release. The earlier
120-case baseline remains a clinical failure. No new accuracy claim is made.

- Build source: `575bcdc6db54c98b396b8c8042bd08007b8fcebd`.
- EXE SHA256: `10d35be239888e3f3301969b75e96e18233fc72a9ec01cf6f46ce777dd01c4e9`.
- Source/driver checkout: `a76f385cc0303415e520c4a383e120523626a7ce` (docs follow-up).
- [Package provenance, smoke and size](scientific-package-2026-09-29.md).
- A fresh copy of all18,771 package files was tree-hash verified before launch.
  No old runtime logs, sessions or credentials were copied into the test runtime.
- Real EXE4364, bundled Gateway12476 and owned Viewer20732; launched from the
  parent directory, exercising portable path resolution. Scientific mode remained
  opt-in. Actual Settings inspection confirmed Astra subscription/medium; App
  performed OAuth migration (12.485s) and profile checking (32.508s).

All inference came from real App controls. Helpers used native mouse/UI Automation;
they never invoked a standalone analyzer or sent model requests themselves.
Credentials and raw runtime remain private. No whole-desktop capture was taken.

## First paid attempt failed; second paid attempt succeeded

The Viewer file dialog opened approved `crop_top_20` input SHA256
`8a8da6c8e2eafc621fbd2735181e9430069d296cbf5421a046a6df51d2f668bd`.
Actual ROI selection saved physical `(33,33)-(1527,891)`,1494x858, at150% scale.
File-to-visible mean absolute pixel difference was0.4761069661 (Viewer scaling).

The first attempt completed all five model stages but publication was blocked
by `viewer_roi_obstructed` / `viewer_unverifiable_before_publication`,144.711s.
Its original receipt and all five paid sessions remain retained. A later
read-only z-order check found a Code - Insiders window covering the Viewer;
this is not proof of the exact covering window at the failure instant.

Only the owned Viewer was made top-most, preserving geometry and ROI. A separate
actual Analyze triggered a new five-stage paid attempt, not a free preflight
retry. It completed in144.864s, including Qt handoff and actual Export. All ordered
stages reached human handoff; displayed analysis duration was140.7s (140734ms),
not just the final stage. No controlled inference-speed improvement is claimed.

- Initial export: `desktop-20260929-091052-127944`.
- Visible-to-export pixel difference:0.
- Source SHA256: `e6597a7362285428f0a09db45d0ad1f8bcc10ada57ba051980f32ae218ec69d2`.
- Canonical SHA256: `f5ed00b9527532cc2f7834718da8dd43a639a5620c9566b753df15a9cd3dd89c`.
- Report showed WARNING / incomplete assessment, two findings and seven AI boxes.
  The live model label appropriately remained unverified; separate receipts below
  do not silently rewrite the original UI or result.

## Actual Mark and regional conversation checks

1. Real Mark drag `(950,710)` → `(1200,865)` started outside all seven AI boxes.
   The whole approved ROI accepts marking, not unrestricted desktop pixels.
2. Submitted a manual-region question and a second question through the inline
   follow-up field/Send. Two answers were visible and retained in that thread.
3. Selected existing finding f1 at `(166,401)` through Inspect. Its Regional QA
   dialog produced a separate one-turn answer, not the manual-region history.
   An initial helper lookup used the wrong dialog title and failed locally;
   reading actual UI controls corrected the helper call, without an extra request.
4. Reopened the manual region at `(1075,790)`. Its two-turn history was unchanged;
   chat-panel image SHA matched the preceding manual export exactly. Reopening
   did not add a model session or an interactive-review event.
5. Used the real Viewer file dialog to change to `crop_bottom_20`. The App
   invalidated the old review, blocked stale Export and made no new model request.

The exported manual rectangle is `(0.6134538153,0.7884615385,0.1676706827,0.1818181818)`
in normalized original-ROI coordinates. Maximum physical edge error is0.5px.
All three review outcomes are `no_change`; original AI findings and canonical
scientific bytes remain unchanged. Reviewer annotations are explicitly separate
from verified findings. Final export: `desktop-20260929-091645-421888`.

Windows alpha-zero layered-window pixels explain the original blank-area input
failure. Mark mode already paints an alpha1 input surface only within the ROI;
outside pixels and passive mode stay click-through. Additional real Win32 smoke
now covers forward/reverse drags and clipping beyond bottom-right/top-left ROI
edges:4 passed in4.04s. These are native input tests, not extra model/clinical cases.
Focused overlay, regional conversation/linkage, review contract, coordinate and
documentation regressions:126 passed in1.24s; Ruff and diff whitespace checks pass.

## Usage and offline audit

Read-only public session/history queries plus Gateway runtime observations bind
15 sessions to `openai/gpt-6-astra`, reasoning `medium`: five failed-publication
stages, five successful-publication stages and five regional turns. Each manual
question used refine plus structured review. The46x20px AI crop skipped refine
because source resolution was insufficient, then answered through structured QA.
No inference was issued by the usage collector.

Public history truncates both long blind-pass answers at8,000 characters. Those
two bindings verify only the exact retained prefix; eight other scientific
answers match the complete public visible text. All complete original App
transport artifacts retain their own verified hashes. The three regional answers
match their public structured responses. These checks do not prove clinical
correctness; session counters are not a monetary bill or complete billing ledger.

Private root: `Ctemp/dicom-frozen-scientific-575bcdc-20260929`.
Retained artifacts include both attempt receipts, four regional exports, actual
UI observations, `invalidation.json`, and `public-evidence-20260929-091646/receipt.json`.
The audit checks schema, source fingerprints, artifact hashes, thread separation,
coordinates, unchanged canonical result and both failed/successful paid stages.

- `regional-audit.json` SHA256:
  `68649cb22bb8a20e6b29c35f4bdb5fe2f3e723d93e178d8d3c14a6512454e7b9`.
- Public usage receipt SHA256:
  `5d8f633b7a8ebf96619c8fe1c83ebd1c32cbc2073404d192c1cae01b34901feb`.

Actual Quit and owned Viewer close completed; App, Gateway, Viewer and its launcher
were absent afterward, with no listener on18796. Runtime is sealed; do not restart
it because startup would truncate evidence logs. Pristine package remains separate.
Shutdown retained a two-second WebSocket-close timeout, then detached and stopped
the owned Gateway successfully; the timeout is not presented as a clean close.

## Remaining limits

Regional conversation works, but tiny crops lack surrounding leads/calibration and
cannot support a complete regional diagnosis. Model context is bounded to recent
turns; visible/exported history is retained, not a restart-restorable workspace.
The review PNG's long annotation text still overflows its side column; full text
remains in JSON and the scrollable actual chat. Broader DPI/vendor acceptance,
external classifier integration, new >=100-case scientific clinical evaluation,
Pages refresh and distribution-license approval remain open. Recoverable source
occlusion currently requires a new analysis; safe retained-result republishing
is an unresolved speed/cost opportunity, not an implemented bypass.
