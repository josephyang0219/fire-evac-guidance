# -*- coding: utf-8 -*-
"""假板子：不用實體 HUB 也能測中控台（鏡頭牆、標示框、拖曳指派）。

    python fake_boards.py [--server http://127.0.0.1:8000] [--n 6] [--offline 1]

每片假板子用 hub_node 一樣的協定：
  POST /api/dev/{mac}/detections  {"seq","ts","fw","fps","dets":[[cls,cx,cy,w,h,conf],...]}  約每秒 5 次
  伺服器回 "snap":1 時，再 POST /api/dev/{mac}/frame 一張 640×480 JPEG
畫面上把偵測框的位置畫成色塊，中控台的標示框應該剛好框住色塊（用來確認座標換算正確）。
--offline k：最後 k 片板子 20 秒後停止回報，模擬「斷 Wi-Fi 沒有重連」。
只用標準函式庫＋Pillow。
"""
import argparse, io, json, math, random, threading, time, urllib.request
from PIL import Image, ImageDraw

COL = [(240, 160, 32), (217, 130, 43), (47, 174, 98), (160, 102, 224), (61, 139, 253), (159, 179, 200), (255, 79, 122)]


def post(url, data, ctype):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": ctype}, method="POST")
    with urllib.request.urlopen(req, timeout=3) as r:
        return r.read()


PERIOD = 0.2


def board(server, k, stop_after):
    mac = f"FAKE00{k:06X}"
    rng = random.Random(k)
    base = [(rng.randrange(6), rng.uniform(.2, .8), rng.uniform(.25, .8), rng.uniform(.08, .25), rng.uniform(.1, .3)) for _ in range(rng.randint(1, 3))]
    t0, seq = time.time(), 0
    while True:
        if stop_after and time.time() - t0 > stop_after:
            return
        t = time.time() - t0
        dets = []
        for j, (c, cx, cy, w, h) in enumerate(base):     # 慢慢晃動，信心在 0.3～0.95 之間變化
            dets.append([c, round(cx + .05 * math.sin(t / 2 + j), 4), round(cy + .03 * math.cos(t / 3 + j), 4), w, h,
                         round(.62 + .33 * math.sin(t / 4 + k + j), 3)])
        seq += 1
        try:
            r = json.loads(post(f"{server}/api/dev/{mac}/detections",
                                json.dumps({"seq": seq, "ts": time.time(), "fw": "fake-1", "fps": 5.0, "rssi": -55 - 3 * k, "up": int(t), "dets": dets}).encode(), "application/json"))
            if r.get("snap"):
                im = Image.new("RGB", (640, 480), (40 + 12 * k, 48, 56))
                g = ImageDraw.Draw(im)
                for x in range(0, 640, 40):
                    g.line([(x, 0), (x, 480)], fill=(70, 78, 86))
                for y in range(0, 480, 40):
                    g.line([(0, y), (640, y)], fill=(70, 78, 86))
                for c, cx, cy, w, h, conf in dets:
                    g.rectangle([(cx - w / 2) * 640, (cy - h / 2) * 480, (cx + w / 2) * 640, (cy + h / 2) * 480], fill=COL[c])
                g.text((10, 10), f"FAKE {mac[-4:]}  t={t:5.1f}s", fill=(255, 255, 255))
                b = io.BytesIO(); im.save(b, "JPEG", quality=70)
                post(f"{server}/api/dev/{mac}/frame", b.getvalue(), "image/jpeg")
        except Exception as e:
            print(mac, "error", e)
        time.sleep(PERIOD)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--offline", type=int, default=1)
    ap.add_argument("--period", type=float, default=0.2, help="回報間隔（秒）；FW 2.6 是 0.2，2.5 開預覽時約 0.05")
    a = ap.parse_args()
    PERIOD = a.period
    for k in range(a.n):
        threading.Thread(target=board, args=(a.server, k, 20 if k >= a.n - a.offline else 0), daemon=True).start()
    print(f"{a.n} 片假板子送到 {a.server}（Ctrl+C 結束）")
    while True:
        time.sleep(1)
