火場避難動態指引系統 v2 — 程式包（小心炎上）

資料夾
  app/server.py                筆電伺服器（FastAPI）。即時模式：python server.py
  app/static/index.html        中控台／避難 App（瀏覽器開 http://筆電IP:8000）
  firmware/hub_model_test_official/  【第一步】官方模型，確認板子硬體正常，不需要伺服器
  firmware/hub_model_test/     【第二步】本組模型上機測試（要先放 yolov7_tiny.nb）
  firmware/hub_node/           正式節點程式：4 塊（或 8 塊）板子燒同一份
                               1F 9 個路口的方向協定與 OLED 設定表見 firmware/hub_node/README.md
  model/best_reparam.pt        訓練好的 YOLOv7-tiny（6 類，以 416 訓練、已重參數化；轉 .nb 時輸入尺寸填 576×320）
  model/yolov7-tiny-fire-deploy.yaml   上面權重對應的模型結構
  sim/                         路徑規劃核心（evac.py）與模擬

安裝：pip install fastapi uvicorn pillow


========== 一、模型上機測試 ==========
Arduino IDE → 工具：
  開發板 HUB-8735_ultra ／ NN Model Load From: Flash ／ Show NN Logs: Enable
  Camera Options：依鏡頭模組選 JXF37 或 PS5268（不確定就兩個都試，畫面全黑或花屏就是選錯）
  Wi-Fi 名稱密碼在程式最上面（預設 FireDemo / firedemo123）

第一階段：燒 hub_model_test_official（官方內建模型）
  目的是先確認鏡頭、NPU、串流都正常，跟我們的模型無關。
  對著人：序列埠會印「類別 0」（person），11 腳 LED 亮。

第二階段：燒 hub_model_test（本組模型）
  兩支分開是因為燒錄工具會直接讀程式裡 modelSelect 那一行決定燒哪個模型，不能用開關切換。
  1. 到 Realtek 線上 AI 模型轉換工具（amebaiot.com 的 AI Model Conversion），
     上傳 convert_upload/best_reparam_pt.zip，類型 YOLOv7-TINY-Pytorch、輸入尺寸填 576×320、量化 UINT8、類別 6，
     校正圖上傳 convert_upload/quant_images.zip（10 張 576×320）。韌體 NNW/NNH 已設為 576×320，兩邊必須一致。
  2. 收到的 .nb 檔改名為 yolov7_tiny.nb，放進 hub_model_test 資料夾（跟 .ino 同一層）。
     沒放的話編譯會停在「Model (.nb file) missing」。
  3. 燒錄。

怎麼判斷 Flash 有沒有跑起來（由簡單到完整）
  LED     11 腳閃 = 連 Wi-Fi 中；11 腳恆亮 = 模型載入中；全部閃 3 下 = 自檢通過
          之後偵測到哪類就亮哪顆：11 櫃子  12 紙箱  13 桌椅  24 瓦礫  23 閘門  18 煙
  序列埠  115200 baud。會依序印 [1/4]~[4/4]，[3/4] 有模型載入時間；之後每秒印偵測清單
  影像    VLC → 媒體 → 開啟網路串流 → 貼上序列埠印的 rtsp://IP:554，畫面上有框和類別名
  卡在 [3/4] 沒下一行 = 模型載不進去（.nb 檔名錯、尺寸不符或轉檔失敗），看序列埠的 NN 錯誤訊息

========== 二、多板連中控（firmware/hub_node） ==========
所有板子燒同一份，不用改任何設定；每塊板子用自己的 Wi-Fi MAC 當身分。
  1. 筆電開熱點 FireDemo / firedemo123，執行 python server.py
     （若筆電熱點 IP 不是 192.168.137.1，改 hub_node.ino 的 SERVER）
  2. 板子開機 → 自動出現在 中控台 → 開發者控制台 → 裝置配置，名稱「板子 N（MAC 末四碼）」
     還沒指派位置時，序列埠印 slot (none)（之後 OLED 顯示「等待指派」）
  3. 指派位置，三種方式任選：
     a. 下拉選單直接選 1F 北／西／南／東（同一位置只能一塊，選了會把原本的擠掉）
     b. 不知道哪塊是哪塊 → 按「閃燈」，那塊板子的 OLED 閃 6 秒（OLED 韌體完成前只有序列埠訊息）
     c. 遮鏡頭自動指認：按下後依提示「請用手遮住 1F 北 的鏡頭」，
        用手蓋住那個位置的鏡頭約 2 秒，畫面變暗的板子就自動被指派過去，接著下一個位置
  4. 「畫面」可看該板目前拍到的影像；「移除」把板子從清單刪掉
  對應表存在 app/devices.json，重開伺服器還在；調換板子位置只要改這裡，不用重燒。
