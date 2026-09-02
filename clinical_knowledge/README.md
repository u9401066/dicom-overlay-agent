# Clinical knowledge governance

這個目錄是 DICOM Overlay Agent 臨床一致性規則的唯一人工維護來源。產品定位是
協助專科醫師共讀影像：規則會抓出模型輸出內部矛盾、提升需要優先複核的項目，
但不會從關鍵字自行製造診斷，也不會改變醫師擁有最終判讀權的責任邊界。

## 單一來源與生成鏈

```text
clinical_knowledge/rules/*.rule.yaml
          + axes/*.axes.yaml
          + legacy-inventory.yaml
                    │
                    ├─ schema + semantic governance gate
                    ├─ generated/human-catalogue.md（完整人用鑑別流程）
                    ├─ generated/agent-steps.md（同 step ID 的精簡 agent 流程）
                    ├─ domain/generated_clinical_rules.py（純資料 runtime）
                    └─ application-owned clinical-knowledge.sqlite（速查投影）
```

Canonical input 是所有 `rules/*.rule.yaml`、`axes/*.axes.yaml`、
`legacy-inventory.yaml` 與 `schema/rule.schema.json`；生成的 Python、Markdown 與
SQLite 都不可手改。`canonical-input-documents-v1` digest 會雜湊每個相對路徑與
解析後內容，刻意不含生成物，避免 self-reference。Domain 只讀生成後的純資料，
不做 YAML／GUI／網路／OpenClaw I/O，維持 DDD 邊界。網站或文件若與 registry
digest 或 digest scope 不同，一律視為 stale。

## 每條規則包含什麼

- `rule_id` 與 `version`：rule ID 的 `.vN` 必須等於 semantic version major。
- `human`：完整 rationale、逐步鑑別流程、來源定位、review 日期。
- `agent.steps`：只保留模型真正要執行的步驟；每個 ID 必須映射到 human
  workflow，且不得改變順序。
- `preconditions/evidence/exclusions`：讓醫師可判斷規則為何應觸發或不觸發。
- `priority`：`product_safety_policy` 表示產品的安全分流下限，不宣稱指南直接
  規定本產品的 `warning/critical` enum；review-only 規則則用
  `clinical_consistency_review`。
- `runtime`：實際 deterministic condition、訊息、severity floor 與 review
  行為。這些資料生成 domain runtime，不再另維護一份 hard-coded rules。
- `tests` 與 `legacy`：正／負／不確定／partial case alias，以及舊 runtime ID
  的可追溯映射。

Runtime condition 是資料，不是可執行 expression。可用欄位限於 `severity`、
`all_text`、`summary` 與 `checklist.<axis>[.status]`；operator 也由 schema 與
semantic validator allow-list 控制。Unknown key、unknown axis、錯誤 operand、
過期 clinical review、未映射 runtime 或失效 pytest node 都 fail closed。

## 人用流程與 agent 流程

[human-catalogue.md](generated/human-catalogue.md) 會列出每條規則的完整判讀與
鑑別步驟，例如先核對 capture/lead/projection，再確認 morphology、比較 mimic、
整合可取得的 serial/clinical evidence，最後協調 checklist、summary、severity、
review 與 bbox。它刻意區分：

1. 截圖上可見的影像證據。
2. 因裁切、缺導程或解析度而無法判斷的部分。
3. 仍需症狀、biomarker、serial study 或 definitive imaging 才能完成的臨床
   結論。

[agent-steps.md](generated/agent-steps.md) 使用相同 step ID，但移除教學性敘述，
讓模型可以快速執行。它不得包含 eval gold、scorer aliases、泛用拒答或冗長醫療
免責樣板。

## 專業共讀輸出政策

Agent 必須完成可見影像的專業共讀，不得只因任務涉及醫療或自身是 AI 就拒答；
也不得用「僅供參考」「不能取代醫師」等重複段落占用臨床輸出。允許而且要求的
是具體限制，例如「V1–V4 被裁切，因此 anterior territory not assessable」，
以及針對該 case 的 reviewer question。Prompt contract 與 OutputValidator 兩層
都有 regression gate；具體 capture limitation 不會被誤判成拒答。

## SQLite 速查庫與 OpenClaw 邊界

Repo 內既有 `openclaw-home/memory/main.sqlite` 是 OpenClaw 私有 FTS cache；
2026-08-28 只讀稽核時 `files/chunks/embedding_cache` 均為 0，沒有 clinical
rule。Core 3 禁止依賴或寫入其內部 schema，因此它不是本產品的規則來源。

本產品改由 YAML deterministic 生成 application-owned SQLite：

```powershell
uv run python scripts/build-clinical-knowledge-sqlite.py `
  --output build/clinical-knowledge.sqlite
uv run python scripts/build-clinical-knowledge-sqlite.py `
  --output build/clinical-knowledge.sqlite --check
```

資料表包含 `rules`、`human_steps`、`agent_steps`、`sources`、
`runtime_conditions`、`lookup_terms`、`legacy_map` 與 `axes`。DB metadata 綁定
canonical registry SHA-256；verifier 逐表比對 YAML 投影，不能只靠 DB 自己宣稱
digest 正確。SQLite 使用 Python 標準庫，不增加封裝 dependency，且 DB 不含
MEETI gold、expected labels、scorer aliases 或 PHI。

`scripts/build-exe.bat` 會在 PyInstaller 前以隔離的 no-dev build environment
重新驗證 generated views、建立 DB 並再次作逐表 parity check。Portable bundle
保留 canonical YAML/schema、兩份 generated Markdown 與
`clinical_knowledge/clinical-knowledge.sqlite`；`--selfcheck` 檢查必要檔案，
bundle verifier 會從封裝內 canonical YAML/JSON 重新驗證固定 schema ID/version、
重算 registry digest 與兩份完整 generated view，再逐表、逐欄、逐列比對 SQLite
投影（另跑 `quick_check` 與 foreign-key check）；因此不能用自稱相同 digest 的
stale/空殼 DB、空殼 schema 或單獨竄改的文件通過發布。

## 維護與稽核流程

1. 在 `rules/*.rule.yaml` 修改或新增規則；不要手改任何 generated file。
2. 使用新的 rule major 時同步更新 `.vN`；保留舊版本只能以明確 retired status
   存在，不能偷偷同時啟用互相衝突的版本。
3. 更新來源的 title/version/effective date/URL/locator，以及 `reviewed_on` 與
   `review_due`。每個 severity floor 必須明示是 product safety policy。
4. 補 positive、negative、uncertain、partial tests，尤其要包含 negation、
   missing lead/crop、錯框與 normal case。
5. 生成並檢查所有 views：

   ```powershell
   uv run python scripts/validate-clinical-knowledge.py --render
   uv run python scripts/validate-clinical-knowledge.py --check-generated
   uv run python -m pytest -q tests/unit/test_clinical_knowledge_registry.py `
     tests/unit/test_clinical_rules.py `
     tests/unit/test_clinical_knowledge_sqlite.py
   ```

6. 由具相關專科資格的 reviewer 審查臨床內容；程式 schema 通過不等於醫學內容
   已獲臨床認證。審查結果、日期與 rule digest 應留在 release evidence。
7. 發布前從乾淨 worktree 重新生成、檢查 SQLite parity、跑 smoke，再確認
   packaged runtime 使用同一 registry SHA。

## 引用與授權

Registry 只保存書目資料與本專案獨立撰寫的高階判讀流程，不複製指南全文。
引用不是商業授權：部分機構（特別是 ESC）在官方頁面明示，將其 guideline
內容納入軟體、演算法或生成式 AI 可能需要正式 license。商業／臨床部署前必須
由法務或授權負責人逐一確認權利；未取得必要權利時應改用已授權來源或移除該
依據，不能把 repository citation 當作許可證。

## 目前邊界

- 現在有 7 條 deterministic consistency rules；這不是完整心電圖或胸片指南。
- Critical-first crop allocation 是跨 finding 的 application policy，仍在 Python
  中維持 budget、geometry 與 final-report invariants；它已列入 inventory 並由
  parity test 稽核，不得偽裝成單一醫學診斷規則。
- Rule engine 只依模型已輸出的結構化內容檢查一致性，不會重新觀看影像或移動
  bbox；影像定位仍由原本的 bbox validator、ROI mapping 與人工 overlay review
  負責。
