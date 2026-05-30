# Progress (Updated: 2026-05-30)

## Done

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
