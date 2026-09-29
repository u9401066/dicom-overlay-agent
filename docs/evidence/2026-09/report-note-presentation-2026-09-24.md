# Compact clinical notes and inspectable technical details

September 25 Taipei / September 24 UTC. Isolated source candidate, based on
`648c50b`; not active in the frozen GUI cohort or the preserved 3029dfb EXE.

## Observed problem

The actual case069 summary exported by the running App at
`desktop-20260924-170103-897124` was visually inspected without opening gold.
Repeated bbox-expansion messages and full crop ROI coordinates occupied substantial
space between clinical findings. This is a usability observation, not adjudication
of the case's diagnoses. The ongoing App/source/config/driver remained unchanged.

## Presentation changes

- Report keeps clinical details, severity, confidence, reviewer questions, original
  notes and limitations. It still puts `[Crop-only evidence]` immediately before a
  crop-limited statement; a missing lead in a crop is not recast as missing globally.
- Only the exact known ROI-prefix format and the complete fixed bbox-expansion
  sentence are relocated. Unknown, malformed and mixed clinical/technical prose
  remain visible in Report. No model-based note classification is introduced.
- **標記來源與座標細節 → Process** opens the original technical notes. Entries retain
  their finding ID, matching presentation-priority number, order, duplicate original
  messages and exact coordinate-prefixed text. Text remains selectable and plain,
  not interpreted as HTML. The button supports keyboard and mouse navigation.
- Clearing/replacing a result removes the entry and its old navigation target;
  delayed scrolling cannot dereference a deleted heading.
- Findings, IDs, source boxes, severity, checklist, summary, review flags, raw notes,
  traces and export data are unchanged. This is not a clinical correction or a
  reclassification of a native receipt. No inference, ROI or overlay mapping changes.

## Additional layout defect and render-environment failures

The first new render checks failed at three panel heights with a 39-pixel horizontal
scroll range, while the Windows offscreen font database was empty. Loading the
installed fonts corrected ordinary identifier measurement. An attempted small
minimum-width workaround was **withdrawn**: Qt does not wrap every unbroken token,
so forcing a narrow label could clip a very long identifier. A new regression
preserves necessary horizontal scrolling for those exceptional strings, rather
than treating a hidden scrollbar as proof that all text fits.

A separate regression reproduced a label retaining **480 pixels** after replacing
a long paragraph with `Short note.`. Qt's height-for-width result included the old
minimum height. Measurement now temporarily releases that minimum and applies the
new measured height, with a reentrancy guard. Shorter text/fonts can reclaim space;
longer wrapped text still grows instead of clipping.

## Render validation and limits

28 new tests plus existing panel/interaction coverage pass **74 checks in 2.35 s**.
Coverage includes scope retention, exact relocated originals, unknown-note safety,
entity immutability, stable priority, keyboard/mouse navigation, stale targets,
literal markup, three panel heights, label shrinkage and access to long unbroken
identifiers. The previous full run passed 2,039 tests before that final defensive
adjustment; final-source verification is recorded separately, not inferred from it.

Fresh child processes render the actual Qt widget with **100%, 150% and 200%**
scale factors and verify pixel dimensions, wrapping, complete notes and navigation.
The 150% report/Process and 200% report images were visually inspected after font
loading; primary clinical text and the secondary original-note section are readable.
The synthetic fixture's Luna model label is just fixture text, not a model call or
a change to the actual Astra-medium target.

The initial Windows offscreen images contained missing-font squares and were **not**
credited as visual acceptance. The test process now loads installed Segoe UI,
Microsoft JhengHei and available symbol/emoji fonts when that offscreen database is
empty. Fonts are not copied, packaged or installed; runtime dependencies and the
production font setup are unchanged. CI availability of particular system fonts
is not proof of native locale/font acceptance.

Local synthetic images from the focused run are under
`C:/Users/Ericlab/AppData/Local/Temp/pytest-of-Ericlab/pytest-3400/`:
`test_isolated_scaled_render_pr{0,1,2}/{report,process}.png`. These are ordinary
test-temporary files, not public or durable clinical artifacts.

The six final-source images were also copied, with source/destination SHA-256
equality checked, to the candidate's ignored
`data/tmp/report-note-presentation-20260925/{report,process}-{100,150,200}.png`.
The 150% report hash is
`df08b3ca929b7bbccf753b6cb90f37f3532993d94e86cf6ac3a8b447c6abe6ff`;
the 150% Process hash is
`c15bb3992be43e2beb644f85fabb5d77911e7b541abf43b7f7d5d29b171f0db9`.
These remain synthetic UI artifacts, not patient images or native clinical runs.

Offscreen Qt rendering is **not** a real desktop interaction, a cross-monitor DPI
transition, a new EXE test or a model/clinical acceptance case. Native acceptance
of this candidate remains for after the frozen cohort is complete. The current
source batch was independently verified at **82/120**, with 38 pending and zero
invalid/technical-failure receipts; its gold remains unopened.

Final-source full regression passes **2,040 tests / seven explicit conditional
skips in 204.41 seconds**, under portable Node 24.18. The skips are the candidate's
optional local Node directory, private cohort artifacts, three frozen-package
opt-ins and two native GUI opt-ins. Ruff/format, focused note-helper mypy,
documentation links and staged secret scanning also pass. This does not replace
the still-pending native candidate and cross-display checks.
