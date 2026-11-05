# 路口方向協定（1F 天花板 9 塊 OLED）

舊版是「每台 HUB 驅動 2～3 個路口的 LED」，伺服器依照板子位置回傳固定順序的 `leds` 陣列。
新版改成**伺服器只回傳 9 個路口各自的方向**，每台 HUB 用韌體裡的設定表 `OLED_MAP`，
自己挑出要顯示的那幾個路口。OLED 怎麼分配給 HUB 還沒定案，所以分配只寫在設定表裡，伺服器不用改。

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

另外有兩個韌體自己產生的狀態，伺服器不會送：

- `--`：超過 3 秒（`LINK_TIMEOUT_MS`）沒收到伺服器回應。顯示「連線中斷」，不要停在舊的箭頭。
- `WAIT`：這塊板子還沒在中控台被指派位置。
- `BLINK`：中控台按了「閃燈」，跟 `--` 每 250 ms 交替，用來找出是哪塊板子。

> 注意：OLED 裝在天花板上，人是**從下面往上看**。韌體裡的 N/S/E/W 是地圖方位；
> 要依照每塊 OLED 實際的安裝方向，把它換算成螢幕上的箭頭方向（左右會鏡像），這件事交給 OLED 韌體處理。

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

## 4. 韌體設定表（`hub_node.ino` 的 `OLED_MAP`）

每塊 OLED 一列：`{位置, 路口 id, I²C 匯流排, 位址}`。匯流排 0 = `Wire`，1 = `Wire1`（目前沒有用到，欄位留著備用）；SSD1306 只能設 0x3C 或 0x3D。
每個位置最多 `MAX_OWN`（4）塊。換分配方式只要改這張表，不用改程式也不用改伺服器。

目前的內容是**暫定**的，照 1f-9-oled 的配置（分支 `claude/oled-ceiling-1f`）：

| 位置 | 0x3C（Wire） | 0x3D（Wire） |
|---|---|---|
| 1N | J(0,1) 北 | J(-1,1) 西北 |
| 1E | J(1,0) 東 | J(1,1) 東北 |
| 1S | J(0,-1) 南 | J(1,-1) 東南 |
| 1W | J(-1,0) 西 | J(-1,-1) 西南 |

**中心路口 `J(0,0)` 不裝 OLED**（2026-11-05 決定），所以 8 塊 OLED 全部接在各台的 `Wire` 上，不需要 `Wire1`。
伺服器的 `junctions` 仍然輸出 9 個路口，中心的方向給中控台和簡報用；韌體設定表裡沒有它，就不會顯示。

2F 的位置（`2N`…）目前沒有列，伺服器也只送 1F 的路口；2F 的板子照樣回報偵測，只是不顯示方向。

### 顯示掛勾

這版韌體還沒有接 OLED，只把方向變化印到序列埠（115200），例如：

```
slot 1E, OLEDs 2
[OLED 0 0x3C] J(1,0) -> S
[OLED 0 0x3D] J(1,1) -> W
```

OLED 韌體只要改寫 `showDirection(const OledSlot& o, const String& dir)` 這一個函式（依 `o.bus`／`o.addr` 選螢幕、畫 `dir`），
再在 `setup()` 裡初始化 `Wire` 和各塊螢幕。`showDirection` 只有在顯示內容改變時才會被呼叫。

## 5. 驗證

- 模擬：`cd fire_evac_v2/sim && python junction_check.py`（需要 numpy）。8 種火／煙／障礙物配置，
  檢查每個路口的箭頭沒有指向牆、沒有指向被封住的走廊、有其他路時不指向起火走廊、
  跟著箭頭走會到出口或樓梯而且不會繞圈；只有真的無路可走才顯示 X。輸出存在 `sim/junction_check_output.md`。
- 編譯：

  ```
  arduino-cli compile --config-file <yaml，directories.data = %LOCALAPPDATA%\Arduino15> --fqbn ideasHatch:AmebaPro2:Ameba_HUB-8735_ultra fire_evac_v2/firmware/hub_node
  ```

  模型用 `DEFAULT_YOLOV7TINY`，讀的是 SDK 裡已經換成本組模型的 `yolov7_tiny.nb`（跟 hub_model_test、people_flow 相同的做法）。
