# 方案 D 多視角圖與接線圖（2026-11-13）

9 塊 OLED、7 台 HUB（4 台鏡頭 HUB＋只驅動 OLED 的 H5、H6、H7），含第 8 節的外接線設計（見 [`../README.md`](../README.md)）。

- 圖都從 `../fire_model_oled_through_hole.blend` 渲染，只出圖，不存檔、不改模型。
- 導線顏色：紅＝VCC／3V3／5V、黑＝GND、黃＝SCL、綠＝SDA、灰＝USB 線。
- 橘色＝塞子頂面（排煙孔、排線孔、十字臂插槽，要能拆）。

## 組合圖

| 檔案 | 內容 |
|---|---|
| `組合圖_方案D_多視角.png` | 3 × 3：拉遠全景、等角斜視剖切、人眼視角 3 張、四方位側視 4 張 |
| `組合圖_方案D_接線.png` | 2 × 3：設備層俯視、H5／H6／H7 接線特寫、南／北電源出口 |

兩張都附圖例：OLED 顏色、導線顏色、HUB 代號、塞子、分接板、固定膠帶。

## 單張圖

| 檔案 | 內容 |
|---|---|
| `3D_拉遠全景_九塊OLED.png` | 從斜下方看整個 1F（切掉地板、牆半透明） |
| `等角斜視剖切_拿掉2F與外牆_天花板半透明.png` | 拿掉 2F 與外牆，看得到設備層裡的 HUB、分接板與線 |
| `人眼視角1_站在中心路口往北看.png`、`人眼視角2_…`、`人眼視角3_…` | 相機在走廊、高 40 mm |
| `側視_從東往西看.png` 等 4 張 | 標出天花板、OLED 底、閘門頂、人偶高度 |
| `接線_設備層俯視_7台HUB與全部外接線.png` | 拿掉 2F 與麵包板座（只畫外框），看得到 7 台 HUB、全部外接線、南北 2 個 USB 集線器 |
| `接線特寫_H5.png`、`接線特寫_H6.png`、`接線特寫_H7.png` | 每台 OLED HUB：它的 OLED、分接板、共用段、I²C 排針（3V3／GND／SDA／SCL）與電源排針（5V／GND） |
| `電源出口特寫_南.png`、`電源出口特寫_北.png` | USB 線從設備層開口出樓層盒，沿外牆垂到桌面的集線器 |

## 重新產生

```bash
blender -b ../fire_model_oled_through_hole.blend --python ../views/render_views.py -- .
```

```bash
blender -b ../fire_model_oled_through_hole.blend --python ../views/render_panorama.py -- .
```

```bash
blender -b ../fire_model_oled_through_hole.blend --python render_wiring.py -- .
```

```bash
blender -b --factory-startup --python make_composites.py -- .
```

最後一行把上面的單張圖排成組合圖，所以要最後跑。
