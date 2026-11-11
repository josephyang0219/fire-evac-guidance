/*
  HUB 8735 Ultra "H5" — the 5th, display-only node of 1F (draft, not yet tested on hardware)

  No camera, no model: it only shows the directions of the 5 junctions the camera HUBs don't drive
  (centre + 4 edge middles), on 5 SSD1306 behind a TCA9548A (0x70) on Wire, all at 0x3C.

  Every POLL_MS:  GET /api/junctions?node=H5&seq=N&fw=..
  Server answers: {"junctions":[{"id":"J(-1,1)","dir":"S"},...9 items]}   dir = N/S/E/W/UP/DOWN/X
  The query is the heartbeat: the console lists H5 under "displays" (online, loss). Picking our 5 ids out of the
  reply is done by EvacOled::applyJson() (oled_fw/libraries/EvacOled, pass it with --library).

  No data for LINK_TIMEOUT_MS (Wi-Fi down, server stopped, bad reply): all 5 displays go dark.
  Dark = "no guidance from here", rather than a stale arrow (could lead into a fire that started since)
  or X (would tell people there is no way out). Before the first reply the displays are dark as well.
*/
#include "WiFi.h"
#include <EvacOled.h>
using namespace evac;

const char* SSID = "FireDemo";          // laptop hotspot (same as hub_node)
const char* PASS = "firedemo123";
const char* SERVER = "192.168.137.1";
const int   PORT = 8000;
const char* NODE = "H5";
const char* FW = "h5-1.0";
const unsigned long POLL_MS = 300;
const unsigned long LINK_TIMEOUT_MS = 3000;

// ---------- the 5 displays (EDIT HERE): id = junction id from the server, muxChannel = TCA9548A channel ----------
// top / ceiling: screen top edge points north and the panel faces down (seen from below) -- fix once mounted
#define OLED(id, bus, addr, ch) {id, bus, addr, ch, Panel::P128x64, Compass::N, true}
const SlotConfig SLOTS[] = {
  OLED("J(0,0)",  Bus::Wire0, 0x3C, 0),   // centre
  OLED("J(0,1)",  Bus::Wire0, 0x3C, 1),   // N
  OLED("J(1,0)",  Bus::Wire0, 0x3C, 2),   // E
  OLED("J(0,-1)", Bus::Wire0, 0x3C, 3),   // S
  OLED("J(-1,0)", Bus::Wire0, 0x3C, 4),   // W
};
const uint8_t N_SLOTS = sizeof(SLOTS) / sizeof(SlotConfig);
const MuxConfig MUX = {Bus::Wire0, 0x70};

EvacOled oled;
WiFiClient client;
unsigned long seq = 0, lastPoll = 0, lastReply = 0;
bool linkLost = true;

String httpGet(const String& path) {
  String resp;
  if (!client.connect(SERVER, PORT)) return resp;
  client.print(String("GET ") + path + " HTTP/1.1\r\nHost: " + SERVER + "\r\nConnection: close\r\n\r\n");
  unsigned long t0 = millis();
  while (client.connected() && millis() - t0 < 500) { while (client.available()) resp += (char)client.read(); }
  client.stop();
  if (!resp.startsWith("HTTP/1.1 200")) return "";
  int b = resp.indexOf("\r\n\r\n");
  return b < 0 ? "" : resp.substring(b + 4);
}

void connectWiFi() {
  Serial.print("Wi-Fi "); Serial.println(SSID);
  WiFi.begin((char*)SSID, (char*)PASS);    // blocks a few seconds; displays stay dark meanwhile
}

void setup() {
  Serial.begin(115200);
  uint8_t ok = oled.begin(SLOTS, N_SLOTS, &MUX);
  Serial.print("H5 OLED online "); Serial.print(ok); Serial.print("/"); Serial.println(N_SLOTS);
  oled.setAll(Sign::Off);
  oled.update();
  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  else if (millis() - lastPoll >= POLL_MS) {
    lastPoll = millis();
    String body = httpGet(String("/api/junctions?node=") + NODE + "&seq=" + (++seq) + "&fw=" + FW);
    Sign before[N_SLOTS];
    for (uint8_t k = 0; k < N_SLOTS; k++) before[k] = oled.sign(k);
    if (body.length() && oled.applyJson(body.c_str()) == N_SLOTS) {   // all 5 ids present = a valid reply
      lastReply = millis();
      if (linkLost) { linkLost = false; Serial.println("link ok"); }
    }
    for (uint8_t k = 0; k < N_SLOTS; k++)
      if (oled.sign(k) != before[k]) { Serial.print("[OLED ch"); Serial.print(SLOTS[k].muxChannel); Serial.print(" "); Serial.print(SLOTS[k].id); Serial.print("] -> "); Serial.println(signName(oled.sign(k))); }
  }
  if (!linkLost && millis() - lastReply > LINK_TIMEOUT_MS) { linkLost = true; oled.setAll(Sign::Off); Serial.println("link lost -> dark"); }
  oled.update();
  delay(10);
}
