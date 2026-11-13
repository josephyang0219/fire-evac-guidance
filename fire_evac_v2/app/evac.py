"""Fire-evacuation decision layer for the miniature model.

detections (per camera, YOLO boxes) -> corridor-segment states (obstacle rate, gate, smoke)
-> evacuation graph (2 floors, 2 stairs, exits on floor 1) -> next-hop direction for every junction LED.
"""
import math, heapq
import numpy as np

CLASSES = ["cabinet", "boxes", "furniture", "rubble", "gate", "smoke"]
F_LENS, SW, SH = 2.9821, 5.6, 3.15          # equisolid fisheye, HFOV 112 / DFOV 130
IMG_W, IMG_H = 640, 360
TILT = 18.0
CAMS = {"N": 0.0, "W": 90.0, "E": -90.0, "S": 180.0}
FLOOR_TOP = 8.0          # walking surface height inside a tray
PITCH = 150.0            # floor-to-floor
FLOORS = {               # floor index -> geometry
    1: dict(kind="new", ringc=99.0, ring_hw=18.0, cross_hw=21.0),   # the ground floor (smaller rooms, exits)
    2: dict(kind="old", ringc=102.0, ring_hw=15.0, cross_hw=15.0),
}
STAIRS = {"W": (-1, 1), "E": (1, -1)}        # tower -> junction (i,j) it opens onto, same on both floors
EXITS = {"EXIT_E": ((1, 0), (1, 1)), "EXIT_W": ((-1, 0), (-1, -1))}   # on floor 1, middle of that segment
BLOCK_RATE = 0.55        # a segment more blocked than this is treated as impassable
HALF_H = {"cabinet": 12.0, "boxes": 8.0, "furniture": 9.0, "rubble": 6.0, "gate": 47.0}   # typical half height (mm); gate block 94 mm tall (2026-11-13)


def rot(rz):
    c, s = math.cos(math.radians(rz)), math.sin(math.radians(rz))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def rotx(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def cam_pose(floor, cam):
    rz = CAMS[cam]
    R = rot(rz) @ rotx(-TILT)
    p = rot(rz) @ np.array([0.0, 92.0, 111.0])
    p[2] += (floor - 1) * PITCH
    return p, R


def pix_ray(u, v):
    s = IMG_W / SW
    xs, ys = (u - IMG_W / 2) / s, (IMG_H / 2 - v) / s
    r = math.hypot(xs, ys)
    th = 2 * math.asin(min(1.0, r / (2 * F_LENS)))
    ph = math.atan2(ys, xs)
    return np.array([math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), -math.cos(th)])


def project(floor, cam, P):
    p, R = cam_pose(floor, cam)
    q = R.T @ (np.asarray(P, float) - p)
    th = math.acos(max(-1, min(1, -q[2] / np.linalg.norm(q))))
    r = 2 * F_LENS * math.sin(th / 2); ph = math.atan2(q[1], q[0])
    s = IMG_W / SW
    return IMG_W / 2 + r * math.cos(ph) * s, IMG_H / 2 - r * math.sin(ph) * s


def unproject(floor, cam, u, v, z_local):
    p, R = cam_pose(floor, cam)
    d = R @ pix_ray(u, v)
    zw = z_local + (floor - 1) * PITCH
    if d[2] >= -1e-6:
        return None
    t = (zw - p[2]) / d[2]
    w = p + t * d
    return w[0], w[1]


# ---------------- floor graph ----------------
def jpos(floor, ij):
    c = FLOORS[floor]["ringc"]
    return ij[0] * c, ij[1] * c


def segments(floor):
    segs = []
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for di, dj in ((1, 0), (0, 1)):
                a, b = (i, j), (i + di, j + dj)
                if abs(b[0]) <= 1 and abs(b[1]) <= 1:
                    segs.append((a, b))
    return segs   # 12


def seg_hw(floor, seg):
    F = FLOORS[floor]
    a, b = seg
    horiz = a[1] == b[1]
    on_ring = (abs(a[1]) == 1) if horiz else (abs(a[0]) == 1)
    return F["ring_hw"] if on_ring else F["cross_hw"]


def locate(floor, x, y):
    """corridor segment a floor point belongs to (nearest centre line within the corridor width)."""
    best, bd = None, 1e9
    for seg in segments(floor):
        (ax, ay), (bx, by) = jpos(floor, seg[0]), jpos(floor, seg[1])
        vx, vy = bx - ax, by - ay; L2 = vx * vx + vy * vy
        t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
        d = math.hypot(x - (ax + t * vx), y - (ay + t * vy))
        if d <= seg_hw(floor, seg) + 4 and d < bd:
            best, bd = seg, d
    return best


def seg_name(floor, seg):
    return f"F{floor}:{seg[0][0]}{seg[0][1]}-{seg[1][0]}{seg[1][1]}"


# ---------------- detections -> segment state ----------------
def fuse(dets_by_cam):
    """dets_by_cam: {(floor, cam): [(cls, cx, cy, w, h, conf), ...]} normalised YOLO boxes.
    returns {seg_name: dict(rate, gate, smoke, items)}"""
    st = {}
    for fl in FLOORS:
        for seg in segments(fl):
            st[seg_name(fl, seg)] = dict(rate=0.0, gate=False, smoke=0.0, items=[], floor=fl, seg=seg)
    for (fl, cam), dets in dets_by_cam.items():
        for (c, cx, cy, w, h, conf) in dets:
            x0, x1 = (cx - w / 2) * IMG_W, (cx + w / 2) * IMG_W
            yb = (cy + h / 2) * IMG_H
            name = CLASSES[c]
            if name == "smoke":
                for (u, v, zl) in ((cx * IMG_W, cy * IMG_H, 60.0), (cx * IMG_W, yb, 30.0), (x0, cy * IMG_H, 60.0), (x1, cy * IMG_H, 60.0)):
                    q = unproject(fl, cam, u, v, zl)
                    if q:
                        seg = locate(fl, *q)
                        if seg:
                            s = st[seg_name(fl, seg)]
                            s["smoke"] = max(s["smoke"], min(1.0, conf * (0.5 + 4 * w * h)))
                continue
            pc = None if (name == "gate" or yb > IMG_H * 0.97) else unproject(fl, cam, cx * IMG_W, yb, FLOOR_TOP)
            seg = locate(fl, *pc) if pc else None
            if not seg:   # bottom edge hidden or off the corridor: use the box centre at the object's typical half height
                pc = unproject(fl, cam, cx * IMG_W, cy * IMG_H, FLOOR_TOP + HALF_H[name])
                seg = locate(fl, *pc) if pc else None
            if not seg:
                continue
            s = st[seg_name(fl, seg)]
            if name == "gate":
                s["gate"] = True; s["rate"] = 1.0; s["items"].append(("gate", conf)); continue
            pl, pr = unproject(fl, cam, x0, yb, FLOOR_TOP), unproject(fl, cam, x1, yb, FLOOR_TOP)
            width = math.dist(pl, pr) if (pl and pr) else 15.0
            (ax, ay), (bx, by) = jpos(fl, seg[0]), jpos(fl, seg[1])
            ux, uy = (bx - ax), (by - ay); n = math.hypot(ux, uy); ux, uy = ux / n, uy / n
            if pl and pr:     # only the part across the corridor matters
                width = abs((pr[0] - pl[0]) * (-uy) + (pr[1] - pl[1]) * ux) + 0.35 * abs((pr[0] - pl[0]) * ux + (pr[1] - pl[1]) * uy)
            r = min(1.0, width / (2 * seg_hw(fl, seg)))
            s["rate"] = 1 - (1 - s["rate"]) * (1 - r)
            s["items"].append((name, round(r, 2)))
    return st


# ---------------- routing ----------------
W_OBS, W_SMOKE, W_PRED, W_FIRE = 2.5, 8.0, 4.0, 5.0


def predict(state, fire=None):
    """smoke-spread prediction and fire proximity per segment (same model as the app):
    pred = max(own smoke, 0.65 x neighbour smoke, 0.45 x if the neighbour is blocked);
    fire_near = 1 at the estimated origin, 0 at 90 mm away (same floor only)."""
    for k, s in state.items():
        fl, seg = s["floor"], s["seg"]
        p = s["smoke"]
        for o in state.values():
            if o is s or o["floor"] != fl or not (set(o["seg"]) & set(seg)):
                continue
            blk = o["gate"] or o["rate"] >= BLOCK_RATE
            p = max(p, o["smoke"] * (0.45 if blk else 0.65))
        s["pred"] = min(1.0, p)
        (ax, ay), (bx, by) = jpos(fl, seg[0]), jpos(fl, seg[1])
        if fire and fire.get("floor") == fl:
            d = math.hypot((ax + bx) / 2 - fire["x"], (ay + by) / 2 - fire["y"])
            s["fire_near"] = max(0.0, 1 - d / 90)
        else:
            s["fire_near"] = 0.0


def build_graph(state, stairs_open=("W", "E"), fire=None):
    predict(state, fire)
    G = {}
    def add(a, b, w):
        G.setdefault(a, []).append((b, w)); G.setdefault(b, []).append((a, w))
    for k, s in state.items():
        fl, seg = s["floor"], s["seg"]
        (ax, ay), (bx, by) = jpos(fl, seg[0]), jpos(fl, seg[1])
        L = math.hypot(bx - ax, by - ay)
        if s["gate"] or s["rate"] >= BLOCK_RATE:
            continue
        m = (1 + W_OBS * s["rate"]) * (1 + W_SMOKE * s["smoke"] + W_PRED * max(0.0, s["pred"] - s["smoke"]) + W_FIRE * s["fire_near"])
        if s["smoke"] >= 0.85:
            m *= 3
        w = L * m
        a, b = (fl,) + seg[0], (fl,) + seg[1]
        ex = [e for e, sg in EXITS.items() if fl == 1 and set(sg) == set(seg)]
        if ex:
            add(a, ex[0], w / 2); add(b, ex[0], w / 2)
        else:
            add(a, b, w)
    for t, ij in STAIRS.items():
        if t in stairs_open:     # the search runs from the exits outward, so an edge u->v is walked v->u
            G.setdefault((1,) + ij, []).append(((2,) + ij, 60.0))     # walking down: normal
            G.setdefault((2,) + ij, []).append(((1,) + ij, 600.0))    # walking up into the fire floor: last resort
    return G


def plan(state, stairs_open=("W", "E"), fire=None):
    G = build_graph(state, stairs_open, fire)
    dist, nxt = {}, {}
    pq = [(0.0, e, None) for e in EXITS]
    while pq:
        d, u, via = heapq.heappop(pq)
        if u in dist:
            continue
        dist[u] = d; nxt[u] = via
        for v, w in G.get(u, []):
            if v not in dist:
                heapq.heappush(pq, (d + w, v, u))
    leds = {}
    for fl in FLOORS:
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                n = (fl, i, j)
                h = nxt.get(n)
                if h is None:
                    leds[n] = ("X", None)
                elif isinstance(h, str):
                    a, b = EXITS[h]
                    o = b if (i, j) == a else a
                    leds[n] = (direction((i, j), o), h)
                elif h[0] != fl:
                    leds[n] = ("DOWN" if h[0] < fl else "UP", h)
                else:
                    leds[n] = (direction((i, j), h[1:]), h)
    return leds, dist


# ---------------- per-junction output (one OLED per 1F junction) ----------------
JUNCTION_ORDER = [(i, j) for j in (1, 0, -1) for i in (-1, 0, 1)]   # NW N NE / W C E / SW S SE
DIRS = ("N", "S", "E", "W", "UP", "DOWN", "X")


def junction_id(ij):
    return f"J({ij[0]},{ij[1]})"


def junctions(leds, floor=1):
    """[{id:"J(-1,1)", dir:"N|S|E|W|UP|DOWN|X"}, ...] for the 9 junctions of one floor, NW..SE"""
    return [dict(id=junction_id(ij), dir=leds.get((floor,) + ij, ("X", None))[0]) for ij in JUNCTION_ORDER]


def direction(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    return {(1, 0): "E", (-1, 0): "W", (0, 1): "N", (0, -1): "S"}[(dx, dy)]
