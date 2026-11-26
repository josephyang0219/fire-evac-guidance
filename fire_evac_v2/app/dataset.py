# -*- coding: utf-8 -*-
"""錄製＋標記（實拍訓練資料），2026-11-27。由 server.py 掛上；網頁在 /label（static/label.html）。

資料放在 app/captures/<組 id>/：
  meta.json     組名、類型（empty 空場景／obstacle 障礙物＋閘門／smoke 通煙／other）、建立時間、標記點（點香、換燈…）
  frames.jsonl  每張一行：file、mac、slot、t、light、dets（板上模型當下的框，當預標用）
  labels.json   {file: {"boxes": [[cls, cx, cy, w, h], ...], "reviewed": bool, "source": "..."}}
  prelabel.json （選用）retrain/tools/prelabel_captures.py 用 v6 權重產生的預標，優先於板上的框
  *.jpg         快照（板子上傳的 640×480）

錄製方式（docs/實拍訓練流程_2026-11-25.md 的「組」）：
  抓一輪：每台已指派、在線的板子各存一張「按下之後才拍到」的新快照（FW 2.8 起板子快照每 2 秒一張，最多等 8 秒）
  連續錄製：通煙用，每台每 interval 秒存一張，可以按「點香／換燈光／熄香」記下時間點
空場景類型的組，存下來就直接當「已檢查、沒有框」。
匯出：所有「已檢查」的張數寫成 YOLO 資料集 captures/_export/<時間>/images、labels（類別 0–6 同訓練），
      之後 make_dataset.py --src <那個資料夾>:3 就能放進訓練。
"""
import asyncio, json, os, re, shutil, time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "captures")
CLASSES = ["cabinet", "boxes", "furniture", "rubble", "gate", "smoke", "person"]
KINDS = {"empty": "空場景", "obstacle": "障礙物＋閘門", "smoke": "通煙", "other": "其他"}
PRE_CONF = 0.4                      # 板上模型的框，信心 ≥ 0.4 才當預標
router = APIRouter()
DEV = None                          # server.py 的 DEV（mac -> 狀態），init() 時給
REC = dict(on=False, set=None, interval=2.0, light="", last={}, shot_until=0.0)


def init(dev):
    global DEV
    DEV = dev
    os.makedirs(ROOT, exist_ok=True)


def wants_snap(mac):
    """板子回報時問：現在要不要上傳快照（錄製中、或剛按了「抓一輪」）"""
    return REC["on"] or time.time() < REC["shot_until"]


def _sdir(sid):
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", sid or ""):
        raise ValueError("bad set id")
    return os.path.join(ROOT, sid)


def _jload(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def _jsave(p, obj):
    tmp = p + ".tmp"
    json.dump(obj, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    os.replace(tmp, p)


def _frames(sid):
    out = []
    try:
        for line in open(os.path.join(_sdir(sid), "frames.jsonl"), encoding="utf-8"):
            if line.strip():
                out.append(json.loads(line))
    except FileNotFoundError:
        pass
    return out


def _save_frame(sid, mac, d, tag=""):
    """把這片板子目前的快照存進組裡"""
    if not d.get("frame"):
        return None
    meta = _jload(os.path.join(_sdir(sid), "meta.json"), {})
    t = d.get("frame_t") or time.time()
    slot = d.get("slot") or "x"
    fn = f"{slot}_{mac[-4:]}_{int(t * 1000)}.jpg"
    open(os.path.join(_sdir(sid), fn), "wb").write(d["frame"])
    dets = [[int(x[0])] + [round(float(v), 5) for v in x[1:5]] + [round(float(x[5]), 3)] for x in (d.get("dets") or []) if len(x) >= 6]
    rec = dict(file=fn, mac=mac, slot=d.get("slot"), t=round(t, 2), light=REC["light"] or meta.get("light", ""), tag=tag, dets=dets)
    with open(os.path.join(_sdir(sid), "frames.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if meta.get("kind") == "empty":                  # 空場景：存下來就是「已檢查、沒有框」
        lab = _jload(os.path.join(_sdir(sid), "labels.json"), {})
        lab[fn] = dict(boxes=[], reviewed=True, source="empty")
        _jsave(os.path.join(_sdir(sid), "labels.json"), lab)
    REC["last"][mac] = time.time()
    return rec


def on_frame(mac, d):
    """server.py 收到快照時呼叫：連續錄製中就依間隔存檔"""
    if REC["on"] and REC["set"] and d.get("slot") and time.time() - REC["last"].get(mac, 0) >= REC["interval"] - 0.05:
        _save_frame(REC["set"], mac, d, "rec")


def _new_set(name, kind, light):
    sid = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(_sdir(sid), exist_ok=True)
    _jsave(os.path.join(_sdir(sid), "meta.json"), dict(id=sid, name=name or sid, kind=kind if kind in KINDS else "other",
                                                       light=light, created=time.time(), marks=[]))
    return sid


def _set_summary(sid):
    meta = _jload(os.path.join(_sdir(sid), "meta.json"), {})
    fr = _frames(sid); lab = _jload(os.path.join(_sdir(sid), "labels.json"), {})
    rv = sum(1 for f in fr if lab.get(f["file"], {}).get("reviewed"))
    nb = sum(len(lab.get(f["file"], {}).get("boxes", [])) for f in fr if lab.get(f["file"], {}).get("reviewed"))
    return dict(id=sid, name=meta.get("name", sid), kind=meta.get("kind", "other"), kind_name=KINDS.get(meta.get("kind"), "其他"),
                created=meta.get("created", 0), n=len(fr), reviewed=rv, boxes=nb, boards=sorted({f.get("slot") or f["mac"][-4:] for f in fr}))


def _find_set(name):
    for sid in sorted(os.listdir(ROOT), reverse=True):
        if os.path.isdir(os.path.join(ROOT, sid)) and not sid.startswith("_"):
            if _jload(os.path.join(ROOT, sid, "meta.json"), {}).get("name") == name:
                return sid
    return None


# ---------------------------------------------------------------- 錄製
@router.get("/api/rec/status")
async def rec_status():
    now = time.time()
    boards = [dict(mac=m, slot=d.get("slot"), online=now - d.get("last", 0) < 5) for m, d in (DEV or {}).items()]
    return dict(on=REC["on"], set=REC["set"], interval=REC["interval"], light=REC["light"],
                set_info=_set_summary(REC["set"]) if REC["set"] and os.path.isdir(_sdir(REC["set"])) else None, boards=boards)


@router.post("/api/rec/shot")
async def rec_shot(req: Request):
    """抓一輪：組名相同就加進同一組（換燈光再抓一輪）；每台存一張按下之後的新快照"""
    b = await req.json()
    name, kind, light = (b.get("name") or "").strip()[:60], b.get("kind", "other"), (b.get("light") or "").strip()[:30]
    sid = _find_set(name) or _new_set(name, kind, light)
    REC["light"] = light
    now = time.time()
    targets = {m: d for m, d in DEV.items() if d.get("slot") and now - d.get("last", 0) < 5}
    if not targets:
        return JSONResponse(dict(ok=False, msg="沒有已指派且在線的板子", set=sid))
    t0 = now
    REC["shot_until"] = now + 9
    for _ in range(80):                                  # 最多等 8 秒，每台都拿到 t0 之後的新快照就停
        if all((d.get("frame_t") or 0) > t0 for d in targets.values()):
            break
        await asyncio.sleep(0.1)
    REC["shot_until"] = 0
    saved, missing = [], []
    for m, d in targets.items():
        if (d.get("frame_t") or 0) > t0:
            saved.append(_save_frame(sid, m, d, "shot"))
        else:
            missing.append(d.get("slot") or m[-4:])
    meta = _jload(os.path.join(_sdir(sid), "meta.json"), {})
    meta.setdefault("marks", []).append(dict(t=round(t0, 2), text=f"抓一輪（{light or '未填燈光'}）"))
    _jsave(os.path.join(_sdir(sid), "meta.json"), meta)
    return dict(ok=True, set=sid, saved=[s["file"] for s in saved if s], missing=missing, info=_set_summary(sid))


@router.post("/api/rec/start")
async def rec_start(req: Request):
    b = await req.json()
    name = (b.get("name") or "").strip()[:60]
    REC.update(on=True, set=_find_set(name) or _new_set(name, b.get("kind", "smoke"), b.get("light", "")),
               interval=max(1.0, float(b.get("interval", 2))), light=(b.get("light") or "").strip()[:30], last={})
    return await rec_status()


@router.post("/api/rec/stop")
async def rec_stop():
    REC["on"] = False
    return await rec_status()


@router.post("/api/rec/mark")
async def rec_mark(req: Request):
    """通煙時記時間點（點香、換燈光、熄香、自訂）；換燈光時一起改之後存檔的燈光欄"""
    b = await req.json()
    sid = b.get("set") or REC["set"]
    if not sid:
        return JSONResponse(dict(ok=False, msg="還沒有組"), status_code=400)
    if b.get("light") is not None:
        REC["light"] = str(b["light"])[:30]
    meta = _jload(os.path.join(_sdir(sid), "meta.json"), {})
    meta.setdefault("marks", []).append(dict(t=round(time.time(), 2), text=str(b.get("text", ""))[:40], light=REC["light"]))
    _jsave(os.path.join(_sdir(sid), "meta.json"), meta)
    return dict(ok=True, marks=meta["marks"])


# ---------------------------------------------------------------- 瀏覽與標記
@router.get("/api/rec/sets")
async def rec_sets():
    out = [_set_summary(s) for s in sorted(os.listdir(ROOT), reverse=True) if os.path.isdir(os.path.join(ROOT, s)) and not s.startswith("_")]
    return dict(sets=out, classes=CLASSES, kinds=KINDS)


@router.get("/api/rec/set/{sid}")
async def rec_set(sid: str):
    lab = _jload(os.path.join(_sdir(sid), "labels.json"), {})
    fr = _frames(sid)
    for f in fr:
        l = lab.get(f["file"])
        f["reviewed"] = bool(l and l.get("reviewed")); f["nbox"] = len(l["boxes"]) if l else None
    return dict(meta=_jload(os.path.join(_sdir(sid), "meta.json"), {}), frames=fr, info=_set_summary(sid))


@router.get("/api/rec/img/{sid}/{fn}")
async def rec_img(sid: str, fn: str):
    p = os.path.join(_sdir(sid), os.path.basename(fn))
    return Response(open(p, "rb").read(), media_type="image/jpeg") if fn.endswith(".jpg") and os.path.exists(p) else Response(status_code=404)


def _label_of(sid, fn):
    lab = _jload(os.path.join(_sdir(sid), "labels.json"), {})
    if fn in lab:
        return dict(lab[fn])
    pre = _jload(os.path.join(_sdir(sid), "prelabel.json"), {})
    if fn in pre:                                        # v6 預標（retrain/tools/prelabel_captures.py）
        return dict(boxes=pre[fn], reviewed=False, source="v6")
    for f in _frames(sid):
        if f["file"] == fn:                              # 板上模型當下的框
            return dict(boxes=[d[:5] for d in f.get("dets", []) if d[5] >= PRE_CONF], reviewed=False, source="board")
    return dict(boxes=[], reviewed=False, source="none")


def _clean_boxes(boxes):
    out = []
    for b in boxes or []:
        try:
            c, cx, cy, w, h = int(b[0]), *(float(v) for v in b[1:5])
        except Exception:
            continue
        x0, y0, x1, y1 = max(0, cx - w / 2), max(0, cy - h / 2), min(1, cx + w / 2), min(1, cy + h / 2)
        if 0 <= c < len(CLASSES) and x1 - x0 > 0.003 and y1 - y0 > 0.003:
            out.append([c, round((x0 + x1) / 2, 5), round((y0 + y1) / 2, 5), round(x1 - x0, 5), round(y1 - y0, 5)])
    return out


@router.get("/api/rec/label/{sid}/{fn}")
async def rec_label_get(sid: str, fn: str):
    return _label_of(sid, fn)


@router.put("/api/rec/label/{sid}/{fn}")
async def rec_label_put(sid: str, fn: str, req: Request):
    b = await req.json()
    p = os.path.join(_sdir(sid), "labels.json"); lab = _jload(p, {})
    lab[fn] = dict(boxes=_clean_boxes(b.get("boxes")), reviewed=bool(b.get("reviewed", True)), source="human", t=round(time.time()))
    _jsave(p, lab)
    return dict(ok=True, label=lab[fn], info=_set_summary(sid))


@router.post("/api/rec/apply/{sid}/{fn}")
async def rec_apply(sid: str, fn: str):
    """這張的框套用到同一組、同一台板子的其他張（擺位沒動，只換燈光／連續錄製時用）"""
    p = os.path.join(_sdir(sid), "labels.json"); lab = _jload(p, {})
    src = lab.get(fn) or _label_of(sid, fn)
    fr = _frames(sid); me = next((f for f in fr if f["file"] == fn), None)
    if not me:
        return JSONResponse(dict(ok=False), status_code=404)
    n = 0
    for f in fr:
        if f["mac"] == me["mac"] and f["file"] != fn:
            lab[f["file"]] = dict(boxes=src["boxes"], reviewed=True, source=f"copied:{fn}", t=round(time.time())); n += 1
    lab[fn] = dict(boxes=src["boxes"], reviewed=True, source=src.get("source", "human"), t=round(time.time()))
    _jsave(p, lab)
    return dict(ok=True, n=n, info=_set_summary(sid))


@router.post("/api/rec/delete/{sid}/{fn}")
async def rec_delete(sid: str, fn: str):
    """刪掉一張（拍壞、有人手入鏡）：從清單拿掉並移到 _trash"""
    fr = _frames(sid); keep = [f for f in fr if f["file"] != fn]
    with open(os.path.join(_sdir(sid), "frames.jsonl"), "w", encoding="utf-8") as f:
        for r in keep:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    lab = _jload(os.path.join(_sdir(sid), "labels.json"), {}); lab.pop(fn, None); _jsave(os.path.join(_sdir(sid), "labels.json"), lab)
    src = os.path.join(_sdir(sid), os.path.basename(fn))
    if os.path.exists(src):
        os.makedirs(os.path.join(_sdir(sid), "_trash"), exist_ok=True); shutil.move(src, os.path.join(_sdir(sid), "_trash", os.path.basename(fn)))
    return dict(ok=True, info=_set_summary(sid))


@router.post("/api/rec/export")
async def rec_export():
    """已檢查的張數 → YOLO 資料集（images/ labels/），檔名前面加組 id；回傳張數、框數與路徑"""
    out = os.path.join(ROOT, "_export", time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(os.path.join(out, "images")); os.makedirs(os.path.join(out, "labels"))
    n = nb = 0; per = {c: 0 for c in CLASSES}; rows = []
    for sid in sorted(os.listdir(ROOT)):
        if sid.startswith("_") or not os.path.isdir(os.path.join(ROOT, sid)):
            continue
        lab = _jload(os.path.join(ROOT, sid, "labels.json"), {})
        meta = _jload(os.path.join(ROOT, sid, "meta.json"), {})
        for f in _frames(sid):
            l = lab.get(f["file"])
            if not l or not l.get("reviewed") or not os.path.exists(os.path.join(ROOT, sid, f["file"])):
                continue
            stem = f"{sid}__{f['file'][:-4]}"
            shutil.copy2(os.path.join(ROOT, sid, f["file"]), os.path.join(out, "images", stem + ".jpg"))
            with open(os.path.join(out, "labels", stem + ".txt"), "w", encoding="ascii", newline="\n") as fo:
                for c, cx, cy, w, h in l["boxes"]:
                    fo.write(f"{c} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n"); per[CLASSES[c]] += 1; nb += 1
            rows.append([stem, sid, meta.get("name", ""), meta.get("kind", ""), f.get("slot") or "", f.get("light", "")]); n += 1
    with open(os.path.join(out, "sources.csv"), "w", encoding="utf-8") as fo:
        fo.write("stem,set,name,kind,slot,light\n" + "".join(",".join(map(str, r)) + "\n" for r in rows))
    return dict(ok=True, path=out, images=n, boxes=nb, per_class=per)
