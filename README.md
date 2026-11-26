# 火場避難動態指引系統（Fire Evacuation Dynamic Guidance）

中央大學「智慧節能實作」專題｜組員：楊恩祈、許仲愷、張桄翰
互動式簡報：https://waipjy.github.io/fire-evac-presentation/

在 1:40 的兩層實體建築模型裡，用 HUB-8735 Ultra 的鏡頭與 NPU 偵測火、煙、障礙物和人偶。
筆電上的伺服器根據偵測結果算出最短的安全路徑，再讓每個路口的 OLED 顯示該往哪個方向走。

> **第一次接手，請依序讀：**
> 1. 本頁：架構、目前進度、檔案在哪。
> 2. [`docs/專案架構與任務板.md`](docs/專案架構與任務板.md)：子系統狀態、實體模型尺寸、已定決策、待辦、待決定事項。
> 3. [`docs/上機測試進度_2026-11-04晚.md`](docs/上機測試進度_2026-11-04晚.md)：最近一次上機測試做到哪、怎麼重現。

---

## 系統架構

```
1:40 實體模型（physical_model/fire_model.blend，兩層 × 井字型走廊）
  │  每層 4 台 HUB-8735 Ultra（N/E/S/W，天花板上方設備層），鏡頭 PS5268 往中心傾斜 18°
  ▼
HUB-8735 韌體
  ├─ YOLOv7-tiny（NPU，輸入 576×320）：櫃子、紙箱、桌椅、瓦礫、閘門、煙（6 類）
  ├─ 人流追蹤計數（people_flow/）
  ├─ 方向指引輸出：天花板 OLED，每台 2～3 塊（SSD1306；Wire Pin3/Pin4、Wire1 Pin0/Pin1）
  └─ Wi-Fi → 伺服器（POST 偵測結果，回應每個路口的方向）
  ▼
伺服器 fire_evac_v2/app（FastAPI；evac.py 負責路網、出口、樓梯、最短安全路徑）
  ▼
RTSP → MediaMTX → WebRTC（看鏡頭畫面）／中控台網頁
```

## 目前進度（2026-11-24）

| 子系統 | 狀態 | 下一步 |
|---|---|---|
| 火災偵測模型 | ✅ 轉檔、上板正常（載入 448 ms）　❌ 實景誤判嚴重（訓練圖是模擬渲染，sim-to-real 落差） | 補實景照片與空場景負樣本、加第 7 類 `6 = person`，重新訓練 |
| 上機測試 | ⏸ 暫停 | 鏡頭對準實體模型與障礙物道具，做受控測試 |
| 人流追蹤計數 | ✅ 程式完成，模擬準確率 97–100%，編譯通過　⏳ 尚未燒錄 | 重訓後上板，用人工計數加錄影驗證 |
| OLED 方向指引 | ✅ 已有 18 塊 OLED 個別配置圖與配置表（`wiring_8hub/oled_layout/`）。**1F、2F 各 9 塊（共 18 塊）由 8 台鏡頭 HUB 直接驅動，每台 2～3 塊**，取消 H5/H6/H7（2026-11-18，`wiring_8hub/`）：72 條母－公線（10 cm × 32＋20 cm × 40，長度都夠）、麵包板座加側窗、2F 角落外移 0.5～1.75 mm（2F 天花板要印新 STL）、18 塊鏡頭 0 像素 | Wire1 桌上實測已通過（SDA→Pin0、SCL(SCK)→Pin1，接反會完全掃不到；SDK 的 `endTransmission()` 送 0 bytes 時對任何位址都回 0，掃描要送 1 byte）。**不改焊 0x3D**：18 塊都用出廠 0x3C。角落接 Wire（SDA Pin3／SCK Pin4），十字臂接 Wire1（SDA Pin0／SCK Pin1），兩層 S 座的中心接軟體 I²C（SDA Pin18／SCK Pin19）；實測一台 HUB 三條同時驅動三塊都穩定。**I²C 根因**：HAL `i2c_write` 在資料送完前就返回，下一筆會蓋掉上一筆，畫面時好時壞但 ACK 正常；現在每筆都等 TX_COMPLETE，100 kHz 約 0.12 秒一張（SDK Wire 每 byte 固定等 200 µs，一張要 0.24 秒）。單台已通過鏡頭＋NN＋三塊 OLED 同時運作（見 hub_node 列）、量實物後切側窗；`model_oled_ceiling/` 的 OLED 位置沿用，接線部分（方案 D）已被取代 |
| 節點韌體 hub_node | ✅ **單台整合測試通過（2026-11-24）**：COM3 那塊 HUB 用 OTA 上了 hub_node `9f2581e2`，鏡頭＋NN（SD 卡 `NN_MDL/yolov7_tiny.nb`）＋三塊 OLED＋中控台同時運作，使用者目視確認。三個修正：建置腳本加 `04_CameraOption=ps5268`；NN 的 RGB 串流必須用第 3 號通道；HAL 硬體 I²C 不通，三塊 OLED 全改軟體 I²C，腳位不變，每張 18–29 ms。OTA 用 `fire_evac_v2/tools/build_hub_node.py --ota` 編譯，8 台共用一個 `ota.bin`。**SD 卡**：要 FAT／FAT32，模型路徑 `NN_MDL/yolov7_tiny.nb`；有兩張卡讀卡機和板子都讀不到，已判定不能用。中控台鏡頭改成持續更新，預覽開著時約每秒 2.6 張（原本約每秒 1 張，15 秒後會定格），偵測回報不受影響。**11-26**：四台 FW 2.9（硬體看門狗、POST 時限、每台 ISP；436B sat=30），伺服器改用 SelectorEventLoop。⏳ 其餘 7 台尚未上板 | 其餘 7 台準備 SD 卡並 USB 首燒 OTA 版；2F 接線；（可選）查 HAL I²C 失效原因；`hub_oled/` 已不用 |
| 伺服器／路網 | ✅ 每台板子回傳自己樓層的 9 個路口（2F 代號 `J2(i,j)`）；8 板 × 18 塊端對端測試 4 情境全部一致（`fire_evac_v2/sim/server_oled8_test_output.md`）；可接受 7 類模型（人偶不算障礙） | 與實機連線測試 |
| 多 OLED 韌體 `oled_fw/` | ✅ 一台 8735 驅動多塊 OLED 的韌體與圖示預覽 | 上板驗證（全部維持 0x3C，不改焊） |
| 重訓資料準備 `retrain/` | ✅ 正式資料集 3400 張、Colab 筆記本已備妥 | 在 Colab 訓練 |
| 互動式簡報 | ✅ 已上線 | 硬體定案後同步（目前寫的「地面 LED、1:100」與實體模型不符） |

**已決定（2026-11-18）：** 2F 也裝 OLED；HUB 維持 8 台。燒錄方式的檢查見 `docs/燒錄方式檢查_2026-11-18.md`，下一階段（7 類重訓、人流）評估見 `docs/下一階段評估_7類重訓與人流_2026-11-18.md`。

## 資料夾

| 路徑 | 內容 |
|---|---|
| `docs/` | 任務板、上機測試紀錄、OLED 方向指引設計 |
| `fire_evac_v2/app/` | 伺服器 `server.py`、路徑規劃 `evac.py`、中控台 `static/index.html` |
| `fire_evac_v2/firmware/` | `hub_model_test_official`（官方模型，用來確認硬體）→ `hub_model_test`（本組模型）→ `hub_node`（正式節點） |
| `fire_evac_v2/model/` | 上板用的 `best_reparam.pt`、`yolov7_tiny_576x320.nb` 和模型結構檔 |
| `fire_evac_v2/sim/` | 路徑規劃模擬與影片產生 |
| `fire_evac_v2/README.txt` | **上機步驟的詳細說明**（LED 燈號、序列埠訊息、轉檔參數） |
| `model/` | 訓練用設定（classes、hyp）、訓練紀錄（混淆矩陣、PR 曲線）、原始權重 `best.pt` |
| `people_flow/` | 人偶追蹤計數（`PeopleFlow.h`）與 PC 端模擬測試 |
| `wiring_8hub/` | **現行接線**：8 台鏡頭 HUB × 18 塊 OLED、72 條線逐條接線表、平面接線圖、麵包板座側窗與 2F 天花板 STL、檢查腳本 |
| `model_oled_ceiling/` | 1F 天花板 9 塊 OLED 穿孔＋雙面膠的位置與 STL（沿用）；其中 H5/H6/H7 接線（方案 D）已被 `wiring_8hub/` 取代；舊的外殼凹槽方案在 `舊方案_外殼凹槽_d6d65a8e/` |
| `model_oled/` | 舊方案：麵包板座外端面的 OLED 模型（0.96／0.91 吋各一份），只留作參考 |
| `oled_fw/` | 一台 8735 驅動多塊 OLED 的 Arduino 函式庫與韌體 |
| `retrain/` | 7 類模型重訓的資料準備（渲染腳本、設定、樣本、補拍清單） |
| `physical_model/fire_model.blend` | **唯一正確的實體模型**。文件裡寫的 `實體模型檔案/fire_model.blend` 就是指這個檔案 |

## 快速開始

**伺服器**
```bash
pip install fastapi "uvicorn[standard]" pillow
# 沒有 websockets，中控台會連不上（uvicorn 會警告 No supported WebSocket library）
cd fire_evac_v2/app
python server.py
```
啟動後用瀏覽器開 `http://筆電IP:8000`。

**韌體（Arduino IDE 或 arduino-cli）**
- 開發板選 `HUB-8735_ultra`（AmebaPro2 SDK 4.0.15），FQBN 是 `ideasHatch:AmebaPro2:Ameba_HUB-8735_ultra`。
- Camera 選 PS5268，NN Model Load From 選 Flash。
- Wi-Fi：把 `secrets.example.h` 複製成同資料夾的 `secrets.h` 再填入。沒有 `secrets.h` 時，程式會用預設的筆電熱點 `FireDemo`。**`secrets.h` 不要 commit。**
- 燒錄前要手動進下載模式：按住 Function，按一下 RST，再放開。
- 要跑本組模型，先把 `fire_evac_v2/model/yolov7_tiny_576x320.nb` 改名成 `yolov7_tiny.nb`，再放進 SDK 的 `variants/common_nn_models/`。燒錄前用 `python fire_evac_v2/tools/check_sdk_model.py --expect-classes 6` 確認 SDK 裡真的是本組模型。
  因為 SDK 的 ino_validation 會拒絕 CUSTOMIZED 模型，所以用 DEFAULT 名稱繞過去。
  原本的 COCO 模型記得先備份；要跑官方範例時再換回來。

**實體模型（Blender 5.2）**
- 一律開**複本**，不要直接改 `physical_model/fire_model.blend`。
- 單位 1 BU = 1 mm，場景名稱是 `Assembly_Full`。
- 1F 地板下方空間和地板圓孔是進煙測試用的，人偶由地板下的磁鐵手動拖動，所以地板上不能裝東西。
- 天花板的開孔是排煙孔和排線孔，不能拿來裝 OLED；線可以從排線孔走。

## 協作規則

- 一次做一件事，開自己的分支，完成後發 PR。
- 做完一段，就在 `docs/專案架構與任務板.md` 更新狀態，並附上證據：截圖、序列埠紀錄或 commit 連結。
- 不 commit `secrets.h`、Wi-Fi 密碼或任何金鑰。
- 不在 repo 裡放超過 50 MB 的檔案；大型渲染圖或資料集放雲端硬碟，在文件裡附連結。
