// EvacOled：HUB-8735 Ultra 一台板子同時驅動多塊 SSD1306，各自顯示避難方向。
//
// 接法（每塊 OLED 一筆 SlotConfig，可混用）：
//   - Wire（Pin3 SDA / Pin4 SCL）上 0x3C、0x3D 各一塊
//   - Wire1（Pin0 SDA / Pin1 SCL）上再 0x3C、0x3D 各一塊，合計 4 塊
//   - TCA9548A 多工器（預設 0x70）的 8 個通道各一塊（muxChannel = 0..7）
// 螢幕：128x64（0.96 吋）與 128x32（0.91 吋）可混用。
//
// 不依賴 Adafruit GFX：圖示是預先算好的點陣（EvacIconData.h，由 tools/gen_icons.py 產生），
// 直接從 flash 串流到螢幕，不佔 RAM 畫面緩衝。
#pragma once

#include <Arduino.h>
#include <Wire.h>

namespace evac {

// 伺服器送來的方向（絕對方位，與螢幕怎麼裝無關）
enum class Sign : uint8_t {
  Off = 0,
  N, NE, E, SE, S, SW, W, NW,  // 平面方向
  Up,                          // 上樓梯
  Down,                        // 下樓梯
  Blocked,                     // X：禁止通行
};

// 方位，0 = 北、順時針每格 45°
enum class Compass : uint8_t { N = 0, NE, E, SE, S, SW, W, NW };

enum class Panel : uint8_t { P128x64, P128x32 };

enum class Bus : uint8_t { Wire0, Wire1 };

constexpr int8_t kNoMux = -1;
constexpr uint8_t kMaxSlots = 16;

struct SlotConfig {
  const char *id;    // 路口代號，對應伺服器的 id（例 "NW"、"C"）
  Bus bus;           // 接在哪組 I2C（有多工器時 = 多工器所在的那組）
  uint8_t addr;      // 0x3C 或 0x3D
  int8_t muxChannel; // kNoMux，或 TCA9548A 通道 0..7
  Panel panel;
  Compass top;       // 螢幕上緣朝哪個方位
  bool ceiling;      // true = 螢幕朝下裝在天花板（從下往上看，左右相反）
};

struct MuxConfig {
  Bus bus;
  uint8_t addr;      // TCA9548A：0x70..0x77
};

// "N"、"ne"、"UP"、"DOWN"、"X"、"OFF"…；不認得回傳 false
bool parseSign(const char *s, Sign &out);
const char *signName(Sign s);

class EvacOled {
 public:
  // slots 必須在 EvacOled 的生命週期內有效（通常是全域 const 陣列）
  // 回傳成功初始化的螢幕數；沒接上的會在 update() 中每 2 秒重試
  uint8_t begin(const SlotConfig *slots, uint8_t count,
                const MuxConfig *mux = nullptr, uint32_t clockHz = 400000);

  bool set(const char *id, Sign sign, bool blink = false);
  bool setIndex(uint8_t i, Sign sign, bool blink = false);
  void setAll(Sign sign, bool blink = false);

  // 解析伺服器回應：找出所有含 "id"、"dir" 的物件，例如
  //   [{"id":"NW","dir":"E"},{"id":"C","dir":"X","blink":true}]
  //   {"oled":[{"id":"N","dir":"W"}]}
  // 未列出的路口保持原狀（斷線時保留最後方向）。回傳套用的筆數。
  int applyJson(const char *json);

  // 相容現有 hub_node 的回應 {"leds":["E","S"],"blink":0}：
  // leds 陣列依序套到第 0、1、2… 塊螢幕；"blink" 非 0 時全部閃爍。回傳套用的筆數。
  int applyLeds(const char *json);

  // 放在 loop() 裡：重畫有變的螢幕、處理閃爍、重試離線的螢幕
  void update();

  uint8_t count() const { return count_; }
  bool online(uint8_t i) const { return i < count_ && state_[i].online; }
  int indexOf(const char *id) const;
  Sign sign(uint8_t i) const { return i < count_ ? state_[i].sign : Sign::Off; }

  // 閃爍週期（亮、暗各半），預設 500 ms → 1 Hz
  void setBlinkPeriod(uint16_t ms) { blinkPeriod_ = ms; }

  // 掃描並列出每組 I2C（含多工器各通道）看得到的位址，接線除錯用
  void scan(Print &out);

 private:
  struct State {
    Sign sign = Sign::Off;
    bool blink = false;
    bool online = false;
    bool dirty = true;
    bool shownOn = true;     // 目前顯示是否開著（閃爍用）
    int8_t drawnIcon = -2;   // 螢幕上現在的圖示；-1 = 全黑，-2 = 未知
    uint32_t retryAt = 0;
  };

  TwoWire &wire(Bus b);
  bool select(const SlotConfig &c);
  bool command(const SlotConfig &c, const uint8_t *cmds, uint8_t n);
  bool initPanel(uint8_t i);
  bool draw(uint8_t i, int8_t icon);
  int8_t iconFor(const SlotConfig &c, Sign s) const;

  const SlotConfig *slots_ = nullptr;
  uint8_t count_ = 0;
  MuxConfig mux_{};
  bool hasMux_ = false;
  int8_t muxSelected_ = -2;  // 目前多工器開著哪個通道；-2 = 未知
  State state_[kMaxSlots];
  uint16_t blinkPeriod_ = 500;
  bool blinkOn_ = true;
  uint32_t blinkAt_ = 0;
};

}  // namespace evac
