"""Run the decision layer over every scenario step.
mode 'det': YOLO detections on the rendered camera images (the real pipeline)
mode 'gt' : hand-written ground truth (for previewing before the model is trained)"""
import sys, os, json, math, copy
import evac as E, states as S

STEPS = [
    dict(t="00:00", note="平常狀態，全部暢通", cams_off=[]),
    dict(t="00:30", note="一樓東側起火冒煙", cams_off=[]),
    dict(t="01:00", note="煙擴散；一樓東出口前櫃子倒下", cams_off=[]),
    dict(t="01:30", note="二樓北側走廊箱子散落、西側瓦礫", cams_off=[]),
    dict(t="02:00", note="一樓南側走廊被封鎖（閘門）", cams_off=[]),
    dict(t="02:30", note="一樓東側鏡頭故障，沿用最後資訊", cams_off=[(1, "E")]),
]

PEOPLE0 = [
    dict(id="p1", name="避難者 A", role="evacuee", node=(2, 1, 1)),
    dict(id="p2", name="避難者 B", role="evacuee", node=(2, -1, 0)),
    dict(id="p3", name="避難者 C", role="evacuee", node=(1, 1, -1)),
    dict(id="p4", name="避難者 D", role="evacuee", node=(1, 0, 1)),
    dict(id="f1", name="消防員 1", role="firefighter", node=(1, -1, -1)),
    dict(id="b1", name="訪客", role="bystander", node=(1, -1, 1)),
]


def coverage():
    cov = {}
    for fl in E.FLOORS:
        for seg in E.segments(fl):
            (ax, ay), (bx, by) = E.jpos(fl, seg[0]), E.jpos(fl, seg[1])
            for c in E.CAMS:
                n = 0
                for t in [i / 8 for i in range(1, 8)]:
                    P = (ax + t * (bx - ax), ay + t * (by - ay), 8 + (fl - 1) * E.PITCH)
                    u, v = E.project(fl, c, P)
                    p, R = E.cam_pose(fl, c)
                    q = R.T @ (__import__("numpy").array(P) - p)
                    if 0 <= u < E.IMG_W and 0 <= v < E.IMG_H and q[2] < 0:
                        n += 1
                if n >= 3:
                    cov.setdefault(E.seg_name(fl, seg), set()).add((fl, c))
    return cov


def gt_state(i):
    st = E.fuse({})
    def seg(fl, a, b):
        return st[E.seg_name(fl, (a, b))]
    if i >= 1:
        for k, v in {(1, (0, 0), (1, 0)): 0.9, (1, (1, 0), (1, 1)): 0.4, (1, (0, 0), (0, 1)): 0.3}.items():
            seg(*k)["smoke"] = v * min(1, 0.4 + 0.25 * i)
    if i >= 2:
        s = seg(1, (1, 0), (1, 1)); s["rate"] = 0.8; s["items"].append(("cabinet", 0.8))
        seg(1, (0, -1), (0, 0))["smoke"] = 0.3; seg(1, (1, -1), (1, 0))["smoke"] = 0.5
    if i >= 3:
        s = seg(2, (0, 1), (1, 1)); s["rate"] = 0.55; s["items"].append(("boxes", 0.55))
        s = seg(2, (-1, 0), (0, 0)); s["rate"] = 0.7; s["items"].append(("rubble", 0.7))
    if i >= 4:
        s = seg(1, (-1, -1), (0, -1)); s["gate"] = True; s["rate"] = 1.0; s["items"].append(("gate", 1.0))
    return st


def move_people(people, leds):
    out = []
    for p in people:
        p = dict(p); fl, i, j = p["node"]
        d = leds.get((fl, i, j), ("X", None))[0]
        if p["role"] == "evacuee" and not p.get("out"):
            step = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}.get(d)
            if step:
                ni, nj = i + step[0], j + step[1]
                if abs(ni) <= 1 and abs(nj) <= 1:
                    p["node"] = (fl, ni, nj)
            elif d == "DOWN":
                p["node"] = (fl - 1, i, j)
        out.append(p)
    return out


def people_json(people, leds):
    res = []
    for p in people:
        fl, i, j = p["node"]; c = E.FLOORS[fl]["ringc"]
        d = leds.get((fl, i, j), ("X", None))[0]
        res.append(dict(id=p["id"], name=p["name"], role=p["role"], floor=fl, x=i * c + (hash(p["id"]) % 9 - 4),
                        y=j * c + (hash(p["id"][::-1]) % 9 - 4), dir=d, trapped=(d == "X" and p["role"] == "evacuee")))
    return res


def main(mode, outdir, weights=None):
    det = None
    if mode == "det":
        import detect_wrap as D
        D.load(weights); det = D
    cov = coverage()
    prev = None; people = [dict(p) for p in PEOPLE0]; seq = []; last_dets = {}; fire0 = None
    for i, stp in enumerate(STEPS):
        sd = os.path.join(outdir, f"step{i}")
        online = {(fl, c) for fl in E.FLOORS for c in E.CAMS} - set(stp["cams_off"])
        dets = {}
        stale = set()
        if mode == "det":
            for (fl, c) in sorted(online):
                p = os.path.join(sd, f"F{fl}_{c}.png")
                if os.path.exists(p):
                    dets[(fl, c)] = det.detect(p)
            for k_, v_ in last_dets.items():      # a camera that went offline keeps its last report
                if k_ not in online:
                    dets[k_] = v_; stale.add(k_)
            last_dets.update({k_: v_ for k_, v_ in dets.items() if k_ not in stale})
            st = E.fuse({k_: v_ for k_, v_ in dets.items() if k_ not in stale})
            if stale:
                st_old = E.fuse({k_: v_ for k_, v_ in dets.items() if k_ in stale})
                for k_, s_ in st.items():
                    o_ = st_old[k_]
                    if o_["rate"] > 0 or o_["gate"] or o_["smoke"] > 0:
                        s_["rate"] = max(s_["rate"], o_["rate"]); s_["gate"] = s_["gate"] or o_["gate"]
                        s_["smoke"] = max(s_["smoke"], o_["smoke"]); s_["items"] += o_["items"]; s_["unknown"] = True
        else:
            st = gt_state(i)
        if prev:   # segments no online camera can see keep their last known state
            for k, s in st.items():
                if not (cov.get(k, set()) & online):
                    for f in ("rate", "gate", "smoke", "items"):
                        s[f] = copy.deepcopy(prev[k][f])
                    s["unknown"] = True
        leds, dist = E.plan(st)
        pj = people_json(people, leds)
        js = S.to_json(stp, st, leds, online, people=pj)
        if js["fire"] and not fire0:
            fire0 = js["fire"]
        if fire0:                                  # the fire origin is where smoke was first seen
            js["fire"] = dict(fire0, conf=max(fire0["conf"], js["fire"]["conf"] if js["fire"] else 0))
        js["dets"] = {f"{k[0]}{k[1]}": v for k, v in dets.items() if k not in stale}
        json.dump(js, open(os.path.join(sd, "state.json"), "w"), ensure_ascii=False)
        json.dump(js["leds"], open(os.path.join(sd, "leds.json"), "w"))
        seq.append(js)
        prev = st
        people = move_people(people, leds)
    json.dump(seq, open(os.path.join(outdir, f"sequence_{mode}.json"), "w"), ensure_ascii=False)
    return seq


if __name__ == "__main__":
    seq = main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    for s in seq:
        print(s["t"], s["note"], {k: v for k, v in s["leds"].items() if v != "X"} if False else "", "fire:", s["fire"])
        for fl in (2, 1):
            print("  F%d" % fl, " | ".join(" ".join(f"{s['leds'][f'{fl},{i},{j}']:>4}" for i in (-1, 0, 1)) for j in (1, 0, -1)))
