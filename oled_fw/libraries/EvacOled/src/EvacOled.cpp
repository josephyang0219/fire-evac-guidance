#include "EvacOled.h"

#include <stdio.h>
#include <string.h>

#include "EvacIconData.h"

extern "C" {
#include "gpio_api.h"
#include "i2c_api.h"
#include "i2c_ex_api.h"
}

namespace evac {

namespace {

constexpr uint8_t kWidth = 128;
constexpr uint8_t kChunk = 16;        // 每次 I2C 傳輸的畫面資料量（wire1_test v9 實測用 16＋1 byte）
constexpr uint32_t kRetryMs = 2000;

constexpr int8_t kIconStairsUp = 8;
constexpr int8_t kIconStairsDown = 9;
constexpr int8_t kIconBlocked = 10;
constexpr int8_t kIconBlank = -1;
constexpr int8_t kIconUnknown = -2;

struct NameMap {
  const char *name;
  Sign sign;
};

const NameMap kNames[] = {
    {"OFF", Sign::Off}, {"N", Sign::N},   {"NE", Sign::NE},     {"E", Sign::E},
    {"SE", Sign::SE},   {"S", Sign::S},   {"SW", Sign::SW},     {"W", Sign::W},
    {"NW", Sign::NW},   {"UP", Sign::Up}, {"DOWN", Sign::Down}, {"X", Sign::Blocked},
    // 別名
    {"", Sign::Off},    {"NONE", Sign::Off}, {"BLOCKED", Sign::Blocked},
};

bool equalsIgnoreCase(const char *a, const char *b) {
  while (*a && *b) {
    char ca = *a, cb = *b;
    if (ca >= 'a' && ca <= 'z') ca -= 32;
    if (cb >= 'a' && cb <= 'z') cb -= 32;
    if (ca != cb) return false;
    ++a;
    ++b;
  }
  return *a == *b;
}

uint8_t pages(Panel p) { return p == Panel::P128x64 ? 8 : 4; }

const uint8_t *iconData(Panel p, int8_t icon) {
  return p == Panel::P128x64 ? EVAC_ICON_64[icon] : EVAC_ICON_32[icon];
}

// 在 [p, end) 內找 "key" 後面的值起點；找不到回傳 nullptr
const char *findValue(const char *p, const char *end, const char *key) {
  size_t klen = strlen(key);
  for (; p + klen + 2 <= end; ++p) {
    if (p[0] != '"' || strncmp(p + 1, key, klen) != 0 || p[klen + 1] != '"') continue;
    const char *q = p + klen + 2;
    while (q < end && (*q == ' ' || *q == '\t' || *q == '\r' || *q == '\n')) ++q;
    if (q >= end || *q != ':') continue;
    ++q;
    while (q < end && (*q == ' ' || *q == '\t' || *q == '\r' || *q == '\n')) ++q;
    return q < end ? q : nullptr;
  }
  return nullptr;
}

bool findString(const char *p, const char *end, const char *key, char *buf, size_t len) {
  const char *v = findValue(p, end, key);
  if (!v || *v != '"') return false;
  ++v;
  size_t n = 0;
  while (v < end && *v != '"') {
    if (n + 1 >= len) return false;
    buf[n++] = *v++;
  }
  if (v >= end) return false;
  buf[n] = '\0';
  return true;
}

bool findBlink(const char *p, const char *end) {
  const char *v = findValue(p, end, "blink");
  if (v && (end - v) >= 4 && strncmp(v, "true", 4) == 0) return true;
  char mode[12];
  return findString(p, end, "mode", mode, sizeof(mode)) && equalsIgnoreCase(mode, "blink");
}

}  // namespace

bool parseSign(const char *s, Sign &out) {
  if (!s) return false;
  for (const NameMap &m : kNames) {
    if (equalsIgnoreCase(s, m.name)) {
      out = m.sign;
      return true;
    }
  }
  return false;
}

const char *signName(Sign s) {
  for (const NameMap &m : kNames) {
    if (m.sign == s) return m.name;
  }
  return "?";
}

// ---------------- 匯流排 ----------------
// 硬體 I2C0／I2C1 用 HAL i2c_t，軟體 I2C 用 HAL gpio_t。見 EvacOled.h 開頭的說明與實測數字。
namespace {

constexpr uint32_t kAckWaitMs = 1;     // 送出後等 TX_COMPLETE 回呼的時間（SDK Wire 也是這樣判斷）
constexpr uint8_t kProbeTries = 3;     // 開機第一次探測偶爾誤判，最多試 3 次

PinName pinOf(uint8_t arduinoPin) { return (PinName)g_APinDescription[arduinoPin].pinname; }

volatile bool g_txDone[2] = {false, false};
void onTxDone0(void *) { g_txDone[0] = true; }
void onTxDone1(void *) { g_txDone[1] = true; }

struct HalBus {
  i2c_t obj;
  uint8_t sdaPin, sclPin, index;
  int hz;
  bool ready;

  void recover() {                     // 重設並重新設定：NACK 之後匯流排會卡住，這樣才能再用
    i2c_reset(&obj);
    i2c_init(&obj, pinOf(sdaPin), pinOf(sclPin));
    i2c_frequency(&obj, hz);
    i2c_set_user_callback(&obj, I2C_TX_COMPLETE, index ? onTxDone1 : onTxDone0);
  }
  void begin(int f) {
    hz = f;
    if (!ready) i2c_init(&obj, pinOf(sdaPin), pinOf(sclPin));
    ready = true;
    recover();
  }
  // 有檢查的寫入：重設 → 寫 → 等回呼 → 再重設（不管成功與否，匯流排都回到乾淨狀態）
  bool checkedWrite(uint8_t addr, const uint8_t *d, uint8_t n) {
    recover();
    g_txDone[index] = false;
    i2c_write(&obj, addr, (const char *)d, n, 1);
    delay(kAckWaitMs);
    bool ok = g_txDone[index];
    recover();
    return ok;
  }
  // 確認過有 ACK 之後的寫入。i2c_write 會在資料還沒送完時就返回，下一筆會蓋掉上一筆（畫面時好時壞），
  // 所以每筆都等 TX_COMPLETE 回呼，逾時 n×200 µs＋2 ms 就 recover() 並算失敗（wire1_test v11 實測 0 次逾時）
  bool write(uint8_t addr, const uint8_t *d, uint8_t n) {
    g_txDone[index] = false;
    i2c_write(&obj, addr, (const char *)d, n, 1);
    const uint32_t limit = (uint32_t)n * 200 + 2000, t0 = micros();
    while (!g_txDone[index] && micros() - t0 < limit) {
    }
    if (g_txDone[index]) return true;
    recover();
    return false;
  }
};

HalBus g_hal[2] = {{{}, I2C_SDA, I2C_SCL, 0, 100000, false}, {{}, I2C1_SDA, I2C1_SCL, 1, 100000, false}};   // 100 kHz：見 EvacOled.h

struct SoftBus {
  gpio_t sda, scl;
  uint8_t sdaPin = 0xFF, sclPin = 0xFF;

  void rel(gpio_t *g) { gpio_dir(g, PIN_INPUT); gpio_mode(g, PullUp); }
  void low(gpio_t *g) { gpio_write(g, 0); gpio_dir(g, PIN_OUTPUT); gpio_mode(g, PullNone); gpio_write(g, 0); }
  void out(gpio_t *g) { gpio_dir(g, PIN_OUTPUT); gpio_mode(g, PullNone); }
  void dly() { delayMicroseconds(2); }
  void begin(uint8_t a, uint8_t c) {
    if (a == sdaPin && c == sclPin) return;
    sdaPin = a; sclPin = c;
    gpio_init(&sda, pinOf(a));
    gpio_init(&scl, pinOf(c));
    rel(&sda); rel(&scl);
  }
  void start() { rel(&sda); rel(&scl); dly(); low(&sda); dly(); low(&scl); dly(); }
  void stop() { low(&sda); dly(); gpio_write(&scl, 1); rel(&scl); dly(); rel(&sda); dly(); }
  bool byteOut(uint8_t b) {            // SSD1306 只收、不拉長時脈：資料推挽輸出，第 9 拍才讀 ACK
    out(&sda);
    for (int i = 7; i >= 0; --i) {
      gpio_write(&sda, (b >> i) & 1);
      gpio_write(&scl, 1);
      gpio_write(&scl, 0);
    }
    rel(&sda);
    gpio_write(&scl, 1);
    dly();
    bool ack = gpio_read(&sda) == 0;
    gpio_write(&scl, 0);
    return ack;
  }
  bool write(uint8_t addr, const uint8_t *d, uint8_t n) {   // 每個 byte 都檢查 ACK，NACK 就收尾
    start();
    bool ok = byteOut(addr << 1);
    for (uint8_t i = 0; ok && i < n; ++i) ok = byteOut(d[i]);
    stop();
    return ok;
  }
};

SoftBus g_soft[3];              // 每條匯流排一個：Wire0 腳位、Wire1 腳位、Soft 腳位
bool g_useHal = false;          // useHardwareI2C(true)：Wire0／Wire1 改走 HAL i2c_t（hub_node 實測不通，預設不用）

bool viaHal(Bus b) { return g_useHal && b != Bus::Soft; }

// 一次有檢查的傳輸（硬體：重設＋回呼；軟體：逐 byte ACK）
bool busChecked(Bus b, uint8_t addr, const uint8_t *d, uint8_t n) {
  if (!viaHal(b)) return g_soft[(uint8_t)b].write(addr, d, n);
  return g_hal[(uint8_t)b].checkedWrite(addr, d, n);
}

// 確認過 ACK 之後的傳輸（硬體：每筆等送完，逾時算失敗；軟體：逐 byte 檢查 ACK）
bool busWrite(Bus b, uint8_t addr, const uint8_t *d, uint8_t n) {
  if (!viaHal(b)) return g_soft[(uint8_t)b].write(addr, d, n);
  return g_hal[(uint8_t)b].write(addr, d, n);
}

}  // namespace

uint8_t EvacOled::begin(const SlotConfig *slots, uint8_t count, const MuxConfig *mux,
                        uint32_t clockHz) {
  slots_ = slots;
  count_ = count > kMaxSlots ? kMaxSlots : count;
  hasMux_ = mux != nullptr;
  if (hasMux_) mux_ = *mux;
  muxSelected_ = -2;

  bool useBus[3] = {false, false, false};
  for (uint8_t i = 0; i < count_; ++i) useBus[(uint8_t)slots_[i].bus] = true;
  if (hasMux_) useBus[(uint8_t)mux_.bus] = true;
  g_useHal = useHal_;
  for (uint8_t b = 0; b < 3; ++b) {
    if (!useBus[b]) continue;
    if (viaHal((Bus)b)) g_hal[b].begin((int)clockHz);
    else g_soft[b].begin(pinSda_[b], pinScl_[b]);
  }

  uint8_t ok = 0;
  for (uint8_t i = 0; i < count_; ++i) {
    state_[i] = State();
    bool up = false;
    for (uint8_t t = 0; t < kProbeTries && !up; ++t) up = initPanel(i);
    if (up) ++ok;
  }
  blinkAt_ = millis();
  return ok;
}

bool EvacOled::select(const SlotConfig &c) {
  if (!hasMux_ || c.bus != mux_.bus) return true;
  // 不在多工器後面的螢幕：關掉所有通道，以免和通道上同位址的螢幕撞在一起
  int8_t want = c.muxChannel < 0 ? -1 : c.muxChannel;
  if (want == muxSelected_) return true;
  const uint8_t mask = want < 0 ? 0 : (uint8_t)(1u << want);
  if (!busChecked(mux_.bus, mux_.addr, &mask, 1)) {
    muxSelected_ = -2;
    // 多工器沒回應（沒接或壞掉）時通道必然都關著，直接接在匯流排上的螢幕照常可用
    return want < 0;
  }
  muxSelected_ = want;
  return true;
}

bool EvacOled::reach(const SlotConfig &c) {
  static const uint8_t kNop[2] = {0x00, 0xE3};   // 指令 NOP：探測用，不改變螢幕
  return select(c) && busChecked(c.bus, c.addr, kNop, sizeof(kNop));
}

bool EvacOled::command(const SlotConfig &c, const uint8_t *cmds, uint8_t n) {
  if (!reach(c)) return false;
  uint8_t buf[1 + 32];
  buf[0] = 0x00;
  if (n > 32) n = 32;
  memcpy(buf + 1, cmds, n);
  return busWrite(c.bus, c.addr, buf, n + 1);
}

bool EvacOled::sendData(const SlotConfig &c, const uint8_t *d, uint8_t n) {
  uint8_t buf[1 + kChunk];
  buf[0] = 0x40;
  if (d) memcpy(buf + 1, d, n); else memset(buf + 1, 0, n);
  return busWrite(c.bus, c.addr, buf, n + 1);
}

bool EvacOled::initPanel(uint8_t i) {
  const SlotConfig &c = slots_[i];
  const bool tall = c.panel == Panel::P128x64;
  const uint8_t init[] = {
      0xAE,                    // 關顯示
      0xD5, 0x80,              // 時脈
      0xA8, (uint8_t)(tall ? 0x3F : 0x1F),// 多工比 = 高度 - 1
      0xD3, 0x00,              // 顯示偏移
      0x40,                    // 起始列
      0x8D, 0x14,              // 內建升壓
      0x20, 0x00,              // 水平定址
      0xA1, 0xC8,              // 一般方向（旋轉由圖示選擇處理）
      0xDA, (uint8_t)(tall ? 0x12 : 0x02),// COM 腳位配置
      0x81, 0xCF,              // 對比（亮一點，遠處看得清楚）
      0xD9, 0xF1,
      0xDB, 0x40,
      0xA4, 0xA6,              // 依 RAM 顯示、不反白
  };
  State &s = state_[i];
  s.online = command(c, init, sizeof(init));
  s.drawnIcon = kIconUnknown;
  s.dirty = true;
  s.shownOn = false;
  if (!s.online) s.retryAt = millis() + kRetryMs;
  return s.online;
}

int8_t EvacOled::iconFor(const SlotConfig &c, Sign sign) const {
  switch (sign) {
    case Sign::Off: return kIconBlank;
    case Sign::Up: return kIconStairsUp;
    case Sign::Down: return kIconStairsDown;
    case Sign::Blocked: return kIconBlocked;
    default: break;
  }
  // 方位 k（0 = 北）換成螢幕方向（0 = 螢幕上方，順時針）。
  // 一般安裝：螢幕方向 = k - top。朝下裝在天花板時從下面看是鏡像：top - k。
  int k = (int)sign - (int)Sign::N;
  int t = (int)c.top;
  int s = c.ceiling ? (t - k) : (k - t);
  return (int8_t)(((s % 8) + 8) % 8);
}

bool EvacOled::draw(uint8_t i, int8_t icon) {
  const SlotConfig &c = slots_[i];
  State &st = state_[i];
  const uint8_t np = pages(c.panel);
  const uint8_t *next = icon >= 0 ? iconData(c.panel, icon) : nullptr;
  const uint8_t *prev = st.drawnIcon >= 0 ? iconData(c.panel, st.drawnIcon) : nullptr;
  bool reached = false;                // 探測一次就好：有 ACK 之後整張連續送

  for (uint8_t p = 0; p < np; ++p) {
    const uint8_t *np_ = next ? next + p * kWidth : nullptr;
    // 只送有變的頁
    if (st.drawnIcon != kIconUnknown) {
      const uint8_t *pp = prev ? prev + p * kWidth : nullptr;
      bool same;
      if (np_ && pp) {
        same = memcmp(np_, pp, kWidth) == 0;
      } else if (!np_ && !pp) {
        same = true;
      } else {
        const uint8_t *d = np_ ? np_ : pp;
        same = true;
        for (uint8_t x = 0; x < kWidth && same; ++x) same = d[x] == 0;
      }
      if (same) continue;
    }
    if (!reached) {
      if (!reach(c)) return false;
      reached = true;
    }
    const uint8_t window[] = {0x00, 0x21, 0, kWidth - 1, 0x22, p, p};
    if (!busWrite(c.bus, c.addr, window, sizeof(window))) return false;
    for (uint8_t x = 0; x < kWidth; x += kChunk)
      if (!sendData(c, np_ ? np_ + x : nullptr, kChunk)) return false;
  }
  st.drawnIcon = icon;
  return true;
}

bool EvacOled::drawBitmap(uint8_t i, const uint8_t *bitmap) {
  if (i >= count_ || !bitmap) return false;
  const SlotConfig &c = slots_[i];
  State &st = state_[i];
  if (!st.online && !initPanel(i)) return false;
  if (!reach(c)) {
    st.online = false;
    st.retryAt = millis() + kRetryMs;
    return false;
  }
  const uint8_t np = pages(c.panel);
  const uint8_t window[] = {0x00, 0x21, 0, kWidth - 1, 0x22, 0, (uint8_t)(np - 1)};
  if (!busWrite(c.bus, c.addr, window, sizeof(window))) return false;
  for (uint16_t k = 0; k < (uint16_t)np * kWidth; k += kChunk)
    if (!sendData(c, bitmap + k, kChunk)) return false;
  const uint8_t on[] = {0x00, 0xAF};
  busWrite(c.bus, c.addr, on, sizeof(on));
  st.drawnIcon = kIconUnknown;         // 下一次 update() 整張重畫回方向
  st.dirty = true;
  st.shownOn = true;
  return true;
}

bool EvacOled::setIndex(uint8_t i, Sign sign, bool blink) {
  if (i >= count_) return false;
  State &s = state_[i];
  if (s.sign != sign || s.blink != blink) {
    s.sign = sign;
    s.blink = blink;
    s.dirty = true;
  }
  return true;
}

int EvacOled::indexOf(const char *id) const {
  for (uint8_t i = 0; i < count_; ++i) {
    if (equalsIgnoreCase(slots_[i].id, id)) return i;
  }
  return -1;
}

bool EvacOled::set(const char *id, Sign sign, bool blink) {
  int i = indexOf(id);
  return i >= 0 && setIndex((uint8_t)i, sign, blink);
}

void EvacOled::setAll(Sign sign, bool blink) {
  for (uint8_t i = 0; i < count_; ++i) setIndex(i, sign, blink);
}

int EvacOled::applyJson(const char *json) {
  if (!json) return 0;
  int applied = 0;
  const char *p = json;
  while ((p = strchr(p, '{')) != nullptr) {
    // 只看最內層的物件（中間沒有其他 '{'）
    const char *end = p + 1;
    while (*end && *end != '}' && *end != '{') ++end;
    if (*end != '}') {
      p = end;
      if (!*p) break;
      continue;
    }
    char id[16], dir[12];
    Sign sign;
    if (findString(p, end, "id", id, sizeof(id)) && findString(p, end, "dir", dir, sizeof(dir)) &&
        parseSign(dir, sign) && set(id, sign, findBlink(p, end))) {
      ++applied;
    }
    p = end + 1;
  }
  return applied;
}

int EvacOled::applyLeds(const char *json) {
  if (!json) return 0;
  const char *end = json + strlen(json);
  const char *v = findValue(json, end, "leds");
  if (!v || *v != '[') return 0;
  bool blink = false;
  const char *b = findValue(json, end, "blink");
  if (b) blink = (*b >= '1' && *b <= '9') || strncmp(b, "true", 4) == 0;

  int applied = 0;
  uint8_t i = 0;
  for (const char *p = v + 1; *p && *p != ']'; ++p) {
    if (*p != '"') continue;
    const char *q = strchr(p + 1, '"');
    if (!q) break;
    char dir[12];
    size_t n = (size_t)(q - p - 1);
    Sign sign;
    if (n < sizeof(dir)) {
      memcpy(dir, p + 1, n);
      dir[n] = 0;
      if (parseSign(dir, sign) && setIndex(i, sign, blink)) ++applied;
    }
    ++i;
    p = q;
  }
  return applied;
}

void EvacOled::update() {
  const uint32_t now = millis();
  if (blinkPeriod_ > 0 && now - blinkAt_ >= blinkPeriod_ / 2) {
    blinkAt_ = now;
    blinkOn_ = !blinkOn_;
  }

  for (uint8_t i = 0; i < count_; ++i) {
    State &s = state_[i];
    if (!s.online) {
      if ((int32_t)(now - s.retryAt) < 0 || !initPanel(i)) continue;
    }
    const SlotConfig &c = slots_[i];
    if (s.dirty) {
      if (!draw(i, iconFor(c, s.sign))) {
        s.online = false;
        s.retryAt = now + kRetryMs;
        continue;
      }
      s.dirty = false;
    }
    // 閃爍只切換顯示開關（一個指令），不重送畫面
    bool wantOn = !s.blink || blinkOn_;
    if (wantOn != s.shownOn) {
      const uint8_t cmd = wantOn ? 0xAF : 0xAE;
      if (!command(c, &cmd, 1)) {
        s.online = false;
        s.retryAt = now + kRetryMs;
        continue;
      }
      s.shownOn = wantOn;
    }
  }
}

void EvacOled::scan(Print &out) {
  bool useBus[3] = {false, false, false};
  for (uint8_t i = 0; i < count_; ++i) useBus[(uint8_t)slots_[i].bus] = true;
  if (hasMux_) useBus[(uint8_t)mux_.bus] = true;
  static const char *const kNames3[3] = {"Wire0(Pin3/4) ", "Wire1(Pin0/1) ", "Soft(Pin18/19)"};

  // 每個位址送一個 NOP（至少 1 byte：SDK 送 0 byte 時任何位址都回成功）
  auto scanBus = [&](Bus b, const char *label) {
    static const uint8_t kNop[2] = {0x00, 0xE3};
    out.print(label);
    out.print(':');
    bool any = false;
    for (uint8_t a = 0x08; a < 0x78; ++a) {
      if (hasMux_ && b == mux_.bus && a == mux_.addr) continue;   // NOP 會改掉多工器的通道設定
      if (busChecked(b, a, kNop, sizeof(kNop))) {
        out.print(" 0x");
        if (a < 16) out.print('0');
        out.print(a, HEX);
        any = true;
      }
    }
    out.println(any ? "" : " (none)");
  };

  for (uint8_t b = 0; b < 3; ++b) {
    if (!useBus[b]) continue;
    const char *name = kNames3[b];
    if (hasMux_ && (Bus)b == mux_.bus) {
      SlotConfig direct{"", (Bus)b, 0, kNoMux, Panel::P128x64, Compass::N, false};
      select(direct);
      scanBus((Bus)b, name);
      for (int8_t ch = 0; ch < 8; ++ch) {
        SlotConfig via{"", (Bus)b, 0, ch, Panel::P128x64, Compass::N, false};
        if (!select(via)) {
          out.println("  mux select failed");
          break;
        }
        char label[24];
        snprintf(label, sizeof(label), "  %s mux ch%d", name, ch);
        scanBus((Bus)b, label);
      }
    } else {
      scanBus((Bus)b, name);
    }
  }
  // 掃描會打亂螢幕狀態的假設：全部重畫
  for (uint8_t i = 0; i < count_; ++i) state_[i].dirty = true;
}

}  // namespace evac
