#include "EvacOled.h"

#include <stdio.h>
#include <string.h>

#include "EvacIconData.h"

namespace evac {

namespace {

constexpr uint8_t kWidth = 128;
constexpr uint8_t kChunk = 64;        // 每次 I2C 傳輸的資料量（SDK 緩衝 128）
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

TwoWire &EvacOled::wire(Bus b) { return b == Bus::Wire1 ? Wire1 : Wire; }

uint8_t EvacOled::begin(const SlotConfig *slots, uint8_t count, const MuxConfig *mux,
                        uint32_t clockHz) {
  slots_ = slots;
  count_ = count > kMaxSlots ? kMaxSlots : count;
  hasMux_ = mux != nullptr;
  if (hasMux_) mux_ = *mux;
  muxSelected_ = -2;

  bool useBus[2] = {false, false};
  for (uint8_t i = 0; i < count_; ++i) useBus[(uint8_t)slots_[i].bus] = true;
  if (hasMux_) useBus[(uint8_t)mux_.bus] = true;
  for (uint8_t b = 0; b < 2; ++b) {
    if (!useBus[b]) continue;
    TwoWire &w = wire((Bus)b);
    w.begin();
    w.setClock(clockHz);
  }

  uint8_t ok = 0;
  for (uint8_t i = 0; i < count_; ++i) {
    state_[i] = State();
    if (initPanel(i)) ++ok;
  }
  blinkAt_ = millis();
  return ok;
}

bool EvacOled::select(const SlotConfig &c) {
  if (!hasMux_ || c.bus != mux_.bus) return true;
  // 不在多工器後面的螢幕：關掉所有通道，以免和通道上同位址的螢幕撞在一起
  int8_t want = c.muxChannel < 0 ? -1 : c.muxChannel;
  if (want == muxSelected_) return true;
  TwoWire &w = wire(mux_.bus);
  w.beginTransmission(mux_.addr);
  w.write(want < 0 ? 0 : (uint8_t)(1u << want));
  if (w.endTransmission() != 0) {
    muxSelected_ = -2;
    return false;
  }
  muxSelected_ = want;
  return true;
}

bool EvacOled::command(const SlotConfig &c, const uint8_t *cmds, uint8_t n) {
  if (!select(c)) return false;
  TwoWire &w = wire(c.bus);
  w.beginTransmission(c.addr);
  w.write((uint8_t)0x00);
  w.write(cmds, n);
  return w.endTransmission() == 0;
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
  static const uint8_t kZero[kChunk] = {0};

  for (uint8_t p = 0; p < np; ++p) {
    const uint8_t *np_ = next ? next + p * kWidth : nullptr;
    // 只送有變的頁：SDK 的 endTransmission 每個位元組固定等 200 µs，整塊 128x64 約 0.2 秒
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
    const uint8_t window[] = {0x21, 0, kWidth - 1, 0x22, p, p};
    if (!command(c, window, sizeof(window))) return false;
    TwoWire &w = wire(c.bus);
    for (uint8_t x = 0; x < kWidth; x += kChunk) {
      w.beginTransmission(c.addr);
      w.write((uint8_t)0x40);
      w.write(np_ ? np_ + x : kZero, kChunk);
      if (w.endTransmission() != 0) return false;
    }
  }
  st.drawnIcon = icon;
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
  bool useBus[2] = {false, false};
  for (uint8_t i = 0; i < count_; ++i) useBus[(uint8_t)slots_[i].bus] = true;
  if (hasMux_) useBus[(uint8_t)mux_.bus] = true;

  auto scanBus = [&](Bus b, const char *label) {
    TwoWire &w = wire(b);
    out.print(label);
    out.print(':');
    bool any = false;
    for (uint8_t a = 0x08; a < 0x78; ++a) {
      w.beginTransmission(a);
      if (w.endTransmission() == 0) {
        out.print(" 0x");
        if (a < 16) out.print('0');
        out.print(a, HEX);
        any = true;
      }
    }
    out.println(any ? "" : " (none)");
  };

  for (uint8_t b = 0; b < 2; ++b) {
    if (!useBus[b]) continue;
    const char *name = b == 0 ? "Wire " : "Wire1";
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
