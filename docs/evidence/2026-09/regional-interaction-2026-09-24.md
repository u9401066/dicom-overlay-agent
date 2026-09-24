# Regional interaction checkpoint — September 24, 2026

Development evidence, not a clinical release or complete Canvas acceptance.

## Reproduced defect and correction

In the actual clean `9a27b61` Windows EXE, Mark at an unmarked point inside the
authorized image ROI reached the underlying Viewer. The same operation over an
AI box reached the App. A physical mouse drag from the blank point failed to
create a region. This reproduces the reported interaction defect.

Windows layered windows pass alpha-zero pixels through to underlying windows
([Microsoft documentation](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features)).
Clearing the input-transparent window flag alone was insufficient. Mark mode now
paints a minimally nonzero-alpha input surface over the captured ROI, including
areas without AI findings. Outside the ROI remains transparent; leaving Mark
restores click-through. The capture area and original-image normalization do not
change. Whole-screen overlay coverage does not authorize whole-desktop capture.

An opt-in native Windows test performs real mouse input, checks the resulting
normalized region, and verifies ROI-exterior/passive hit testing. It passed at
the current 150% desktop scale after correcting the fixture's mixed DPI contexts.
Earlier fixture failures are not App acceptance passes. Qt tests also cover
reverse/outward drags, starts outside the ROI, zero-area marks and alpha clearing.
Run the native test alone on an interactive Windows desktop:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:DICOM_RUN_WINDOWS_INPUT_SMOKE = '1'
uv run pytest tests/smoke/test_windows_overlay_hit_testing.py -q
```

This test moves the pointer over its own synthetic windows and restores it. It
does not capture the desktop, load patient data, or invoke inference.

Local default unit/smoke suite: **1,552 passed, six explicit skips** in 194.54 s;
the opt-in native input test was separately run and passed twice. Integration:
**55 passed** in 0.46 s (combined 1,607 ordinary tests). Ruff passes.

## Actual regional QA and remaining gaps

The actual frozen App analyzed the exposed hidden-label case 119 again in
125.559 seconds. One refinement exhausted its budget; that failure remains in
the trace. Existing AI-region Inspect opened the actual question dialog. Two
questions were submitted through that dialog. The second answer was observed in
the actual ChatPanel: it could not favor ectopy versus artifact without adjacent
beats and synchronized traces. No report change was proposed. The first answer
expired before observation and is not claimed as visually verified.

Private artifacts remain outside Git:

- `data/tmp/regional-ui-existing2.json`: actual accessibility read of question
  and answer; the observer makes zero model requests.
- Frozen exports `desktop-20260924-094330-218022` (analysis) and
  `desktop-20260924-094907-988421` (after regional QA), beneath the isolated
  `data/tmp/live-medium-9a27b61/DICOMOverlayAgent/data/exports/` directory.
- Each export's usage supplement binds the three original analysis-stage turns
  to Astra medium. Those supplements do **not** establish separate regional-QA
  usage binding, nor a complete billing ledger.

The patched **source App**, using the isolated verified runtime on port 18795,
was launched and driven through real QFileDialog/Analyze actions twice. Both
coarse requests timed out at the 60-second stage deadline, before Mark/QA could
be tested on a completed result. Runtime logs confirm Astra medium; no fallback
was used. Both `interaction-74d6ee9-gui-case-119-mark1` and `mark2` private receipts
retain technical failure. Do not call the patched App's new-region end-to-end
flow passed, and do not equate source execution with a rebuilt frozen package.

Still incomplete:

- Per-region multi-turn context: previous questions/answers are not included in
  the next crop-review prompt. Manual annotations retain only the latest pair.
- Persistent readable history: answers normally disappear after 30 seconds.
- Existing-region answer text is not fully retained in the structured export.
- New-region real-model QA and proposed-update Apply/reject require live tests.
- Selecting arbitrary browser/third-party viewer windows needs more usable UI
  and separate actual-window acceptance; capture must remain ROI-bounded.

Explicit Export now includes the visible app-owned ChatPanel rendering. This
does not disable capture exclusion or capture other applications, and is not a
replacement for persistent conversation history. The separate incorrect NORMAL
heading on indeterminate results remains open.
