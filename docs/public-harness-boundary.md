# Public Harness Boundary

本文件定義公開科學 harness 與私人商品程式的所有權、依賴方向及 release
gate。它是 repository policy，不是對既有版本的追溯撤銷授權，也不構成
法律或醫療意見。

## 1. 授權歷史不溯及撤回

`dicom-overlay-agent` 曾以 MIT License 發布，並自 commit
`43d17ae8a408db1ad0e744cbae7d28c99817a987` 起以 Apache License 2.0
發布。公開 harness 的初始 commit 是
`81c8efec1eb4a946dca38c57f6c700e8c5475a50`，抽取基準是商品 repo 的
`434c1fdca7a3fe40a26b307c318a8b3eddca5b01`。

將商品 repository 設為 private 只限制未來的 repository access；不撤回
已對既有 source snapshots 授予的 MIT 或 Apache-2.0 權利。不得把曾公開
的 snapshots 描述成重新取得排他性的 proprietary source。未來從未公開
的商品程式可以維持非公開，但仍須確認作者權利及所有第三方授權，並保留
upstream license、copyright 與 NOTICE。

## 2. 公開與私人所有權

Public harness 擁有：

- provider-neutral models、schemas、protocols 與 agent skills；
- input/QC/output validation、multi-pass 與 evidence-ledger logic；
- provenance、evaluation 與 deterministic synthetic-fixture tooling；
- 不依賴商品 runtime 的 analyzer/refinement/finalizer ports。

Private product 擁有：

- PyQt desktop UI、screen/window capture、ROI 與 overlay rendering；
- OpenClaw/Gateway/plugin/MCP transport、credentials 與 product tool names；
- PACS/RIS/EHR/writeback、installer、telemetry 與 site configuration；
- commercial models/weights、governed datasets 與 screen automation。

唯一允許的方向是：

```text
private product -> public harness
```

Public package 不得 import 或動態依賴 `dicom_overlay`、PyQt6、mss、win32、
OpenClaw、transport SDK、PACS code、商品設定或 runtime state。Private
adapters 可以實作 public ports。

`third_party/medical-image-agent-harness` 是固定 commit 的公開來源。
`.agents/skills/medical-image-reading/` 是由該 submodule 產生、供
Codex/Copilot 在 parent repo 發現的 committed thin adapter；不得直接編輯，
也不得複製或分叉 canonical method。
`openclaw/workspace/skills/` 則是私人 OpenClaw runtime adapters，不是科學
方法的 source of truth。實際共通 prompt 由公開套件 resource 載入，私人
adapter 只加入受 host 綁定的工具名稱與參數。

目前私人 OpenClaw path 的產物仍是 **legacy analyzer draft**，不是可發布的
canonical result。Parser 會保留 observation/evidence ledger，但 tool/manifest
attestations 必須由 trusted host 重建；refinement ADD/CONFIRM/REVISE 會清掉
可能過期的 canonical links。尚未實作 study/provenance/ledger assembler 前，
private clinical adapter 必須由 host deterministic 標成 `incomplete` 並要求
authorized human review，且 `AnalysisResult.to_contract_payload()` 必須 fail closed。Private
`analysis_trace` 也不能直接冒充 public `workflow_events`；後者只能由 host
依固定 stage/status contract 組裝。Experimental minimal-control path 只保留
legacy envelope。

在 screen-capture product path 中，canonical source asset 若未來實作，必須
明確定義為「完成使用者 ROI/PHI crop 後、尚未 downscale 的原解析影像 bytes」。
Full screen、傳給模型的 coarse downscale 與 refinement crop 都不是同一 asset；
其 hash 及座標不得混用。Crop-local bbox 必須 remap 並在原解析 ROI 上重新取得
host-bound receipt，才可能標成 source-coordinate verified evidence。

## 3. PyQt 與商品 binary licensing gate

目前 desktop 依賴 PyQt6，PyInstaller 也會封裝 Qt modules。Repository
privacy 不會免除 distributed binary 的授權義務。專有 binary release 必須
維持 blocked，直到下列其中一條路徑經記錄及核准：

1. 取得涵蓋開發者與實際散布版本的 Riverbank Commercial License，並依
   該授權允許的 build/distribution 方法發布；
2. 以 GPLv3-compatible 條款散布組合程式並完成全部義務；或
3. 遷移 GUI binding，之後重新完成完整授權稽核。

PyQt 與其封裝的 Qt libraries 必須分別稽核；裁掉未用 module 或減少包體
不改變授權義務。每個 release 必須產生 SBOM 及完整 notices，涵蓋實際
出貨的 PyQt/Qt、OpenClaw/Node、Python/native dependencies。Repository
license 不會自動授權下載的模型、資料集或 weights。

## 4. Fixture provenance 與再散布

任何 binary image、waveform、DICOM object 或 report fixture 進入公開
harness 前，必須有 reviewed provenance record，至少記錄：

- repository-relative path 與 SHA-256；
- generator/revision，或原始 source URL/revision；
- 作者/權利人、精確 license 與 redistribution basis；
- `synthetic`、`public-clinical` 或 `restricted-clinical` 分類；
- PHI/de-identification 聲明、review date 及允許的發布 surfaces。

已知邊界資產：

- `tests/ecg_sample.jpg` 的 SHA-256 是
  `90afb7ffa28a80fbeffe6a18665e16445de65d000ee43aa43ca2d23ed8c5f172`；
  EXIF 作者為 `Etienne Grima`，但沒有可驗證的來源或再散布授權。它是
  `restricted/unverified`，不得複製到 public harness、文件、package、CI
  artifact 或商品 release。留在私人 working tree 不等於取得再散布權。
- `site/assets/synthetic-ecg.png` 的 SHA-256 是
  `334fdf2cdbbfe0b234832ac8bbbb2614795414128c6371a442b35b74cff83b22`，
  decoded RGB pixels 與 `create_sample_ekg_image()` 在目前環境的輸出完全
  一致；PNG encoded bytes 可能隨 Pillow/encoder 版本不同。只有在 fixture
  manifest 分別記錄 committed asset SHA-256、generator revision、encoder
  environment、license 與 no-PHI 聲明後，才可視為 project-created
  synthetic content。

Public CI 只能使用生成式 synthetic data，或具有明確再散布權且完成去識別
審查的資產。看不到可辨識文字，不代表已完成 de-identification 或 provenance。

## 5. Runtime state 排除

Mutable state 永遠不是 source code、fixture 或公開 harness asset。下列內容
不得進入 public repo、source archive、wheel/sdist、文件 build 或 portable
product seed：

- `openclaw-home/**`，包含 memory SQLite databases；
- DB/WAL/SHM、indexes、embedding caches；
- case prompts/responses、transcripts、logs、telemetry、review crops；
- credentials、identities、sessions/devices 與 local dataset manifests。

本次抽取時，已追蹤的 `openclaw-home/memory/main.sqlite` 沒有 indexed files、
chunks 或 embeddings，但仍是會變動的 runtime state，已從目前 index 移除並
加入 ignore。只有後續稽核在歷史 object 找到 PHI、secret 或 restricted data
時，才需要另行評估 history rewrite。

## 6. Pinning 與可重現解析

商品 repo 透過 `third_party/medical-image-agent-harness` 的 pinned gitlink
消費公開 harness。更新流程：

1. 先在 public repo 完成 code、contract、skill、license/provenance review；
2. 公開 CI 綠燈後，將 private gitlink 推進到已審查的 exact commit；
3. 執行 `uv lock`、`uv sync --reinstall-package medical-image-agent-harness` 與
   `python scripts/sync-medical-image-harness.py --write`；
4. 提交 gitlink、lockfile 與 generated `.agents` tree；
5. 在 clean environment 跑 private compatibility、unit、integration、smoke
   與 packaged-resource checks。

Release build 必須：

- 在 submodule missing、dirty 或與 indexed gitlink 不同時 fail closed；
- 從該 exact commit 建 wheel，記錄 private/public SHA、wheel SHA-256、package、
  protocol 與 schema versions；
- 從 controlled build output 驗 hash後安裝，不得 fallback 到未受控 public
  package index；
- 使用 clean environment，避免 stale `.venv` package 掩蓋 submodule 變更。

## 7. Public-export release gate

有任何一項成立就禁止公開 export：

- public code 反向依賴 private product；
- runtime DB/log/credential/clinical image/review artifact 被追蹤；
- fixture 缺 provenance 或 redistribution permission；
- model/dataset/weight license 缺失或不相容；
- public commit 與 extracted-source provenance 未記錄；
- LICENSE、NOTICE、package metadata 與 README 互相矛盾；
- public-boundary、distribution 或 cross-agent compatibility check 未通過。

## 8. Authoritative license references

- [Apache License 2.0 official text](https://www.apache.org/licenses/LICENSE-2.0.txt)
- [PyQt licensing](https://www.riverbankcomputing.com/software/pyqt/)
- [Riverbank Commercial License FAQ](https://www.riverbankcomputing.com/commercial/license-faq)
