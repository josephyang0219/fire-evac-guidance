# -*- coding: utf-8 -*-
"""從中控台抓板子的即時快照與板上偵測結果（2026-11-25，做實景誤判測試、補拍訓練資料用）。

    python capture_frames.py <伺服器 host:port> <輸出資料夾> <秒數> [MAC 末四碼,逗號分隔]

連上中控台的 WebSocket，每 2 秒請每台（或指定的幾台）板子上傳快照，每秒抓一次 /api/devframe/<mac>.jpg，
和上一張相同就略過。存成 <輸出>/<mac>/<時間>.jpg；板上（目前上板的模型）同一時刻的偵測框寫在 <輸出>/ondev.jsonl。
需要 websockets（pip install websockets，或用 uvicorn[standard] 的環境）。
"""
import asyncio, json, os, sys, time, urllib.request, hashlib
import websockets
SERVER, OUT, DUR = sys.argv[1], sys.argv[2], float(sys.argv[3])
ONLY = sys.argv[4].split(',') if len(sys.argv) > 4 else None
os.makedirs(OUT, exist_ok=True)
async def main():
    async with websockets.connect(f"ws://{SERVER}/ws", max_size=None) as ws:
        devs = {}; last = {}; t0 = time.time(); snap_at = 0; n = 0
        log = open(os.path.join(OUT, "ondev.jsonl"), "a", encoding="utf-8")
        async def reader():
            nonlocal devs
            while True:
                m = json.loads(await ws.recv())
                if m.get("type") == "state":
                    devs = {d["mac"]: d for d in m["state"].get("devices", []) if not ONLY or d["mac"][-4:] in ONLY}
        rt = asyncio.create_task(reader())
        while time.time() - t0 < DUR:
            now = time.time()
            if now - snap_at > 2:
                snap_at = now
                for mac, d in devs.items():
                    if d.get("online"): await ws.send(json.dumps({"type": "snap", "mac": mac}))
            for mac, d in list(devs.items()):
                if not d.get("online"): continue
                try: b = await asyncio.to_thread(lambda: urllib.request.urlopen(f"http://{SERVER}/api/devframe/{mac}.jpg?t={time.time()}", timeout=3).read())
                except Exception: continue
                h = hashlib.md5(b).hexdigest()
                if last.get(mac) == h: continue
                last[mac] = h; os.makedirs(os.path.join(OUT, mac), exist_ok=True)
                fn = f"{now:.2f}.jpg"; open(os.path.join(OUT, mac, fn), "wb").write(b); n += 1
                log.write(json.dumps({"mac": mac, "slot": d.get("slot"), "file": f"{mac}/{fn}", "dets": d.get("dets", [])}) + "\n"); log.flush()
            await asyncio.sleep(1.0)
        rt.cancel(); print("saved", n, "frames from", sum(1 for d in devs.values() if d.get("online")), "boards")
asyncio.run(main())
