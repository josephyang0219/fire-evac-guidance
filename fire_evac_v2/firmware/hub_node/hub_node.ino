/*
  HUB 8735 Ultra camera node — ONE sketch for every board (draft, not yet tested on hardware)

  No per-board settings: each board identifies itself by its Wi-Fi MAC address.
  The laptop server keeps a table  MAC -> position (1N 1W 1S 1E 2N 2W 2S 2E)  that you edit in the console
  (開發者控制台 → 裝置配置). Swapping boards around = change the dropdown, no re-flashing.

  Every ~200 ms:  POST /api/dev/<MAC>/detections   {"seq","fps","fw","dets":[[cls,cx,cy,w,h,conf],...]}
  Server answers: {"slot":"1N","node":"N","leds":["E","S"],"blink":0,"snap":0}
    slot/node  position assigned in the console ("" = not assigned yet -> LEDs breathe slowly, waiting)
    leds       one direction per junction this position drives (N/S/E/W/DOWN/UP/X)
    blink      1 = flash all LEDs (console "閃燈" button, to find this board physically)
    snap       1 = also upload a JPEG snapshot (console preview / "遮鏡頭指認" wizard)

  Board package: Realtek AmebaPro2 (Arduino IDE). Model: yolov7_tiny.nb in this sketch folder, Tools -> NN Model Load from: Flash.
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
const char* FW = "2.0";

// ---------- direction LEDs (one single-colour LED per walkable direction) ----------
//   N: 北口 [E,W,S], 西北角 [E,S,樓梯]    W: 西口 [N,S,E], 西南角 [N,E]
//   S: 南口 [E,W,N], 東南角 [N,W,樓梯]    E: 東口 [N,S,W], 東北角 [S,W], 中央 [N,S,E,W]
// Pins: junction A -> 11,12,13 ; junction B -> 24,23 (+18 stair LED) ; centre (E only) -> 22,21,20,19
// Wire all 10 pins on every board the same way; unused ones simply stay off for that position.
const int ALL_PINS[] = {11, 12, 13, 24, 23, 18, 22, 21, 20, 19};
const int N_PINS = sizeof(ALL_PINS) / sizeof(int);
struct Junction { const char* dirs; int pins[4]; };
Junction J[3]; int N_J = 0; char node = 0;

void defineJunctions(char c) {
  node = c; N_J = 2;
  if (c == 'N') { J[0] = {"EWS", {11, 12, 13}}; J[1] = {"EST", {24, 23, 18}}; }
  else if (c == 'W') { J[0] = {"NSE", {11, 12, 13}}; J[1] = {"NE", {24, 23}}; }
  else if (c == 'S') { J[0] = {"EWN", {11, 12, 13}}; J[1] = {"NWT", {24, 23, 18}}; }
  else if (c == 'E') { J[0] = {"NSW", {11, 12, 13}}; J[1] = {"SW", {24, 23}}; J[2] = {"NSEW", {22, 21, 20, 19}}; N_J = 3; }
  else N_J = 0;
}
void allLeds(bool on) { for (int i = 0; i < N_PINS; i++) digitalWrite(ALL_PINS[i], on ? HIGH : LOW); }
void setJunction(int k, const String& d) {
  bool stair = (d == "DOWN" || d == "UP");
  for (int n = 0; J[k].dirs[n]; n++) {
    bool on = J[k].dirs[n] == 'T' ? stair : (d.length() == 1 && d[0] == J[k].dirs[n]);
    digitalWrite(J[k].pins[n], on ? HIGH : LOW);
  }
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
  for (int i = 0; i < N_PINS; i++) { pinMode(ALL_PINS[i], OUTPUT); digitalWrite(ALL_PINS[i], LOW); }
  while (WiFi.begin((char*)SSID, (char*)PASS) != WL_CONNECTED) delay(1000);
  byte mac[6]; WiFi.macAddress(mac);
  sprintf(macStr, "%02X%02X%02X%02X%02X%02X", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  Serial.print("MAC "); Serial.println(macStr);      // also shown in the console
  Camera.configVideoChannel(0, configJPG);
  Camera.configVideoChannel(1, configNN);
  Camera.videoInit();
  ObjDet.configVideo(configNN);
  ObjDet.modelSelect(OBJECT_DETECTION, CUSTOMIZED_YOLOV7TINY, NA_MODEL, NA_MODEL);
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
    String n = jStr(resp, "node");
    if ((n.length() ? n[0] : 0) != node) { allLeds(false); defineJunctions(n.length() ? n[0] : 0); }
    if (jInt(resp, "blink")) allLeds((millis() / 250) % 2);                       // "閃燈": find this board
    else if (!N_J) { allLeds(false); digitalWrite(11, (millis() / 1000) % 2); }   // waiting for a position: pin 11 blinks slowly
    else {
      int p = resp.indexOf("\"leds\":[");
      for (int k = 0; k < N_J && p >= 0; k++) {
        int a = resp.indexOf('"', p + 8 + (k ? 1 : 0)); int b = resp.indexOf('"', a + 1);
        if (a < 0 || b < 0) break;
        setJunction(k, resp.substring(a + 1, b)); p = b;
      }
    }
    if (jInt(resp, "snap") && millis() - lastSnap > 700) {                         // snapshot only when the console asks
      uint32_t addr = 0, len = 0; Camera.getImage(0, &addr, &len);
      if (len) httpPost(String("/api/dev/") + macStr + "/frame", "image/jpeg", (const uint8_t*)addr, len);
      lastSnap = millis();
    }
  }
  delay(150);
}
