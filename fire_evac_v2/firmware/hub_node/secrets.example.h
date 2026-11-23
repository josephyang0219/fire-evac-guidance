// Copy to secrets.h (same folder) and fill in. secrets.h is in .gitignore and must never be committed.
// Anything left out falls back to the defaults in hub_node.ino (FireDemo / 192.168.137.1:8000 / OTA on :3000).
#pragma once
#define WIFI_SSID "your-hotspot"
#define WIFI_PASS "your-password"
#define EVAC_SERVER_IP "192.168.137.1"   // laptop running fire_evac_v2/app/server.py
#define EVAC_SERVER_PORT 8000
#define OTA_SERVER_IP "192.168.137.1"    // laptop running fire_evac_v2/tools/ota_server.py
#define OTA_SERVER_PORT 3000
