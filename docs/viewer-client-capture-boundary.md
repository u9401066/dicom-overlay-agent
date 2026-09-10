# Viewer 客戶區擷取邊界

## 問題

ROI 是相對 Viewer 視窗的使用者選區。視窗縮小時，四邊排除距離會按比例向內
取整，但 Windows 的標題列／邊框不一定同比縮小。因此「仍在外視窗內」不等於
「仍在影像客戶區內」。標題列可能帶有敏感資訊，不應成為推論附件的一部分。

例如參考視窗 1522×1137、上排除 45 px；較短圖片使視窗變成 1522×917 時，上
排除會縮為 37 px。若客戶區仍從頂端 45 px 開始，就會露出 8 px 非影像區。
這是合成幾何回歸，沒有擷取或儲存含 PHI 的標題列。

## 防護契約

`ScreenMonitor.verify_capture_target` 除了既有的視窗身份、位置、外框與遮擋
檢查，還讀取 [GetClientRect](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getclientrect)
並用 [ClientToScreen](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-clienttoscreen)
換到螢幕 device coordinates。右／下邊界是 exclusive；負座標有效，不再乘 Qt DPR。

- ROI 跨入標題列或任一邊框，即使只有 1 px，也回報
  `roi_outside_viewer_client`，停止送圖。
- 無法取得有效客戶區或客戶區與外框矛盾時，fail closed；Win32 exception 的
  內文不傳入日誌或 UI。
- 不自動裁成交集、不移動、不放大已選 ROI；使用者需在 Viewer 內重新確認
  安全影像範圍。無框 Viewer 的全客戶區仍可使用原先明確選定的 ROI。
- 擷取前、擷取後都檢查。任一時點失敗則清除 review snapshot，且不呼叫模型。
  畫面提示「ROI 跨入 Viewer 標題列或邊框，未送出影像」。

這不改 bbox 映射、domain 依賴、結果 schema、模型或 OpenClaw 通訊，也不加入
依賴。正常、完全落在客戶區內的 ROI 不改變。

## 已驗證／尚未驗證

新增測試在修正前重現 10 項失敗；修正後 98 項 capture／agent／ROI 測試通過。
包括 1 px 四邊、負座標、縮短視窗但標題列不變、空客戶區、API 失敗、無框
視窗，以及擷取前／後被拒絕時模型呼叫數必須為零。

2026-09-10 14:14 UTC 對正在使用的 Viewer 做 **唯讀原生 Win32** 檢查：DPI 144
（150%），外框 `(19,30,1522,1136)`、客戶區 `(30,75,1500,1080)`。現有安全 ROI
通過；四個跨入邊框 1 px 的矩形均被新 guard 拒絕。沒有移動 Viewer、擷取新
畫面或呼叫模型；不計入實機判讀案例。

完整 unit／smoke／mock integration 回歸：**1,406 通過、6 個具名略過**，
166.24 秒。略過為本 worktree 未放置的 portable Node／frozen cohort，以及
opt-in 封裝／原生畫面擷取檢查；Ruff 通過。未用這些略過取代上述原生幾何證據。

這仍不是原子式桌面擷取，也無法知道客戶區內是否顯示 PHI、工具列或重新排版
的病人資訊。原有去識別 ROI 仍是必要防線；不能把 client containment 宣稱成
全自動去識別。真實跨 DPI／縮放切換、不完整 ECG 與候選版 GUI 驗收仍待執行。
