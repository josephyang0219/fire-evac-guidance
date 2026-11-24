// 已知問題：HTTP Content-Length 解析得到 0，下載會失敗；目前改用讀卡機把模型放進 SD 卡
// 不用讀卡機：板子透過 Wi-Fi 從筆電下載模型，寫進自己 SD 卡的 NN_MDL/yolov7_tiny.nb，再讀回來核對。
// 筆電端：在放模型的資料夾執行  python -m http.server 3001
// 板子流程：連熱點 → 掛載 SD 卡（印容量）→ 下載到 .tmp → 讀回算 CRC32 → 改名成正式檔名 → 印出大小與 CRC32。
// 程式也開 OTA（ota_server.py），寫完之後可以直接無線推 hub_node。
// 編譯：FQBN 加 :08_OTAMode=Enable,06_LoadNNModelSource=sd；Wi-Fi 設定在 secrets.h（不進 git）。
#include <WiFi.h>
#include "AmebaFatFS.h"
#include "OTA.h"
#include "secrets.h"

#define FW_TAG "sd_model_writer v1"
#define MODEL_HOST OTA_SERVER_IP        // 筆電熱點 IP
#define MODEL_PORT 3001
#define MODEL_URL "/yolov7_tiny.nb"

char ssid[] = WIFI_SSID;
char pass[] = WIFI_PASS;
char otaServer[] = OTA_SERVER_IP;
OTA ota;
AmebaFatFS fs;
static uint8_t buf[4096];

uint32_t crc32Update(uint32_t c, const uint8_t *p, size_t n) {
  c = ~c;
  while (n--) {
    c ^= *p++;
    for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1)));
  }
  return ~c;
}

bool download(const char *path, long &gotLen, uint32_t &crc) {
  WiFiClient cl;
  if (!cl.connect(MODEL_HOST, MODEL_PORT)) { Serial.println("[SD] connect to laptop failed"); return false; }
  cl.print(String("GET ") + MODEL_URL + " HTTP/1.0\r\nHost: " + MODEL_HOST + "\r\n\r\n");
  // 讀標頭
  long contentLen = -1;
  String line;
  unsigned long t0 = millis();
  while (millis() - t0 < 10000) {
    if (!cl.available()) { delay(2); continue; }
    char ch = cl.read();
    if (ch == '\n') {
      line.trim();
      if (line.length() == 0) break;
      if (line.startsWith("Content-Length:") || line.startsWith("content-length:")) contentLen = line.substring(15).toInt();
      if (line.startsWith("HTTP/") && line.indexOf(" 200") < 0) { Serial.print("[SD] HTTP error: "); Serial.println(line); return false; }
      line = "";
    } else line += ch;
  }
  Serial.print("[SD] Content-Length="); Serial.println(contentLen);
  if (contentLen <= 0) return false;
  fs.remove(path);
  File f = fs.open(path);
  if (!f) { Serial.println("[SD] open for write failed"); return false; }
  gotLen = 0; crc = 0;
  t0 = millis();
  unsigned long lastByte = millis(), lastPrint = 0;
  while (gotLen < contentLen && millis() - lastByte < 15000) {
    int n = cl.available();
    if (n <= 0) { delay(1); continue; }
    if (n > (int)sizeof(buf)) n = sizeof(buf);
    n = cl.read(buf, n);
    if (n <= 0) continue;
    f.write(buf, n);
    crc = crc32Update(crc, buf, n);
    gotLen += n;
    lastByte = millis();
    if (millis() - lastPrint > 2000) { lastPrint = millis(); Serial.print("[SD] "); Serial.print(gotLen * 100 / contentLen); Serial.println("%"); }
  }
  f.close();
  cl.stop();
  Serial.print("[SD] downloaded "); Serial.print(gotLen); Serial.print(" bytes in "); Serial.print(millis() - t0); Serial.println(" ms");
  return gotLen == contentLen;
}

bool readBack(const char *path, long &len, uint32_t &crc) {
  File f = fs.open(path);
  if (!f) return false;
  len = 0; crc = 0;
  int n;
  while ((n = f.read(buf, sizeof(buf))) > 0) { crc = crc32Update(crc, buf, n); len += n; }
  f.close();
  return true;
}

void setup() {
  Serial.begin(115200);
  Serial.println("[SD] boot " FW_TAG);
  int st = WL_IDLE_STATUS;
  while (st != WL_CONNECTED) { st = WiFi.begin(ssid, pass); delay(2000); }
  Serial.print("[SD] IP="); Serial.println(WiFi.localIP());
  ota.start_OTA_threads(OTA_SERVER_PORT, otaServer);

  if (!fs.begin()) { Serial.println("[SD] RESULT FAIL: SD card mount failed (no card / bad card / not FAT32)"); return; }
  Serial.print("[SD] root="); Serial.print(fs.getRootPath());
  Serial.print(" free MB="); Serial.print((long)(fs.get_free_space() / 1024 / 1024));
  Serial.print(" used MB="); Serial.println((long)(fs.get_used_space() / 1024 / 1024));

  char dir[64], tmp[96], fin[96];
  sprintf(dir, "%sNN_MDL", fs.getRootPath());
  sprintf(tmp, "%sNN_MDL/yolov7_tiny.tmp", fs.getRootPath());
  sprintf(fin, "%sNN_MDL/yolov7_tiny.nb", fs.getRootPath());
  if (!fs.exists(dir)) fs.mkdir(dir);

  long dlLen = 0, rbLen = 0; uint32_t dlCrc = 0, rbCrc = 0;
  if (!download(tmp, dlLen, dlCrc)) { Serial.println("[SD] RESULT FAIL: download"); return; }
  if (!readBack(tmp, rbLen, rbCrc) || rbLen != dlLen || rbCrc != dlCrc) {
    Serial.print("[SD] RESULT FAIL: read-back mismatch len="); Serial.print(rbLen); Serial.print(" crc="); Serial.println(rbCrc, HEX);
    return;
  }
  fs.remove(fin);
  fs.rename(tmp, fin);
  if (!readBack(fin, rbLen, rbCrc)) { Serial.println("[SD] RESULT FAIL: final file missing"); return; }
  Serial.print("[SD] RESULT OK "); Serial.print(fin); Serial.print(" size="); Serial.print(rbLen);
  Serial.print(" crc32="); Serial.println(rbCrc, HEX);
}

void loop() { delay(1000); }
