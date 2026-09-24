# EKG 影像共讀：系統化流程與 agent 對照

版本：2026-09-24；狀態：**供專科審查的設計文件，尚未完整接入 runtime**。
適用成人 ECG 截圖／掃描；不涵蓋所有兒科、先天性或罕見疾病的診斷標準。
這份文件補足端到端閱讀順序，不把目前的五條 EKG 一致性規則當成完整診斷器。
使用者是具判讀能力的臨床人員；輸出重點是所見、可能診斷、證據與下一個需要
確認的問題，不是重複泛用免責文字，也不簽署報告或下達治療。

以下是本專案獨立整理的工作流程。醫學背景使用段落旁的第一手來源；ROI、
證據 ID、優先順序、預算與人工確認是**產品政策**，不是指南對本產品的背書。
來源於 2026-09-24 核對官方網頁或出版社索引；部分期刊全文存取回傳 403，
不宣稱已逐頁審閱全文。數值閾值、診斷準則細節與軟體再利用權利仍須專科／
授權審查，不能由這份設計文件自動成為 active rule。

## 人用流程

### 01 intake — 固定輸入與判讀範圍

核對實際可見的影像、來源、去識別化聲明、ROI 與 SHA-256；確認是完整影像、
局部導程還是單一 rhythm strip。記錄掃描／旋轉／縮放，不因畫面標題有
「12-lead」就假設十二導程皆可讀。機器列印的診斷、OCR、舊報告及傳統模型
先隔離；完成盲讀觀察後才拿來比較。這是本專案
[影像證據協定](../../third_party/medical-image-agent-harness/.agents/skills/medical-image-reading/references/core-protocol.md)
的輸入政策。

### 02 quality — 先判斷每一項能否看清楚

列出可讀導程名稱、排列／是否同時記錄、紙速、增益、格線、校正標記、波形
重疊、截斷與雜訊。不可用固定位置猜導程，或把不明紙速當成 25 mm/s。
技術品質影響自動量測與解讀，包含導程放置及數位處理；參見
[AHA/ACCF/HRS ECG 技術標準 Part I](https://www.jacc.org/doi/10.1016/j.jacc.2007.01.024)。

本產品採逐軸限制：`diagnostic`、`limited`、`non_diagnostic`；完全無法讀圖時
停止病理推論，局部可讀則繼續可支持的項目。缺校正不表示所有形態都不可描述，
但不能編造 bpm、ms、mV、mm 或角度。缺一個導程也不等於整張正常。
對古老機器、單色掃描、非標準排列先辨認實際標籤，不套用資料集模板。

### 03 urgent_scan — 高風險快速掃描，但不以分流取代診斷

先看是否有可能需即時臨床複核的持續快速／緩慢節律、廣 QRS 節律、明顯
傳導異常或缺血／電解質型態；把「波形可疑」與「已確認病因」分開。
血壓、意識與脈搏不在截圖內，不能憑 ECG 宣告血流動力學穩定、休克或無脈搏。
成人高風險心律的臨床評估背景見
[AHA 2025 Adult Advanced Life Support](https://cpr.heart.org/en/resuscitation-science/cpr-and-ecc-guidelines/adult-advanced-life-support)。

產品的 critical-first 策略：先核對最高風險假說的來源框、替代解釋與缺失資料；
不要為輕微 axis 或 voltage 爭議耗盡 refinement 預算。只延後低優先精修，
不把未做的項目寫成陰性；所有十六軸仍列出已觀察、不能判讀或延後原因。
critical 是複核優先度，不能自動提升 confidence 或確診程度。

### 04 rhythm — 心率、規則性與心房活動

在可讀時間尺度下評估 rate；逐拍比較 R-R、P 波與 QRS 的關係，記錄早搏、
停頓及節律持續範圍。AF 需要對心房活動和波形作視覺確認，不能只由「不規則」
或機器標籤決定；相關原則見
[2023 ACC/AHA/ACCP/HRS AF guideline](https://www.jacc.org/doi/10.1016/j.jacc.2023.08.017)。

人用鑑別問題：不規則是 AF、竇性變異、早搏、變動傳導，還是基線／肌電干擾？
找得到一致的 P-QRS 關係嗎？一個可疑搏動是否在其他同時段導程也存在？
看不清 P 波時寫「心房活動未能辨識」，不可直接寫「P 波不存在」。

### 05 conduction — PR、QRS 與房室傳導

確認量測基礎及波形起訖，再描述 PR、QRS 和 P-QRS 配對；不要把單導程模糊
邊緣當作可靠的全導程 interval。全域 interval 與跨導程邊界的技術背景見
[AHA/ACCF/HRS Part III](https://www.jacc.org/doi/10.1016/j.jacc.2008.12.013)。

慢節律要分辨 sinus node、AV block 與其他傳導問題；被阻斷的早發心房搏動
可能造成 AV block 誤判，參見
[2018 ACC/AHA/HRS bradycardia guideline](https://www.ahajournals.org/doi/10.1161/CIR.0000000000000628)。
檢查足夠長的 strip、P 波是否提早出現、PR 是否可追蹤，以及是否真的有未傳導
P 波。片段太短時保留「傳導型態未定」，不要勉強命名阻滯亞型。

### 06 morphology — QRS 型態、軸與空間一致性

逐個已識別導程描述 QRS 極性、形狀、異常 Q／R progression 候選、起搏或
預激候選，再比較技術因素與傳導／心肌來源。軸與 territory 必須有相應已知
導程支持。導程放錯可能造成假的梗塞解讀，不能只憑 poor R progression
宣告舊梗塞；見
[ACC/AHA electrocardiography competence statement](https://www.jacc.org/doi/10.1016/S0735-1097%2801%2901680-1)。

人用鑑別問題：是導程／掃描問題、傳導改變、起搏、心室來源，還是心肌所見？
是否有真正同時段的比較，而非把不同時段列當成同一搏動？起搏尖波不清楚時，
保留「可能起搏／傳導異常」，並要求原波形或裝置資料確認。

### 07 repolarization — ST、T、QT 與缺血整合

在可讀基線與已識別導程確認 ST/T 所見、相鄰導程一致性、reciprocal／動態
支持或衝突。比較缺血、再極化變異、肥厚／strain、傳導／起搏、心包或電解質
相關替代解釋；可疑影像型態不等同已確診 MI。初始 ECG 無診斷性時，serial
ECG 與臨床／biomarker 脈絡仍重要；參見
[2025 ACS guideline](https://www.ahajournals.org/doi/pdf/10.1161/CIR.0000000000001309)
及 [Fourth Universal Definition of MI](https://www.jacc.org/doi/10.1016/j.jacc.2018.08.1038)。

QT 必須核對起訖、T/U 分界、R-R 與校正方法；寬 QRS 會影響 QT 的解釋。
不能把模糊影像的數字或機器 QTc 直接當成已驗證量測；相關技術背景見
[AHA/ACCF/HRS Part IV](https://www.jacc.org/doi/10.1016/j.jacc.2008.12.014)。
原波形、藥物／電解質與病史缺失時逐項列明，不由 T 波型態單獨確診血鉀異常。

### 08 structure — 心房／心室負荷候選

檢查 P 波、QRS voltage 及形態是否可評估，並核對增益、體表／導程與傳導因素。
ECG 的 chamber hypertrophy 指標不是影像學心室壁厚，陰性也不能排除結構病變；
背景見 [AHA/ACCF/HRS Part V](https://www.jacc.org/doi/10.1016/j.jacc.2008.12.015)。
人用輸出應區分「可見高電壓」、「符合已驗證準則的 ECG 候選」及「需要心臟
影像或其他資料確認的結構性診斷」。急迫問題尚未核對時，此步驟的額外精修
可以延後，但需保留狀態，不可暗自填為 normal。

### 09 challenge — 從來源影像核對假說與精準標記

每個正向、陰性或不確定觀察都要有可評估性與 evidence ID。由原始 ROI 取 crop，
保留 parent rectangle，將 crop-local 框回映到 normalized source coordinates。
框住支持所見的代表性短片段；不要框整列正常心電圖，也不要以診斷類別猜座標。
以上是本專案 [EKG 影像協定](../../third_party/medical-image-agent-harness/.agents/skills/medical-image-reading/references/ekg.md)
與定位政策。

每個假說明列 confirm／revise／retract／add／unevaluable 及簡短可見證據理由。
可選 OCR、digitizer 或傳統模型只在盲讀後作獨立比較，須具輸入、版本與品質
紀錄；分類器標籤不能變成定位證據。衝突未解決就保留 reviewer question。
人工新框是 reviewer-selected region，不可宣稱是模型自主精準定位。

### 10 reconcile — 產生可讀的結論、限制與後續問題

用固定順序呈現：**最重要所見／可能診斷 → 支持的導程或片段 → 主要替代解釋
→ 仍缺的資料／具體複核問題**。有支持時直接描述診斷假說；證據不足時精確指出
缺哪個訊號，不用泛用拒答替代工作。把 checklist、finding、summary、priority、
certainty 與 source bbox 對齊；僅由已核對 observation 產生結論。

例如合成的表達模板：「可見〔導程〕的〔重複所見〕，支持〔假說〕；〔替代解釋〕
仍待區分。請核對〔最能區分的原始影像／資料〕。」這不是某一病例的診斷。
不將 unresolved 或缺資料的結果顯示為 NORMAL。局部輸入與刻意延後的項目
保留 incomplete/review；模型自述 confidence 不是經校準機率。
報告修改須由使用者 Apply，Dismiss 不得改報告；詳見
[人工標記與區域問答操作](../operations/real-desktop-tests.md#manual-mark-and-per-region-conversations-development-source)。

## 十六軸覆蓋對照

這是文件與 [canonical axis inventory](../../clinical_knowledge/axes/ekg.axes.yaml)
的對照，不是宣稱每個軸都有 deterministic diagnosis rule。

| Axis | 人用步驟 | 必須保留的判讀條件或限制 |
| --- | --- | --- |
| `heart_rate` | rhythm | 時間尺度不明時不編造數字 |
| `rhythm` | rhythm | 心房活動與 QRS 關係，不只機器標籤 |
| `regularity` | rhythm | 實際觀察長度、逐拍差異及 artifact |
| `p_wave` | rhythm | 看不清與不存在分開 |
| `pr_interval` | conduction | P/QRS 邊界與量測基礎 |
| `qrs_duration` | conduction | 起訖、導程及技術支持 |
| `conduction` | conduction | 形態、起搏／預激等候選需證據 |
| `av_block` | conduction | 可追蹤 P-QRS 關係及足夠 strip |
| `axis` | morphology | 已識別的必要導程；不由局部 crop 猜角度 |
| `qrs_morphology` | morphology | 每個導程的型態與替代解釋 |
| `st_segment` | repolarization | 基線、導程與重複性 |
| `t_wave` | repolarization | 形態、分布與替代解釋 |
| `qtc_interval` | repolarization | 起訖、R-R、校正方法及量測可行性 |
| `stemi_pattern` | repolarization | 缺血型態與臨床確診分開 |
| `ischemia` | repolarization | 相鄰／動態證據、缺失 territory 與臨床脈絡 |
| `chamber_enlargement` | structure | 增益與形態限制；不是結構診斷替代品 |

## Agent 精簡步驟

以下 ID 與人用步驟一一對照；這是待接入的指令規格，不是已載入 OpenClaw 的
提示檔。不能在正在執行的 frozen cohort 中途換入。

| Step ID | 精簡執行指令 |
| --- | --- |
| `intake` | Bind immutable input, safe ROI, provenance and scope; isolate prior/tool interpretations until blind read. |
| `quality` | Inventory actual readable labels, layout, calibration and defects; gate each axis; never infer absent data. |
| `urgent_scan` | Identify time-critical candidates first; separate priority from certainty; record deferred low-priority work. |
| `rhythm` | Inspect rate support, R-R, atrial activity and P-QRS relationships; compare ectopy, conduction and artifact. |
| `conduction` | Verify interval support and conduction relationships; do not force block subtypes from insufficient strips. |
| `morphology` | Describe source-bound QRS/axis patterns; compare technical, conduction, pacing and myocardial alternatives. |
| `repolarization` | Reconcile ST/T/QT and ischemic hypotheses against visible leads, mimics and missing context; do not invent measurements. |
| `structure` | Assess supported chamber/voltage candidates; defer extra low-priority refinement explicitly when urgent work remains. |
| `challenge` | Ground each observation and box; independently compare optional tools; confirm, revise, retract, add or mark unevaluable. |
| `reconcile` | Summarize verified observations into prioritized hypotheses, limitations and reviewer questions; validate all axes and references. |

## 與 YAML／SQLite 及執行層的界線

- 現行 [YAML registry](../../clinical_knowledge/rules/core.rule.yaml) 是七條一致性
  規則的 canonical source；生成文件與 SQLite 綁定同一 digest。不要把本文件的
  新步驟手動寫進 DB，或以更改 DB 偽裝成已接入模型判讀。
- [SQLite 維護流程](../../clinical_knowledge/README.md#sqlite-速查庫與-openclaw-邊界)
  逐表檢查的是這七條規則的投影，不是本文件十步流程的臨床完整性。
- 現有 critical-first、ROI/crop 與 review 機制有各自的程式和測試；它們不能
  代替每個 clinical axis 的觀察證據或專科審查。
- 尚待接入：同一版本化 workflow source 生成 human/agent 視圖與 SQLite
  投影；host observation/evidence ledger；盲讀→獨立工具→challenge 的完整
  event 證明；每個 axis 的觀察、限制、未完成狀態及診斷概念評分。
- 更動流程須等當前 cohort 封存後，使用新版本、新 run 與未曝光案例驗證；
  不回寫已完成結果，不把重跑挑選出的成功例替換原失敗。

## 專科審查與驗收

審查人應逐步核對來源、範圍、鑑別遺漏及各數值準則的適用條件；目前沒有
「已完成專科審查」簽章。發布前仍須取得適用內容授權與臨床／產品核准。

驗收集合至少包含：清楚十二導程、單一節律條、少導程、校正缺失、導程字樣
不可讀、非標準排列／古老掃描、waveform clipping、雜訊、起搏／寬 QRS、
重要多重候選，以及陰性與近似型態。正常、陰性、不確定和不能判讀不得混為
同一類。記錄 urgent miss、unsupported assertion、框的位置及人機問答品質，
不僅 schema 或操作是否完成；評分時才開啟 gold。

`tests/smoke/test_clinical_workflow_documentation.py` 只防止步驟 ID、十六軸與
文件狀態脫節，**不驗證臨床正確性、引用授權或 runtime 已執行本流程**。
