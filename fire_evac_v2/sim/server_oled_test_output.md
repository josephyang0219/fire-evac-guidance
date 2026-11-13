# 1F 9 塊 OLED 端對端測試（2026-11-13 12:20，伺服器 port 8766）

## OLED 設定表（從韌體原始碼讀出）

| 路口 | 板子 | 匯流排 | 位址 | 多工器通道 |
|---|---|---|---|---|
| J(-1,1) 西北 | 1N | Wire0 | 0x3C | — |
| J(0,1) 北 | H6 | Wire0 | 0x3D | — |
| J(1,1) 東北 | 1E | Wire0 | 0x3C | — |
| J(-1,0) 西 | H6 | Wire0 | 0x3C | — |
| J(0,0) 中央 | H7 | Wire0 | 0x3C | — |
| J(1,0) 東 | H5 | Wire0 | 0x3D | — |
| J(-1,-1) 西南 | 1W | Wire0 | 0x3C | — |
| J(0,-1) 南 | H5 | Wire0 | 0x3C | — |
| J(1,-1) 東南 | 1S | Wire0 | 0x3C | — |

9 個路口各出現一次：是

還沒有顯示節點輪詢時，`GET /api/displays` 列出 ['H5', 'H6', 'H7']，全部 offline：是

## 平常狀態，全部暢通（junction_check 情境 1）

螢幕上看到的（從下往上看的地圖方位，北在上）：
```
   S     E     S
   S     W     N
   N     W     N
```
| 路口 | 由誰顯示 | 螢幕 | 本機 evac | junction_check 表 |
|---|---|---|---|---|
| J(-1,1) 西北 | 1N 0x3C | S | S | S |
| J(0,1) 北 | H6 0x3D | E | E | E |
| J(1,1) 東北 | 1E 0x3C | S | S | S |
| J(-1,0) 西 | H6 0x3C | S | S | S |
| J(0,0) 中央 | H7 0x3C | W | W | W |
| J(1,0) 東 | H5 0x3D | N | N | N |
| J(-1,-1) 西南 | 1W 0x3C | N | N | N |
| J(0,-1) 南 | H5 0x3C | W | W | W |
| J(1,-1) 東南 | 1S 0x3C | N | N | N |

鏡頭 HUB 回應欄位不變（blink junctions leds node slot snap）：是；顯示節點套用 H5 2/2、H6 2/2、H7 1/1
9 塊螢幕＝本機 evac：一致；＝junction_check 表：一致；規則檢查：通過

## 西出口閘門關閉＋東南側冒煙（junction_check 情境 6）

螢幕上看到的（從下往上看的地圖方位，北在上）：
```
   E     E     S
   E     E     N
   E     N     N
```
| 路口 | 由誰顯示 | 螢幕 | 本機 evac | junction_check 表 |
|---|---|---|---|---|
| J(-1,1) 西北 | 1N 0x3C | E | E | E |
| J(0,1) 北 | H6 0x3D | E | E | E |
| J(1,1) 東北 | 1E 0x3C | S | S | S |
| J(-1,0) 西 | H6 0x3C | E | E | E |
| J(0,0) 中央 | H7 0x3C | E | E | E |
| J(1,0) 東 | H5 0x3D | N | N | N |
| J(-1,-1) 西南 | 1W 0x3C | E | E | E |
| J(0,-1) 南 | H5 0x3C | N | N | N |
| J(1,-1) 東南 | 1S 0x3C | N | N | N |

鏡頭 HUB 回應欄位不變（blink junctions leds node slot snap）：是；顯示節點套用 H5 2/2、H6 2/2、H7 1/1
9 塊螢幕＝本機 evac：一致；＝junction_check 表：一致；規則檢查：通過

## 東側起火＋東出口北段櫃子倒下（junction_check 情境 3）

螢幕上看到的（從下往上看的地圖方位，北在上）：
```
   S     W     W
   S     W     S
   N     W     W
```
| 路口 | 由誰顯示 | 螢幕 | 本機 evac | junction_check 表 |
|---|---|---|---|---|
| J(-1,1) 西北 | 1N 0x3C | S | S | S |
| J(0,1) 北 | H6 0x3D | W | W | W |
| J(1,1) 東北 | 1E 0x3C | W | W | W |
| J(-1,0) 西 | H6 0x3C | S | S | S |
| J(0,0) 中央 | H7 0x3C | W | W | W |
| J(1,0) 東 | H5 0x3D | S | S | S |
| J(-1,-1) 西南 | 1W 0x3C | N | N | N |
| J(0,-1) 南 | H5 0x3C | W | W | W |
| J(1,-1) 東南 | 1S 0x3C | W | W | W |

鏡頭 HUB 回應欄位不變（blink junctions leds node slot snap）：是；顯示節點套用 H5 2/2、H6 2/2、H7 1/1
9 塊螢幕＝本機 evac：一致；＝junction_check 表：一致；規則檢查：通過

## 兩個出口都被封住（junction_check 情境 8）

螢幕上看到的（從下往上看的地圖方位，北在上）：
```
   X     X     X
   X     X     X
   X     X     X
```
| 路口 | 由誰顯示 | 螢幕 | 本機 evac | junction_check 表 |
|---|---|---|---|---|
| J(-1,1) 西北 | 1N 0x3C | X | X | X |
| J(0,1) 北 | H6 0x3D | X | X | X |
| J(1,1) 東北 | 1E 0x3C | X | X | X |
| J(-1,0) 西 | H6 0x3C | X | X | X |
| J(0,0) 中央 | H7 0x3C | X | X | X |
| J(1,0) 東 | H5 0x3D | X | X | X |
| J(-1,-1) 西南 | 1W 0x3C | X | X | X |
| J(0,-1) 南 | H5 0x3C | X | X | X |
| J(1,-1) 東南 | 1S 0x3C | X | X | X |

鏡頭 HUB 回應欄位不變（blink junctions leds node slot snap）：是；顯示節點套用 H5 2/2、H6 2/2、H7 1/1
9 塊螢幕＝本機 evac：一致；＝junction_check 表：一致；規則檢查：通過

## 顯示節點心跳（`GET /api/displays`）

| 節點 | online | 輪詢次數 n | loss % | 預期 loss % |
|---|---|---|---|---|
| H5 | True | 4 | 0.0 | 0.0 |
| H6 | True | 4 | 0.0 | 0.0 |
| H7 | True | 4 | 20.0 | 20.0 |

H7 在最後一個情境故意跳過一個 seq，用來確認伺服器有從 seq 算掉包。判定：正確

## 伺服器停掉之後

顯示節點輪詢：連不上（URLError）。韌體規則：超過 LINK_TIMEOUT_MS = 3000 ms 沒有有效回應 → H5/H6/H7 的螢幕全部 Off（全黑）；鏡頭 HUB 同樣在 3 秒後把自己的角落螢幕關掉。

伺服器 log：47 個請求，非 200 的 0 個，Traceback 0 個

**總結：全部通過**

## 編譯（arduino-cli，FQBN ideasHatch:AmebaPro2:Ameba_HUB-8735_ultra，--library oled_fw/libraries/EvacOled）

| sketch | 結果 | 大小 | 映像內的路口 id |
|---|---|---|---|
| `hub_oled` H5（預設 NODE_ID 5） | rc=0 | 4,788,224（28%） | J(0,-1)、J(1,0) |
| `hub_oled` H6（build.extra_flags …-DNODE_ID=6） | rc=0 | 4,788,224（28%） | J(-1,0)、J(0,1) |
| `hub_oled` H7（-DNODE_ID=7） | rc=0 | 4,788,224（28%） | J(0,0) |
| `hub_node`（4 台鏡頭 HUB，0x3C） | rc=0 | 9,990,144（59%） | （含 yolov7_tiny.nb） |
