// EvacOled：HUB-8735 Ultra 一台板子同時驅動多塊 SSD1306，各自顯示避難方向。
//
// 接法（每塊 OLED 一筆 SlotConfig，可混用）：
//   - Bus::Wire0：Pin3 SDA / Pin4 SCL（Wire 的腳位）
//   - Bus::Wire1：Pin0 SDA / Pin1 SCL（Wire1 的腳位）
//   - Bus::Soft ：Pin18 SDA / Pin19 SCL
//   三條預設都是軟體 I2C（各自獨立），腳位可用 setBusPins() 改。2026-11-24：hub_node 跑起鏡頭／NN／SD 之後，
//   HAL 硬體 I2C 的 TX_COMPLETE 回呼永遠不來（探測 0 成功），原因未明；同樣的程式單獨跑（wire1_test v11）正常。
//   所以硬體路徑改成選項 useHardwareI2C(true)，預設不用。
//   - 每條線上 0x3C、0x3D 各一塊；或 TCA9548A 多工器（預設 0x70）的 8 個通道各一塊（muxChannel = 0..7）
// 螢幕：128x64（0.96 吋）與 128x32（0.91 吋）可混用。
//
// 選用的硬體路徑（useHardwareI2C(true)）不經 Arduino Wire，直接用 SDK 的 HAL i2c_t（wire1_test v9–v11）：
//   - Wire::endTransmission() 每 byte 固定等 200 µs，整張 128x64 要 236 ms。原因是 HAL i2c_write 在資料送完前就返回；
//     EvacOled 改成每筆等 TX_COMPLETE 回呼（逾時 n×200 µs＋2 ms 就重設匯流排），100 kHz 約 0.12 秒／張（wire1_test v11）。
//   - 預設 100 kHz：400 kHz 在杜邦線＋模組上拉下實測不穩（位址有 ACK、畫面資料卻傳錯，螢幕不亮），wire1_test v10。
//   - HAL i2c_write 的回傳值不反映 NACK，NACK 之後匯流排還會卡住。所以每次跟一塊螢幕講話前，先重設匯流排、
//     送一個 NOP，用 TX_COMPLETE 回呼判斷有沒有 ACK（1 ms 內），再重設一次；沒 ACK 就不寫，螢幕標成離線。
//   → 程式裡用了 EvacOled 的硬體匯流排，就不能再對同一組腳位呼叫 Wire.begin()／Wire1.begin()。
// 軟體 I2C 用 HAL gpio_t（不用 pinMode，那會每次印警告）：資料位元推挽輸出，第 9 拍才把 SDA 切成輸入讀 ACK，
//   每個 byte 都檢查 ACK，NACK 就結束這次傳輸，不會卡住；一張約 29 ms。
//
// 不依賴 Adafruit GFX：圖示是預先算好的點陣（EvacIconData.h，由 tools/gen_icons.py 產生），
// 直接從 flash 串流到螢幕，不佔 RAM 畫面緩衝。
#pragma once

#include <Arduino.h>

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

enum class Bus : uint8_t { Wire0, Wire1, Soft };

constexpr int8_t kNoMux = -1;
constexpr uint8_t kMaxSlots = 16;

struct SlotConfig {
  const char *id;    // 路口代號，對應伺服器的 id（例 "J(0,0)"）
  Bus bus;           // 接在哪條匯流排（有多工器時 = 多工器所在的那條）
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
  // 某條匯流排的腳位（Arduino 腳位編號），要在 begin() 之前設定。預設 Wire0 = 3/4、Wire1 = 0/1、Soft = 18/19
  void setBusPins(Bus b, uint8_t sdaPin, uint8_t sclPin) { pinSda_[(uint8_t)b] = sdaPin; pinScl_[(uint8_t)b] = sclPin; }
  void setSoftPins(uint8_t sdaPin, uint8_t sclPin) { setBusPins(Bus::Soft, sdaPin, sclPin); }   // 舊名稱
  // true：Wire0／Wire1 改走 HAL 硬體 I2C（100 kHz）。hub_node 實測不通、原因未明，預設 false（全部軟體 I2C）
  void useHardwareI2C(bool on) { useHal_ = on; }

  // slots 必須在 EvacOled 的生命週期內有效（通常是全域 const 陣列）
  // 回傳成功初始化的螢幕數（每塊最多試 3 次）；沒接上的會在 update() 中每 2 秒重試
  uint8_t begin(const SlotConfig *slots, uint8_t count,
                const MuxConfig *mux = nullptr, uint32_t clockHz = 100000);

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

  // 在第 i 塊螢幕直接畫一張整頁點陣（SSD1306 頁格式，128x64 = 1024 bytes、128x32 = 512 bytes），並開顯示。
  // 例如 OTA 時的「更新中」。之後再呼叫 update() 時，這塊會整張重畫回方向。回傳是否送達（有 ACK）。
  bool drawBitmap(uint8_t i, const uint8_t *bitmap);

  uint8_t count() const { return count_; }
  bool online(uint8_t i) const { return i < count_ && state_[i].online; }
  int indexOf(const char *id) const;
  Sign sign(uint8_t i) const { return i < count_ ? state_[i].sign : Sign::Off; }

  // 閃爍週期（亮、暗各半），預設 500 ms → 1 Hz
  void setBlinkPeriod(uint16_t ms) { blinkPeriod_ = ms; }

  // 掃描並列出每條匯流排（含多工器各通道）看得到的位址，接線除錯用
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

  bool select(const SlotConfig &c);
  bool reach(const SlotConfig &c);                                   // 這塊有沒有 ACK（也讓匯流排回到乾淨狀態）
  bool command(const SlotConfig &c, const uint8_t *cmds, uint8_t n); // reach() 後送指令
  bool sendData(const SlotConfig &c, const uint8_t *d, uint8_t n);  // 送一段畫面資料（0x40 開頭）
  bool initPanel(uint8_t i);
  bool draw(uint8_t i, int8_t icon);
  int8_t iconFor(const SlotConfig &c, Sign s) const;

  const SlotConfig *slots_ = nullptr;
  uint8_t count_ = 0;
  MuxConfig mux_{};
  bool hasMux_ = false;
  int8_t muxSelected_ = -2;  // 目前多工器開著哪個通道；-2 = 未知
  uint8_t pinSda_[3] = {3, 0, 18}, pinScl_[3] = {4, 1, 19};
  bool useHal_ = false;
  State state_[kMaxSlots];
  uint16_t blinkPeriod_ = 500;
  bool blinkOn_ = true;
  uint32_t blinkAt_ = 0;
};

}  // namespace evac
