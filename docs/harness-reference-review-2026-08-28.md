# Image / medical-agent harness reference review — 2026-08-28

本文件補充 2026-08-27 的初版審查，聚焦可直接改善本專案的
multimodal eval、schema validation、tool receipts、visual grounding、
retry/resume、dataset leakage、human review 與 medical-AI evaluation。

這是工程設計審查，不是臨床驗證，也不是任何模型、benchmark 或產品的
診斷效能背書。所有 GitHub revision 與日期均在 2026-08-28（Asia/Taipei）
查核；commit 日期以下以 UTC 表示。沒有複製外部程式、加入 runtime
dependency、下載模型權重或接觸受管制資料。

## 結論

維持目前的輕量、repo-local Python harness。外部專案最值得採用的是契約與
測試模式，而不是它們的框架：

1. 將每題拆成 input、Gateway、interpretation、geometry、score 五段 receipt，
   以 ID 與 SHA-256 串起來。
2. schema／transport／bbox 合法性先做不可妥協的 hard gate；臨床內容、
   localization quality、latency 與 review burden 再分開評分。
3. retry/resume 必須依 stable case ID、attempt ID 與完整 protocol fingerprint
   復原；已被 Gateway 接受的 `chat.send` 不可盲目 replay。
4. bbox 不只驗證 `0-1` 範圍，也要分別量測 point hit、IoU／containment、
   空白訊號、過寬框與 ROI→螢幕 round-trip drift。
5. 不完整 ECG 採成對干預：完整 baseline、已知 lead 裁切／遮蔽、同面積隨機
   control。只有可見 evidence 可被判讀；不可見 lead 必須保留
   `not_assessable`／review，而不是由共現關係補答案。
6. gold 只可進入離線 selector 與封存後 scorer。實際 inference manifest 必須
   answer-free，並保留 exposure denylist、selection hash 與 case-order hash。
7. 醫療品質需看 critical miss、normal false-positive、worst-of-n、專科醫師
   review 與 reviewer disagreement；單一總分或 LLM judge 不能代表臨床有效。

## 可稽核來源快照

| ID | 官方／原始來源 | 查核 revision、日期 | License |
| --- | --- | --- | --- |
| R1 | [openclaw/openclaw](https://github.com/openclaw/openclaw) | release [`v2026.7.1-2`](https://github.com/openclaw/openclaw/tree/v2026.7.1-2)，tag `be8b8a9e8838f832e4fa47cde8bea0a33aec71ba`，commit `0790d9f593ad30c940ed93b5872a8cf6d6f3cf8c`，released 2026-08-04；main `8a9202a392476d6fe24bb8d845cab0eae7bfad57`，2026-08-28 | MIT |
| R2 | [openai/openai-cookbook](https://github.com/openai/openai-cookbook) | image-eval file [`0aaed0f`](https://github.com/openai/openai-cookbook/blob/0aaed0f1d32f83a43732c9cc23283a037a801782/examples/multimodal/image_evals.ipynb)，2026-07-20；eval-flywheel file [`2ce7c32`](https://github.com/openai/openai-cookbook/blob/2ce7c32a253a0540c9bd65d7c84c773e16e1eead/examples/evaluation/Building_resilient_prompts_using_an_evaluation_flywheel.md)，2025-10-07 | MIT |
| R3 | [EvolvingLMMs-Lab/lmms-eval](https://github.com/EvolvingLMMs-Lab/lmms-eval) 與[原始論文](https://arxiv.org/abs/2407.12772) | main [`5938516`](https://github.com/EvolvingLMMs-Lab/lmms-eval/tree/593851645597652776b39c812f99064b35aa29f4)，2026-08-27；latest release [`v0.7.2`](https://github.com/EvolvingLMMs-Lab/lmms-eval/releases/tag/v0.7.2)，2026-06-24 | Main pipeline MIT；`tasks/`、`models/` Apache-2.0，依其 LICENSE 分區 |
| R4 | [UKGovernmentBEIS/inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai) | main [`86ad4fa`](https://github.com/UKGovernmentBEIS/inspect_ai/tree/86ad4fa73042a445588e2eca18df1502da6bb661)，2026-08-27 | MIT |
| R5 | [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | main [`f1a806a`](https://github.com/openai/openai-agents-python/tree/f1a806ad35071053f5248b38b58b8c0c40f67350)，2026-08-28；latest release [`v0.22.0`](https://github.com/openai/openai-agents-python/releases/tag/v0.22.0)，2026-08-19 | MIT |
| R6 | [microsoft/RadFact](https://github.com/microsoft/RadFact) 與[原始 MAIRA-2 論文](https://arxiv.org/abs/2406.04449) | main [`887724f`](https://github.com/microsoft/RadFact/tree/887724f460522a4d47b68f58e73458a237425e23)，2026-08-24 | MIT |
| R7 | [rajpurkarlab/cheXlocalize](https://github.com/rajpurkarlab/cheXlocalize) 與[原始論文](https://doi.org/10.1038/s42256-022-00536-x) | master / README [`2a79492`](https://github.com/rajpurkarlab/cheXlocalize/tree/2a79492e9ecdf1c3cad74d968134cadc16be4a70)，2023-12-13；release [`v1.0.0`](https://github.com/rajpurkarlab/cheXlocalize/releases/tag/v1.0.0)，2022-08-05 | MIT |
| R8 | [arco-group/ShoViR-Bench](https://github.com/arco-group/ShoViR-Bench) 與[原始論文](https://arxiv.org/abs/2606.30201) | main `86d4fb38fec75767ce58f38e5009312c801cf896`，於 2026-08-28 查核；paper 2026 | CC-BY-NC-4.0 |
| R9 | [openai/simple-evals](https://github.com/openai/simple-evals) 與[官方 HealthBench 說明](https://openai.com/index/healthbench/) | HealthBench file [`496e457`](https://github.com/openai/simple-evals/blob/496e4570446e9f0499a00557a231a440c446df76/healthbench_eval.py)，2026-04-22；repo head `652c89d0ca9df547706735883097e9537d40dc47` | MIT（code）；benchmark data 另依其發布條款 |
| R10 | [microsoft/HealthAgentBench](https://github.com/microsoft/HealthAgentBench) 與[原始論文](https://arxiv.org/abs/2606.31179) | main [`ce89def`](https://github.com/microsoft/HealthAgentBench/tree/ce89def2edf56f4a2ef068f37c8544bff944d5fc)，2026-07-28 | MIT；底層資料集另有各自 DUA／license |
| R11 | [amazon-science/PatientAgentBench](https://github.com/amazon-science/PatientAgentBench) 與[原始論文](https://arxiv.org/abs/2607.25485) | main [`c9bfa1b`](https://github.com/amazon-science/PatientAgentBench/tree/c9bfa1b57253d731582cb64da4e9dfe6fe633f15)，2026-07-29 | CC-BY-NC-4.0 |
| R12 | [cornerstonejs/cornerstone3D](https://github.com/cornerstonejs/cornerstone3D) | release [`v5.8.4`](https://github.com/cornerstonejs/cornerstone3D/tree/v5.8.4) / commit `fbea912e4ec31748d2fd5c3f8d1bd9d2dfd75278`，2026-08-27 | MIT |

「官方／原始」在此指專案維護者、論文作者群、OpenAI、Microsoft、Amazon、
UK AI Security Institute、Stanford/Rajpurkar Lab 或 Cornerstone 官方來源；未用
部落格轉述、排行榜彙整或非作者重作版作為證據。

| 審查面向 | 主要來源 | 借鏡到本專案的最小 pattern |
| --- | --- | --- |
| Multimodal eval | R2、R3 | case／runner／grader 分離；image input 與每題 artifact identity 固定 |
| Schema validation | R1、R5 | closed object、required fields、invalid JSON hard fail、stream/non-stream parity |
| Tool receipts | R1、R4、R11 | request/call ID 對應 result、run/attempt identity、safe trace 與 usage |
| Visual grounding / bbox | R6、R7、R8、R12 | finding correctness 先於 box credit；hit/overlap/containment/transform 分項 |
| Retry / resume | R1、R4、R11 | idempotency、stable case ID、new attempt ID、fingerprint 相同才復用 |
| Dataset leakage | R3、R9、R11 | answer-free inference、canary/denylist、fresh seed 與 frozen hash 各司其職 |
| Human review | R7、R9 | 多 reviewer reference、blind review、grader meta-eval、disagreement/adjudication |
| Medical-agent eval | R9、R10、R11 | task-specific verifier、critical-weighted rubric、repeats/CI、明示非臨床認證 |

## 來源別採用決策

### R1 — OpenClaw public Gateway

官方 [`gateway/protocol.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1-2/docs/gateway/protocol.md)
把 request、response 與 event 定義成可關聯 frame，副作用方法使用
idempotency key；[`webchat.md`](https://github.com/openclaw/openclaw/blob/v2026.7.1-2/docs/web/webchat.md)
說明相同 `chat.send` idempotency key 會被去重。

- 採用：保存 request ID、idempotency key、accepted `runId`、terminal event、
  event sequence、server version 與 `hello-ok.protocol`。斷線後若已 accepted，
  追蹤既有 run，不重送同一個影像判讀。
- 查核風險：`v2026.7.1-2` source 宣告一般 client minimum protocol 4；本專案
  現行 client advertises `minProtocol=3`、`maxProtocol=4`。這應以實際
  `hello-ok` 協商結果與 Gateway smoke 證明，而不是把文件中的「protocol 3」
  當成固定事實。
- 不採用：不 import Gateway/plugin SDK internals，不讀 `dist` chunk 推導
  contract，也不因 main branch 新功能自動改 wire shape。
- 對應：Core 2（receipt／artifact）、Core 3（唯一 public boundary）。

### R2–R5 — 一般 multimodal／agent evaluation harness

OpenAI image-eval cookbook 把系統拆成 test cases、runner、grader、score 與
feedback，並區分 non-negotiable gating graders、graded metrics、rubric labels
及 pairwise human preference。LMMs-Eval 把 task、model adapter、scorer、
per-sample log/cache 與統計彙整分開。Inspect 保存 input、output、target、score、
token usage、tool calls/results 與錯誤，並以 stable sample ID 重用已完成題目；
retry 不覆寫舊 log。OpenAI Agents SDK 的 schema 維護說明要求 object schema
封閉 `additionalProperties`、驗證 invalid JSON、並保持 streaming／non-streaming
adapter 行為一致。

這些通用資源不是 medical-image validation；本專案只借用可重現性、契約與
artifact pattern，不繼承其 benchmark claims。

- 採用：本 repo 的 16-key validator 繼續 fail closed；runner、scorer 與 artifact
  validator 保持分離；每個 attempt 保留自己的 identity，完成題只在 fingerprint
  完全相符時 resume；tool call 與 result 必須用 call ID 配對。
- 採用：把「grader 本身失敗」列為 engineering failure，不可默認成臨床陰性，
  也不可從 aggregate 分母消失。
- 不採用：不安裝 LMMs-Eval、Inspect 或 OpenAI Agents SDK；不啟用另一個 agent
  runtime，不把 trace 上傳到外部服務，不讓 SDK 取代 OpenClaw。
- 原因：這些框架會引入大型 ML／資料／web stack、第二套 transport 與新的 PHI
  surface，削弱 Core 3、Core 4 與 ROI privacy。
- 對應：Core 2、Core 3、Core 4。

### R6–R8 — visual grounding 與影像依賴性

RadFact 分開 logical precision/recall、grounding precision/recall 與 spatial
precision/recall；只有 finding 在文字上成立且空間也成立才取得 grounding credit。
它也明列 LLM entailment failure 數量，警告失敗過多時分數不可靠。

CheXlocalize 同時使用較嚴格的 mIoU 與較寬鬆的 pointing-game hit rate，並提供
多位 board-certified radiologists 的 pixel mask／代表點作 human benchmark。
這證明「框到病灶」與「框得精準」是兩個不同問題，不能只檢查 box 在畫面內。

SHOVIR 以 target-region occlusion、co-occurring-region occlusion 與 matched
random occlusion 對照，檢查文字品質高的模型是否其實不依賴目標像素。這個設計
可轉用到 ECG lead 缺失／裁切，但不能直接搬用 CXR pathology 定義。

- 採用：先判 finding 內容是否正確，再計 box；至少報 point hit、IoU 或
  candidate-in-reference containment、blank-signal 與 oversized-box rate。
- 採用：不完整 ECG 建立 paired perturbation，保留 source/variant hash、裁切
  transform、可見 lead inventory 與 matched-area control；比較同一病例在完整與
  不完整影像上的結論變化。
- 不採用：不把報告 weak labels 假裝成 bbox ground truth；沒有 specialist mask／
  point 的 MEETI case 只能做內容與工程評估，不能宣稱 localization accuracy。
- 不採用：RadFact 的 LLM judge 不能成為 release hard gate；SHOVIR code 為
  CC-BY-NC-4.0，且需要多組 GPU/model environment，故不複製、不 vendor。
- 對應：Core 1（bbox 與 viewer）、Core 2（grounding eval）、Core 4（不加重）。

### R9–R11 — 醫療 rubric、agent task 與 leakage

HealthBench 使用逐案例 physician-written weighted rubrics，包含正向與負向條件；
Consensus 子集由多位醫師再確認，另以 worst-of-n 觀察醫療情境的尾端失敗，並
meta-evaluate model grader 與 physician judgment 的一致性。官方也要求不要公開
benchmark 例題，並提供 contamination canary；本文件不重刊 canary 或題目內容。

HealthAgentBench 的每個 task 都有自己的 instruction、environment、tests 與
task-specific verifier，並報告 repeated trials、Wilson interval、cost 與 time，
而不是只報一次成功。PatientAgentBench 以 seed distribution 產生新案例、保留
message/tool-call/tool-result structured trace，並讓既有 run directory 可 resume；
它明確說 benchmark score 不是 clinical certification。

- 採用：critical finding、normal control、partial input、bbox 與 professional
  communication 分開 rubric；critical miss 與「把緊急事項埋在低優先 detail 後」
  使用較高負分，不能被平均分稀釋。
- 採用：對專科醫師的輸出若只是泛用拒答或冗長免責、且沒有完成可見影像判讀，
  應記為 failure；但針對真正缺失的 lead／裁切證據，具體的 `not_assessable` 與
  review request 是正確的不確定性，不可誤當 refusal。
- 採用：同一 frozen cohort 至少重複若干次，報 critical worst-of-n、正常片
  false-positive／review burden、latency、tokens 與失敗率；model judge 必須抽樣由
  專科醫師盲審校準。
- 採用：gold selector 與 inference runner 分權；selection 後輸出 answer-free
  manifest，保存 selection policy/hash、case/order hash、曝光 denylist 與下一輪
  exclusion list。
- 不採用：不下載 HealthBench、MIMIC-CXR、CT-RATE 或其他 gated dataset 到產品
  bundle；不採用 Harbor／LangGraph／Docker benchmark runtime；不複製
  PatientAgentBench 的 CC-BY-NC code。
- 對應：Core 2、Core 4，以及四核心共同的臨床證據邊界。

### R12 — DICOM viewer coordinate spaces

Cornerstone3D 將 image/index、world 與 canvas 座標明確分層，annotation state
綁定 `FrameOfReferenceUID` 並把 handles 存在 world coordinates；官方文件也明確
區分 image corners 與 canvas corners。這是 viewer architecture 參考，不是要把
現有 PyQt overlay 改寫成 JavaScript。

- 採用：每個 bbox receipt 都應記錄 source image dimensions、normalized ROI box、
  ROI logical pixels、screen logical pixels、device-pixel ratio、monitor origin、最後
  physical screen rectangle 與反向投影誤差。
- 採用：DPI matrix 至少涵蓋 100/125/150/175/200%、不同 viewport aspect ratio、
  zoom/pan、負座標 secondary monitor 與跨螢幕；測試 image↔ROI↔screen round trip，
  不以肉眼看起來接近代替數值 gate。
- 不採用：不加入 Cornerstone/npm/VTK，且絕不為了匹配 viewport 擴大 capture ROI。
- 對應：Core 1（position）、Core 4（無新增前端 runtime）；ROI 邊界保持不變。

## 建議的本地 receipt chain

以下欄位可用現有 JSON artifact 實作，不需要新 dependency。名稱是設計建議，
不是本輪 schema 變更。

| Receipt | 最低必要證據 | Fail-closed 條件 |
| --- | --- | --- |
| Input | `case_id`、source SHA-256、ROI bounds、width/height、modality、variant transform、visible regions | hash／尺寸不符、ROI 越界、partial variant 無可見範圍說明 |
| Gateway | request ID、idempotency key、session key digest、advertised protocol range、negotiated protocol、server version、attachment MIME/bytes/SHA、accepted run ID、terminal event | image 未進 attachment、request/response ID 不符、run event 混線、未知 terminal 狀態 |
| Interpretation | attempt ID、prompt/rule/skill digest、16-key payload digest、validator version、stage decision、latency/tokens、safe tool call/result pairs | invalid JSON、missing/extra key、tool result 無 matching call ID、grader error 被吞掉 |
| Geometry | bbox normalized coords、evidence-image SHA、crop→source transform、ROI→screen transform、DPR/monitor、projected rectangle、round-trip drift | NaN/Inf、零面積、全在影像外、evidence hash 不符、transform receipt 缺失 |
| Score | sealed inference digest、gold/scorer version/hash、per-case metrics、judge failures、human-review status | inference 後內容被覆寫、gold 在推論前可見、失敗 case 從分母消失 |

Artifact 不應保存 chain-of-thought、PHI、OAuth token、Platform API key、完整桌面或
ROI 外像素。需要識別 session 時使用不可逆 digest 或本地 opaque ID。

## 建議的 release gates

### P0 — 在下一個真實 100+ case 批次前

1. 確認 Gateway artifact 實際保存 `hello-ok.protocol` 與 server version；
   `v2026.7.1-2` 的 3..4 negotiation 必須由真實 smoke 證明。
2. 對每題封存 attachment/source SHA、accepted run ID、terminal event 與 result SHA，
   並驗證 accepted 後沒有 replay。
3. frozen inference manifest 不含 diagnosis、scorer alias、rubric answer 或 gold path；
   selection hash、denylist hash 與 case-order hash 必須 fail closed。
4. 不完整 ECG 以同病例 paired set 測 baseline、known-lead crop/mask 與 matched random
   control；不可見 lead 不得產生假精確 finding/bbox。
5. bbox release report 分開輸出 geometry-valid、point hit、IoU/containment、blank
   signal、oversize 與 screen projection drift。沒有 expert localization 的資料列標為
   `reference_unavailable`，不可混入 localization 分母。

### P1 — 效能／正確率迭代

1. 對 critical-heavy、multi-diagnosis、normal control 與 partial-input strata 報
   per-stratum 指標及 worst-of-n；不可只報 aggregate mean。
2. 每個 prompt/harness change 使用同一 frozen pair、paired bootstrap／permutation
   或適當 confidence interval；只有 effect 與 failure tail 都改善才稱為提升。
3. human review 覆蓋所有 critical disagreement、所有 invisible-region assertion、
   所有 low-signal/oversized bbox，再加一組分層隨機樣本；比較實驗時 reviewer 應對
   arm/model identity 盲化並記錄 adjudication。
4. 對專業使用者的 rubric 明確區分：無理由拒答／泛用免責為錯誤，image-limited
   uncertainty、具體缺失證據與精準 review question 為正確行為。

### P2 — 維護

1. 每次 OpenClaw bump 重查 release tag 的 public Gateway docs、protocol range、
   attachment contract 與 idempotency，並跑真實 image smoke；不追 internal chunk。
2. 每季重查本文件 revision；只有可解決已觀察 failure mode 的 pattern 才進入 backlog。
3. 外部 benchmark、模型或 scorer 若改 license／DUA，預設停止取用，直到完成授權審查。

## 四大核心映射

| 核心 | 本審查帶來的具體約束 |
| --- | --- |
| Core 1 — overlay position/content/privacy | 座標空間與 DPR receipt、round-trip gate、雙層 localization metric、partial-image visible-region contract；ROI 絕不擴大。 |
| Core 2 — complete interpretation harness | 五段 receipt、strict schema、grader-failure accounting、paired perturbation、stable resume、gold isolation、worst-of-n 與 human adjudication。 |
| Core 3 — OpenClaw compatibility | 只用 `connect` + `chat.send` public Gateway；保存 negotiated protocol/idempotency/run receipt；升版依 release tag 與真實 smoke，不依 internals。 |
| Core 4 — minimal executable | 全部採用 pattern-only；不加入 LMMs-Eval、Inspect、Agents SDK、Cornerstone、Harbor、LangGraph、RadFact、SHOVIR 或模型權重。 |

## 醫療證據與發布聲明邊界

三份原始／官方 reporting guidance 用來界定「何時能談臨床證據」，不當作 scorer：

- [CLAIM 2024 Update](https://doi.org/10.1148/ryai.240300) 要求透明報告 medical
  imaging AI 的資料分割層級、reference standard、test set 與 reproducibility；
  它是 reporting checklist，不是分數。
- [STARD-AI](https://doi.org/10.1038/s41591-025-03953-8)（published 2025-09-15，
  2026-07-13 有 author correction）要求診斷準確性研究說清楚資料、index test、
  reference standard、bias/fairness 與 applicability。
- [DECIDE-AI](https://doi.org/10.1038/s41591-022-01772-9)（published 2022-05-18）
  針對 early live clinical evaluation，強調實際 workflow、human factors、safety
  與小規模臨床表現。

因此：10,001-case identity/resume test 只能證明 plumbing；MEETI report labels 可做
held-out內容 canary，但沒有專科醫師 localization reference 就不能證明 bbox 臨床
準確；100+ 張真實 Luna 批次仍是 engineering/retrospective evaluation。要宣稱
臨床有效、優於醫師或 deployment-ready，仍需明確 intended use、獨立外部資料、
合適 reference standard、專科醫師 reader study，以及依研究設計進行 prospective
workflow evaluation。

## 明確不採用項目

- 不把任何 GitHub leaderboard 或 paper benchmark 分數稱為本產品臨床驗證。
- 不讓 LLM-as-judge 單獨決定 clinical correctness 或 release readiness。
- 不在公開文件、fixture、網站或 screenshot 洩漏 held-out gold／benchmark 題目。
- 不複製 CC-BY-NC／CC-BY-NC-ND code 到可能商用的產品。
- 不新增另一套 agent runtime、remote trace backend、GPU model stack 或 DICOM
  viewer framework。
- 不以 full-screen capture、ROI 外像素或 PHI 換取更高模型分數。
- 不為了縮小 bundle 移除 OpenClaw internal `dist` chunks，也不從它們推導協定。
