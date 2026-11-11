# 1F 9 塊 OLED 端對端測試（2026-11-10 01:58，伺服器 port 8766）

## OLED 設定表（從韌體原始碼讀出）

| 路口 | 板子 | 匯流排 | 位址 | 多工器通道 |
|---|---|---|---|---|
| J(-1,1) 西北 | 1N | Wire0 | 0x3C | — |
| J(0,1) 北 | H5 | Wire0 | 0x3C | ch1 |
| J(1,1) 東北 | 1E | Wire0 | 0x3C | — |
| J(-1,0) 西 | H5 | Wire0 | 0x3C | ch4 |
| J(0,0) 中央 | H5 | Wire0 | 0x3C | ch0 |
| J(1,0) 東 | H5 | Wire0 | 0x3C | ch2 |
| J(-1,-1) 西南 | 1W | Wire0 | 0x3C | — |
| J(0,-1) 南 | H5 | Wire0 | 0x3C | ch3 |
| J(1,-1) 東南 | 1S | Wire0 | 0x3C | — |

9 個路口各出現一次：是

## 平常狀態，全部暢通（junction_check 情境 1）

螢幕上看到的（從下往上看的地圖方位，北在上）：
```
   S     E     S
   S     W     N
   N     W     N
```
| 路口 | 由誰顯示 | 螢幕 | 本機 evac | junction_check 表 |
|---|---|---|---|---|
| J(-1,1) 西北 | 1N | S | S | S |
| J(0,1) 北 | H5 ch1 | E | E | E |
| J(1,1) 東北 | 1E | S | S | S |
| J(-1,0) 西 | H5 ch4 | S | S | S |
| J(0,0) 中央 | H5 ch0 | W | W | W |
| J(1,0) 東 | H5 ch2 | N | N | N |
| J(-1,-1) 西南 | 1W | N | N | N |
| J(0,-1) 南 | H5 ch3 | W | W | W |
| J(1,-1) 東南 | 1S | N | N | N |

鏡頭 HUB 回應欄位不變（blink junctions leds node slot snap）：是；H5 套用 5/5 筆
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
| J(-1,1) 西北 | 1N | E | E | E |
| J(0,1) 北 | H5 ch1 | E | E | E |
| J(1,1) 東北 | 1E | S | S | S |
| J(-1,0) 西 | H5 ch4 | E | E | E |
| J(0,0) 中央 | H5 ch0 | E | E | E |
| J(1,0) 東 | H5 ch2 | N | N | N |
| J(-1,-1) 西南 | 1W | E | E | E |
| J(0,-1) 南 | H5 ch3 | N | N | N |
| J(1,-1) 東南 | 1S | N | N | N |

鏡頭 HUB 回應欄位不變（blink junctions leds node slot snap）：是；H5 套用 5/5 筆
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
| J(-1,1) 西北 | 1N | S | S | S |
| J(0,1) 北 | H5 ch1 | W | W | W |
| J(1,1) 東北 | 1E | W | W | W |
| J(-1,0) 西 | H5 ch4 | S | S | S |
| J(0,0) 中央 | H5 ch0 | W | W | W |
| J(1,0) 東 | H5 ch2 | S | S | S |
| J(-1,-1) 西南 | 1W | N | N | N |
| J(0,-1) 南 | H5 ch3 | W | W | W |
| J(1,-1) 東南 | 1S | W | W | W |

鏡頭 HUB 回應欄位不變（blink junctions leds node slot snap）：是；H5 套用 5/5 筆
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
| J(-1,1) 西北 | 1N | X | X | X |
| J(0,1) 北 | H5 ch1 | X | X | X |
| J(1,1) 東北 | 1E | X | X | X |
| J(-1,0) 西 | H5 ch4 | X | X | X |
| J(0,0) 中央 | H5 ch0 | X | X | X |
| J(1,0) 東 | H5 ch2 | X | X | X |
| J(-1,-1) 西南 | 1W | X | X | X |
| J(0,-1) 南 | H5 ch3 | X | X | X |
| J(1,-1) 東南 | 1S | X | X | X |

鏡頭 HUB 回應欄位不變（blink junctions leds node slot snap）：是；H5 套用 5/5 筆
9 塊螢幕＝本機 evac：一致；＝junction_check 表：一致；規則檢查：通過

## H5 心跳（`GET /api/displays`）

`{"online": true, "age": 0.0, "loss": 84.0, "n": 4, "ip": "127.0.0.1", "fw": "h5-1.0"}`

測試時 H5 的 seq 每個情境跳 8（中間是鏡頭 HUB 的請求），所以 loss 不是 0 是預期的：這證明伺服器有從 seq 算掉包。 判定：正確

## 伺服器停掉之後

H5 輪詢：連不上（URLError）。韌體規則：超過 LINK_TIMEOUT_MS = 3000 ms 沒有有效回應 → 5 塊全部 Off（全黑）；鏡頭 HUB 同樣在 3 秒後把自己的角落螢幕關掉。

伺服器 log：38 個請求，非 200 的 0 個，Traceback 0 個

**總結：全部通過**

## 編譯（arduino-cli，FQBN ideasHatch:AmebaPro2:Ameba_HUB-8735_ultra，--library oled_fw/libraries/EvacOled）

- `hub_oled5`（H5）：rc=0，4,788,224 位元組（28%），沒有 NN 模型
- `hub_node`（4 台鏡頭 HUB 同一份，EVAC_CORNER_ADDR=0x3C）：rc=0，9,990,144 位元組（59%），含 yolov7_tiny.nb
- `hub_node` 改回 0x3D（`build.extra_flags` 保留板子原本的旗標＋`-DEVAC_CORNER_ADDR=0x3D`）：rc=0，59%；verbose log 確認 sketch 的編譯命令有帶到這個旗標
