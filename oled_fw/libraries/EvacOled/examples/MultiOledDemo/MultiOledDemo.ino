// 多塊 SSD1306 方向顯示示範（HUB-8735 Ultra）
//
// EVAC_WIRING 選接法（改下面的預設值；用 build.extra_flags 指定時見 README「編譯」）：
//   1 = Wire 上 0x3C、0x3D 兩塊              （Pin3 SDA / Pin4 SCL）
//   2 = Wire 兩塊 + Wire1 兩塊，最多 4 塊     （Wire1：Pin0 SDA / Pin1 SCL）
//   3 = Wire 上接 TCA9548A（0x70），8 個通道各一塊
//
// 預設全部 0.96 吋 128x64；0.91 吋把 panel 改成 Panel::P128x32。
//
// 開機後每 3 秒換一個方向輪播。序列埠（115200）可輸入：
//   [{"id":"A","dir":"E"},{"id":"B","dir":"X","blink":true}]   伺服器格式
//   A NE        單一路口；後面加 b 表示閃爍，例：B UP b
//   auto        回到輪播
//   scan        掃描 I2C 位址
#include <EvacOled.h>

#ifndef EVAC_WIRING
#define EVAC_WIRING 1
#endif

using namespace evac;

#if EVAC_WIRING == 1
const SlotConfig kSlots[] = {
    {"A", Bus::Wire0, 0x3C, kNoMux, Panel::P128x64, Compass::N, false},
    {"B", Bus::Wire0, 0x3D, kNoMux, Panel::P128x64, Compass::N, false},
};
const MuxConfig *kMux = nullptr;
#elif EVAC_WIRING == 2
const SlotConfig kSlots[] = {
    {"A", Bus::Wire0, 0x3C, kNoMux, Panel::P128x64, Compass::N, false},
    {"B", Bus::Wire0, 0x3D, kNoMux, Panel::P128x64, Compass::N, false},
    {"C", Bus::Wire1, 0x3C, kNoMux, Panel::P128x64, Compass::N, false},
    {"D", Bus::Wire1, 0x3D, kNoMux, Panel::P128x64, Compass::N, false},
};
const MuxConfig *kMux = nullptr;
#elif EVAC_WIRING == 3
const SlotConfig kSlots[] = {
    {"A", Bus::Wire0, 0x3C, 0, Panel::P128x64, Compass::N, false},
    {"B", Bus::Wire0, 0x3C, 1, Panel::P128x64, Compass::N, false},
    {"C", Bus::Wire0, 0x3C, 2, Panel::P128x64, Compass::N, false},
    {"D", Bus::Wire0, 0x3C, 3, Panel::P128x64, Compass::N, false},
    {"E", Bus::Wire0, 0x3C, 4, Panel::P128x64, Compass::N, false},
    {"F", Bus::Wire0, 0x3C, 5, Panel::P128x64, Compass::N, false},
    {"G", Bus::Wire0, 0x3C, 6, Panel::P128x64, Compass::N, false},
    {"H", Bus::Wire0, 0x3C, 7, Panel::P128x64, Compass::N, false},
};
const MuxConfig kMuxCfg = {Bus::Wire0, 0x70};
const MuxConfig *kMux = &kMuxCfg;
#else
#error "EVAC_WIRING 只能是 1、2、3"
#endif

constexpr uint8_t kCount = sizeof(kSlots) / sizeof(kSlots[0]);

const Sign kTour[] = {Sign::N,  Sign::E,  Sign::S,    Sign::W,      Sign::NE, Sign::SE,
                      Sign::SW, Sign::NW, Sign::Up,   Sign::Down,   Sign::Blocked};
constexpr uint8_t kTourLen = sizeof(kTour) / sizeof(kTour[0]);

EvacOled oled;
bool autoTour = true;
uint8_t tourStep = 0;
uint32_t tourAt = 0;
char line[256];
size_t lineLen = 0;

void showTour() {
  // 每塊錯開一格，一眼看出各自獨立；最後一塊用閃爍
  for (uint8_t i = 0; i < kCount; ++i) {
    oled.setIndex(i, kTour[(tourStep + i) % kTourLen], i == kCount - 1);
  }
  tourStep = (tourStep + 1) % kTourLen;
}

void handleLine(char *s) {
  while (*s == ' ') ++s;
  if (!*s) return;
  if (strcmp(s, "scan") == 0) {
    oled.scan(Serial);
    return;
  }
  if (strcmp(s, "auto") == 0) {
    autoTour = true;
    return;
  }
  autoTour = false;
  if (strchr(s, '{')) {
    Serial.print("applyJson: ");
    Serial.println(oled.applyJson(s));
    return;
  }
  char *id = strtok(s, " ");
  char *dir = strtok(nullptr, " ");
  char *flag = strtok(nullptr, " ");
  Sign sign;
  if (!id || !dir || !parseSign(dir, sign) || !oled.set(id, sign, flag && *flag == 'b')) {
    Serial.println("?? 格式：<id> <N|NE|E|SE|S|SW|W|NW|UP|DOWN|X|OFF> [b]");
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  uint8_t ok = oled.begin(kSlots, kCount, kMux);
  Serial.print("EvacOled wiring ");
  Serial.print(EVAC_WIRING);
  Serial.print(": ");
  Serial.print(ok);
  Serial.print("/");
  Serial.print(kCount);
  Serial.println(" online");
  oled.scan(Serial);
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[lineLen] = 0;
      handleLine(line);
      lineLen = 0;
    } else if (lineLen + 1 < sizeof(line)) {
      line[lineLen++] = c;
    }
  }
  if (autoTour && millis() - tourAt >= 3000) {
    tourAt = millis();
    showTour();
  }
  oled.update();
  delay(10);
}
