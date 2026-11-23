// HUB-8735 Ultra 無線更新（OTA）單機測試
// 第一版用 USB 燒錄；之後改 FW_VERSION 重新編譯，由筆電 ota_server.py 無線推送。
// 編譯時必須開 OTA：FQBN 加 :08_OTAMode=Enable
// Wi-Fi 帳密放在 secrets.h（不進 git），格式見 secrets.example.h
#include <WiFi.h>
#include "OTA.h"
#include "secrets.h"

#define FW_VERSION 1                 // 改這個數字就能分辨是不是更新成功

char ssid[] = WIFI_SSID;
char pass[] = WIFI_PASS;
char server[] = OTA_SERVER_IP;       // 筆電熱點 IP，Windows 行動熱點預設 192.168.137.1
const int port = OTA_SERVER_PORT;    // 筆電 ota_server.py 的 port

OTA ota;

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.print("[OTA-TEST] boot, FW_VERSION=");
  Serial.println(FW_VERSION);
  int status = WL_IDLE_STATUS;
  while (status != WL_CONNECTED) {
    Serial.print("[OTA-TEST] connecting to ");
    Serial.println(ssid);
    status = WiFi.begin(ssid, pass);
    delay(2000);
  }
  Serial.print("[OTA-TEST] IP=");
  Serial.println(WiFi.localIP());
  ota.start_OTA_threads(port, server);
}

void loop() {
  // 版本 1 慢閃、版本 2 以上快閃，不看序列埠也能分辨
  int ms = (FW_VERSION == 1) ? 1000 : 150;
  digitalWrite(LED_BUILTIN, HIGH); delay(ms);
  digitalWrite(LED_BUILTIN, LOW);  delay(ms);
  static unsigned long last = 0;
  if (millis() - last > 5000) {
    last = millis();
    Serial.print("[OTA-TEST] alive, FW_VERSION=");
    Serial.print(FW_VERSION);
    Serial.print(" IP=");
    Serial.println(WiFi.localIP());
  }
}
