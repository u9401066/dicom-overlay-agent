# Actual dual-image regional QA — 2026-09-29

Source `c7fd1f83ab52a1d35b0331fc65eaa893a24a21d2`; this is not the previously
accepted575bcdc EXE. One exposed deidentified partial ECG, not a new blind case,
100-case evaluation, clinical approval or controlled accuracy/speed comparison.
The [design](../../architecture/regional-image-context.md) explains the two-image
scope and unchanged safety gates.

## Real desktop flow

A fresh static runtime was copied and all18,771 files hash-verified before any
config/auth writes. Source App17488/launcher6476, Gateway31516, Viewer32620/
launcher29500 used separate `Ctemp/dicom-regional-context-20260929`. The App,
not a standalone analyzer, owned OAuth migration, all analysis and regional
questions. Read-only session/history queries added no inference. Existing sealed
runtimes and pristine package remained unchanged.

The actual Viewer file dialog opened the approved `crop_top_20` source. The same
previously user-selected1494x858 ROI `(33,33)-(1527,891)` was retained; no new ROI
selection or broader desktop capture was claimed. Only the owned Viewer was
made top-most, with unchanged geometry, before analysis. Five scientific stages,
Qt handoff and actual Export completed in131.432s; displayed analysis122.8s.
File-to-visible MAE0.4761069661; visible-to-export MAE0.

- Initial export: `desktop-20260929-094258-337396`.
- Source SHA256: `e6597a7362285428f0a09db45d0ad1f8bcc10ada57ba051980f32ae218ec69d2`.
- Canonical SHA256: `05570d03279550317bb1cf921086c4fdbbc821e0f25bd9ce473ced89be63c42f`.
- Manual Mark `(950,710)` → `(1200,865)` began outside all AI boxes. Maximum
  physical edge error0.5px; same normalized rectangle as the preceding EXE check.
- Manual question plus inline second question completed, then an independent f1
  question at `(166,401)`. Reopening manual history at `(1075,790)` restored the
  exact prior chat-panel pixels without another model turn or outcome event.
- All three outcomes were `no_change`. Original AI findings and canonical bytes
  remained unchanged, with manual annotations separate from report findings.
- Actual file-dialog change to `crop_bottom_20` invalidated the review, blocked
  stale Export and caused zero new model requests.

## What changed in the visible answers

The manual answer explicitly separated crop morphology from surrounding-image
evidence. It used the original ROI's labels to identify the two selected rows as
V5/V6, while retaining the missing paper-speed/gain/calibration limitation. Its
second answer continued that same region, identified which claims depended on
the surrounding ROI and declined unsupported numeric conversion.

The existing AI crop was43x22 source pixels. Its answer distinguished the small
local downward curve from the original ROI's V1 label and surrounding V2/V3
context. It still reported inadequate local resolution, missing calibration and
uncertainty about etiology/new or dynamic change. Low-resolution refinement was
skipped; no report change was applied. These are observed outputs with inspected
App screenshots, not independent expert adjudication of diagnostic accuracy.

The previous crop-only and new dual-image questions were not identical, and model
outputs are stochastic. Do not turn this development comparison into a quantified
quality improvement or compare whole-analysis timings as a controlled speed test.

## Attachment and usage proof

Ten public sessions plus Gateway observations bind to `openai/gpt-6-astra`,
reasoning `medium`: five scientific stages, two manual refine stages and three
structured regional reviews. No new inference was issued for reopening, changing
the image, collecting public evidence or auditing saved files.

Each structured regional trace retains attachment count2 and both PNG hashes.
An offline audit independently recomputed the actual enlarged crop from the
exported original ROI and selected rectangle. It matched public `chat.history`
media order/type/size with the Gateway's retained inbound PNG bytes, not merely
the configured model name or prompt's claim that two images were present.

| Structured question | Retained selected-crop SHA256 | Context |
| --- | --- | --- |
| Manual1 | `3ea17c4eabe97d0f1e539c8e5308e83c713370c99479243566c12da89be167de` | Exact source SHA above |
| Manual2 | `3ea17c4eabe97d0f1e539c8e5308e83c713370c99479243566c12da89be167de` | Exact source SHA above |
| Existing f1 | `ebf359668a29f409f33e73d5277d0853798ce744b78c1153f0d6029113ec6d40` | Exact source SHA above |

All three rendered answers equal the parsed public structured answer strings.
The initial auditor compared an answer containing newlines directly against
escaped JSON text and failed; correcting the auditor to decode JSON established
exact equality. No model answer or retained artifact was altered or regenerated.

The long scientific blind-pass response remains truncated at8,000 characters in
public history: only its exact prefix is remotely matched; complete original App
transport bytes have their separate local hashes. Four other scientific outputs
match full public visible text. Hidden reasoning blocks are excluded. Subscription
session counters are snapshots, not a complete bill or a money-cost assertion.

## Retained evidence and checks

Private runtime above contains `case-000/receipt.json`, four regional exports,
actual UI observations, `invalidation.json`, and
`public-evidence-20260929-094553/receipt.json`. Final reopened export is
`desktop-20260929-094548-370934`; AI-box screenshot is in
`desktop-20260929-094546-228245/chat-panel.png`.

- Offline `regional-audit.json` SHA256:
  `d609217e3a4587677ef82351a529bf0e570cecd54ddcec2cc45791c0b8860650`.
- Usage receipt SHA256:
  `3355b2da0665279c05f4fcfbf362f2d3e81ab4cdf7372cbbdbaa60edebfc0fcb`.
- Focused175pass6.33s; full offscreen2412pass/10skip448.36s. Skips explicitly
  include fresh packaging/native desktop gates; they are not claimed as passed.
- Ruff and targeted mypy pass. Both c7fd1f8 CI runs36549921028/36549912527 and
  both secret scans passed. The preceding343518f CI also completed green.
- Real Quit and owned Viewer close completed normally. App, Gateway, Viewer and
  both launchers were absent, with no listener on18796. Runtime is SEALED; never
  restart it or overwrite the original receipts.

Pending: updated frozen build/acceptance, review-PNG side-column text overflow,
durable conversation restoration, broader scientific clinical evaluation,
external-model integration, current Pages deployment and distribution-license
approval. Adding context increases image input; it does not by itself make the
agent faster or prove safe clinical deployment.
