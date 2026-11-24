/*
  HUB 8735 Ultra camera node — ONE sketch for every board (draft, not yet tested on hardware)

  No per-board settings: each board identifies itself by its Wi-Fi MAC address.
  The laptop server keeps a table  MAC -> position (1N 1W 1S 1E 2N 2W 2S 2E)  that you edit in the console
  (開發者控制台 → 裝置配置). Swapping boards around = change the dropdown, no re-flashing.

  Every ~200 ms:  POST /api/dev/<MAC>/detections   {"seq","fps","fw","dets":[[cls,cx,cy,w,h,conf],...]}
  Server answers: {"leds":["E","S"],"junctions":[{"id":"J(-1,1)","dir":"S"},...9 items],"slot":"1N","node":"N","blink":0,"snap":0}
    slot/node  position assigned in the console ("" = not assigned yet -> displays show "waiting")
    junctions  1F: one direction per junction J(i,j) at (i*99, j*99) mm, dir = N/S/E/W/UP/DOWN/X
    leds       old per-board LED list, still sent for compatibility; this sketch no longer uses it
    blink      1 = flash the displays (console "閃燈" button, to find this board physically)
    snap       1 = also upload a JPEG snapshot (console preview / "遮鏡頭指認" wizard)

  Which junction OLEDs a board drives is the OLED_MAP table below (by slot), not the server. Layout (2026-11-18, wiring_8hub/):
  the 8 camera HUBs drive all 18 ceiling OLEDs (1F + 2F, 9 each), no display-only HUBs, no multiplexer:
    corner OLED  -> Bus::Wire0 0x3C (Pin3 SDA / Pin4 SCL)   enters the breadboard seat through the new side window
    cross-arm    -> Bus::Wire1 0x3C (Pin0 SDA / Pin1 SCL)   enters through the seat's inner window
    centre       -> the S board's Bus::Soft 0x3C (Pin18 SDA / Pin19 SCL)  -> S boards drive 3, the others 2
  All 18 OLEDs keep the factory address 0x3C (no resoldering, 2026-11-23). All three buses are SOFTWARE I2C in
  EvacOled (2026-11-24): with camera + NN + SD running, the HAL hardware I2C never completed a transfer on the board
  (cause unknown), while software I2C worked (wire1_test v12, 18-29 ms per screen). Nothing in this sketch may touch
  pins 0, 1, 3, 4, 18, 19 (no Wire.begin(), pinMode(), SPI ...).
  Displays are drawn by the EvacOled library (oled_fw/libraries/EvacOled, pass it with --library).

  Board package: Realtek AmebaPro2 (Arduino IDE). Model: our yolov7_tiny.nb swapped into the SDK (DEFAULT_YOLOV7TINY), Tools -> NN Model Load from: Flash.

  OTA (wireless update): build with  python fire_evac_v2/tools/build_hub_node.py --ota  (FQBN ...:08_OTAMode=Enable,
  06_LoadNNModelSource=sd). That compiles a generated copy that defines Arduino_OTA_MODE (the SDK does NOT pass it to the
  compiler, despite boards.txt) and reads the model from the SD card. Without it this sketch behaves as before. With it:
    - the SDK's OTA threads report to fire_evac_v2/tools/ota_server.py (OTA_SERVER_IP:OTA_SERVER_PORT) and listen on TCP 5000
    - the model is read from the SD card: sd:/NN_MDL/yolov7_tiny.nb (the SDK refuses a flash model when OTA is on)
    - while an update runs the displays show "更新中" (no direction) and no detections are posted
    - every 30 s the board tells the OTA server its MAC / FW / slot (POST /api/nodeinfo), so the server can name boards
  Identity stays a runtime thing (MAC -> slot on the main server), so all 8 boards take the same ota.bin. See README.md.
  Wi-Fi / server addresses can be overridden in secrets.h (not in git, copy secrets.example.h).
*/
#include "WiFi.h"
#include "StreamIO.h"
#include "VideoStream.h"
#include "NNObjectDetection.h"
#include <EvacOled.h>
#if defined(Arduino_OTA_MODE) && !defined(Arduino_LOAD_MODEL_SD)
#error "OTA build needs the SD card model: FQBN ...:08_OTAMode=Enable,06_LoadNNModelSource=sd (use tools/build_hub_node.py --ota)"
#endif
#if __has_include("secrets.h")
#include "secrets.h"                    // local Wi-Fi / server settings, not in git (copy secrets.example.h)
#endif
// No ObjectClassList.h: the board only sends class indices; the server maps them to names (evac.CLASSES).

// ---------- same for every board ----------
#ifndef WIFI_SSID
#define WIFI_SSID "FireDemo"            // laptop hotspot
#endif
#ifndef WIFI_PASS
#define WIFI_PASS "firedemo123"
#endif
#ifndef EVAC_SERVER_IP
#define EVAC_SERVER_IP "192.168.137.1"  // laptop address on the hotspot
#endif
#ifndef EVAC_SERVER_PORT
#define EVAC_SERVER_PORT 8000
#endif
#ifndef OTA_SERVER_IP
#define OTA_SERVER_IP EVAC_SERVER_IP    // tools/ota_server.py, normally on the same laptop
#endif
#ifndef OTA_SERVER_PORT
#define OTA_SERVER_PORT 3000
#endif
const char* SSID = WIFI_SSID;
const char* PASS = WIFI_PASS;
const char* SERVER = EVAC_SERVER_IP;
const int   PORT = EVAC_SERVER_PORT;
const char* FW = "2.4";                 // bump for every OTA release: the OTA server checks it after the reboot

// ---------- junction OLEDs: which displays this position drives (EDIT HERE) ----------
// One row per OLED: slot = console position (1N 1E 1S 1W 2N ...) + an EvacOled SlotConfig whose id is the junction id the
// server sends (1F "J(i,j)", 2F "J2(i,j)"). top = where the screen's top edge (= the pin header side) points, from
// wiring_8hub/wiring_8hub.json; ceiling = true (mounted face down, seen from below). Verify top once mounted.
// software I2C pins per bus (Arduino pin numbers); the wiring is unchanged from the Wire/Wire1 days
#define CORNER_SDA_PIN 3                // PE_4
#define CORNER_SCL_PIN 4                // PE_3
#define ARM_SDA_PIN 0                   // PF_2
#define ARM_SCL_PIN 1                   // PF_1
#define SOFT_SDA_PIN 18                 // PF_5, centre OLED on the S boards
#define SOFT_SCL_PIN 19                 // PF_6
#ifndef EVAC_CORNER_ADDR
#define EVAC_CORNER_ADDR 0x3C
#endif
using namespace evac;
#define OLED(id, bus, addr, top) {id, bus, addr, kNoMux, Panel::P128x64, Compass::top, true}
struct SlotOled { const char* slot; SlotConfig cfg; };
const SlotOled OLED_MAP[] = {
  // 1F                    junction     bus         address            screen top
  {"1N", OLED("J(-1,1)",  Bus::Wire0, EVAC_CORNER_ADDR, E)},    // NW corner
  {"1N", OLED("J(0,1)",   Bus::Wire1, 0x3C,             S)},    // N cross-arm middle
  {"1E", OLED("J(1,1)",   Bus::Wire0, EVAC_CORNER_ADDR, S)},    // NE corner
  {"1E", OLED("J(1,0)",   Bus::Wire1, 0x3C,             W)},    // E cross-arm middle
  {"1S", OLED("J(1,-1)",  Bus::Wire0, EVAC_CORNER_ADDR, S)},    // SE corner
  {"1S", OLED("J(0,-1)",  Bus::Wire1, 0x3C,             N)},    // S cross-arm middle
  {"1S", OLED("J(0,0)",   Bus::Soft,  0x3C,             S)},    // centre: software I2C Pin18/19
  {"1W", OLED("J(-1,-1)", Bus::Wire0, EVAC_CORNER_ADDR, N)},    // SW corner
  {"1W", OLED("J(-1,0)",  Bus::Wire1, 0x3C,             E)},    // W cross-arm middle
  // 2F: same layout (corners 0.5-1.75 mm further out, see wiring_8hub/README.md)
  {"2N", OLED("J2(-1,1)",  Bus::Wire0, EVAC_CORNER_ADDR, E)},
  {"2N", OLED("J2(0,1)",   Bus::Wire1, 0x3C,             S)},
  {"2E", OLED("J2(1,1)",   Bus::Wire0, EVAC_CORNER_ADDR, S)},
  {"2E", OLED("J2(1,0)",   Bus::Wire1, 0x3C,             W)},
  {"2S", OLED("J2(1,-1)",  Bus::Wire0, EVAC_CORNER_ADDR, S)},
  {"2S", OLED("J2(0,-1)",  Bus::Wire1, 0x3C,             N)},
  {"2S", OLED("J2(0,0)",   Bus::Soft,  0x3C,             S)},
  {"2W", OLED("J2(-1,-1)", Bus::Wire0, EVAC_CORNER_ADDR, N)},
  {"2W", OLED("J2(-1,0)",  Bus::Wire1, 0x3C,             E)},
};
const int N_MAP = sizeof(OLED_MAP) / sizeof(SlotOled);
const unsigned long LINK_TIMEOUT_MS = 3000;   // no reply this long -> displays go dark (no stale arrow)

#define MAX_OWN 4
SlotConfig own[MAX_OWN]; int N_OWN = 0;       // this slot's displays (EvacOled keeps a pointer to this array)
EvacOled oled;
String mySlot = "?";                 // "?" = nothing received yet, so the first reply always runs defineSlot()
unsigned long lastReply = 0;
bool linkLost = false;
#ifdef Arduino_OTA_MODE
unsigned long otaInfoAt = 0;          // next node-info report to the OTA server (0 = now)
#endif

void defineSlot(const String& slot) {
  oled.setAll(Sign::Off); oled.update();      // blank the old position's displays before re-pointing the library
  mySlot = slot; N_OWN = 0;
  for (int r = 0; r < N_MAP && N_OWN < MAX_OWN; r++)
    if (slot == OLED_MAP[r].slot) own[N_OWN++] = OLED_MAP[r].cfg;
  uint8_t ok = oled.begin(own, N_OWN);
#ifdef Arduino_OTA_MODE
  otaInfoAt = 0;                              // tell the OTA server about the new slot right away
#endif
  Serial.print("slot "); Serial.print(slot.length() ? slot : String("(none)"));
  Serial.print(", OLEDs "); Serial.print(ok); Serial.print("/"); Serial.println(N_OWN);
}

// log every display change on the serial port: [OLED J(1,1)] -> W
void logChanges(const Sign* before) {
  for (int k = 0; k < N_OWN; k++)
    if (oled.sign(k) != before[k]) { Serial.print("[OLED "); Serial.print(own[k].id); Serial.print("] -> "); Serial.println(signName(oled.sign(k))); }
}

// ---------- camera: channel 0 = small JPEG for snapshots, channel 3 = RGB for the NPU ----------
// RGB output only works on channel 3: with channel 1 the SDK prints "RGB output only on ch4" / "str3 paring fail"
// and neither camera nor NN start (found on the board 2026-11-24; hub_model_test uses CH_NN 3 too).
#define CH_JPG 0
#define CH_NN 3
#define NNW 576             // must match the input size used when converting yolov7_tiny.nb (16:9 camera -> no squash)
#define NNH 320
VideoSetting configJPG(VIDEO_VGA, 10, VIDEO_JPEG, 1);
VideoSetting configNN(NNW, NNH, 10, VIDEO_RGB, 0);
NNObjectDetection ObjDet;
StreamIO videoStreamerNN(1, 1);
WiFiClient client;
unsigned long seq = 0, lastSnap = 0;
char macStr[13];

// tiny helpers for the fixed-shape JSON reply
String jStr(const String& s, const char* key) {
  int p = s.indexOf(String("\"") + key + "\":\""); if (p < 0) return "";
  p += strlen(key) + 4; int q = s.indexOf('"', p); return q < 0 ? "" : s.substring(p, q);
}
int jInt(const String& s, const char* key) {
  int p = s.indexOf(String("\"") + key + "\":"); if (p < 0) return 0;
  return s.substring(p + strlen(key) + 3).toInt();
}

String httpPost(const char* host, int port, const String& path, const char* type, const uint8_t* data, uint32_t len) {
  String resp;
  if (!client.connect(host, port)) return resp;
  client.print(String("POST ") + path + " HTTP/1.1\r\nHost: " + host + "\r\nContent-Type: " + type +
               "\r\nContent-Length: " + len + "\r\nConnection: close\r\n\r\n");
  client.write(data, len);
  unsigned long t0 = millis();
  while (client.connected() && millis() - t0 < 500) { while (client.available()) resp += (char)client.read(); }
  client.stop();
  int b = resp.indexOf("\r\n\r\n");
  return b < 0 ? resp : resp.substring(b + 4);
}
String httpPost(const String& path, const char* type, const uint8_t* data, uint32_t len) {
  return httpPost(SERVER, PORT, path, type, data, len);
}

#ifdef Arduino_OTA_MODE
// ---------- OTA: SDK threads + what this sketch does around them ----------
#include "OTA.h"
extern "C" {
#include "ota_drv.h"                // g_otaState / OtaState[]: the SDK's OTA state (IDLE, ..., DOWNLOAD_IN_PROGRESS, ...)
}
#include "ota_banner.h"
OTA ota;
char otaServer[] = OTA_SERVER_IP;
const unsigned long OTA_INFO_MS = 30000;          // node info to the OTA server every 30 s ...
const unsigned long OTA_INFO_BACKOFF_MS = 300000; // ... or every 5 min while it is not reachable
const unsigned long OTA_FAIL_MS = 15000;          // COMPLETED for this long without a reboot = the update failed
unsigned long otaCompletedAt = 0;
bool otaBusy = false, otaFailed = false;

// "更新中" on every display of this slot (through EvacOled, so on the software buses), no direction shown
void showOtaBanner() {
  oled.setAll(Sign::Off);                        // library state = dark; oled.begin() redraws if the update fails
  for (int k = 0; k < N_OWN; k++)
    oled.drawBitmap(k, own[k].panel == Panel::P128x64 ? OTA_BANNER_64 : OTA_BANNER_32);
}

// true while an update runs: loop() then skips detections and directions
bool otaInLoop() {
  const char* st = g_otaState;
  if (st == OtaState[0] || otaFailed) return false;
  if (!otaBusy) { otaBusy = true; Serial.print("[OTA] "); Serial.println(st); showOtaBanner(); }
  if (st == OtaState[3]) {                       // a good update goes on to REBOOT and resets; staying here = failed
    if (!otaCompletedAt) otaCompletedAt = millis();
    else if (millis() - otaCompletedAt > OTA_FAIL_MS) {
      otaFailed = true;
      Serial.println("[OTA] update failed, back to normal (press RST before the next try)");
      oled.begin(own, N_OWN);                    // forget the banner, the next reply redraws the directions
      return false;
    }
  }
  return true;
}

// MAC / FW / slot to the OTA server, so it can name boards (its own reports only carry the state)
void sendNodeInfo() {
  if ((long)(millis() - otaInfoAt) < 0) return;
  String b = String("{\"mac\":\"") + macStr + "\",\"fw\":\"" + FW + "\",\"slot\":\"" + mySlot + "\",\"ota\":\"" +
             (otaFailed ? "FAILED" : g_otaState) + "\"}";
  bool ok = httpPost(otaServer, OTA_SERVER_PORT, "/api/nodeinfo", "application/json", (const uint8_t*)b.c_str(), b.length()).length() > 0;
  otaInfoAt = millis() + (ok ? OTA_INFO_MS : OTA_INFO_BACKOFF_MS);
}
#endif

void setup() {
  Serial.begin(115200);
  oled.setBusPins(Bus::Wire0, CORNER_SDA_PIN, CORNER_SCL_PIN);   // all software I2C (default; HAL is off)
  oled.setBusPins(Bus::Wire1, ARM_SDA_PIN, ARM_SCL_PIN);
  oled.setBusPins(Bus::Soft, SOFT_SDA_PIN, SOFT_SCL_PIN);
  while (WiFi.begin((char*)SSID, (char*)PASS) != WL_CONNECTED) delay(1000);
  byte mac[6]; WiFi.macAddress(mac);
  sprintf(macStr, "%02X%02X%02X%02X%02X%02X", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  Serial.print("MAC "); Serial.println(macStr);      // also shown in the console
#ifdef Arduino_OTA_MODE
  ota.start_OTA_threads(OTA_SERVER_PORT, otaServer); // reports every ~4 s, listens on TCP 5000 for start_ota
#endif
  Camera.configVideoChannel(CH_JPG, configJPG);
  Camera.configVideoChannel(CH_NN, configNN);
  Camera.videoInit();
  ObjDet.configVideo(configNN);
  // DEFAULT_YOLOV7TINY on purpose: the SDK copy variants/common_nn_models/yolov7_tiny.nb is our 6-class model.
  // Keep this the ONLY model line: the SDK's ino_validation scans the text (#if branches and comments too) and wants
  // the default model for a flash build but no default model at all for an SD (= OTA) build. The OTA build therefore
  // goes through tools/build_hub_node.py, which writes a copy of this sketch with this one line switched to the
  // customized (SD card) model, sd:/NN_MDL/yolov7_tiny.nb.
  ObjDet.modelSelect(OBJECT_DETECTION, DEFAULT_YOLOV7TINY, NA_MODEL, NA_MODEL);
  ObjDet.begin();
  videoStreamerNN.registerInput(Camera.getStream(CH_NN));
  videoStreamerNN.setStackSize();
  videoStreamerNN.registerOutput(ObjDet);
  videoStreamerNN.begin();
  Camera.channelBegin(CH_JPG);
  Camera.channelBegin(CH_NN);
}

void loop() {
#ifdef Arduino_OTA_MODE
  if (otaInLoop()) { delay(100); return; }    // updating: banner stays, no detections, Wi-Fi left to the download
  sendNodeInfo();
#endif
  std::vector<ObjectDetectionResult> res = ObjDet.getResult();
  String body = String("{\"seq\":") + (++seq) + ",\"fps\":5,\"fw\":\"" + FW + "\",\"dets\":[";
  for (size_t i = 0; i < res.size(); i++) {
    ObjectDetectionResult r = res[i];
    float cx = (r.xMin() + r.xMax()) / 2, cy = (r.yMin() + r.yMax()) / 2, w = r.xMax() - r.xMin(), h = r.yMax() - r.yMin();
    body += String(i ? "," : "") + "[" + r.type() + "," + String(cx, 4) + "," + String(cy, 4) + "," + String(w, 4) + "," + String(h, 4) + "," + String(r.score() / 100.0, 3) + "]";
  }
  body += "]}";
  String resp = httpPost(String("/api/dev/") + macStr + "/detections", "application/json", (const uint8_t*)body.c_str(), body.length());

  Sign before[MAX_OWN];
  for (int k = 0; k < N_OWN; k++) before[k] = oled.sign(k);
  if (resp.indexOf("\"slot\":") >= 0) {
    String slot = jStr(resp, "slot");
    if (slot != mySlot) defineSlot(slot);
    if (!slot.length()) oled.setAll(Sign::Off);                                   // not assigned yet: dark
    int n = slot.length() ? oled.applyJson(resp.c_str()) : 0;                    // picks out our junction id(s)
    if (!slot.length() || n >= N_OWN) { lastReply = millis(); linkLost = false; } // a cut-off reply doesn't count
    bool blink = jInt(resp, "blink");                                            // "閃燈": current sign blinks
    for (int k = 0; k < N_OWN; k++) oled.setIndex(k, blink && oled.sign(k) == Sign::Off ? Sign::Blocked : oled.sign(k), blink);
    if (jInt(resp, "snap") && millis() - lastSnap > 700) {                         // snapshot only when the console asks
      uint32_t addr = 0, len = 0; Camera.getImage(CH_JPG, &addr, &len);
      if (len) httpPost(String("/api/dev/") + macStr + "/frame", "image/jpeg", (const uint8_t*)addr, len);
      lastSnap = millis();
    }
  }
  if (millis() - lastReply > LINK_TIMEOUT_MS && !linkLost) { linkLost = true; oled.setAll(Sign::Off); Serial.println("link lost"); }
  logChanges(before);
  oled.update();
  delay(150);
}
