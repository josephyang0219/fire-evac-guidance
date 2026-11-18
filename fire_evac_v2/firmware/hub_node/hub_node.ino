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
    corner OLED  -> Wire  0x3C (Pin3 SDA / Pin4 SCL)   enters the breadboard seat through the new side window
    cross-arm    -> Wire1 0x3C (Pin0 SDA / Pin1 SCL)   enters through the seat's inner window
    centre       -> the S board's Wire1 0x3D (resoldered) -> S boards drive 3, the others 2
  Displays are drawn by the EvacOled library (oled_fw/libraries/EvacOled, pass it with --library).

  Board package: Realtek AmebaPro2 (Arduino IDE). Model: our yolov7_tiny.nb swapped into the SDK (DEFAULT_YOLOV7TINY), Tools -> NN Model Load from: Flash.
*/
#include "WiFi.h"
#include "StreamIO.h"
#include "VideoStream.h"
#include "NNObjectDetection.h"
#include <EvacOled.h>
// No ObjectClassList.h: the board only sends class indices; the server maps them to names (evac.CLASSES).

// ---------- same for every board ----------
const char* SSID = "FireDemo";          // laptop hotspot
const char* PASS = "firedemo123";
const char* SERVER = "192.168.137.1";   // laptop address on the hotspot
const int   PORT = 8000;
const char* FW = "2.3";

// ---------- junction OLEDs: which displays this position drives (EDIT HERE) ----------
// One row per OLED: slot = console position (1N 1E 1S 1W 2N ...) + an EvacOled SlotConfig whose id is the junction id the
// server sends (1F "J(i,j)", 2F "J2(i,j)"). top = where the screen's top edge (= the pin header side) points, from
// wiring_8hub/wiring_8hub.json; ceiling = true (mounted face down, seen from below). Verify top once mounted.
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
  {"1S", OLED("J(0,0)",   Bus::Wire1, 0x3D,             S)},    // centre (resoldered to 0x3D)
  {"1W", OLED("J(-1,-1)", Bus::Wire0, EVAC_CORNER_ADDR, N)},    // SW corner
  {"1W", OLED("J(-1,0)",  Bus::Wire1, 0x3C,             E)},    // W cross-arm middle
  // 2F: same layout (corners 0.5-1.75 mm further out, see wiring_8hub/README.md)
  {"2N", OLED("J2(-1,1)",  Bus::Wire0, EVAC_CORNER_ADDR, E)},
  {"2N", OLED("J2(0,1)",   Bus::Wire1, 0x3C,             S)},
  {"2E", OLED("J2(1,1)",   Bus::Wire0, EVAC_CORNER_ADDR, S)},
  {"2E", OLED("J2(1,0)",   Bus::Wire1, 0x3C,             W)},
  {"2S", OLED("J2(1,-1)",  Bus::Wire0, EVAC_CORNER_ADDR, S)},
  {"2S", OLED("J2(0,-1)",  Bus::Wire1, 0x3C,             N)},
  {"2S", OLED("J2(0,0)",   Bus::Wire1, 0x3D,             S)},
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

void defineSlot(const String& slot) {
  oled.setAll(Sign::Off); oled.update();      // blank the old position's displays before re-pointing the library
  mySlot = slot; N_OWN = 0;
  for (int r = 0; r < N_MAP && N_OWN < MAX_OWN; r++)
    if (slot == OLED_MAP[r].slot) own[N_OWN++] = OLED_MAP[r].cfg;
  uint8_t ok = oled.begin(own, N_OWN);
  Serial.print("slot "); Serial.print(slot.length() ? slot : String("(none)"));
  Serial.print(", OLEDs "); Serial.print(ok); Serial.print("/"); Serial.println(N_OWN);
}

// log every display change on the serial port: [OLED J(1,1)] -> W
void logChanges(const Sign* before) {
  for (int k = 0; k < N_OWN; k++)
    if (oled.sign(k) != before[k]) { Serial.print("[OLED "); Serial.print(own[k].id); Serial.print("] -> "); Serial.println(signName(oled.sign(k))); }
}

// ---------- camera: channel 0 = small JPEG for snapshots, channel 1 = RGB for the NPU ----------
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

String httpPost(const String& path, const char* type, const uint8_t* data, uint32_t len) {
  String resp;
  if (!client.connect(SERVER, PORT)) return resp;
  client.print(String("POST ") + path + " HTTP/1.1\r\nHost: " + SERVER + "\r\nContent-Type: " + type +
               "\r\nContent-Length: " + len + "\r\nConnection: close\r\n\r\n");
  client.write(data, len);
  unsigned long t0 = millis();
  while (client.connected() && millis() - t0 < 500) { while (client.available()) resp += (char)client.read(); }
  client.stop();
  int b = resp.indexOf("\r\n\r\n");
  return b < 0 ? resp : resp.substring(b + 4);
}

void setup() {
  Serial.begin(115200);
  while (WiFi.begin((char*)SSID, (char*)PASS) != WL_CONNECTED) delay(1000);
  byte mac[6]; WiFi.macAddress(mac);
  sprintf(macStr, "%02X%02X%02X%02X%02X%02X", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  Serial.print("MAC "); Serial.println(macStr);      // also shown in the console
  Camera.configVideoChannel(0, configJPG);
  Camera.configVideoChannel(1, configNN);
  Camera.videoInit();
  ObjDet.configVideo(configNN);
  // DEFAULT_YOLOV7TINY on purpose: the SDK copy variants/common_nn_models/yolov7_tiny.nb is our 6-class model
  ObjDet.modelSelect(OBJECT_DETECTION, DEFAULT_YOLOV7TINY, NA_MODEL, NA_MODEL);
  ObjDet.begin();
  videoStreamerNN.registerInput(Camera.getStream(1));
  videoStreamerNN.setStackSize();
  videoStreamerNN.registerOutput(ObjDet);
  videoStreamerNN.begin();
  Camera.channelBegin(0);
  Camera.channelBegin(1);
}

void loop() {
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
      uint32_t addr = 0, len = 0; Camera.getImage(0, &addr, &len);
      if (len) httpPost(String("/api/dev/") + macStr + "/frame", "image/jpeg", (const uint8_t*)addr, len);
      lastSnap = millis();
    }
  }
  if (millis() - lastReply > LINK_TIMEOUT_MS && !linkLost) { linkLost = true; oled.setAll(Sign::Off); Serial.println("link lost"); }
  logChanges(before);
  oled.update();
  delay(150);
}
