# 路口方向協定（1F 天花板 9 塊 OLED）

舊版是「每台 HUB 驅動 2～3 個路口的 LED」，伺服器依照板子位置回傳固定順序的 `leds` 陣列。
新版改成**伺服器只回傳 9 個路口各自的方向**，每台板子用韌體裡的設定表自己挑出要顯示的路口，伺服器不管分配。

1F 定案布置（2026-11-10）：

| 板子 | 韌體 | 顯示的路口 | 接法 |
|---|---|---|---|
| 鏡頭 HUB 1N | `hub_node` | J(-1,1) 西北 | Wire 直接接 1 塊，0x3C |
| 鏡頭 HUB 1E | `hub_node` | J(1,1) 東北 | 同上 |
| 鏡頭 HUB 1S | `hub_node` | J(1,-1) 東南 | 同上 |
| 鏡頭 HUB 1W | `hub_node` | J(-1,-1) 西南 | 同上 |
| **H5**（只驅動 OLED，不跑鏡頭和模型） | `hub_oled`（`NODE_ID 5`） | J(0,-1) 南 0x3C、J(1,0) 東 0x3D | Wire 直接接 2 塊，不用多工器 |
| **H6**（同上） | `hub_oled`（`NODE_ID 6`） | J(-1,0) 西 0x3C、J(0,1) 北 0x3D | 同上 |
| **H7**（同上） | `hub_oled`（`NODE_ID 7`） | J(0,0) 中心 0x3C | Wire 直接接 1 塊 |

H5/H6/H7 的分組已定案（方案 D，1f-9-oled 依實際擺放位置決定，094610bb）。之後要改，只改 `hub_oled.ino` 開頭的表。不用 TCA9548A，也不用 Wire1（2026-11-13 決定）。

螢幕都由 EvacOled 函式庫驅動（`oled_fw/libraries/EvacOled`，從 8735-oled 的 ad032855 帶進來，沒有修改）。

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
| `snap` | 1 = 請上傳一張 JPEG |

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

`EVAC_CORNER_ADDR` 預設 0x3C（每條匯流排只有一塊，用出廠位址就好，不用改焊電阻）。要改回 0x3D 時，編譯加
下面這個參數（實測可編譯）：

```
--build-property "build.extra_flags=-DARDUINO_SDK -DARDUINO_AMBPRO2 -DBOARD_AMB82_HUB8735 -DBOARD_AMB82_HUB8735_ULTRA {build.usb_flags} {build.menu_flags} -DEVAC_CORNER_ADDR=0x3D"
```

AmebaPro2 的 C++ 編譯規則只讀 `build.extra_flags`，用 `compiler.cpp.extra_flags` 會被默默忽略。另外要保留板子原本的旗標（`boards.txt` 第 108 行），
只加 `-DEVAC_CORNER_ADDR=0x3D` 的話，`Arduino.h` 會報「Please choose between Flash or SD card」。
比較簡單的做法是直接改 `hub_node.ino` 開頭的 `#define EVAC_CORNER_ADDR`。每個位置最多 `MAX_OWN`（4）塊。
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
