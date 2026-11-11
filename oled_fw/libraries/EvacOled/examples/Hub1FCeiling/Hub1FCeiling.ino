// 1F 天花板 9 塊 OLED：4 台角落 HUB 各 1 塊，第 5 台（只驅動 OLED）負責中心＋4 個邊中點。
//
//   NW ── N ── NE        EVAC_HUB=0..3（N/E/S/W 四台，跑鏡頭＋模型）：
//   │     │     │          Wire 0x3D 接一個角落：N→NW、E→NE、S→SE、W→SW
//   W ─── C ─── E        EVAC_HUB=4（第 5 台，只驅動 OLED）：
//   │     │     │          EVAC_HUB5_BUS=2（預設）：Wire 上的 TCA9548A（0x70），
//   SW ── S ── SE            通道 0..4 = C、N、E、S、W，全部 0x3C，不用改焊
//                          EVAC_HUB5_BUS=1（備案）：Wire 0x3C/0x3D ＋ Wire1 0x3C/0x3D，
//                            最多 4 塊，不夠 5 塊，W 會沒有螢幕
//
// 全部 0.96 吋 128x64。接線與步驟見 README。
//
// 伺服器回應：{"oled":[{"id":"N","dir":"W"},{"id":"NW","dir":"S","blink":true}]}
// 這裡沒有網路，改成從序列埠一次貼一行 JSON（或輸入 scan）；接上 hub_node 時把 HTTP 回應字串交給
// oled.applyJson()（新格式）或 oled.applyLeds()（現有 {"leds":[...]} 格式）即可。
#include <EvacOled.h>

#ifndef EVAC_HUB
#define EVAC_HUB 0
#endif
// 角落螢幕的位址。每台角落 HUB 只有一塊，用出廠 0x3C 也行（就不必改焊）；照目前規劃用 0x3D。
#ifndef EVAC_CORNER_ADDR
#define EVAC_CORNER_ADDR 0x3D
#endif
// 第 5 台的接法：2 = TCA9548A（主要做法），1 = Wire＋Wire1（備案，最多 4 塊）
#ifndef EVAC_HUB5_BUS
#define EVAC_HUB5_BUS 2
#endif
// 備案時 Wire1 上接幾塊（1 或 2）
#ifndef EVAC_WIRE1_COUNT
#define EVAC_WIRE1_COUNT 2
#endif

using namespace evac;

// top / ceiling：螢幕上緣朝向與是否朝下裝在天花板。模型尚未實裝，先假設上緣朝北、朝下裝；
// 裝好後依實際方向改 top，並用序列埠送 {"id":"N","dir":"N"} 確認箭頭指向北。
#define OLED(id, bus, addr, ch) {id, bus, addr, ch, Panel::P128x64, Compass::N, true}

#if EVAC_HUB == 0
const char *kHubName = "HUB_N";
const SlotConfig kSlots[] = {OLED("NW", Bus::Wire0, EVAC_CORNER_ADDR, kNoMux)};
const MuxConfig *const kMux = nullptr;
#elif EVAC_HUB == 1
const char *kHubName = "HUB_E";
const SlotConfig kSlots[] = {OLED("NE", Bus::Wire0, EVAC_CORNER_ADDR, kNoMux)};
const MuxConfig *const kMux = nullptr;
#elif EVAC_HUB == 2
const char *kHubName = "HUB_S";
const SlotConfig kSlots[] = {OLED("SE", Bus::Wire0, EVAC_CORNER_ADDR, kNoMux)};
const MuxConfig *const kMux = nullptr;
#elif EVAC_HUB == 3
const char *kHubName = "HUB_W";
const SlotConfig kSlots[] = {OLED("SW", Bus::Wire0, EVAC_CORNER_ADDR, kNoMux)};
const MuxConfig *const kMux = nullptr;

#elif EVAC_HUB == 4 && EVAC_HUB5_BUS == 2
const char *kHubName = "HUB_OLED (TCA9548A)";
const SlotConfig kSlots[] = {
    OLED("C", Bus::Wire0, 0x3C, 0),
    OLED("N", Bus::Wire0, 0x3C, 1),
    OLED("E", Bus::Wire0, 0x3C, 2),
    OLED("S", Bus::Wire0, 0x3C, 3),
    OLED("W", Bus::Wire0, 0x3C, 4),
};
const MuxConfig kMuxCfg = {Bus::Wire0, 0x70};
const MuxConfig *const kMux = &kMuxCfg;

#elif EVAC_HUB == 4 && EVAC_HUB5_BUS == 1
// 備案：每條匯流排只有 0x3C、0x3D 兩個位址 → 最多 4 塊，W 沒有螢幕。
// Wire1 = Pin0 SDA / Pin1 SCL；Pin0 同時是光感測器 AO（A2），用了就不能接光感測器。
const char *kHubName = "HUB_OLED (Wire+Wire1 backup)";
const SlotConfig kSlots[] = {
    OLED("C", Bus::Wire0, 0x3C, kNoMux),
    OLED("N", Bus::Wire0, 0x3D, kNoMux),
    OLED("E", Bus::Wire1, 0x3C, kNoMux),
#if EVAC_WIRE1_COUNT >= 2
    OLED("S", Bus::Wire1, 0x3D, kNoMux),
#endif
};
const MuxConfig *const kMux = nullptr;

#else
#error "EVAC_HUB 只能是 0..4；EVAC_HUB5_BUS 只能是 1 或 2"
#endif

constexpr uint8_t kCount = sizeof(kSlots) / sizeof(kSlots[0]);

EvacOled oled;
char line[512];
size_t lineLen = 0;

void setup() {
  Serial.begin(115200);
  delay(200);
  uint8_t ok = oled.begin(kSlots, kCount, kMux);
  Serial.print(kHubName);
  Serial.print(" OLED online ");
  Serial.print(ok);
  Serial.print("/");
  Serial.println(kCount);
  // 收到第一筆指令前保持全黑（平時不顯示）
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[lineLen] = 0;
      if (strcmp(line, "scan") == 0) {
        oled.scan(Serial);
      } else {
        int n = strstr(line, "\"leds\"") ? oled.applyLeds(line) : oled.applyJson(line);
        Serial.print("applied ");
        Serial.println(n);
      }
      lineLen = 0;
    } else if (lineLen + 1 < sizeof(line)) {
      line[lineLen++] = c;
    }
  }
  oled.update();
  delay(10);
}
