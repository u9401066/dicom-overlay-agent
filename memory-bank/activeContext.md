# Active Context

## 2026-09-11 Actual corrected EXE and first resize guard

- c3532d7 ZIP is 148,419,324 bytes (141.54 MiB), SHA
  f07c63a9c4463819a47c1c168c167429f68e565451d14b8881dc23bb24216a9f.
  All 18,771 entries roundtrip/hash-match; separate live copy matches; 53 UPX
  native payload tests pass. Original package preserved, no binary publication.
- Old App/Gateway closed normally via Quit. Live candidate EXE PID 33640 uses
  port 18791 and its own state. Real Settings selects Astra low; official pinned
  OAuth migration succeeds, Codex runtime/API key disabled. A known failed case
  now completes four verified Astra-low stages in 113.735 s (old 175.805 s with
  final timeout). Exact same captured source hash, finalization 40.400 s, zero
  parse retries, seven receipt-bound boxes. Still incomplete/review-required;
  not general speed/accuracy or blind acceptance. Summary widget visually checked.
- Actual Viewer shrink 1522x1136 -> 1200x850 + Analyze fails closed before sending
  with roi_outside_viewer_client; restored geometry and unchanged ROI. Retained
  startup/config convergence, GUI focus and local evidence-formatting failures
  are documented in docs/candidate-desktop-2026-09-11.md.
- Separate deliberate partial ROI selected through actual Set ROI dragging,
  inside the original safe region: actual 1484x708 source matches the Viewer
  subrectangle pixel-for-pixel. Four Astra-low stages finish in 91.436 s and
  prose identifies V3-V6 absent, but structured layout FAILS (lead instead of
  name, missing label_visible, unsupported partial_stacked). Eight malformed
  entries, zero valid mapped leads; raw output and separate one-pixel driver
  expectation/recovery receipts preserved. No rerun or baseline rescoring.
- Actual triage prompt now states exact canonical partial shape and prioritizes
  fields over character count. Parser requires boolean visible=true; missing,
  string/numeric visibility is not accepted or filled by row normalization.
  No lead/name alias, new clinical rule or model change. New + related target
  regression 224 pass; Ruff pass. This is source-only pending new EXE/model QA;
  preserved c3532d7 binaries do not contain it. See candidate desktop report.

## 2026-09-11 Post-seal usage and corrected package verification

- Read-only usage supplement v2 binds all 460 public sessions to Astra low:
  446 original stages plus 14 nested attempts. Thirteen synthetic binding checks
  cover exact/masked identity ambiguity; two masked identifiers never suffice.
  Seal verified unchanged, no inference or rescoring. Failed attempts without
  exported identity remain unknown; no complete billing or monetary claim.
  Supplement SHA 0684cbfb65d0bb7fcba56d46821d38c34220728b184bb278f415f4e26c45a045.
- Cumulative exposure denylist now has 1,358 identities, conservatively including
  all 128 selected cases. New blind selections must exclude them. Original
  selection, gold, exports and failed baseline are unchanged.
- Captured seven-box tool replay accepts all seven and matches the exact draft
  digest under plugin 1.5.9. Zero model requests; not clinical validation.
- c3532d7 clean-source static/runtime package verification passes; 20 frozen
  smoke checks pass (103.22 s), 90 native sources approved. Launcher 4.68 MiB,
  App 54.42 MiB, folder 337.01 MiB. Source and payload hashes are recorded in
  docs/direct-harness-integration.md. CI push 34501374911 and PR 34501380408
  pass on Windows/Ubuntu; secret scans pass. Immutable bundle retained; actual
  candidate GUI/OAuth/model checks will use a separate writable copy.
  No binary publication or license decision; failed clinical acceptance stays open.

## 2026-09-11 Bbox receipt defect and direct-model package checkpoint

- Primary real-GUI cohort is complete and sealed: 121 distinct successes,
  six retained technical failures, 1,991 inventoried files; six pilots excluded.
  Seal `data/tmp/desktop-astra-ui-20260910-main/primary-seal-20260910-1613.json`
  SHA 2de49ad479ddeef43b4e47fb1539e78161d4c4654d4ffc13c37ea63fb5e43657.
  First paired-gold score uses candidate a7d8fb4's recorded scorer, not the new
  coordinate correction: strict 0/46 complete-label cases; urgent concerns 2/21;
  exact severity 8/121; schema 113/121. All 121 results incomplete/review-required;
  109 finalizations complete, 12 timeout after a mismatched-receipt retry.
  Mean completed-case latency 136.662 s. This is a failed preliminary automatic
  acceptance result, not clinical sensitivity/specificity or release approval.
  Raw evidence is unchanged; see the separate dated evaluation report.
- Further synthetic origin half-tie tests found two Python rounding failures.
  App and artifact validator now share fractional-part rounding matching native
  Math.round. All 30,000 scalar half-tie/adjacent-float vectors match; expanded
  targeted suite 128 passed; full regression 1516 passed / five explicit skips
  (205.70 s). PR CI 34500348053 then exposed another existing 40 ms Windows
  stream-test race before acceptance. The mock now supplies its known-run ack
  immediately, uses a 200 ms test deadline and has a 1 s outer bound against
  endless deadline renewal. Production timeout/abort behavior is unchanged.

- Read-only public Gateway history on an original failed GUI finalization
  identified native `(origin + extent) - origin` cancellation on unclipped
  boxes. Synthetic cross-language parity first reproduced 23 failures / 13
  passes; plugin 1.5.9 preserves untouched extents and rejects rounded ROI
  overflow, without relaxing exact digest or image/turn binding. New + existing
  native/Gateway checks: 94 passed; full regression 1505 passed / five explicit
  skips (210.59 s), Ruff passed. Actual new-model latency/accuracy is not yet
  measured. See `docs/bbox-receipt-canonicalization.md`.
- PR #17 direct-model branch merged the candidate scorer; head 7abc364 retains
  pinned public harness efeff23. Push CI 34498083016 passed; parallel PR CI
  34498089534 found a Windows 20 ms scheduling-test race (1458 pass / 6 skip).
  That policy test now uses its existing injected clock; 139 multi-pass checks
  pass locally, with no production SLA or timeout-test change.
- Separate clean-source 7abc364 local package: static verifier passes, 90 native
  dependency sources approved, 20 actual frozen packaging checks pass (126.76 s).
  Launcher 4.67 MiB, App layer 54.42 MiB, full folder 337.01 MiB. This artifact
  retains plugin 1.5.8 and does not cover the later receipt correction; older
  f7e3347 bundle is unchanged. No binary publication/license change.
- Frozen main cohort at 16:01 UTC has 118 primary distinct GUI successes; index
  118 initial timeout remains, and index 126 was blocked pre-send by ROI
  obstruction while packaged tests were also active. Six technical failures
  are retained. Packaged tests ended; real Viewer rerun 126..127 is in progress,
  then 118 must be retried before sealing. No gold scoring has run.

## 2026-09-10 Current acceptance target and runtime fixes

- Separate `agent/direct-harness-models-20260910` worktree consumes public
  harness efeff23 directly for seven shared model types; duplicate App classes
  and all old caller imports are removed, with no compatibility exports.
  CI/Pages initialize the submodule and use the frozen uv source map. Schema
  resources are required by packaging and tested offline. Extra schema dependency
  installed non-pyc footprint is 1.43 MiB, not a measured EXE/ZIP increase.
  1127 existing checks passed; new boundary/package-verifier 56 passed; public
  harness own environment 222 passed plus public/agent-method and built-package
  integrity checks. Public PR #1 supplies missing py.typed metadata only; CI
  passed and the direct App's three targeted mypy modules pass without ignores.
  Full App run exposed one fresh-install OpenClaw staging failure (1420 passed,
  six explicit skips). Public CLI preparation now runs before OAuth-only
  migration relocation/pruning, with isolated state and a cleared child
  environment. Another cold locked install passes 9 helper/staging checks;
  full App regression passes 1429 / six explicit skips (186.95 s). Main runtime
  and the earlier accepted bundle remain unchanged. The candidate's isolated
  preparation fix a7d8fb4 passes CI 34496955373 and secret scans.
  See `docs/direct-harness-integration.md`. Full engine extraction, canonical
  host assembly and actual candidate GUI/model/packaging remain pending.

- New `scripts/score-desktop-cohort.py` verifies a complete >=100-case primary
  hash seal before opening the pre-digested paired gold, then scores immutable
  GUI exports with the existing scorer and no guardrail replay. Pilots stay
  separate; original technical failures remain in the report. Source/usage/model
  binding, pairing, changed evidence/gold, traversal, duplicate/negative indices,
  overwrite protection and descriptive Wilson endpoints have synthetic checks.
  New plus existing rebuild regressions: 38 passed; full unit/smoke/mock-integration
  suite: 1437 passed, 5 explicit opt-in/local-artifact skips (205.01 s); Ruff passed. Initial test
  exposed a floating-point nonzero lower endpoint at 0/100; fixed explicitly.
  This is tooling, not a real clinical score. Main at 15:06 UTC: 95 primary
  successes + six earlier pilots = 101 distinct actual UI cases.

- Integrated candidate is now `f7e3347`: PR #16 merged into #15, then #15
  merged into #13's branch; #13 remains draft and main stays on the frozen
  7.1-2 cohort implementation. CI 34489747248 and Secret 34489747329 pass.
  Clean isolated-PATH rebuild includes both crop-scope and client-boundary
  fixes: static verifier passes, 89 native sources approved, 52 UPX integrity
  checks pass, and 19 actual frozen packaging smoke tests pass (120.60 s).
  Owned test Gateway shuts down with no residual listener; no real model/auth.
  Launcher 4.47 MiB, App 53.84 MiB, folder 336.43 MiB; local Deflate-9 ZIP
  141.13 MiB, all 18,720 decompressed hashes match. Verifier report stays outside
  the archive. Historical f184258 and failed fe0a612 artifacts remain untouched.
- At 14:52 UTC, 89 primary distinct GUI successes plus six earlier pilots = 95.
  Primary planned indices 7..127 continue; clinical scoring has not run and
  pilots will stay separate. Main source/runtime are unchanged. No binary
  publication; real candidate GUI/OAuth/model, partial-ECG/DPI/rollback and PyQt
  distribution-license decision remain open. Old extraction PR #4 retains
  compatibility exports, contrary to the user's requested direct separation;
  it is not an integrated independent-harness implementation.
- Diagnostic-only Qt PE import audit found Qt6Network.dll is imported by
  qtuiotouchplugin.dll, and Qt6Svg.dll by SVG icon/image plugins. No extra
  payload was removed: static imports alone do not prove safe removal of a
  dynamically loaded plugin or establish a startup/GUI improvement.

- Capture client guard pushed as draft stacked PR #16 (`69ac5c9`); CI
  34488167020 and Secret scans 34488169068 / 34488160587 pass. No main runtime
  change or binary release. The original 9.3 packaged f184258 artifact is not
  evidence for these later crop/client changes.
- Main cohort case 85 completed actual GUI inference/export but its diagnostic
  usage collector failed: Gateway log masking shortened one UUID to a prefix
  plus `***`. Public session metadata and the exact session id still bound the
  four actual Astra-low turns. Helper now requires matching public session id,
  provider/model, >=16-character masked-run prefix and one unique log match;
  14 synthetic positive/negative binding checks pass. Original failed receipt
  and export remain unchanged; separate `usage-receipt.recovered.json` plus an
  append-only recovery row record the repair, with no new model request.
  Batch resumed at index 86. At 14:27 UTC, primary 79 distinct successes plus
  six early pilots = 85; four primary technical-failure rows remain retained.
  Primary seal preflight verifies 1301 artifact hashes, excludes pilots, and
  will refuse sealing before planned indices 7..127 are complete. Gold scoring
  has not run. Diagnostic helper changes do not alter the frozen main runtime.

- Separate stacked `agent/capture-client-boundary-20260910` branch adds
  fail-closed native client-area containment before/after screenshot capture.
  Proportional window-margin scaling can enter a fixed-height titlebar after
  a resize; no automatic ROI intersection/expansion is allowed. Ten regression
  failures reproduced first, then 98 capture/agent/ROI tests pass. Read-only
  native check against Viewer PID 26088 at 150% DPI accepted the current safe
  ROI and rejected all four one-pixel chrome crossings; no screenshot or model
  calls. Full unit/smoke/mock-integration regression: 1406 passed, 6 explicit
  opt-in/local-artifact skips (166.24 s); Ruff passes. Actual resize/DPI and
  model cases remain pending. See `docs/viewer-client-capture-boundary.md`.
- Crop-scope fix is pushed as draft stacked PR #15 (`e583a92`); CI 34487320267
  and Secret scans 34487320261 / 34487314337 pass. Candidate #13 is clean after
  isolated merge `8c3fb6e`; CI 34486122894 and Secret scan 34486038887 pass.

- Separate `agent/crop-provenance-20260910` worktree addresses unscoped crop
  notes observed in the real UI cohort. Crop notes/rationale now carry the
  orchestrator-owned normalized ROI bounds; original notes, diagnosis, bbox
  mapping, prompts and request count remain unchanged. Synthetic scope
  regression reproduced nine failures first; 149 scope/multi-pass tests pass
  after the fix. Full unit/smoke/mock-integration: 1393 passed, 6 explicit
  opt-in/local-artifact skips (171.93 s). Five initial native-plugin failures
  were ERR_MODULE_NOT_FOUND in the new worktree; installing the locked 9.3
  runtime under Node 24.18 resolved them without skips. Qt scope/wrapping and
  JSON export checks pass; a synthetic offscreen report was visually reviewed
  after explicitly loading Windows fonts (initial preview had missing glyphs).
  See `docs/crop-evidence-scope.md`. Separate candidate GUI/partial-ECG evidence
  remains pending; main cohort untouched, 80 distinct UI successes at 14:08 UTC.

- English/Traditional-Chinese READMEs, maintenance size charter and the upgrade
  audit now report the verified f184258 package/ZIP measurements, with explicit
  pending real candidate and distribution-license gates. The dated GUI progress
  note is 70 distinct successes at 13:43 UTC, not clinical passes. Historical
  pilot/failed-build evidence remains available rather than silently replaced.

- f184258 rebuild is now verified: static bundle checks pass; **19/19 actual
  frozen packaging smoke checks pass**, including random-port public connect,
  exact synthetic PNG at the loopback provider, four persistent workspace files,
  no Codex plugin load/command, and no residual Gateway listener/process. The
  previous failed candidate remains preserved separately. No real OAuth/model
  or clinical acceptance is implied. 52 compressed payloads pass `upx -t`.
  Local unit/smoke 1327 passed / 5 explicit skips plus 55 mock integration
  tests passed; CI 34483865336 passed (1379 / 8 platform/opt-in skips), Secret
  scan 34483602372 passed. All code/contract changes are on draft PR #13.
- Distribution ZIP benchmark on the verified f184258 tree: Deflate 1 gives
  154.44 MiB in 9.140 s; Deflate 9 gives **141.14 MiB in 23.529 s**. All 18,721
  decompressed entries match the source SHA-256, with no source mutation.
  Installed size remains 336.43 MiB; ZIP size is not an EXE/installed-size claim.
  Artifacts remain local; PyQt distribution-license decision, real candidate
  GUI/OAuth/clinical/rollback and image-edge gates remain open.
- The 24 redacted vendor-scan matches were verified byte-identical to the
  locked installed packages. Classified as JS symbols, translation/schema text,
  database record names, public OAuth client ids, WebSocket fixture values,
  and one upstream embedded TTS shared service constant. This is not a claim
  that upstream constants are risk-free, nor a binary/archive secret scan.

- Candidate fe0a612 full regression passed (1362 tests, 5 explicit skips).
  Its UPX build/verifier passed: 336.43 MiB total, 53.84 MiB App layer, 89
  approved native sources; 52 UPX-marked payloads pass integrity testing.
  **Actual packaged Gateway smoke failed**: the manager's configured port
  was not passed to `gateway run`, so the child attempted the occupied default
  port. It exited without stopping the ongoing cohort Gateway. Follow-up now
  pins public `--port` / `--bind loopback` and rejects invalid port types/ranges.
  Real source-App probe reached a local 401 image endpoint on the chosen port.
  It exposed two more smoke assumptions: public 9.3 error events sanitize the
  provider marker, and one-time BOOTSTRAP.md is not guaranteed in the App's
  pre-seeded workspace. Require the exact fixed-model public auth error, an
  accepted run id, four persistent workspace files, and independent exact-PNG
  provider proof; keep all five upstream templates packaged. Fresh EXE rerun
  remains pending. Unit/smoke regression: 1326 passed, 5 opt-in skips; final
  persistent-template adjustment separately passes 84 tests, 3 opt-in skips.
- Runtime Codex exclusion is now explicit `entries.codex.enabled=false` in
  managed Gateway config and after OAuth migration/settings cleanup. Real
  source-App startup confirmed no Codex plugin loading/command registration,
  while native harness loaded. Fabricated App OAuth import/reuse still passes
  (16.765/3.024 s); no real credentials or paid model requests in that probe.
- Full vendor text secret scan now removes Gitleaks' default node_modules
  path exclusion: 235.97 MB scanned vs the earlier 0.51 MB. It reported 24
  vendor findings requiring classification, not zero findings. Binary/archive
  coverage is not claimed; no new broad allowlist has been added.
- Main GUI cohort paused at case 64 when switching the docs merge checkout
  changed raw CRLF bytes. Read-only audit verified all 88 implementation files
  equal frozen 58af7a5 Git content after CRLF normalization. The affected
  receipt remains a failure; GUI rerun succeeded under a new raw fingerprint.
  Another pre-send Viewer stale-image guard stopped case 67; GUI driver now
  waits at most five seconds for a matching actual repaint, then boundedly
  reopens via QFileDialog. Identity threshold unchanged; no inference sent on
  the stale image. Do not switch the main worktree while this batch is active.
  66 distinct pilot/main UI successes observed before case 67 restart; clinical
  accuracy remains unevaluated. Public Pages PR #14 merged as 01c5c4d; deploy
  34481931670 and real Edge desktop/mobile QA passed, including menu focus.

- Candidate bfd7426 pushed as draft PR #13; CI 34478247522 and both Secret scans
  passed. Initial UPX build was deliberately stopped (owned PyInstaller process)
  after audit found 47 upstream notice files omitted by extension slimming.
  That interrupted build has no completed size. Fix restores 324 exact npm
  notices (562,442 B); refreshed slim stage is 280.77 MiB / 18,581 files.
  Python/runtime closure, bootloader, Python, Node and App add 21 notices;
  both inventories verify SHA-256 and safe paths. Node download now checks
  official SHA-256 and extracts only binary/LICENSE without recursive temp
  deletion. 106 targeted tests pass. Maintainer asked non-blockingly about
  PyQt GPL-compatible vs commercial distribution; do not change source license
  or publish binary before that decision and other release gates.
- Follow-up smoke exposed unavailable `Get-FileHash` in pytest-spawned Windows
  PowerShell; staging/downloader use streaming .NET SHA-256 instead. Real
  staging/bootstrap smoke now passes (2 tests, 113.60 s). Separate HTTP sidecar
  regression reproduced WinError 10053 on repeated unauthorized POSTs: unread
  request bodies caused early socket-close races. Rejection now discards only
  a known <=16 KiB body within a total one-second deadline, never parses it or
  invokes inference. Thirty real 401 exchanges plus bounded/chunked/invalid/
  trickling-body regressions pass (23 sidecar tests); fe0a612 full suite passed.

- Isolated candidate branch `agent/openclaw-2026-9-3-20260910` now pins core and
  OAuth-only migration provider 2026.9.3, with full npm lifecycle under portable
  Node 24.18.0 (335-package audit: zero matches). Slim staging: 280.62 MiB,
  18,533 files, five actual bootstrap templates, flat dependencies, no Codex
  binaries. Native bbox + fabricated OAuth probes pass against slim tree;
  actual App helper import/reuse passed in 8.440/2.739 s. Main cohort remains
  frozen, not switched to this candidate. New EXE and real auth gates pending.
- Initial managed Gateway/client port wiring passed unit tests, but did not
  propagate to the child CLI (see actual failure/fix above). Bundle smoke chooses a
  temporary port and supports `DICOM_TEST_BUNDLE`; it must not interfere with
  the ongoing real cohort. 120 targeted tests passed, 3 packaged opt-in skips.
- Candidate full non-GUI/non-slow regression: 1333 passed, 5 explicit local/
  packaged/rendered opt-in skips (168.79 s). Final migration self-check pin/flat
  Codex-ban regression separately passed with the auth module's 3 tests. Ruff
  passed. Fresh default 9.3 stage restored with no native-probe plugin residue;
  historical 7.1-2 stage preserved as `build/openclaw-runtime-baseline-7`.
- Synced the already-published PR #14 website into the isolated candidate;
  retained both the dated initial website evidence and subsequent package
  corrections. No checkout or source mutation in the running main cohort.

### Earlier PR #14 website checkpoint (superseded where updated above)

- Website upgrade copy now distinguishes the frozen 7.1-2 Astra GUI cohort
  from isolated 9.3 PR #13: slim native bbox/template/fabricated App-auth checks
  passed, real auth/clinical/package/license gates remain open. Candidate first
  CI 34478247522 green; later notice-preservation and bounded HTTP-rejection
  changes remain independently gated. No main runtime source changed here.
  Browser plugin unavailable; isolated Playwright/Edge passed at 1440x1000 and
  390x844, including actual candidate-callout screenshots, menu/Escape/focus,
  navigation, no horizontal overflow, no console warnings/errors. Both new
  screenshots visually inspected. Website smoke: 12 passed. Public deployment
  pending. Candidate fe0a612 full local suite separately passed 1362 / 5 skips.

- Package comparisons on clean UI repair source: no-UPX 337.77 MiB vs UPX 5.2.1
  241.29 MiB; existing frozen checks passed. TOC audit revealed ambient MiKTeX /
  TortoiseGit DLL sources, so these are not approved hermetic builds. New build
  wrapper isolates PATH and audits every native source. Isolated-PATH UPX rebuild
  passed with 84 approved native sources, 239.03 MiB total, 53.41 MiB App layer;
  compressed Node HTTPS smoke passed. Full regression 1305 passed, 4 opt-in skips.
  See `memory-bank/package-audit-2026-09-10.md` for evidence and release blockers.

- New binary-release blocker: pinned production npm lock audit reports 11
  affected package entries (7 high / 4 moderate); all exact versions are present
  in the freshly staged slim runtime. Candidate 2026.9.3 lock audit reports zero,
  not a safety guarantee. Old-pin build is size/function baseline only; no
  force-fix of the running cohort. SECURITY.md and the dated upgrade audit list
  the evidence and remaining migration/tool/real-App gates.
- Public Pages latest deployment `34472693765` on `242f7f4` passed actual Edge
  desktop/mobile URL, navigation, menu keyboard/focus, overflow and console QA.
  Native mobile screenshot inspected. No binary/clinical release is implied.

- Latest upstream candidate is **2026.9.3**. Isolated supported-Node probe
  negotiated protocol 4, sent a synthetic PNG through the existing public frame,
  verified exact image hash at a loopback fake provider, and received correlated
  final events. No paid model call. Public config validation accepted the App's
  generated Astra profile. Core measured 175.683 MiB; full raw dependency tree
  799.055 MiB includes 377.406 MiB of Codex runtime dependencies that must not ship.
  HEARTBEAT template relocation and migration-only staging remain concrete gates.
  See `docs/openclaw-upgrade-audit-2026-09-10.md`; active pin remains unchanged.
- UI repair is isolated in worktree `data/tmp/astra-ui-worktree-20260910`, branch
  `agent/astra-ui-report-20260910`, to preserve the running cohort fingerprint.
  It fixes clipped wrapped labels, improves text contrast/priority, preserves full
  review reasons behind a compact navigation alert, and clears stale warnings.
  Real native panel preview inspected; not merged or counted as a new model case.
- Public Pages deployment `34467904677` succeeded on `2fd0fec`; real Edge/
  Playwright checks passed on the public URL at 1440×1000 and 390×844, including
  navigation, mobile menu/Escape/focus, no overflow, and no console errors.
  The previous Qt-plugin failure is repaired. PR #6 workflow-marker changes
  passed CI and merged as `58af7a5`; full local suite 1293 passed, 4 skipped.
  No clinical/binary release or tag is claimed.
- The UI-only cohort now verifies the actual Viewer client screenshot against
  all 128 answer-free source thumbnails BEFORE Analyze, then separately verifies
  the exported ROI and every recorded model/effort receipt. File-dialog UIA
  races are boundedly retried before analysis; Analyze is never blindly retried.
  Source/clinical/workspace fingerprints must stay frozen during the batch.
- User now requests **GPT-6 Astra low only**; Luna high comparison is dropped.
  Exact model ID is `gpt-6-astra`, routed through OpenClaw's
  `openai-chatgpt-responses` subscription transport, not a Codex agent runtime.
- GUI settings were operated and photographed: Astra/low is now saved. A Qt
  list-item selection alone did not commit the combo box; actual pointer
  activation and re-reading the saved configuration confirmed the selection.
- Real desktop startup/normal Quit validated owned Gateway cleanup. The first
  Analyze attempt exposed stale migrated OAuth after native Codex rotation;
  importing a fingerprinted OAuth-only snapshot repairs this on next startup.
- Gateway receipt validation, exact process ownership, cancellation isolation,
  and multi-pass partial-crop evidence protections have targeted regression
  coverage (421 tests passed before the new subscription change).
- The September 2-3 historical GUI batch attempted 103 records: 60 exports and
  43 timeouts. Offline source-image matching identified the intended case in
  all 60 exports (maximum thumbnail MAE 0.39/255), and all 60 have Gateway
  receipts. These are NOT 100 completed cases, clinical passes, or an Astra
  result; reasoning effort was not recorded for that historical Luna batch.
- Broad title matching can latch onto the repository's VS Code window when no
  viewer exists. Current real-run config is manual and matches only
  `DICOM Harness Viewer`; general product target-selection hardening remains.
- GitHub secret scanning and push protection enabled September 10. A fully
  redacted Gitleaks history scan found one historical Gateway-token disclosure
  in commit `08581ba`; it is absent from current Memory Bank and differs from
  the active config. No history rewriting has been performed. Runtime migration,
  skill-workshop, and memory directories must remain private and untracked.

## 2026-08-28 live Luna / GUI / release acceptance in progress

- Current objective requires real Windows desktop evidence: launch the packaged
  app and OpenClaw agent, display a test image in a viewer, route image analysis
  through `openai/gpt-5.6-luna`, capture the rendered overlay/report, and record
  latency plus request/token usage. Mock/headless checks are supporting gates,
  not substitutes for this acceptance path.
- Work is staged as: preserve the existing dirty worktree; establish live GUI
  and model baseline; repair smoke/edge failures; validate speed/accuracy on an
  unseen bounded canary; audit and safely slim the bundle; finish GitHub Pages
  and bilingual docs; then make reviewed, path-scoped commits/pushes/releases.
- The 9,922-image paired experiment remains gated by the existing frozen-source
  rule: launch only after the scoped source is verified, committed, and pushed.
  It must remain resumable and must not be mixed with subsequent code changes.
- Existing unrelated changes in `.github/agents/research.agent.md`, Copilot hook
  policy/evaluators, `.claude/skills/pubmed-research-chronicle/`, and
  `openclaw-home/memory/main.sqlite*` are user-owned and excluded from this
  task's commits.
- The packaged GUI acceptance reached `DISPLAYING` against a real 1000 x 720
  credentialed local MEETI ECG shown in the harness viewer. The app captured the
  configured
  `(19, 30, 1522, 1136)` physical-pixel viewer ROI on a 2560 x 1600 display at
  150% Windows scaling, sent
  five OpenClaw-owned `openai-chatgpt-responses` image turns to
  `gpt-5.6-luna`, and exported a review with four diagnostic boxes plus two
  analysis-crop outlines. Capture exclusion correctly kept the top-most app
  panels black to external Windows capture; the app-owned Export action is the
  inspectable evidence path.
- The live run took 146.915 s and recorded 50,607 input, 4,906 output, 56,320
  cache-read, 1,970 reasoning, and 111,833 total tokens. Subscription transport
  reported zero metered API cost; at the documented Luna token prices the same
  traffic is approximately USD 0.017135. Every exported projection was in
  bounds with no clamping and 0.104-0.368 physical-pixel maximum edge drift.
- This live case is a correctness failure, not a success claim. Gold describes
  atrial fibrillation with slow ventricular response, prolonged QT, poor R-wave
  progression and nonspecific inferior ST-T changes; the GUI instead reported
  sinus rhythm and possible LVH. The bounded unseen canary and prompt/harness
  changes must address this miss before any clinical-accuracy statement.
- A subsequent answer-free two-case canary (seed 20260828, 1,222-ID denylist)
  passed schema, bbox and every SLA with zero JSON repair. It scored 1/2 strict,
  0.522 mean partial, and 1.0 normal specificity; the warning case showed poor
  R-wave progression/prominent anterior T waves but missed weak-label LVH and
  asserted sinus rhythm. Usage was 167,102 total tokens and about USD 0.02972464
  API-equivalent on the subscription route. Its source fingerprint was dirty
  during release metadata synchronization, so it is pre-release evidence only.
- The first clean-source frozen canary (seed 20260829, 1,224-ID denylist) also
  failed the release gate: strict 0/2, mean partial 0.456 and normal specificity
  0.0 despite 2/2 schema, bbox and SLA passes. The normal case had a false
  poor-R-progression call; the warning case missed asserted sinus and ST-T/T-wave
  changes. One successful parse-retry refinement also lost its already-written
  bbox receipt from the captured trace, so the artifact verifier correctly
  rejected the run. This remains negative evidence, not a release result.
- The post-canary repair keeps the same turn budget. Every trusted precordial
  crop now receives a hypothesis-independent V1-V4 R/S-transition and V2-V4
  ST-T/T-wave review; V1/V2 deep S alone cannot establish poor progression and
  V3/V4 R dominance requires retraction. Native bbox audit reads preserve
  partial JSONL records, wait at most 0.5 s for Windows append visibility, and
  include `confirm` coordinates in exact receipt matching. A fresh blind canary
  is required after committing these changes.
- The first explicitly exposed two-case regression on that repair completed
  with zero errors, zero JSON repair, all refinement/final receipts present and
  every 60/100/180 SLA met. The former normal false positive became a strict
  normal pass, so specificity recovered to 1.0; aggregate strict/partial moved
  to 0.5/0.569 at 103.381 s mean latency. The warning case recovered sinus and
  retracted poor progression, but still missed reproducible nonspecific ST-T/
  T-wave change. Because these cases are revealed, the result is development
  regression evidence only.
- The next prompt revision separates acute ischemic morphology from nonspecific
  repolarization: absent ST elevation/reciprocal change cannot erase a pattern
  that repeats across adjacent beats in at least two mapped related leads;
  isolated one-lead variation or non-reproducible noise still stays normal. It
  adds no turn and needs one more exposed check before the fresh blind canary.
- Real packaging/runtime failures found by the acceptance path are now explicit
  gates: the staged OpenClaw runtime omitted required agent templates; a stale
  Gateway lock could survive forced shutdown; the GUI quit path hung; and final
  reconciliation changed one draft bbox coordinate before its receipt check,
  causing a safe incomplete fallback after the retry deadline. The local export
  and trajectories remain ignored/generated evidence and contain no secrets.
- The release default remains `openai/gpt-5.4-mini`. The live Luna evidence used
  an explicit `openai-codex` model override to `openai/gpt-5.6-luna`; OAuth
  migration did not transfer the image-analysis loop away from OpenClaw.
- Core 2 now requires a non-empty image and exact 16-key result on the correlated
  frame, and overlay geometry rejects non-finite, zero-area, and fully off-image
  boxes. Gateway recovery is acceptance-aware and charge-safe, never terminates
  an unknown PID, and closes boundedly. The 10,001-identity scale gate verifies
  resumable set partition and fingerprint rejection without claiming a
  10,001-image clinical run.
- Product metadata is v0.4.7 and harness/plugin metadata is 1.5.8; OpenClaw
  remains pinned at 2026.7.1-2. Staging now retains and hashes seven required
  upstream templates. The staged OpenClaw runtime is verified at 165.162 MiB,
  a conservative 19.804 MiB reduction that does not prune internal `dist`
  chunks. The final full bundle size/hash and post-fix frozen unseen canary
  remain pending.
- The rebuilt GitHub Pages source is synthetic-only and exposes the real
  engineering evidence plus the accuracy miss. It must reach `main` before the
  public Pages deployment changes; tagging the feature branch alone will not
  deploy it.

> Current state is the 2026-09-10 section above. Earlier dated session updates
> are historical snapshots and intentionally retain their then-valid blockers,
> versions and run states.

## Session Update (2026-08-05, evidence-v3 and GPT-5.4 Mini release default)

- The release default is `openai/gpt-5.4-mini` through the `openai-vision`
  Responses profile; Luna remains explicitly selectable. The four experiment
  arms are one-look `minimal_control`, clinical `single_pass`, `multipass`, and
  `multipass_ecgfounder`. Real completion requires strict pass >=0.75 and mean
  partial credit >=0.85; incompatible protocols fail closed.
- The clean-source `manifest-v2.json` mock MultiPass artifact is
  `data/eval/meeti-v2-1000-mock-multipass-evidencev3-20260805`, protocol
  `9408a142...dd4`. It completed 1,000/1,000, 4,869 analyzer calls, 2,869 source
  crops, 2,000 systematic probes, and 1,000 review PNGs. All 865 bbox rows pass
  with zero clamp/invalid/low-signal and 0 px drift. The 1.0 mock scores remain
  protocol self-test evidence, not model accuracy.
- Formal score denominators are asserted references only: 299 clinical cases,
  244 diagnosis-scorable, 49 explicit-normal controls, and 32 urgent concerns.
  The remaining 701 weak-label cases are exploratory and no abnormal finding is
  forced for normal/within-range ECGs.
- The current real GPT-5.4 Mini canary reached an image-capable OpenAI Responses
  transaction after a 72.359-second Gateway start, then returned
  `provider_credit_exhausted`. It is `blocked`, contains zero model answers, and
  cannot establish four-arm accuracy or significant improvement.
- The pinned ECGFounder v3 batch traversed 1,000 waveforms in 555.086 seconds:
  999 eligible and one exact-flat V5 exclusion. Eligibility-aware 5-fold
  research metrics are macro BA 0.865, sensitivity 0.847, explicit-normal
  specificity 0.883, and 3-5 diagnosis complete recall 0.479. The tool stays
  uncalibrated supporting evidence and supplies no screenshot bbox.
- Verification passes Ruff, mypy for 63 source files, unit+smoke 791 passed with
  3 opt-in skips, OpenClaw integration 55 passed, and the opt-in native Windows
  rendered capture-exclusion smoke. The fresh frozen bundle from `1d73a9c` is
  manifest `ok`: 363.94 MiB / 15,226 files, OpenClaw `2026.7.1-2`, Node
  `v24.18.0`, EXE SHA-256 `444b99d4...a24d`, and release-only smoke 4/4. Frozen
  PYZ contains the GPT-5.4 Mini defaults; plugin 1.2.0 source/bundle hashes match
  and both native tools load. No `.env`, SQLite, Torch, checkpoint, MEETI,
  waveform, sidecar, banned component, runtime residue, or failure was bundled.

## Session Update (2026-08-04, regional/ECGFounder audit hardening)

- Published analysis state is now one immutable `ReviewSnapshot`: image bytes,
  result, capture rectangle, and revision become visible atomically only after a
  successful analysis. Export, image QA, regional review, and writeback all read
  that snapshot; writeback is rejected outside `DISPLAYING` or after revision
  drift. Apply executes on `AsyncBridge`, not the Qt thread.
- Regional QA audits the original source-pixel crop. When MultiPass is enabled,
  it runs a bounded refine turn before the JSON-only proposal turn and records
  both OpenClaw sessions/runs/tools/receipts. Missing, failed, or low-signal
  audit blocks every `ADD`, `REVISE`, and `RETRACT`. Exact finding ids survive
  the canvas click path; duplicate ids fail closed; single-crop edits cannot
  rewrite multi-box or multi-static-region findings; unprocessed manual regions
  survive rerender.
- Image follow-ups now use unique OpenClaw sessions and accept tool events only
  after response/run correlation. Applied, dismissed, blocked, and no-change
  regional turns all persist in `analysis_trace`. Manual-mode image changes
  invalidate the old snapshot immediately, and edge crops clamp to real source
  pixels instead of padding blank space outside the ROI.
- ECGFounder evaluation now accepts only 12-lead input and exact official model
  revision/checkpoint provenance. Each case has a random evidence nonce; exactly
  one matching `status=ok` receipt is required, transport failures leave an
  audit row, and invalid evidence becomes an infrastructure failure. Desktop
  Settings explicitly says evaluation-only because no trusted desktop
  study-to-waveform resolver exists yet.
- Sidecar deep health verifies model readiness; per-lead finite/flat/clipping
  gates run before preprocessing. The portable bundle verifier now bans Torch,
  sidecar/MEETI paths, waveform/model suffixes, and includes the upstream MIT
  notice without bundling checkpoint or waveform data.
- Current source verification: Ruff passed; unit+smoke `741 passed, 1 skipped`;
  OpenClaw integration `55 passed`; frozen bundle smoke `2 passed`.
- Final portable rebuild from `bffd6c5` is manifest `ok`: 15,226 payload files,
  363.91 MiB, OpenClaw `2026.7.1-2`, Node `v24.18.0`, EXE SHA-256
  `0097097DECA61313FBF39EC48508520841CD47653FBED035B2713A82D20FE274`.
  Two consecutive verifier runs had identical payload statistics and left no
  `.log` or `openclaw-home`; source and bundled native plugin hashes match.
- An isolated full GUI launch remained responding after 12 seconds and started
  the bundled Node/OpenClaw gateway. The pinned/latest OpenClaw production tree
  still has 7 moderate / 4 high / 0 critical transitive npm advisories; the
  non-breaking audit-fix dry run proposed zero changes.

## Session Update (2026-08-04, reviewer-confirmed regional writeback)

- AI boxes and reviewer-drawn regions now send the exact app-owned crop through
  a separate JSON-only OpenClaw follow-up. The model can propose `ADD`, `REVISE`,
  or `RETRACT`, but cannot supply coordinates or mutate the report; an explicit
  Apply click is required.
- `AnnotationAccumulator` is now wired into `OverlayAgent`. Accepted changes
  retain `interactive_ai_review` provenance in the report, Process trace, JSON,
  and annotated PNG. Same-label plus IoU is required for geometric dedup, so
  distinct diagnoses sharing one region are no longer merged.
- Writeback fails closed on stale result revisions, late same-image chat request
  ids, missing targets, id collisions, malformed/out-of-ROI boxes, normal
  add/revise proposals, and missing/error/low-signal crop receipts. The local
  signal gate checks blank fields, ink/bright pixels, edge density, entropy, and
  robust dynamic range; QA/manual export remains available when signal is low,
  but no report-changing action is allowed.
- Chat expiry is independent from the report/markers, model/user text renders as
  plain text, and promoting a manual region consumes that region to avoid a
  duplicate export marker. Native Qt and annotated-PNG visual probes were
  inspected at production dimensions.
- Superseded source verification: full Ruff passed; OOM-safe unit+smoke was 706
  passed plus one release-only skip; OpenClaw integration is 55/55. A fresh
  Windows bundle rebuild and its final hash are still pending in this session.

## Session Update (2026-08-04, Luna default + ECGFounder held-out audit)

- Desktop, fresh Gateway config, and both experiment runners now default to
  `openai/gpt-5.6-luna`; the bundled Node `v24.18.0` validated the config and
  exposed Luna as `text+image` with a 1.05M context. GPT-5.4 Mini and other API
  profiles remain selectable. Settings now reads the active model instead of
  showing an unrelated first preset.
- A true one-image Luna MultiPass canary reached OpenAI Responses and was
  retained as `blocked` after `credit_balance_exhausted`. No model answer or
  accuracy score was manufactured. The full three-arm image experiment remains
  externally blocked.
- Found and fixed Windows stale Gateway-lock recovery: `os.kill(pid, 0)` could
  report a terminated PID as live. Shared Win32 `OpenProcess/GetExitCodeProcess`
  logic now protects both desktop and Python experiment runner, with a reaped
  child-process regression test.
- ECGFounder offline batching can retain all 150 class scores while the live
  OpenClaw tool stays capped at 20. Batch v3 records runner hash plus affirmative,
  uncertain, and ungradable label metadata; evaluator accepts the completed v2
  run with verified protocol fingerprint.
- Full 150-score inference completed 1,000/1,000 in 605.847 s. The leakage-aware
  five-fold audit (`0384ed02...d40a`) maps 33/38 observed concepts and 99.157%
  of asserted instances. For 23 supported concepts: macro BA 0.865, sensitivity
  0.848, explicit-normal-control specificity 0.883. Holdout top-20 recall is
  0.837; 3-5 diagnosis complete recall is only 0.479, below the 0.75 target.
- UI now shows secret-free waveform-assist configuration and records ECGFounder
  status, prediction count, and calibration state in the Process tab. OOM-safe
  unit+smoke is 680 passed plus one release-only skip; integration is 55/55.
- Fresh portable bundle is manifest `ok`, frozen smoke 2/2, 15,225 files and
  363.87 MiB with OpenClaw `2026.7.1-2` and Node `v24.18.0`. EXE SHA-256 is
  `3FFE577B3562965E34360BC765811F150BDA594AFA4E5BA7147E8575A4320D48`.
  Frozen PYZ inspection proves the Luna defaults are present; sensitive/external
  model filename scan found zero `.env`, Torch/checkpoint, MEETI, waveform,
  SQLite, or sidecar artifacts.

## Session Update (2026-08-04, systematic harness + GPT-5.4 Mini + final bundle)

- MultiPass now reserves bounded original-ROI EKG discovery turns for limb and
  precordial regions, even when the coarse model emits no bbox. Trace artifacts
  record planned/completed probe ids, crop source, tool receipts, and protocol
  data; the production artifact gate rejects a MultiPass EKG run without both
  completed probes. Current mock protocol digest is
  `3083822c30d5e5c3f9efb36303b74edc595fd8c9001a81b8346293d812e887a0`.
- Partial-credit aggregation now uses component-specific denominators and the
  comparison report includes safety deltas plus paired sign tests. The current
  six-case guardrail replay improves recorded MultiPass partial credit
  0.596->0.678 and urgent recall 0/2->1/2, but n=6 and p=1.0 do not establish
  significance. Raw model JSON is never mutated.
- `openai-vision` now registers `openai/gpt-5.4-mini` as `text+image` over the
  Responses API (400k context); Luna remains `openai-luna`. The transactional
  canary reached a ready Gateway in 16.078 s, attached one MEETI image
  (`promptImages=1`), and reached `/v1/responses`, then stopped on provider
  `credit_balance_exhausted` / `insufficient_quota`. Static readiness explicitly
  says `provider_transaction_tested=false`.
- Final verification: full Ruff passed; OOM-safe unit+smoke is 666 passed with
  one release-only skip; OpenClaw integration is 55/55; frozen bundle smoke is
  2/2. Fresh EXE SHA-256 is
  `B3066A365EB72F705EC49F4EFFB3E2B93A1C32D52BA218EB0C531F03F3B0B8D8`.
- The 363.86 MiB bundle contains OpenClaw `2026.7.1-2`, Node `v24.18.0`, 51
  skills, and runtime-loaded bbox/ECGFounder tools. Staging strips `.env*`, and
  recursive scans found no environment file, Torch, checkpoint, MEETI,
  waveform, sidecar, or experiment database content.

## Session Update (2026-08-04, coordinate-safe desktop + Pages + rebuild)

- Fixed a real primary-screen-only defect across the capture-to-overlay path.
  `ScreenMonitor` now resolves a physical `DisplayFrame`; `OverlayAgent` syncs
  the viewer display and saves the exact successful `last_capture_rect`;
  `OverlayCoordinateFrame` maps physical edges into target-screen Qt-local
  coordinates with independent X/Y ratios and negative-origin support.
- ROI setup, AI bbox projection, static region fallback, top-level report/chat
  placement, click QA, and manual annotation now share that display frame.
  `Severity.INFO` bboxes are intentionally drawn for uncertainty review.
- Focused tests passed 87/87. The then-current OOM-safe suite was 647 passed with
  one release-only bundle skip; OpenClaw overlay integration was 54/54. A real Qt +
  Win32 probe found a `1222x836` window and an exactly matching `1222x836` mss
  capture on the current 150% display.
- Added a synthetic-only GitHub Pages site under `site/` and a current official
  Pages workflow. Playwright passed at 1440x900 and 390x844 with no overflow,
  missing media, or console errors; mobile menu and evidence navigation work.
- Rebuilt the portable app after the coordinate fix. Superseded SHA-256:
  `C44DA431AA5D1BFC72D943B3835BFC6A403BD426B483F9661B5FA17266383F66`.
  Bundle verifier status is `ok`; OpenClaw `2026.7.1-2`, Node `v24.18.0`, 51
  skills, total 363.86 MiB. Real frozen-EXE opt-in smoke passed 2/2.
- The bundle includes no Torch, ECGFounder checkpoint/runtime, MEETI assets,
  secrets, or sidecar. npm audit debt remains 7 moderate / 4 high / 0 critical.
- Current Windows 11 build is verified. Windows 10 needs clean-machine testing;
  Windows 7 is not credibly supported by Python 3.13/PyQt6/Node 24/OpenClaw.
- Full new `openai/gpt-5.4-mini` three-arm MLLM accuracy comparison remains
  blocked by `credit_balance_exhausted` / `insufficient_quota`; do not claim an
  accuracy gain from the completed waveform-only arm.

## Session Update (2026-08-04, ECGFounder paired waveform arm)

- ECGFounder is now implemented as an optional OpenClaw native tool backed by a
  bearer-authenticated loopback sidecar. The agent receives only an opaque
  waveform artifact id and sanitized evidence; it cannot send paths, use a PNG
  as waveform input, or derive image bboxes from the model.
- The full MEETI archive contains matching raw MATLAB waveforms. The rebuilt
  `data/eval-datasets/meeti-1000-all` cohort has 1,000 images, 1,000 exact
  12x5000/500 Hz/10 s waveforms, and a hash-protected one-to-one registry.
- The official 12-lead checkpoint was downloaded and verified at SHA-256
  `ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997`.
  Loading is `weights_only=True`; the temporary Torch safe-global allowlist is
  cleared after load and there is no unsafe pickle fallback.
- Real standalone inference completed 1,000/1,000 cases at
  `data/eval-runs/ecgfounder-meeti-1000-20260804`: zero failures, 691.182 s,
  median 756.491 ms, p95 794.734 ms, protocol fingerprint
  `2b79fb8caffed0eabe1467fa3aba4c5a8287e753d7dcdcae1fa308fc7ca2d933`.
  Every score remains explicitly uncalibrated.
- A real Node/OpenClaw plugin -> HTTP sidecar -> Torch checkpoint smoke passed
  and wrote a PHI-free tool receipt. One urgent canary disagreed strongly
  (image/reference ST concern vs waveform model `NORMAL SINUS RHYTHM` 0.9992),
  proving the sidecar must stay supporting evidence rather than an override.
- `run-eval.py --ecgfounder-waveform-evidence` binds the exact artifact only in
  an explicit paired arm. The intended comparison remains single-pass image vs
  MultiPass crop/refine vs MultiPass + ECGFounder.
- A new full OpenClaw `openai/gpt-5.4-mini` paired run is currently blocked by
  the configured OpenAI account's `credit_balance_exhausted` /
  `insufficient_quota` response. This is an external experiment blocker, not a
  model miss; the waveform-only 1,000-case run is complete.
- Final verification: the OOM-safe suite completed 636 passed / 1 default
  bundle-smoke skip; the opt-in real EXE bundle smoke passed 2/2. The rebuilt
  `dist/DICOMOverlayAgent/DICOMOverlayAgent.exe` passed packaged self-check and
  runtime plugin inspection with OpenClaw `2026.7.1-2` and Node `v24.18.0`.
  Total bundle size is 363.86 MiB; Torch/checkpoint/sidecar/MEETI assets are
  confirmed absent and remain separately installed optional evidence tooling.
- Residual packaging risk: `npm audit --omit=dev` reports 11 advisories in the
  pinned OpenClaw production tree (7 moderate, 4 high, 0 critical). No
  `audit fix --force` was applied because that would silently diverge from the
  tested `2026.7.1-2` lock; address in a separate dependency-upgrade cycle.

## Session Update (2026-07-05)

- **Real-model path proven**: `api.openai.com` is reachable on this network
  (OpenRouter / Anthropic are firewall-reset), `OPENAI_API_KEY` is valid, and a
  MEETI single-case real run with `openai/gpt-5.5` + `openai-vision` profile
  passed (strict 1.0, schema/bbox 1.0). Runner default model fixed to
  `openai/gpt-5.5` (the `-mini` id is absent from the OpenAI catalog).
- **Harness increment 1 — lead-aware EKG (general)**: `dicom-ekg-analysis`
  SKILL.md now runs a Step 0 lead-localization ("declare, don't assume": read
  printed lead labels, inventory only visible leads, mark unlabeled "unknown")
  and lead-conditioned gating (no STEMI territory / axis / R-progression /
  chamber claims the captured leads cannot support). Optional additive `layout`
  block; 16-key checklist contract unchanged.
- **Harness increment 2 — scorer robustness**: `eval_harness` adds
  `_normalize_lexical` (hyphen/underscore/slash folding) and an expanded
  clinical-synonym alias table so correct reads phrased as abbreviations
  (RBBB, afib, LVH, PVC…) or hyphen/plural variants count; ambiguous bare
  abbreviations (LAD/RAD) excluded; negation still honored.
- **Mining verdict (25-case real gpt-5.5)**: scorer false-negatives are real
  but small (keyword_recall 0.531→0.55, strict 0.24→0.28 on free re-score);
  ~72% of failures are genuine misses (PR/AV-block/BBB/rhythm) or noisy/
  aggregated MEETI ground-truth labels. Next levers: lead-aware rhythm-strip
  second-pass crop, empty-summary retry (8% hard-fail), severity calibration,
  and manifest GT de-duplication. New `scripts/analyze-eval-failures.py`
  (OOM-safe) aggregates failure modes per run.
- **Levers 1+2 implemented (2026-07-05)**: empty-summary retry
  (`run-eval` re-sends once on a blank read) and a general rhythm-strip second
  pass (`application/rhythm_strip.py` crops the model-declared
  `layout.rhythm_strip_bbox` and re-reads it, escalate-only merge). Remaining
  levers: severity calibration and manifest GT de-duplication.

## Current Eval Harness Focus (2026-07-02)

- Active goal: keep the local desktop OpenClaw co-reading app up to date,
  configurable for OpenRouter, clinically useful for image-assisted
  recognition/report/bbox review, and backed by a production-scale harness with
  at least 1000 verified images.
- Local OpenClaw runtime is updated and validated at `2026.6.11`; the app still
  uses only the stable public Gateway boundary (`connect` + `chat.send`,
  protocol 3 image attachments). `MIN_SAFE_OPENCLAW_VERSION` remains
  `2026.4.22` because no verified Gateway incompatibility was found.
- The desktop Settings dialog exposes AI Provider profiles including OpenRouter
  (`OPENROUTER_API_KEY`, `https://openrouter.ai/api/v1`) with MiniMax M3 as the
  default OpenRouter model (`openrouter/minimax/minimax-m3`). Saving a profile
  writes only app-managed provider/model config and keeps secrets in env/.env.
  Both the normal OpenClaw config and generated OpenRouter experiment configs
  validated with the OpenClaw CLI.
- MEETI source: local `MEETI.rar` from Zenodo record `18523205` is available but
  gitignored. The builder can scan the full archive via Windows `tar`/`bsdtar`;
  current local scan found 9922 PNG-bearing studies.
- Production artifact gate: `data\eval-datasets\meeti-1000-all\manifest.json`
  was built with 1000 cases from the full MEETI archive. The mock strict eval at
  `data\eval\meeti-1000-mock-20260630-assist` completed 1000/1000 cases and
  `scripts\verify-eval-artifacts.py --min-cases 1000` passed:
  `min_cases`, `scorecard_complete`, `schema_gate`, `bbox_gate`,
  `cant_miss_gate`, `mock_perfect_gate`, `results_artifacts`,
  `local_preflight_artifacts`, `model_assist_artifacts`, and `review_artifacts`.
- OOM fix verification: `data\eval\meeti-1000-mock-oomfix-20260702` reran the
  1000-case MEETI mock gate after partial-scorecard throttling, exported 1000
  review images, and passed `scripts\verify-eval-artifacts.py --min-cases 1000`
  including `local_preflight_artifacts`, `model_assist_artifacts`, and
  `review_artifacts`.
- Large eval runs no longer rewrite the full `scorecard.partial.json` after
  every image. `run-eval.py` and `run_evaluation()` now refresh partial
  scorecards every 50 cases by default, always writing final/abort checkpoints;
  `--partial-scorecard-interval 0` writes only final/abort checkpoints.
- Non-MLLM/model-assisted layers: `ImageProcessor.image_quality_profile()`
  records deterministic `local_image_quality` per eval result (size, aspect
  ratio, ink density, bright-pixel ratio, low-signal flag), and
  `ImageProcessor.local_signal_candidates()` records deterministic
  `local_signal_candidates` waveform/signal bbox proposals. These make
  blank/unreadable input detection and first-pass candidate boxes auditable
  without forcing every quality decision through an MLLM. In multi-pass eval,
  those local candidates now feed crop re-analysis when the coarse MLLM result
  is non-normal but lacks usable bboxes. `multipass-trace.jsonl` records
  `local_candidate_count` and normalized `local_candidate_regions` per case, so
  1000-case runs can audit how often local assist was available for crop
  re-analysis. `verify_eval_artifacts()` now validates these fields when the
  trace exists and reports `multipass_trace_artifacts`; production multi-pass
  runs can pass `--require-multipass-trace` to fail if the trace is missing.
- Expert-review export now audits no-bbox cases at case level, so 1000-case
  review completeness is not inflated by bbox count alone. Review artifacts
  include PNG overlays, `bbox-audit.jsonl`, crop thumbnails, and `index.html`.
- Console-output hygiene: `run-eval.py` now bounds default per-case printing with
  `--case-print-limit 50`; use `--verbose` only for small diagnostic subsets.
  Avoid raw `tar -tf MEETI.rar` and broad recursive searches over generated data
  or OpenClaw internals in normal PowerShell sessions.
- OOM-safe test entry point: `scripts\run-tests-safe.cmd` runs unit+smoke with
  the existing uv-managed `.venv\Scripts\python.exe`, `TMP`/`TEMP=data\tmp\pytest-safe`,
  pytest `--basetemp`, and `-p no:cacheprovider`. Pytest defaults now collect only
  `tests/unit` and `tests/smoke`, exclude generated/vendored trees, and suppress
  captured-output dumps on failure. Prefer the `.cmd` path over PowerShell after
  the 2026-07-02 PowerShell OOM report. The `.cmd` runner now delegates to
  `scripts\run_pytest_safe.py`, so default/pure-option runs such as
  `scripts\run-tests-safe.cmd -q` execute each `test_*.py` file in a separate
  short-lived pytest process instead of one long-lived session. Directory
  targets such as `tests\unit -q` and multiple explicit test files also expand
  into per-file batches after the follow-up OOM report; a single explicit target
  such as `tests\unit\test_agent.py -q` stays targeted. Set
  `DICOM_OVERLAY_TEST_SINGLE_SESSION=1` only for deliberate diagnostics of the
  old one-session behavior. It also takes
  `data\tmp\pytest-run.lock`; concurrent pytest runners exit 75 instead of
  spawning another Python test process. It now also sets
  `DICOM_OVERLAY_TEST_DISABLE_REAL_OPENCLAW=1`, so unit/smoke tests cannot
  accidentally start a real OpenClaw Gateway unless a deliberate integration
  run opts in with `DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS=1`.
- OOM-safe lint entry point: `scripts\run-ruff-safe.cmd check ...` calls
  `.venv\Scripts\ruff.exe` directly and takes `data\tmp\ruff-run.lock`. This
  avoids `uv run ruff ...` after naked uv tried to initialize the user AppData
  cache and failed with access denied.
- OpenClaw/conhost OOM guard: `GatewayManager.start()` now holds
  `data\tmp\openclaw-gateway.lock` while its OpenClaw subprocess is alive and
  refuses a second live launch. `scripts\test-real-stack.bat` no longer starts
  the Gateway through `cmd /k`; it uses `start /B` with `gateway.log` redirection
  to avoid stray interactive `conhost.exe` windows. The MEETI real-experiment
  Python runner also takes the same Gateway lock before spawning OpenClaw, so
  GUI/manual runs and experiment runs cannot silently multi-launch Gateway.
- Fresh checks on 2026-07-02: npm latest reports OpenClaw `2026.6.11`, local
  runtime is `2026.6.11`, 1000-case assist verifier passed, targeted
  unit/smoke tests for the local assist gate passed, and
  `scripts\run-tests-safe.cmd -q` completed all 38 per-file batches without OOM.
  The 1000-case mock artifact verifier still passes without the optional
  multi-pass trace requirement, while the same artifact correctly fails with
  `--require-multipass-trace` because it has no `multipass-trace.jsonl`.
- Real-model 1000-case accuracy gate is still external-network/provider gated.
  `scripts\check-real-model-readiness.cmd --dotenv .env` now merges repo-local
  `.env` values into readiness checks without printing or serializing secrets
  while using `.venv\Scripts\python.exe` and `data\tmp\readiness-run.lock`;
  `--probe-provider`
  additionally checks provider egress and advertised image-input support before
  a Gateway run. Offline OpenRouter MiniMax M3
  readiness is `ready`:
  `data\experiments\real-model-readiness-20260702-openrouter-minimax-m3.json`
  sees `OPENROUTER_API_KEY`, the 1000-case manifest, OpenClaw `2026.6.11`, and
  completed mock artifacts. Provider-probed readiness is blocked:
  `data\experiments\real-model-readiness-20260702-openrouter-minimax-m3-probed.json`
  and
  `data\experiments\real-model-readiness-20260702-openrouter-minimax-m3-cmd-probed.json`
  see WinError 10054 while fetching OpenRouter metadata. Real Gateway smoke is
  still blocked by local egress: OpenClaw logs `ECONNRESET` while fetching
  OpenRouter model capabilities/pricing and calling `minimax/minimax-m3`.
  Latest OOM-safe probed readiness artifact
  `data\experiments\real-model-readiness-20260702-openrouter-minimax-m3-current-probed.json`
  still blocks before Gateway startup with provider key present, 1000-case mock
  artifacts OK, OpenClaw `2026.6.11`, and OpenRouter probe failing with
  WinError 10013 socket permission denial.
- `scripts\run-meeti-openclaw-experiment.cmd` is the preferred non-PowerShell
  launcher. It uses `.venv\Scripts\python.exe`, takes
  `data\tmp\meeti-run.lock`, then calls
  `scripts\run-meeti-openclaw-experiment.py`, which generates an
  experiment-local OpenClaw config before model-catalog checks, takes
  `data\tmp\openclaw-gateway.lock` before Gateway spawn, retries eval while the
  Gateway is still starting, exports review artifacts, and treats
  `scorecard.json.error_count > 0` as a failed experiment even when `run-eval.py`
  exits 0. It now also runs `scripts\verify-eval-artifacts.py` after review
  export; bounded smoke runs use `--limit` as the verifier minimum, full runs
  default to 1000 cases, and `--multi-pass` automatically adds
  `--require-multipass-trace`. Readiness next commands now point to this `.cmd`
  wrapper, not PowerShell.
- OpenClaw-side specialization can be developed as the existing
  `dicom-overlay-agent-harness` plugin/skill bundle. The manifest now advertises
  bbox crop re-analysis, coordinate drift calibration, and overlay annotation
  capabilities, while the desktop app remains Gateway-only (`connect` /
  `chat.send`) to avoid coupling to private OpenClaw plugin SDK internals.
- Overlay bbox drawing now goes through
  `infrastructure.overlay_geometry.project_bbox_to_overlay_highlight()`, which
  clamps overflow extents, uses edge rounding across DPR conversions, and
  records round-trip drift calibration evidence before drawing the highlight.
  The desktop AI bbox path now uses
  `infrastructure.overlay_highlight_builder.build_ai_bbox_highlights()` to emit
  PHI-free audit rows for every attempted AI bbox and withhold dynamic boxes
  whose round-trip drift calibration fails.
- `OpenClawClient` disables client-side WebSocket keepalive pings and relies on
  explicit inference timeouts for long medical-image requests. This prevented
  false keepalive closure from hiding the real current blocker, which is local
  model-provider network egress.
- Latest real 1-case evidence:
  `data\experiments\meeti-openrouter-minimax-m3-1case-resume-20260702`
  reached Gateway `connect` + `chat.send` with `openrouter/minimax/minimax-m3`
  and produced scorecard/raw/review artifacts, but ended
  `completed_with_failures` with `eval_error_count=1` due `LLM request failed:
  network connection error` from OpenRouter transport `ECONNRESET`.
- Updated clinical-usability objective: after the OOM-safe runner work, extend
  the overlay/harness path from initial whole-ROI agent triage to per-bbox crop
  re-analysis, then auto-correct returned crop-local bboxes back onto the
  overlay coordinate frame so screen/DPI/transform drift is detectable before a
  physician sees a misplaced box.

## Current Eval Harness Focus (2026-05-30)

- Current user-directed run: full MEETI `openai/gpt-5.4-mini` strict MultiPass
  experiment is running under
  `data\experiments\meeti-full-multipass-20260530-221551-openai_gpt-5.4-mini`.
  It uses `-MultiPass -MultiPassMaxTargets 2 -RequirePerfect`; progress is
  observable via `eval\multipass-trace.jsonl`, raw `eval\results\*.json`,
  rebuilt partial scorecards, review PNGs, and Gateway/eval logs. This process
  was started before the newest checkpoint/postprocess wrapper changes, so it
  will not itself write `experiment.json` or `scorecard.partial.json` until a
  future run uses the updated wrapper.
- MultiPass eval is now testable from `scripts\run-eval.py` with
  `--multi-pass --multi-pass-max-targets N`. The harness wraps the real
  `MultiPassAnalyzer` and records per-image `openclaw_analyze_calls`,
  `zoom_passes`, and `crop_calls` in `multipass-trace.jsonl`.
- Scorecards now include clinical partial-credit scoring, strict pass rate, and
  per-target-axis performance. Partial credit weights are 30% abnormal-vs-normal
  severity, 20% exact severity, 35% positive keyword recall, and 15%
  pertinent-negative recall, but the negative component only counts when the
  case has expected negatives, and missed can't-miss labels cap partial credit
  at 0.40. Schema/bbox/cost/safety metrics remain separate.
- Paired baseline-vs-MultiPass comparison is available via
  `uv run python scripts\compare-eval-runs.py --baseline <single-pass experiment-or-eval> --candidate <multipass experiment-or-eval>`.
  It writes `comparison.json`/`comparison.md`, counts improved/regressed cases,
  reports partial-credit and strict-pass deltas, includes MultiPass call/crop
  cost, optional bbox low-signal summaries, and an exact paired sign-test
  p-value. It now rejects incomplete/error scorecards by default; use
  `--allow-incomplete` only for exploratory comparison of non-error shared cases.
- Existing raw `results/*.json` can be rescored without rerunning the model via
  `uv run python scripts\rebuild-eval-scorecard.py --eval-dir <eval> --manifest data\eval-datasets\meeti\manifest.json`;
  this is useful because the current long-running process started before the
  partial-credit/schema-gate/checkpoint changes.
- `scripts\run-meeti-openclaw-experiment.ps1` now writes `experiment.json` with
  `status=running` before the eval process starts, and after `run-eval.py`
  returns it postprocesses `scorecard.rebuilt.json` plus expert-review PNGs /
  bbox audit artifacts. Future `run-eval.py` executions also write
  `scorecard.partial.json` after each case and fail fast on repeated Gateway
  infrastructure errors.
- Eval scoring has been tightened: positive keyword recall is negation-aware
  (`no ischemia` no longer counts as an ischemia hit), incomplete
  `OutputValidator` results set `schema_ok=false`, can't-miss detection uses
  positive evidence only, and WNL / within-normal-range MEETI reports map to an
  explicit normal concept.
- The desktop app and eval path now pass the downscaled image size into
  `MultiPassAnalyzer` when available, so the resolution-aware manual-zoom guard
  is actually active instead of always digitally cropping.
- `MultiPassAnalyzer` target selection now includes `info` findings with bboxes
  after warning/critical findings, so a first pass that under-calls a suspicious
  ECG change as `info` still gets crop/refine attention.
- EKG skill prompt was tightened for waveform-only MEETI screenshots: 10-second
  rhythm-strip rate estimation, LVH voltage/strain checks, ST-T/ischemia axis
  consistency, and warning severity floor for clinically meaningful ST-T/LVH/rate
  abnormalities.
- Real 1-case `openai/gpt-5.4-mini` MultiPass smoke after prompt update produced
  3 OpenClaw `analyze` calls (coarse + 2 crop/refine), fixed severity/LVH/ischemia
  for `meeti_43522917`, but still missed bradycardia. This is now recorded as
  model/prompt diagnostic miss, not a Gateway/MultiPass harness failure.
- Expert review images can be exported from any eval directory with
  `uv run python scripts\export-eval-annotations.py --eval-dir <eval> --manifest data\eval-datasets\meeti\manifest.json`.
  The exporter now also writes `review\bbox-audit.jsonl` and `review\crops\*`
  with original-image pixel coordinates, clamped normalized coordinates, crop
  thumbnails, ink-pixel ratios, `low_signal`, `was_clamped`, and
  `invalid_reason`; low-signal bboxes are cross-marked in review PNGs so
  blank/irrelevant boxes can be separated from coordinate-pipeline errors. The
  exporter cleans generated review PNGs/crops by default to avoid stale expert
  review artifacts.
  Current partial full-run review output lives under
  `data\experiments\meeti-full-multipass-20260530-221551-openai_gpt-5.4-mini\eval\review`.
- OpenClaw runtime is local `2026.5.27`; model catalog has `openai/gpt-5.5` and `openai/gpt-5.4-mini`, but no `openai/gpt-5.5-mini`.
- `openclaw/openclaw.json` now defaults to `openai/gpt-5.5`.
- MEETI eval entry point: `uv run python scripts\run-eval.py --gateway ws://127.0.0.1:18789 --dataset meeti --timeout-sec 90 --require-perfect`.
- `--mock --dataset meeti --require-perfect` passes all 400 cases and proves scoring/artifact flow.
- Real GPT-5.5 MEETI 10-case probe completed with no timeout/parser crashes after per-image `analysis-<uuid>` session isolation and narrow bbox JSON repair. Current real metrics: schema 90%, bbox 100%, severity exact 70%, abnormal/normal 90%, mean keyword recall 37%; GPT-5.5 still does not meet PERFECT GATE.
- Remaining real misses are model/read-label/prompt issues (e.g. LVH/bradycardia/low-voltage keyword misses and one malformed/empty-summary schema failure), not OpenClaw Gateway protocol failures.
- Full real experiment wrapper: `powershell -ExecutionPolicy Bypass -File scripts\run-meeti-openclaw-experiment.ps1 -ModelId openai/gpt-5.5-mini -TimeoutSec 90 -RequirePerfect`. It writes `data\experiments\...\experiment.json` and blocks if the requested model is not in the OpenClaw catalog.
- Experiment records from wrapper validation:
  - `data\experiments\meeti-20260530-214839-openai_gpt-5.5-mini\experiment.json`: blocked because OpenClaw catalog does not expose `openai/gpt-5.5-mini`.
  - `data\experiments\meeti-20260530-214859-openai_gpt-5.4-mini\experiment.json`: completed 1-case runner smoke with experiment-local config/logs/eval artifacts.

## 2026-08-06 OpenClaw subscription experiment freeze

- Agent ownership is explicit: OpenClaw runs every image turn, crop/refine loop,
  and native tool call. ChatGPT/Codex OAuth is only the subscription transport
  for `openai-chatgpt-responses`; the Codex app server is never an analyzer.
- Official `@openclaw/codex` is staged only as an OAuth migration provider, then
  removed from the live Gateway config. Packaged verification proves
  `codex_agent_runtime_dependencies_bundled=false` and zero platform binaries.
- Full blind MEETI manifests contain 9,922 ordered image cases with no answer
  fields in the inference manifest. The separate gold manifest is opened only
  after inference for scoring.
- Paired protocol runs a no-tool/no-harness baseline and a MultiPass candidate
  with bounded crop/refine plus `dicom_bbox_validate`; ECGFounder remains
  supporting evidence only and requires a valid matched-waveform sidecar.
- Exploratory baseline pilot v1 finished 64/64 with zero runtime errors,
  partial score 0.288, and mean latency 24.4 seconds. It is not the formal arm
  because source code changed afterward; both formal arms will be rerun from
  one frozen source fingerprint.
- Fresh portable build exists at `dist/DICOMOverlayAgent/DICOMOverlayAgent.exe`.
  Bundle verifier and opt-in isolated Gateway smoke are green; OpenClaw is
  2026.7.1-2 and both native harness tools are discoverable.
- A live post-fix ownership canary completed 1/1 with no error and partial
  credit 0.886. Gateway evidence shows `[agent/embedded]`,
  `api=openai-chatgpt-responses`, the ChatGPT Codex subscription endpoint,
  `openai/gpt-5.4-mini`, one prompt image, and `tools=count=0` for baseline.
- The research runner no longer installs, inspects, or uninstalls a Codex
  plugin. It shares the app's bundled migration-only bootstrap, applies bounded
  command timeouts, removes the temporary provider before Gateway launch, and
  fails closed through the OpenClaw ownership guard.
- Protocol source identity now hashes final contents of every tracked and
  untracked file in the scoped worktree, including the arm runner, paired
  supervisor, and comparator. A regression test proves same-path untracked
  edits change the fingerprint even when Git status text does not.
- OpenClaw may auto-discover the bundled Codex extension even after its config
  entry is removed, so extension loading is not used as the ownership claim.
  The install/stage flow now prunes the full `@openclaw/codex` runtime package,
  `@openai/codex`, and all `codex.exe` binaries after extracting the official
  OAuth migration provider.
- Live ownership canary v5 completed successfully after pruning. Its audit has
  one observed agent route (`openai/gpt-5.4-mini`), no Codex handoff markers,
  no runtime dependencies/binaries, `tools=count=0`, and HTTP 200 through
  OpenClaw's `openai-chatgpt-responses` transport.
- Final desktop rebuild completed after the runtime-pruning fix. The bundle is
  green, contains both native harness tools, has zero Codex binaries/full
  runtime packages, and passed four opt-in packaged selfcheck/Gateway tests.

> 📌 此檔案記錄當前工作焦點，每次工作階段開始時檢視，結束時更新。

## 🎯 當前焦點

- **四大核心維護章程已文件化 (2026-05-30)**：
  - README.md / README.zh-TW.md 改寫為 DICOM Overlay Agent 內容（移除 template 殘留），新增「四大核心」章節
  - AGENTS.md 改寫為四大核心 AI 維護 harness（取代過時的 Zotero/PubMed 內容）
  - 四核心：1) 影像判讀圖層互動（位置+內容）2) OpenClaw 判讀完整 harness 3) plugin 兼容穩定版本 4) 執行檔最小封裝
- 兼容性修正與 CI 重建已完成
- **6 組 Sonnet 平行查核 + 自主修正 (2026-05-30)**：修正多螢幕座標錯位（潛在 PHI 風險）、modality fallback、config 字串防呆；補 9 測試
- 目前已驗證：
  - Linux 可成功 `pip install -e '.[dev]'`
  - headless Qt 測試可執行（需系統套件 + `QT_QPA_PLATFORM=offscreen`）
  - **231 個 pytest 測試通過**

## 📝 最近完成的變更 (2026-03-15)

| 檔案/目錄 | 變更內容 |
|-----------|----------|
| `src/dicom_overlay/infrastructure/gateway_manager.py` | 新增：Gateway 自動啟動/停止 |
| `src/dicom_overlay/infrastructure/dpi.py` | 新增：DPI 感知工具 |
| `start.bat` | 簡化啟動流程（Gateway 自動管理） |
| `src/dicom_overlay/infrastructure/logging_config.py` | Gateway stdout → gateway.log |
| `src/dicom_overlay/presentation/overlay_window.py` | DraggableWindowMixin + 智慧顯示 |
| `src/dicom_overlay/presentation/roi_setup.py` | DPI 修正 + 改善 |
| `src/dicom_overlay/domain/entities.py` | Finding.bboxes + MonitorConfig phash |
| `src/dicom_overlay/infrastructure/screen_monitor.py` | 可配置 hash 演算法 |
| `src/dicom_overlay/infrastructure/openclaw_client.py` | WS log 過濾 + bbox 解析 + prompt |
| `src/dicom_overlay/application/overlay_agent.py` | EKG 16 項 checklist |
| `src/dicom_overlay/infrastructure/hooks/output_validator.py` | 16 key schema |
| `src/dicom_overlay/__main__.py` | Gateway 整合 + hash config + bbox highlight |
| `config.yaml` | phash + threshold 5 |
| `openclaw/workspace/skills/dicom-ekg-analysis/SKILL.md` | bbox 指示 |
| `openclaw-home/workspace/skills/dicom-ekg-analysis/SKILL.md` | 同步 bbox 指示 |
| `tests/unit/test_display_pipeline.py` | 擴充 display pipeline 測試 |
| `tests/unit/test_hooks_and_mcp.py` | 新增 OutputValidator + hooks 測試 |
| `tests/unit/test_roi.py` | 新增 ROI 單元測試 |
| `tests/integration/test_openclaw_overlay.py` | _make_result 對齊 16 keys |

## ⚠️ 待解決

- MCP adapter `_StubProvider` 需替換為真正的 MCP SDK client
- enum→str modality 全面解耦（目前新增全新模態仍需在 `Modality` enum 加一行）
- 6 個既有 ruff 警告（eval_harness ARG001、overlay_window 全形標點等，與本次無關）
- Live 測試 AI bbox 精確度

## 🔧 Gateway 啟動要點

- 正確指令：`gateway run`（非 `gateway start`）
- Gateway port: 18789; auth token is generated locally and never recorded here
- 模型：`github-copilot/gpt-5-mini`
- 現在由 `GatewayManager` 自動管理啟動/停止

## 📁 Portable 架構狀態

| 元件 | 狀態 |
|------|------|
| OpenClaw 本地安裝 (`openclaw/node_modules/`) | ✅ 完成 |
| HOME 隔離 (`openclaw-home/`) | ✅ 完成 |
| Credentials (`github-copilot.token.json`) | ✅ 完成 |
| Skills 同步 (robocopy) | ✅ 完成 |
| `start.bat` 一鍵啟動 | ✅ 完成 |
| Gateway 自動啟動/停止 | ✅ 完成 |
| Node.js portable binary | ✅ 完成（fetch-node.ps1） |
| PyInstaller 打包 | ✅ 完成（dicom-overlay-agent.spec） |

---
*Last updated: 2026-05-30*

## 2026-08-07 OpenClaw SLA harness iteration

- Current source harness/plugin version: `1.4.9`; model route remains
  `openai/gpt-5.4-mini` with per-turn OpenClaw `fastMode=true`.
- `fastMode` is recorded only as a Gateway execution request. The native
  ChatGPT subscription transport strips unsupported `service_tier`; a priority
  tier may be claimed only when `transport-receipt.json` observes it. The
  64-case baseline receipt found 64/64 fast trajectories and 64/64
  `serviceTier=undefined` provider requests.
- MultiPass hard budgets are 60 seconds for coarse response, 100 seconds for
  first crop/refinement, and 180 seconds total. Deadline degradation returns
  the best completed result with review/incomplete receipts instead of waiting
  indefinitely.
- ECGFounder sidecar now emits deterministic lead-II R-R regularity evidence.
  It does not diagnose AF. A local conflict guard acts only when top-three
  waveform ranking contains AF/flutter and measured R-R timing is irregular;
  it upgrades/reconciles an existing localized finding when possible.
- `ImageProcessor.ekg_row_strip_evidence()` confirms 12-row geometry from
  full-width black-ink periodicity while excluding red grid lines. Missing lead
  declarations are repaired only with this independent image evidence; true
  3x4/partial/low-signal images fail closed.
- Experiment scoring is negation/uncertainty aware, including shared `no ...`
  clauses, `excludes ... read`, and cautious labels that repeat an expected
  concept without creating a second false positive.
- Real blinded smoke v3 (2 cases), rebuilt with the frozen scorer: strict,
  partial, schema, concept precision, normal specificity, and all SLA rates are
  `1.0`. Final runtime canary: 45.613 s coarse, 57.833 s first refinement,
  92.417 s total; trace proves fastMode, three OpenClaw turns, ECGFounder, and
  `layout_signal_check` with 12-row confirmation.
- Pilot failure review found three general defects: irregular R-R was allowed to
  imply AF despite top-ranked ectopy, LVH-specific wording displaced balanced
  waveform review, and one local crop could retract a multi-box hypothesis.
  Version `1.4.9` routes rhythm/ectopy/AV-block hypotheses to a declared rhythm
  strip or full lead II, routes bounded multi-lead patterns to their declared
  lead context, and blocks retraction when the actual crop omits any coarse
  evidence bbox. ECGFounder top-three ectopy now also routes a lead-II probe.
- EKG prompts now test rhythm/ectopy, conduction, high versus low voltage,
  Q/QS/R-wave progression, and ST-T morphology without ranking-driven priority.
  Irregularity or poorly visible P waves alone cannot create AF.
- ECGFounder acquisition is nonce-idempotent: only one sidecar request and one
  evidence receipt are allowed; later attempts get a compact cached response
  and a separate `ecg_founder_duplicate_suppressed` audit event. The agent sees
  a compact evidence summary while full provenance remains in the receipt.
- Top-three waveform labels can route the bounded systematic slot to lead II,
  limb leads, or precordials; they still cannot set diagnosis/severity.
- Verification after the `1.4.9` changes: Ruff clean; 892 passed, 3 opt-in
  skips.
- Fresh blinded pilot artifacts use a 1,080-case exposure denylist and exclude
  all inspected smoke cases: `pilot-64-final.{inference,gold}.json`.
- Paired pilot baseline is complete at 64/64; candidate is running in a frozen
  `1.4.6` process so both arms remain comparable. Source/release `1.4.7`
  and subsequent `1.4.9` changes will not be mixed into that running pair.
- A fresh 32-case paired gate is prepared without inspecting case contents. It
  excludes 1,144 exposed identities (the prior 1,080 plus the current 64) and
  contains 8 normal, 14 warning, and 10 critical cases. It will validate
  `1.4.9` after the frozen pilot releases the Gateway.
- The currently rebuilt packaged app still contains harness/plugin `1.4.7`;
  a `1.4.9` rebuild is pending the active pilot. Its verifier status is
  `ok` with zero failures and packaged selfcheck is 3 passed, 1 Gateway smoke
  skipped while the pilot owns port 18789.

## 2026-08-04 ECGFounder 外部工具狀態

- 官方 `PKUDigitalHealth/ECGFounder` 是 ECG waveform classifier，不是 PNG
  影像模型。12-lead 合約為 500 Hz、10 秒、每導聯 5000 點，輸出 150 類
  sigmoid score；官方 live threshold 表未隨 checkpoint 發布。
- `dicom-overlay-agent-harness` 已新增 opt-in native tool
  `ecg_founder_analyze_waveform`。只有 `DICOM_ECGFOUNDER_ENDPOINT` 與
  `DICOM_ECGFOUNDER_TOKEN` 同時存在時，Gateway 才註冊並 allow 此 tool。
- Tool 只接受 app 提供的不透明 waveform artifact id，endpoint 強制 loopback，
  response 強制 checkpoint/input/preprocessing/calibration provenance；未校準
  score 不會轉成陽性/陰性，且永遠標示無 spatial localization。
- OpenClaw `plugins inspect --runtime --json` 實測：plugin `loaded`，
  `dicom_bbox_validate` 與 `ecg_founder_analyze_waveform` 都出現在 runtime，
  diagnostics 0。未設定 sidecar 時 screenshot-only allowlist 維持只有 bbox tool。
- 目前沒有把 Torch 或 370 MB checkpoint 塞入主 EXE，也還沒有可供 MEETI PNG
  使用的合格 waveform。若只有截圖，必須先有獨立、經校正品質 gate 驗證的
  waveform digitizer；現有 threshold/ink bbox 輔助不等於波形數位化。
- 完整契約：`docs/ecgfounder-tool.md`。新增/相關測試目前 86 passed，Ruff 通過。
- 系統化 MultiPass urgent canary 已完成但不是改善證據：2 案中 1 案 timeout，
  可評分案 partial 0.4、urgent concern 0/2。不能用此小樣本宣稱提升，需先處理
  多輪 timeout/成本並重新做 paired run。

## 2026-08-09 OpenClaw MultiPass evidence and release status

- Source harness/plugin is `1.5.7`; route is `openai/gpt-5.4-mini` through
  OpenClaw-owned `openai-chatgpt-responses` with subscription OAuth. Codex only
  migrates auth before Gateway start; runtime ownership receipts show no Codex
  agent/app-server handoff and Platform API keys are disabled.
- Frozen 32-case paired pilot (`1.5.2`) completed both arms. MultiPass improved
  mean partial credit by +0.227 with bootstrap 95% CI `[+0.085,+0.368]` and
  random-sign `p=0.00449955`; 23 cases improved, 4 regressed. Candidate met all
  60/100/180 SLA stages, but normal severity-safe fell 8/8 to 6/8 and urgent
  recall was only 3/10. This is significant weak-label agreement improvement,
  not clinical validation.
- Fresh `1.5.6` unseen8 completed 8/8 with zero errors, 8 review PNGs and 30
  crops. Ownership/toolchain/schema/bbox/projection/SLA gates pass; mean stage
  times are 16.180/28.508/71.058 seconds. Strict is 0.250, partial 0.595,
  normal specificity 2/2, and urgent concern 1/3. Safety misses remain results.
- Weak-label scorer now distinguishes asserted and candidate concepts.
  Candidate uncertainty receives only 0.5 weight on incomplete weak labels and
  cannot affect strict/cant-miss/urgent metrics; explicit negatives never score.
- `1.5.7` removes exact duplicate study-level rate/rhythm findings while
  preserving localized morphology. A real exposed one-case regression produced
  one lead-II sinus-bradycardia box and no duplicate precordial rhythm boxes.
- Process UI exposes ECGFounder ranked scores and deterministic rate/R-R
  evidence with the uncalibrated/supporting-only/no-localization boundary.
  Desktop review export is self-contained with source, result, marked image,
  crop PNGs, and coordinate audit.
- Detailed experiment record:
  `docs/meeti-openclaw-experiments-2026-08-09.md`.
- The pre-publication 9,922-case run at
  `data/experiments/meeti-paired-full9922-v157-20260809` was deliberately stopped
  at 289 baseline results before final commits. Its state is `interrupted`; the
  retained HTTP 200/OpenClaw ownership/`fastMode=true` rows are launch evidence,
  not a comparable full experiment.
- The authoritative frozen-source root is
  `data/experiments/meeti-paired-full9922-v157-postpublish-v1`. Launch it only
  after all scoped commits are pushed, then treat its `paired-experiment.json`
  as the sole live/completion state. The supervisor atomically resumes matching
  results with retry; do not change source/harness/scorer until both arms and
  comparison finish. At the unseen8 mean, candidate alone is about 196 hours.
- Full verification is complete: Ruff passed; unit/smoke `915 passed, 3
  skipped`; post-build packaged tests `4 passed`; Windows capture exclusion `1
  passed`. The rebuilt bundle is `ok`, 368.01 MiB / 16,188 files, with OpenClaw
  `2026.7.1-2`, Node `v24.18.0`, plugin `1.5.7`, and launcher SHA-256
  `27fcb0fafecdb2285d9dc1aae1a51d6ca46a0930592400740abfbe6deb17984e`.
- An isolated 15-second full GUI launch remained responsive, started bundled
  Node/OpenClaw, and released port 18789 on shutdown. Release smoke did not call
  a model. The pinned npm tree still has 7 moderate/4 high/0 critical upstream
  advisories.

## 2026-08-28 Critical-first phased interpretation

- MultiPass planning now distinguishes a structured/localizable critical
  finding from top-level urgency or a generic label. Only the former activates
  critical-first triage.
- Every available refinement slot is assigned to critical hypotheses first.
  When budget remains, EKG may add at most one mechanism-related lead-II,
  reciprocal-lead, or cross-lead morphology support crop. CXR receives no
  invented generic support turn.
- Lower-priority finding crops, local safety candidates, and unrelated
  systematic probes are skipped with an explicit critical_triage receipt,
  including overflow, selected IDs, support reason, skipped categories, budget,
  and deferred checklist axes.
- Deferred normal EKG axes are changed to
  not_assessed_due_to_critical_triage with info status. Final reconciliation
  must preserve incomplete/review state even if all critical candidates are
  retracted; bbox geometry and the original-ROI final turn remain unchanged.

## 2026-08-28 Frozen important multi-diagnosis 128 cohort

- A fixed-seed, answer-free inference cohort of 128 important multi-diagnosis
  MEETI cases is frozen from the 9,922-case manifest. It is a purposefully
  gold-enriched safety/uncertainty stress cohort, not a prevalence-weighted
  population-accuracy sample and not independent physician adjudication.
- Selection excludes 1,230 previously exposed cases and requires at least three
  canonical diagnoses, five mutually exclusive clinical tiers, fixed
  asserted/partially-uncertain quotas, and at least 12 examples for every one
  of the 16 EKG axes. The source has no patient-group field, so patient-level
  independence cannot be claimed.
- The pair contract now binds the ordered SHA-256 of all 128 actual PNG files,
  rejects duplicate image bytes, strips uncertain concepts before diagnosis
  counting, rejects unknown acute-signal vocabulary, recursively blocks answer
  fields, and fails when frozen local artifacts are only partially present.
- Frozen pair id is
  `7bdc87f6d184b321938a09e4f02335692fbda75a378127305742b6f41e8a46e0`;
  ordered image digest is
  `38bcf5b0bd4008ac3bb6a39da3cb7f430278c55aff4c818d0a08a1fd2348c7ca`.
  Local gold/inference/report artifacts stay gitignored; they must never be
  published or treated as available in clean CI without a controlled download.

## 2026-08-28 Auditable clinical knowledge registry

- Seven deterministic EKG/CXR consistency rules now have one canonical
  `clinical_knowledge/rules/core.rule.yaml` source with strict JSON Schema and
  dependency-free semantic validation. Unknown keys/axes/operators, stale
  review dates, unmapped runtime IDs, invalid source locators, or missing parity
  test nodes fail closed.
- The same step IDs generate a detailed clinician-facing differential workflow,
  a compact agent execution view, and pure domain runtime data. The previous
  hand-written `_BUILTIN_RULES` duplication was removed; runtime behavior is
  generated from YAML and guarded by the registry SHA-256.
- Priority metadata distinguishes product safety severity floors from guideline
  statements. A citation does not claim that a guideline directly defines the
  app's warning/critical enum, and screenshot findings remain distinct from a
  clinical diagnosis requiring symptoms, biomarkers, serial studies, or other
  imaging.
- An application-owned SQLite quick-lookup projection is generated and verified
  table-by-table from YAML. OpenClaw's private empty `main.sqlite` FTS cache is
  neither written nor treated as a rule source, preserving the public Gateway
  boundary.
- Registry digest scope is now `canonical-input-documents-v1`: parsed rule and
  axis YAML, legacy inventory, strict JSON schema, and their relative paths.
  The packaged verifier reloads those bundled canonical inputs, rejects the
  wrong schema ID/version or an empty shell, regenerates both views, and checks
  every SQLite table/column/row plus integrity and foreign keys. Current digest
  is `d22a03e037293636c86ca029452a8486f93f5625cb5655b3381088b8cc1fc22c`.
- Prompt and OutputValidator contracts now reject generic AI/medical refusal or
  disclaimer boilerplate while preserving concrete case-specific capture limits.
  The agent remains a specialist co-reader and does not redirect routine work to
  another professional.
- OpenClaw `2026.7.1-2` documents current operator/UI protocol 4 while retaining
  protocol 3 only for the N-1 node/probe window. The desktop client still
  advertises its verified `3..4` compatibility range, but now rejects a generic
  successful response unless it is a valid `hello-ok`, records negotiated
  protocol/server version, and carries that receipt into smoke/eval artifacts.
  `MIN_SAFE_OPENCLAW_VERSION` remains `2026.4.22`; no floor bump was inferred.

## 2026-09-02 Reproducible package evidence

- Release builds use an isolated no-dev environment pinned through `uv` to
  64-bit CPython 3.13.12. The bundle carries a receipt with exact Python
  architecture plus PyInstaller, Pillow, PyQt6, Qt6, and sip versions.
- UPX remains enabled by default in the spec. `build-exe.bat` enables it only
  when the tool is available; verification requires an observed UPX-marked app
  PE. Otherwise the receipt says `no_upx_baseline` rather than claiming an
  unobserved compression gain.
- Relative configured logs now resolve inside the executable's `base_dir`,
  independent of launch cwd; traversal outside that base is rejected.
