/*
  HUB 8735 Ultra 人偶人流計數（天花板俯拍、手動在地板下拖磁鐵移動 1:10 人偶）

  - 推論：本組 YOLOv7-tiny（SDK 內建 yolov7_tiny.nb 已換成本組模型，用 DEFAULT_YOLOV7TINY 繞道，見 fire_evac_v2 上機測試進度）
  - 追蹤與計數：PeopleFlow.h（電腦端模擬測試在 ../test/sim_test.cpp）
  - 畫面：A 區黃框、B 區藍框，每個人偶畫框＋ID，移動中綠框、停住白框，左上角顯示 A→B / B→A 人數
  - 序列埠（115200）每秒一行：運行秒數、畫面人數、移動中人數、A→B、B→A、擁擠度
  - 序列埠輸入 r 可把計數歸零（每次實測前先歸零）

  現在模型還沒有 person 類別：PERSON_CLASS 設 -1 會追蹤所有類別，只能拿來測追蹤流程。
  補訓出 7 類模型後改成 6。
*/
#include "WiFi.h"
#include "StreamIO.h"
#include "VideoStream.h"
#include "RTSP.h"
#include "NNObjectDetection.h"
#include "VideoStreamOverlay.h"
#include "PeopleFlow.h"

#if __has_include("secrets.h")
  #include "secrets.h"
  char ssid[] = WIFI_SSID;
  char pass[] = WIFI_PASSWORD;
#else
  char ssid[] = "FireDemo";
  char pass[] = "firedemo123";
#endif

#define PERSON_CLASS -1       // 補訓後改 6
#define SDK_CONF 0.30f        // SDK 內部門檻；PeopleFlow 另以 minScore 再過濾
#define SDK_NMS  0.45f

// A、B 區域（正規化座標，依走廊在畫面中的方向調整）；中間 0.35～0.65 是緩衝區
const PFBox ZONE_A = {0.00f, 0.00f, 0.35f, 1.00f};
const PFBox ZONE_B = {0.65f, 0.00f, 1.00f, 1.00f};

#define CH_STREAM 0
#define CH_NN 3
#define NNW 576
#define NNH 320

VideoSetting config(VIDEO_HD, 15, VIDEO_H264, 0);
VideoSetting configNN(NNW, NNH, 10, VIDEO_RGB, 0);
NNObjectDetection ObjDet;
RTSP rtsp;
StreamIO videoStreamer(1, 1);
StreamIO videoStreamerNN(1, 1);
PeopleFlow flow;

void connectWiFi() {
  while (WiFi.begin(ssid, pass) != WL_CONNECTED) { Serial.println("連線 Wi-Fi 中..."); delay(1000); }
  Serial.print("Wi-Fi OK，IP = "); Serial.println(WiFi.localIP());
}

void setup() {
  Serial.begin(115200);
  Serial.println("\n===== HUB 人偶人流計數 =====");
  connectWiFi();

  config.setBitrate(1 * 1024 * 1024);
  Camera.configVideoChannel(CH_STREAM, config);
  Camera.configVideoChannel(CH_NN, configNN);
  Camera.videoInit();
  rtsp.configVideo(config);
  rtsp.begin();

  ObjDet.configVideo(configNN);
  ObjDet.configThreshold(SDK_CONF, SDK_NMS);
  // 燒錄工具直接讀這一行決定燒哪個模型，不能包在 #if 裡
  ObjDet.modelSelect(OBJECT_DETECTION, DEFAULT_YOLOV7TINY, NA_MODEL, NA_MODEL);
  ObjDet.begin();

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

  flow.classFilter = PERSON_CLASS;
  flow.setZones(ZONE_A, ZONE_B);
  Serial.print("開始計數。RTSP：rtsp://"); Serial.print(WiFi.localIP()); Serial.print(":"); Serial.println(rtsp.getPort());
}

int px(float v, int size) { return constrain((int)(v * size), 0, size - 1); }

void drawZone(const PFBox& z, uint32_t color, int w, int h) {
  OSD.drawRect(CH_STREAM, px(z.x0, w), px(z.y0, h), px(z.x1, w), px(z.y1, h), 2, color);
}

unsigned long lastReport = 0;

void loop() {
  if (Serial.available() && Serial.read() == 'r') { flow.reset(); Serial.println("計數已歸零"); }
  if (WiFi.status() != WL_CONNECTED) connectWiFi();   // 熱點斷過也能自己接回來

  std::vector<ObjectDetectionResult> results = ObjDet.getResult();
  PFDet dets[PeopleFlow::MAX_DETS];
  int n = 0;
  for (size_t i = 0; i < results.size() && n < PeopleFlow::MAX_DETS; i++) {
    ObjectDetectionResult r = results[i];
    dets[n++] = {{r.xMin(), r.yMin(), r.xMax(), r.yMax()}, r.type(), r.score()};
  }
  flow.update(dets, n, millis());

  int w = config.width(), h = config.height();
  OSD.createBitmap(CH_STREAM);
  drawZone(flow.zoneABox(), OSD_COLOR_YELLOW, w, h);
  drawZone(flow.zoneBBox(), OSD_COLOR_BLUE, w, h);
  for (int i = 0; i < PeopleFlow::MAX_TRACKS; i++) {
    const PFTrack& t = flow.track(i);
    if (!t.used || !t.confirmed) continue;
    uint32_t c = flow.isMoving(t) ? OSD_COLOR_GREEN : OSD_COLOR_WHITE;
    int bx0 = px(t.box.x0, w), by0 = px(t.box.y0, h);
    OSD.drawRect(CH_STREAM, bx0, by0, px(t.box.x1, w), px(t.box.y1, h), 3, c);
    char label[16]; snprintf(label, sizeof(label), "#%d", t.id);
    int ty = by0 - OSD.getTextHeight(CH_STREAM);
    OSD.drawText(CH_STREAM, bx0, ty < 0 ? 0 : ty, label, OSD_COLOR_CYAN);
  }
  char head[48];
  snprintf(head, sizeof(head), "A>B %d  B>A %d  now %d", flow.countAB(), flow.countBA(), flow.activeCount());
  OSD.drawText(CH_STREAM, 10, 10, head, OSD_COLOR_RED);
  OSD.update(CH_STREAM);

  if (millis() - lastReport > 1000) {
    Serial.print("運行 "); Serial.print(millis() / 1000);
    Serial.print(" 秒 | 畫面 "); Serial.print(flow.activeCount());
    Serial.print(" 人，移動中 "); Serial.print(flow.movingCount());
    Serial.print(" | A→B "); Serial.print(flow.countAB());
    Serial.print("  B→A "); Serial.print(flow.countBA());
    Serial.print(" | 擁擠度 "); Serial.print((int)(flow.occupancy() * 100)); Serial.println("%");
    lastReport = millis();
  }
  delay(20);
}
