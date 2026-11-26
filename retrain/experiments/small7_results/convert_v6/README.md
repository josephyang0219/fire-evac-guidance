# v6（7 類）轉檔包：給 Realtek 線上 AI 模型轉換工具

2026-11-27。用第 6 輪權重 `../weights/small7_v6_best.pt` 做出來的，要轉成板子用的 `.nb`。

| 檔案 | 說明 |
|---|---|
| `best_reparam_v6_pt.zip` | 重參數化後的部署權重（zip 裡是 `best_reparam.pt`，12.3 MB，SHA-256 `a64ea767…66ecd3`）。用 `retrain/train/reparam.py` ＋ `retrain/config/yolov7-tiny-fire7-deploy.yaml` 在使用者電腦做的；訓練版和部署版輸出最大差異 2.1e-4（< 1e-3，等價） |
| `quant_images.zip` | 量化校正圖 10 張，576×320 |
| `quant_images/` | 同上，解開的圖，方便先看 |

## 轉檔設定（線上工具）

- 模型類型：**YOLOv7-TINY-Pytorch**
- 上傳：`best_reparam_v6_pt.zip`
- 輸入尺寸：**576×320**（和韌體 NNW/NNH 一樣）
- 量化：**UINT8**
- 類別數：**7**（0 cabinet 1 boxes 2 furniture 3 rubble 4 gate 5 smoke 6 person）
- 校正圖：`quant_images.zip`

## 校正圖怎麼挑的

| 檔名 | 來源 | 張數 |
|---|---|---|
| `real_436B*.jpg` | 實景：2F 西（436B）裝在模型裡的空場景快照（11/25） | 2 |
| `render_smoke*.jpg` | v6 訓練用渲染圖，有流體模擬的煙（含整片起霧） | 3 |
| `render_obstacles*.jpg` | v6 訓練用渲染圖，3 個以上障礙物或閘門 | 3 |
| `render_empty*.jpg` | v6 空場景渲染圖 | 2 |

- 實景快照是 640×480，先上下各裁掉一點變 16:9（640×360），再縮成 576×320。
- 其他板子 11/25 抓到的快照是鏡頭朝向教室天花板（還沒裝進模型），不代表實際畫面，**沒有用**。
- 實景只有 2 張，因為還沒開始實拍。舊模型的校正圖全是暗的渲染圖，這是實景誤判的原因之一；**實拍（`docs/實拍訓練流程_2026-11-25.md`）之後，重訓的模型要改用實拍照片當校正圖**。

## 轉完之後

1. 下載的 `.nb` **不要覆蓋**現在上板的模型，另存成例如 `yolov7_tiny_v6_576x320.nb`。
2. 檢查類別數：`python fire_evac_v2/tools/check_sdk_model.py <下載的 .nb> --expect-classes 7`。
3. 要上板測試時才放進 SD 卡的 `NN_MDL/yolov7_tiny.nb`（記得先備份原本那個），測完換回來。
4. 注意：v6 只用合成資料訓練，實景誤判仍然會有（11/25 測 2F 西空場景：v6 誤判櫃子 0.51，舊模型誤判煙 0.68）。這版是給大家比較用的，正式上板等實拍重訓。
