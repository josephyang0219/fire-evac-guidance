"""Smoke test of the running server (app/server.py) over plain HTTP.

python server_smoke_test.py [base_url]        default http://127.0.0.1:8765, prints a markdown report

For each scenario the script turns the junction_check layout into YOLO boxes (projected through the real
camera model), POSTs them as the four 1F HUBs, and compares the server's "junctions" with
  (a) the same boxes run through evac in-process (fuse -> fire estimate -> plan)   -> must match
  (b) the table in junction_check_output.md (hand-set segment values)            -> reported
"""
import sys, json, time, re, os, urllib.request
import evac as E, states as ST, junction_check as J

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
HUBS = ["1E", "1N", "1S", "1W"]
CLS = {n: k for k, n in enumerate(E.CLASSES)}


def http(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read()
        return r.status, raw


def box_for(name, seg, fl=1, t=0.5, strength=1.0):
    """a YOLO box on some 1F camera that fuse() puts on `seg`; returns (cam, box) or None"""
    (ax, ay), (bx, by) = E.jpos(fl, seg[0]), E.jpos(fl, seg[1])
    x, y = ax + t * (bx - ax), ay + t * (by - ay)
    hw = E.seg_hw(fl, seg)
    ux, uy = (bx - ax) / 99.0, (by - ay) / 99.0          # along the corridor
    nx, ny = -uy, ux                                       # across
    for cam in E.CAMS:
        try:
            if name == "smoke":
                pts = [(x + s * 25 * ux + q * 0.8 * hw * nx, y + s * 25 * uy + q * 0.8 * hw * ny, z)
                       for s in (-1, 1) for q in (-1, 1) for z in (30, 60)]
            elif name == "gate":
                pts = [(x + q * hw * nx, y + q * hw * ny, z) for q in (-1, 1) for z in (8, 60)]
            else:                                          # obstacle across `strength` of the corridor width
                w = strength * hw
                pts = [(x + q * w * nx, y + q * w * ny, z) for q in (-1, 1) for z in (8, 8 + 2 * E.HALF_H[name])]
            uv = [E.project(fl, cam, p) for p in pts]
        except ValueError:
            continue
        us, vs = [u for u, _ in uv], [v for _, v in uv]
        x0, x1, y0, y1 = max(0, min(us)), min(E.IMG_W, max(us)), max(0, min(vs)), min(E.IMG_H, max(vs))
        if x1 - x0 < 4 or y1 - y0 < 4:                   # clipped to the frame; fuse() below decides if it lands right
            continue
        w, h = (x1 - x0) / E.IMG_W, (y1 - y0) / E.IMG_H
        conf = min(0.99, strength / (0.5 + 4 * w * h)) if name == "smoke" else 0.9   # smoke = conf * (0.5 + 4wh) in fuse()
        b = [CLS[name], (x0 + x1) / 2 / E.IMG_W, (y0 + y1) / 2 / E.IMG_H, w, h, round(conf, 3)]
        st = E.fuse({(fl, cam): [tuple(b)]})
        s = st[E.seg_name(fl, seg)]
        if (name == "smoke" and s["smoke"] > 0.2) or (name == "gate" and s["gate"]) or (name not in ("smoke", "gate") and s["rate"] > 0):
            return cam, b
    return None


# scenario = (junction_check function index, title, [(class, seg, strength)])
# strength: smoke = target smoke value (same numbers as junction_check), obstacle = share of the corridor width
SCENARIOS = [
    (1, "平常狀態，全部暢通", []),
    (6, "西出口閘門關閉＋東南側冒煙", [("gate", ((-1, -1), (-1, 0)), 1), ("smoke", ((0, -1), (1, -1)), 0.6), ("smoke", ((1, -1), (1, 0)), 0.3)]),
    (3, "東側起火＋東出口北段櫃子倒下",
     [("smoke", ((0, 0), (1, 0)), 0.9), ("smoke", ((1, -1), (1, 0)), 0.5), ("smoke", ((0, -1), (0, 0)), 0.3),
      ("cabinet", ((1, 0), (1, 1)), 0.9)]),
    (8, "兩個出口都被封住", [("gate", ((-1, -1), (-1, 0)), 1), ("gate", ((1, 0), (1, 1)), 1)]),
]


def expected_from_table(k):
    txt = open(os.path.join(os.path.dirname(__file__), "junction_check_output.md"), encoding="utf-8").read()
    part = txt.split(f"## 情境 {k}：")[1].split("## 情境")[0]
    return dict(re.findall(r"\| (J\([-0-9,]+\)) \S+ \| (\S+) \|", part))


def main():
    out = [f"# 伺服器實測（{time.strftime('%Y-%m-%d %H:%M')}，{BASE}）", ""]
    ok = True

    st, raw = http("GET", "/")
    page_ok = st == 200 and "<title>避難指引中控台</title>".encode() in raw[:500]
    out.append(f"- `GET /` → {st}，{len(raw)} bytes，{'中控台頁面（title 正確）' if page_ok else '不是預期的中控台頁面'}")
    ok &= page_ok

    st, raw = http("GET", "/api/junctions")
    js = json.loads(raw)
    out.append(f"- `GET /api/junctions`（還沒有任何板子回報）→ {st}，{len(js['junctions'])} 筆：" +
               " ".join(f"{o['id']}={o['dir']}" for o in js["junctions"]))
    ok &= st == 200 and len(js["junctions"]) == 9

    st, raw = http("POST", "/api/dev/AABBCCDDEEFF/detections", {"seq": 1, "fps": 5, "fw": "smoke", "dets": []})
    js = json.loads(raw)
    out.append(f"- `POST /api/dev/AABBCCDDEEFF/detections`（未指派的板子）→ {st}，keys={sorted(js)}，"
               f"slot={js['slot']!r}，leds={js['leds']}，junctions {len(js['junctions'])} 筆")
    ok &= st == 200 and len(js["junctions"]) == 9 and "leds" in js

    st, raw = http("GET", "/api/hub/1E/leds")
    js = json.loads(raw)
    out.append(f"- `GET /api/hub/1E/leds` → {st}，leds={js['leds']}，junctions {len(js['junctions'])} 筆")
    ok &= st == 200 and len(js["leds"]) == 3 and len(js["junctions"]) == 9
    out.append("")

    seq = 10
    for k, title, items in SCENARIOS:
        dets = {h: [] for h in HUBS}
        for name, seg, strength in items:
            r = box_for(name, seg, strength=strength)
            if r is None:
                out.append(f"（{title}：{name} {seg} 找不到能看到的鏡頭）"); ok = False; continue
            cam, b = r
            dets[f"1{cam}"].append(b)
        last = None
        for h in HUBS[1:] + HUBS[:1]:                       # 1E last, so its reply (old leds = 3 junctions) is the final state
            seq += 1
            st, raw = http("POST", f"/api/hub/{h}/detections", {"seq": seq, "fps": 5, "ts": time.time(), "dets": dets[h]})
            last = json.loads(raw)
        _, raw = http("GET", "/api/junctions")
        got_get = {o["id"]: o["dir"] for o in json.loads(raw)["junctions"]}
        got = {o["id"]: o["dir"] for o in last["junctions"]}

        # (a) same boxes in-process
        stl = E.fuse({(1, h[1]): [tuple(b) for b in v] for h, v in dets.items()})
        leds, _ = E.plan(stl, fire=ST.fire_estimate(stl))
        local = {o["id"]: o["dir"] for o in E.junctions(leds)}
        table = expected_from_table(k)
        same_local = got == local == got_get
        same_table = got == table
        ok &= same_local and len(got) == 9

        out.append(f"## {title}（對照 junction_check 情境 {k}）")
        out.append("")
        out.append("送出的偵測框（類別(cx,cy,w,h,conf)）：" + ("無" if not any(dets.values()) else "；".join(
            f"{h}: " + ", ".join(f"{E.CLASSES[b[0]]}({b[1]:.2f},{b[2]:.2f},{b[3]:.2f},{b[4]:.2f},{b[5]:.2f})" for b in v) for h, v in dets.items() if v)))
        fused = [f"{kk[3:]} " + ("閘門" if s["gate"] else "") + (f"阻擋{s['rate']:.2f} " if s["rate"] and not s["gate"] else "") +
                 (f"煙{s['smoke']:.2f}" if s["smoke"] else "") for kk, s in stl.items() if s["floor"] == 1 and (s["rate"] or s["smoke"])]
        out.append("伺服器融合後的走廊：" + ("全部暢通" if not fused else "、".join(fused)))
        out.append(f"1E 回應的舊 `leds` 欄位（HUB_LEDS 1E = J(1,0) J(1,1) J(0,0)）：{last['leds']}")
        ok &= last["leds"] == [local[E.junction_id(ij)] for ij in ((1, 0), (1, 1), (0, 0))]
        out.append("")
        out.append("| 路口 | 伺服器（POST 回應） | GET /api/junctions | 本機 evac 同樣輸入 | junction_check 表 |")
        out.append("|---|---|---|---|---|")
        for o in E.JUNCTION_ORDER:
            i = E.junction_id(o)
            mark = "" if got[i] == table.get(i) else " ≠"
            out.append(f"| {i} {J.NAMES[o]} | {got[i]} | {got_get[i]} | {local[i]} | {table.get(i)}{mark} |")
        out.append("")
        out.append(f"伺服器＝本機 evac：{'一致' if same_local else '**不一致**'}；伺服器＝junction_check 表：" +
                   ("一致" if same_table else f"有 {sum(got[i] != table.get(i) for i in got)} 個路口不同（輸入是偵測框，煙與阻擋的數值跟表中手設的不完全一樣）"))
        errs = J.check(stl, leds, ST.fire_estimate(stl))
        out.append("junction_check 規則檢查（用伺服器融合後的狀態）：" + ("通過" if not errs else "失敗：" + "；".join(errs)))
        ok &= not errs
        out.append("")

    out.append(f"**總結：{'全部通過' if ok else '有失敗項目'}**")
    print("\n".join(out))
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
