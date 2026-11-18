"""
8 台鏡頭 HUB 直接驅動 18 塊天花板 OLED（1F、2F 各 9 塊）的接線設計與檢查（2026-11-18）

取代方案 D（3 台只驅動 OLED 的 H5/H6/H7）。每台鏡頭 HUB 最多 3 塊 OLED：
  - 角落 OLED  → Wire  0x3C（Pin3 SDA / Pin4 SCL），經麵包板座「側窗」（本腳本新開）進座
  - 十字臂 OLED → Wire1 0x3C（Pin0 SDA / Pin1 SCL），經麵包板座朝中心的既有窗口進座
  - 中心 OLED  → S 座 HUB 的 Wire1 0x3D（要改焊），經 S 座既有窗口進座
每塊 OLED 4 條 20 cm 母－公杜邦線（母頭插 OLED 排針、公頭插麵包板），共 18 × 4 = 72 條。

OLED 位置、長條孔、畫面方向沿用 model_oled_ceiling/（穿孔＋雙面膠，9 塊）。2F 天花板、封孔板、麵包板座、鏡頭
與 1F 逐點相同（只高 150 mm，見 check 輸出），所以 2F 用同一組位置，再用 2F 樓層盒檢查模組下方沒有牆。

用法（參數路徑只能用英文；原檔不會被寫入）：
  python build_8hub_wiring.py <fire_model.blend> <輸出資料夾>        # 用 pip 的 bpy 5.2
  blender -b <fire_model.blend> --python build_8hub_wiring.py -- <輸出資料夾>
"""
import bpy, bmesh, sys, os, math, json, heapq
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

if "--" in sys.argv:
    OUT = sys.argv[sys.argv.index("--") + 1]
else:
    bpy.ops.wm.open_mainfile(filepath=sys.argv[1]); OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)
SRC = bpy.data.filepath
assert os.path.basename(SRC) == "fire_model.blend" or True
sc = bpy.data.scenes["Assembly_Full"]; bpy.context.window_manager  # noqa
Z = Vector((0, 0, 1))
PITCH = 150.0                               # 層距

# ---------- OLED 規格與位置（沿用 model_oled_ceiling/build_through_hole.py） ----------
PW, PH = 27.8, 27.3
PIN_ROW = 1.68
SLOT_U, SLOT_V = 11.4, 3.4
Z_DUP1 = 122.5                              # 杜邦母座頂（相對 1F）
Z_WIRE = 118.4                              # 線排在封孔板頂面上的線芯高度
D = {"N": (0, 1), "E": (1, 0), "S": (0, -1), "W": (-1, 0)}
# up = 畫面上方（排針那一側）在世界座標的方向
P0 = [
    dict(id="NW", J=(-1, 1), center=(-97.0, 100.0), up="E", kind="corner"),
    dict(id="NE", J=(1, 1), center=(100.0, 97.0), up="S", kind="corner"),
    dict(id="SE", J=(1, -1), center=(99.0, -101.0), up="S", kind="corner"),
    dict(id="SW", J=(-1, -1), center=(-100.0, -97.0), up="N", kind="corner"),
    dict(id="C", J=(0, 0), center=(0.0, 5.5), up="S", kind="center"),
    dict(id="N", J=(0, 1), center=(0.0, 46.85), up="S", kind="arm"),
    dict(id="E", J=(1, 0), center=(46.85, 0.0), up="W", kind="arm"),
    dict(id="S", J=(0, -1), center=(0.0, -46.85), up="N", kind="arm"),
    dict(id="W", J=(-1, 0), center=(-46.85, 0.0), up="E", kind="arm"),
]
# 分配：每座 HUB 接「自己那支十字臂＋順時針那個角落」；S 座另外接中心 → 3＋2＋2＋2
ASSIGN = {
    "NW": ("N", "Wire0", 0x3C, "side"), "N": ("N", "Wire1", 0x3C, "inner"),
    "NE": ("E", "Wire0", 0x3C, "side"), "E": ("E", "Wire1", 0x3C, "inner"),
    "SE": ("S", "Wire0", 0x3C, "side"), "S": ("S", "Wire1", 0x3C, "inner"), "C": ("S", "Wire1", 0x3D, "inner"),
    "SW": ("W", "Wire0", 0x3C, "side"), "W": ("W", "Wire1", 0x3C, "inner"),
}
BUS_PINS = {"Wire0": ("Pin3", "Pin4"), "Wire1": ("Pin0", "Pin1")}      # (SDA, SCL)
OLED_PINS = ("GND", "VCC", "SCL", "SDA")                               # OLED 排針順序（從下方看、排針在上，由左到右）
WIRE_COLOR = {"GND": "黑", "VCC": "紅", "SCL": "黃", "SDA": "綠"}
WIRE_LEN = 200.0                                                       # 20 cm 母－公杜邦線

# ---------- 麵包板座側窗（本次修改）：N 座的西牆，其他座是同一個零件轉 90° ----------
# 座內：麵包板是倒掛的（靠中心那端最高，頂面 y 70 處 z 142.9、往外降到 y 140 處 z 120），HUB 插在麵包板下面、
# 鏡頭朝下；HUB 排針在 y 54.5～91.4、z 124.6～138.7。HUB 與天花板之間、排針外側有一層空間（z 約 118～130），
# 側窗就開在這層：對著 HUB 排針那一段，窗底高於封孔板頂面，窗頂低於麵包板下緣。
WIN_Y = (68.0, 87.0)        # N 座座標，沿座長方向（離中心）；y > 88 起麵包板下緣已低到 z 127
WIN_Z = (122.0, 129.0)      # 相對 1F；牆下段厚 5 mm（x −29.5～−24.5），座底板在 y 66 一帶高到 z 約 120
WIN_CUT_IN = 6.0            # 從外牆面往內切 6 mm（牆厚 5 mm）
SEAT_HALF = 29.5            # 座外寬一半；牆內面約 27
ROT = {"N": Matrix.Rotation(0, 3, "Z"), "E": Matrix.Rotation(-math.pi / 2, 3, "Z"),
       "S": Matrix.Rotation(math.pi, 3, "Z"), "W": Matrix.Rotation(math.pi / 2, 3, "Z")}
def seat_to_world(seat, x, y):
    v = ROT[seat] @ Vector((x, y, 0)); return Vector((v.x, v.y))

def bvh_of(objs, dg):
    vs, fs = [], []
    for o in objs:
        me = o.evaluated_get(dg).to_mesh(); M = o.matrix_world; b = len(vs)
        vs += [M @ v.co for v in me.vertices]; fs += [tuple(b + i for i in f.vertices) for f in me.polygons]
    return BVHTree.FromPolygons(vs, fs)

def cutter(name, verts_min, verts_max):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector(tuple(verts_min[i] if v.co[i] < 0 else verts_max[i] for i in range(3)))
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob); return ob

def apply_bool(target, cut):
    m = target.modifiers.new("cut", "BOOLEAN"); m.operation = "DIFFERENCE"; m.object = cut; m.solver = "EXACT"
    bpy.context.view_layer.objects.active = target
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(target.evaluated_get(dg)); target.modifiers.clear()
    old = target.data; target.data = me; bpy.data.meshes.remove(old)

def nonmanifold(ob):
    bm = bmesh.new(); bm.from_mesh(ob.data); n = sum(1 for e in bm.edges if not e.is_manifold); bm.free(); return n

report = {"source": SRC, "floors": {}, "checks": {}}
coll = bpy.data.collections.new("OLED_8HUB接線"); sc.collection.children.link(coll)
def link_new(ob):
    for c in list(ob.users_collection): c.objects.unlink(ob)
    coll.objects.link(ob)

# ---------- 1. 兩層幾何是否相同 ----------
def pts(n, dz=0.0):
    o = sc.objects[n]; M = o.matrix_world
    return sorted((round(v.x, 2), round(v.y, 2), round(v.z - dz, 2)) for v in (M @ x.co for x in o.data.vertices))
same = {n: pts("1F_" + n) == pts("2F_" + n, PITCH) for n in ("天花板", "天花板封孔板", "麵包版座_N", "麵包版座_E", "麵包版座_S", "麵包版座_W",
                                                          "HUB8735_Lens_N", "HUB8735_Headers_N", "Breadboard_N")}
report["checks"]["2F_same_as_1F"] = same

# ---------- 2. 開側窗（8 座），檢查窗內淨空 ----------
dg = bpy.context.evaluated_depsgraph_get()
win_info = {}
for fl in (1, 2):
    dz = (fl - 1) * PITCH
    for seat in "NESW":
        o = sc.objects[f"{fl}F_麵包版座_{seat}"]
        a = seat_to_world(seat, -SEAT_HALF - 3, WIN_Y[0]); b = seat_to_world(seat, -SEAT_HALF + WIN_CUT_IN, WIN_Y[1])   # 只穿側牆
        lo = (min(a.x, b.x), min(a.y, b.y), WIN_Z[0] + dz); hi = (max(a.x, b.x), max(a.y, b.y), WIN_Z[1] + dz)
        c = cutter(f"_win_{fl}{seat}", lo, hi)
        apply_bool(o, c); bpy.data.objects.remove(c)
        win_info[f"{fl}{seat}"] = dict(lo=[round(v, 2) for v in lo], hi=[round(v, 2) for v in hi], nonmanifold=nonmanifold(o))
dg = bpy.context.evaluated_depsgraph_get()
# 窗內淨空：從牆外往座內打水平射線，窗口範圍內第一個打到的東西要離牆面 ≥ 8 mm（線要轉進去）
for fl in (1, 2):
    dz = (fl - 1) * PITCH
    inner = [o for o in sc.objects if o.type == "MESH" and o.name.startswith(f"{fl}F_") and ("HUB8735" in o.name or "Breadboard" in o.name or "麵包版座" in o.name)]
    B = bvh_of(inner, dg)
    for seat in "NESW":
        nmin = 99.0; hits = 0; dists = []
        for y in [WIN_Y[0] + 1 + k * 2 for k in range(int((WIN_Y[1] - WIN_Y[0] - 2) / 2) + 1)]:
            for z in [WIN_Z[0] + 1 + k * 2 for k in range(int((WIN_Z[1] - WIN_Z[0] - 2) / 2) + 1)]:
                p0 = seat_to_world(seat, -SEAT_HALF - 5, y); p1 = seat_to_world(seat, 0, y); dirv = (p1 - p0).normalized()
                h = B.ray_cast(Vector((p0.x, p0.y, z + dz)), Vector((dirv.x, dirv.y, 0)), 60)
                if h[0] is not None:
                    dist_in = h[3] - 5 - 0.0          # 從牆外面（x = −29.5）算起
                    nmin = min(nmin, dist_in); hits += 1; dists.append(dist_in)
        win_info[f"{fl}{seat}"]["first_obstacle_mm_from_outer_face"] = round(nmin, 1)
        win_info[f"{fl}{seat}"]["clear_ge_10mm"] = f"{sum(1 for d_ in dists if d_ >= 10)}/{len(dists)}"
report["checks"]["seat_windows"] = win_info

# ---------- 3. 每層：位置檢查、繞線 ----------
GX = list(range(-117, 118)); NG = len(GX)
GI = lambda v: (int(round(v[0])) + 117, int(round(v[1])) + 117)
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))

def box_cells(cx, cy, hx, hy, grow):
    return [(i, j) for i, x in enumerate(GX) if abs(x - cx) <= hx + grow for j, y in enumerate(GX) if abs(y - cy) <= hy + grow]
def dilate(cells, r):
    out = set()
    for i, j in cells:
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if 0 <= i + di < NG and 0 <= j + dj < NG: out.add((i + di, j + dj))
    return out

def make_floor(fl):
    dz = (fl - 1) * PITCH
    ceil, lid, floor = sc.objects[f"{fl}F_天花板"], sc.objects[f"{fl}F_天花板封孔板"], sc.objects[f"{fl}F_樓層"]
    B_ceil, B_lid, B_floor = bvh_of([ceil], dg), bvh_of([lid], dg), bvh_of([floor], dg)
    obst = [o for o in sc.objects if o.type == "MESH" and o.name.startswith(f"{fl}F_") and o not in (ceil, lid, floor)]
    obst += [o for o in sc.objects if o.type == "MESH" and o.name.startswith("樓梯塔")]
    B_obst = bvh_of(obst, dg)
    occ = [o for o in sc.objects if o.type == "MESH" and o.name.startswith(f"{fl}F_") and "HUB8735" not in o.name]
    B_occ = bvh_of(occ, dg)
    blocked, plug, hole = set(), set(), set()
    for i, x in enumerate(GX):
        for j, y in enumerate(GX):
            h = B_obst.ray_cast(Vector((x, y, 105.0 + dz)), Z, 24.65)
            if h[0] is not None and h[0].z > 107.9 + dz: blocked.add((i, j))
            hl = B_lid.ray_cast(Vector((x, y, 100.0 + dz)), Z, 30); hc = B_ceil.ray_cast(Vector((x, y, 100.0 + dz)), Z, 18)
            if hl[0] is not None and hl[0].z < 109 + dz: plug.add((i, j))
            if (hc[0] is None or hc[0].z > 117.0 + dz) and (hl[0] is None or hl[0].z > 117.7 + dz): hole.add((i, j))
    return dict(dz=dz, B_occ=B_occ, B_floor=B_floor, B_ceil=B_ceil, B_lid=B_lid, B_obst=B_obst, blocked=blocked, plug=plug, hole=hole)

def oled_frame(p):
    up = Vector((*D[p["up"]], 0)); right = Z.cross(up); c = Vector((*p["center"], 0))
    W = lambda uu, vv: c + uu * right + vv * up
    return up, right, W

def route(start, goals, blk, cost):
    si = GI(start); dist = {(si, -1): 0.0}; prev = {}; pq = [(0.0, si, -1)]; end = None
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
    return cells[::-1]
def simplify(cells):
    path = [(GX[i], GX[j]) for i, j in cells]; simp = [path[0]]
    for k in range(1, len(path) - 1):
        a, b, c2 = simp[-1], path[k], path[k + 1]
        if (b[0] - a[0]) * (c2[1] - b[1]) != (b[1] - a[1]) * (c2[0] - b[0]): simp.append(b)
    if len(path) > 1: simp.append(path[-1])
    return simp
def plen(pts_):
    return sum((Vector(pts_[k + 1]) - Vector(pts_[k])).length for k in range(len(pts_) - 1))

# 麵包板座的進線目標（線排中心停在窗外），以及窗口位置
INNER_GOAL = {"N": (0, 41.5, 15, 0.5), "E": (41.5, 0, 0.5, 15), "S": (0, -41.5, 15, 0.5), "W": (-41.5, 0, 0.5, 15)}
def side_goal(seat):
    c = seat_to_world(seat, -SEAT_HALF - 5.0, sum(WIN_Y) / 2); along = (WIN_Y[1] - WIN_Y[0]) / 2 - 4
    return (c.x, c.y, 0.5, along) if seat in "NS" else (c.x, c.y, along, 0.5)
def goal_cells(box, blk):
    cx, cy, hx, hy = box
    return set(c for c in box_cells(cx, cy, hx, hy, 0.5) if c not in blk)

# HUB 排針兩排（模型示意）：取每排兩端點，座內走線長取「窗口中心 → 最遠那排最遠一端」當保守值
def header_rows(fl, seat):
    o = sc.objects[f"{fl}F_HUB8735_Headers_{seat}"]; M = o.matrix_world
    vs = [M @ v.co for v in o.data.vertices]
    rows = {}
    for v in vs:
        loc = ROT[seat].transposed() @ Vector((v.x, v.y, 0))
        key = "W" if loc.x < 0 else "E"; rows.setdefault(key, []).append(Vector((loc.x, loc.y, v.z)))
    out = {}
    for k, r in rows.items():
        ys = [q.y for q in r]; zs = [q.z for q in r]; xm = sum(q.x for q in r) / len(r)
        out[k] = [(xm, min(ys), min(zs)), (xm, max(ys), max(zs))]     # 粗略兩端
    return out

# 2F 的房間塊比 1F 大（四角延伸到 ±88，1F 是 ±85.5），1F 的角落位置會讓模組壓到 2F 牆頂 0.65～4.65 mm。
# 2F 角落改用 search_2f_corners.py 搜出的最小移位（0.25 mm 網格、±6 mm 內，模組外擴 0.6 mm 不壓到高過 z 98 的牆、
# 長孔外擴 0.8 mm 從 108.2 到 117.6 連續實心）；長孔跟著移，所以 2F 天花板要用本資料夾的 2F 版 STL。
FLOOR_SHIFT = {2: {"NW": (0.0, 1.5), "NE": (1.5, 0.0), "SE": (0.0, -0.5), "SW": (-1.75, 0.0)}}

# 鏡頭：PS5268 等立體角魚眼 f = 2.98 mm、576×320（16:9），水平半視角 56°；位置與傾角同 model_oled_ceiling 的檢查
F_MM, PX_PER_MM = 2.98, 288.0 / (2 * 2.98 * math.sin(math.radians(28.0)))
CAMS = {"N": 0.0, "W": 90.0, "E": -90.0, "S": 180.0}
def cams_of(fl):
    dz = (fl - 1) * PITCH; out = []
    for cn, rz in CAMS.items():
        Rz = Matrix.Rotation(math.radians(rz), 3, "Z")
        pos = Rz @ Vector((0, 92, 111 + dz)); fwd = (Rz @ Matrix.Rotation(math.radians(-18), 3, "X") @ Vector((0, 0, -1))).normalized()
        right = (Rz @ Vector((1, 0, 0))).normalized(); upv = right.cross(fwd).normalized()
        out.append((f"{fl}F{cn}", pos, fwd, right, upv))
    return out
def pixel(cam, q):
    _, pos, fwd, right, upv = cam; v = q - pos; d = v.normalized()
    th = math.acos(max(-1.0, min(1.0, d.dot(fwd))))
    if th > math.radians(89.9): return None
    r = 2 * F_MM * math.sin(th / 2) * PX_PER_MM
    lat = Vector((d.dot(right), d.dot(upv))); 
    if lat.length < 1e-9: return (288, 160)
    lat.normalize(); u, w = 288 + r * lat.x, 160 - r * lat.y
    return (int(u), int(w)) if 0 <= u < 576 and 0 <= w < 320 else None

floors = {}
for fl in (1, 2):
    F = make_floor(fl); dz = F["dz"]
    P = [dict(p) for p in P0]
    for p in P:
        sh = FLOOR_SHIFT.get(fl, {}).get(p["id"])
        if sh: p["center"] = (p["center"][0] + sh[0], p["center"][1] + sh[1]); p["shift"] = sh
        p["floor"] = fl; p["oid"] = f"{fl}F-{p['id']}"
        p["seat"], p["bus"], p["addr"], p["entry"] = ASSIGN[p["id"]]
        up, right, W = oled_frame(p); p["W"] = W
        p["slot"] = W(0, PH / 2 - PIN_ROW)
        # 位置檢查：模組外框 0.6 mm 內，下方沒有牆（2F 樓層盒不同，要重查）
        wall = 0
        for k in range(15):
            for m in range(15):
                q = W(-PW / 2 - 0.6 + (PW + 1.2) * k / 14, -PH / 2 - 0.6 + (PH + 1.2) * m / 14)
                z0, hits = -1.0 + dz, []
                while True:
                    h = F["B_floor"].ray_cast(Vector((q.x, q.y, z0)), Z, 200)
                    if h[0] is None: break
                    hits.append(h[0].z); z0 = h[0].z + 1e-3
                # 只算高到天花板附近（z > 98）的牆；2F 角落有高 6～42 mm 的低矮構件，離 OLED 還有 60 mm 以上，不算
                if any(hits[i + 1] > 98 + dz and hits[i] < 107.95 + dz for i in range(0, len(hits) - 1, 2)): wall += 1
        p["wall_below_samples"] = wall
        # 長條孔（外擴 0.8 mm）要落在實心處：角落與中心＝天花板 108～116＋封孔板頂板 116～117.6；十字臂＝封孔板塞子 108.2～117.6
        def ivs(B, x, y):
            z0, hs = 100.0 + dz, []
            while True:
                h = B.ray_cast(Vector((x, y, z0)), Z, 40)
                if h[0] is None: break
                hs.append(round(h[0].z - dz, 1)); z0 = h[0].z + 1e-3
            return [(hs[i], hs[i + 1]) for i in range(0, len(hs) - 1, 2)]
        long_x = abs(Z.cross(Vector((*D[p["up"]], 0))).x) > 0.5
        hx, hy = ((SLOT_U / 2, SLOT_V / 2) if long_x else (SLOT_V / 2, SLOT_U / 2))
        badh = 0; nh = 0
        for k in range(13):
            for m in range(7):
                x = p["slot"].x - hx - 0.8 + (2 * hx + 1.6) * k / 12; y = p["slot"].y - hy - 0.8 + (2 * hy + 1.6) * m / 6
                ci, li = ivs(F["B_ceil"], x, y), ivs(F["B_lid"], x, y); nh += 1
                iv = sorted(ci + li); cover = 108.2; ok_ = True        # 合併後要從 108.2 連續實心到 117.6（中間不能有縫）
                for a_, b_ in iv:
                    if a_ > cover + 0.05: ok_ = False; break
                    cover = max(cover, b_)
                solid = ok_ and cover >= 117.55
                badh += 0 if solid else 1
        p["hole_bad_samples"] = f"{badh}/{nh}"
        # 鏡頭：模組外殼底面與側面取樣，投影到同層 4 台鏡頭的 576×320 畫面，沒被擋住的算可見像素
        samples = [W(-PW / 2 + PW * k / 10, -PH / 2 + PH * m / 10) for k in range(11) for m in range(11)]
        pts3 = [Vector((q.x, q.y, 103.0 + dz)) for q in samples]
        for zz in (103.5, 104.75, 106.0):
            pts3 += [Vector((q.x, q.y, zz + dz)) for q in samples if abs((q - W(0, 0)).x) > PW / 2 - 0.1 or abs((q - W(0, 0)).y) > PH / 2 - 0.1]
        vis = {}
        for cam in cams_of(fl):
            seen = set()
            for q in pts3:
                px_ = pixel(cam, q)
                if px_ is None: continue
                v = q - cam[1]; h = F["B_occ"].ray_cast(cam[1], v.normalized(), v.length - 0.3)
                if h[0] is None: seen.add(px_)
            vis[cam[0]] = len(seen)
        p["camera_visible_px"] = vis
    slot_cells = {p["id"]: set(box_cells(p["slot"].x, p["slot"].y, *((SLOT_U / 2, SLOT_V / 2) if abs(Vector((*D[p["up"]], 0)).cross(Z).x) > 0.5 else (SLOT_V / 2, SLOT_U / 2)), 3)) for p in P}
    all_slots = set().union(*slot_cells.values())
    base_block = dilate(F["blocked"], 4) | dilate(F["hole"], 2)
    used = {}
    def mark(cells, key):
        for c in dilate(cells, 4):
            d_ = used.setdefault(c, {}); d_[key] = d_.get(key, 0) + 1
    order = sorted(P, key=lambda p: (p["entry"] != "inner", p["id"]))     # 先繞短的（進朝中心窗口），角落最後
    for p in order:
        key = p["seat"] + p["bus"]
        def cost(c, key=key):
            k = 1.0; u = used.get(c)
            if u: k = 0.3 if key in u else k + 4.0
            if c in F["plug"]: k += 30.0
            return k
        blk = base_block | (all_slots - slot_cells[p["id"]])
        box = INNER_GOAL[p["seat"]] if p["entry"] == "inner" else side_goal(p["seat"])
        cells = route(p["slot"], goal_cells(box, blk), blk, cost)
        mark(cells, key)
        p["cells"] = cells; p["path"] = simplify(cells)
        p["plug_mm"] = sum(1 for c in cells if c in F["plug"])
        # 窗口與座內
        if p["entry"] == "inner":
            win = seat_to_world(p["seat"], 0, 47.0); win3 = Vector((win.x, win.y, 128.0 + dz))
        else:
            w2 = seat_to_world(p["seat"], -SEAT_HALF, sum(WIN_Y) / 2); win3 = Vector((w2.x, w2.y, sum(WIN_Z) / 2 + dz))
        rows = header_rows(fl, p["seat"])
        far = 0.0
        for r in rows.values():
            for e in r:
                ew = seat_to_world(p["seat"], e[0], e[1]); far = max(far, (Vector((ew.x, ew.y, e[2])) - win3).length)
        end2 = Vector(p["path"][-1])
        L_up = (Z_DUP1 - Z_WIRE) + 5.0                     # 出母座往上 5 mm 再彎回封孔板頂面
        L_2d = plen(p["path"]) + (Vector((win3.x, win3.y)) - end2).length
        L_rise = abs(win3.z - (Z_WIRE + dz))
        L_in = far + 10.0                                  # 窗口 → 最遠排針端（保守）＋插麵包板的彎
        L_service = 15.0                                   # OLED 端服務環
        p["len"] = dict(up=round(L_up, 1), route=round(L_2d, 1), rise=round(L_rise, 1), inside_max=round(L_in, 1),
                        service=L_service, total=round(L_up + L_2d + L_rise + L_in + L_service, 1))
        p["margin"] = round(WIRE_LEN - p["len"]["total"], 1)
    floors[fl] = dict(F=F, P=P)

# ---------- 4. 建模型：側窗已開；加 OLED 模組示意、長條孔、線排 ----------
def box_obj(name, W, u0, u1, v0, v1, z0, z1, color):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    q = [W(u0, v0), W(u1, v0), W(u1, v1), W(u0, v1)]
    vs = [bm.verts.new((a.x, a.y, z)) for z in (z0, z1) for a in q]
    if (q[1] - q[0]).cross(q[2] - q[1]).z < 0: vs = vs[:4][::-1] + vs[4:][::-1]
    bm.faces.new(vs[3::-1]); bm.faces.new(vs[4:])
    for i in range(4):
        j = (i + 1) % 4; bm.faces.new((vs[i], vs[j], vs[4 + j], vs[4 + i]))
    bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new(name, me); coll.objects.link(ob); ob.color = color
    m = bpy.data.materials.new(name + "_m"); m.diffuse_color = color; me.materials.append(m); return ob
SEAT_COLOR = {"N": (0.9, 0.2, 0.2, 1), "E": (0.2, 0.7, 0.2, 1), "S": (0.95, 0.75, 0.1, 1), "W": (0.6, 0.3, 0.9, 1)}
for fl, d in floors.items():
    dz = d["F"]["dz"]
    for p in d["P"]:
        W = p["W"]
        box_obj(f"{fl}F_OLED_{p['id']}", W, -PW / 2, PW / 2, -PH / 2, PH / 2, 103.0 + dz, 106.0 + dz, (0.05, 0.05, 0.08, 1))
        box_obj(f"{fl}F_OLED_{p['id']}_顯示區", W, -21.7 / 2, 21.7 / 2, 11.5 - PH / 2 - 5.45, 11.5 - PH / 2 + 5.45, 102.95 + dz, 103.0 + dz, (0.2, 0.85, 1.0, 1))
        box_obj(f"{fl}F_OLED_{p['id']}_母座", W, -5.08, 5.08, PH / 2 - PIN_ROW - 1.27, PH / 2 - PIN_ROW + 1.27, 106.0 + dz, Z_DUP1 + dz, (0.1, 0.1, 0.1, 1))
        # 線排：4 條並排 1.6 mm，沿路徑（z 118.4），起點在長孔、終點進窗口
        pts3 = [Vector((p["slot"].x, p["slot"].y, Z_DUP1 + 5 + dz))] + [Vector((x, y, Z_WIRE + dz)) for x, y in p["path"]]
        if p["entry"] == "inner":
            wv = seat_to_world(p["seat"], 0, 52.0); pts3.append(Vector((wv.x, wv.y, 128.0 + dz)))
        else:
            wv = seat_to_world(p["seat"], -SEAT_HALF + 6, sum(WIN_Y) / 2); pts3 += [Vector((pts3[-1].x, pts3[-1].y, sum(WIN_Z) / 2 + dz)), Vector((wv.x, wv.y, sum(WIN_Z) / 2 + dz))]
        cu = bpy.data.curves.new(f"{fl}F_線排_{p['id']}", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 3.0; cu.bevel_resolution = 0
        sp = cu.splines.new("POLY"); sp.points.add(len(pts3) - 1)
        for k, v in enumerate(pts3): sp.points[k].co = (v.x, v.y, v.z, 1)
        ob = bpy.data.objects.new(f"{fl}F_線排_{p['id']}", cu); coll.objects.link(ob); ob.color = SEAT_COLOR[p["seat"]]
        m = bpy.data.materials.new(ob.name + "_m"); m.diffuse_color = SEAT_COLOR[p["seat"]]; cu.materials.append(m)

# 匯出：開側窗後的麵包板座（N 座方向，座標原點移到座中心底）
seat_stl = os.path.join(OUT, "麵包板座_側窗_N方向.stl")
o = sc.objects["1F_麵包版座_N"]
tmp = o.copy(); tmp.data = o.data.copy(); sc.collection.objects.link(tmp)
tmp.matrix_world = Matrix.Translation((0, -95.75, -109.0)) @ o.matrix_world
bpy.ops.object.select_all(action="DESELECT"); tmp.select_set(True); bpy.context.view_layer.objects.active = tmp
try:
    bpy.ops.wm.stl_export(filepath=seat_stl, export_selected_objects=True, ascii_format=False)
except Exception as e:
    report["checks"]["stl_export_error"] = str(e)
bpy.data.objects.remove(tmp)

# 天花板與封孔板開 9 個長條孔（兩層都開進模型）；2F 版另外匯出 STL（1F 版用 model_oled_ceiling/ 既有 STL，這裡只拿來對照）
import bmesh as _bm
def mesh_volume(ob):
    b = _bm.new(); b.from_mesh(ob.data); b.transform(ob.matrix_world); v = b.calc_volume(signed=False); b.free(); return v
stl_out = {}
for fl, d in floors.items():
    dz = d["F"]["dz"]
    for nm in ("天花板", "天花板封孔板"):
        o = sc.objects[f"{fl}F_{nm}"]
        for p in d["P"]:
            long_x = abs(Z.cross(Vector((*D[p["up"]], 0))).x) > 0.5
            hx, hy = (SLOT_U / 2, SLOT_V / 2) if long_x else (SLOT_V / 2, SLOT_U / 2)
            c = cutter("_slot", (p["slot"].x - hx, p["slot"].y - hy, 100 + dz), (p["slot"].x + hx, p["slot"].y + hy, 121 + dz))
            apply_bool(o, c); bpy.data.objects.remove(c)
        stl_out[f"{fl}F_{nm}"] = dict(volume_mm3=round(mesh_volume(o), 1), nonmanifold=nonmanifold(o))
        if fl == 2:
            path = os.path.join(OUT, f"2F_{nm}_穿孔.stl")
            tmp = o.copy(); tmp.data = o.data.copy(); sc.collection.objects.link(tmp)
            bpy.ops.object.select_all(action="DESELECT"); tmp.select_set(True); bpy.context.view_layer.objects.active = tmp
            bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, ascii_format=False)
            bpy.data.objects.remove(tmp); stl_out[f"{fl}F_{nm}"]["stl"] = os.path.basename(path)
# 對照：model_oled_ceiling/ 的 1F STL 體積
here = os.path.dirname(os.path.abspath(__file__))
for nm, fn in (("天花板", "1F_天花板_穿孔.stl"), ("天花板封孔板", "1F_天花板封孔板_穿孔.stl")):
    ref = os.path.join(here, "..", "model_oled_ceiling", fn)
    if os.path.exists(ref):
        before = set(bpy.data.objects); bpy.ops.wm.stl_import(filepath=ref)
        new = [o for o in bpy.data.objects if o not in before]
        stl_out[f"1F_{nm}"]["repo_stl_volume_mm3"] = round(sum(mesh_volume(o) for o in new), 1)
        for o in new: bpy.data.objects.remove(o)
report["checks"]["ceiling_slots"] = stl_out
out_blend = os.path.join(OUT, "fire_model_8hub_wiring.blend")
bpy.ops.wm.save_as_mainfile(filepath=out_blend, copy=True)

# ---------- 5. 報告 ----------
rows = []
for fl, d in floors.items():
    for p in sorted(d["P"], key=lambda q: ("NESW".index(q["seat"]), q["bus"], q["addr"])):
        sda, scl = BUS_PINS[p["bus"]]
        hubpin = {"GND": "GND（藍軌）", "VCC": "3V3（紅軌）", "SCL": f"{scl}（{'Wire1' if p['bus'] == 'Wire1' else 'Wire'} SCL）", "SDA": f"{sda}（{'Wire1' if p['bus'] == 'Wire1' else 'Wire'} SDA）"}
        for pin in OLED_PINS:
            rows.append(dict(floor=fl, oled=p["id"], junction=(f"J({p['J'][0]},{p['J'][1]})" if fl == 1 else f"J2({p['J'][0]},{p['J'][1]})"), hub=f"{fl}{p['seat']}", bus=p["bus"], addr=hex(p["addr"]),
                             oled_pin=pin, hub_end=hubpin[pin], color=WIRE_COLOR[pin], entry=("朝中心窗口" if p["entry"] == "inner" else "側窗"),
                             length=p["len"]["total"], margin=p["margin"]))
report["oleds"] = [dict(oid=p["oid"], floor=fl, id=p["id"], J=p["J"], hub=f"{fl}{p['seat']}", bus=p["bus"], addr=hex(p["addr"]), up=p["up"],
                        entry=p["entry"], slot=[round(p["slot"].x, 1), round(p["slot"].y, 1)], path=p["path"], len=p["len"], margin=p["margin"],
                        plug_mm=p["plug_mm"], wall_below_samples=p["wall_below_samples"], hole_bad=p["hole_bad_samples"],
                        cam=p["camera_visible_px"], center=list(p["center"]), shift=p.get("shift"))
                   for fl, d in floors.items() for p in d["P"]]
report["wires"] = rows
report["files"] = dict(blend=os.path.basename(out_blend), seat_stl=os.path.basename(seat_stl))
json.dump(report, open(os.path.join(OUT, "wiring_8hub.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
print("WROTE", OUT, len(rows), "wires")
for o_ in report["oleds"]:
    print(o_["oid"], o_["hub"], o_["bus"], o_["addr"], o_["entry"], o_["len"]["total"], "margin", o_["margin"], "plug", o_["plug_mm"], "wall", o_["wall_below_samples"], "hole", o_["hole_bad"], "cam", o_["cam"])
print(json.dumps(report["checks"], ensure_ascii=False))
