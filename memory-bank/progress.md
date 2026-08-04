# Progress (Updated: 2026-08-04)

## Done

- **Regional review and ECGFounder evidence-chain hardening** (2026-08-04):
  - Made image/result/capture/revision publication atomic; moved reviewer Apply
    to `AsyncBridge` and rejected stale or in-flight writeback.
  - Regional review now audits source pixels, performs a bounded refine plus
    structured proposal turn, preserves both public tool traces, and blocks all
    report mutations on low/missing/failed signal evidence.
  - Preserved exact finding ids and manual-region lifecycle; protected
    multi-box/multi-static-region findings from a single-crop rewrite and
    persisted revised confidence/questions. Unique image sessions reject stale
    tool events, while applied/dismissed/blocked/no-change outcomes are audited.
  - Invalidated manual-mode snapshots on image changes, clamped source crops at
    right/bottom edges, and kept thin ECG traces out of the blank-crop gate.
  - Added ECGFounder per-case nonce correlation, exactly-one pinned success
    receipts, success/failure provenance, strict 12-lead/per-lead gates, deep
    health, desktop evaluation-only status, full MIT notice, and bundle bans for
    model/waveform/sidecar payloads.
  - Ruff passed. Unit+smoke: 738 passed plus one release-only skip. OpenClaw
    integration: 55/55. Fresh bundle rebuild is pending.

- **Reviewer-confirmed regional writeback and export provenance** (2026-08-04):
  - Wired `AnnotationAccumulator` into the desktop agent and added exact-crop,
    JSON-only regional follow-ups with explicit Apply/Dismiss controls.
  - Bound every proposal to app-owned original-ROI coordinates and current
    finding/result identity; added result-revision and same-image request-id
    race guards plus deterministic low-signal writeback rejection.
  - Preserved `interactive_ai_review` source and reviewer confirmation through
    the report, Process trace, JSON, and annotated PNG; manual regions are
    consumed after promotion so exports do not duplicate them.
  - Corrected geometry dedup to require a matching normalized diagnosis label
    in addition to IoU, retaining multiple diagnoses over the same waveform.
  - Superseded verification: OOM-safe unit+smoke was 706 passed plus one release-only
    skip. OpenClaw integration: 55/55. Fresh bundle rebuild is pending.

- **Luna default, recoverable Gateway, and ECGFounder held-out evaluation**
  (2026-08-04):
  - Made `openai/gpt-5.6-luna` the desktop/runner default and verified the real
    bundled-OpenClaw catalog row (`text+image`, 1.05M context). A paid one-image
    transaction reached Responses but remains blocked by exhausted credits.
  - Fixed a Windows stale-lock defect in both desktop and experiment runner by
    replacing `os.kill(pid, 0)` with Win32 process exit-state inspection.
  - Added full 150-score offline ECGFounder output, protocol integrity checks,
    exact semantic mapping, deterministic five-fold evaluation, and 7 focused
    evaluator tests. The live agent payload remains capped at 20 predictions.
  - Real 1,000-row research result: 23 supported concepts, macro CV BA 0.865,
    sensitivity 0.848, explicit-normal specificity 0.883, top-20 concept recall
    0.837, and 3-5 diagnosis complete recall 0.479. No deployment threshold or
    screenshot-agent accuracy claim is made.
  - Settings/Process UI exposes actual model and secret-free external waveform
    evidence provenance. OOM-safe unit+smoke now passes 680 tests plus one
    release-only skip; OpenClaw integration remains 55/55.
  - Rebuilt and verified the portable bundle: manifest `ok`, frozen smoke 2/2,
    363.87 MiB / 15,225 files, OpenClaw `2026.7.1-2`, Node `v24.18.0`, EXE
    SHA-256 `3FFE577B3562965E34360BC765811F150BDA594AFA4E5BA7147E8575A4320D48`.
    Frozen PYZ contains all Luna defaults; external-model/sensitive scan is empty.

- **Systematic MultiPass harness, GPT-5.4 Mini canary, and final bundle**
  (2026-08-04):
  - Added mandatory, bounded original-ROI EKG limb/precordial discovery probes,
    trace/provenance fields, artifact gates, and UI process-trace visibility.
  - Corrected component-specific partial-credit denominators, safety comparison
    metrics, paired sign tests, and derived guardrail replay provenance. The
    six-case replay moves partial credit 0.596->0.678 and urgent recall
    0/2->1/2, but p=1.0 remains explicitly non-significant.
  - Registered `openai/gpt-5.4-mini` as an image-capable Responses API profile.
    A real one-image canary reached the provider with `promptImages=1`, then was
    correctly recorded as blocked by exhausted provider credits; no answer or
    full three-arm accuracy claim was fabricated.
  - Full repository Ruff passed. OOM-safe unit+smoke: 666 passed plus one
    release-only skip. OpenClaw integration: 55 passed. Frozen bundle: 2 passed.
  - Final portable EXE SHA-256:
    `B3066A365EB72F705EC49F4EFFB3E2B93A1C32D52BA218EB0C531F03F3B0B8D8`;
    manifest `ok`, 363.86 MiB, OpenClaw `2026.7.1-2`, Node `v24.18.0`, both
    native tools runtime-loaded. Build staging now strips `.env*`; recursive
    sensitive-content scan is empty.

- **Monitor-bound coordinates, GitHub Pages, and fresh desktop bundle**
  (2026-08-04):
  - Replaced primary-screen DPR assumptions with Win32 physical display lookup,
    target Qt screen selection, saved successful capture rects, per-axis frame
    mapping, and physical-edge round-trip calibration.
  - Fixed uncertain `INFO` bbox suppression; uncertain reviewer questions can
    now remain visible and clickable while normal findings stay report-only.
  - Verified focused coordinate/UI paths 87/87, then-current unit+smoke 647,
    then-current OpenClaw integration 54/54, and frozen bundle smoke 2/2.
  - Real GUI probe: Win32 viewer `1222x836`, mss PNG `1222x836`, display
    physical `2560x1600`, Qt logical `1707x1067`.
  - Added `site/`, synthetic ECG media, Pages deployment workflow, and four site
    smoke assertions. Playwright desktop/mobile QA passed with zero console
    errors or horizontal overflow.
  - Superseded bundle from the coordinate-only checkpoint: SHA-256
    `C44DA431AA5D1BFC72D943B3835BFC6A403BD426B483F9661B5FA17266383F66`;
    launcher 6.90 MiB, app 94.58 MiB, OpenClaw 181.03 MiB, Node 88.25 MiB,
    total 363.86 MiB. Manifest status `ok`.
  - Explicit platform boundary: Windows 11 verified, Windows 10 pending clean
    machine, Windows 7 unsupported by the current modern runtime stack.

- **ECGFounder external waveform tool + full MEETI waveform arm** (2026-08-04):
  - Added a loopback-only sidecar with trusted artifact registry, bearer token,
    source/checkpoint hash verification, exact official lead reorder and
    preprocessing, lazy serial CPU inference, bounded output, and explicit
    calibration/provenance limitations.
  - Rebuilt the 1,000-case MEETI cohort with one matched raw waveform per image;
    all inputs satisfy 12 leads x 5,000 points at 500 Hz for 10 seconds.
  - Added the conditional OpenClaw `ecg_founder_analyze_waveform` tool and an
    explicit paired-arm prompt/context in `run-eval.py`; uncalibrated scores are
    never converted to decisions and the tool can never supply image bboxes.
  - Added isolated setup/start scripts and a resume-safe batch runner with
    immutable protocol fingerprint, JSONL rows, atomic summary, and no emitted
    filesystem paths.
  - Official checkpoint real run: 1,000/1,000 `ok`, zero failures, 691.182 s,
    median 756.491 ms, p95 794.734 ms. A real native-plugin HTTP bridge smoke
    also passed and wrote a PHI-free audit receipt.
  - Rebuilt the portable desktop bundle after fixing calendar-version handling,
    stale PyInstaller launcher use, PyInstaller 6.19 contents placement, and the
    bounded cold plugin-inspection timeout. Packaged verifier is `ok`, real EXE
    self-check smoke is 2/2, OpenClaw is `2026.7.1-2`, Node is `v24.18.0`, and
    total size is 363.86 MiB. No Torch/checkpoint/sidecar/MEETI files are bundled.
  - Then-current OOM-safe suite: 47 isolated batches, 636 passed and 1 default-skipped
    opt-in bundle smoke (run separately and passed). All 76 changed Python files
    passed changed-file Ruff; the 26 pre-existing full-repo findings were later
    cleaned up by the final 2026-08-04 verification pass.
  - New end-to-end OpenClaw image experiments remain blocked by OpenAI account
    credits; provider quota failure is recorded as blocked, never scored as an
    image-model answer.

- **Harness 槓桿 1+2：rhythm-strip 二次 crop + empty-summary retry**（2026-07-05）:
  - 槓桿 2（empty-summary retry）：`eval_harness.is_empty_read()` 判定空讀
    （summary 空白且無 findings），`run-eval.py` 的 analyze closure 偵測到就
    重送一次，救回挖掘發現的 ~8% 硬失敗；mock 永不觸發故不影響既有測試。
  - 槓桿 1（rhythm-strip 二次 pass，通用）：新增
    `application/rhythm_strip.py`——`resolve_rhythm_strip_region()` 只從模型
    Step 0 宣告的 `layout.rhythm_strip_bbox` 取區域（無宣告即 no-op，不猜位置
    → 單導極／局部／非標準安全）；`refine_rhythm_strip()` crop rhythm strip、
    用 raw client 重讀一次（1 bounded call，不進 multipass trace）、
    `merge_rhythm_strip()` 以 escalate-only 合併 rhythm 軸（heart_rate/rhythm/
    regularity/p_wave/pr_interval/av_block）與新 abnormal findings（bbox remap
    回 0-1），絕不降級。
  - 支撐改動：`AnalysisResult` 加 optional `layout` field（additive）、
    `_parse_result` passthrough layout；EKG SKILL.md ×2 加 `rhythm_strip_bbox`
    宣告與 Step 0 指示；run-eval 加 `--rhythm-strip-pass`（預設開，
    `--no-rhythm-strip-pass` 關）。
  - 測試：新增 `tests/unit/test_rhythm_strip.py`（11 個：resolve/merge/refine，
    含 non-EKG no-op、無 bbox no-op、never-downgrade、analyze 失敗回 coarse）
    + `is_empty_read` 測試。完整套件 39 批全綠、無回歸。

- **Real-model path + lead-aware EKG + scorer robustness** (2026-07-05):
  - Real-model path proven: on a network where OpenRouter/Anthropic are
    firewall-reset, `api.openai.com` is reachable and `OPENAI_API_KEY` is
    valid. MEETI single-case real run with `openai/gpt-5.5` + `openai-vision`
    passed (strict/schema/bbox 1.0, `gateway_mode: real`). Runner default
    model fixed to `openai/gpt-5.5` (the `-mini` id is absent from the OpenAI
    catalog). Copilot subscription models (MAI Flash) are unusable as an API
    provider (OAuth device-token flow, not an API key).
  - Harness increment 1 — lead-aware EKG (general, "declare don't assume"):
    EKG SKILL.md runs a Step 0 lead-localization (read printed lead labels,
    inventory only visible leads, mark unlabeled `unknown`) and gates
    lead-dependent conclusions (STEMI territory / axis / R-progression /
    chamber) on the captured leads. Handles 12-lead / 6-lead / single rhythm
    strip / partial / non-standard / unknown. Optional additive `layout`
    block; 16-key checklist contract unchanged.
  - Harness increment 2 — scorer robustness: `eval_harness` adds
    `_normalize_lexical` (hyphen/underscore/slash folding) + expanded clinical
    synonym aliases (RBBB/afib/LVH/PVC/flutter/axis deviation…); ambiguous
    bare abbreviations (LAD/RAD) excluded; negation still honored. +5
    regression tests (incl. "genuine disagreement still misses" and "negation
    still not counted").
  - Mining verdict (25-case real gpt-5.5, free re-score with the new scorer):
    keyword_recall 0.531→0.55, strict 0.24→0.28. Scorer false-negatives are
    real but small; ~72% of failures are genuine misses (PR/AV-block/BBB/
    rhythm) or noisy/aggregated MEETI ground-truth labels. Next levers:
    lead-aware rhythm-strip second-pass crop, empty-summary retry (8%
    hard-fail), severity calibration, manifest GT de-duplication. New
    `scripts/analyze-eval-failures.py` (OOM-safe) aggregates per-run failure
    modes.

- **MEETI 1000+ production artifact gate + OpenClaw/OpenRouter refresh**
  (2026-07-02):
  - Updated local OpenClaw runtime to `2026.6.11` and validated the CLI config.
    The Gateway contract remains the stable public `connect` + `chat.send`
    protocol 3 image-attachment path; no minimum-safe version bump was needed.
  - Validated a generated OpenRouter profile config using
    `OPENROUTER_API_KEY` and `https://openrouter.ai/api/v1`, with secrets kept
    as environment SecretRefs rather than committed config values.
  - Built `data\eval-datasets\meeti-1000-all\manifest.json` from local
    `MEETI.rar` (Zenodo record `18523205`) using Windows `tar`/`bsdtar`.
    Local archive scan found 9922 PNG-bearing studies; the gate manifest keeps
    1000 cases.
  - Ran strict mock evaluation:
    `data\eval\meeti-1000-mock-20260630-assist` completed 1000/1000 cases with
    zero errors and strict/schema/bbox pass rates of 1.0.
  - Exported expert-review annotations for all 1000 cases and verified artifacts
    with `scripts\verify-eval-artifacts.py --min-cases 1000`. Passed checks:
    `min_cases`, `scorecard_complete`, `schema_gate`, `bbox_gate`,
    `cant_miss_gate`, `mock_perfect_gate`, `results_artifacts`,
    `local_preflight_artifacts`, `model_assist_artifacts`, and
    `review_artifacts`.
  - Fixed the current 1000-case "question test" OOM path: `run_evaluation()` no
    longer rewrites the full `scorecard.partial.json` after every image. Partial
    checkpoints now refresh every 50 cases by default while still writing
    final/abort evidence; `scripts/run-eval.py` exposes
    `--partial-scorecard-interval`.
  - Added `scripts\run-tests-safe.cmd` as the OOM-safe local test entry point.
    It now calls the existing uv-managed `.venv\Scripts\python.exe` directly,
    routes temp files through `data\tmp\pytest-safe`, disables the pytest cache
    provider, and defaults to the unit+smoke suite. PowerShell is no longer the
    default test path after the 2026-07-02 OOM report. After the follow-up OOM
    report, the runner now delegates to `scripts\run_pytest_safe.py`: default
    and pure-option runs such as `scripts\run-tests-safe.cmd -q` execute each
    `test_*.py` file in its own short-lived pytest process. After the next OOM
    report, explicit directory targets (`tests\unit -q`, `tests -q`) and
    multiple explicit test files also expand into per-file batches, while a
    single explicit test file remains one targeted pytest session. It also takes
    `data\tmp\pytest-run.lock`, so a second pytest runner exits 75 before
    creating another test process.
    It also sets `DICOM_OVERLAY_TEST_DISABLE_REAL_OPENCLAW=1`, preventing
    unit/smoke tests from accidentally starting a real OpenClaw Gateway unless
    an explicit integration run opts in.
  - Added `scripts\run-ruff-safe.cmd` after naked `uv run ruff ...` tried to
    initialize the user AppData uv cache and failed with access denied. The
    wrapper now calls `.venv\Scripts\ruff.exe` directly and uses
    `data\tmp\ruff-run.lock`.
  - Added OpenClaw/conhost OOM guards: `GatewayManager.start()` now takes
    `data\tmp\openclaw-gateway.lock` for the lifetime of the Gateway subprocess
    and refuses a second live launch; `scripts\test-real-stack.bat` no longer
    launches Gateway through `cmd /k`, using `start /B` + `gateway.log` instead.
    `scripts\run-meeti-openclaw-experiment.py` also takes the same Gateway lock
    before spawning OpenClaw, closing the remaining experiment-run path that
    could have multi-launched Gateway/conhost outside the GUI manager.
  - Hardened pytest defaults to collect only `tests/unit` + `tests/smoke`, skip
    generated/vendored trees (`data`, `openclaw`, `openclaw-home`,
    `.uv-cache-codex`, `node_modules`, etc.), suppress captured-output dumps on
    failures, and filter structlog debug noise in tests.
  - Re-verified after the OOM fix:
    `data\eval\meeti-1000-mock-oomfix-20260702` completed 1000/1000 MEETI mock
    eval, exported 1000 review images, and passed
    `scripts\verify-eval-artifacts.py --min-cases 1000` including review,
    local preflight, and model-assist artifact gates.
  - Added deterministic local image-quality metadata to eval raw results via
    `ImageProcessor.image_quality_profile()`: width/height, aspect ratio, ink
    pixel ratio, bright pixel ratio, and `low_signal`. This is the first
    non-MLLM assist layer for cheap unreadable-input detection.
  - Added deterministic local signal/bbox candidate metadata via
    `ImageProcessor.local_signal_candidates()`. Each eval raw result now records
    `local_signal_candidates`, giving reviewers a cheap local waveform/signal
    bbox proposal before the MLLM read; `verify-eval-artifacts.py` now gates
    this as `model_assist_artifacts`. `run-eval.py --multi-pass` now converts
    those candidates into crop targets when the coarse MLLM read is non-normal
    but lacks bboxes, so crop re-analysis does not depend entirely on first-pass
    model coordinates. `multipass-trace.jsonl` now records
    `local_candidate_count` and normalized `local_candidate_regions`, making the
    local-assist path auditable after 1000-case runs. The eval artifact
    verifier validates those trace fields when present and reports
    `multipass_trace_artifacts`; `scripts\verify-eval-artifacts.py` now also
    exposes `--require-multipass-trace` so production multi-pass runs fail when
    crop re-analysis trace evidence is missing.
  - Hardened annotation review completeness: no-bbox cases now produce
    case-level audit rows, so bbox-free normal cases are still counted in the
    1000-case review gate.
  - Bounded `run-eval.py` console output by default with `--case-print-limit 50`
    and `--verbose` for short diagnostics, reducing PowerShell/OOM risk during
    1000+ image harness runs.
  - Fresh verification: OpenClaw image harness smoke + verifier passed on
    `data\harness-smoke\latest-openclaw-20260702`; targeted unit/smoke tests
    for the assist gate passed.
  - Latest OOM-safe test runner verification:
    `scripts\run-tests-safe.cmd -q` completed all 38 per-file pytest batches
    without OOM; observed result was 438 passed and 1 existing opt-in bundle
    smoke skipped.
  - Latest multi-pass trace gate verification:
    the targeted eval artifact validator tests passed, the 1000-case mock
    artifact still passed the default gate, and the same artifact correctly
    failed with `--require-multipass-trace` because it lacks
    `multipass-trace.jsonl`.
  - Added real-model readiness gate:
    `scripts\check-real-model-readiness.cmd` writes a `ready`/`blocked` JSON
    artifact before any long Gateway-backed run. It checks provider credential
    presence, 1000-case manifest size, completed eval artifacts, and local
    OpenClaw runtime evidence without leaking secrets, while the `.cmd`
    wrapper calls `.venv\Scripts\python.exe` directly and uses
    `data\tmp\readiness-run.lock`. The new `--probe-provider` flag also checks
    provider egress and advertised image-input support before launching
    Gateway/eval.
  - Switched the desktop OpenRouter default profile to MiniMax M3
    (`openrouter/minimax/minimax-m3`) and added
    `scripts\run-meeti-openclaw-experiment.cmd` as the non-PowerShell real-run
    wrapper. Readiness next commands now point to this `.cmd` wrapper, which
    calls `.venv\Scripts\python.exe` directly and uses `data\tmp\meeti-run.lock`.
  - OpenRouter MiniMax M3 readiness is ready at
    `data\experiments\real-model-readiness-20260702-openrouter-minimax-m3.json`:
    `OPENROUTER_API_KEY` is present, the 1000-case manifest is valid, OpenClaw
    is `2026.6.11`, and the mock artifact gate is complete.
  - Provider-probed readiness is blocked at
    `data\experiments\real-model-readiness-20260702-openrouter-minimax-m3-probed.json`:
    local OpenRouter metadata fetch fails with WinError 10054 before Gateway
    startup, and next commands now point back to readiness probe instead of full
    experiment launch.
  - OOM-safe readiness wrapper recheck is blocked at
    `data\experiments\real-model-readiness-20260702-openrouter-minimax-m3-cmd-probed.json`:
    the wrapper reads `.env`, verifies the 1000-case manifest and mock artifacts,
    then blocks on the same OpenRouter WinError 10054 provider egress failure.
  - Latest OOM-safe OpenRouter probe remains blocked at
    `data\experiments\real-model-readiness-20260702-openrouter-minimax-m3-current-probed.json`:
    `OPENROUTER_API_KEY` is present, OpenClaw is `2026.6.11`, 1000-case mock
    artifacts pass, but the provider probe fails before Gateway startup with
    WinError 10013 socket permission denial.
  - Latest MiniMax M3 1-case smoke:
    `data\experiments\meeti-openrouter-minimax-m3-1case-resume-20260702`
    reached Gateway `connect` + `chat.send` and exported scorecard/raw/review
    artifacts, but ended `completed_with_failures` because local OpenRouter
    network fetches fail with `ECONNRESET`.
  - Next clinical-usability harness target: wire the existing MultiPass/crop
    path into an auditable two-step overlay flow: whole-ROI triage, per-bbox
    crop re-analysis for the text inside each box, and automatic remapping /
    drift validation before the bboxes are drawn back onto the physician's
    screen.
  - Added `infrastructure.overlay_geometry.project_bbox_to_overlay_highlight()`
    and wired the AI bbox overlay path through it. It clamps overflow bboxes,
    rounds projected edges across DPR conversion, and records round-trip drift
    calibration before returning the 6-field overlay highlight tuple.
  - Added `infrastructure.overlay_highlight_builder.build_ai_bbox_highlights()`
    so the desktop AI bbox path produces PHI-free projection audit rows and
    withholds any dynamic bbox whose round-trip drift calibration fails before
    drawing it on the physician overlay.
  - Updated the OpenClaw harness manifest to explicitly advertise
    `bboxCropReanalysis`, `coordinateDriftCalibration`, and
    `gatewayOnlyDesktopBoundary`, clarifying that OpenClaw-side specialization
    can be plugin-shaped while the desktop app remains Gateway-only for version
    compatibility.
  - Legacy PowerShell wrapper note: `scripts\run-meeti-openclaw-experiment.ps1`
    still exists for compatibility, but current docs/readiness prefer the
    `.cmd`/Python path because PowerShell caused OOM in this workspace.
  - Hardened real-model readiness and experiment launch:
    `scripts\check-real-model-readiness.py --dotenv .env` can use repo-local
    credentials without leaking values; `scripts\run-meeti-openclaw-experiment.py`
    supports `--provider-profile`, generated provider configs before catalog
    checks, Gateway-start retry, review export, and scorecard `error_count`
    gating so failed real evals cannot look green. The `.cmd` wrapper supplies
    repo-local `.uv-cache-codex`, repo-local temp, uv progress suppression, and
    disabled uv-managed Python downloads.
  - Hardened MEETI experiment artifact gating:
    `scripts\run-meeti-openclaw-experiment.py` now runs
    `scripts\verify-eval-artifacts.py` after review export. Bounded smoke runs
    use `--limit` as the verifier minimum, full runs default to 1000 cases, and
    `--multi-pass` automatically adds `--require-multipass-trace` so crop
    re-analysis trace evidence is mandatory for production multi-pass runs. The
    same post-run verifier now adds `--require-projection-audit`, making
    desktop-overlay projection round-trip calibration fields mandatory for
    bbox audit rows with model boxes.
  - Disabled client-side WebSocket keepalive pings in `OpenClawClient` for long
    medical-image inference; explicit inference timeout remains the control.
  - Latest real 1-case smoke:
    `data\experiments\meeti-openai-gpt54mini-1case-pingfix-20260702b` reached
    OpenClaw Gateway `connect` + `chat.send` and wrote scorecard/raw/review
    artifacts, then correctly failed with `eval_error_count=1` because local
    network egress to `api.openai.com:443` is blocked (`Node fetch` reports
    `EACCES`, `curl` cannot connect). Superseded OpenRouter/MiniMax M3 smoke now
    proves `OPENROUTER_API_KEY` is present but the local OpenRouter egress path
    is still blocked by connection resets.

- **MEETI MultiPass real-run harness** (2026-05-30):
  - Added `scripts/run-eval.py --multi-pass --multi-pass-max-targets N` to run
    the actual app `MultiPassAnalyzer` path during evaluation, not only a
    single image+prompt pass.
  - Added per-image `multipass-trace.jsonl` artifacts with
    `openclaw_analyze_calls`, `coarse_passes`, `zoom_passes`, and `crop_calls`;
    mock smoke showed 2 analyze calls / 1 crop per first two MEETI cases.
  - `scripts/run-meeti-openclaw-experiment.ps1` now records multi-pass settings
    and can launch reproducible full MEETI runs with experiment-local OpenClaw
    config/logs/artifacts.
  - MultiPass selector now refines non-normal (`info`, `warning`, `critical`)
    findings with bboxes, prioritizing critical -> warning -> info, so under-called
    suspicious findings still get a crop/refine pass.
  - Eval scorer now treats abnormal checklist axes and underscore-normalized
    checklist values as keyword evidence, preventing false misses such as
    `ischemia` when `checklist.ischemia = st_depression/warning`.
  - EKG skill prompt now explicitly preserves MEETI waveform-reading instructions:
    10-second rhythm-strip rate estimation, LVH voltage/strain checks, ST-T
    ischemia axis consistency, and warning severity floor for clinically meaningful
    ST-T/LVH/rate abnormalities.
  - Real `openai/gpt-5.4-mini` 1-case smoke after the prompt update produced
    3 OpenClaw analyze calls (coarse + 2 crops), improved `meeti_43522917` to
    warning severity with LVH/ischemia hits, but still missed bradycardia.
  - Full 400-case strict MultiPass run is in progress:
    `data\experiments\meeti-full-multipass-20260530-221551-openai_gpt-5.4-mini`.
  - Added offline expert-review export:
    `scripts\export-eval-annotations.py --eval-dir <eval> --manifest <manifest>`
    renders `review\<case>.review.png` with AI bboxes, numbered markers, and a
    right-side summary/finding panel, plus `review\index.html`.
  - Hardened the review export with bbox QA artifacts:
    `review\bbox-audit.jsonl` records normalized and pixel coordinates,
    crop-thumbnail paths, ink-pixel ratios, and `low_signal` flags for every
    bbox; `review\crops\*.png` stores the exact content inside each bbox, and
    low-signal boxes are cross-marked in the review PNG.
  - Added clinical partial-credit scoring to the eval harness: each case now
    records `partial_credit`, `partial_credit_breakdown`, and `strict_pass`;
    aggregate scorecards record `strict_pass_rate`, `mean_partial_credit`,
    mean partial-credit components, and per-target-axis performance. The
    negative component is only included when expected negatives exist, and a
    missed can't-miss label caps partial credit at 0.40.
  - Added paired run comparison:
    `scripts\compare-eval-runs.py --baseline <single-pass> --candidate <multipass>`
    resolves experiment roots or eval dirs, compares only shared cases,
    reports improved/regressed/unchanged counts, strict/partial/keyword deltas,
    MultiPass analyze/crop cost, optional bbox low-signal summaries, and an
    exact two-sided paired sign-test p-value. The comparator now rejects
    incomplete/error scorecards by default and requires `--allow-incomplete` for
    exploratory partial-run comparisons.
  - Added posthoc rescoring:
    `scripts\rebuild-eval-scorecard.py --eval-dir <eval> --manifest <manifest>`
    rebuilds `scorecard.rebuilt.json` from saved `results/*.json`, so older or
    still-running experiments can gain the new partial-credit metrics without
    rerunning the model.
  - `scripts\run-meeti-openclaw-experiment.ps1` now writes an in-progress
    `experiment.json` (`status=running`) before launching eval, then overwrites
    it with the final result in `finally`; future wrapper runs also rebuild the
    scorecard and export expert-review PNG/bbox-audit artifacts after eval.
  - Fixed `remap_bbox()` so zoom-pass child bboxes that overflow their crop-local
    frame are clamped to the parent crop before being mapped back to ROI
    coordinates.
  - Tightened eval scoring after subagent audit: positive keyword recall now
    ignores negated mentions (`no ischemia`), incomplete schema warnings make
    `schema_ok=false`, can't-miss detection requires positive evidence, and
    WNL / within-normal-range MEETI reports are explicit normal concepts.
  - Added `scorecard.partial.json` checkpoints after each eval case and
    fail-fast protection for repeated Gateway infrastructure errors, preventing
    aborted runs from producing hundreds of fake model failures.
  - Review export now cleans stale generated artifacts, records clamped bbox
    coordinates with `was_clamped` / `invalid_reason`, and the harness validator
    rejects bbox extents where `x+w` or `y+h` exceeds the normalized image frame.
  - The desktop app and `run-eval.py` now pass the actual downscaled image size
    into `MultiPassAnalyzer`, so the resolution-aware manual-zoom guard is wired
    through the real app/eval path.

- **MEETI / OpenClaw GPT-5.5 eval harness hardening** (2026-05-30):
  - Switched repo-local OpenClaw config from `openai/gpt-4o-mini` to the catalog-supported `openai/gpt-5.5`; confirmed local OpenClaw 2026.5.27 exposes `openai/gpt-5.5` but not `openai/gpt-5.5-mini`.
  - Added `scripts/load-env.bat` and wired it into `scripts/test-real-stack.bat` / `start.bat` so `.env` credentials are available to the Gateway without printing secret values.
  - Hardened `scripts/run-eval.py` for MEETI: `--dataset`, `--limit`, `--timeout-sec` (default 90s), `--require-perfect`, modality default `valid_regions`, and strict PERFECT GATE reporting.
  - Fixed scorer false misses: shared negative clauses (`No consolidation, effusion, pneumothorax`), keyword aliases (`no acute` via `without/no focal`, `infarction` via STEMI, ST-T/T-wave aliases), checklist values for positive keyword recall, and normal/info equivalence for strict severity.
  - Fixed MEETI report label extraction so generic nonspecific T-wave changes no longer imply ischemia or ST depression; regenerated the 400-case MEETI manifest.
  - Isolated each image analysis request with a fresh `analysis-<uuid>` Gateway session key to prevent cross-case context leakage; added narrow repair for malformed bbox JSON numbers such as `"x": 0.17"`.
  - Added `scripts/run-meeti-openclaw-experiment.ps1` to create reproducible full MEETI real-run records under `data/experiments/`, including model catalog, experiment-local OpenClaw config, Gateway logs, eval console, scorecard, and a blocked record when the requested model id is unavailable.
  - Recorded `openai/gpt-5.5-mini` blocked experiment (`data/experiments/meeti-20260530-214839-openai_gpt-5.5-mini`) and validated the runner with a 1-case `openai/gpt-5.4-mini` smoke (`data/experiments/meeti-20260530-214859-openai_gpt-5.4-mini`).
  - Verified: OpenClaw config validate OK; MEETI 400-case mock strict PASS; unit+smoke pass; GPT-5.5 real MEETI 10-case run completed with no timeout/parser crashes but still failed PERFECT GATE (schema 90%, bbox 100%, severity exact 70%, abnormal/normal 90%, keyword recall 37%).

- **臨床規則可審核性（對照文字說明 + 強制 description + 命中證據）** (2026-05-30)：
  - 🟢 **需求**：無論 soft/hard rule harness，人類要能審核——需保留「對照的文字說明」
  - 🟢 **規則對照表** `ClinicalConsistencyEngine.catalogue()` + `__main__ --explain-rules` CLI（仿 `--selfcheck`，不啟動 GUI/不連 LLM）：依 modality 分組列出每條**生效**規則（內建＋YAML 覆寫）的 id／白話觸發條件／醫學依據／命中行為（升級至 X、標記複核）／訊息。`RuleCondition.explain()` 把宣告式條件轉中文（欄位/運算子標籤表 `_FIELD_LABELS`/`_OP_LABELS`），`ClinicalRule.catalogue_entry()` 組成可讀區塊
  - 🟢 **命中證據（為什麼命中）** `RuleCondition.matched_terms()` 回傳實際比中的 `contains_any` 關鍵字、`ClinicalRule.evidence()` 聚合、`RuleViolation.audit_line()` 在 reason 後加「｜命中關鍵字：…」；hook log 新增 `evidence`/`audit` 欄位 → 審核者看得到 AI 自身輸出哪個字觸發升級，而非只知道規則 fired
  - 🟢 **強制可審核（enforce）**：`clinical_rule_loader._parse_rule` 拒絕載入沒寫 `description` 的 YAML 規則（記 log 跳過，永不擲例外）——把「可審核性」變成上線門檻，跟 wiring guard 文化一致；範本 `.example` 標注 description 為必填並附 `--explain-rules` 用法
  - 🟢 新增 9 測試（explain/evidence/audit_line/catalogue/分組/空引擎/強制 description）→ **unit+smoke 300 passed, 1 skipped**；變更檔 ruff 乾淨

- **臨床一致性引擎（資料驅動 + 醫學指引根據 + 模組化更新）** (2026-05-30)：
  - 🟢 **需求**：harness 除了 soft 建議 OpenClaw，要更穩健但又不能只是 hardcode rule——除非有醫學根據，且須能在指引更新時模組化抽換
  - 🟢 **設計哲學（不強加診斷）**：引擎只檢查 AI **自身結構化輸出**的「自我矛盾」（如 checklist 說 ST 抬高但 severity=NORMAL）與「不可漏診的低估」（can't-miss under-call），**只升級嚴重度（`_max_severity`，永不降級）**、**永不刪 finding、永不替醫師下診斷**，僅標記人工複核——醫師永遠保留最終判讀權（符合 Four Cores 憲章）
  - 🟢 **純 domain 引擎** `domain/clinical_rules.py`：`RuleCondition`（frozen，運算子 `contains_any`/`not_contains_any`/`equals` 文字類；`severity_at_most`/`severity_at_least` 嚴重度類；欄位存取 `summary`/`all_text`/`checklist.<key>`/`severity`，型別不符運算子於 `__post_init__` 擲 `ConditionError`）、`ClinicalRule`（frozen，附 `guideline`/`guideline_version`/`effective_date`/`source_url` 引用、`escalate_to`、`require_review`，`fires()`/`citation()`）、`ClinicalConsistencyEngine`（依 modality 分組，`evaluate()` 唯讀、`apply()` 升級＋標記＋去重 reasons）。4 條內建規則皆附指引引用（STEMI 未標記→CRITICAL、高鉀尖 T 波→WARNING、氣胸低估→CRITICAL、縱膈擴大→WARNING）
  - 🟢 **模組化更新（指引變更免改程式碼）** `infrastructure/clinical_rule_loader.py`：載入 `clinical_rules/*.rules.yaml` 規則包，`merge_rules` 依 **id 覆寫**內建規則或新增規則；malformed 檔/規則記 log 跳過**永不擲例外**（fail-safe）。仿 `modality_profile.py` 內建＋外部覆寫模式。附 `clinical_rules/ekg-cxr.rules.yaml.example` 範本（`.example` 後綴不載入）
  - 🟢 **接線** `infrastructure/hooks/clinical_consistency.py::ClinicalConsistencyHook`（post-analyze，呼叫 `engine.apply`，**永不擲例外**）接進 `__main__` hook pipeline（RateLimiter → InputGuard → OutputValidator → ClinicalConsistency）；引擎由 `build_clinical_engine(app_base_dir()/"clinical_rules")` 建立
  - 🟢 **呈現**：`AnalysisResult` 加 `review_required` / `review_reasons`（仿 incomplete 模式：app/infra 寫、presentation 讀）；`overlay_window.py` 加粗體紅字「🚨 需人工複核」面板，列出附指引引用的複核理由
  - 🟢 新增 30 測試（條件比對、升級不降級、去重、modality 範圍、內建規則、YAML 載入/覆寫/容錯、hook 整合）→ **unit+smoke 291 passed, 1 skipped**；變更檔 ruff 乾淨

- **接線護欄 + 多趟放大正式接線 + 跨輪去重（孤兒功能消除）** (2026-05-30)：
  - 🟢 **問題根因**：「純函式優先、GUI 接線最後、風險高就暫緩」策略系統性製造孤兒——`MultiPassInterpreter`、`AnnotationAccumulator` 都已建好＋測試＋寫進 README/ROADMAP，但 `__main__.py` 從未呼叫（README 宣傳的 multi-pass 出貨版其實沒跑）
  - 🟢 **治本：接線護欄** `tests/unit/test_wiring.py`：用 `pkgutil`/`inspect` 列舉 application 層公開 orchestrator（排除 `@dataclass` DTO 與 `Protocol`），強制每個「已接線（名稱出現在 `__main__.py` 源碼，測試證明可達）或顯式登記 `DEFERRED_WIRING`（附原因）」。新 orchestrator 兩者皆非 → CI fail，逼出誠實決策而非靜默孤兒。另測 DEFERRED 條目須有原因、且必須是現存 orchestrator（防 stale）
  - 🟢 **治標：multi-pass 正式接線**：新增 `MultiPassAnalyzer`（`application/multi_pass.py`）作為 `VisionAnalyzerService` drop-in——`analyze()` 走 `interpreter.interpret()`，`connect/chat/disconnect/is_connected` 委派 inner analyzer → `OverlayAgent` 零狀態機改動。`__main__` 在 `hooked_analyzer` 後依 `config.analysis.multi_pass_enabled`（預設 False，省延遲/token）條件包裝。`AnalysisConfig` 加 `multi_pass_enabled` / `multi_pass_max_zoom_targets`（entities + config_loader 解析）
  - 🟢 **新增 infra cropper**：`ImageProcessor.crop_region_base64(image_base64, region)`（PIL，符合 `ImageCropper` Protocol）：normalized 0-1 子區裁剪（**PHI 不變式：永遠是輸入子集，clamp 不越界**），短邊 < 512 時 LANCZOS 放大保留小病灶可讀性
  - 🟡 **誠實 DEFERRED**：`AnnotationAccumulator` 登記為待接線，原因＝chat 對話需產生結構化 `FindingDelta` 回寫 overlay 標記（目前 chat 僅回傳文字），不假裝接線
  - 🟢 新增 9 測試（wiring 護欄 4、`MultiPassAnalyzer` drop-in 3、cropper PHI 子集/clamp 2）→ **unit+smoke 261 passed, 1 skipped**；變更檔 ruff 乾淨
- **文件同步 + 分段 commit + push** (2026-05-30)：README.md / README.zh-TW.md（Core 1 多趟放大＋CXR 10 軸、Core 2 eval 評分＋can't-miss gate、Core 4 USB 即插即用＋`--selfcheck`、test-runner GPT-5.5 mini）、CHANGELOG.md Unreleased、ROADMAP.md v0.4.0 全部更新；刪除暫存 `test_out.txt`。`research.agent.md`（無關 in-progress 變更）保留不提交
- **USB 隨插隨用打包打通 + 自我檢查（--selfcheck）** (2026-05-30)：
  - 🟢 **真正的可攜性地雷修掉**：`__main__.py` 全程用 `Path.cwd()` 當 base（gateway/settings/openclaw-home/data/log）。雙擊 exe 時 cwd 不保證等於 exe 資料夾（可能是 System32）→ 別台電腦會找不到 config、寫錯地方。新增 `infrastructure/app_paths.py` 純函式 `resolve_app_base_dir(frozen, executable, cwd)`：frozen 時用 `Path(sys.executable).parent`，dev 時維持 cwd。`main()` 改用 `app_base_dir()` 串接所有路徑
  - 🟢 **Python 本身已包**：PyInstaller spec 嵌 CPython+stdlib+PyQt6（目標機免裝 Python）；Node.js 由 `fetch-node.ps1` 抓 portable `node\node.exe` 打包；OpenClaw runtime 由 `stage-openclaw-runtime.ps1` staged → 三者皆零安裝
  - 🟢 **`--selfcheck` CLI**：`GatewayManager.verify_runtime()` 回傳 `[(component, ok, detail)]` 驗 node/openclaw/可寫 base；`__main__._run_selfcheck()` 印報告並 exit 0(全 OK)/1(缺件)，**不啟動 GUI、不連 LLM** → 別台電腦插上隨身碟跑 `DICOMOverlayAgent.exe --selfcheck` 幾秒內知道能不能用
  - 🟢 測試：`test_infrastructure.py::TestAppBaseDir`(frozen 用 exe 夾、dev 用 cwd 各 1 測)；`tests/smoke/test_packaging_bundle.py`：in-process self-check（fast，always）+ 真實 exe `--selfcheck`（**opt-in `RUN_BUNDLE_SMOKE=1`**，避免跑到 stale build 或彈 GUI 視窗）
  - 🟡 **教訓**：第一版 packaging 測試沒 gate，CI 跑到上次 session 的 stale build（無 --selfcheck）→ 啟動 GUI hang 120s。改 opt-in env var + timeout 60s。發布流程：`build-exe.bat` 後再 `RUN_BUNDLE_SMOKE=1` 驗新 bundle
  - 🟢 **227 passed, 1 skipped**（packaging exe 測試正確跳過）；ruff 乾淨
  - 🟢 `test-runner` agent 模型改 GPT-5.5 mini 優先（fallback GPT-5 mini → GPT-4.1）
- **MultiPass 解析度感知（4K 截圖上限 + 手動放大提示）** (2026-05-30)：
  - 🟢 **問題**：影像 API 尚未接入前靠螢幕截圖（上限 4K），對截圖做數位切片放大**不會增加真實解析度**——某病灶在截圖中只佔少數像素時，數位放大只是內插模糊。
  - 🟢 `multi_pass.py` 新增純函式：`region_source_edge_px(region, source_size_px)`（回傳該區在截圖中的短邊像素）、`needs_manual_zoom(...)`（短邊 < `DEFAULT_MIN_ZOOM_SOURCE_EDGE_PX=256` 視為太小）、`build_manual_zoom_message(label, px)`（zh-TW 提示文案）
  - 🟢 `MultiPassInterpreter.__init__` 加 `min_zoom_source_edge_px`；`interpret(...)` 新增選用參數 `source_size_px`：提供時，太小的目標**不做數位切片**，改 append 手動放大提示到 `zoom_hints`；夠大才數位切片（可救回 pass-1 縮圖損失）。`source_size_px=None` → 行為與舊版完全一致（向後相容）
  - 🟢 `AnalysisResult` 新增 `zoom_hints: list[str]` 欄位（仿 `incomplete_reasons` 模式：app/infra 寫、presentation 讀）；`overlay_window.py` 加藍色獨立提示標籤渲染（與 amber incomplete 徽章語意分離）
  - 🟢 PHI 不變式：手動放大路徑**完全不切片**，不可能擴大截取範圍 → ROI guardrail 不動。DDD 邊界不動（純函式可測、切片仍委派 `ImageCropper`）
  - 🟢 新增 11 測試（短邊像素數學、門檻判斷、文案、小區→提示不切片、大區→仍數位切片、未知尺寸→照舊、混合目標各走一路）→ **unit+smoke 224 passed**
  - 🟢 ruff 設定：`RUF001`/`RUF003`（全形標點）加入 ignore——對 zh-TW 產品的 UI 字串而言全形標點是正確排版（既有 overlay 徽章本就觸發此誤報）
  - 🟡 **未接線（後續同前）**：`OverlayAgent` 改呼叫編排器並傳入截取尺寸，屬高風險 GUI/狀態機改動，暫緩；核心邏輯已穩
- **CXR 系統性 checklist + 軸×嚴重度覆蓋矩陣 + can't-miss 硬門檻**(2026-05-30)：
  - 🟢 **A. CXR 從「沒框架」變「有安全網」**：`modality_profile.py` 新增 `_CXR_CHECKLIST`(10 軸：airway/lungs/pleura/cardiac_silhouette/mediastinum/hila/diaphragm/bones/soft_tissue/lines_tubes)並掛上 CXR built-in profile → validator 自動強制(對齊 EKG 16-key 做法)。CXR skill prompt(`openclaw/` + `openclaw-home/` 兩份同步)改寫成完整 systematic 10 點 JSON schema + 閱讀順序 + can't-miss 清單
  - 🟢 **B. 軸×嚴重度矩陣 + 框架覆蓋率**：`EvalCase` 新增 `target_axes`；`eval_harness` 新增 `compute_axis_coverage()`(每模態回報 total/covered/coverage_rate/fully_covered(normal+abnormal 都測過)/missing_axes/matrix)；`EvalReport.axis_coverage` + scorecard 報「幾個軸被測過」而非只報平均；manifest 6 案全標 `target_axes`
  - 🟢 **C. can't-miss 硬門檻擋 CI**：`eval_harness` 新增 `CANT_MISS` 參考清單(EKG: STEMI/complete heart block/VT/hyperkalemia/long QT/Wellens；CXR: tension pneumothorax/pneumothorax/large effusion/pneumomediastinum/free air)；`EvalCase.cant_miss` + `CaseScore.cant_miss_caught/missed` + `EvalReport.cant_miss_total/caught_count/missed/cant_miss_passed`。caught = **abnormal 嚴重度符合 AND 致命診斷字串出現在判讀**(漏判 STEMI 卻說 normal 也算 miss)。`run-eval.py` 漏任一 can't-miss → **exit code 3 擋 CI**(不再只記一行)；manifest STEMI 案標 `cant_miss:["STEMI"]`
  - 🟢 **EKG harness 強化到專科級**：EKG skill(兩份同步)加 can't-miss 段(STEMI territory→culprit vessel 對應、de Winter/Wellens/Sgarbossa STEMI-equivalents、complete heart block/VT/hyperkalemia/long QT/Brugada/WPW)+ reading depth(報數值心率、ST 形態與 reciprocal、checklist 軸自洽性檢查)。**不動 16 keys**(會破壞 validator/測試)
  - 🟢 新增 5 測試(axis coverage normal+abnormal、can't-miss caught、called-normal miss、not-named miss、aggregate cant_miss+coverage)→ **unit+smoke 213 passed**
  - 🟡 mock 端到端需先下載 6 張 Wikimedia 影像(gitignored 未存在)才能跑 `run-eval.py --mock`；邏輯已由 smoke 測試全覆蓋
- **harness 新增 pertinent-negative(切題陰性發現)評分** (2026-05-30)：
  - 🟢 釐清現況：**生成端有**(EKG 16-key checklist 用 `absent`/`normal` 值即結構化陰性發現,OutputValidator 強制 16 鍵到齊→不能漏掉「排除 STEMI」);**評分端原本沒有**(`_haystack` 只收 summary+finding,完全不看 checklist,也無「該排除什麼」的 ground truth)
  - 🟢 `EvalCase` 新增 `expected_negatives: tuple[str,...]`；`CaseScore` 新增 `negative_hits/misses/recall`；`EvalReport` 新增 `mean_negative_recall`
  - 🟢 新增 `_negative_haystack()`：在 summary+finding 之外**併入 checklist 的 key 與 value**,所以 EKG 陰性發現(藏在 checklist 的 `stemi_pattern: absent`)也能被計分；正向 `keyword_recall` 維持只看 summary+finding(不改既有語意)
  - 🟢 抽出共用 `_recall()` helper;`run-eval.py` manifest 讀 `negatives` 欄位
  - 🟢 新增 5 測試(free-text 陰性召回、checklist 陰性召回、漏排除被扣分、無陰性預設滿分、aggregate `mean_negative_recall`)→ **unit+smoke 208 passed**
  - 🟡 後續：manifest 的 6 案尚未填 `negatives`;CXR 仍無 checklist→陰性只能靠 free-text(呼應先前 CXR 無系統性 checklist 的缺口)
- **多趟判讀編排器 MultiPassInterpreter（反覆標註 + 主動切片放大）** (2026-05-30)：
  - 🟢 新增 `application/multi_pass.py`：coarse→crop→refine 編排器。Pass 1 粗掃整張縮圖；對每個 abnormal(warning/critical) 且有 bbox 的 finding，從**原解析度** ROI 圖切出該區(含 padding)再送 `analyze` 細看；精修 bbox 用 `remap_bbox` 映射回 ROI 全域座標
  - 🟢 純函式可測：`clamp_unit` / `pad_region`(往外擴 padding，clamp 回 [0,1]) / `remap_bbox`(crop 相對座標→全域) / `select_zoom_targets`(critical 優先、無 bbox 跳過、max_targets 上限)
  - 🟢 DDD 乾淨：不解碼影像，切片委派注入的 `ImageCropper` Protocol（PIL 留在 infra）；只呼叫 `VisionAnalyzerService`(connect+analyze)，不碰 OpenClaw 內部 → Core 3 邊界不動
  - 🟢 PHI 不變式：zoom crop 永遠是 ROI 的**子集**(只會縮小)，測試 `test_crop_region_is_subset_of_roi` 鎖死 → 不違反 ROI guardrail
  - 🟢 收斂保護：`max_zoom_targets`(預設 3) 限制趟數；單一 zoom 失敗只 log warning 保留粗框，不讓整趟失敗
  - 🟢 新增 `tests/unit/test_multi_pass.py`（20 測試，含座標數學、target 選取、編排、額外 finding 串接）→ **unit 194 passed**
  - 🟡 **未接線（後續）**：overlay 累積標註(`show_result` 目前覆蓋 `_highlights`)與 `OverlayAgent` ANALYZING 狀態改呼叫編排器，屬高風險 GUI/狀態機改動，暫緩；核心邏輯已穩
- **真實公開標註資料集辨識實驗 + harness 修正** (2026-05-30)：
  - 🟢 **真實資料來源**：HuggingFace / GitHub raw 在本機網路被擋（連線重置 / DNS 失敗）；改用可連的 **Wikimedia Commons** 6 張已標註醫療影像（3 CXR + 3 EKG，授權 CC0/PD/CC-BY，記於 `data/eval-datasets/real-urls.commons.json`）
  - 🔴 **真實資料抓出 4 個 production / harness bug**：
    1. `fetch-eval-datasets.py` 缺 User-Agent → Wikimedia 回 403（加 `_HTTP_HEADERS`）
    2. `--urls-from` 真實跑零下載時靜默 fallback 合成資料 → 改 fail loud (`return 1`)
    3. eval 未 downscale（送原圖最大 50MB，與 production 不一致）→ 補 `downscale_to_max_edge(1568)`
    4. **WS 1 MiB 預設 frame 上限**（真圖 base64 > 1MiB 直接斷線）→ client connect + mock serve 設 `max_size=16 MiB`
  - 🔴 **CXR checklist 回傳 list（非 dict）導致 `AttributeError: 'list' object has no attribute 'items'`**：`_parse_result` 改用新 helper `_iter_checklist()` 容錯 dict / list（list-of-dict 取 key/name/label/item，scalar 用 `item_N`）；新增 2 回歸測試 → **233 passed**
  - 🟢 **真實實驗結果**（gpt-4o-mini, 6/6 案無 error）：severity 83%、abnormal 83%、schema 100%（修正前）、bbox in-bounds 100%、keyword recall 57%、mean latency 16.3s。artifacts: `data/eval/real-20260530-091759/scorecard.json`
  - 🟡 **有效發現**：STEMI ECG 被 gpt-4o-mini 誤判為 normal（模型能力限制，非 harness bug）— 證明 harness 能抓出模型漏判
  - 🟡 gateway 啟動須設 `OPENCLAW_CONFIG_PATH` / `OPENCLAW_STATE_DIR` / `HOME` / `USERPROFILE` 指向 repo-local config，否則載入錯誤預設 config → token mismatch
- **6 組 Sonnet 平行查核 + 修正** (2026-05-30)：
  - 🔴 **多螢幕座標錯位修正（潛在 PHI 風險）**：`__main__.py` 只記 `geo.width/height`、漏 `geo.x/y`，導致主螢幕不在原點時 mss 截到錯誤螢幕。修正：`OverlayAgent` 新增 `screen_left/top`、`_get_roi_rect` 與 inline capture_rect 加上螢幕原點 offset、`control_bar.position_bottom_right` 加 `screen_left/top` 參數、`__main__` 傳入 `geo.x/y*dpr`。（highlight 為 widget-local，無需改）
  - 🟡 **modality 解析 fallback 改善**：`openclaw_client._parse_result` 新增 `request_modality` 參數，未知/缺漏 modality 改回退「請求時的 modality」並 log warning（不再靜默寫死 EKG）
  - 🟡 **config 擴充非靜默**：`__main__` 對「registry 有但不在 Modality enum」的 config 模態 log warning（無法進 cycle 不再靜默）
  - 🟡 **build_registry 字串防呆**：`from_dict` 用 `_as_str_sequence` 把 `checklist_keys`/`aliases` 的單一字串視為單一元素（不再逐字元拆解）
  - 🟢 **新增 9 測試**（multi-screen ROI、icon 📊 預設合併、alias 衝突 last-wins、str checklist 防呆、supported 傳播、requested-modality fallback）→ **231 passed**
  - 查核結論：Core 2/3/4 幾乎全 🟢（harness 合約、Gateway 協定邊界、打包瘦身、PHI/yaml.safe_load 皆健康）；`_humanize_checklist_key` 已有 `.title()` fallback；log_file 路徑為使用者自有 config 同信任級，未強制 basename
- **Modality 註冊表模組化（多影像模態可擴充）** (2026-03-15)：
  - 🟢 新增 `domain/modality_profile.py`：`ModalityProfile`（key/display_name/icon/skill_name/checklist_keys/aliases/model_hint/supported）+ `ModalityRegistry`（key/alias 大小寫不敏感、`resolve()` 對未知模態回傳 fallback、`supported_keys()`）+ `default_registry()`/`build_registry()`/`get_active_registry()`/`set_active_registry()`
  - 🟢 收斂原本散落 7 處的 per-modality 知識（enum skill map、skill path、validator checklist、input-guard supported set、overlay icon、`__main__` cycle）到單一來源
  - 🟢 config.yaml 可透過 `modalities:` 區段覆寫/新增模態（KUB/echo/CT/MRI）免改 code；`model_hint`/`backend` 預留未來模型路由
  - 🟢 注入式 DI：`OpenClawClient`/`InputGuard`/`OutputValidator` 接受 `registry=`，未注入則回退 active registry（200 既有測試零改動）
  - 🟢 `__main__` 啟動時 `build_registry(config.modalities)` + `set_active_registry()`，modality cycle 由 `registry.supported_keys()` 動態產生
  - 🟢 新增 `tests/unit/test_modality_profile.py`（22 測試）→ **222 passed**
- **Core 2 強健化（6 項修正）** (2026-03-15)：
  - 🔴 live 結果經 OutputValidator 標記 `incomplete`+reasons，SummaryPanel 顯示「結果不完整」徽章（entities/output_validator/overlay_window）
  - 🔴 暫時性 inference timeout 退避重試一次（`_analyze_with_retry`，config: analyze_retries/backoff）
  - 🔴 散文包裹 JSON 容錯：`_extract_first_json_object` 平衡括號擷取（string/escape-aware）
  - 🟡 拆分 connect_timeout / inference_timeout（`OpenClawConfig` + client + config_loader + `__main__`）
  - 🟡 送圖前 `downscale_to_max_edge`（預設長邊 ≤1568px）並記錄尺寸
  - 🟡 越界 bbox 改為 log + drop（不再 silent suppress）；新增 14 個測試 → **200 passed**
- 修正 portable OpenClaw config 與 Windows 啟動腳本
- 將 OpenClaw client 從自訂 vision.analyze 改為真實 Gateway connect/chat.send RPC
- 更新 smoke test 為新協定並改用動態埠，測試通過
- 實際對真實 Gateway 發送帶 EKG 截圖的 chat.send 請求並驗證事件流
- GitHub Copilot device flow 認證完成，token 儲存於 `openclaw-home/credentials/`
- End-to-end 測試：真實 GPT-4o 分析截圖成功
- 修復 code fence JSON 解析 bug（`_strip_code_fence` regex）
- 新增 TTS 語音播報（Windows SAPI）+ toggle 開關
- 全模組 stdlib logging → structlog 25.5.0 遷移（10 模組）
- 修復 shutdown 錯誤、ROI persistence、reconnect UI freeze
- 新增 chat 功能（5 檔案）
- 修復 EKG rhythm_strip missing from config.yaml
- 系統審計 4 issues 全部修復（AsyncBridge、display timer、hotkeys、test mock）
- 模型從 gpt-4o 改為 gpt-5-mini
- WebSocket 自動重連（analyze + chat 包裝器）+ ping_interval=30, ping_timeout=60
- Code fence regex 改用 `re.search` 支援 `\r\n`
- 測試隔離修復（monkeypatch _DEFAULT_CONFIG_PATHS）
- Portable 架構審計完成：OpenClaw 本地安裝 ✅、HOME 隔離 ✅、credentials ✅、skills sync ✅
- **端到端測試 GPT-5-mini 成功** (2026-03-14)
- **Display Pipeline 深度審查 + 修復** (2026-03-14)
- **OpenClaw Overlay 完整整合測試** (2026-03-14)：42 個 mock WS 整合測試
- **Real Gateway 實際測試** (2026-03-14)：4/4 測試通過
- **Hook/Guardrail 系統** (2026-03-14)
- **MCP Adapter 對齊 OpenClaw** (2026-03-14)
- 初次 Git push 到私人 GitHub Repo ✅ (2026-03-14)

## Done (recent) — 2026-03-15

- **Gateway 自動啟動** (2026-03-15)：
  - `GatewayManager` 類：自動啟動/停止 Gateway subprocess
  - `dpi.py`：DPI 感知工具函式
  - `start.bat` 簡化：移除手動 Gateway 啟動步驟
  - `logging_config.py`：Gateway stdout 重導向至 `gateway.log`
- **Presentation 層重構** (2026-03-15)：
  - `DraggableWindowMixin`：SummaryPanel/ChatPanel 改為獨立可拖曳視窗
  - Smart Display：異常項優先、正常項摺疊為「✅ N items normal」
  - ROI 設定 DPI 修正
- **核心功能強化** (2026-03-15)：
  - EKG checklist 從 5 項擴展到 16 項系統性心臟病學項目
  - `OutputValidator` 對齊 16 key schema
  - 可配置 hash 演算法（phash/ahash/dhash/whash），預設 phash + threshold 5
  - WS frame log noise 修復（過濾 `type=event` 訊息）
  - 連線 log noise 修復（`logger.exception` → `logger.warning`）
- **AI 動態 Bounding Box** (2026-03-15)：
  - `Finding` 新增 `bboxes: list[RegionRect]` 欄位
  - AI prompt 改要求歸一化 0-1 座標 bounding box
  - `__main__.py` highlight 優先使用 AI bbox，fallback 到 static region maps
  - SKILL.md × 2 更新 bbox 指示
- **測試**：135 個 pytest 測試全部通過 (0.49s)

## Done (recent) — 2026-04-10

- **兼容性修正 + CI 重建** (2026-04-10)：
  - `pywin32` 改為 Windows-only 條件式依賴，修正 Linux/CI 安裝失敗
  - `OpenClawClient` 缺少本地 token 檔案時可無 token 建立，mock 測試不再依賴本機私有設定
  - `.github/workflows/ci.yml` 改為實際驗證跨平台安裝、`pip check` 與 pytest
  - 新增 gateway token fallback 測試
  - Linux headless 驗證通過：137 個 pytest 測試全部通過

## Doing

（無）

## Done (recent) — 2026-05-30

- **辨識評測 harness（如何記錄判讀成果）**：
  - 新增 `src/dicom_overlay/infrastructure/eval_harness.py`：`EvalCase`/`CaseScore`/`EvalReport`，`score_case()` 評 severity(精確+異常二元)、keyword recall、schema(重用 OutputValidator)、bbox 界內、latency；`run_evaluation()` 逐案評分並寫 scorecard.json + 每張 raw result
  - 新增 `scripts/fetch-eval-datasets.py`：產生帶標註合成 CXR/EKG（預設），或 `--urls-from` 下載真實公開影像
  - 新增 `scripts/run-eval.py`：`--mock`（內建 gateway，免 token，驗證評分管線）/ 真實 gateway（`--gateway`，量模型準確度）；走真實 OpenClawClient frame 建構+解析路徑
  - **實跑驗證**：mock 模式 6/6 案，severity 100%、schema 100%、bbox 100%，產出 `data/eval/mock-*/scorecard.json`
  - REAL_TEST_RUNBOOK 新增「Recognition evaluation」章節
  - 新增 5 個 smoke 測試 → **186 passed**
  - ⚠️ 限制：無 token 只能驗證「評分管線」非模型準確度；合成圖非診斷準確度宣稱

- **四大核心文件化 + Core 4 打包收斂**：
  - README.md / README.zh-TW.md 改寫為 DICOM Overlay Agent，新增四大核心章節與實測體積表
  - AGENTS.md 改寫為四大核心 AI 維護 harness（取代過時 Zotero 內容）
  - PyInstaller spec 瘦身：排除未用 PyQt6 模組（WebEngine/Qml/Quick/Pdf/Multimedia 等）+ 修剪 opengl32sw.dll、Qt6 重型 DLL、qml/translations data
  - 新增 `scripts/fetch-node.ps1`：下載 portable `node\node.exe`（opt-in 零安裝）
  - spec 新增 `optional_file("node/node.exe")` 打包 portable node
  - `gateway_manager._find_node()` 優先用 bundled node\node.exe，fallback 系統 node
  - build-exe.bat 串接 fetch-node（失敗不阻擋，退回系統 node）
  - 新增 4 個測試（_find_node bundled/system/missing + spec 打包斷言）
  - **實測體積**：exe 6.75MB ✅<50MB；App+Python/Qt ~89MB ✅<100MB；完整 bundle ~205MB（含 vendored OpenClaw 114MB，刻意不侵入內部以保 Core 3）
  - PyQt6 瘦身：72.6MB → 41.3MB（dist 234MB → 203MB）
  - **181 個 pytest 測試全部通過**

## Next

- 替換 `_StubProvider` 為真正的 Python MCP SDK client（`mcp` package）
- 測試真實 MCP server 連接（如 pubmed-search-mcp via stdio）
- 實機跑 fetch-node + build-exe 驗證 portable node 內嵌後 Gateway 可零安裝啟動
- Live 測試 AI bbox 精確度與 phash 偵測靈敏度

## Done (recent) - 2026-08-04

- **ECGFounder opt-in tool bridge**：
  - native plugin 新增 `ecg_founder_analyze_waveform`，endpoint 只允許 loopback
    HTTP，使用 bearer token，不接受路徑或 screenshot source。
  - response sanitizer 強制官方 500 Hz/10 秒/5000 點 input proof、lead count、
    model revision、checkpoint/source SHA-256、preprocessing 與 calibration
    provenance。
  - 未校準 threshold 一律降為 `uncalibrated_score`；輸出固定
    `supporting_evidence_only` 與 `spatial_localization: not_provided`。
  - Gateway allowlist 只有 endpoint+token 齊全時才加入工具，既有 MEETI
    screenshot baseline protocol 不受影響。
  - OpenClaw runtime inspect 實測 loaded、兩工具皆註冊、diagnostics 0。
  - OpenClawClient 會合併 PHI-free ECGFounder receipt 到 `analysis_trace`。
  - 文件：`docs/ecgfounder-tool.md`，README/README.zh-TW/ARCHITECTURE/skill 已同步。
  - 驗證：相關 pytest 86 passed、Node syntax/plugin smoke passed、Ruff passed。

## Next (current)

- 若要讓 ECGFounder 真正參與資料集實驗，先取得 matched raw waveform，或建立
  通過 lead label、紙速、電壓刻度、grid 與 trace continuity gate 的 digitizer。
- 將 Torch/checkpoint 放在獨立 sidecar 環境，核對 checkpoint SHA-256，並用
  獨立 calibration cohort 產生部署 threshold；不得從測試集現算 threshold。
- 修正系統化 MultiPass urgent canary 的 90 秒 timeout/多輪成本後重新 paired run。
