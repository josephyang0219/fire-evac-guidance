// 電腦端模擬測試：模擬手動拖磁鐵的人偶（速度忽快忽慢、會停、偶爾漏偵測、偶有誤判），
// 比對 PeopleFlow 算出的 A→B / B→A 人數與正確答案。
// 編譯：python -m ziglang c++ -std=c++17 -O2 -I../hub_people_flow sim_test.cpp -o sim_test.exe
#include <cstdio>
#include <cstdlib>
#include <vector>
#include "PeopleFlow.h"

static float frand() { return rand() / (float)RAND_MAX; }

struct Fig {            // 一個人偶的移動腳本
  float x, y;           // 中心
  float dir;            // +1 往 B（右），-1 往 A（左）
  float speed;          // 畫面寬／秒
  uint32_t start;       // 何時出現（ms）
  bool active, done;
};

struct Scenario {
  const char* name;
  std::vector<Fig> figs;
  float missRate;       // 漏偵測機率
  float fpRate;         // 每幀出現一個隨機誤判框的機率
  float jitter;         // 框位置抖動
  bool pauses;          // 手動拖動：中途停頓、忽快忽慢
  bool linger;          // 有一個人偶在 A 區交界前後晃但沒有走過去
};

static int runScenario(const Scenario& sc, int seed, int& gotAB, int& gotBA) {
  srand(seed);
  PeopleFlow flow;
  flow.minScore = 40;
  std::vector<Fig> figs = sc.figs;
  const float W = 0.07f, H = 0.12f;     // 俯拍人偶框約 40×38 px（576×320）
  int wantAB = 0, wantBA = 0;
  for (auto& f : figs) (f.dir > 0 ? wantAB : wantBA)++;

  const uint32_t FRAME = 125;           // 8 fps
  for (uint32_t now = 0; now < 40000; now += FRAME + (rand() % 30)) {   // 推論時間不固定
    PFDet dets[PeopleFlow::MAX_DETS]; int n = 0;
    for (auto& f : figs) {
      if (f.done || now < f.start) continue;
      if (!f.active) { f.active = true; f.x = f.dir > 0 ? 0.03f : 0.97f; }
      float sp = f.speed;
      if (sc.pauses) {
        float phase = fmodf((now - f.start) / 1000.0f, 3.0f);
        if (phase < 0.6f) sp = 0;                   // 每 3 秒停 0.6 秒（換手）
        else if (phase > 2.4f) sp *= 2.2f;          // 然後拖快一點
        sp *= 0.6f + 0.8f * frand();
      }
      f.x += f.dir * sp * (FRAME / 1000.0f);
      if (f.x > 1.02f || f.x < -0.02f) { f.done = true; continue; }
      if (frand() < sc.missRate) continue;
      float jx = (frand() - 0.5f) * sc.jitter, jy = (frand() - 0.5f) * sc.jitter;
      PFBox b{f.x - W / 2 + jx, f.y - H / 2 + jy, f.x + W / 2 + jx, f.y + H / 2 + jy};
      dets[n++] = {b, 6, 50 + rand() % 45};
    }
    if (sc.linger) {                                 // 在 A 區邊緣 0.30～0.42 間來回，永遠不進 B
      float x = 0.36f + 0.06f * sinf(now / 700.0f);
      dets[n++] = {{x - W / 2, 0.75f - H / 2, x + W / 2, 0.75f + H / 2}, 6, 70};
    }
    if (frand() < sc.fpRate && n < PeopleFlow::MAX_DETS) {   // 一閃而過的誤判
      float x = frand(), y = frand();
      dets[n++] = {{x, y, x + 0.05f, y + 0.08f}, 6, 40 + rand() % 30};
    }
    flow.update(dets, n, now);
  }
  gotAB = flow.countAB(); gotBA = flow.countBA();
  return (gotAB == wantAB && gotBA == wantBA) ? 0 : 1;
}

static Fig fig(float y, float dir, float speed, uint32_t start) { return {0, y, dir, speed, start, false, false}; }

int main() {
  std::vector<Scenario> scs = {
    {"單一人偶 A→B，等速", {fig(0.5f, +1, 0.12f, 0)}, 0, 0, 0.005f, false, false},
    {"單一人偶，手動拖動（停頓＋忽快忽慢）", {fig(0.5f, +1, 0.12f, 0)}, 0.05f, 0, 0.01f, true, false},
    {"3 人同向，間隔 2 秒", {fig(0.3f, +1, 0.12f, 0), fig(0.5f, +1, 0.12f, 2000), fig(0.7f, +1, 0.12f, 4000)}, 0.1f, 0, 0.01f, true, false},
    {"雙向交錯（2 往 B、2 往 A）", {fig(0.3f, +1, 0.12f, 0), fig(0.45f, -1, 0.12f, 500), fig(0.6f, +1, 0.12f, 3000), fig(0.8f, -1, 0.12f, 3500)}, 0.1f, 0, 0.01f, true, false},
    {"漏偵測 25%", {fig(0.4f, +1, 0.12f, 0), fig(0.6f, -1, 0.12f, 1000)}, 0.25f, 0, 0.01f, true, false},
    {"有誤判框（每幀 30%）", {fig(0.4f, +1, 0.12f, 0), fig(0.6f, +1, 0.12f, 3000)}, 0.1f, 0.3f, 0.01f, true, false},
    {"交界前後晃動（不應計數）", {fig(0.3f, +1, 0.12f, 0)}, 0.05f, 0, 0.01f, true, true},
    {"並排靠近同向（間距 0.13）", {fig(0.43f, +1, 0.12f, 0), fig(0.57f, +1, 0.12f, 300)}, 0.1f, 0, 0.01f, true, false},
  };
  const int RUNS = 200;
  int totalFail = 0;
  for (auto& sc : scs) {
    int fail = 0, errSum = 0, want = 0, over = 0, under = 0;
    for (int r = 0; r < RUNS; r++) {
      int ab, ba;
      fail += runScenario(sc, 1000 + r, ab, ba);
      int wAB = 0, wBA = 0;
      for (auto& f : sc.figs) (f.dir > 0 ? wAB : wBA)++;
      errSum += abs(ab - wAB) + abs(ba - wBA);
      over += (ab > wAB ? ab - wAB : 0) + (ba > wBA ? ba - wBA : 0);
      under += (ab < wAB ? wAB - ab : 0) + (ba < wBA ? wBA - ba : 0);
      want += wAB + wBA;
    }
    float acc = 100.0f * (1.0f - (float)errSum / (want ? want : 1));
    printf("%-34s 完全正確 %3d/%d  計數準確率 %.1f%%  多算 %d 少算 %d\n", sc.name, RUNS - fail, RUNS, acc, over, under);
    totalFail += fail;
  }
  printf(totalFail ? "\n有失誤：%d 次\n" : "\n全部正確\n", totalFail);
  return 0;
}
