# 路口方向協定（1F、2F 天花板各 9 塊 OLED）

舊版是「每台 HUB 驅動 2～3 個路口的 LED」，伺服器依照板子位置回傳固定順序的 `leds` 陣列。
新版改成**伺服器只回傳該樓層 9 個路口各自的方向**，每台板子用韌體裡的設定表自己挑出要顯示的路口，伺服器不管分配。

**現行布置（2026-11-18，取代方案 D）**：8 台鏡頭 HUB 直接驅動 18 塊 OLED，不用 H5/H6/H7、不用多工器。
接線、側窗、線長檢查見 [`wiring_8hub/`](../../../wiring_8hub/README.md)。

| 板子 | 顯示的路口（1F；2F 同位置，代號 `J2(i,j)`） | 接法 |
|---|---|---|
| 鏡頭 HUB 1N／2N | J(-1,1) 西北、J(0,1) 北臂 | 角落 Pin3/4；北臂 Pin0/1 |
| 鏡頭 HUB 1E／2E | J(1,1) 東北、J(1,0) 東臂 | 角落 Pin3/4；東臂 Pin0/1 |
| 鏡頭 HUB 1S／2S | J(1,-1) 東南、J(0,-1) 南臂、J(0,0) 中心 | 角落 Pin3/4；南臂 Pin0/1；中心 Pin18/19 |
| 鏡頭 HUB 1W／2W | J(-1,-1) 西南、J(-1,0) 西臂 | 角落 Pin3/4；西臂 Pin0/1 |

- **三條全部是軟體 I²C，全部出廠位址 0x3C**（不改焊，使用者 11-23 決定；三條改軟體，2026-11-24）。接線和原本一樣：
  角落 SDA Pin3（PE_4）／SCL Pin4（PE_3）；十字臂 SDA Pin0（PF_2）／SCL Pin1（PF_1）；中心 SDA Pin18（PF_5）／SCL Pin19（PF_6）。
- 伺服器回應的 `junctions` 只含該板子所在樓層的 9 個路口（1F `J(i,j)`、2F `J2(i,j)`）。
- `hub_oled/`（H5/H6/H7）已不用，保留檔案只供參考。

螢幕都由 EvacOled 函式庫驅動（`oled_fw/libraries/EvacOled`）：

| 匯流排（`SlotConfig.bus`） | 預設腳位（`setBusPins()` 可改） | 做法 | 一張 128x64 |
|---|---|---|---|
| `Bus::Wire0` | SDA 3／SCL 4 | 軟體 I²C | 約 18–29 ms |
| `Bus::Wire1` | SDA 0／SCL 1 | 軟體 I²C | 約 18–29 ms |
| `Bus::Soft` | SDA 18／SCL 19 | 軟體 I²C | 約 18–29 ms |

- 軟體 I²C 用 HAL `gpio_t`，**不用 `pinMode`**（那個每次都會印警告，一張圖要好幾秒）。資料位元推挽輸出，只有第 9 拍才把 SDA 切成輸入讀 ACK；每個 byte 都檢查 ACK，NACK 就送 STOP 結束，不會卡住。時間是 wire1_test v12（老闆分支 61febcff）三條全軟體實測的結果。
- 開機時每塊最多探測 3 次（第一輪偶爾誤判沒接）；探測一定送 2 bytes（NOP）。「更新中」畫面（`drawBitmap()`）和 `scan()` 都走同一套匯流排。
- **HAL 硬體 I²C 保留成選項，預設不用**：`oled.useHardwareI2C(true)` 會讓 Wire0／Wire1 改走 HAL `i2c_t`（100 kHz，每筆等 TX_COMPLETE，約 0.12 秒／張）。
  - wire1_test v11 單獨跑時正常。
  - 但在 hub_node 裡（鏡頭＋NN＋SD 都在跑）實測完全不通：探測 W0 0/10、W1 0/9，等待時間拉長到 20 ms 也一樣，原因未明。
  - 可能的方向（沒有證實）：鏡頭的 ISP/VOE 用自己的 `i2c_id` 控制感測器，SDK release note 提到「I2c resource protection」，可能佔用或鎖住了 I²C 控制器。
- **腳位不能被其他程式碰到**：
  - hub_node 沒有 `Wire.begin()`、`pinMode`、`digitalWrite`、`analogRead`、`SPI`、`Serial1/2`。
  - hub_node 用到的 WiFi、Multimedia（鏡頭）、NeuralNetwork、FileSystem（SD）、OTA 函式庫原始碼裡，沒有 `Wire.begin`、`i2c_init`，也沒有 PE_3／PE_4／PF_1／PF_2／PF_5／PF_6。
  - core 只有 `analogRead()` 會碰 PF_1／PF_2，hub_node 沒用。
  - LED 在 Pin25/26，LOG UART 在 Pin16/17。
  - 預先編譯的 HAL 內部無法讀到，只能等上板確認。

### 2026-11-24 整合測試找到的三個問題（已修，只到編譯通過）

| 問題 | 原因 | 修正 |
|---|---|---|
| 鏡頭沒有啟動 | `tools/build_hub_node.py` 的 FQBN 沒有 `04_CameraOption`，SDK 預設成 JXF37 | 腳本加 `--camera`（預設 `ps5268`），兩種編譯都帶 `:04_CameraOption=ps5268` |
| 鏡頭和 NN 都沒啟動，序列埠出現 `RGB output only on ch4`、`str3 paring fail`、`hal_video_str2cmd fail` | NN 的 RGB 串流用了 1 號通道；SDK 規定 RGB 只能用 3 號通道 | `CH_NN 3`（configVideoChannel／getStream／channelBegin 三處都改）；JPEG 快照留在 `CH_JPG 0`，`Camera.getImage(CH_JPG, …)` → `POST /api/dev/<MAC>/frame` 的流程不變 |
| Pin0/1、Pin3/4 的 OLED 沒有畫面（`OLEDs 1/3`） | HAL 硬體 I²C 在 hub_node 裡不通，見上 | 三條全部改軟體 I²C，接線不變 |

11-26：四台已 OTA 上板（本機版號暫記 2.7，內容＝d7be3cf 的 FW 2.6）；GitHub 版拿掉了板上 LED 閃燈，之後補回。

## 1. 路口編號

1F 井字型共 9 個路口，座標是 (i·99, j·99) mm，i、j 都是 −1、0、1。編號寫成 `J(i,j)`，例如 `J(-1,1)`：

```
            北 (+y)
  J(-1,1) ── J(0,1) ── J(1,1)
     │          │         │
  J(-1,0) ── J(0,0) ── J(1,0)     東 (+x)
     │          │         │
  J(-1,-1) ─ J(0,-1) ─ J(1,-1)
```

- 樓梯：W 樓梯在 `J(-1,1)`（西北角），E 樓梯在 `J(1,-1)`（東南角）。
- 出口：EXIT_W 在 `J(-1,0)`～`J(-1,-1)` 那段的中間，EXIT_E 在 `J(1,0)`～`J(1,1)` 那段的中間。
- 回傳陣列固定依 西北、北、東北、西、中、東、西南、南、東南 的順序（`evac.JUNCTION_ORDER`），但韌體一律**用 id 查**，不靠順序。

## 2. 方向值

| dir | 意思 | OLED 建議畫法 |
|---|---|---|
| `N` `S` `E` `W` | 往北／南／東／西走（地圖方位，+y 是北） | 箭頭 |
| `UP` / `DOWN` | 從這裡的樓梯上樓／下樓（只會出現在兩個樓梯路口） | 樓梯圖示＋上／下 |
| `X` | 沒有安全路線（例如兩個出口都被封住） | 叉叉，或「原地待援」 |

### 沒有方向時的預設畫面：全黑

| 情況 | 鏡頭 HUB（`hub_node`） | H5/H6/H7（`hub_oled`） |
|---|---|---|
| 開機、還沒收到第一筆回應 | 全黑 | 全黑 |
| 超過 3 秒（`LINK_TIMEOUT_MS`）沒有有效回應：Wi-Fi 斷、伺服器關掉、回應不完整 | 全黑（回應裡要找得到自己的路口才算有效） | 全黑（這台的路口要全部找得到才算有效） |
| 還沒在中控台指派位置 | 全黑 | —（身分在編譯時就決定，不用指派） |
| 中控台按「閃燈」 | 目前的方向閃爍；還沒有方向就閃 X | — |

選全黑的理由：斷線時伺服器已經看不到現場。如果停在舊的箭頭，可能把人帶往斷線後才起火的地方；
如果顯示 X，又等於告訴大家「沒有出路」，可能讓人原地不動。全黑代表「這裡沒有指引」，大家會改看其他還亮著的螢幕。
序列埠會印 `link lost`，方便除錯。

> 注意：OLED 裝在天花板上，人是**從下面往上看**。伺服器的 N/S/E/W 是地圖方位；換算成螢幕上的箭頭由 EvacOled 處理，
> 依據是每塊的 `top`（螢幕上緣朝哪個方位）和 `ceiling`（朝下裝，左右鏡像）。目前全部先假設上緣朝北、朝下裝，裝好後要逐塊確認。

## 3. HTTP

### 板子回報偵測（每約 200 ms）

`POST /api/dev/<MAC>/detections`，body 跟以前一樣：`{"seq","fps","fw","dets":[[cls,cx,cy,w,h,conf],...]}`

回應（伺服器輸出的是不含空白的緊湊 JSON，韌體靠這一點做字串比對）：

（以下是模擬情境 3「東側起火＋東出口北段櫃子倒下」的實際輸出，板子在 1E）

```json
{"leds":["S","W","W"],
 "junctions":[{"id":"J(-1,1)","dir":"S"},{"id":"J(0,1)","dir":"W"},{"id":"J(1,1)","dir":"W"},
              {"id":"J(-1,0)","dir":"S"},{"id":"J(0,0)","dir":"W"},{"id":"J(1,0)","dir":"S"},
              {"id":"J(-1,-1)","dir":"N"},{"id":"J(0,-1)","dir":"W"},{"id":"J(1,-1)","dir":"W"}],
 "slot":"1E","node":"E","blink":0,"snap":0}
```

| 欄位 | 說明 |
|---|---|
| `junctions` | **新**：1F 9 個路口的方向，每筆 `{id, dir}`。不管板子在哪個位置，或還沒指派位置，都會送 |
| `leds` | **舊**，保留做相容：依舊版 `HUB_LEDS` 表，列出這個位置那 2～3 個路口的方向。新韌體不用，之後會移除 |
| `slot` / `node` | 中控台指派的位置（`1N`…`2E`），`""` 表示還沒指派 |
| `blink` | 1 = 中控台按了「閃燈」 |
| `snap` | 1 = 中控台開著預覽：每 250 ms 上傳一張 JPEG 到 `/api/dev/<MAC>/frame`，loop 的等待從 150 ms 縮成 30 ms（實測約每秒 2.6 張，偵測回報沒有變少）。伺服器收到一次預覽要求會讓這個值維持 15 秒，網頁約每 5 秒重要一次 |

舊的 `POST /api/hub/<hub>/detections`、`GET /api/hub/<hub>/leds` 回應裡也會多帶 `junctions`。

### 只拿方向

`GET /api/junctions` → `{"junctions":[...]}`（格式同上）。給不做偵測的顯示節點、或除錯用。
WebSocket 廣播的 state 也多了 `junctions` 欄位。

### H5/H6/H7 輪詢與心跳

每台每 300 ms 送 `GET /api/junctions?node=H5&seq=<遞增>&fw=<版本>`（`node` 依序是 H5、H6、H7），回應跟上面一樣。
有帶 `node` 時，伺服器會把它記成顯示節點的心跳；不帶參數時行為不變。
`GET /api/displays` → `{"displays":{"H5":{"online":true,"age":0.1,"loss":0.0,"n":123,"ip":"…","fw":"holed-1.0"},"H6":{…},"H7":{…}}}`。H5、H6、H7 一定都會列出來，還沒輪詢過的就是 `online:false`。
（5 秒內有輪詢就算 online；loss 由 seq 的跳號計算），WebSocket 的 state 也多了 `displays`。
**4 台鏡頭 HUB 的協定完全沒變。**

## 4. 韌體設定表

### 鏡頭 HUB：`hub_node.ino` 的 `OLED_MAP`

每塊 OLED 一列：`{位置, SlotConfig}`。`SlotConfig` 是 EvacOled 的格式：`{路口 id, bus, addr, muxChannel, panel, top, ceiling}`，
路口 id 直接用伺服器的 `J(i,j)`，所以回應交給 `oled.applyJson()` 就會挑出自己的路口。4 台燒同一份，位置在執行時由中控台決定。

```cpp
{"1N", OLED("J(-1,1)",  Bus::Wire0, EVAC_CORNER_ADDR, kNoMux)},
{"1E", OLED("J(1,1)",   Bus::Wire0, EVAC_CORNER_ADDR, kNoMux)},
{"1S", OLED("J(1,-1)",  Bus::Wire0, EVAC_CORNER_ADDR, kNoMux)},
{"1W", OLED("J(-1,-1)", Bus::Wire0, EVAC_CORNER_ADDR, kNoMux)},
```

18 塊全部用出廠位址 0x3C，不改焊。三條匯流排各自獨立，同一條線上最多只有一塊，位址不會衝突。`EVAC_CORNER_ADDR` 巨集只是沿用舊版的寫法，留著但不需要改。中心在 S 座的軟體 I²C（`Bus::Soft`），腳位是 `hub_node.ino` 開頭的 `SOFT_SDA_PIN 18`、`SOFT_SCL_PIN 19`。每個位置最多 `MAX_OWN`（4）塊。
（若要用編譯參數改巨集：AmebaPro2 只讀 `build.extra_flags`，而且要保留 `boards.txt` 第 108 行原本的旗標，否則 `Arduino.h` 會報「Please choose between Flash or SD card」。）
2F 的位置（`2N`…）沒有列：2F 板子照樣回報偵測，只是不顯示。

### H5/H6/H7：`hub_oled.ino` 開頭的 `NODE_ID` 與 `SLOTS`

三台燒同一份。燒錄前把開頭的 `#define NODE_ID 5` 改成 5、6 或 7，對應表也寫在同一個地方：

```cpp
#define OLED(id, addr) {id, Bus::Wire0, addr, kNoMux, Panel::P128x64, Compass::N, true}
#if NODE_ID == 5
const SlotConfig SLOTS[] = {OLED("J(0,-1)", 0x3C), OLED("J(1,0)", 0x3D)};    // 南、東
#elif NODE_ID == 6
const SlotConfig SLOTS[] = {OLED("J(-1,0)", 0x3C), OLED("J(0,1)", 0x3D)};    // 西、北
#elif NODE_ID == 7
const SlotConfig SLOTS[] = {OLED("J(0,0)", 0x3C)};                           // 中心
#endif
```

每台最多 2 塊（Wire 上的 0x3C 和 0x3D）。用 0x3D 的那塊（H5 的東、H6 的北）要改焊模組背面的位址電阻。
也可以不改檔案，在編譯時加 `--build-property "build.extra_flags=-DARDUINO_SDK -DARDUINO_AMBPRO2 -DBOARD_AMB82_HUB8735 -DBOARD_AMB82_HUB8735_ULTRA {build.usb_flags} {build.menu_flags} -DNODE_ID=6"`
（原因和下面 0x3D 那段一樣：要保留板子原本的旗標）。

### 序列埠（115200）

```
slot 1E, OLEDs 1/1
[OLED J(1,1)] -> W
link lost
```

H5/H6/H7 會印 `H6 OLED online 2/2`、`[OLED 0x3D J(0,1)] -> E`、`link ok` 或 `link lost -> dark`。

## 5. 驗證

- 路線規則：`cd fire_evac_v2/sim && python junction_check.py`（需要 numpy）。共 8 種火、煙、障礙物配置，檢查每個路口：
  箭頭沒有指向牆或被封住的走廊；有其他路時不指向起火走廊；跟著箭頭走會到出口或樓梯，而且不會繞圈；
  只有真的無路可走才顯示 X。輸出在 `sim/junction_check_output.md`。
- 伺服器 HTTP：`python server_smoke_test.py`（伺服器要先跑在 8765），輸出在 `sim/server_smoke_test_output.md`。
- **9 塊 OLED 端對端**：`python server_oled_test.py`，會自己啟動伺服器（8766），測完關掉。
  - 用暫時的 `devices.json` 把 4 個假 MAC 指派到 1N/1E/1S/1W，走跟韌體相同的 `/api/dev/<MAC>/detections`；H5、H6、H7 各自用 `?node=Hn&seq=N` 輪詢，並確認 `/api/displays` 的 online 和掉包計算。
  - 每塊板子的回應照 `applyJson()` 的規則套到自己的螢幕；OLED 設定表直接從兩份 `.ino` 讀出來。
  - 結果和本機 evac、`junction_check_output.md` 對照。輸出在 `sim/server_oled_test_output.md`。
- 編譯（EvacOled 用 `--library` 帶入）：

  ```
  arduino-cli compile --config-file <yaml，directories.data = %LOCALAPPDATA%\Arduino15> --fqbn ideasHatch:AmebaPro2:Ameba_HUB-8735_ultra --library oled_fw/libraries/EvacOled fire_evac_v2/firmware/hub_node
  arduino-cli compile （同上） fire_evac_v2/firmware/hub_oled                       # H5（預設 NODE_ID 5）
  arduino-cli compile （同上） --build-property "build.extra_flags=…原本的旗標… -DNODE_ID=6" fire_evac_v2/firmware/hub_oled   # H6，H7 同理
  ```

  hub_node 的模型用 `DEFAULT_YOLOV7TINY`，讀的是 SDK 裡已經換成本組模型的 `yolov7_tiny.nb`（跟 hub_model_test、people_flow 相同的做法）。

## 6. OTA 無線更新（2026-11-23 加入，只到編譯通過，還沒上板）

不開 OTA 時，行為和原本完全相同，只有兩處不同：FW 從 2.3 改成 2.4；Wi-Fi 與伺服器位址可以用 `secrets.h` 覆蓋（不放這個檔就用原本的預設值）。

### 6.1 怎麼編譯

```
python fire_evac_v2/tools/build_hub_node.py        --config-file <yaml>    # 一般版：模型放 flash
python fire_evac_v2/tools/build_hub_node.py --ota  --config-file <yaml>    # OTA 版：模型放 SD 卡
```

- yaml 的 `directories.data` 要指向 `%LOCALAPPDATA%\Arduino15`；腳本會清掉 `LANG`／`LC_*`，build path 預設用 `%TEMP%\hbn`、`%TEMP%\hbo` 這種短的 ASCII 路徑。
- OTA 版的 FQBN 是 `ideasHatch:AmebaPro2:Ameba_HUB-8735_ultra:04_CameraOption=ps5268,08_OTAMode=Enable,06_LoadNNModelSource=sd`（一般版是 `…:04_CameraOption=ps5268`；`--camera f37` 可換鏡頭）。
- 編完會把 `ameba_pro2_tools/1.4.1/ota.bin` 立刻複製成 `fire_evac_v2/tools/ota_out/hub_node_fw<FW>_ota.bin`，因為 SDK 每次編譯都會覆蓋這個檔。`ota_out/` 不進 git。

**為什麼 OTA 版要經過腳本、不能直接編 `hub_node/`**（2026-11-23 實際驗證）：

1. SDK 的 `ino_validation` 是**照文字**掃描 `.ino` 裡的 `modelSelect(...)`，`#if` 的分支和註解也會被掃到：
   - flash 模式：最後一行 `modelSelect` 要是 `DEFAULT_YOLOV7TINY`，否則報「Model (.nb file) missing」。
   - SD 模式：只要有任何一行 `modelSelect` 用 `DEFAULT_…`，就報「Model selection mismatched」；改用 `CUSTOMIZED_YOLOV7TINY`（= `SD_YOLOV7TINY`，讀 `sd:/NN_MDL/yolov7_tiny.nb`）才會過。

   所以同一個 `.ino` 不可能兩種模式都過。腳本會產生 `<build path>_sketch/hub_node_ota/hub_node_ota.ino`，只把那一行換成 `CUSTOMIZED_YOLOV7TINY`。
2. `boards.txt` 雖然有 `build.ota_mode_flags=-DArduino_OTA_MODE`，但**沒有任何編譯規則用到它**（`build.menu_flags` 只放了 STD_PRINTF 和 LOAD_MODEL），所以 SDK **不會**替程式定義 `Arduino_OTA_MODE`。腳本產生的 sketch 第一行會寫 `#define Arduino_OTA_MODE 1`。
3. 防呆：如果定義了 `Arduino_OTA_MODE`，卻沒有用 SD 卡模型，編譯會直接 `#error`。

用 Arduino IDE 的話：先用腳本 `--ota --dry-run` 產生 sketch，再用 IDE 開那個資料夾，選單選 OTA Mode: Enable、NN Model Load From: SD Card。

### 6.2 身分：維持「MAC → 主伺服器指派的位置」，8 台共用同一個 ota.bin

查過交接 repo 的 hub_node（a0479ba），韌體裡**沒有** NODE_ID、樓層之類每台不同的編譯常數：
- `OLED_MAP` 一張表就列了 8 個位置（1N…2W）的 18 塊螢幕。
- 板子的位置是執行時才決定的：伺服器用 MAC 查 `devices.json`，在每次回應的 `slot` 欄位告訴板子，板子再從 `OLED_MAP` 挑出自己的螢幕。

所以 **8 台本來就是同一個 ota.bin**，這次不用改。另外兩種做法比較差：

| 做法 | 缺點 |
|---|---|
| SD 卡放設定檔 | 每張卡都要個別改；卡片插錯就跑錯位置；SD 卡現在也拿來放模型，每次準備卡片都要多一個步驟 |
| 韌體內建 MAC 對照表 | 換一塊板子就要重編、重推；所有板子都要更新才能生效 |
| **現行：中控台指派（維持）** | 換板子只要在中控台下拉選單改一下，不用重編，也不用碰 SD 卡 |

### 6.3 SD 卡準備（OTA 版每台都要一張）

1. microSD，格式化成 **FAT32**（建議 32 GB 以下，用 Windows 內建格式化就好）。
2. 在卡的根目錄建資料夾 **`NN_MDL`**（大小寫要一樣）。
3. 把目前用的模型（轉檔時輸入尺寸 576×320，和 flash 版放在 SDK `variants/common_nn_models/yolov7_tiny.nb` 的是同一份）複製進去，檔名改成 **`yolov7_tiny.nb`**。完整路徑：`sd:/NN_MDL/yolov7_tiny.nb`（SDK `libraries/NeuralNetwork/src/SD_Model.cpp` 寫死的）。
4. 卡片插到板子上再開機。之後換模型只要換卡上的檔案，不用 OTA；OTA 只更新程式。

### 6.4 更新流程

第一次要先用 USB 燒一次 OTA 版。arduino-cli upload 搭配自訂 build path 會找不到成品，要直接呼叫 `image_windows.exe`，參數照 `platform.txt` 的 `upload.pattern`。之後每次更新的步驟：

1. 改 `hub_node.ino` 的 `FW`（例如 `"2.5"`），執行 `build_hub_node.py --ota`。
2. `python fire_evac_v2/tools/ota_server.py serve --bin fire_evac_v2/tools/ota_out/hub_node_fw2.5_ota.bin --expect-fw 2.5`（port 3000）。
3. 另開一個視窗執行 `python ota_server.py status`，確認 8 台都在線、狀態都是 IDLE。名字從 hub_node 每 30 秒送一次的 `/api/nodeinfo` 來。
4. `python ota_server.py update all`（或只更新指定的幾台：`update 1N 2S`）。伺服器會一台一台照順序更新，每台的成功或失敗原因寫在 status 的「結果」欄：
   - 「離線」或「不是 IDLE，要先按 RST」：還沒開始就被擋下。
   - 「沒有開始下載」或「下載沒有完成（送出 x/y bytes）」：下載階段出問題。
   - 「下載完但沒有重開（板子拒收映像）」：狀態停在 COMPLETED，要按 RST。
   - 「重開了，但 FW 是舊版」：可能開回了舊分區。
   - 預設一台失敗就停下，後面的板子標成「略過」；加 `--keep-going` 則繼續下一台。

更新時板子的行為：
- 螢幕顯示「更新中」（不顯示方向），停止回報偵測結果。主伺服器會把這台當成離線，它負責的走廊沿用最後的狀態。
- 更新成功會自動重開機；失敗時，狀態停在 COMPLETED 超過 15 秒，板子就自己回到正常運作，等下次按 RST 再更新。

「更新中」的畫面由 `tools/gen_ota_banner.py` 用微軟正黑體粗體產生（`ota_banner.h`），直接寫進 SSD1306。文字**不鏡像**，因為從下往上看到的是螢幕正面。

### 6.5 資源檢查（讀 SDK 原始碼推論，沒有上板量測）

- **OTA 執行緒 1**（堆疊 1024）：每約 3.5 秒連線到 OTA 伺服器並 POST 狀態，在自己的執行緒裡阻塞，不影響 `loop()`。OTA 伺服器沒開時，序列埠會一直印「Connection to server failed」。
- **OTA 執行緒 2**（堆疊 2048）：`WiFiServer(5000)` 用預設的阻塞模式（`lwip_accept`），沒有連線時就是在等，不會空轉吃 CPU。
- **port 5000**：hub_node 本身不開任何 server port，主伺服器只是被動接收連線，不衝突。
- **堆疊單位**：`os_thread_create_arduino` 把數字直接交給 CMSIS-RTOS 的 `stacksize`，是 bytes 還是 words（4 KB 或 8 KB）沒有查證。
- **記憶體**：OTA.cpp 有幾個全域變數（`char buffer[1024]`、`JsonDocument`、`String`）。ArduinoJson 7.0.4 序列化到 String 前會先清空字串，所以回報內容不會越來越長。
- **下載任務**：優先權是 `tskIDLE_PRIORITY+1`，堆疊 1024。下載期間 `loop()` 會暫停偵測回報，每次 `delay(100)` 讓出 CPU。但 NN 的串流執行緒還在跑，和下載搶 CPU、搶記憶體的程度**沒有量測**。
- **I²C**：「更新中」畫面只在 `loop()` 裡寫，和 EvacOled 同一個執行緒，不會同時搶匯流排。
- **Wi-Fi**：`loop()` 每 30 秒多一次對 OTA 伺服器的短 POST，共用同一個 `WiFiClient`，依序執行。
  - 筆電在、但 OTA 伺服器沒開：連線會馬上被拒絕。
  - 筆電整台連不到：可能卡在 lwIP 的連線逾時；這時主伺服器本來也連不到，失敗後會退避成 5 分鐘一次。
- **flash**（arduino-cli 報的 Sketch 大小）：一般版 9,990,144 bytes（59%，含模型）；OTA 版 9,576,448 bytes（57%，不含模型，含 OTA 程式）；`ota.bin` 2,654,212 bytes（firmware.bin＋4 bytes 檢查碼）。OTA 版的符號與字串確認有 `otaInLoop`、`sendNodeInfo`、`start_OTA_threads`、`/api/nodeinfo`；一般版裡完全沒有。

### 6.6 還沒驗證

- 整套都還沒上板：「更新中」畫面、失敗後自動恢復、`/api/nodeinfo` 都只確認到編譯通過，和伺服器的模擬自測（`tools/ota_selftest.py`，8 台模擬板子，結果在 `tools/ota_selftest_output.md`）。
- 從 SD 卡載入模型的速度、OTA 版第一次 USB 燒錄的指令、更新後是否確實開進新分區，都要實機確認。
- OTA 執行緒加上 NN 串流和 EvacOled 一起跑時的記憶體與延遲。
- 8 台同時在熱點上時，回報的流量和依序更新所需的總時間：單台實測一輪的時間，乘以 8，再加上重開機的時間。

## FW 2.5：Wi-Fi 斷線自動處理（2026-11-25）

- 原因：11/25 有兩台板子掉出熱點後一直離線（熱點的裝置表裡也沒有它們），因為 2.4 以前只在 `setup()` 連一次 Wi-Fi。
- 2.5：`loop()` 裡 Wi-Fi 斷了每 5 秒重連一次；超過 60 秒沒收到伺服器回應就 `sys_reset()` 重開（OTA 執行緒、鏡頭一起重新啟動）。OTA 下載中（`otaInLoop()`）不會觸發。
- 注意：伺服器關掉超過 1 分鐘，板子會每分鐘重開一次，伺服器回來後就恢復。
- 編譯：`tools/build_hub_node.py --ota` 在使用者電腦（SDK 4.0.15）通過，ota.bin 2,572,292 bytes。**OTA 要在開熱點、IP 192.168.137.1 的那台電腦推**（韌體裡 OTA 伺服器位址寫死），並且用那台的 `secrets.h` 編譯（熱點名稱不是預設的 FireDemo）。


## FW 2.6：固定回報頻率＋訊號與重開診斷（2026-11-25）

- 原因：2.5 在中控台開著預覽（鏡頭牆）時，迴圈縮短到 30 ms 而且每圈都回報，每台每秒 15～22 次；伺服器每筆都重算、推送，跟不上，板子請求逾時、60 秒後被 2.5 的看門狗重開，中控台上就常見「4 台有 2 台離線」。8 台會更嚴重。
- 2.6：偵測結果固定每 200 ms 回報一次（每秒 5 次），預覽快照最多每 500 ms 一張；回報多帶 `rssi`（Wi-Fi 訊號 dBm）與 `up`（開機秒數），中控台顯示訊號強弱、開機多久，並從開機秒數變小算出重開次數。
- 伺服器同時改為每秒最多推送 5 次狀態，卡住的網頁 0.5 秒沒收就斷開（`app/server.py`）；這部分不用重燒，pull 後重開伺服器就生效。
- 編譯：`build_hub_node.py --ota` 在使用者電腦（SDK 4.0.15）通過，ota.bin 2,572,292 bytes（和前幾版相同大小，是固定大小的映像）。OTA 時用 `--expect-fw 2.6`。尚未上板。
