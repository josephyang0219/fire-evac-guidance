# 火場避難動態指引系統｜YOLOv7-tiny 訓練檔

## 檔案
| 路徑 | 說明 |
|---|---|
| weights/best.pt | 訓練用權重（PyTorch，含 IDetect 隱式層），驗證集 mAP@0.5 = 0.782 |
| weights/best_reparam.pt | **已重參數化**的部署權重，精度相同（已驗證 0.782），直接拿去轉 .nb |
| config/yolov7-tiny-fire.yaml | 訓練用網路結構（nc = 6） |
| config/yolov7-tiny-fire-deploy.yaml | 部署用網路結構（重參數化後） |
| config/classes.yaml | 類別：0 櫃子 1 紙箱 2 桌椅 3 瓦礫 4 閘門 5 煙 |
| config/hyp.stage1.yaml / hyp.ft.yaml | 第一階段 30 輪／續訓 36 輪的超參數 |
| logs/ | 每輪結果、曲線、混淆矩陣 |
| firmware/hub_node.ino | HUB 韌體初稿（未上機測試） |

輸入尺寸 416×416。

## 放上 HUB 8735 Ultra 的步驟
1. 把 `weights/best_reparam.pt` 上傳到 Realtek（Ameba）AI 模型轉換工具，取得 `.nb` 檔（上傳上限約 35 MB）。轉換時若要求輸入尺寸，填 416×416。
2. 把 `.nb` 改名為 `yolov7_tiny.nb`，放進 Arduino 專案資料夾（與 `hub_node.ino` 同一層）。
3. Arduino IDE：Tools → NN Model Load from → **Flash**。
4. 程式裡 `modelSelect(OBJECT_DETECTION, CUSTOMIZED_YOLOV7TINY, NA_MODEL, NA_MODEL)`（韌體初稿已寫好）。
5. 把 SDK 的 `ObjectClassList.h` 類別改成上面 6 類（順序要一致）。
6. 每片板子改 `HUB_ID`（1N/1W/1S/1E/2N/2W/2S/2E）與 `NODE`（N/W/S/E），再燒錄。

若 Flash 載入失敗（錯誤訊息為模型檔名不符），確認檔名是 `yolov7_tiny.nb`；仍不行可改用 SD 卡：在卡上建 `NN_MDL` 資料夾放入 .nb，Tools 改選 SD card。

## 若要自己重新訓練
用 YOLOv7 官方 repo（WongKinYiu/yolov7）：
```
python train.py --weights weights/best.pt --cfg config/yolov7-tiny-fire.yaml --data <你的data.yaml> --hyp config/hyp.ft.yaml --epochs 30 --batch-size 16 --img-size 416 416
```
`data.yaml` 的 names 須與 classes.yaml 相同順序。補訓實拍照片時，用 best.pt 接續即可。
