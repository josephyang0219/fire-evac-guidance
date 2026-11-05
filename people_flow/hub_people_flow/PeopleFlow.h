/*
  PeopleFlow.h — 人偶人流追蹤與 A/B 區域計數（單一標頭檔，不依賴 Arduino）

  用法（每一幀推論結果呼叫一次）：
    PeopleFlow flow;
    flow.setZones({0.00f, 0.0f, 0.35f, 1.0f}, {0.65f, 0.0f, 1.00f, 1.0f});   // A 在左、B 在右，中間是緩衝區
    flow.update(dets, n, millis());
    flow.countAB() / flow.countBA() / flow.activeCount() / flow.movingCount()

  座標一律是正規化 0～1（SDK 的 xMin()/yMin()/xMax()/yMax() 直接用）。
  設計給「天花板俯拍、手動在地板下拖磁鐵移動的 1:10 人偶」：
   - 速度忽快忽慢、會停頓 → 配對不靠速度預測，只看 IoU 與中心距離
   - 偶爾一兩幀漏偵測 → 目標消失後保留 KEEP_MS 才刪除，回來沿用同一個 ID
   - 一閃而過的誤判 → 新目標要連續命中 CONFIRM_HITS 幀才算數
   - 站在區域交界前後晃 → A、B 之間留緩衝區，只有「先在 A、後進 B」才計一次
  所有陣列固定大小、不用 new／vector，可直接在 8735 上跑。
*/
#pragma once
#include <math.h>
#include <stdint.h>

struct PFBox { float x0, y0, x1, y1; };

struct PFDet {
  PFBox box;
  int cls;
  int score;   // 0～100
};

struct PFTrack {
  bool used;
  int id;
  PFBox box;
  float cx, cy;          // 中心點
  float vx, vy;          // 平滑後的速度（畫面寬高／秒）
  int hits;              // 累計命中幀數
  bool confirmed;
  uint32_t lastSeen;     // 最後一次配對到的時間（ms）
  int8_t zone;           // 最後一次所在區域：0 = 未知、1 = A、2 = B（緩衝區不改變）
  int cls;
};

class PeopleFlow {
public:
  static const int MAX_TRACKS = 16;
  static const int MAX_DETS = 32;

  // 參數：都可在 setup() 依實測調整
  float iouMin = 0.10f;          // IoU 至少這麼多才可能是同一個
  float maxJump = 0.12f;         // 或中心點移動不超過畫面寬度的 12%（連續幀時；手動拖動偶爾會快一點）
  float maxSpeed = 0.6f;         // 漏偵測幾幀後重新出現時，允許的距離 = 最高速度（畫面寬／秒）× 消失時間
  float maxGap = 0.22f;          // 但最多放寬到這麼遠（要小於 A、B 間距，一次配對不可能直接從 A 跳到 B）
  float edgeMargin = 0.06f;      // 在畫面邊緣這個範圍內消失 → 視為已走出畫面，提早刪除
  int confirmHits = 3;           // 連續命中幾幀才成為正式目標
  uint32_t keepMs = 1000;        // 消失多久才刪除
  uint32_t tentativeKeepMs = 300;// 還沒確認的目標，消失就快點刪
  float movingSpeed = 0.05f;     // 速度超過「畫面寬度 5%／秒」算移動中
  float velAlpha = 0.3f;         // 速度平滑係數（越小越平滑）
  int minScore = 40;             // 低於此信心值的框不追蹤
  int classFilter = -1;          // 只追蹤這一類（-1 = 全部；補訓後設 6 = person）

  void setZones(PFBox a, PFBox b) { zoneA = a; zoneB = b; }
  void reset() {
    for (int i = 0; i < MAX_TRACKS; i++) tracks[i].used = false;
    nextId = 1; nAB = nBA = 0;
  }
  PeopleFlow() { reset(); zoneA = {0, 0, 0.35f, 1}; zoneB = {0.65f, 0, 1, 1}; }

  void update(const PFDet* dets, int n, uint32_t nowMs) {
    if (n > MAX_DETS) n = MAX_DETS;
    bool detUsed[MAX_DETS] = {false};
    bool trkUsed[MAX_TRACKS] = {false};

    // 1. 先把不要的框標成已用（信心低或類別不符）
    for (int d = 0; d < n; d++)
      if (dets[d].score < minScore || (classFilter >= 0 && dets[d].cls != classFilter)) detUsed[d] = true;

    // 2. 貪婪配對：每次挑分數最高的一組（追蹤目標, 偵測框），直到沒有合格的組合
    while (true) {
      float best = 0; int bt = -1, bd = -1;
      for (int t = 0; t < MAX_TRACKS; t++) {
        if (!tracks[t].used || trkUsed[t]) continue;
        for (int d = 0; d < n; d++) {
          if (detUsed[d]) continue;
          float s = matchScore(tracks[t], dets[d].box, nowMs);
          if (s > best) { best = s; bt = t; bd = d; }
        }
      }
      if (bt < 0) break;
      trkUsed[bt] = detUsed[bd] = true;
      apply(tracks[bt], dets[bd], nowMs);
    }

    // 3. 沒配到的偵測框 → 新目標
    for (int d = 0; d < n; d++) {
      if (detUsed[d]) continue;
      int slot = freeSlot();
      if (slot < 0) break;
      PFTrack& t = tracks[slot];
      t.used = true; t.id = nextId++; t.box = dets[d].box;
      center(t.box, t.cx, t.cy); t.vx = t.vy = 0;
      t.hits = 1; t.confirmed = (confirmHits <= 1); t.lastSeen = nowMs;
      t.zone = zoneOf(t.cx, t.cy); t.cls = dets[d].cls;
      trkUsed[slot] = true;
    }

    // 4. 太久沒看到的目標刪除；沒配到的速度慢慢歸零（停下來的人偶）
    for (int t = 0; t < MAX_TRACKS; t++) {
      if (!tracks[t].used || trkUsed[t]) continue;
      uint32_t gone = nowMs - tracks[t].lastSeen;
      const PFTrack& k = tracks[t];
      bool atEdge = k.cx < edgeMargin || k.cx > 1 - edgeMargin || k.cy < edgeMargin || k.cy > 1 - edgeMargin;
      if (gone > (k.confirmed && !atEdge ? keepMs : tentativeKeepMs)) tracks[t].used = false;
      else { tracks[t].vx *= 0.8f; tracks[t].vy *= 0.8f; }
    }
  }

  int countAB() const { return nAB; }
  int countBA() const { return nBA; }
  int activeCount() const {
    int c = 0;
    for (int t = 0; t < MAX_TRACKS; t++) if (tracks[t].used && tracks[t].confirmed) c++;
    return c;
  }
  int movingCount() const {
    int c = 0;
    for (int t = 0; t < MAX_TRACKS; t++) if (tracks[t].used && tracks[t].confirmed && isMoving(tracks[t])) c++;
    return c;
  }
  // 擁擠程度：正式目標的框面積加總占畫面比例（0～1，可能重疊所以只是估計）
  float occupancy() const {
    float a = 0;
    for (int t = 0; t < MAX_TRACKS; t++)
      if (tracks[t].used && tracks[t].confirmed) a += (tracks[t].box.x1 - tracks[t].box.x0) * (tracks[t].box.y1 - tracks[t].box.y0);
    return a > 1 ? 1 : a;
  }
  bool isMoving(const PFTrack& t) const { return sqrtf(t.vx * t.vx + t.vy * t.vy) > movingSpeed; }
  const PFTrack& track(int i) const { return tracks[i]; }
  PFBox zoneABox() const { return zoneA; }
  PFBox zoneBBox() const { return zoneB; }

private:
  PFTrack tracks[MAX_TRACKS];
  PFBox zoneA, zoneB;
  int nextId, nAB, nBA;

  static void center(const PFBox& b, float& cx, float& cy) { cx = (b.x0 + b.x1) * 0.5f; cy = (b.y0 + b.y1) * 0.5f; }
  static bool inside(const PFBox& z, float x, float y) { return x >= z.x0 && x <= z.x1 && y >= z.y0 && y <= z.y1; }
  int8_t zoneOf(float x, float y) const { return inside(zoneA, x, y) ? 1 : inside(zoneB, x, y) ? 2 : 0; }

  static float iou(const PFBox& a, const PFBox& b) {
    float w = fminf(a.x1, b.x1) - fmaxf(a.x0, b.x0), h = fminf(a.y1, b.y1) - fmaxf(a.y0, b.y0);
    if (w <= 0 || h <= 0) return 0;
    float inter = w * h, u = (a.x1 - a.x0) * (a.y1 - a.y0) + (b.x1 - b.x0) * (b.y1 - b.y0) - inter;
    return u > 0 ? inter / u : 0;
  }

  // 0 = 不可能是同一個；越大越像。IoU 為主，框不重疊時才看中心距離（快速拖動的那一幀）。
  // 距離上限隨「多久沒看到」放寬：漏偵測幾幀後人偶已經走遠，不放寬會在緩衝區被當成新人偶而漏算
  float matchScore(const PFTrack& t, const PFBox& b, uint32_t nowMs) const {
    float o = iou(t.box, b);
    float cx, cy; center(b, cx, cy);
    float dist = sqrtf((cx - t.cx) * (cx - t.cx) + (cy - t.cy) * (cy - t.cy));
    float lim = fminf(maxGap, fmaxf(maxJump, maxSpeed * (nowMs - t.lastSeen) / 1000.0f));
    if (o < iouMin && dist > lim) return 0;
    return o + (1.0f - dist / lim) * 0.5f + 0.001f;
  }

  void apply(PFTrack& t, const PFDet& d, uint32_t nowMs) {
    float cx, cy; center(d.box, cx, cy);
    float dt = (nowMs - t.lastSeen) / 1000.0f;
    if (dt > 0.001f) {
      t.vx = velAlpha * ((cx - t.cx) / dt) + (1 - velAlpha) * t.vx;
      t.vy = velAlpha * ((cy - t.cy) / dt) + (1 - velAlpha) * t.vy;
    }
    t.box = d.box; t.cx = cx; t.cy = cy; t.lastSeen = nowMs; t.cls = d.cls;
    if (++t.hits >= confirmHits) t.confirmed = true;

    int8_t z = zoneOf(cx, cy);
    if (z == 0) return;                       // 在緩衝區：不改變，避免交界晃動重複計數
    if (t.confirmed && t.zone != 0 && z != t.zone) {
      if (t.zone == 1 && z == 2) nAB++;
      else if (t.zone == 2 && z == 1) nBA++;
    }
    t.zone = z;
  }

  int freeSlot() const {
    for (int t = 0; t < MAX_TRACKS; t++) if (!tracks[t].used) return t;
    return -1;
  }
};
