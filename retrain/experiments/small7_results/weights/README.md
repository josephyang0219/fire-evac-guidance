# 7 類小規模補訓的權重（2026-11-25）

| 檔案 | 說明 | SHA-256 |
|---|---|---|
| `small7_v6_best.pt` | **第 6 輪（v6）最佳權重**：7 類（0 cabinet 1 boxes 2 furniture 3 rubble 4 gate 5 smoke 6 person），yolov7-tiny，輸入 576×576。流體模擬煙＋煙框不限大小，450＋60 張 train、50 輪 | `79db27ba88bca40b1679af5daddf3a65cb9e820250a4ca524afdcb6be72114ce` |
| `best6to7.pt` | 訓練起點：舊 6 類 `model/weights/best.pt` 的偵測頭用 `retrain/tools/head_transplant.py` 搬到 7 類模型（只有 person 是新的） | `eff8ed827b1b37a2ed442f7fed21892a9ac5b2bb97a3118a7ab7ffe3b4ca3d4b` |

**v6 成績**（AP@0.5，合成 val；詳見上一層 `README.md` 的 v6）

- v6 val（模擬煙，train 沒用過的 8 組模擬）：全部 0.734，煙 0.685（conf 0.4：召回 59%、precision 89%）
- v4 val：全部 0.768；櫃子 0.769、紙箱 0.815、桌椅 0.906、瓦礫 0.893、閘門 0.934、人偶 0.958

**注意：這是可行性評估用的權重，不是上板用的。**

- 只有 1F 的合成圖（450 張）、50 輪；沒有實拍照片，實景表現未知（舊 6 類模型合成 val 0.78、實景卻大量誤判）。
- 還沒重參數化、轉 `.nb`、量化。要試著上板，流程照 `retrain/train/訓練與轉檔步驟.md`，並用 `fire_evac_v2/tools/check_sdk_model.py --expect-classes 7` 檢查。

**重現**：`retrain/experiments/small_retrain_pc.py`，設定在上一層 `README.md` 的 v5／v6；訓練參數在 `../logs_v6/opt_v6.yaml`、`hyp_v6.yaml`，每輪分數在 `results_v6.txt`，評估輸出在 `eval_*.log`（`data_v6.yaml` 的路徑是使用者電腦上的）。
