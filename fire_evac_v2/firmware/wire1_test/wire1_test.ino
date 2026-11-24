// 一台 HUB 三條 I2C 同時驅動 OLED 的桌上實測（含 OTA，可用 ota_server.py 無線推送）
//   Wire  ：SDA Pin3／SCL Pin4   → 角落那塊（畫左右箭頭）
//   Wire1 ：SDA Pin0／SCL Pin1   → 十字臂那塊（畫上下箭頭）
//   軟體 I2C：SDA Pin18／SCL Pin19 → 中心那塊（畫「X」與「O」交替），不用改焊 0x3D
// 三塊都是出廠 0x3C。每 5 秒一起換圖，序列埠印出每條線有沒有回應（ACK）。
// 編譯：FQBN 加 :08_OTAMode=Enable,06_LoadNNModelSource=sd；Wi-Fi 設定在 secrets.h（不進 git）。
// 歷史：v1–v3 只測 Wire1，v4 測 Wire＋Wire1，v5 加軟體 I2C（使用者 11-23 決定不改焊）。
#include <WiFi.h>
#include <Wire.h>
#include "OTA.h"
#include "secrets.h"
#include "StreamIO.h"
#include "VideoStream.h"
#include "NNObjectDetection.h"
extern "C" {
#include "gpio_api.h"
#include "i2c_api.h"
#include "i2c_ex_api.h"
}

#define FW_TAG "wire1_test v12"
#define I2C_HZ 100000   // v10：400 kHz 時使用者看到 Pin0/1、3/4 兩塊不亮（ACK 仍正常），先降到 100 kHz 排查訊號品質
#define SOFT_SDA 18
#define SOFT_SCL 19

char ssid[] = WIFI_SSID;
char pass[] = WIFI_PASS;
char server[] = OTA_SERVER_IP;
OTA ota;

// ---------- 匯流排抽象：硬體 TwoWire 或軟體 I2C ----------
struct Bus {
  virtual bool write(uint8_t addr, const uint8_t *d, int n) = 0;   // 一次傳輸，回傳是否 ACK
};

struct HwBus : Bus {
  TwoWire &w;
  HwBus(TwoWire &x) : w(x) {}
  bool write(uint8_t addr, const uint8_t *d, int n) override {
    w.beginTransmission(addr);
    w.write(d, n);
    return w.endTransmission() == 0;    // n>=1 時才準（0 bytes 時 SDK 對任何位址都回 0）
  }
};

// 開汲極模擬：放開＝輸入＋上拉（OLED 模組上也有上拉電阻），拉低＝輸出 0。
// v5 用 Arduino pinMode() 切換方向：SDK 每次重設已初始化的腳位都會 printf 一行警告，畫一張要好幾秒。
// v6 改用 HAL 的 gpio_t 直接切方向，不經 pinMode，也不印警告。
struct SoftBus : Bus {
  PinName sdaName, sclName;
  gpio_t gs, gc;
  gpio_t *sda = &gs, *scl = &gc;
  SoftBus(PinName a, PinName c) : sdaName(a), sclName(c) {}
  void rel(gpio_t *g) { gpio_dir(g, PIN_INPUT); gpio_mode(g, PullUp); }
  void low(gpio_t *g) { gpio_write(g, 0); gpio_dir(g, PIN_OUTPUT); gpio_mode(g, PullNone); gpio_write(g, 0); }
  bool readSda() { return gpio_read(sda); }
  void dly() { delayMicroseconds(2); }
  void begin() { gpio_init(sda, sdaName); gpio_init(scl, sclName); rel(sda); rel(scl); }
  // SCL 在傳輸期間一直是推挽輸出；start() 開始時切成輸出、stop() 結束時放開。
  void start() { rel(sda); rel(scl); dly(); low(sda); dly(); low(scl); dly(); }
  void stop() { low(sda); dly(); gpio_write(scl, 1); rel(scl); dly(); rel(sda); dly(); }
  // v9：資料位元改成推挽輸出，只寫 gpio_write，不切方向（SSD1306 只收不送、也不拉長時脈，推挽沒問題）；
  // 只有第 9 拍 ACK 時才把 SDA 切成輸入。每個 byte 從約 36 次切方向降到 2 次。
  void outFast(gpio_t *g) { gpio_dir(g, PIN_OUTPUT); gpio_mode(g, PullNone); }
  bool byteOut(uint8_t b) {
    outFast(sda);
    for (int i = 7; i >= 0; i--) {
      gpio_write(sda, (b >> i) & 1);
      gpio_write(scl, 1);
      gpio_write(scl, 0);
    }
    rel(sda); gpio_write(scl, 1); dly();
    bool ack = readSda() == 0;
    gpio_write(scl, 0);
    return ack;
  }
  bool write(uint8_t addr, const uint8_t *d, int n) override {
    start();
    bool ok = byteOut(addr << 1);
    for (int i = 0; ok && i < n; i++) ok = byteOut(d[i]);
    stop();
    return ok;
  }
};

// v7：直接用 HAL 的 i2c_t（不經 Wire 函式庫）。SDK 的 Wire::endTransmission() 每傳 1 byte 固定等 200 µs，
// 一張 1024 bytes 的畫面要約 0.24 秒；HAL 直接寫、400 kHz，理論約 25 ms。
// 注意：用了 HalBus 就不能再對同一組腳位呼叫 Wire.begin()／Wire1.begin()。
// v8：i2c_write 的回傳值不反映 NACK（不存在的 0x3D 也回 2），而且 NACK 之後匯流排會卡住、下一次寫入不回來。
// 所以比照 SDK Wire：每次探測、每畫一張前都先 i2c_reset＋重新 init（只做一次，不是每個 byte），
// 有沒有 ACK 則用 SDK 的 TX_COMPLETE 回呼旗標判斷（Wire 也是這樣判斷）。
static volatile int g_txDone = 0;
static void onTxDone(void *) { g_txDone = 1; }

struct HalBus : Bus {
  i2c_t i2c;
  PinName sda, scl;
  int hz = 400000;
  HalBus(PinName a, PinName c) : sda(a), scl(c) {}
  void recover() {
    i2c_reset(&i2c);
    i2c_init(&i2c, sda, scl);
    i2c_frequency(&i2c, hz);
    i2c_set_user_callback(&i2c, I2C_TX_COMPLETE, onTxDone);
  }
  void begin(int f) { hz = f; i2c_init(&i2c, sda, scl); recover(); }
  // v11：v7–v10 畫一張只要 2 ms（100 kHz 理論上要約 90 ms）→ i2c_write 沒等送完就返回，下一筆蓋掉上一筆，
  // 畫面時好時壞。改成每筆送出後等 TX_COMPLETE 回呼（逾時 = n×0.2 ms＋2 ms，和 Wire 的固定等待同級但先到先走），
  // 逾時就 recover() 並記數。
  int nWrites = 0, nTimeouts = 0;
  bool write(uint8_t addr, const uint8_t *d, int n) override {
    g_txDone = 0;
    i2c_write(&i2c, addr, (const char *)d, n, 1);
    unsigned long limit = (unsigned long)n * 200 + 2000, t0 = micros();
    while (!g_txDone && micros() - t0 < limit) { }
    nWrites++;
    if (!g_txDone) { nTimeouts++; recover(); return false; }
    return true;
  }
  bool ack(uint8_t addr) {           // 探測：重設後送 NOP，等 1 ms 看回呼有沒有來
    recover();
    g_txDone = 0;
    uint8_t d[2] = {0x00, 0xE3};
    i2c_write(&i2c, addr, (const char *)d, 2, 1);
    delay(1);
    bool ok = g_txDone;
    recover();                       // 不管有沒有 ACK，都把匯流排恢復成乾淨狀態
    return ok;
  }
};

// v12：hub_node 實測鏡頭＋NN 跑起來後，HAL 硬體 I2C 的 TX_COMPLETE 永遠不來（探測 0 成功），軟體 I2C 正常。
// 所以三塊都改軟體 I2C（同樣的腳位，不用改線），並在這裡同時開鏡頭＋NN 驗證。
SoftBus busWire(PE_4, PE_3), busWire1(PF_2, PF_1);   // Pin3 SDA／Pin4 SCL；Pin0 SDA／Pin1 SCL（都改軟體）
#define NNW 576
#define NNH 320
VideoSetting configNN(NNW, NNH, 10, VIDEO_RGB, 0);
NNObjectDetection ObjDet;
StreamIO videoStreamerNN(1, 1);
SoftBus busSoft(PF_5, PF_6);   // Pin18 = PF_5（SDA）、Pin19 = PF_6（SCL），見 variant.h

// ---------- SSD1306 ----------
static uint8_t fb[128 * 64 / 8];

bool cmd(Bus &b, uint8_t a, uint8_t c) { uint8_t d[2] = {0x00, c}; return b.write(a, d, 2); }

bool oledInit(Bus &b, uint8_t a) {
  const uint8_t seq[] = {0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14, 0x20, 0x00,
                         0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF};
  bool ok = true;
  for (uint8_t c : seq) ok &= cmd(b, a, c);
  return ok;
}

void flush(Bus &b, uint8_t a) {
  cmd(b, a, 0x21); cmd(b, a, 0); cmd(b, a, 127);
  cmd(b, a, 0x22); cmd(b, a, 0); cmd(b, a, 7);
  uint8_t d[17];
  d[0] = 0x40;
  for (int i = 0; i < (int)sizeof(fb); i += 16) {
    memcpy(d + 1, fb + i, 16);
    b.write(a, d, 17);
  }
}

void px(int x, int y) {
  if (x < 0 || x >= 128 || y < 0 || y >= 64) return;
  fb[x + (y / 8) * 128] |= (1 << (y & 7));
}

void frame() {
  memset(fb, 0, sizeof(fb));
  for (int x = 0; x < 128; x++) { px(x, 0); px(x, 63); }
  for (int y = 0; y < 64; y++) { px(0, y); px(127, y); }
}

void drawArrowV(bool down) {
  frame();
  for (int i = 0; i < 24; i++) { int y = down ? 56 - i : 8 + i; for (int x = 64 - i; x <= 64 + i; x++) px(x, y); }
  for (int y = 0; y < 24; y++) { int yy = down ? 10 + y : 32 + y; for (int x = 56; x <= 72; x++) px(x, yy); }
}

void drawArrowH(bool right) {
  frame();
  for (int i = 0; i < 26; i++) { int x = right ? 110 - i : 17 + i; for (int y = 32 - i; y <= 32 + i; y++) px(x, y); }
  for (int x = 0; x < 40; x++) { int xx = right ? 45 + x : 43 + x; for (int y = 25; y <= 39; y++) px(xx, y); }
}

void drawXO(bool x) {
  frame();
  if (x) {
    for (int t = -22; t <= 22; t++) for (int w = -4; w <= 4; w++) { px(64 + t + w, 32 + t); px(64 + t + w, 32 - t); }
  } else {
    for (int y = -24; y <= 24; y++) for (int xx = -24; xx <= 24; xx++) {
      int r2 = xx * xx + y * y;
      if (r2 <= 24 * 24 && r2 >= 17 * 17) px(64 + xx, 32 + y);
    }
  }
}

bool probe(Bus &b, uint8_t a) {   // NOP 探測；硬體匯流排走 HalBus::ack()（會先重設）
  uint8_t d[2] = {0x00, 0xE3};
  return b.write(a, d, 2);
}

void setup() {
  Serial.begin(115200);
  Serial.println("[W1] boot " FW_TAG);
  busWire.begin();
  busWire1.begin();
  busSoft.begin();
  Camera.configVideoChannel(3, configNN);   // RGB（NN）只能在第 3 號通道
  Camera.videoInit();
  ObjDet.configVideo(configNN);
  ObjDet.modelSelect(OBJECT_DETECTION, CUSTOMIZED_YOLOV7TINY, NA_MODEL, NA_MODEL);   // SD 卡 NN_MDL/yolov7_tiny.nb
  ObjDet.begin();
  videoStreamerNN.registerInput(Camera.getStream(3));
  videoStreamerNN.setStackSize();
  videoStreamerNN.registerOutput(ObjDet);
  videoStreamerNN.begin();
  Camera.channelBegin(3);
  Serial.println("[W1] camera + NN started");
  int st = WL_IDLE_STATUS;
  while (st != WL_CONNECTED) { st = WiFi.begin(ssid, pass); delay(2000); }
  Serial.print("[W1] IP="); Serial.println(WiFi.localIP());
  ota.start_OTA_threads(OTA_SERVER_PORT, server);
}

void loop() {
  static unsigned long last = 0;
  static bool flip = false;
  if (millis() - last < 5000) { delay(50); return; }
  last = millis();
  flip = !flip;
  struct { Bus *b; const char *name; int kind; } buses[] = {
    {&busWire, "Wire  (Pin3/4)  corner", 0}, {&busWire1, "Wire1 (Pin0/1)  arm   ", 1}, {&busSoft, "Soft  (Pin18/19) center", 2}};
  Serial.print("[W1] " FW_TAG);
  for (auto &e : buses) {
    bool ack = probe(*e.b, 0x3C);
    unsigned long t0 = micros();
    if (ack) {
      if (e.kind == 0) drawArrowH(flip); else if (e.kind == 1) drawArrowV(flip); else drawXO(flip);
      oledInit(*e.b, 0x3C);
      flush(*e.b, 0x3C);
    }
    Serial.print(" | "); Serial.print(e.name); Serial.print(ack ? " 0x3C drawn " : " absent ");
    if (ack) { Serial.print((micros() - t0) / 1000); Serial.print("ms"); }
  }
  Serial.print(" | NN dets "); Serial.print((int)ObjDet.getResult().size());
  Serial.println(flip ? " | shown: RIGHT / DOWN / X" : " | shown: LEFT / UP / O");
}
