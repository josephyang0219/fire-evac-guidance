// 1F 天花板 9 塊 OLED 的建議分配：每台 HUB 只驅動自己附近的路口。
//
//   NW ── N ── NE        HUB_N：N (0x3C) + NW (0x3D)            Wire
//   │     │     │        HUB_E：E (0x3C) + NE (0x3D)            Wire
//   W ─── C ─── E        HUB_S：S (0x3C) + SE (0x3D)            Wire
//   │     │     │        HUB_W：W (0x3C) + SW (0x3D)            Wire
//   SW ── S ── SE               C (0x3C)                        Wire1
//
// 全部 0.96 吋 128x64。NW、NE、SE、SW 四塊要把背面 IIC ADDRESS SELECT 電阻改焊到 0x7A（= 0x3D），
// 步驟見 README。
// 用 -DEVAC_HUB=0..3（N/E/S/W）或改下面的預設值選這台板子的位置。
//
// 伺服器回應：{"oled":[{"id":"N","dir":"W"},{"id":"NW","dir":"S","blink":true}]}
// 這裡沒有網路，改成從序列埠一次貼一行 JSON；接上 hub_node 時把 HTTP 回應字串交給
// oled.applyJson()（新格式）或 oled.applyLeds()（現有 {"leds":[...]} 格式）即可。
#include <EvacOled.h>

#ifndef EVAC_HUB
#define EVAC_HUB 0
#endif

using namespace evac;

// top / ceiling：螢幕上緣朝向與是否朝下裝在天花板。模型尚未實裝，先假設上緣朝北、朝下裝；
// 裝好後依實際方向改 top，並用序列埠送 {"id":"N","dir":"N"} 確認箭頭指向北。
#if EVAC_HUB == 0
const char *kHubName = "HUB_N";
const SlotConfig kSlots[] = {
    {"N", Bus::Wire0, 0x3C, kNoMux, Panel::P128x64, Compass::N, true},
    {"NW", Bus::Wire0, 0x3D, kNoMux, Panel::P128x64, Compass::N, true},
};
#elif EVAC_HUB == 1
const char *kHubName = "HUB_E";
const SlotConfig kSlots[] = {
    {"E", Bus::Wire0, 0x3C, kNoMux, Panel::P128x64, Compass::N, true},
    {"NE", Bus::Wire0, 0x3D, kNoMux, Panel::P128x64, Compass::N, true},
};
#elif EVAC_HUB == 2
const char *kHubName = "HUB_S";
const SlotConfig kSlots[] = {
    {"S", Bus::Wire0, 0x3C, kNoMux, Panel::P128x64, Compass::N, true},
    {"SE", Bus::Wire0, 0x3D, kNoMux, Panel::P128x64, Compass::N, true},
};
#elif EVAC_HUB == 3
const char *kHubName = "HUB_W";
const SlotConfig kSlots[] = {
    {"W", Bus::Wire0, 0x3C, kNoMux, Panel::P128x64, Compass::N, true},
    {"SW", Bus::Wire0, 0x3D, kNoMux, Panel::P128x64, Compass::N, true},
    {"C", Bus::Wire1, 0x3C, kNoMux, Panel::P128x64, Compass::N, true},
};
#else
#error "EVAC_HUB 只能是 0..3"
#endif

constexpr uint8_t kCount = sizeof(kSlots) / sizeof(kSlots[0]);

EvacOled oled;
char line[512];
size_t lineLen = 0;

void setup() {
  Serial.begin(115200);
  delay(200);
  uint8_t ok = oled.begin(kSlots, kCount);
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
      int n = strstr(line, "\"leds\"") ? oled.applyLeds(line) : oled.applyJson(line);
      Serial.print("applied ");
      Serial.println(n);
      lineLen = 0;
    } else if (lineLen + 1 < sizeof(line)) {
      line[lineLen++] = c;
    }
  }
  oled.update();
  delay(10);
}
