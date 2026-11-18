"""
在 Blender 裡直接排線（2026-11-18）：在已開啟的 fire_model.blend（場景 Assembly_Full）上，
放 18 塊 OLED（取自 GitHub model_oled_ceiling/fire_model_oled_through_hole.blend 的穿孔版 0.96 吋模組）、
切天花板長條孔、開麵包板座側窗，並拉出 72 條實體杜邦線（每條一個 curve，顏色＝腳位）。

用法（在 Blender 的 Python 環境執行；分步驟，避免一次跑太久）：
  g = dict(OLED_LIB=r"...\\oled_through_hole.blend", OUT=r"...\\輸出資料夾", STEP="all")   # STEP: cut / oled / wires / all
  exec(open(r"...\\blender_build_wiring.py", encoding="utf-8").read(), g)
也可以 headless：python blender_build_wiring.py <fire_model.blend> <oled_through_hole.blend> <輸出資料夾>

OLED 位置、畫面方向、分配、2F 角落外移量沿用 build_8hub_wiring.py（已檢查：鏡頭 0 像素、長孔實心、不壓牆）。
"""
import bpy, bmesh, os, sys, math, json, heapq
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

G = globals()
if "OLED_LIB" not in G:                       # headless
    bpy.ops.wm.open_mainfile(filepath=sys.argv[1]); OLED_LIB, OUT, STEP = sys.argv[2], sys.argv[3], "all"
os.makedirs(OUT, exist_ok=True)
sc = bpy.data.scenes["Assembly_Full"]
if bpy.context.window: bpy.context.window.scene = sc
Z = Vector((0, 0, 1)); PITCH = 150.0
D = {"N": (0, 1), "E": (1, 0), "S": (0, -1), "W": (-1, 0)}
ANG = {"E": 0.0, "N": 90.0, "W": 180.0, "S": -90.0}
PW, PH, PIN_ROW = 27.8, 27.3, 1.68
SLOT_U, SLOT_V = 11.4, 3.4
Z_DUP1, Z_WIRE, R_WIRE = 122.5, 118.4, 0.75
P0 = [
    dict(id="NW", J=(-1, 1), center=(-97.0, 100.0), up="E"), dict(id="NE", J=(1, 1), center=(100.0, 97.0), up="S"),
    dict(id="SE", J=(1, -1), center=(99.0, -101.0), up="S"), dict(id="SW", J=(-1, -1), center=(-100.0, -97.0), up="N"),
    dict(id="C", J=(0, 0), center=(0.0, 5.5), up="S"),
    dict(id="N", J=(0, 1), center=(0.0, 46.85), up="S"), dict(id="E", J=(1, 0), center=(46.85, 0.0), up="W"),
    dict(id="S", J=(0, -1), center=(0.0, -46.85), up="N"), dict(id="W", J=(-1, 0), center=(-46.85, 0.0), up="E"),
]
ASSIGN = {"NW": ("N", "Wire0", 0x3C, "side"), "N": ("N", "Wire1", 0x3C, "inner"), "NE": ("E", "Wire0", 0x3C, "side"),
          "E": ("E", "Wire1", 0x3C, "inner"), "SE": ("S", "Wire0", 0x3C, "side"), "S": ("S", "Wire1", 0x3C, "inner"),
          "C": ("S", "Wire1", 0x3D, "inner"), "SW": ("W", "Wire0", 0x3C, "side"), "W": ("W", "Wire1", 0x3C, "inner")}
FLOOR_SHIFT = {2: {"NW": (0.0, 1.5), "NE": (1.5, 0.0), "SE": (0.0, -0.5), "SW": (-1.75, 0.0)}}
PINS = ("GND", "VCC", "SCL", "SDA")
PIN_COLOR = {"GND": (0.03, 0.03, 0.03, 1), "VCC": (0.85, 0.08, 0.06, 1), "SCL": (0.95, 0.8, 0.05, 1), "SDA": (0.1, 0.65, 0.2, 1)}
BUS_PIN = {"Wire0": {"SDA": "Pin3", "SCL": "Pin4"}, "Wire1": {"SDA": "Pin0", "SCL": "Pin1"}}
WIN_Y, WIN_Z, WIN_CUT_IN, SEAT_HALF = (68.0, 87.0), (122.0, 129.0), 6.0, 29.5
ROT = {"N": Matrix.Rotation(0, 3, "Z"), "E": Matrix.Rotation(-math.pi / 2, 3, "Z"),
       "S": Matrix.Rotation(math.pi, 3, "Z"), "W": Matrix.Rotation(math.pi / 2, 3, "Z")}
def s2w(seat, x, y, z=0.0):
    v = ROT[seat] @ Vector((x, y, 0)); return Vector((v.x, v.y, z))

def placements():
    out = []
    for fl in (1, 2):
        for p in P0:
            q = dict(p); q["floor"] = fl; q["dz"] = (fl - 1) * PITCH
            sh = FLOOR_SHIFT.get(fl, {}).get(p["id"])
            if sh: q["center"] = (p["center"][0] + sh[0], p["center"][1] + sh[1])
            q["seat"], q["bus"], q["addr"], q["entry"] = ASSIGN[p["id"]]
            up = Vector((*D[q["up"]], 0)); right = Z.cross(up); c = Vector((*q["center"], 0))
            q["upv"], q["right"] = up, right
            q["slot"] = c + up * (PH / 2 - PIN_ROW)
            q["name"] = f"{fl}F_OLED_{p['id']}"
            out.append(q)
    return out
PL = placements()

def coll(name):
    c = bpy.data.collections.get(name)
    if not c: c = bpy.data.collections.new(name); sc.collection.children.link(c)
    return c
def mat(name, color):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name); m.diffuse_color = color
    m.use_nodes = True
    bs = m.node_tree.nodes.get("Principled BSDF")
    if bs: bs.inputs["Base Color"].default_value = color
    return m
def box_cutter(lo, hi):
    me = bpy.data.meshes.new("_cut"); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co = Vector(tuple(lo[i] if v.co[i] < 0 else hi[i] for i in range(3)))
    bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new("_cut", me); sc.collection.objects.link(ob); return ob
def apply_bool(target, cuts):
    for c in cuts:
        m = target.modifiers.new("cut", "BOOLEAN"); m.operation = "DIFFERENCE"; m.object = c; m.solver = "EXACT"
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(target.evaluated_get(dg)); target.modifiers.clear()
    old = target.data; target.data = me; bpy.data.meshes.remove(old)
    for c in cuts: bpy.data.objects.remove(c)
def nonmanifold(ob):
    bm = bmesh.new(); bm.from_mesh(ob.data); n = sum(1 for e in bm.edges if not e.is_manifold); bm.free(); return n

REPORT = os.path.join(OUT, "blender_build_report.json")
rep = json.load(open(REPORT, encoding="utf-8")) if os.path.exists(REPORT) else {}

# ---------- 1. 切孔：麵包板座側窗、天花板＋封孔板長條孔 ----------
def step_cut():
    if sc.get("wiring_cut_done"): return {"skipped": "already cut"}
    out = {}
    for fl in (1, 2):
        dz = (fl - 1) * PITCH
        for seat in "NESW":
            o = sc.objects[f"{fl}F_麵包版座_{seat}"]
            a = s2w(seat, -SEAT_HALF - 3, WIN_Y[0]); b = s2w(seat, -SEAT_HALF + WIN_CUT_IN, WIN_Y[1])
            apply_bool(o, [box_cutter((min(a.x, b.x), min(a.y, b.y), WIN_Z[0] + dz), (max(a.x, b.x), max(a.y, b.y), WIN_Z[1] + dz))])
            out[o.name] = nonmanifold(o)
        for nm in ("天花板", "天花板封孔板"):
            o = sc.objects[f"{fl}F_{nm}"]; cuts = []
            for q in [q for q in PL if q["floor"] == fl]:
                hx, hy = (SLOT_U / 2, SLOT_V / 2) if abs(q["right"].x) > 0.5 else (SLOT_V / 2, SLOT_U / 2)
                cuts.append(box_cutter((q["slot"].x - hx, q["slot"].y - hy, 100 + dz), (q["slot"].x + hx, q["slot"].y + hy, 121 + dz)))
            apply_bool(o, cuts); out[o.name] = nonmanifold(o)
    sc["wiring_cut_done"] = True
    return {"nonmanifold": out}

# ---------- 2. OLED 模組：複製 GitHub 穿孔版模組（NW 那塊當樣板） ----------
TEMPLATE_PARTS = ("玻璃", "顯示區", "PCB", "背面零件", "雙面膠", "排針塑膠座", "排針", "杜邦母座")
def step_oled():
    names = [f"1F_OLED穿孔_NW_{p}" for p in TEMPLATE_PARTS]
    with bpy.data.libraries.load(OLED_LIB, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in names]
    tmpl = {o.name.split("_")[-1]: o for o in dst.objects if o}
    assert len(tmpl) == len(TEMPLATE_PARTS), sorted(tmpl)
    c0 = Vector((-97.0, 100.0, 0)); a0 = ANG["E"]           # 樣板在 GitHub 檔裡的位置與方向（NW，排針朝東）
    C = coll("OLED_18塊")
    for q in PL:
        if q["name"] + "_PCB" in bpy.data.objects: continue
        M = (Matrix.Translation((q["center"][0], q["center"][1], q["dz"])) @ Matrix.Rotation(math.radians(ANG[q["up"]] - a0), 4, "Z")
             @ Matrix.Translation(-c0))
        for part, t in tmpl.items():
            o = t.copy(); o.data = t.data.copy(); o.name = f"{q['name']}_{part}"; o.matrix_world = M @ t.matrix_world
            C.objects.link(o)
    for t in tmpl.values(): bpy.data.objects.remove(t)
    return {"oleds": len(PL), "parts_each": len(TEMPLATE_PARTS)}

# ---------- 3. 繞線（封孔板頂面 1 mm 網格）＋ 72 條杜邦線 ----------
GX = list(range(-117, 118)); NG = len(GX)
GI = lambda v: (int(round(v[0])) + 117, int(round(v[1])) + 117)
def bvh_of(objs):
    dg = bpy.context.evaluated_depsgraph_get(); vs, fs = [], []
    for o in objs:
        me = o.evaluated_get(dg).to_mesh(); M = o.matrix_world; b = len(vs)
        vs += [M @ v.co for v in me.vertices]; fs += [tuple(b + i for i in f.vertices) for f in me.polygons]
    return BVHTree.FromPolygons(vs, fs)
def box_cells(cx, cy, hx, hy, grow):
    return [(i, j) for i, x in enumerate(GX) if abs(x - cx) <= hx + grow for j, y in enumerate(GX) if abs(y - cy) <= hy + grow]
def dilate(cells, r):
    out = set()
    for i, j in cells:
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if 0 <= i + di < NG and 0 <= j + dj < NG: out.add((i + di, j + dj))
    return out
def route(start, goals, blk, cost):
    si = GI(start); dist = {(si, -1): 0.0}; prev = {}; pq = [(0.0, si, -1)]; end = None
    DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
    while pq:
        d, c, k = heapq.heappop(pq)
        if d > dist.get((c, k), 1e18): continue
        if c in goals: end = (c, k); break
        for kk, (di, dj) in enumerate(DIRS):
            n = (c[0] + di, c[1] + dj)
            if not (0 <= n[0] < NG and 0 <= n[1] < NG): continue
            if n in blk and max(abs(n[0] - si[0]), abs(n[1] - si[1])) > 6: continue
            nd = d + cost(n) + (2.0 if k not in (-1, kk) else 0.0)
            if nd < dist.get((n, kk), 1e18): dist[(n, kk)] = nd; prev[(n, kk)] = (c, k); heapq.heappush(pq, (nd, n, kk))
    assert end is not None, f"no route from {tuple(start)}"
    cells = []; s_ = end
    while s_ is not None: cells.append(s_[0]); s_ = prev.get(s_)
    path = [(GX[i], GX[j]) for i, j in cells[::-1]]; simp = [path[0]]
    for k in range(1, len(path) - 1):
        a, b, c2 = simp[-1], path[k], path[k + 1]
        if (b[0] - a[0]) * (c2[1] - b[1]) != (b[1] - a[1]) * (c2[0] - b[0]): simp.append(b)
    if len(path) > 1: simp.append(path[-1])
    return cells[::-1], [Vector((x, y)) for x, y in simp]
INNER_GOAL = {"N": (0, 41.5, 15, 0.5), "E": (41.5, 0, 0.5, 15), "S": (0, -41.5, 15, 0.5), "W": (-41.5, 0, 0.5, 15)}
def side_goal(seat):
    c = s2w(seat, -SEAT_HALF - 5.0, sum(WIN_Y) / 2); along = (WIN_Y[1] - WIN_Y[0]) / 2 - 4
    return (c.x, c.y, 0.5, along) if seat in "NS" else (c.x, c.y, along, 0.5)

def offset_poly(pts2, off):
    """2D 折線往左平移 off（直角轉彎用 miter）"""
    out = []
    for k, p in enumerate(pts2):
        ns = []
        if k > 0: d = (p - pts2[k - 1]).normalized(); ns.append(Vector((-d.y, d.x)))
        if k < len(pts2) - 1: d = (pts2[k + 1] - p).normalized(); ns.append(Vector((-d.y, d.x)))
        n = sum(ns, Vector((0, 0))); n = n.normalized() if n.length > 1e-6 else ns[0]
        cosv = max(0.5, n.dot(ns[0])); out.append(p + n * (off / cosv))
    return out

def step_wires():
    C = coll("杜邦線_72條"); used = {}
    mats = {p: mat(f"杜邦線_{p}", PIN_COLOR[p]) for p in PINS}
    wires = []
    for fl in (1, 2):
        dz = (fl - 1) * PITCH
        ceil, lid, floor = sc.objects[f"{fl}F_天花板"], sc.objects[f"{fl}F_天花板封孔板"], sc.objects[f"{fl}F_樓層"]
        B_ceil, B_lid = bvh_of([ceil]), bvh_of([lid])
        obst = [o for o in sc.objects if o.type == "MESH" and o.name.startswith(f"{fl}F_") and o not in (ceil, lid, floor) and "OLED" not in o.name]
        B_obst = bvh_of(obst)
        blocked, plug, hole = set(), set(), set()
        for i, x in enumerate(GX):
            for j, y in enumerate(GX):
                h = B_obst.ray_cast(Vector((x, y, 105.0 + dz)), Z, 24.65)
                if h[0] is not None and h[0].z > 107.9 + dz: blocked.add((i, j))
                hl = B_lid.ray_cast(Vector((x, y, 100.0 + dz)), Z, 30); hc = B_ceil.ray_cast(Vector((x, y, 100.0 + dz)), Z, 18)
                if hl[0] is not None and hl[0].z < 109 + dz: plug.add((i, j))
                if (hc[0] is None or hc[0].z > 117.0 + dz) and (hl[0] is None or hl[0].z > 117.7 + dz): hole.add((i, j))
        base = dilate(blocked, 4) | dilate(hole, 2)
        PLf = [q for q in PL if q["floor"] == fl]
        slot_cells = {q["id"]: set(box_cells(q["slot"].x, q["slot"].y, *((SLOT_U / 2, SLOT_V / 2) if abs(q["right"].x) > 0.5 else (SLOT_V / 2, SLOT_U / 2)), 3)) for q in PLf}
        all_slots = set().union(*slot_cells.values())
        for q in sorted(PLf, key=lambda q: (q["entry"] != "inner", q["id"])):
            key = f"{fl}{q['seat']}{q['bus']}"
            def cost(c, key=key):
                k = 1.0; u = used.get(c)
                if u: k = 0.3 if key in u else k + 4.0
                return k + (30.0 if c in plug else 0.0)
            blk = base | (all_slots - slot_cells[q["id"]])
            box = INNER_GOAL[q["seat"]] if q["entry"] == "inner" else side_goal(q["seat"])
            goals = set(c for c in box_cells(*box, 0.5) if c not in blk)
            cells, path = route(q["slot"], goals, blk, cost)
            for c in dilate(cells, 4): used.setdefault(c, set()).add(key)
            q["path"] = path; q["plug_mm"] = sum(1 for c in cells if c in plug)
            # 座內目標：角落線從側窗進到 HUB 西排排針旁；十字臂、中心從朝中心窗口進到 HUB 東排（Wire1 腳位，示意）
            if q["entry"] == "side":
                win_out = s2w(q["seat"], -SEAT_HALF - 2, sum(WIN_Y) / 2); win_in = s2w(q["seat"], -SEAT_HALF + 7, sum(WIN_Y) / 2)
                tgt = s2w(q["seat"], -15.5, 74.0); zwin = sum(WIN_Z) / 2
            else:
                win_out = s2w(q["seat"], 6.0 if q["id"] != "C" else 10.0, 44.0); win_in = s2w(q["seat"], 8.0, 50.0)
                tgt = s2w(q["seat"], 15.5, 58.0 if q["id"] != "C" else 62.0); zwin = 128.0
            d0 = (path[1] - path[0]) if len(path) > 1 else Vector((1, 0))
            n0 = Vector((-d0.y, d0.x)).normalized()
            sgn = 1.0 if Vector((q["right"].x, q["right"].y)).dot(n0) >= 0 else -1.0   # 線排左右順序跟排針一致，不交叉
            for k, pin in enumerate(PINS):
                lane = sgn * (k - 1.5) * 1.6
                pin_xy = q["slot"] + q["right"] * ((k - 1.5) * 2.54)
                lp = offset_poly([Vector((pin_xy.x, pin_xy.y))] + path[1:] if len(path) > 1 else [Vector((pin_xy.x, pin_xy.y)), path[0]], lane)
                lp[0] = Vector((pin_xy.x, pin_xy.y))
                pts3 = [Vector((pin_xy.x, pin_xy.y, Z_DUP1 + dz)), Vector((pin_xy.x, pin_xy.y, Z_DUP1 + 5 + dz))]
                pts3 += [Vector((v.x, v.y, Z_WIRE + dz + R_WIRE)) for v in lp]
                along = (win_in - win_out).normalized(); side = Vector((-along.y, along.x, 0))
                pts3 += [win_out + side * lane + Vector((0, 0, zwin + dz)), win_in + side * lane + Vector((0, 0, zwin + dz)),
                         tgt + side * (lane * 1.6) + Vector((0, 0, 131.0 + dz))]
                L = sum((pts3[i + 1] - pts3[i]).length for i in range(len(pts3) - 1)) + 15.0
                cu = bpy.data.curves.new(f"{q['name']}_線_{pin}", "CURVE"); cu.dimensions = "3D"
                cu.bevel_depth = R_WIRE; cu.bevel_resolution = 2; cu.use_fill_caps = True
                sp = cu.splines.new("POLY"); sp.points.add(len(pts3) - 1)
                for i, v in enumerate(pts3): sp.points[i].co = (v.x, v.y, v.z, 1)
                cu.materials.append(mats[pin])
                ob = bpy.data.objects.new(f"{q['name']}_線_{pin}", cu); C.objects.link(ob)
                hub_end = {"GND": "GND（藍軌）", "VCC": "3V3（紅軌）"}.get(pin) or BUS_PIN[q["bus"]][pin]
                wires.append(dict(floor=fl, oled=q["id"], junction=(f"J({q['J'][0]},{q['J'][1]})" if fl == 1 else f"J2({q['J'][0]},{q['J'][1]})"),
                                  hub=f"{fl}{q['seat']}", bus=q["bus"], addr=hex(q["addr"]), pin=pin, hub_end=hub_end,
                                  entry=q["entry"], length_mm=round(L, 1), margin_mm=round(200 - L, 1), plug_mm=q["plug_mm"]))
    rep["wires"] = wires
    L = [w["length_mm"] for w in wires]
    return {"wires": len(wires), "min": min(L), "max": max(L), "over_200": sum(1 for x in L if x > 200)}

res = {}
if STEP in ("cut", "all"): res["cut"] = step_cut()
if STEP in ("oled", "all"): res["oled"] = step_oled()
if STEP in ("wires", "all"): res["wires"] = step_wires()
rep.setdefault("steps", {}).update(res)
json.dump(rep, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
RESULT = res
print(json.dumps(res, ensure_ascii=False))
