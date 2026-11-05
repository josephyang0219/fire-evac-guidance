/*
  HUB 8735 Ultra 模型上機測試（單機、不需要筆電伺服器）
  目的：確認自訓的 YOLOv7-tiny（yolov7_tiny.nb）能從 Flash 載入並在 NPU 上跑。

  看結果的三種方式（由簡單到完整）：
   1. LED：11 腳閃 = 連 Wi-Fi 中，11 腳恆亮 = 模型載入中；載入成功後全部 LED 閃 3 下。
           之後偵測到哪一類，就亮對應的 LED（見 CLASS_PIN）。
   2. 序列埠監看視窗（115200）：開機自檢結果（含模型載入時間）、每秒的偵測清單。
   3. 影像：電腦用 VLC 開「媒體 → 開啟網路串流」，輸入序列埠印出的 rtsp:// 網址，
           會看到鏡頭畫面疊上偵測框與類別名稱。

  兩階段測試：
   第一階段 先燒 hub_model_test_official（官方內建 YOLOv7-tiny，COCO 80 類），對著人，確認鏡頭、NPU、串流都正常。
   第二階段 再燒 hub_model_test：把 yolov7_tiny.nb 放在 hub_model_test 資料夾（跟 .ino 同一層），Tools → NN Model Load From: Flash，
           對著列印的障礙物或線香煙，看是否框出本組 6 類。
*/
#include "WiFi.h"
#include "StreamIO.h"
#include "VideoStream.h"
#include "RTSP.h"
#include "NNObjectDetection.h"
#include "VideoStreamOverlay.h"

#define USE_CUSTOM 0          // 官方內建模型（COCO），用來先確認硬體正常

char ssid[] = "FireDemo";     // 筆電熱點或任何 2.4/5 GHz Wi-Fi
char pass[] = "firedemo123";

// 本組 6 類（順序與訓練時相同）
const char* MY_CLASSES[6] = {"cabinet", "boxes", "furniture", "rubble", "gate", "smoke"};
const char* MY_CLASSES_ZH[6] = {"櫃子", "紙箱", "桌椅", "瓦礫", "閘門", "煙"};
const int CLASS_PIN[6] = {11, 12, 13, 24, 23, 18};   // 偵測到該類就亮這顆（沿用節點接線的前 6 支腳）
const int ALL_PINS[] = {11, 12, 13, 24, 23, 18, 22, 21, 20, 19};
#define MIN_SCORE 40          // 信心值（%）低於此不算

#define CH_STREAM 0
#define CH_NN 3
#if USE_CUSTOM
  #define NNW 576             // 本組模型轉 .nb 時填 576×320，這裡要一致（與 hub_model_test 相同）
  #define NNH 320
#else
  #define NNW 576             // 官方範例的輸入尺寸
  #define NNH 320
#endif

VideoSetting config(VIDEO_FHD, 30, VIDEO_H264, 0);    // 1920×1080 串流（官方範例設定）
VideoSetting configNN(NNW, NNH, 10, VIDEO_RGB, 0);
NNObjectDetection ObjDet;
RTSP rtsp;
StreamIO videoStreamer(1, 1);
StreamIO videoStreamerNN(1, 1);

void allLeds(bool on) { for (int p : ALL_PINS) digitalWrite(p, on ? HIGH : LOW); }

void setup() {
  Serial.begin(115200);
  for (int p : ALL_PINS) { pinMode(p, OUTPUT); digitalWrite(p, LOW); }
  Serial.println("\n===== HUB 模型上機測試 =====");
  Serial.println(USE_CUSTOM ? "模式：本組模型 yolov7_tiny.nb（Flash）" : "模式：官方 YOLOv7-tiny（COCO）");

  int tries = 0;
  while (WiFi.begin(ssid, pass) != WL_CONNECTED) { Serial.println("連線 Wi-Fi 中..."); digitalWrite(11, tries++ % 2); delay(1000); }
  IPAddress ip = WiFi.localIP();
  Serial.print("[1/4] Wi-Fi OK，IP = "); Serial.println(ip);

  config.setBitrate(2 * 1024 * 1024);
  Camera.configVideoChannel(CH_STREAM, config);
  Camera.configVideoChannel(CH_NN, configNN);
  Camera.videoInit();
  rtsp.configVideo(config);
  rtsp.begin();
  Serial.println("[2/4] 鏡頭 OK");

  unsigned long t0 = millis();
  digitalWrite(11, HIGH);
  ObjDet.configVideo(configNN);
  // 注意：燒錄工具會直接讀這一行決定把哪個模型燒進 Flash，所以這行不能包在 #if 裡
  ObjDet.modelSelect(OBJECT_DETECTION, DEFAULT_YOLOV7TINY, NA_MODEL, NA_MODEL);
  ObjDet.begin();                                   // 模型從 Flash 載入到 NPU；失敗時 SDK 會在序列埠印錯誤並停住
  Serial.print("[3/4] 模型載入 OK，用時 "); Serial.print(millis() - t0); Serial.println(" ms");

  videoStreamer.registerInput(Camera.getStream(CH_STREAM));
  videoStreamer.registerOutput(rtsp);
  if (videoStreamer.begin() != 0) Serial.println("串流啟動失敗");
  Camera.channelBegin(CH_STREAM);
  videoStreamerNN.registerInput(Camera.getStream(CH_NN));
  videoStreamerNN.setStackSize();
  videoStreamerNN.setTaskPriority();
  videoStreamerNN.registerOutput(ObjDet);
  if (videoStreamerNN.begin() != 0) Serial.println("NN 串流啟動失敗");
  Camera.channelBegin(CH_NN);
  OSD.configVideo(CH_STREAM, config);
  OSD.begin();

  Serial.print("[4/4] 開始推論。VLC 開啟 rtsp://"); Serial.print(ip); Serial.print(":"); Serial.println(rtsp.getPort());
  for (int i = 0; i < 3; i++) { allLeds(true); delay(200); allLeds(false); delay(200); }   // 自檢通過：全部閃 3 下
}

unsigned long lastReport = 0;
int seen[6];

void loop() {
  std::vector<ObjectDetectionResult> results = ObjDet.getResult();
  int w = config.width(), h = config.height();
  bool lit[6] = {false};
  OSD.createBitmap(CH_STREAM);
  for (size_t i = 0; i < results.size(); i++) {
    ObjectDetectionResult r = results[i];
    int t = r.type(), sc = r.score();
    if (sc < MIN_SCORE) continue;
    const char* name;
#if USE_CUSTOM
    if (t < 0 || t > 5) continue;
    name = MY_CLASSES[t]; lit[t] = true; seen[t]++;
#else
    static char buf[8]; snprintf(buf, sizeof(buf), "id%d", t); name = buf;   // COCO：0 = person，56 = chair
#endif
    int bx0 = constrain((int)(r.xMin() * w), 0, w - 1);    // 不能叫 y0/y1：會和數學函式庫的 y0()/y1() 撞名
    int by0 = constrain((int)(r.yMin() * h), 0, h - 1);
    int bx1 = constrain((int)(r.xMax() * w), 0, w - 1);
    int by1 = constrain((int)(r.yMax() * h), 0, h - 1);
    OSD.drawRect(CH_STREAM, bx0, by0, bx1, by1, 3, OSD_COLOR_GREEN);
    char label[32]; snprintf(label, sizeof(label), "%s %d%%", name, sc);
    int ty = by0 - OSD.getTextHeight(CH_STREAM);
    OSD.drawText(CH_STREAM, bx0, ty < 0 ? 0 : ty, label, OSD_COLOR_CYAN);
  }
  OSD.update(CH_STREAM);
#if USE_CUSTOM
  for (int k = 0; k < 6; k++) digitalWrite(CLASS_PIN[k], lit[k] ? HIGH : LOW);
#else
  digitalWrite(11, results.size() > 0);       // 官方模型：有任何偵測就亮 11 腳
#endif

  if (millis() - lastReport > 1000) {          // 每秒回報一次
    Serial.print("運行 "); Serial.print(millis() / 1000); Serial.print(" 秒 | 目前偵測 "); Serial.print(results.size()); Serial.print(" 個");
#if USE_CUSTOM
    Serial.print(" | 累計：");
    for (int k = 0; k < 6; k++) { Serial.print(MY_CLASSES_ZH[k]); Serial.print(seen[k]); Serial.print(" "); }
#endif
    Serial.println();
    for (size_t i = 0; i < results.size(); i++) {
      ObjectDetectionResult r = results[i];
      Serial.print("   - 類別 "); Serial.print(r.type());
#if USE_CUSTOM
      if (r.type() >= 0 && r.type() < 6) { Serial.print(" "); Serial.print(MY_CLASSES_ZH[r.type()]); }
#endif
      Serial.print("  信心 "); Serial.print(r.score()); Serial.print("%  框 (");
      Serial.print(r.xMin(), 2); Serial.print(","); Serial.print(r.yMin(), 2); Serial.print(")-(");
      Serial.print(r.xMax(), 2); Serial.print(","); Serial.print(r.yMax(), 2); Serial.println(")");
    }
    lastReport = millis();
  }
  delay(50);
}
