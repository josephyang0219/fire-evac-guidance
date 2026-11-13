# 伺服器實測（2026-11-13 12:20，http://127.0.0.1:8765）

- `GET /` → 200，67102 bytes，中控台頁面（title 正確）
- `GET /api/junctions`（還沒有任何板子回報）→ 200，9 筆：J(-1,1)=X J(0,1)=X J(1,1)=X J(-1,0)=X J(0,0)=X J(1,0)=X J(-1,-1)=X J(0,-1)=X J(1,-1)=X
- `POST /api/dev/AABBCCDDEEFF/detections`（未指派的板子）→ 200，keys=['blink', 'junctions', 'leds', 'node', 'slot', 'snap']，slot=''，leds=[]，junctions 9 筆
- `GET /api/hub/1E/leds` → 200，leds=['N', 'S', 'W']，junctions 9 筆

## 平常狀態，全部暢通（對照 junction_check 情境 1）

送出的偵測框（類別(cx,cy,w,h,conf)）：無
伺服器融合後的走廊：全部暢通
1E 回應的舊 `leds` 欄位（HUB_LEDS 1E = J(1,0) J(1,1) J(0,0)）：['N', 'S', 'W']

| 路口 | 伺服器（POST 回應） | GET /api/junctions | 本機 evac 同樣輸入 | junction_check 表 |
|---|---|---|---|---|
| J(-1,1) 西北 | S | S | S | S |
| J(0,1) 北 | E | E | E | E |
| J(1,1) 東北 | S | S | S | S |
| J(-1,0) 西 | S | S | S | S |
| J(0,0) 中央 | W | W | W | W |
| J(1,0) 東 | N | N | N | N |
| J(-1,-1) 西南 | N | N | N | N |
| J(0,-1) 南 | W | W | W | W |
| J(1,-1) 東南 | N | N | N | N |

伺服器＝本機 evac：一致；伺服器＝junction_check 表：一致
junction_check 規則檢查（用伺服器融合後的狀態）：通過

## 西出口閘門關閉＋東南側冒煙（對照 junction_check 情境 6）

送出的偵測框（類別(cx,cy,w,h,conf)）：1E: smoke(0.93,0.68,0.14,0.50,0.77), smoke(0.83,0.20,0.34,0.40,0.29)；1W: gate(0.13,0.34,0.26,0.68,0.90)
伺服器融合後的走廊：-1-1--10 閘門、0-1-1-1 煙0.60、1-1-10 煙0.30
1E 回應的舊 `leds` 欄位（HUB_LEDS 1E = J(1,0) J(1,1) J(0,0)）：['N', 'S', 'E']

| 路口 | 伺服器（POST 回應） | GET /api/junctions | 本機 evac 同樣輸入 | junction_check 表 |
|---|---|---|---|---|
| J(-1,1) 西北 | E | E | E | E |
| J(0,1) 北 | E | E | E | E |
| J(1,1) 東北 | S | S | S | S |
| J(-1,0) 西 | E | E | E | E |
| J(0,0) 中央 | E | E | E | E |
| J(1,0) 東 | N | N | N | N |
| J(-1,-1) 西南 | E | E | E | E |
| J(0,-1) 南 | N | N | N | N |
| J(1,-1) 東南 | N | N | N | N |

伺服器＝本機 evac：一致；伺服器＝junction_check 表：一致
junction_check 規則檢查（用伺服器融合後的狀態）：通過

## 東側起火＋東出口北段櫃子倒下（對照 junction_check 情境 3）

送出的偵測框（類別(cx,cy,w,h,conf)）：1E: smoke(0.83,0.20,0.34,0.40,0.48)；1N: smoke(0.74,0.93,0.28,0.15,0.99), cabinet(0.90,0.59,0.13,0.08,0.90)；1W: smoke(0.26,0.93,0.28,0.15,0.45)
伺服器融合後的走廊：-10-00 煙0.30、0-1-00 煙0.30、00-10 煙0.66、00-01 煙0.66、1-1-10 煙0.50、10-11 阻擋1.00 
1E 回應的舊 `leds` 欄位（HUB_LEDS 1E = J(1,0) J(1,1) J(0,0)）：['S', 'W', 'W']

| 路口 | 伺服器（POST 回應） | GET /api/junctions | 本機 evac 同樣輸入 | junction_check 表 |
|---|---|---|---|---|
| J(-1,1) 西北 | S | S | S | S |
| J(0,1) 北 | W | W | W | W |
| J(1,1) 東北 | W | W | W | W |
| J(-1,0) 西 | S | S | S | S |
| J(0,0) 中央 | W | W | W | W |
| J(1,0) 東 | S | S | S | S |
| J(-1,-1) 西南 | N | N | N | N |
| J(0,-1) 南 | W | W | W | W |
| J(1,-1) 東南 | W | W | W | W |

伺服器＝本機 evac：一致；伺服器＝junction_check 表：一致
junction_check 規則檢查（用伺服器融合後的狀態）：通過

## 兩個出口都被封住（對照 junction_check 情境 8）

送出的偵測框（類別(cx,cy,w,h,conf)）：1E: gate(0.13,0.34,0.26,0.68,0.90)；1W: gate(0.13,0.34,0.26,0.68,0.90)
伺服器融合後的走廊：-1-1--10 閘門、10-11 閘門
1E 回應的舊 `leds` 欄位（HUB_LEDS 1E = J(1,0) J(1,1) J(0,0)）：['X', 'X', 'X']

| 路口 | 伺服器（POST 回應） | GET /api/junctions | 本機 evac 同樣輸入 | junction_check 表 |
|---|---|---|---|---|
| J(-1,1) 西北 | X | X | X | X |
| J(0,1) 北 | X | X | X | X |
| J(1,1) 東北 | X | X | X | X |
| J(-1,0) 西 | X | X | X | X |
| J(0,0) 中央 | X | X | X | X |
| J(1,0) 東 | X | X | X | X |
| J(-1,-1) 西南 | X | X | X | X |
| J(0,-1) 南 | X | X | X | X |
| J(1,-1) 東南 | X | X | X | X |

伺服器＝本機 evac：一致；伺服器＝junction_check 表：一致
junction_check 規則檢查（用伺服器融合後的狀態）：通過

**總結：全部通過**

## 附註

- 伺服器：`python app/server.py --port 8765`，Python 3.11（`yolov7_tiny_mini_demo/.conda-yolov7`），測完以 taskkill 關閉。
- 本次（2026-11-13，閘門半高改 47 mm、測試的閘門框改用整塊 94 mm 高）伺服器 log：25 個請求全部 200，沒有 Traceback。
- 這個環境沒有 `websockets`，所以 `/ws` 沒有測；中控台頁面能載入，但在這個環境下即時更新連不上。
- 測試產生的 `app/devices.json`（未指派的假 MAC）已刪除。
- 2026-11-06 第一輪的觀察：當時煙框過大，「東南—東」走廊的煙到 0.94（表裡是 0.5）。在這個條件下，J(1,0) 東選了 W（走進 0.60 的煙），沒有選 S（走進 0.94 的濃煙），規則檢查判定「指向起火走廊」。這是兩條都有煙時的取捨，不是程式錯誤；改成依表設定煙濃度後，結果和表一致。
