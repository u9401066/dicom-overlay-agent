# Corrected candidate — actual desktop checkpoint, 2026-09-11

This is exposed development validation, **not a new blind clinical benchmark or
release**. The failed 121-case baseline remains sealed and unchanged. The actual
Apps are the clean c3532d7 and corrected 0e55a61 frozen EXEs, with OpenClaw
2026.9.3 and plugin 1.5.9, each run from a separately hash-verified writable
copy of its preserved package.

## Actual EXE, subscription and known-failure case

The previous App was closed through Quit and its owned Gateway shut down normally.
The candidate uses a separate state directory and loopback port 18791. Its real
Settings UI selected `openai-codex-astra`: `gpt-6-astra`, low reasoning,
`openai-chatgpt-responses`. The official pinned migration-provider receipt reports
OAuth ready, temporary migration config removed, Codex agent runtime disabled,
and no Platform API key. Public Gateway negotiation records protocol 4 and server
2026.9.3; four stage sessions bind to actual Astra-low runtime and public usage.
Fast mode is requested but priority service is not observed; no service-tier or
monetary-cost claim follows.

One previously failed bbox case was opened using the Viewer's real QFileDialog,
then analyzed/exported through App buttons. Its captured source SHA-256 equals
the old export exactly:
`8cf91e95aa001000c170230b1d9f6a37d39172f6a7e1010ba5b1b116e5ef89c3`.

| Observation | Old baseline attempt | Candidate attempt |
| --- | --- | --- |
| Analysis elapsed | 175.805 s | 113.735 s |
| Finalization | Receipt mismatch, retry, timeout | Completed in 40.400 s |
| Recorded candidate model stages | Not a new control | Four completed, no parse retries |
| Finalization native receipt | Rejected by exact draft comparison | Seven accepted boxes, exact draft geometry retained |

This single unrandomized pair does not isolate all code/runtime changes or prove
a general speedup. The candidate result still has four low-confidence findings,
is incomplete and requires review; no diagnostic-accuracy improvement is claimed.
Candidate result SHA-256:
`7fafab3e572351ce45cc93ce4e26699110ab33f9331a2a59976ca0dbef54870b`.

The actual summary-widget export was visually inspected at 150% DPI. Eight review
reasons are collapsed into an expandable control, with findings visible below.
The seven logged bbox projections have maximum edge drift 0.619 physical pixels;
this is projection consistency, not independently adjudicated clinical localization.
Widget exports preserve capture exclusion and do not read the desktop background.

## Real resize guard and retained failures

The real Viewer was resized from 1522×1136 to 1200×850, followed by the actual
Analyze button. The old proportional ROI would enter the fixed-height titlebar.
The candidate fails closed with `roi_outside_viewer_client` before any analysis
request; the original window dimensions are restored and ROI is not enlarged.
This checks the client-boundary guard, not inference on an incomplete ECG.

Retained engineering events:

- Saving the provider while the first Gateway startup was still converging
  caused upstream startup to refuse readiness because its config changed. The
  UI already requests a restart after provider saving; Quit/relaunch completed
  the correct subscription import. Better startup/settings coordination remains
  a product edge to address, not a silently discarded success.
- An initial GUI file-open attempt failed before any inference. `AppActivate`
  alone did not deliver Ctrl+O; an actual Viewer click plus verified foreground
  ownership opened the real dialog. The failed driver receipt remains separate.
- The first resize guard itself succeeded and restored the window, but its local
  evidence script failed when formatting a PowerShell subtraction inside an
  array. Parenthesizing the values and rerunning produced a complete receipt;
  both guard attempts sent zero analysis requests.

## Deliberate eight-row crop: recognition present, contract failed

Through the actual Set ROI dialog, a new selection was dragged wholly inside the
original safe image. The logged physical capture is `(36,81,1484,708)`; pixel
comparison with that subrectangle of the actual Viewer is exact (MAE 0.0). It
excludes V3–V6 and clips upper deflections/labels. No full-desktop image is sent.

The four Astra-low stages complete in 91.436 s without parse retries. The report
explicitly describes the partial ECG and absent V3–V6, remains incomplete, and
does not reconstruct a full 12-row layout. However, its eight lead entries use
`lead` instead of required `name`, omit `label_visible`, and use unsupported
`partial_stacked`. Thus **the structured partial-input contract fails**: zero
valid lead entries reach crop mapping, and the final validator removes references
to leads it cannot bind. Recognition in prose is not successful structured grounding.
Raw result SHA-256: `0f3f3f34718fdd4c6bf7a34e45002568129121f6a12c85fe4594742e78a648b3`.
ROI image SHA-256: `00294b0b9f695a2aa80de35870be0a75ba5f5e062af37ec3562972738ff51270`.

The local driver initially expected height 709. The saved reference height 1137
versus actual Viewer height 1136 produces a conservative one-pixel contraction.
The failed expectation receipt is retained; a separate read-only recovery verifies
the exact 708-pixel logged ROI with no new inference or source-result mutation.

The correction under development adds the existing schema's exact partial-layout
shape to the actual compact triage prompt, prioritizing required fields over its
character target. The prior full skill already contained the correct shape; the
compact prompt omitted those field names. This is a format instruction, not a
new clinical threshold, model switch or compatibility alias. The parser now
requires explicit boolean `label_visible=true` to accept a lead; absent/string/
numeric values cannot imply visibility. Row normalization cannot manufacture a
missing visibility field, even with periodicity evidence; the separately declared
compact `lead_order` path is retained. Existing valid synthetic fixtures now
explicitly supply the already-required visibility field. The new shape, missing
lead and visibility regressions plus related suites pass **224 checks**; Ruff
passes. These source changes are not in the preserved c3532d7 EXE yet.

The [medical-image-reading method](https://github.com/u9401066/medical-image-agent-harness/blob/efeff23d8dc07c74e90cb9900cad5bdb45875c4b/.agents/skills/medical-image-reading/SKILL.md)
keeps this failed raw prediction immutable and missing leads non-negative.
The prompt audit also follows the official recommendation to inspect
[Astra's loaded instructions](https://developers.openai.com/api/docs/guides/latest-model#prompting-best-practices);
neither source establishes this candidate's clinical accuracy.

## Corrected 0e55a61 actual EXE rerun

The actual Settings UI selects Astra subscription, then Quit/relaunch imports
OAuth through the pinned provider. On loopback port 18792, Gateway protocol 4
and server 2026.9.3 are verified. Codex agent runtime and Platform key remain
disabled. The real Viewer file dialog, Analyze and Export controls repeat the
same eight-row ROI; its source hash above matches the failed c3532d7 capture
exactly, with Viewer-subrectangle MAE 0.0.

The analysis completes in **96.990 s** (103.286 s including GUI/export), with
four bound Astra-low/public-usage sessions, all completed with zero parse retries.
Individual model turns take 26.776, 16.038, 17.307 and 36.633 s.
The result uses schema-valid `format=partial` and eight canonical `name` /
boolean `label_visible` entries. The parser accepts eight declarations, zero
malformed entries, and retains V3–V6 as missing. Both refinement crops now have
nonempty mapped lead inventories, containing only declared original-ROI leads.
A separate read-only audit validates these properties without another model
request or result mutation. Result SHA-256:
`462234165629ebece90e013c14b6c5223004b69f0efe75db1e793d2b0febac07`.

This passes the single-case **layout-schema and crop-mapping regression**, not
clinical or label-visibility adjudication. Upper labels/deflections are clipped;
the model's `label_visible=true` is a declaration, not an independent proof that
each label is readable. A hidden-label challenge remains necessary. The result
has three low-confidence findings, is incomplete and requires review. Source/
review and actual App-owned summary renders were visually inspected at 150% DPI;
capture exclusion remained enabled. The fixed panel title still says “12-Lead
EKG Analysis” for partial input: a remaining presentation edge, not a completeness
claim. Five projected boxes have maximum edge drift 0.744 physical pixels, not
clinical localization accuracy. There is no general speedup claim (this partial
run is slower than c3532d7's failed-contract run).

## Fully hidden lead labels — actual same-EXE challenge

The real Set ROI dialog contracts the previous safe capture horizontally to
`(150,81,1370,708)`, removing all left-side lead labels without enlarging the ROI.
The actual Viewer file dialog, Analyze and Export workflow completes in 85.872 s
(92.356 s GUI wall); four Astra-low sessions bind to public usage with no parse
retries. An idle Gateway connection breaks before request acceptance, then the
App reconnects and replays once with the same idempotency key. This transport
event remains recorded rather than counted as another independent case.

All eight rows declare `name=unknown`, `label_visible=false`, with partial
layout. No named leads are accepted; both crop lead maps and all final finding
region lists are empty. The report describes unlabeled waveform rows and
image-grounded possibilities without inventing lead identities. It remains
incomplete/review-required with three findings. Source and review render were
visually inspected: all labels are absent. This passes one exposed
**hidden-label non-fabrication challenge**, not clinical accuracy or localization;
one retained box is explicitly marked low-signal by the exported audit.

Source SHA-256:
`cce82cb830055010eed9296e5c4cb7146e9b46ac2658c2e4ccf7603adc6f8e94`.
Result SHA-256:
`f3a60f45ea7be00913d8d2a050be581bf3d66acc1a4477ff8b52fa3233379ecd`.
The validator's combined “malformed or hidden” warning still groups valid hidden
declarations with malformed ones, a remaining presentation/diagnostic distinction.

Further partial-ECG variants and broader hidden-label grounding,
display-scale transitions, canvas/layer interactions and broader candidate model
validation remain separate gates. Binary distribution licensing and specialist
adjudication of the failed clinical baseline stay open.
