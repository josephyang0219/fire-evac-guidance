# 8 台鏡頭 HUB × 18 塊 OLED 端對端測試（2026-11-18 14:56，伺服器 port 8767）

## OLED 設定表（從 hub_node.ino 讀出）

| 板子 | 路口 | 匯流排 | 位址 | 螢幕上緣 |
|---|---|---|---|---|
| 1N | J(-1,1) | Wire0 | 0x3C | E |
| 1N | J(0,1) | Wire1 | 0x3C | S |
| 1E | J(1,1) | Wire0 | 0x3C | S |
| 1E | J(1,0) | Wire1 | 0x3C | W |
| 1S | J(1,-1) | Wire0 | 0x3C | S |
| 1S | J(0,-1) | Wire1 | 0x3C | N |
| 1S | J(0,0) | Wire1 | 0x3D | S |
| 1W | J(-1,-1) | Wire0 | 0x3C | N |
| 1W | J(-1,0) | Wire1 | 0x3C | E |
| 2N | J2(-1,1) | Wire0 | 0x3C | E |
| 2N | J2(0,1) | Wire1 | 0x3C | S |
| 2E | J2(1,1) | Wire0 | 0x3C | S |
| 2E | J2(1,0) | Wire1 | 0x3C | W |
| 2S | J2(1,-1) | Wire0 | 0x3C | S |
| 2S | J2(0,-1) | Wire1 | 0x3C | N |
| 2S | J2(0,0) | Wire1 | 0x3D | S |
| 2W | J2(-1,-1) | Wire0 | 0x3C | N |
| 2W | J2(-1,0) | Wire1 | 0x3C | E |

18 個路口各出現一次：是；每台 1～3 塊：是；同一台同一匯流排沒有重複位址：是；每台只接自己樓層：是

`GET /api/junctions?floor=2` 回 9 筆 2F 代號：是；`GET /api/displays` 已沒有 H5/H6/H7：是

## 平常狀態，全部暢通（junction_check 情境 1，1F 與 2F 放同樣的狀況）

```
1F
   S     E     S
   S     W     N
   N     W     N
2F
DOWN     W     W
   N     W     S
   N     E  DOWN
```
18 塊螢幕＝本機 evac：一致

## 西出口閘門關閉＋東南側冒煙（junction_check 情境 6，1F 與 2F 放同樣的狀況）

```
1F
   E     E     S
   E     E     N
   E     N     N
2F
DOWN     W     W
   N     W     N
   E     E  DOWN
```
18 塊螢幕＝本機 evac：一致

## 東側起火＋東出口北段櫃子倒下（junction_check 情境 3，1F 與 2F 放同樣的狀況）

```
1F
   S     W     W
   S     W     S
   N     W     W
2F
DOWN     W     W
   N     W     N
   N     W  DOWN
```
18 塊螢幕＝本機 evac：一致

## 兩個出口都被封住（junction_check 情境 8，1F 與 2F 放同樣的狀況）

```
1F
   X     X     X
   X     X     X
   X     X     X
2F
   X     X     X
   X     X     X
   X     X     X
```
18 塊螢幕＝本機 evac：一致

伺服器 log：67 個請求，非 200 的 0 個，Traceback 0 個

**總結：全部通過**
