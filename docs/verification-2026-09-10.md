# Desktop evidence update — 2026-09-10

This supplements, not rewrites, the [September 2 record](verification-2026-09-02.md).
The active requested target is **GPT-6 Astra low only**. Luna high comparison
was dropped. No complete Astra cohort, new release, or clinical-accuracy pass
is claimed here.

## Real software path

Windows viewer → manual App Analyze → configured ROI → OpenClaw public Gateway
→ native ChatGPT/Codex subscription transport → App overlay and Export.
The saved preset is `openai-codex-astra`; runtime diagnostics observed
`gpt-6-astra`, `thinking=low`, `reasoningEffort=low`, and HTTP 200.
The [official model page](https://developers.openai.com/api/docs/models/gpt-6-astra)
documents the exact model. OAuth does not transfer image-agent ownership to Codex.

| Calibration export (same case) | Time | Outcome |
| --- | ---: | --- |
| `desktop-20260910-094636-035106` | 179.252 s | First crop completed; later crop and final reconciliation timed out; incomplete |
| `desktop-20260910-095926-407907` | 165.043 s | Final reconciliation completed after compact-output change; later crop timed out; review required |

A second distinct case was opened through Ctrl+O and exported as
`desktop-20260910-102218-658881`: **140.481 s**, coarse + two refinements + final
completed, two unresolved findings. The original ROI and actual SummaryPanel
were visually inspected; all four recorded turns have public usage rows and
runtime observations of Astra low. Clinical scoring remains pending. The next
pilot case `meeti_46169897` hit the 60 s initial-response deadline and was
retained as a technical failure, not silently counted as completed.

The second result's original ROI is 1499 × 1079 physical pixels on a 150% DPI
display. Export includes source, structured findings, bound bbox audit, review
rendering, and actual app-owned widget renderings with geometry/DPR receipts.
Widget rendering does not disable Windows capture exclusion or copy unrelated
desktop/background pixels. Subpixel projection drift alone does not establish
correct anatomical localization. No cohort speed improvement is inferred from
these two attempts.

## Defects discovered and addressed

- Native Codex rotated OAuth while the imported OpenClaw profile remained stale.
  Import now binds an OAuth-only source snapshot to a secret-free SHA-256
  receipt; a changed source is reimported through the pinned public migration
  provider. A profile listing alone is not credential freshness evidence.
- Broad viewer-title matching can select an editor window. Current real-run
  configuration is manual and restricted to `DICOM Harness Viewer`; general
  product viewer-selection hardening remains open.
- Narrative negations were misread by a local ventricular-run guard. The guard
  is now limited to explicitly asserted finding labels, not free-text
  differential prose. Multi-event crops retain all distinct event times and
  intervening beats.
- The next crop now needs a budget informed by the preceding crop's observed
  duration. Skipped work remains explicit; no skipped axis is declared normal.
- Export `desktop-20260910-100742-309046` contained an obstructing launcher
  console. Astra recognized the occlusion; this is a capture failure, not an
  accepted ECG case. Source launch now uses `pythonw`. A new pre/post analysis
  capture gate rejects changed viewer identity/geometry, out-of-window ROI,
  visible intersecting windows, and unverifiable window state. App-owned and
  transparent windows are not exempt. The real GUI Open-dialog obstruction
  test was blocked before any model request; a foreground editor was likewise
  blocked. Pre/post checks reduce but cannot atomically eliminate compositor
  races. Local change detection is distinct from the transmission gate.
- A model also reported unavailable skill-file access. Tool availability and
  phase-specific inline clinical instructions still need reconciliation; this
  limitation is not hidden from the evidence ledger.

## Usage, historical batch, and CI

Public `openclaw sessions --json` rows are linked to exported session/run IDs.
They are reported snapshots, not a verified lifetime billing ledger. Missing
or aborted-turn usage is unknown, not zero. Subscription usage is not a dollar
charge, and API-equivalent estimates must be labeled separately.

The September 2-3 historical Luna driver recorded **103 attempts: 60 exports,
43 timeouts**. Offline comparison matched every exported source to its intended
frozen-case image (maximum thumbnail MAE 0.39/255); all 60 had Gateway receipts.
Reasoning effort was not established, so these cannot be called Luna-high or
Astra results. The 128-case frozen cohort is still not a completed Astra study.

Local full suite before the final incremental changes: **1243 passed, 4 opt-in
skips**. Subsequent targeted contract/acceptance checks: **302 passed**.
Commit `ca801b7` passed GitHub CI and Secret scan. Its local full suite was
**1288 passed, 4 opt-in skips**. Later changes must earn their own CI result;
mocks and unit tests do not count as real GUI cases.

Website source passed 11 smoke checks and actual Playwright/installed Edge QA
at 1440×1000 and 390×844: identity, content, console, overflow, docs navigation,
mobile menu open/Escape/focus, and screenshots. Browser plugin was unavailable;
QA used an isolated dependency environment, not the packaged App. Public Pages
deployment of this source is still pending.

GitHub secret scanning and push protection are enabled. The one historical
Gateway-token disclosure has an exact documented Gitleaks baseline; it is not
present in active config/environment or current documentation. Git history
has not been rewritten. See [SECURITY.md](../SECURITY.md).

Outstanding release gates: ≥100 distinct real Astra cases with source/model
identity and honest clinical scoring, real partial-lead tests, visual bbox/DPI
review, fresh clean bundle measurement, Pages publication, and release artifacts.
