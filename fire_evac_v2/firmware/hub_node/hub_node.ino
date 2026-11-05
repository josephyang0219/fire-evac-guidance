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

  Which junction OLEDs a board drives is the OLED_MAP table below (by slot), not the server:
  the OLED wiring is not final yet, so change the table, not the code. See README.md.

  Board package: Realtek AmebaPro2 (Arduino IDE). Model: our yolov7_tiny.nb swapped into the SDK (DEFAULT_YOLOV7TINY), Tools -> NN Model Load from: Flash.
*/
#include "WiFi.h"
#include "StreamIO.h"
#include "VideoStream.h"
#include "NNObjectDetection.h"
// No ObjectClassList.h: the board only sends class indices; the server maps them to names (evac.CLASSES).

// ---------- same for every board ----------
const char* SSID = "FireDemo";          // laptop hotspot
const char* PASS = "firedemo123";
const char* SERVER = "192.168.137.1";   // laptop address on the hotspot
const int   PORT = 8000;
const char* FW = "2.1";

// ---------- junction OLEDs: which displays this position drives (EDIT HERE) ----------
// One row per OLED. slot = console position (1N 1W 1S 1E 2N ...), junction = id the server sends,
// bus/addr = where the display sits (0 = Wire, 1 = Wire1; SSD1306 0x3C or 0x3D). A slot may own 0..MAX_OWN rows.
// PROVISIONAL: follows the 1f-9-oled layout (edge middle on 0x3C, corner on 0x3D, all on Wire) -- not decided yet.
// No OLED at the centre J(0,0) (decided 2026-11-05); the server still sends its direction for the console / slides.
struct OledSlot { const char* slot; const char* junction; uint8_t bus; uint8_t addr; };
const OledSlot OLED_MAP[] = {
  {"1N", "J(0,1)",   0, 0x3C}, {"1N", "J(-1,1)",  0, 0x3D},
  {"1E", "J(1,0)",   0, 0x3C}, {"1E", "J(1,1)",   0, 0x3D},
  {"1S", "J(0,-1)",  0, 0x3C}, {"1S", "J(1,-1)",  0, 0x3D},
  {"1W", "J(-1,0)",  0, 0x3C}, {"1W", "J(-1,-1)", 0, 0x3D},
};
const int N_MAP = sizeof(OLED_MAP) / sizeof(OledSlot);
const unsigned long LINK_TIMEOUT_MS = 3000;   // no reply this long -> displays show "--" (link lost), not a stale arrow

#define MAX_OWN 4
int own[MAX_OWN]; String shown[MAX_OWN]; int N_OWN = 0;   // OLED_MAP rows of this slot + what each one shows now
String mySlot = "?";                 // "?" = nothing received yet, so the first reply always runs defineSlot()
unsigned long lastReply = 0;

// Output hook: the OLED sketch replaces this with real drawing (bus/addr from the row). Called only on change.
// dir: N S E W UP DOWN X, "--" = no data from the server, "WAIT" = no position assigned, "BLINK" = 閃燈 on-phase.
void showDirection(const OledSlot& o, const String& dir) {
  Serial.print("[OLED "); Serial.print(o.bus); Serial.print(" 0x"); Serial.print(o.addr, HEX); Serial.print("] ");
  Serial.print(o.junction); Serial.print(" -> "); Serial.println(dir);
}

void setDisplay(int k, const String& dir) { if (shown[k] != dir) { shown[k] = dir; showDirection(OLED_MAP[own[k]], dir); } }

void defineSlot(const String& slot) {
  mySlot = slot; N_OWN = 0;
  for (int r = 0; r < N_MAP && N_OWN < MAX_OWN; r++)
    if (slot == OLED_MAP[r].slot) { own[N_OWN] = r; shown[N_OWN] = ""; N_OWN++; }
  Serial.print("slot "); Serial.print(slot.length() ? slot : String("(none)")); Serial.print(", OLEDs "); Serial.println(N_OWN);
}

// direction for one junction id in the reply: ..."id":"J(0,1)","dir":"N"...  ("" if missing)
String junctionDir(const String& resp, const char* id) {
  int p = resp.indexOf(String("\"id\":\"") + id + "\",\"dir\":\"");
  if (p < 0) return "";
  p += strlen(id) + 15; int q = resp.indexOf('"', p);
  return q < 0 ? "" : resp.substring(p, q);
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

  if (resp.length()) {
    lastReply = millis();
    String slot = jStr(resp, "slot");
    if (slot != mySlot) defineSlot(slot);
    if (jInt(resp, "blink")) for (int k = 0; k < N_OWN; k++) setDisplay(k, (millis() / 250) % 2 ? "BLINK" : "--");   // "閃燈"
    else if (!slot.length()) for (int k = 0; k < N_OWN; k++) setDisplay(k, "WAIT");
    else for (int k = 0; k < N_OWN; k++) {
      String d = junctionDir(resp, OLED_MAP[own[k]].junction);
      setDisplay(k, d.length() ? d : "--");
    }
    if (jInt(resp, "snap") && millis() - lastSnap > 700) {                         // snapshot only when the console asks
      uint32_t addr = 0, len = 0; Camera.getImage(0, &addr, &len);
      if (len) httpPost(String("/api/dev/") + macStr + "/frame", "image/jpeg", (const uint8_t*)addr, len);
      lastSnap = millis();
    }
  }
  if (millis() - lastReply > LINK_TIMEOUT_MS) for (int k = 0; k < N_OWN; k++) setDisplay(k, "--");
  delay(150);
}
