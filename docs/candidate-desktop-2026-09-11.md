# Corrected candidate — actual desktop checkpoint, 2026-09-11

This is exposed development validation, **not a new blind clinical benchmark or
release**. The failed 121-case baseline remains sealed and unchanged. The actual
App is the clean c3532d7 frozen EXE, with OpenClaw 2026.9.3 and plugin 1.5.9,
run from a separately hash-verified writable copy of the preserved package.

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

Further partial-ECG variants, a fresh EXE/model rerun of the format correction,
display-scale transitions, canvas/layer interactions and broader candidate model
validation remain separate gates. Binary distribution licensing and specialist
adjudication of the failed clinical baseline stay open.
