# Colab 操作步驟（7 類模型重訓）

照著做就能從「上傳檔案」一路走到「板子跑新模型」。筆記本是 `retrain/train/colab_train.ipynb`。
類別順序：`0 櫃子 1 紙箱 2 桌椅 3 瓦礫 4 閘門 5 煙 6 人偶`（英文 cabinet, boxes, furniture, rubble, gate, smoke, person）。

## 總覽與時間

| 步驟 | 在哪裡 | 大約時間 |
|---|---|---|
| 1. 上傳檔案到 Google Drive | 瀏覽器 | 5–15 分鐘（約 120 MB，看網速） |
| 2. 開筆記本、選 GPU | Colab | 1 分鐘 |
| 3. 執行第 1–4 格（GPU、Drive、YOLOv7、解壓） | Colab | 3–5 分鐘 |
| 4. 執行第 5 格：訓練 80 輪 | Colab | **約 1.5–2.5 小時**（T4；可以先設 `EPOCHS = 5` 跑通，約 8 分鐘） |
| 5. 執行第 6–7 格：曲線、混淆矩陣、誤判檢查 | Colab | 3 分鐘 |
| 6. 執行第 8–9 格：重參數化、打包、下載 | Colab | 2 分鐘 |
| 7. Realtek 線上轉檔 | amebaiot.com | 填表 5 分鐘＋等候（依網站排隊，通常幾十分鐘，完成會寄信） |
| 8. 換進 SDK、改韌體、燒錄 | Arduino IDE | 15 分鐘 |

訓練時間是估計值（約 3000 張訓練圖、batch 32、每輪約 95 步），實際以 Colab 顯示為準。

## 1. 上傳到 Google Drive

在 Drive 的「我的雲端硬碟」建立資料夾 **`fire_retrain`**，把本機
`C:\Users\User\Documents\fire_retrain_data\upload_to_drive\` 裡的 **7 個檔案**全部拖進去：

| 檔案 | 用途 |
|---|---|
| `fire7.zip` | 資料集（train / val、data.yaml） |
| `fire7_quant_images.zip` | 30 張量化校正圖，第 9 格會一起打包，轉檔時上傳 |
| `best.pt` | 舊的 6 類權重，訓練起點 |
| `yolov7-tiny-fire7.yaml` | 訓練用網路（nc = 7） |
| `yolov7-tiny-fire7-deploy.yaml` | 部署用網路（重參數化用） |
| `hyp.ft7.yaml` | 超參數 |
| `reparam.py` | 重參數化腳本 |

同一個資料夾裡也有 `colab_train.ipynb`：在 Drive 上對它按右鍵 → 選「開啟工具 → Google Colaboratory」。也可以到 colab.research.google.com → 上傳。

## 2. 開始前選 GPU

Colab 上方選單 **執行階段 → 變更執行階段類型 → T4 GPU → 儲存**。

## 3–6. 依序執行每一格

從上到下按 Shift+Enter。每格上方都有中文說明，重點：

- **第 2 格**會跳出 Google 授權，允許存取 Drive。如果缺檔案，會列出缺哪幾個。
- **第 5 格（訓練）**：訓練結果直接存在 Drive 的 `fire_retrain/runs/fire7/`。
  - 如果斷線或逾時：重新連線後，再執行第 1–4 格，接著把第 5 格的 `RESUME = False` 改成 `True` 再執行，就會從上次接續。
  - 如果出現 `CUDA out of memory`：把 `BATCH = 32` 改成 16。
- **第 6 格**會顯示 3 張圖：
  - 訓練曲線
  - PR 曲線：圖例裡有各類 mAP
  - 混淆矩陣：重點看 `background` 那一列，數字越小代表誤判越少
- **第 7 格**會印出「val 負樣本裡有幾張在門檻 0.4 下出現框」。舊模型在教室實景幾乎每張都有框。
- **第 8 格**印出「已存 best_reparam.pt」就代表重參數化正確：腳本比對過訓練版和部署版的輸出，差異 < 1e-3 才會存檔。下面那行 mAP 應和第 6 格相同。
- **第 9 格**會下載兩個 zip 到電腦，也存一份在 Drive 的 `fire_retrain/convert_upload/`。

## 7. Realtek 線上轉檔

到 amebaiot.com 的 **AI Model Conversion** 頁面：

| 欄位 | 填寫 |
|---|---|
| 模型類型 | **YOLOv7-TINY-Pytorch** |
| 模型檔 | `best_reparam_pt.zip` |
| 輸入尺寸 | **寬 576 × 高 320** |
| 量化 | **UINT8** |
| 類別數 | **7** |
| 量化校正圖 | **`fire7_quant_images.zip`** |

量化校正圖說明：

- 這 30 張 576×320 的圖從 val 平均挑出，包含偏亮的渲染圖和空場景。
- **不要用舊的 `convert_upload/quant_images.zip`**：那 10 張是很暗的渲染圖，量化範圍會照暗圖估計，這可能是實景誤判的原因之一。
- 之後有實拍照片時，重跑 `make_dataset.py --quant 30`，實拍照片也會被挑進去。

## 8. 收到 .nb 之後換進 SDK

1. **備份目前的 6 類模型**：到 `%LOCALAPPDATA%\Arduino15\packages\ideasHatch\hardware\AmebaPro2\4.0.15-Release\variants\common_nn_models\`，把 `yolov7_tiny.nb` 改名成 `yolov7_tiny.nb.fire6_backup`。原本的 COCO 模型已經備份成 `yolov7_tiny.nb.coco_backup`，不要動。
2. **放入新模型**：把收到的 .nb 改名成 `yolov7_tiny.nb`，複製兩份：
   - 上面的 `common_nn_models\`
   - 韌體資料夾（和 `.ino` 同一層，例如 `fire_evac_v2/firmware/hub_model_test/`）
3. **改韌體成 7 類**（`hub_model_test.ino`、`hub_node.ino`）：
   - `MY_CLASSES[6]` → `MY_CLASSES[7]`，最後加 `"person"`；`MY_CLASSES_ZH` 加 `"人偶"`
   - `CLASS_PIN` 加第 7 個腳位。沒有多的 LED 就填 `-1`，並在 `digitalWrite` 前跳過 -1
   - 所有 `k < 6`、`r.type() < 6` 改成 `< 7`
   - `NNW 576`、`NNH 320` 不用改
4. Arduino IDE → Tools → **NN Model Load From: Flash** → 燒錄。
5. 序列埠看偵測清單，RTSP 看畫面框。依 `火場模型上機測試進度_2026-11-04晚.md`，門檻調回 0.4。

## 還原

要換回舊模型時，把 `.fire6_backup`（舊 6 類）或 `.coco_backup`（官方範例）改回 `yolov7_tiny.nb`。
