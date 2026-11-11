"""
邊中點 OLED 沿十字臂往中心 (0,0) 移動的可行性掃描（2026-11-10）。
  blender -b <fire_model.blend 的複本> --python arm_sweep.py -- <scratch 資料夾（含 derived*.npz）> <輸出 json>
對每支十字臂，顯示區中心從邊中點往中心每 1 mm 一格（橫向偏移 ±8 mm、4 個方向），檢查：
  - 模組：不碰鏡頭孔、牆、貫穿孔（可以從下方蓋住塞子）；不碰中心那塊 OLED（四周 0.6 mm）
  - 長孔＋0.8 mm：實心天花板或塞子（比照 B 方案），不碰排線溝、塞子與孔之間的縫、中心長孔
  - 孔上方：到第一個既有零件要放得下母座＋線彎（z 127.5）；TCA9548A（−30,18）的位置另外標出（可搬）
  - 鏡頭：576×320 逐像素（evac.py 等立體角魚眼），8 台
"""
import bpy, sys, math, json
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

A = sys.argv[sys.argv.index("--") + 1:]; S, OUTJ = A[0], A[1]
d = np.load(S + "/derived.npz"); d2 = np.load(S + "/derived2.npz")
xs = d["xs"]; N = len(xs); R = 0.5; X0 = xs[0]
bot, hole, st, free, wallany = d["bot"], d["hole"], d2["solid_top"], d2["free"], d2["wallany"]
ribs = np.isclose(bot, 105.2, atol=0.05); plug = np.isclose(bot, 108.2, atol=0.05); groove = np.isclose(st, 112.0, atol=0.05)
lens = np.zeros((N, N), bool)
for (x0, x1, y0, y1) in [(-11.5, 11.5, 81, 100), (-11.5, 11.5, -100, -81), (81, 100, -11.5, 11.5), (-100, -81, -11.5, 11.5)]:
    lens |= (xs[:, None] >= x0) & (xs[:, None] <= x1) & (xs[None, :] >= y0) & (xs[None, :] <= y1)
small = (hole & ~lens) | np.isclose(bot, 116.0, atol=0.05)
def dil(m, mm):
    k = int(round(mm / R)); out = m.copy()
    for dx in range(-k, k + 1):
        for dy in range(-k, k + 1):
            if dx * dx + dy * dy <= k * k: out |= np.roll(np.roll(m, dx, 0), dy, 1)
    return out
def box_mask(x0, x1, y0, y1): return (xs[:, None] >= x0) & (xs[:, None] <= x1) & (xs[None, :] >= y0) & (xs[None, :] <= y1)
CENTER_MOD = box_mask(-13.9, 13.9, -8.15, 19.15)          # 中心 OLED（定稿位置）
CENTER_SLOT = box_mask(-5.7 - 3, 5.7 + 3, -6.47 - 1.7 - 3, -6.47 + 1.7 + 3)
MUX = box_mask(-30 - 15.25, -30 + 15.25, 18 - 8.9, 18 + 8.9)
bad_fp = dil(lens, 0.6) | dil(wallany | ribs, 0.4) | (hole & ~small) | dil(CENTER_MOD, 0.6)
st_eff = np.where(plug, 117.6, st)
bad_slot = dil((np.isnan(st) & ~plug) | groove | (~np.isnan(st) & (np.nan_to_num(st) < 114.9)), 0.8) | CENTER_SLOT
def sat(m):
    s = np.zeros((N + 1, N + 1)); s[1:, 1:] = np.cumsum(np.cumsum(m.astype(float), 0), 1); return s
SF, SSl, SP, SM = sat(bad_fp), sat(bad_slot), sat(plug), sat(MUX)
def q(T, x0, x1, y0, y1):
    i0 = int(np.ceil((x0 - X0) / R - 1e-6)); i1 = int(np.floor((x1 - X0) / R + 1e-6)); j0 = int(np.ceil((y0 - X0) / R - 1e-6)); j1 = int(np.floor((y1 - X0) / R + 1e-6))
    if i0 < 0 or j0 < 0 or i1 >= N or j1 >= N: return 1e9
    return T[i1 + 1, j1 + 1] - T[i0, j1 + 1] - T[i1 + 1, j0] + T[i0, j0]
def headroom(x0, x1, y0, y1):
    i0 = int(np.ceil((x0 - X0) / R)); i1 = int(np.floor((x1 - X0) / R)); j0 = int(np.ceil((y0 - X0) / R)); j1 = int(np.floor((y1 - X0) / R))
    return float((np.nan_to_num(st_eff[i0:i1 + 1, j0:j1 + 1]) + free[i0:i1 + 1, j0:j1 + 1]).min())
NEED = 127.5
HU, HV = 27.8 / 2, 27.3 / 2; SLU, SLV = 11.4 / 2, 3.4 / 2; PIN = HV - 1.68; ACY = 11.5 - HV
DIRS = {"N": (0, 1), "E": (1, 0), "S": (0, -1), "W": (-1, 0)}

# ---------- 逐像素鏡頭檢查 ----------
sc = bpy.data.scenes["Assembly_Full"]; dg = bpy.context.evaluated_depsgraph_get()
vs_, fs_ = [], []
for o in sc.objects:
    if o.type == "MESH" and o.visible_get() and (o.name.startswith("1F_") or o.name.startswith("2F_")) and "Lens" not in o.name and "HUB8735" not in o.name:
        me = o.evaluated_get(dg).to_mesh(); M = o.matrix_world; b = len(vs_)
        vs_ += [M @ v.co for v in me.vertices]; fs_ += [tuple(b + i for i in f.vertices) for f in me.polygons]
B_scene = BVHTree.FromPolygons(vs_, fs_)
IW, IH, FL, SWD = 576, 320, 2.9821, 5.6; SC = IW / SWD
CAMS = []
for fl, dz in (("1F", 0.0), ("2F", 150.0)):
    for cn, rz in (("N", 0.0), ("E", -90.0), ("S", 180.0), ("W", 90.0)):
        Rz = Matrix.Rotation(math.radians(rz), 3, "Z"); CAMS.append((fl + cn, Rz @ Vector((0, 92, 111 + dz)), Rz @ Matrix.Rotation(math.radians(-18), 3, "X")))
def in_corridor(x, y):
    ring = (abs(abs(x) - 99) <= 18 and abs(y) <= 117) or (abs(abs(y) - 99) <= 18 and abs(x) <= 117)
    cross = (abs(x) <= 21 and abs(y) <= 81) or (abs(y) <= 21 and abs(x) <= 81)
    return ring or cross
def pixel_check(cx, cy, hx, hy):
    corners = [Vector((cx + sx * hx, cy + sy * hy, z)) for sx in (-1, 1) for sy in (-1, 1) for z in (103.0, 108.0)]
    Bm = BVHTree.FromPolygons(corners, [(0, 2, 6, 4), (1, 5, 7, 3), (0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6)])
    res = {}
    for name, P0, Rc in CAMS:
        Rt = Rc.transposed(); uv = []
        for P3 in corners:
            qv = Rt @ (P3 - P0); th = math.acos(max(-1, min(1, -qv.z / qv.length)))
            if th > math.radians(89): continue
            r = 2 * FL * math.sin(th / 2); ph = math.atan2(qv.y, qv.x); uv.append((IW / 2 + r * math.cos(ph) * SC, IH / 2 - r * math.sin(ph) * SC))
        if len(uv) < 8: continue
        u0, u1 = max(0, int(min(t[0] for t in uv)) - 1), min(IW - 1, int(max(t[0] for t in uv)) + 1)
        v0, v1 = max(0, int(min(t[1] for t in uv)) - 1), min(IH - 1, int(max(t[1] for t in uv)) + 1)
        if u0 > u1 or v0 > v1: continue
        n = 0; floor_px = 0; box = [9999, 9999, -1, -1]
        for u in range(u0, u1 + 1):
            for v in range(v0, v1 + 1):
                xs_, ys_ = (u + 0.5 - IW / 2) / SC, (IH / 2 - v - 0.5) / SC; rr = math.hypot(xs_, ys_)
                th = 2 * math.asin(min(1.0, rr / (2 * FL))); ph = math.atan2(ys_, xs_)
                dv = (Rc @ Vector((math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), -math.cos(th)))).normalized()
                hm = Bm.ray_cast(P0, dv, 800)
                if hm[0] is None: continue
                hs = B_scene.ray_cast(P0, dv, 800)
                if hs[0] is not None and hs[3] < hm[3]: continue
                n += 1; box = [min(box[0], u), min(box[1], v), max(box[2], u), max(box[3], v)]
                if hs[0] is not None and abs(hs[0].z - 8.0) < 0.6 and in_corridor(hs[0].x, hs[0].y): floor_px += 1
        if n: res[name] = dict(px=n, box=box, floor_px=floor_px)
    return res

ARMS = {"N": ((0, 99), (0, -1), (1, 0)), "E": ((99, 0), (-1, 0), (0, 1)), "S": ((0, -99), (0, 1), (1, 0)), "W": ((-99, 0), (1, 0), (0, 1))}
out = {}
for arm, (J, a, b) in ARMS.items():
    rows = []
    for s_ in range(0, 100):
        best = None; reasons = set()
        for l in sorted(range(-8, 9), key=abs):
            for up, (ux, uy) in DIRS.items():
                ax, ay = J[0] + a[0] * s_ + b[0] * l, J[1] + a[1] * s_ + b[1] * l
                cx, cy = ax - ux * ACY, ay - uy * ACY
                hx, hy = (HV, HU) if ux else (HU, HV)
                if q(SF, cx - hx, cx + hx, cy - hy, cy + hy): reasons.add("模組碰到鏡頭孔／牆／中心 OLED"); continue
                px, py = cx + ux * PIN, cy + uy * PIN; sx, sy = (SLV, SLU) if ux else (SLU, SLV)
                if q(SSl, px - sx, px + sx, py - sy, py + sy): reasons.add("長孔碰到排線溝／孔／中心長孔"); continue
                if headroom(px - sx - 1.5, px + sx + 1.5, py - sy - 1.5, py + sy + 1.5) < NEED: reasons.add("長孔上方是麵包板座（沒有母座空間）"); continue
                best = dict(s=s_, lateral=l, up=up, pcb=[cx, cy], slot=[round(px, 2), round(py, 2)], hx=hx, hy=hy,
                            slot_in_plug=bool(q(SP, px - sx, px + sx, py - sy, py + sy)), near_mux=bool(q(SM, px - sx - 6, px + sx + 6, py - sy - 6, py + sy + 6)))
                break
            if best: break
        dist_c = math.hypot(J[0] + a[0] * s_, J[1] + a[1] * s_)
        if best:
            best["cams"] = pixel_check(best["pcb"][0], best["pcb"][1], best["hx"], best["hy"])
            best["dist_center"] = round(dist_c, 1)
            rows.append(best)
        else:
            rows.append(dict(s=s_, dist_center=round(dist_c, 1), feasible=False, reasons=sorted(reasons)))
        r = rows[-1]
        print("ARM", arm, "s", s_, "center_dist", r["dist_center"], ("OK up %s lat %d slot %s plug %s mux %s cams %s" % (r["up"], r["lateral"], r["slot"], r["slot_in_plug"], r["near_mux"],
              {k: (v["px"], v["box"], v["floor_px"]) for k, v in r["cams"].items()})) if "up" in r else ("NO " + "；".join(r["reasons"])), flush=True)
    out[arm] = rows
json.dump(out, open(OUTJ, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
