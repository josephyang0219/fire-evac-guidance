// Wire1（Pin0 SDA／Pin1 SCL）桌上實測，含 OTA，可用 ota_server.py 無線推送。
// 接線：OLED GND→GND、VCC→3.3V、SCL→Pin1、SDA→Pin0（只接 Wire1）。光感測器先拔掉。
// 每 5 秒掃描 Wire（Pin3/4）與 Wire1（Pin0/1），印出找到的位址；
// Wire1 上有 0x3C／0x3D 就初始化 SSD1306，畫一個向上箭頭＋外框，之後每 5 秒左右翻轉一次（看得出有在更新）。
// 編譯：FQBN 加 :08_OTAMode=Enable,06_LoadNNModelSource=sd；Wi-Fi 設定在 secrets.h（不進 git）。
#include <WiFi.h>
#include <Wire.h>
#include "OTA.h"
#include "secrets.h"

#define FW_TAG "wire1_test v3"

char ssid[] = WIFI_SSID;
char pass[] = WIFI_PASS;
char server[] = OTA_SERVER_IP;
OTA ota;

static uint8_t fb[128 * 64 / 8];
uint8_t oledAddr = 0;
bool flip = false;

void cmd(TwoWire &w, uint8_t a, uint8_t c) {
  w.beginTransmission(a); w.write(0x00); w.write(c); w.endTransmission();
}

bool oledInit(TwoWire &w, uint8_t a) {
  const uint8_t seq[] = {0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14, 0x20, 0x00,
                         0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF};
  for (uint8_t c : seq) cmd(w, a, c);
  return true;
}

void px(int x, int y) {
  if (x < 0 || x >= 128 || y < 0 || y >= 64) return;
  fb[x + (y / 8) * 128] |= (1 << (y & 7));
}

void drawArrow(bool down) {
  memset(fb, 0, sizeof(fb));
  for (int x = 0; x < 128; x++) { px(x, 0); px(x, 63); }
  for (int y = 0; y < 64; y++) { px(0, y); px(127, y); }
  for (int i = 0; i < 24; i++) {             // 箭頭三角形
    int y = down ? 56 - i : 8 + i;
    for (int x = 64 - i; x <= 64 + i; x++) px(x, y);
  }
  for (int y = 0; y < 24; y++) {              // 箭桿
    int yy = down ? 10 + y : 32 + y;
    for (int x = 56; x <= 72; x++) px(x, yy);
  }
}

void flush(TwoWire &w, uint8_t a) {
  cmd(w, a, 0x21); cmd(w, a, 0); cmd(w, a, 127);
  cmd(w, a, 0x22); cmd(w, a, 0); cmd(w, a, 7);
  for (int i = 0; i < (int)sizeof(fb); i += 16) {
    w.beginTransmission(a); w.write(0x40);
    for (int j = 0; j < 16; j++) w.write(fb[i + j]);
    w.endTransmission();
  }
}

// SDK 4.0.15 的 endTransmission() 在 0 bytes 時不管有沒有 ACK 都回 0（實測 1～126 全部「有回應」），
// 所以改送 1 個 byte（0x00，對 SSD1306 是無害的控制位元組）來探測；回應超過 8 個位址就視為掃描不可靠。
String scan(TwoWire &w) {
  String s;
  int n = 0;
  for (uint8_t a = 0x08; a < 0x78; a++) {
    w.beginTransmission(a);
    w.write((uint8_t)0x00);
    if (w.endTransmission() == 0) { char b[8]; snprintf(b, sizeof(b), " 0x%02X", a); s += b; n++; }
  }
  if (n > 8) return String(" (scan unreliable: ") + n + " addrs ACK)";
  return n ? s : String(" (none)");
}

void setup() {
  Serial.begin(115200);
  Serial.println("[W1] boot " FW_TAG);
  Wire.begin();
  Wire1.begin();
  int st = WL_IDLE_STATUS;
  while (st != WL_CONNECTED) { st = WiFi.begin(ssid, pass); delay(2000); }
  Serial.print("[W1] IP="); Serial.println(WiFi.localIP());
  ota.start_OTA_threads(OTA_SERVER_PORT, server);
}

void loop() {
  static unsigned long last = 0;
  if (millis() - last < 5000) { delay(50); return; }
  last = millis();
  String s0 = scan(Wire), s1 = scan(Wire1);
  Serial.print("[W1] " FW_TAG " Wire(Pin3/4):"); Serial.print(s0);
  Serial.print(" | Wire1(Pin0/1):"); Serial.println(s1);
  // v3：不靠掃描，直接對 Wire1 的 0x3C 和 0x3D 都送初始化＋畫圖（掃描結果只當參考）。
  // 每次都重送初始化，OLED 中途才接上也能亮。
  drawArrow(flip); flip = !flip;
  for (uint8_t a = 0x3C; a <= 0x3D; a++) {
    oledInit(Wire1, a);
    flush(Wire1, a);
    Wire1.beginTransmission(a); Wire1.write((uint8_t)0x00); Wire1.write((uint8_t)0xE3);   // NOP，看回傳值
    int rc = Wire1.endTransmission();
    Serial.print("[W1] Wire1 0x"); Serial.print(a, HEX); Serial.print(" draw sent, NOP rc="); Serial.println(rc);
  }
  Serial.println(flip ? "[W1] drew arrow UP" : "[W1] drew arrow DOWN");
}
