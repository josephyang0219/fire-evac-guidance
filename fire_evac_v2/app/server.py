"""Evacuation guidance server — runs on the demo laptop.

Boards -> POST /api/dev/{mac}/detections   one sketch for all boards; the console maps MAC -> position (devices.json)
       -> POST /api/dev/{mac}/frame        JPEG snapshot, only when the server asks (preview / cover-the-lens wizard)
HUBs   -> POST /api/hub/{hub}/detections   (legacy, fixed position in the sketch) YOLO boxes from the on-board NPU
       -> POST /api/hub/{hub}/frame        a JPEG snapshot (for the live-view button)
       <- GET  /api/hub/{hub}/leds         directions for the 2-3 LEDs this HUB drives
Phones <-> WS /ws                          state broadcast, position / role updates, developer commands

python server.py                      live mode (HUBs on the same Wi-Fi hotspot)
python server.py --sim seq.json DIR   replay the simulated world (camera images in DIR/stepK/F1_N.jpg ...)
"""
import argparse, asyncio, json, os, sys, time, copy
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, Response, JSONResponse
import uvicorn

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sim"))
import evac as E, states as ST

HERE = os.path.dirname(os.path.abspath(__file__))
# which junction LEDs each camera HUB drives (9 per floor, 2-3 per HUB)
HUB_LEDS = {"N": [(0, 1), (-1, 1)], "W": [(-1, 0), (-1, -1)], "S": [(0, -1), (1, -1)], "E": [(1, 0), (1, 1), (0, 0)]}

app = FastAPI()
S = dict(dets={}, hubs={}, frames={}, clients={}, people={}, edits={}, cams_off=set(), stairs={"W": True, "E": True},
         sim=None, step=0, note="即時模式", t0=time.time(), state=None, prev=None)
COV = None
SLOTS = [f"{fl}{c}" for fl in (1, 2) for c in ("N", "W", "S", "E")]
DEV_FILE = os.path.join(HERE, "devices.json")
# devices: mac -> {name, slot, last, fps, fw, ip, lum, blink_until, snap_until}
DEV = {}
try:
    for mac, d in json.load(open(DEV_FILE, encoding="utf-8")).items():
        DEV[mac] = dict(name=d.get("name", mac[-4:]), slot=d.get("slot"), last=0, fps=0, fw="", ip="", lum=None)
except Exception:
    pass
WIZ = None   # cover-the-lens wizard: {"slots":[...], "i":0, "base":{mac:lum}, "hits":{mac:n}}


def dev_save():
    json.dump({m: dict(name=d["name"], slot=d["slot"]) for m, d in DEV.items()}, open(DEV_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def dev_assign(mac, slot):
    """put board `mac` on `slot` (None = unassign); a board already on that slot is freed"""
    for m, d in DEV.items():
        if slot and d["slot"] == slot and m != mac:
            d["slot"] = None
    if mac in DEV:
        old = DEV[mac]["slot"]
        DEV[mac]["slot"] = slot
        if old and old != slot:
            S["dets"].pop((int(old[0]), old[1]), None); S["hubs"].pop(old, None)
    dev_save()


def dev_list():
    now = time.time()
    return [dict(mac=m, name=d["name"], slot=d["slot"], online=now - d["last"] < 5, age=round(now - d["last"], 1) if d["last"] else None,
                 fps=d["fps"], fw=d["fw"], ip=d["ip"], lum=None if d["lum"] is None else round(d["lum"]), blink=d.get("blink_until", 0) > now)
            for m, d in sorted(DEV.items(), key=lambda kv: (kv[1]["slot"] or "9", kv[0]))]


def wiz_state():
    if not WIZ:
        return None
    return dict(slots=WIZ["slots"], i=WIZ["i"], slot=WIZ["slots"][WIZ["i"]] if WIZ["i"] < len(WIZ["slots"]) else None, msg=WIZ.get("msg", ""))


def wiz_begin_step():
    WIZ["base"] = {m: d["lum"] for m, d in DEV.items() if d["lum"] is not None and time.time() - d["last"] < 5}
    WIZ["hits"] = {}


def wiz_check(mac):
    """called on every snapshot while the wizard runs: the board whose image goes dark is the one being covered"""
    if not WIZ or WIZ["i"] >= len(WIZ["slots"]) or mac in WIZ.setdefault("done", set()):
        return
    base, lum = WIZ["base"].get(mac), DEV[mac]["lum"]
    if base is None:
        WIZ["base"][mac] = lum; return
    if base > 25 and lum < base * 0.45:
        WIZ["hits"][mac] = WIZ["hits"].get(mac, 0) + 1
    else:
        WIZ["hits"][mac] = 0
    if WIZ["hits"][mac] >= 2:
        slot = WIZ["slots"][WIZ["i"]]
        dev_assign(mac, slot); WIZ["done"].add(mac)
        WIZ["msg"] = f"{DEV[mac]['name']} → {slot}"
        WIZ["i"] += 1
        WIZ["cool"] = time.time() + 2.5        # give the user time to uncover before the next step
        WIZ["base"] = {}


def compute():
    global COV
    if COV is None:
        import run_steps
        COV = run_steps.coverage()
    online = {(fl, c) for fl in E.FLOORS for c in E.CAMS if f"{fl}{c}" not in S["cams_off"] and (S["sim"] or f"{fl}{c}" in S["hubs"])}
    st = E.fuse({k: v for k, v in S["dets"].items() if k in online})
    if S["prev"]:
        for k, s in st.items():
            if not (COV.get(k, set()) & online):
                for f in ("rate", "gate", "smoke", "items"):
                    s[f] = copy.deepcopy(S["prev"][k][f])
                s["unknown"] = True
    S["prev"] = copy.deepcopy(st)
    for k, tool in S["edits"].items():
        s = st.get(k)
        if not s:
            continue
        if tool == "clear": s.update(rate=0.0, gate=False, smoke=0.0, items=[])
        if tool == "obs": s["rate"] = max(s["rate"], 0.5); s["items"].append(("manual", 0.5))
        if tool == "gate": s.update(gate=True, rate=1.0); s["items"].append(("gate", 1.0))
        if tool == "smoke": s["smoke"] = max(s["smoke"], 0.7)
    stairs = tuple(k for k, v in S["stairs"].items() if v)
    leds, dist = E.plan(st, stairs_open=stairs)
    people = []
    for pid, p in list(S["people"].items()):
        fl = p["floor"]; c = E.FLOORS[fl]["ringc"]
        i, j = min(((i, j) for i in (-1, 0, 1) for j in (-1, 0, 1)), key=lambda ij: (ij[0] * c - p["x"]) ** 2 + (ij[1] * c - p["y"]) ** 2)
        d = leds[(fl, i, j)][0]
        people.append(dict(p, id=pid, dir=d, trapped=(d == "X" and p["role"] == "evacuee")))
    step = dict(t=time.strftime("%M:%S", time.gmtime(time.time() - S["t0"])) if not S["sim"] else S["sim"][S["step"]]["t"], note=S["note"])
    js = ST.to_json(step, st, leds, online, people=people, net=net_stats())
    js["dets"] = {f"{k[0]}{k[1]}": v for k, v in S["dets"].items()}
    js["devices"] = dev_list(); js["wizard"] = wiz_state()
    S["state"], S["leds"] = js, leds
    return js


def net_stats():
    out, now = {}, time.time()
    for fl in E.FLOORS:
        for c in E.CAMS:
            h = S["hubs"].get(f"{fl}{c}")
            if not h:
                out[f"HUB-{fl}{c}"] = dict(online=False); continue
            out[f"HUB-{fl}{c}"] = dict(online=now - h["last"] < 5 and f"{fl}{c}" not in S["cams_off"], latency=int(h["lat"]), loss=round(100 * h["lost"] / max(1, h["n"] + h["lost"]), 1), fps=round(h["fps"], 1), age=round(now - h["last"], 1))
    return out


async def broadcast():
    js = compute()
    msg = json.dumps({"type": "state", "state": js}, ensure_ascii=False)
    for ws in list(S["clients"]):
        try:
            await ws.send_text(msg)
        except Exception:
            S["clients"].pop(ws, None)


@app.get("/")
async def index():
    return HTMLResponse(open(os.path.join(HERE, "static", "index.html"), encoding="utf-8").read())


def ingest(hub, b):
    fl, c = int(hub[0]), hub[1]
    h = S["hubs"].setdefault(hub, dict(n=0, lost=0, seq=None, last=0, lat=0, fps=0))
    if h["seq"] is not None and b.get("seq", 0) > h["seq"] + 1:
        h["lost"] += b["seq"] - h["seq"] - 1
    h.update(seq=b.get("seq", 0), n=h["n"] + 1, last=time.time(), fps=b.get("fps", 0), lat=max(0, (time.time() - b.get("ts", time.time())) * 1000))
    S["dets"][(fl, c)] = [tuple(d) for d in b.get("dets", [])]


@app.post("/api/hub/{hub}/detections")
async def hub_dets(hub: str, req: Request):
    ingest(hub, await req.json())
    await broadcast()
    return JSONResponse(hub_leds(hub))


@app.post("/api/dev/{mac}/detections")
async def dev_dets(mac: str, req: Request):
    b = await req.json(); now = time.time()
    d = DEV.get(mac)
    if d is None:                       # a new board says hello -> listed in the console as unassigned
        d = DEV[mac] = dict(name=f"板子 {len(DEV) + 1}（{mac[-4:]}）", slot=None, last=0, fps=0, fw="", ip="", lum=None); dev_save()
    if d["last"] and now - d["last"] < 5:   # measured report rate (what the board actually achieves)
        d["fps"] = round(0.8 * (d["fps"] or 0) + 0.2 / max(now - d["last"], 1e-3), 1)
    d.update(last=now, fw=b.get("fw", ""), ip=req.client.host if req.client else "")
    slot = d["slot"]
    if slot:
        ingest(slot, b)
    if WIZ and WIZ.get("cool") and now > WIZ["cool"]:
        WIZ["cool"] = None; wiz_begin_step()
    await broadcast()
    out = hub_leds(slot) if slot else {"leds": []}
    out.update(slot=slot or "", node=slot[1] if slot else "", blink=int(d.get("blink_until", 0) > now),
               snap=int(bool(WIZ) or d.get("snap_until", 0) > now))
    return JSONResponse(out)


@app.post("/api/dev/{mac}/frame")
async def dev_frame(mac: str, req: Request):
    body = await req.body(); d = DEV.get(mac)
    if d is None:
        return Response(status_code=404)
    d["frame"] = body
    try:
        from PIL import Image, ImageStat
        import io
        d["lum"] = ImageStat.Stat(Image.open(io.BytesIO(body)).convert("L").resize((64, 36))).mean[0]
    except Exception:
        pass
    if d["slot"]:
        S["frames"][d["slot"]] = body
    if WIZ and not WIZ.get("cool"):
        wiz_check(mac)
        await broadcast()
    return {"ok": True}


@app.get("/api/devframe/{mac}.jpg")
async def dev_jpg(mac: str):
    d = DEV.get(mac)
    return Response(d["frame"], media_type="image/jpeg") if d and d.get("frame") else Response(status_code=404)


def hub_leds(hub):
    fl, c = int(hub[0]), hub[1]
    leds = S.get("leds") or {}
    return {"leds": [leds.get((fl,) + ij, ("X", None))[0] for ij in HUB_LEDS[c]]}


@app.get("/api/hub/{hub}/leds")
async def get_leds(hub: str):
    return JSONResponse(hub_leds(hub))


@app.post("/api/hub/{hub}/frame")
async def hub_frame(hub: str, req: Request):
    S["frames"][hub] = await req.body()
    return {"ok": True}


@app.get("/api/cam/{cid}.jpg")
async def cam(cid: str):
    b = S["frames"].get(cid)
    return Response(b, media_type="image/jpeg") if b else Response(status_code=404)


@app.websocket("/ws")
async def ws_ep(ws: WebSocket):
    global WIZ
    await ws.accept()
    pid = f"u{id(ws) % 100000}"
    S["clients"][ws] = pid
    await ws.send_text(json.dumps({"type": "state", "state": S["state"] or compute()}, ensure_ascii=False))
    try:
        while True:
            m = json.loads(await ws.receive_text())
            t = m.get("type")
            if t == "pos":
                S["people"][pid] = dict(name=m.get("name", "手機 " + pid[-3:]), role=m["role"], floor=m["floor"], x=m["x"], y=m["y"])
            elif t == "edit":
                S["edits"][m["seg"]] = m["tool"]
            elif t == "cam":
                (S["cams_off"].discard if m["online"] else S["cams_off"].add)(m["id"])
            elif t == "stair":
                S["stairs"][m["id"]] = m["open"]
            elif t == "assign":            # console: board -> position (None = unassign)
                dev_assign(m["mac"], m.get("slot") or None)
            elif t == "rename" and m.get("mac") in DEV:
                DEV[m["mac"]]["name"] = m["name"][:30]; dev_save()
            elif t == "blink" and m.get("mac") in DEV:
                DEV[m["mac"]]["blink_until"] = time.time() + 6
            elif t == "snap" and m.get("mac") in DEV:
                DEV[m["mac"]]["snap_until"] = time.time() + 15
            elif t == "forget" and m.get("mac") in DEV:
                dev_assign(m["mac"], None); DEV.pop(m["mac"]); dev_save()
            elif t == "wizard":
                if m.get("on"):
                    WIZ = dict(slots=m.get("slots") or SLOTS[:4], i=0, base={}, hits={}, cool=time.time() + 2.0, msg="")
                else:
                    WIZ = None
            elif t == "wizard_skip" and WIZ:
                WIZ["i"] += 1; WIZ["cool"] = time.time() + 1.0
            elif t == "reset":
                S["edits"].clear(); S["cams_off"].clear()
            await broadcast()
    except WebSocketDisconnect:
        S["clients"].pop(ws, None); S["people"].pop(pid, None)
        await broadcast()


async def sim_loop(seq, imgdir, period):
    """pretend to be the 8 HUBs: replay each step's detections and images"""
    import random
    while True:
        for k, step in enumerate(seq):
            S["step"], S["note"] = k, step["note"]
            S["dets"] = {(int(h[0]), h[1]): [tuple(d) for d in v] for h, v in step.get("dets", {}).items()}
            for fl in E.FLOORS:
                for c in E.CAMS:
                    hub = f"{fl}{c}"
                    if any(cm["id"] == hub and not cm["online"] for cm in step["cams"]):
                        continue
                    h = S["hubs"].setdefault(hub, dict(n=0, lost=0, seq=0, last=0, lat=0, fps=0))
                    h.update(n=h["n"] + 1, last=time.time(), lat=random.uniform(30, 110), fps=random.uniform(4.2, 5.8))
                    p = os.path.join(imgdir, f"step{k}", f"F{fl}_{c}.jpg") if imgdir else None
                    if p and os.path.exists(p):
                        S["frames"][hub] = open(p, "rb").read()
            for p in step.get("people", []):
                S["people"][p["id"]] = dict(name=p["name"], role=p["role"], floor=p["floor"], x=p["x"], y=p["y"])
            await broadcast()
            await asyncio.sleep(period)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", nargs="*")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--period", type=float, default=4.0)
    a = ap.parse_args()
    if a.sim:
        S["sim"] = json.load(open(a.sim[0], encoding="utf-8"))
        img = a.sim[1] if len(a.sim) > 1 else None

        @app.on_event("startup")
        async def _start():
            asyncio.create_task(sim_loop(S["sim"], img, a.period))
    uvicorn.run(app, host="0.0.0.0", port=a.port)
