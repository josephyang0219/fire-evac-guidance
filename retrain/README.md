# retrain：7 類 YOLOv7-tiny 重新訓練的資料準備

目標：降低舊 6 類模型在實景的誤判（sim-to-real：舊訓練圖和量化校正圖都是很暗的渲染），並新增 `6 = person`（磁鐵拖動的小人偶）。

| 類別 | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| 名稱 | cabinet 櫃子 | boxes 紙箱 | furniture 桌椅 | rubble 瓦礫 | gate 閘門 | smoke 煙 | **person 人偶** |

0–5 與 `fire_yolo/fire_yolo/config/classes.yaml` 順序相同。

## 資料夾

| 路徑 | 內容 |
|---|---|
| `render/dr_render.py` | Blender domain randomization 渲染＋YOLO 標註（在 .blend 複本裡執行） |
| `render/draw_preview.py` | 把標註框疊到圖上 |
| `negatives/prepare_negatives.py` | 教室照片 → 576×320 負樣本＋空標註 |
| `tools/run_blender.py` | 啟動器：複製 .blend、確保路徑是英文、背景執行 Blender |
| `tools/check_labels.py` | 標註檢查（格式、對應、渲染交叉驗證） |
| `tools/make_dataset.py` | 多來源合併、切 train/val、打包 zip 和量化校正圖 |
| `train/訓練與轉檔步驟.md` | Colab 訓練 → 重參數化 → Realtek 轉檔 → 上板 |
| `train/reparam.py` | 重參數化（IDetect → Detect）＋輸出比對 |
| `config/` | `yolov7-tiny-fire7.yaml`（訓練）、`-deploy.yaml`（部署）、`hyp.ft7.yaml`，都是 nc = 7 |
| `補拍清單.md` | 實體模型回來後要拍的照片 |
| `samples/` | 5 張疊框預覽、對應的原圖／標註／meta、2 張空場景、檢查報告 |

大型輸出（渲染、資料集、zip）都在工作資料夾 `%USERPROFILE%\fire_retrain`，不進 git。

## 快速開始

系統 Python 3 就能跑（不需要 numpy、torch）；Blender 5.2 裝在預設位置。在 repo 根目錄執行：

```bash
python retrain/tools/run_blender.py render --count 200 --seed 1
python retrain/tools/run_blender.py empty --count 40 --seed 2
python retrain/tools/run_blender.py preview --src out/dr_s001 --n 5
python retrain/tools/check_labels.py %USERPROFILE%\fire_retrain\out\dr_s001 %USERPROFILE%\fire_retrain\out\empty_s002
python retrain/tools/run_blender.py negatives --src <教室照片資料夾> --name classroom
```

- 要更多張：換 `--seed`（每個種子一個資料夾），或同一個種子用 `--start 200 --count 800` 接續；`--skip-existing` 可中斷後續跑。
- 速度：RTX 5060 Laptop（OptiX）約 1 秒／張（200 張 191 秒）。

## 原檔保護與英文路徑

- `run_blender.py` 把 `實體模型檔案/fire_model.blend` 複製成 `%USERPROFILE%\fire_retrain\fire_model_dr.blend`，用 SHA-256 判斷原檔有沒有變，變了才重新複製；執行完再算一次原檔 SHA-256，被改過會警告。
- `dr_render.py` 開頭檢查：檔名是 `fire_model.blend` 就拒絕執行；腳本從不存檔。
- 傳給 Blender 的所有參數（.blend、腳本、輸出、照片）都檢查是 ASCII；教室照片若在中文資料夾，會先以內容 hash 命名複製到 `neg_src/<name>/`，對照表在 `source_names.csv`。

## 渲染做了什麼（`dr_render.py`）

場景用 .blend 裡的 `FireModel`，地板換成 `Floor_Tray_G`（新版：環廊中心 ±99、半寬 18；十字走廊半寬 21），閘門用對應的 `Gate_Plug_G36`／`G42`。

| 項目 | 內容 |
|---|---|
| 鏡頭 | .blend 裡的 `Cam_N/E/S/W`（PS5268：等立體角魚眼、fisheye_lens 2.98 mm、感光元件寬 5.6 mm），離地約 103 mm、往中心傾斜 18°；隨機選一支，位置 ±3 mm、角度 ±2.5°、焦距 ±2%。偏移後用射線檢查鏡頭沒有退進鏡頭座裡（否則全黑） |
| 解析度 | 576×320（和上板一致；感光元件水平對齊） |
| 光照 | 世界光（4000–7500 K，強度 0.3–1.5）＋模型內 1–3 盞燈（3200–6800 K，第一盞靠近畫面中心）；25% 開蓋＋頭頂日光燈（40% 再加陽光）。最後**自動曝光到偏亮的平均亮度 0.38–0.62** |
| 材質 | 地板／牆／蓋子：白、灰 PLA 或其他顏色；障礙物：原色微調，25% 完全隨機色；閘門 50% 隨機色；全部加雜訊混色紋理、粗糙度隨機。樓梯門原本和閘門共用材質，改成獨立材質（避免沒標的門永遠和閘門同色） |
| 目標物 | 障礙物 0–4 個（.blend 裡 8 個道具，大小 ±15%、任意轉向、腳印必須在走廊內且不重疊）、閘門 0–2 個（12 個槽位；鏡頭正下方的槽位大多跳過）、人偶 0–4 個、煙 0–2 團（45% 的圖） |
| 人偶（新） | 36–44 mm；兩型：四肢人偶／木頭人偶（圓柱＋球）；50% 有磁鐵底座；膚色、上衣、褲子隨機 |
| 煙 | Cycles 體積：從地板冒出的煙柱或天花板下的煙層；密度、雜訊、顏色隨機 |
| 干擾物（不標） | 0–4 個：圓柱、球、錐、紙片／膠帶、電線，隨機顏色——讓模型學會「不是每個東西都要框」 |
| 負樣本 | 8% 的圖沒有目標物；`empty` 模式整批都沒有 |
| 後處理 | 白平衡、gamma、對比、飽和度、暗角、高斯模糊（60%）、動態模糊（15%）、讀出＋散粒雜訊、JPEG 品質 55–95 |

物件位置大多（85%）取在鏡頭看得到的地方（投影在畫面內、射線不被牆擋），15% 不檢查，保留被擋住只露一角的情況。

### 標註怎麼算

每張圖渲染 3–4 次：

1. 彩色圖：32 spp＋降噪，存 EXR 線性值，再做上面的後處理。
2. 遮罩 A：所有物件換成「發光強度＝物件編號」的材質（1 spp、box 濾波 0.01 px，每個像素就是一個整數編號），煙隱藏。
3. 遮罩 B：煙顯示（縮成 0.85 倍，對應密度衰減的邊緣）。
4. 有煙時：同一個種子再渲一張沒有煙的彩色圖，亮度相對差 > 6% 的像素才算「看得到煙」。

框 = 該物件在遮罩裡**可見像素**的外接矩形（被牆擋住、出畫面的部分自動扣掉）；可見像素 < 40 或框邊 < 4 px 不標。

### 標註怎麼驗證

| 檢查 | 結果（seed 1 的 200 張＋seed 2 的 40 張空場景） |
|---|---|
| 格式：5 欄、類別 0–6、數值 (0,1]、框不出畫面 | 錯誤 0 |
| 每張圖都有標註檔、沒有多餘的標註檔 | 錯誤 0 |
| 標註檔和 meta 裡的物件、框一致 | 錯誤 0 |
| 遮罩裡沒有不認識的編號 | 錯誤 0 |
| **獨立方法交叉驗證**：把物件網格（每條邊取 9 點）用等立體角魚眼公式 `r = 2·f·sin(θ/2)` 投影，遮罩框必須落在投影框內（容許 3 px） | 742 個物件全部通過；9 個（很靠近鏡頭的閘門，有頂點在鏡頭後方）略過 |
| 目視：5 張疊框預覽圖 | `samples/preview/`，框和物件吻合 |
| 重跑：同一個種子重渲前 5 張 | 標註檔逐字相同；圖片因 GPU 降噪有極小差異（煙的可見像素差 2 px 以內，不影響框） |

統計（240 張，空標註 62 張）：

| 類別 | 框數 | 平均面積（像素） | 看不到／太小沒標 |
|---|---|---|---|
| 0 cabinet | 61 | 5605 | 11 |
| 1 boxes | 80 | 5020 | 15 |
| 2 furniture | 82 | 3684 | 22 |
| 3 rubble | 59 | 5845 | 12 |
| 4 gate | 108 | 28587 | 29 |
| 5 smoke | 67 | 23309 | 45 |
| 6 person | 290 | 3994 | 86 |

完整報告：`samples/check_report_s001.json`。每張圖的參數（鏡頭、光、後處理、每個物件的位置／像素數／投影框）都在 `meta/*.json`。

## 負樣本流程

1. **空場景渲染**：`run_blender.py empty`——同樣的隨機光照、材質、干擾物，但沒有目標物，標註為空。
2. **教室實景照片**：`run_blender.py negatives --src <資料夾> --name <名稱>`
   - 每張照片：中央裁切 1 張＋隨機裁切 2 張（576:320，邊長 50–100%），縮成 576×320，輸出空的 `.txt`。
   - 隨機裁切的種子是照片內容的 hash，重跑結果一樣；`manifest.csv` 記錄裁切範圍。
   - 照片裡不能有模型道具、人偶、線香煙；教室本身的桌椅櫃子可以（正是要壓下去的誤判）。
   - 錄影可先用 ffmpeg 抽幀：`ffmpeg -i rec.mp4 -vf fps=1 frames/%04d.jpg`。
3. `make_dataset.py` 把它們和渲染圖合併，負樣本建議占 20–30%。

流程已用 2 張測試圖（放在中文路徑）跑過：暫存、裁切、空標註、manifest 都正常；真正的教室照片還沒拍。

## 已知限制

- 渲染裡的道具是 .blend 的簡化模型，人偶是程式產生的簡單幾何體，和實物外觀有差距；實拍照片進來後要加權（`make_dataset.py --src real/xxx:3`）。
- 只渲染 1F（鏡頭只在 1F 蓋子上）。
- 靠近鏡頭的閘門只看得到頂面一大片，照樣標成 gate（框平均約佔畫面 15%）。
- `reparam.py` 和 Colab 步驟還沒實際跑過（本機沒有 torch）。
