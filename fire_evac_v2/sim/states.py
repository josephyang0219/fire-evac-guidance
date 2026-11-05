"""Turn fused segment states + routing into the JSON the app / animation consume."""
import math, json
import evac as E


def seg_mid(fl, seg):
    (ax, ay), (bx, by) = E.jpos(fl, seg[0]), E.jpos(fl, seg[1])
    return (ax + bx) / 2, (ay + by) / 2


def fire_estimate(st):
    best = None
    for fl in E.FLOORS:
        tot = 0; sx = sy = 0
        for k, s in st.items():
            if s["floor"] != fl or s["smoke"] <= 0.05:
                continue
            x, y = seg_mid(fl, s["seg"]); w = s["smoke"] ** 2
            tot += w; sx += w * x; sy += w * y
        if tot > 0 and (best is None or tot > best[3]):
            best = (fl, sx / tot, sy / tot, tot)
    if not best:
        return None
    return dict(floor=best[0], x=round(best[1], 1), y=round(best[2], 1), conf=round(min(1.0, best[3]), 2))


def to_json(step, st, leds, cams_online, people=None, net=None):
    segs = []
    for k, s in st.items():
        risk = min(1.0, 0.65 * s["smoke"] + 0.45 * s["rate"] + (0.3 if s["gate"] else 0))
        segs.append(dict(id=k, floor=s["floor"], a=list(s["seg"][0]), b=list(s["seg"][1]), rate=round(s["rate"], 2),
                         gate=s["gate"], smoke=round(s["smoke"], 2), risk=round(risk, 2), items=s["items"],
                         unknown=s.get("unknown", False), hw=E.seg_hw(s["floor"], s["seg"])))
    cams = []
    for fl in E.FLOORS:
        for c in E.CAMS:
            p, _ = E.cam_pose(fl, c)
            cams.append(dict(id=f"{fl}{c}", floor=fl, x=round(p[0], 1), y=round(p[1], 1), online=(fl, c) in cams_online))
    return dict(t=step["t"], note=step["note"],
                floors={str(f): dict(ringc=v["ringc"], ring_hw=v["ring_hw"], cross_hw=v["cross_hw"]) for f, v in E.FLOORS.items()},
                segments=segs,
                leds={f"{k[0]},{k[1]},{k[2]}": v[0] for k, v in leds.items()},
                exits={k: dict(floor=1, a=list(v[0]), b=list(v[1])) for k, v in E.EXITS.items()},
                stairs={k: list(v) for k, v in E.STAIRS.items()},
                cams=cams, fire=fire_estimate(st), people=people or [], net=net or {})
