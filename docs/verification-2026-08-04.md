# Verification Record - 2026-08-04

This file is the release-facing evidence ledger for the current desktop MVP.
It separates completed execution from blocked experiments so a local JSON file
or a schema-valid response is never mistaken for clinical accuracy evidence.

## Status Matrix

| Surface | Status | Evidence |
| --- | --- | --- |
| Source self-check | passed | Node, OpenClaw, 51 bundled skills, native plugin, rules, writable base |
| Unit + smoke suite | 738 passed, 1 release-only skip | `uv run python -m pytest -q` |
| Full repository Ruff | passed | `scripts/run-ruff-safe.cmd check .` |
| OpenClaw overlay integration | 55 passed | `tests/integration/test_openclaw_overlay.py` |
| Fresh bundle smoke | 2 passed | `RUN_BUNDLE_SMOKE=1`, real frozen EXE self-check |
| Packaged native plugin | loaded | `dicom_bbox_validate` and `ecg_founder_analyze_waveform`, zero diagnostics |
| Interactive review writeback | passed | refine + JSON proposal -> Apply/Dismiss/no-change trace -> JSON/PNG smoke; all low-signal mutations rejected |
| Real Win32/Qt coordinate probe | passed | Win32 window `1222x836`; mss capture `1222x836`; physical display `2560x1600`; Qt frame `1707x1067` |
| ECGFounder paired waveform arm | 1,000/1,000 completed | `data/eval-runs/ecgfounder-meeti-1000-fullscores-20260804` |
| ECGFounder full-score research audit | 23 supported concepts | CV macro BA 0.865; 3-5 diagnosis complete recall 0.479 |
| Existing real MLLM paired pilot | 6/6 per arm, exploratory | Single-pass vs recorded MultiPass Luna run; paired p=1.0 |
| Current guardrail replay | 6/6 derived, no raw mutation | Partial credit 0.596 -> 0.678; safety improved/regressed/unchanged 1/0/5 |
| Current systematic-probe pipeline | passed mock execution gate | 1 EKG, 2/2 original-ROI discovery probes completed and trace-verified; protocol `3083822c...87a0` |
| New three-arm MLLM image comparison | blocked | OpenAI `credit_balance_exhausted` / `insufficient_quota` |
| Clinical accuracy target | not established | Six cases are underpowered; current full three-arm run is unavailable |

## What Runs Per Image

The auditable MultiPass flow is:

1. Capture the configured PHI-safe ROI in physical screen pixels.
2. Record source dimensions and run deterministic local image-assist candidate
   extraction when the image processor supports it.
3. Run the coarse OpenClaw image read with lead/layout inventory and image
   quality gates.
4. Split a bounded crop budget between evidence-backed finding verification and,
   for EKG, layout-derived limb/precordial discovery probes. The latter search
   for omissions even when the coarse pass did not propose a finding.
5. Run refine reads for those crops, map every accepted box back to
   `normalized_original_roi`, and reconcile a final report without silently
   downgrading urgent evidence.
6. Apply input, schema, clinical-consistency, and bbox-calibration guardrails.
7. Project physical bbox edges through the target display's Qt logical frame;
   draw only boxes whose edge round-trip audit passes.
8. Keep a reviewer-safe `analysis_trace` with stages, registered tools, crop
   coordinates, decisions, and provenance. Hidden chain-of-thought is neither
   requested nor stored.
9. A clicked AI box or reviewer-drawn region may start a source-pixel regional
   refine turn followed by a separate structured crop follow-up. Both runtime
   traces are retained. The model cannot return coordinates; a deterministic
   local signal audit and explicit reviewer Apply gate every report writeback.
10. Each image follow-up uses a unique OpenClaw session and records tool events
    only after the response id/run id matches. No-change, blocked, dismissed,
    and applied outcomes all remain in the exported Process trace.

OpenClaw's native plugin always exposes `dicom_bbox_validate`. The conditional
`ecg_founder_analyze_waveform` tool is usable only with an authenticated
loopback sidecar and an app-supplied opaque waveform artifact id. It cannot read
arbitrary paths, cannot treat a PNG as a waveform, and cannot create image
boxes. See [the ECGFounder tool contract](ecgfounder-tool.md).

The desktop does not yet resolve the current viewer study to a trusted waveform
artifact; ECGFounder binding is evaluation-only. Each bound case receives a
random evidence nonce. A case is valid only with exactly one `status=ok` tool
receipt matching that nonce, the artifact digest, the official model revision,
and the pinned 12-lead checkpoint. Transport failures also leave receipts.

## ECGFounder Waveform Run

- Dataset build: 1,000 MEETI images paired to their raw 12-lead waveforms.
- Checkpoint: official `12_lead_ECGFounder.pth`, kept outside git and the app.
- Protocol fingerprint:
  `a7a55cca53031e799b678b43f9a6e4499c54342326e6f9d51facd95bffd7742b`.
- Completed: 1,000 successful results, 0 failed results.
- Observed wall time: 605.847 seconds.
- Recorded inference time: 605,563.211 ms total, 547.202 ms median,
  783.532 ms p95.
- Interpretation boundary: all class scores are explicitly uncalibrated
  supporting evidence. No fixed diagnostic threshold or image bbox is inferred.

The complete 150-score audit has evaluation protocol
`0384ed02442200be8132943cf87210f8b52ac4ca8c9730de3a2237118c5dd40a`.
It maps 33/38 observed concepts and 99.157% of asserted concept instances. The
primary deterministic five-fold estimate covers 23 concepts: macro balanced
accuracy 0.865, sensitivity 0.848, and specificity 0.883 against explicit
normal controls. Holdout top-20 concept recall is 0.837, while complete recall
for 3-5 diagnosis cases is 0.479. This does not meet the 0.75 multi-diagnosis
target and is not comparable to screenshot-agent accuracy.

The run artifacts and checkpoint are intentionally ignored because they are
large external data. Reproduction commands and hashes are in
[ecgfounder-tool.md](ecgfounder-tool.md).

## Exploratory MLLM Evidence

Two real `openai/gpt-5.6-luna` six-case arms from 2026-07-25 use the same
stratified MEETI manifest and source commit:

- Single-pass:
  `data/experiments/meeti-v2-strat6-singlepass-luna-20260725-1530`.
- Recorded MultiPass:
  `data/experiments/meeti-v2-strat6-multipass-luna-20260725-1530`.
- Current scorer digest:
  `06d0e44fa6ea0fdcd9c91920bb94deca9fee80b721f49d01789dc49d7cd4fb6a`.

Current-scored results are:

| Arm | Strict | Partial | Exact severity | Abnormal detection | Urgent concern |
| --- | ---: | ---: | ---: | ---: | ---: |
| Single-pass | 0.333 | 0.583 | 0.500 | 0.667 | 1/2 |
| Recorded MultiPass | 0.333 | 0.596 | 0.500 | 0.833 | 0/2 |
| MultiPass + current guardrail replay | 0.333 | 0.678 | 0.667 | 0.833 | 1/2 |

The replay is explicitly `derived_counterfactual`: it applies the current
`OutputValidator` and cited clinical rules to saved model output, records the
before/after state and implementation hashes, and never modifies raw result
JSON. Relative to recorded MultiPass it improves one case, regresses none, adds
8.3 percentage points of mean partial credit, and raises critical exact and
urgent-concern recall from 0/2 to 1/2. Relative to single-pass it adds 9.5
partial-credit points and improves the normal false-positive rate from 1/2 to
0/2. With only one discordant case, every paired exact p-value is 1.0; this is a
debugging signal, not evidence of statistical significance.

The main corrected case, `meeti_47511997`, retained diagnostic uncertainty but
already reported V2-V4 ST elevation and an unresolved acute-anterior-injury
differential. The current rule raises triage to critical without rewriting it as
a confirmed STEMI, and the scorer credits that uncertainty contract as a
surfaced urgent concern. `meeti_48293149` remains a true image-reading miss.

The 2026-07-25 run predates the current EKG systematic discovery probes. The
new artifact gate rejects it because no `systematic_assist` or completed
`ekg_systematic_*` crop exists. A current in-process mock execution completed
two original-ROI probes (limb and precordial), recorded 3 OpenClaw turns and 2
crops, and passed `ekg_systematic_probe_artifacts`. A real provider rerun is
still required to measure whether this fixes `meeti_48293149`.

## MLLM Comparison Blocker

The planned adequately sized paired comparison remains:

1. Single-pass image baseline.
2. MultiPass image analysis.
3. MultiPass plus ECGFounder waveform evidence.

The current transactional canary is retained under
`data/experiments/luna-multipass-canary-20260804-default-migration-final2`.
It proves the following
without exposing the API key:

- the Settings/runner default selects `openai/gpt-5.6-luna` over the Responses
  API, while other provider profiles remain selectable;
- OpenClaw's parsed model row declares `text+image` with a 1.05M context;
- the Gateway became ready in 26.136 seconds and sent one MEETI image to
  `/v1/responses`;
- the provider transaction then failed with `credit_balance_exhausted` /
  `insufficient_quota`, so the case has an error artifact and no model answer.

On this Windows portable Node build, `openclaw models list` can emit a usable
catalog row and then terminate with a libuv closing-handle assertion. The runner
now records that non-zero exit as a warning only after parsing the exact model
row, and still rejects a missing or text-only model. Static readiness separately
records `provider_transaction_tested=false`; it is never presented as a paid
provider canary.

There is therefore no complete current-protocol three-arm scorecard and no
significant-improvement claim. Once quota is available, all three arms must use
the same case order, labels, scorer digest, and image inputs; arm 3 additionally
receives only the matching waveform artifact id. MultiPass arms must pass
`--require-ekg-systematic-probes`.

## Coordinate Evidence

The previous primary-screen-only path was replaced with a monitor-bound frame:

- Win32 `MonitorFromRect` resolves the display containing the viewer.
- The exact successful `last_capture_rect` is saved by `OverlayAgent`.
- Qt screen selection accounts for primary status, device name, physical size,
  monitor index, and desktop topology.
- Physical edges are mapped to overlay-local logical pixels using independent
  X/Y ratios and display origins, including negative-origin secondary screens.
- AI boxes and static region fallbacks share the same conversion.
- `Severity.INFO` boxes are now drawn for uncertain reviewer questions; only
  normal findings are omitted from the canvas.

Focused coordinate tests cover negative origins, mixed scaling, physical-edge
round-trip, exact capture preservation, display lookup, and uncertainty boxes.
The real local GUI probe also proved that mss returned exactly the Win32 window
dimensions on the current 150% display.

The six-case review export contains six annotated PNGs and eleven model bbox
rows. All 11 passed normalized-to-pixel-to-normalized projection round trips,
none were clamped or low-signal, and the maximum measured edge drift was
0.373 px. Visual inspection of `meeti_47511997.review.png` confirms the three
markers land on the V2, V3, and V4 waveforms rather than blank space.

Interactive regional review now keeps the same coordinate boundary. `ADD`
uses the reviewer-selected original-ROI rectangle; `REVISE` and `RETRACT` bind
to the selected finding id and its existing accepted boxes. A deterministic
gate combines bright-blank detection, edge density, robust dynamic range, and
pixel density and original source resolution; a crop it marks low-signal (or a
missing/failed audit) may still be discussed and exported as a manual region,
but cannot perform `ADD`, `REVISE`, or `RETRACT`. A monotonic chat request id also rejects late
same-image responses, while result revision rejects responses from older images.
Manual-mode image changes invalidate the prior review snapshot immediately, so
old boxes, crops, and exports cannot remain actionable while a new image awaits
analysis. Duplicate finding ids fail validation instead of selecting an
ambiguous writeback target.
The deterministic end-to-end smoke verifies proposal parsing, explicit Apply,
result-revision protection, report provenance, JSON coordinates, and a nonblank
box-border pixel in the annotated PNG. A native Qt snapshot also verified the
Apply/Dismiss controls fit at the production panel width. The inspected
signal-bearing sample placed the box over lead V2 and measured 3.7% ink; its
side panel recorded `Source: interactive_ai_review`.

## Portable Bundle

Fresh artifact:

- Path: `dist/DICOMOverlayAgent/DICOMOverlayAgent.exe`
- SHA-256:
  `3FFE577B3562965E34360BC765811F150BDA594AFA4E5BA7147E8575A4320D48`
- Launcher: 6.91 MiB
- App/Python/Qt layer: 94.59 MiB
- OpenClaw: 181.03 MiB, version `2026.7.1-2`
- Node.js: 88.25 MiB, version `v24.18.0`
- Total: 363.87 MiB, 15,225 files
- Manifest: `dist/DICOMOverlayAgent/bundle-manifest.json`, status `ok`
- Frozen module proof: PyInstaller `PYZ-00.toc` contains
  `dicom_overlay.presentation.screen_selection` and
  `dicom_overlay.infrastructure.overlay_geometry`. Direct PYZ inspection also
  found all four Luna default constants (`openai-luna`, model ref, model id,
  and UI label) in the frozen `openclaw_settings` module.

Bundled surfaces include the executable, config, portable Node, slim pinned
OpenClaw runtime, native harness plugin, EKG/CXR/CT skills, and clinical rules.
The verifier found no banned components. A separate recursive filename scan
also found no `.env*`, Torch, ECGFounder runtime, checkpoint/weight, MEETI,
waveform, SQLite, or sidecar content. The build stage removes npm-package
development environment files and the verifier rejects any such file that
reaches the final bundle.

The pinned OpenClaw dependency audit currently reports 7 moderate and 4 high
transitive vulnerabilities, 0 critical. A force upgrade was not applied because
it can break the runtime compatibility contract; this remains release debt.

## Website QA

The static GitHub Pages source is under `site/` and deploys through
`.github/workflows/pages.yml`. It uses only the repository's synthetic ECG
asset. Playwright verified 1440x900 and 390x844 viewports, image loading,
desktop/mobile overflow, first-viewport continuation, evidence navigation,
mobile menu state, four complete trace stages, and zero console warnings/errors.

## Platform Boundary

This artifact was built and exercised on Windows 11. The current Python 3.13,
PyQt6, Node 24, and current OpenClaw stack does not provide a credible Windows 7
compatibility claim. Windows 10 also requires a separate clean-machine test.
Do not label the current bundle Windows 7 compatible; supporting it would need
a separately pinned legacy runtime architecture and its own security policy.
