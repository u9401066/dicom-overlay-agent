# Verification record — 2026-09-02

本文件記錄目前可重現的證據與未完成 gate。它不是 release note，也不是臨床驗證
報告。Working-tree metadata 為 `0.4.7`／plugin `1.5.8`，但建立本紀錄時 repository
沒有 Git tag 或 GitHub Release；公開 GitHub Pages 也尚未部署目前 branch 的內容。

## Evidence vocabulary

| 等級 | 能證明什麼 | 不能證明什麼 |
| --- | --- | --- |
| Source unit/smoke | 純函式、schema、protocol builder 與 regression contract | 真實 Gateway、GUI、provider 或診斷效果 |
| Mock artifact | manifest、resume、輸出、bbox/partial plumbing 可完整流動 | 模型辨識、真實 latency、計費或 viewer interaction |
| Real Gateway/headless | 真實 OpenClaw/provider transport 與 response parsing | viewer ROI、overlay 實際位置與醫師桌面 UX |
| Real viewer + desktop App | 實際 ROI capture、App-managed Gateway、render/export 與使用量 | 若病例少或結果錯，不能推論 cohort accuracy |
| Clean packaged release | frozen EXE/runtime、residue scan、尺寸/hash 與 packaged smoke | 沒有 blinded cohort 與 specialist review 時仍非臨床認證 |

## Current requirement matrix

| Requirement | Authoritative current evidence | Status |
| --- | --- | --- |
| GPT-5.6 Luna subscription route | Settings profile `openai-codex-luna`; native OpenClaw `openai-chatgpt-responses`; no `OPENAI_API_KEY`; three real App attempts below | Route reached; diagnostic gate failed |
| GPT-5.6 Luna API route | Separate `openai-luna`; `OPENAI_API_KEY`; OpenClaw `openai-responses` | Profile/source tests only in this cycle |
| First frozen critical case | Three desktop exports under `data/exports/desktop-20260902-*`; all `incomplete=true`, `review_required=true` and clinically inadequate | Failed; rerun required |
| Important multi-diagnosis cohort | Frozen answer-separated 128-case pair, pair id `7bdc87f6…8a46e0` | Constructed and exposed/reserved; real App batch not run |
| Partial ECG | Eight deterministic v2 variants; manifest SHA-256 `e61b5fc6…5d50`; 8/8 mock verification | Mock plumbing passed; real App run pending |
| Bbox/Gateway ownership | Shared canonical absolute audit resolver plus atomic ownership receipt keyed by PID/port/token/launch-owner/audit path | Source regression evidence; real App rerun pending |
| Clinical rules | Seven YAML rules; generated human/agent/runtime/SQLite views; registry SHA-256 `d22a03e…fc22c` | Software parity present; specialist/licensing review pending |
| Speed and accuracy | Three negative single-case timings; historical experiments are separately documented | No current 128-case aggregate claim |
| Packaging | Historical clean 368.01 MiB bundle; safe reductions identified | Clean current rebuild/hash/package smoke pending |
| OpenClaw 2.x | `2026.8.2` isolated public-protocol probe | Adoption deferred; migration/rollback/size gates open |
| Website and release | Site source exists; version metadata exists | Current Pages deployment, tag, and GitHub Release absent |

## Real desktop App evidence

The same first frozen critical ECG was visible in the real viewer and acquired
through the desktop App's configured ROI. The App used OpenClaw-owned GPT-5.6
Luna through the subscription profile. Each export contains `source.png`,
`result.json`, `review.png`, `bbox-audit.json`, and a crop directory.

| Export | Wall time | Token receipt | API-equivalent cost | Structured outcome |
| --- | ---: | --- | ---: | --- |
| `desktop-20260902-082210-259256` | 139.4 s | input 48,789; cached 20,480; output 5,517; reasoning 3,217; total 74,786 | US$0.0167878 | `info`; 0 findings; `incomplete/review`; regular-sinus/artifact summary; wrong |
| `desktop-20260902-090424-024627` | 61.673 s | input 24,787; cached 10,752; output 2,272; reasoning 1,093; total 37,811 | US$0.00789884 | `info`; one unboxed possible-LVH finding; only 5 checklist rows; `incomplete/review` |
| `desktop-20260902-092532-259033` | 153.398 s | input 61,500; cached 20,480; output 5,714; reasoning 3,053; total 87,694 | US$0.0195664 | `info`; one unboxed nonspecific ST-T finding; `incomplete/review`; critical miss |

Costs are recomputed with the
[official GPT-5.6 Luna API token rates](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
current on 2026-09-02: US$0.20/M input, US$0.02/M cached input, and US$1.20/M output. They
are comparison estimates, not ChatGPT/Codex subscription charges. Reasoning
tokens are included in output accounting rather than added a second time.

The gold reference includes a critical acute-infarction concern together with
multiple rhythm/conduction/axis/voltage/ST findings. None of the attempts
recovered the required critical disposition. Transport completion, low bbox
count, or an `incomplete` flag is not a pass.

## Failure interpretation and implemented guardrails

The attempts exposed two interacting issues:

1. An externally started Gateway and the client could anchor a relative bbox
   tool-audit path to different working directories. The model response could
   be semantically useful while the matching native bbox receipt appeared
   missing to the client.
2. Critical-first finalization could retract/downgrade all critical candidates
   yet keep the lower-priority axes deferred, producing an internally negative
   summary rather than resuming the systematic read.

Current source resolves one absolute bbox audit path for launcher and client.
The App-managed Gateway writes `data/tmp/openclaw-gateway.lock/ownership.json`
atomically with receipt schema, PID, port, token SHA-256, launch-owner SHA-256,
and that audit path. Reuse requires exact matching liveness/listener evidence;
unknown or mismatched listeners are refused without termination. Receipt values
contain digests, not the token.

These source changes still need a successful real viewer+App rerun. Tests alone
do not close the failure that the real desktop workflow exposed.

## Frozen evaluation inputs

`important-multi-128-v1` is a purposefully gold-enriched stress cohort selected
from 9,922 ordered MEETI image cases with seed `1946247532`:

- 128 unique case identities, normalized reports, and exact image hashes;
- at least three canonical diagnoses per case;
- 24 critical and 104 warning cases;
- 48 asserted and 80 partially uncertain reports;
- tier allocation 24 acute-risk, 28 ischemic/infarct, 28 rhythm/ectopy, 32
  conduction/QT, and 16 structure/voltage;
- pair id
  `7bdc87f6d184b321938a09e4f02335692fbda75a378127305742b6f41e8a46e0`;
- ordered image digest
  `38bcf5b0bd4008ac3bb6a39da3cb7f430278c55aff4c818d0a08a1fd2348c7ca`.

The pair is frozen and all selected cases are exposure-reserved. It has not
completed a real viewer+App run. Because selection intentionally enriches
important and multi-finding cases, future scores describe this stress cohort,
not disease prevalence or population accuracy.

`incomplete-ecg-20260902-v2` contains top/bottom/left/right crops, a central
band, masked left labels, a one-row-like narrow band, and a 67×48 downsample.
The corpus manifest SHA-256 is
`e61b5fc6ede4047640d4204c9c9a557661c615549d86435632e5c69966f85d50`.
Its 8/8 result verifies mock schema, bbox, partial flags, hashes, and artifacts
only. It deliberately has no diagnostic answers, so it cannot generate an
accuracy score. Every variant remains pending in the real App.

## Clinical knowledge truth

Canonical input consists of `clinical_knowledge/rules/*.rule.yaml`,
`axes/*.axes.yaml`, `legacy-inventory.yaml`, and `schema/rule.schema.json`.
Those inputs generate:

- `generated/human-catalogue.md` for detailed, auditable differential steps;
- `generated/agent-steps.md` for concise execution steps with matching IDs;
- `domain/generated_clinical_rules.py` for dependency-free runtime data;
- `clinical-knowledge.sqlite` as an application-owned quick-lookup projection.

The seven-rule registry is bound to SHA-256
`d22a03e037293636c86ca029452a8486f93f5625cb5655b3381088b8cc1fc22c`
with digest scope `canonical-input-documents-v1`. The verifier reconstructs all
views/tables from YAML rather than trusting database metadata alone.

This proves traceability and parity, not clinical completeness. A qualified
specialist must review the actual rationale, exclusions, severity policy,
sources, and review dates. Legal/licensing review is also required before a
commercial or clinical deployment; a citation in the registry is not a license.

## Packaging evidence

The last complete clean build (2026-08-09) measured:

| Layer | Bytes | MiB |
| --- | ---: | ---: |
| Launcher | 7,397,370 | 7.05 |
| App + Python/Qt | 99,338,066 | 94.74 |
| OpenClaw | 194,011,520 | 185.02 |
| Node | 92,534,088 | 88.25 |
| Full bundle | 385,883,674 | 368.01 |

Current `dist/` measures 378.18 MiB but contains 10.156 MiB of runtime residue;
it is explicitly rejected as release evidence. Safe staging reductions already
implemented but still awaiting a clean full measurement are PDB/tree-sitter C/H
(19.804 MiB), foreign-native payloads (0.642 MiB), and Pillow AVIF (7.471 MiB).
The arithmetic projection of about 340.3 MiB must not be reported as measured.

Next candidates must each pass import tracing, source tests, frozen self-check,
real App/viewer smoke, and bundle verification:

- win32ui + `mfc140u.dll`, about 6.41 MiB, while retaining pythoncom/win32com SAPI;
- unused Qt plugins, about 3.87 MiB;
- unused Pillow native codecs, about 0.70 MiB.

OpenClaw `dist`, TypeScript, Playwright, provider dependencies, QuickJS, and Node
are protected. Pruning them is an internal-coupling change, not safe packaging.

## OpenClaw 2.x and release status

An isolated OpenClaw `2026.8.2` copy negotiated the public Gateway contract, so
there is no protocol-only blocker. It was not adopted because the tested core
unpacked footprint grew from 83.43 to 196.68 MiB and the auth/config migration,
state-schema rollback, staged OAuth provider, and full packaged gates have not
closed. The repository remains pinned to `2026.7.1-2`; see the dedicated
[decision record](openclaw-2x-decision-2026-09-02.md).

Release remains pending until, at minimum, the first critical rerun, all eight
partial variants, the 128-case real App run, display/bbox review, clean bundle,
CI, current Pages deployment, Git tag, and GitHub Release are evidenced. No
unfinished item should be converted into a badge, release note, or clinical
claim.
