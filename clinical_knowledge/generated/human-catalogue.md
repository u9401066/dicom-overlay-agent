# Clinical knowledge catalogue

Registry SHA-256: `d22a03e037293636c86ca029452a8486f93f5625cb5655b3381088b8cc1fc22c`
Registry digest scope: `canonical-input-documents-v1`

## 明確氣胸宣稱卻低估嚴重度

Rule: `cxr.pneumothorax_undercall.v1` v1.0.0 (CXR)

若輸出肯定提及 pneumothorax，整體結果不可仍為 normal/info。規則修正 模型自身的分流矛盾並要求 critical 人工複核；它不從關鍵字推斷大小、 張力生理或治療方式，這些必須由可見影像與臨床狀態分別判斷。

### Differential workflow

1. **verify_assertion** — 區分肯定、否定與不確定的氣胸敘述；只有肯定宣稱觸發 undercall 規則，possible 氣胸仍應保留鑑別與適當 review，而非冒充確診。
1. **inspect_pleural_evidence** — 在原圖檢查 visceral pleural line、線外肺紋理消失、肺尖及肋膈角， 同時排除皮膚皺褶、衣物、床單、scapular edge 與過度曝光假象。
1. **assess_extent_and_tension_signs** — 記錄可見側別與範圍，檢查縱膈偏移、橫膈壓低及血流動力學資訊； 未提供臨床狀態時不得單憑影像把一般氣胸改稱張力性氣胸。
1. **check_capture_completeness** — 若肺尖或外側胸壁被 ROI 裁切，將該區域標成 not assessable；不以 被裁掉區域「未見 pleural line」作陰性結論。
1. **reconcile_critical_review** — 對齊 pleura checklist、finding、summary、critical severity、bbox 與 review reason，確保框選的是實際胸膜證據而非整張胸片或文字標籤。

### Sources

- BTS: Guideline for Pleural Disease (2023), Spontaneous pneumothorax guideline and clinical pathways — https://www.brit-thoracic.org.uk/clinical-resources/guidelines/pleural-disease/

## 明確縱膈變寬所見卻維持正常分流

Rule: `cxr.widened_mediastinum.v1` v1.0.0 (CXR)

若輸出肯定描述 widened mediastinum，整體結果不可仍為 normal/info；至少 升為 warning 並由專科醫師核對急性主動脈疾病及其他原因。此徵象非特異， 胸片也不能單獨確認或排除 acute aortic syndrome。

### Differential workflow

1. **verify_projection_quality** — 先確認 AP/PA、旋轉、吸氣程度、放大與 supine technique；portable AP 與旋轉可造成假性縱膈增寬，品質限制必須寫入判讀。
1. **verify_mediastinal_observation** — 在原圖確認縱膈輪廓是否確實增寬或異常，bbox 應涵蓋相關輪廓而非整張 胸片，並檢查與既往影像是否有可用的改變資訊。
1. **inspect_supporting_aortic_signs** — 檢查 aortic contour、左側 apical cap、氣管或胃管偏移、胸腔積液等 支持線索；缺少任何單一徵象不得用來排除主動脈疾病。
1. **compare_mediastinal_differentials** — 比較技術性放大、主動脈迂曲/擴張、腫塊、淋巴結、縱膈脂肪、出血及 其他結構性原因，避免把非特異胸片徵象直接等同主動脈剝離。
1. **integrate_clinical_risk** — 列出需由醫師整合的急性胸背痛、脈搏或血壓差、神經症狀與 definitive imaging；只提供具體下一步資訊，不以泛用免責段落取代影像判讀。
1. **reconcile_warning_review** — 對齊 mediastinum、summary、warning severity 與 review reason；若有更 直接的危急可見證據，依該 finding 的較高嚴重度處理。

### Sources

- ACR: Appropriateness Criteria — Suspected Acute Aortic Syndrome (2021), Variant 1, acute chest pain with suspected acute aortic syndrome — https://acsearch.acr.org/docs/69402/Narrative

## 明確 STEMI／急性心肌損傷宣稱卻低估嚴重度

Rule: `ekg.explicit_stemi_undercall.v1` v1.0.0 (EKG)

若輸出已肯定宣稱 STEMI、急性心肌梗塞或急性心肌損傷，整體結果不可仍 為 normal/info。規則只修正模型自身的語意矛盾；心肌梗塞的臨床確診仍 需要心肌損傷證據與缺血脈絡，不能由截圖單獨完成。

### Differential workflow

1. **classify_assertion** — 將關鍵文字分成肯定、否定與不確定；「possible」「cannot exclude」 或鑑別列表不可誤算成肯定診斷，否定敘述也不得觸發。
1. **verify_visible_pattern** — 回到原圖確認已宣稱的 ST/T/Q-wave 或 reciprocal morphology 是否在 已識別的相鄰導程可見，並檢查框選位置是否對準該證據。
1. **assess_capture_completeness** — 判斷導程、校正、時間軸與影像品質是否足以支持範圍；若不完整，維持 緊急分流但把無法判斷的 territory/axis 標成 not assessable。
1. **separate_injury_from_infarction** — 將「影像上的急性損傷/缺血型態」與「需 biomarkers、症狀或影像學 證據整合的 MI 診斷」分開，避免過度確診同時保留時間敏感性。
1. **reconcile_all_outputs** — 對齊 findings、checklist、summary、severity、review_required 與理由； 肯定急性宣稱必須升至 critical 並呈現可追溯證據。

### Sources

- ESC/ACC/AHA/WHF: Fourth Universal Definition of Myocardial Infarction (2018), Sections 2 and 4, myocardial injury and clinical criteria for MI — https://academic.oup.com/eurheartj/article/40/3/237/5079081
- ACC/AHA/ACEP/NAEMSP/SCAI: Guideline for the Management of Patients With Acute Coronary Syndromes (2025), Scope covering acute management of unstable angina, NSTEMI, and STEMI — https://professional.heart.org/en/science-news/2025-guideline-for-the-management-of-patients-with-acute-coronary-syndromes

## 高尖 T 波所見卻維持正常分流

Rule: `ekg.peaked_t_hyperkalemia.v1` v1.0.0 (EKG)

輸出若肯定描述 peaked/tented T waves，整體結果不可仍為 normal/info； 應提示高血鉀與其他急性再極化異常的鑑別。ECG 所見的敏感度與特異度 都有限，規則不得把高尖 T 波單獨轉成確定高血鉀診斷。

### Differential workflow

1. **verify_t_morphology** — 確認 T 波是否在多個可見導程可重複、是否相對狹窄對稱且超出相鄰 baseline，而不是增益、裁切、重疊或單一雜訊造成的假象。
1. **inventory_associated_changes** — 同步檢查 P 波可見度、PR、QRS 寬度、ST-T 融合、節律與心率；將缺失 導程或不可測 interval 明確標示，不自行補值。
1. **compare_repolarization_differentials** — 比較高血鉀、超急性缺血、早期再極化、LVH/strain 與技術因素；若有 regional contiguous change 或 reciprocal change，優先處理急性缺血。
1. **request_clinical_correlation** — 建議專科醫師結合血鉀、腎功能、藥物、症狀與 serial ECG；這些資料若 未提供，只列為具體待核對項目，不輸出泛用免責文字。
1. **reconcile_warning_floor** — 對齊 t_wave、conduction、interval findings 與 summary；肯定高尖 T 波 且原分流偏低時至少升為 warning 並要求人工複核。

### Sources

- AHA: Adult and Pediatric Special Circumstances of Resuscitation (2025), Section 15 Hyperkalemia, ECG abnormalities and diagnostic limitations — https://cpr.heart.org/en/resuscitation-science/cpr-and-ecc-guidelines/adult-and-pediatric-special-circumstances-of-resuscitation

## 未排除超急性缺血性 T 波卻未進入急症分流

Rule: `ekg.possible_hyperacute_ischemia_triage.v1` v1.0.0 (EKG)

當輸出保留 hyperacute ischemia／hyperacute ischemic T-wave 的非否定 鑑別，應保留不確定性但升級為 critical 專科複核。規則不把「possible」 改寫成肯定診斷，而是避免時間敏感的鑑別被低嚴重度掩蓋。

### Differential workflow

1. **verify_regional_morphology** — 確認寬大、對稱或相對突出的 T 波是否在相鄰可見導程形成區域性型態， 並檢查對應 ST、reciprocal change 與 bbox 是否正確。
1. **assess_temporal_and_capture_limits** — 檢查是否只有單張、缺導程、裁切或低解析度；缺少 serial change 時不 假定穩定，未涵蓋的 territory 標示 not assessable。
1. **compare_urgent_mimics** — 比較急性冠狀動脈阻塞、高血鉀、早期再極化、LVH/strain、傳導異常與 技術因素；具區域性或 reciprocal 證據時優先處理缺血風險。
1. **integrate_available_context** — 整合症狀、既往 ECG、心肌標記與時間軸；未提供的資料列為具體待確認 項目，不因資料缺乏拒絕完成可見影像判讀。
1. **preserve_uncertainty_with_urgency** — summary 使用明確的 cautious differential，severity 設 critical、 review_required=true，並指出哪些可見證據與缺失資料決定此分流。

### Sources

- ACC/AHA/ACEP/NAEMSP/SCAI: Guideline for the Management of Patients With Acute Coronary Syndromes (2025), Scope covering acute management and risk stratification across ACS — https://professional.heart.org/en/science-news/2025-guideline-for-the-management-of-patients-with-acute-coronary-syndromes

## ST 段抬高所見與整體分流不一致

Rule: `ekg.st_elevation_not_flagged.v1` v1.0.0 (EKG)

當可見 ST segment 軸已描述抬高且狀態不正常，整體結果仍標為 normal/info 時，至少需要專科醫師複核。這是輸出一致性安全網；ST 抬高本身不等同 STEMI，也不可只憑截圖宣告心肌梗塞。

### Differential workflow

1. **verify_capture_support** — 先確認 ROI、校正標記、導程標籤與基線是否可見；缺導程、裁切或 artifact 必須逐項記錄為限制，不得把未見區域當作陰性證據。
1. **verify_st_observation** — 在實際可見導程確認 ST 偏移是否可重複、是否出現在相鄰導程，並將 觀察到的導程與定位寫清楚；不以單一模糊片段外推全導程。
1. **compare_st_mimics** — 比較急性缺血與早期再極化、LVH/strain、束支傳導阻滯、心室節律、 心包炎及基線漂移等替代解釋，保留仍無法由影像排除的鑑別。
1. **seek_supporting_context** — 檢查 reciprocal change、動態變化與症狀、serial ECG、心肌標記等 可取得資訊；截圖沒有的臨床資料要列為待補資料而非自行臆測。
1. **reconcile_triage** — 對齊 st_segment、stemi_pattern、ischemia、summary 與 severity；若 目前僅能確認 ST 抬高所見，維持鑑別語句並要求人工複核。

### Sources

- ESC/ACC/AHA/WHF: Fourth Universal Definition of Myocardial Infarction (2018), Sections 2 and 4, myocardial injury and clinical criteria for MI — https://academic.oup.com/eurheartj/article/40/3/237/5079081

## 異常 ST 抬高伴未解急性損傷鑑別卻未進入急症分流

Rule: `ekg.uncertain_acute_injury_with_st_elevation_triage.v1` v1.0.0 (EKG)

非正常 ST-elevation 軸若同時保留急性缺血、急性心肌損傷或急性冠狀動脈 阻塞的非否定鑑別，不可停留在 warning 以下。規則維持 diagnostic uncertainty，只把時間敏感的人工複核提升至 critical。

### Differential workflow

1. **establish_st_evidence** — 在具標籤的可見導程確認 ST 抬高與狀態，檢查相鄰導程、一致的 J-point 基線與 reciprocal change，並排除 bbox 對錯導程或框到文字區。
1. **classify_acute_differential** — 區分肯定、否定及仍未解的 acute injury/ischemia/occlusion 敘述；只有 非否定鑑別配合異常 ST 軸才啟動此規則。
1. **compare_st_elevation_differentials** — 系統比較早期再極化、心包炎、LVH/strain、束支傳導阻滯、心室節律、 aneurysm pattern、電解質與 artifact，不把單一特徵當成排除證據。
1. **check_territory_completeness** — 對照已見導程與缺失導程；裁切影像只允許描述已見區域，不得聲稱未見 reciprocal change 或其他 territory 正常。
1. **reconcile_critical_triage** — 維持「未排除」層級，將 findings/checklist/summary 協調為 critical review，並列出 serial ECG、症狀與 biomarkers 等具體待整合資訊。

### Sources

- ACC/AHA/ACEP/NAEMSP/SCAI: Guideline for the Management of Patients With Acute Coronary Syndromes (2025), Acute management and risk stratification across STEMI and NSTE-ACS — https://professional.heart.org/en/science-news/2025-guideline-for-the-management-of-patients-with-acute-coronary-syndromes
- ESC/ACC/AHA/WHF: Fourth Universal Definition of Myocardial Infarction (2018), Sections 2 and 4, myocardial injury and clinical criteria for MI — https://academic.oup.com/eurheartj/article/40/3/237/5079081
