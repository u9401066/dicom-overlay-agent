# Native partial ECG replay and negated-ST review fix — 2026-09-25

## Actual App evidence, before the rule change

Clean source `93e0c815c6d8c29de2979ec2e853c97dc5cf65b7`, public harness
`f0f486229cd057c291dd2a66f036f1ce796a42b6`, Windows 2560×1600 at 150% DPI.
The existing answer-free/de-identified partial-v2 corpus contains eight variants
of **one** source, not eight patients or eight vendor formats. No diagnostic gold
was supplied. Input labels were visually inventoried separately, not sent to the
model. Model requests started only through the actual App Analyze control.

The actual file dialog opened each PNG. Viewer-relative ROI changes were confirmed
through the native ROI dialog. No capture widened outside the owned image Viewer.
Six variants reached Analyze → OpenClaw → displayed result → actual Export; two
were blocked before inference. All six source exports exactly match their visible
ROI pixels (RGB MAE 0). File-to-visible MAE was 0.437–0.476 after accounting for
Qt display scaling and the explicitly selected crop. App/plugin/engine source
fingerprints stayed unchanged throughout. There was no direct analyzer call.

| Variant | Native outcome | Visible labels declared | Analysis seconds | Verified stages |
| --- | --- | ---: | ---: | ---: |
| Top 20% removed | Exported | 10 | 92.567 | 4 |
| Bottom 20% removed | Exported | 9; cut-off bottom row unknown | 74.366 | 4 |
| Left 20% removed | Exported | 0; twelve unknown traces | 60.099 | 4 |
| Right 20% removed | Exported | 12; all labels actually survive | 92.040 | 4 |
| Central 50% band | Exported | 6 | 66.172 | 4 |
| Labels masked | Exported | 0; twelve unknown traces | 46.417 | 3 |
| 60-pixel single band | Analyze disabled before inference | Not assessed by model | — | — |
| 67×48 tiny image | Analyze disabled before inference | Not assessed by model | — | — |

All **23** completed stages bind exact run/session observations to GPT-6 Astra
medium and subscription routing. Public session snapshots are not a monetary
billing ledger. No Platform key or Codex-owned inference runtime was enabled.
Different images and stage counts preclude a controlled speedup claim.

All six exports are incomplete/review-required. Declared visible-label sets match
the manual inventories without restoring hidden labels from row order. In
particular, bottom-crop V4 remains unknown; the right crop legitimately retains
all twelve labels despite shortened time coverage. A twelve-label inventory does
not establish a complete calibrated study. No numeric rate/interval/axis claim
was found in the displayed checklists without calibration.

All six saved summary-panel images were visually inspected; each says
INDETERMINATE / review required. Two exported historical severity values remain
`normal`, but the UI does not present these incomplete studies as NORMAL. The
four marked review exports were also inspected. Bboxes overlap waveform rows,
but this is **not** clinician-verified lesion localization or diagnostic accuracy.
No focal boxes were fabricated for the two unlabeled inputs.

## Failures retained, not silently counted as passes

- Native automatic window discovery excludes width or height ≤100 physical
  pixels. The narrow band renders at 1500×90 and the tiny image at 101×72; both
  show Waiting for viewer / disabled Analyze. This is a discovery/usability gap,
  **not** a model quality-gate pass. No automatic paid retries were made.
- Pre-inference driver errors exposed scaled saved-ROI geometry, a fullscreen Qt
  ROI dialog measuring 2561×1601, and foreground restrictions. Failed attempts
  remain separate. The driver was corrected to use effective scaled ROI and an
  owned-window native drag; App ROI protections were not bypassed.
- The first successful export's post-export usage collection failed. A separate
  read-only collection with a 120-second public CLI timeout recovered its four
  usage bindings; the failed receipt and original result remain unchanged. The
  original exception alone does not prove why collection failed.
- Layout warnings still describe genuinely absent leads as “missing visible
  leads” and unknown rows as “malformed or hidden”. These are misleading wording /
  partial-layout contract issues, not proof that the model invented labels.
- Windows SAPI speech reported a class-not-registered error. Results still
  displayed; voice output did not pass native acceptance.
- Top/bottom exports contained a false-positive ST-elevation review reason even
  though their ST checklist explicitly negated elevation. This is fixed below;
  the captured original outputs are not rewritten.

## Narrow deterministic correction after the frozen replay

The canonical YAML ST consistency rule used substring `contains_any: elevat`.
It contradicted its own documented exclusion for negated text. Rule version
1.0.1 uses the existing `contains_any_non_negated` operator with complete lexical
forms; the example override matches. Positive, uncertain and contrasted mentions
still request review, without escalating severity or manufacturing a diagnosis.
The shared parser, other triage rules and frozen cohort scorer are unchanged.
This is a bounded English-negation regression fix, not a general multilingual
clinical-language parser or a new clinical guideline.

Sixteen new regressions initially gave **7 failed / 9 passed**. After the fix,
clinical rule / registry / SQLite / workflow checks gave **105 passed in 1.34 s**.
Generated Python, human/agent views and rebuilt/verified SQLite share digest
`8194933290c085ab81a1ab97d57154bb17d6d2e5835f2e28a327fe1cce312435`.
The native run above predates this change; it is not post-fix GUI acceptance.

Interaction regressions separately gave **71 passed / one opt-in skip in 0.82 s**.
The skipped test was then explicitly enabled on the native Windows Qt platform:
**one passed in 1.20 s**, using real Win32 mouse input on a bounded test window.
It checks starting a drag with no AI highlights in blank ROI, normalized geometry,
outside-ROI pass-through and passive-mode pass-through. This is a native hit-test
smoke, distinct from the earlier actual App/OpenClaw regional QA evidence.
The existing regional history retains all turns for display/export; model context
is limited to the latest six pairs within 12,000 characters, not unlimited recall.

Full source suite: **2,205 passed / seven explicit skips in 390.01 s**. The native
mouse test is one of the default opt-in skips and passed separately as stated
above; package/capture opt-ins were not silently treated as passes. Ruff/format,
generated-view checks and documentation links passed. The 28.41 KB staged change
passed the redacted secret scan. No dependencies or packaging configuration changed.

## Provenance and remaining work

Private evidence is retained outside Git at
`C:/Users/Ericlab/AppData/Local/Temp/dicom-partial-desktop-20260925/`:
plan, manual visibility review, versioned replay drivers, every attempt receipt,
six actual exports, usage bindings and create-only audit. The audit verifies
source fingerprints, per-export artifacts and exact visible/source pixels.

- Plan SHA-256: `40848f580f95c807457486fae18573f53ca937b1abd69b7f8b38d690fc6eef55`.
- Audit SHA-256: `7b21523e3ac8414680d34122de1b6f03a598efdb7e8d8f62e5fcbabbf6245500`.
- Manual label inventory SHA-256: `29b50f33bbe5fd82c9931c4f63fd8d73138ca8c130365728c92adef9d581a978`.
- Original corpus source SHA-256: `33d5fba35339af28e55ca33261661cfcd0219e9268b5b839d147a488df902181`.

Owned App and Gateway were closed via App Quit; their PIDs and port 18795 listener
were absent afterward. The test Viewer was retained. No original sealed runtime
was restarted. Full clinical accuracy, independent legacy/vendor cases, tiny-input
workflow, post-fix native replay, latest executable and license acceptance remain
open. Existing [manual-marker QA evidence](native-marker-promotion-2026-09-24.md)
remains separate; this batch did not repeat those conversations.
