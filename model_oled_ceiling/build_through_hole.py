"""
「穿孔＋雙面膠」方案的模擬（2026-11-09）：0.96 吋 OLED 螢幕朝下，用雙面泡棉膠貼在 1F 天花板底面；
天花板（含封孔板頂板）開一個長條孔，讓已焊好的 4 pin 直排針接上杜邦母座後整束往上穿到設備層。

用法（Blender 5.2；參數路徑只能用英文）：
  blender -b <fire_model.blend 的複本> --python build_through_hole.py -- <輸出資料夾>

只有 4 個角落找得到同時滿足「模組在走廊天花板下、長條孔不碰孔／塞子／排線溝、孔上方有杜邦母座空間、8 台鏡頭看不到」的位置
（見 README 與 search_through_hole.py）；邊中點與中心只標示最近的候選位置與失敗原因，不建模組。
"""
import bpy, bmesh, sys, os, math, json
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

OUT = sys.argv[sys.argv.index("--") + 1]; os.makedirs(OUT, exist_ok=True)
sc = bpy.context.scene; assert sc.name == "Assembly_Full"

# ---------- 實物規格（使用者提供；列印前請再量） ----------
PW, PH, PT = 27.8, 27.3, 1.6          # PCB：排針那條長邊 = 27.8（u 方向），另一邊 27.3（v 方向）
GW, GH, GT, GY0 = 26.7, 19.3, 1.4, 1.0
AW, AH, ACY = 21.7, 10.9, 11.5        # 顯示區；中心距 PCB 下緣（排針對邊）11.5
BACK = 1.5                            # 背面零件
SPACER = 2.5                          # 排針塑膠座
PIN_ROW = 1.68                        # 排針中心距 PCB 上緣
PIN_ABOVE = 6.0                       # 塑膠座以上的針長
DUP_W, DUP_L = 2.54, 14.0             # 杜邦母座（單 pin）截面、長度
TAPE = 2.0                            # 雙面泡棉膠厚（要 > 背面零件 1.5）
SLOT_U, SLOT_V = 11.4, 3.4            # 長條孔：4 個母座並排 10.16×2.54，每邊留 0.6／0.43 mm
WIRE_BEND = 5.0                       # 母座頂以上的線彎空間
CEIL = 108.0

Z_BACK = CEIL - TAPE                  # PCB 背面 z 106.0
Z_PCB0 = Z_BACK - PT                  # 104.4
Z_GLASS0 = Z_PCB0 - GT                # 103.0（往下凸出 5.0 mm）
Z_SP1 = Z_BACK + SPACER               # 塑膠座頂 108.5（伸進孔內 0.5 mm）
Z_DUP1 = Z_SP1 + DUP_L                # 母座頂 122.5

D = {"N": (0, 1), "E": (1, 0), "S": (0, -1), "W": (-1, 0)}
Z = Vector((0, 0, 1))
# 角落：位置由 search_corner_exact.py 用精確射線選出（顯示區中心離路口最近、四周 ≥ 0.6 mm、孔不碰溝與孔、上方有空間、鏡頭看不到）
#   up = 畫面上方（排針那一側）在世界座標的方向；route = 母座頂以上焊線沿封孔板頂面走到麵包板座內側端窗口
P = [
    # 角落：各由自己的鏡頭 HUB 驅動（Wire、0x3C，不用改焊）；走線由下面的自動繞線找到該 HUB 麵包板座朝中心那端的窗口
    dict(id="NW", J=(-99, 99), center=(-97.0, 100.0), up="E", hub="N", addr="0x3C", pod="N", route=None),
    dict(id="NE", J=(99, 99), center=(100.0, 97.0), up="S", hub="E", addr="0x3C", pod="E", route=None),
    dict(id="SE", J=(99, -99), center=(99.0, -101.0), up="S", hub="S", addr="0x3C", pod="S", route=None),
    dict(id="SW", J=(-99, -99), center=(-100.0, -97.0), up="N", hub="W", addr="0x3C", pod="W", route=None),
    # 中心（2026-11-10 使用者同意：模組可以從下方蓋住十字臂插槽塞子的一部分）。長孔完全落在路口中央實心區，不切任何塞子或排線溝
    dict(id="C", J=(0, 0), center=(0.0, 5.5), up="S", hub="H7", addr="0x3C", cover=True, route=None),
    # 邊中點（2026-11-10 定稿 s = 50）：十字臂中點，顯示區離邊中點 50 mm、離中心 49 mm；長孔穿過十字臂插槽的塞子
    dict(id="N", J=(0, 99), center=(0.0, 46.85), up="S", hub="H6", addr="0x3D", cover=True, slot_plug=True, route=None),
    dict(id="E", J=(99, 0), center=(46.85, 0.0), up="W", hub="H5", addr="0x3D", cover=True, slot_plug=True, route=None),
    dict(id="S", J=(0, -99), center=(0.0, -46.85), up="N", hub="H5", addr="0x3C", cover=True, slot_plug=True, route=None),
    dict(id="W", J=(-99, 0), center=(-46.85, 0.0), up="E", hub="H6", addr="0x3C", cover=True, slot_plug=True, route=None),
]
# 方案 D（2026-11-13）：不用 TCA9548A、不用 Wire1。中心與 4 個十字臂中點由 3 台只驅動 OLED 的 HUB-8735 驅動，每台只用 Wire（0x3C＋0x3D），2＋2＋1。
#   search_hub_spots.py：依 9 個長孔扣掉麵包板座、支撐柱、塞子頂面、長孔周圍後，放得下 HUB 板（40.5×27＋每邊 1 mm）的只有 4 區：
#   SE 房間頂南側 (52,−84)、SW 房間頂南側 (−52,−84)、西側南段 (−84,−52)、西側北段 (−84,52)；SW 房間頂與西側南段互相重疊 → 用其中 3 區
#   電源：4 個空位都夾在麵包板座側牆與房間角支撐柱之間，HUB 板兩個短邊各只剩約 2.25 mm，USB-C 插頭（含護套 ≥ 15 mm）插不進去。
#   → 改用「USB 轉杜邦」電源線：USB-A 公頭接集線器，另一端 5V／GND 兩條杜邦母頭插在 HUB 排針上，沿封孔板頂面走到樓層盒外緣。
#   pwr_side：電源線從板子哪一側離開；pwr_goal：外緣的目標區（x, y, 半寬, 半高）
HUBS = [
    dict(id="H5", center=(52.0, -84.0), size=(40.5, 27.0), bus_side="N", pwr_side="S", pwr_goal=(55.0, -116.5, 20.0, 0.5), color=(0.1, 0.8, 0.85, 1)),
    dict(id="H6", center=(-84.0, 52.0), size=(27.0, 40.5), bus_side="E", pwr_side="W", pwr_goal=(-100.0, 116.5, 15.0, 0.5), color=(0.95, 0.4, 0.75, 1)),
    dict(id="H7", center=(-52.0, -84.0), size=(40.5, 27.0), bus_side="N", pwr_side="S", pwr_goal=(-55.0, -116.5, 20.0, 0.5), color=(0.55, 0.85, 0.25, 1)),
]
HUBD = {h["id"]: h for h in HUBS}
Z_DEV0 = 117.6 + 4.0                 # 板子用 4 mm 銅柱架在封孔板頂面上
Z_DEV_TOP = Z_DEV0 + 1.6 + 2.5 + 14.0  # 排針＋杜邦母座頂 z 139.7（2F 樓板 z 150）
for p in P:
    up = Vector((*D[p["up"]], 0)); right = Z.cross(up)          # 面朝下：從下方看，畫面右方 = ẑ × 畫面上方
    c = Vector((*p["center"], 0)); p["u"], p["r"] = up, right
    p["W"] = lambda uu, vv, c=c, r=right, u=up: c + uu * r + vv * u
    p["slot"] = p["W"](0, PH / 2 - PIN_ROW)
    p["aa"] = p["W"](0, ACY - PH / 2)

def frame_box(bm, p, u0, u1, v0, v1, z0, z1):
    q = [p["W"](u0, v0), p["W"](u1, v0), p["W"](u1, v1), p["W"](u0, v1)]
    vs = [bm.verts.new((a.x, a.y, z)) for z in (z0, z1) for a in q]
    if (q[1] - q[0]).cross(q[2] - q[1]).z < 0: vs = vs[:4][::-1] + vs[4:][::-1]
    bm.faces.new(vs[3::-1]); bm.faces.new(vs[4:])
    for i in range(4):
        j = (i + 1) % 4; bm.faces.new((vs[i], vs[j], vs[4 + j], vs[4 + i]))

def mat(key, color):
    m = bpy.data.materials.get(key) or bpy.data.materials.new(key); m.diffuse_color = color; return m

coll = bpy.data.collections.new("OLED_穿孔方案"); sc.collection.children.link(coll)
made = []
def obj(name, build, color):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); build(bm); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob); ob.color = color; me.materials.append(mat(name.split("_")[-1] + "_mat", color))
    made.append(ob); return ob

def bvh(ob):
    dg = bpy.context.evaluated_depsgraph_get(); me = ob.evaluated_get(dg).to_mesh(); M = ob.matrix_world
    return BVHTree.FromPolygons([M @ v.co for v in me.vertices], [f.vertices[:] for f in me.polygons])

def nonmanifold(ob):
    bm = bmesh.new(); bm.from_mesh(ob.data); n = sum(1 for e in bm.edges if not e.is_manifold); bm.free(); return n

ceil, lid, floor = sc.objects["1F_天花板"], sc.objects["1F_天花板封孔板"], sc.objects["1F_樓層"]
B_ceil, B_lid, B_floor = bvh(ceil), bvh(lid), bvh(floor)

def stack(x, y):
    """垂直射線：天花板＋封孔板的區間、下方是否有牆"""
    iv = []
    for t in (B_ceil, B_lid):
        z, hits = 100.0, []
        while True:
            h = t.ray_cast(Vector((x, y, z)), Z, 40)
            if h[0] is None: break
            hits.append(h[0].z); z = h[0].z + 1e-3
        iv += [(hits[i], hits[i + 1], t is B_lid) for i in range(0, len(hits) - 1, 2)]
    z, hits = -1.0, []
    while True:
        h = B_floor.ray_cast(Vector((x, y, z)), Z, 200)
        if h[0] is None: break
        hits.append(h[0].z); z = h[0].z + 1e-3
    wall = any(hits[i + 1] > 9 and hits[i] < 107.95 for i in range(0, len(hits) - 1, 2))
    return sorted(iv), wall

def rect_pts(p, u0, u1, v0, v1, grow=0.0, step=0.5):
    out = []; nu = max(2, int((u1 - u0 + 2 * grow) / step) + 1); nv = max(2, int((v1 - v0 + 2 * grow) / step) + 1)
    for i in range(nu):
        for j in range(nv):
            out.append(p["W"](u0 - grow + (u1 - u0 + 2 * grow) * i / (nu - 1), v0 - grow + (v1 - v0 + 2 * grow) * j / (nv - 1)))
    return out

# ---------- 位置檢查（用原始網格） ----------
for p in P:
    hu, hv = PW / 2, PH / 2; bad = []; below = 0; cov = {}
    for q in rect_pts(p, -hu, hu, -hv, hv, grow=0.6):       # 模組四周 0.6 mm 內：天花板底面要是平的 z 108（不能是塞子、鏡頭孔、銷孔）
        iv, wall = stack(q.x, q.y)
        if p.get("cover"):                                  # 中心：只禁止貫穿孔；其餘記錄蓋住了什麼
            if not iv: bad.append((round(q.x, 1), round(q.y, 1)))
            continue
        if not iv or abs(iv[0][0] - CEIL) > 0.05 and not (iv[0][2] and iv[0][0] > 115.9): bad.append((round(q.x, 1), round(q.y, 1)))
    if p.get("cover"):                                      # 蓋住的面積（0.25 mm 網格、每點 0.0625 mm²），只算模組本體
        n = 0; ring = []
        for q in rect_pts(p, -hu, hu, -hv, hv, step=0.25):
            iv, _ = stack(q.x, q.y); n += 1
            if not iv: k = "貫穿孔"
            elif iv[0][2] and iv[0][0] < 109:
                if max(abs(q.x), abs(q.y)) > 70: k = "環廊排線孔塞子"; ring.append((q.x, q.y))
                else:
                    k = "ArmN 塞子" if q.y > 1.5 else "ArmS 塞子" if q.y < -9.5 and abs(q.x) < 13 else "ArmW 塞子" if q.x < -1.5 else "ArmE 塞子"
                    if p["id"] in "NESW" and k[3] == p["id"]: ring.append((q.x, q.y))
            elif iv[0][2] and iv[0][0] > 115.9: k = "(11,11) 路口孔"
            elif abs(iv[0][0] - CEIL) > 0.05: k = "塞子與孔之間的縫"
            else:
                zt = iv[0][1]; gap = False
                for a, b, _l in iv[1:]:
                    if a <= zt + 0.05: zt = max(zt, b)
                    else: gap = True
                k = "排線溝（只從下方蓋住，不切）" if gap or zt < 114.9 else "實心天花板"
            cov[k] = cov.get(k, 0) + 1
        p["cover_area"] = {k: round(v * 0.0625, 1) for k, v in sorted(cov.items(), key=lambda t: -t[1])}
        if ring:   # 邊中點：自己那支十字臂的插槽塞子沿走廊方向被蓋住的長度
            xs_ = [t[0] for t in ring]; ys_ = [t[1] for t in ring]
            p["ring_cover_len"] = round(((max(ys_) - min(ys_)) if p["id"] in "NS" else (max(xs_) - min(xs_))) + 0.25, 1)
    for q in rect_pts(p, -hu, hu, -hv, hv, grow=0.4): below += stack(q.x, q.y)[1]
    sbad = []; top = 99.0
    for q in rect_pts(p, -SLOT_U / 2, SLOT_U / 2, PH / 2 - PIN_ROW - SLOT_V / 2, PH / 2 - PIN_ROW + SLOT_V / 2, grow=0.8):
        iv, _ = stack(q.x, q.y)
        # 長條孔＋0.8 mm 壁：天花板從 108 連續實體到頂（中間不能有排線溝的空腔、不能是塞子或孔）
        ok = iv and abs(iv[0][0] - CEIL) < 0.05 and not iv[0][2]
        if p.get("slot_plug") and iv and iv[0][2] and iv[0][0] < 109: ok = True      # 長孔穿過塞子（塞子 z 108.2～117.6 實心）
        zt = iv[0][1] if ok else 0
        for a, b, _l in iv[1:]:
            if a <= zt + 0.05: zt = max(zt, b)
            else: ok = False
        if not ok or zt < 114.9: sbad.append((round(q.x, 1), round(q.y, 1)))
        else: top = min(top, zt)
    p["check"] = dict(bad=len(bad), below=below, slot_bad=len(sbad), ceil_top=top)

# ---------- 開孔（天花板與封孔板頂板都要開） ----------
def apply_cut(ob, boxes):
    ob.data = ob.data.copy(); ob.data.name = ob.name + "_穿孔"
    for b in boxes:
        me = bpy.data.meshes.new("_t"); bm = bmesh.new(); b(bm); bm.to_mesh(me); bm.free()
        t = bpy.data.objects.new("_t", me); sc.collection.objects.link(t)
        m = ob.modifiers.new("b", "BOOLEAN"); m.operation = "DIFFERENCE"; m.object = t; m.solver = "EXACT"
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.data.objects.remove(t, do_unlink=True); bpy.data.meshes.remove(me)
slots = [lambda bm, p=p: frame_box(bm, p, -SLOT_U / 2, SLOT_U / 2, PH / 2 - PIN_ROW - SLOT_V / 2, PH / 2 - PIN_ROW + SLOT_V / 2, CEIL - 1, 125) for p in P]
NM0 = (nonmanifold(ceil), nonmanifold(lid))
keep = bpy.data.collections.new("_原始天花板與封孔板（僅供比較）"); sc.collection.children.link(keep)
for o in (ceil, lid):
    c = o.copy(); c.data = o.data.copy(); c.name = o.name + "_原始"; keep.objects.link(c)
apply_cut(ceil, slots); apply_cut(lid, slots)
bpy.context.view_layer.layer_collection.children[keep.name].exclude = True
NM1 = (nonmanifold(ceil), nonmanifold(lid))

# ---------- 設備層走線（2026-11-13 接線設計）：1 mm 網格加權最短路 ----------
#   不能走：封孔板頂面以上 12 mm 內有既有零件（再膨脹 4 mm）、天花板＋封孔板都穿透的孔（鏡頭孔等，膨脹 2 mm）、其他長條孔（含 3 mm）、HUB 板（含 1 mm）
#   成本：一般格 1；塞子頂面（排煙孔／排線孔／十字臂插槽塞子，要能拆）+30；同一台 HUB 已走過的線束 ±4 mm 內 ×0.3（併成一束）；
#         別台 HUB 的線束 ±4 mm 內 +4（少交叉）；每轉一次彎 +2（少鋸齒）
import heapq
HUB_COLOR = {"N": (0.9, 0.2, 0.2, 1), "E": (0.2, 0.7, 0.2, 1), "S": (0.95, 0.75, 0.1, 1), "W": (0.6, 0.3, 0.9, 1), **{h["id"]: h["color"] for h in HUBS}}
obst_objs = [o for o in sc.objects if o.type == "MESH" and o.visible_get() and not o.name.startswith("ASM_")
             and o.name not in ("1F_天花板", "1F_天花板封孔板", "1F_樓層") and o not in made and (o.name.startswith("1F_") or o.name.startswith("2F_"))]
vs_, fs_ = [], []
dg0 = bpy.context.evaluated_depsgraph_get()
for o in obst_objs:
    me = o.evaluated_get(dg0).to_mesh(); M = o.matrix_world; b = len(vs_)
    vs_ += [M @ v.co for v in me.vertices]; fs_ += [tuple(b + i for i in f.vertices) for f in me.polygons]
B_obst = BVHTree.FromPolygons(vs_, fs_)
GX = [x for x in range(-117, 118)]; NG = len(GX)
blocked = set(); plug_cells = set(); hole_cells = set()
for i, x in enumerate(GX):
    for j, y in enumerate(GX):
        h = B_obst.ray_cast(Vector((x, y, 105.0)), Z, 24.65)     # 從天花板下方往上打，才不會從零件內部起算而漏掉（例如麵包板座側牆）
        if h[0] is not None and h[0].z > 107.9: blocked.add((i, j))
        hl = B_lid.ray_cast(Vector((x, y, 100.0)), Z, 30); hc = B_ceil.ray_cast(Vector((x, y, 100.0)), Z, 18)
        if hl[0] is not None and hl[0].z < 109: plug_cells.add((i, j))            # 封孔板的塞子（從 z 108.2 起）＝塞子頂面
        if (hc[0] is None or hc[0].z > 117.0) and (hl[0] is None or hl[0].z > 117.7): hole_cells.add((i, j))
def box_cells(cx, cy, hx, hy, grow):
    return [(i, j) for i, x in enumerate(GX) for j, y in enumerate(GX) if abs(x - cx) <= hx + grow and abs(y - cy) <= hy + grow]
def dilate(cells, r=2):
    out = set()
    for i, j in cells:
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if 0 <= i + di < NG and 0 <= j + dj < NG: out.add((i + di, j + dj))
    return out
base_block = dilate(blocked, 4) | dilate(hole_cells, 2)       # 線排寬 6 mm（4 條 × 1.6）：中心線離障礙 ≥ 4 mm
dev_cells = set().union(*[set(box_cells(*h["center"], h["size"][0] / 2, h["size"][1] / 2, 1)) for h in HUBS])
def slot_cells(p, grow=3):
    long_x = abs(p["r"].x) > 0.5; hx, hy = (SLOT_U / 2, SLOT_V / 2) if long_x else (SLOT_V / 2, SLOT_U / 2)
    return set(box_cells(p["slot"].x, p["slot"].y, hx, hy, grow))
all_slots = set().union(*[slot_cells(o) for o in P])
used = {}; keepout = set()
def mark(cells, key, r=4):
    for c in dilate(cells, r):
        d_ = used.setdefault(c, {}); d_[key] = d_.get(key, 0) + 1
def cell_cost(c, key):
    k = 1.0; u = used.get(c)
    if u:
        if key in u: k = 0.3
        else: k += 4.0
    if c in plug_cells: k += 30.0
    if c in keepout and key not in ("N", "E", "S", "W"): k += 10.0      # 麵包板座窗口前的進線區留給角落線
    return k
GI = lambda v: (int(round(v[0])) + 117, int(round(v[1])) + 117)
def ring_goals(box, blk, r0=1.5, r1=3):
    cx, cy, hx, hy = box
    return set(c for c in box_cells(cx, cy, hx, hy, r1) if c not in blk) - set(box_cells(cx, cy, hx, hy, r0))
def route(start, goals, blk, key, relax=6):
    si = GI(start); DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
    dist = {(si, -1): 0.0}; prev = {}; pq = [(0.0, si, -1)]; end = None
    while pq:
        d, c, k = heapq.heappop(pq)
        if d > dist.get((c, k), 1e18): continue
        if c in goals: end = (c, k); break
        for kk, (di, dj) in enumerate(DIRS):
            n = (c[0] + di, c[1] + dj)
            if not (0 <= n[0] < NG and 0 <= n[1] < NG): continue
            if n in blk and max(abs(n[0] - si[0]), abs(n[1] - si[1])) > relax: continue
            nd = d + cell_cost(n, key) + (2.0 if k not in (-1, kk) else 0.0)
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
    return [Vector((float(x), float(y))) for x, y in simp]
def plug_runs(cells):
    runs, cur = [], []
    for c in cells:
        if c in plug_cells: cur.append(c)
        elif cur: runs.append(cur); cur = []
    if cur: runs.append(cur)
    return [dict(start=[GX[r[0][0]], GX[r[0][1]]], end=[GX[r[-1][0]], GX[r[-1][1]]], mm=len(r)) for r in runs]
def edge_pt(h, side, inset, t=0.0):
    """HUB 板邊上的點：side 那一邊、inset＝往板內的距離（負＝板外）、t＝沿邊偏移"""
    v = Vector(D[side]); w = Vector((-v.y, v.x)); half = h["size"][0] / 2 if abs(v.x) else h["size"][1] / 2
    return Vector(h["center"]) + v * (half - inset) + w * t
def side_goals(h, side, blk, along=5, across=1):
    c = edge_pt(h, side, -3.0); v = D[side]
    hx, hy = (across, along) if abs(v[0]) else (along, across)
    return set(cc for cc in box_cells(c.x, c.y, hx, hy, 0) if cc not in blk)
# HUB 排針（示意排列，實際依 HUB-8735 Ultra 絲印）：I²C 那一排在 bus_side 長邊中段：3V3、GND、SDA(Pin3)、SCL(Pin4)；電源那一排在 pwr_side：5V、GND
for h in HUBS:
    h["bus_pin"] = {nm: edge_pt(h, h["bus_side"], 2.5, (k - 1.5) * 2.54) for k, nm in enumerate(("3V3", "GND", "SDA", "SCL"))}
    h["pwr_pin"] = {nm: edge_pt(h, h["pwr_side"], 2.5, (k - 0.5) * 2.54) for k, nm in enumerate(("5V", "GND"))}
# 麵包板座朝中心那端的窗口（z 127～140、寬 ±24 mm）：線從窗口外 0.5 mm 的細長目標區進去，最後伸進窗口 4.5 mm
POD_GOAL = {"N": ((0, 44.5, 15, 0.5), (0, 4.5)), "E": ((44.5, 0, 0.5, 15), (4.5, 0)), "S": ((0, -44.5, 15, 0.5), (0, -4.5)), "W": ((-44.5, 0, 0.5, 15), (-4.5, 0))}
for g_, _i in POD_GOAL.values():
    keepout |= set(box_cells(g_[0], g_[1], g_[2] + 6, g_[3] + 10, 0))
for p in sorted([p for p in P if "pod" not in p], key=lambda q: (q["hub"], q["addr"])):     # 先繞第 5～7 台 HUB 的線（同一台先繞 0x3C）
    blk = base_block | (all_slots - slot_cells(p)) | dev_cells
    h = HUBD[p["hub"]]
    p["cells"] = route(p["slot"], side_goals(h, h["bus_side"], blk), blk, p["hub"]); p["end_kind"] = "hub"
    mark(p["cells"], p["hub"])
# 兩塊 OLED 的 HUB：在兩條線會合處放一塊小分接板（洞洞板＋3 組 4 pin 直角公排針：輸入 A、輸入 B、輸出），線全部用一般母－母杜邦線
#   位置：在網格上找「OLED A → 板 ＋ OLED B → 板 ＋ 板 → HUB 排針」加權距離總和最小、板子 20×14 mm（含 1 mm）底下沒有塞子／障礙／長孔、
#   也不擋麵包板座窗口前的進線區（窗口目標區外擴 6×10 mm）的格子
import numpy as np
BOARD_L, BOARD_W = 20.0, 14.0
DIRS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
def dist_map(srcs, blk, key, relax_src=None):
    dist = {}; pq = []
    for s_ in srcs: dist[s_] = 0.0; heapq.heappush(pq, (0.0, s_))
    while pq:
        d, c = heapq.heappop(pq)
        if d > dist[c]: continue
        for di, dj in DIRS4:
            n = (c[0] + di, c[1] + dj)
            if not (0 <= n[0] < NG and 0 <= n[1] < NG): continue
            if n in blk and (relax_src is None or max(abs(n[0] - relax_src[0]), abs(n[1] - relax_src[1])) > 6): continue
            nd = d + cell_cost(n, key)
            if nd < dist.get(n, 1e18): dist[n] = nd; heapq.heappush(pq, (nd, n))
    return dist
board_cells_all = set()
for h in HUBS:
    mine = sorted([p for p in P if p["hub"] == h["id"]], key=lambda q: q["addr"])
    if len(mine) < 2: continue
    A, B = mine
    blk = base_block | (all_slots - slot_cells(A) - slot_cells(B)) | dev_cells
    forbid = np.zeros((NG + 1, NG + 1))
    for c in (base_block | all_slots | dev_cells | plug_cells | keepout | board_cells_all): forbid[c[0] + 1, c[1] + 1] = 1
    S_ = forbid.cumsum(0).cumsum(1)
    def free(i, j, a, b):
        i0, i1, j0, j1 = i - a, i + a + 1, j - b, j + b + 1
        if i0 < 0 or j0 < 0 or i1 > NG or j1 > NG: return False
        return S_[i1, j1] - S_[i0, j1] - S_[i1, j0] + S_[i0, j0] == 0
    dA = dist_map([GI(A["slot"])], blk | (all_slots - slot_cells(A)), h["id"], GI(A["slot"]))
    dB = dist_map([GI(B["slot"])], blk | (all_slots - slot_cells(B)), h["id"], GI(B["slot"]))
    dH = dist_map(list(side_goals(h, h["bus_side"], blk)), blk, h["id"])
    best = None
    for c in set(dA) & set(dB) & set(dH):
        for a, b in ((11, 8), (8, 11)):
            if free(c[0], c[1], a, b):
                tot = dA[c] + dB[c] + dH[c]
                if best is None or tot < best[0]: best = (tot, c, a - 1, b - 1)
    assert best, f"{h['id']}: 找不到分接板位置"
    _t, cc, hx, hy = best
    ctr = Vector((GX[cc[0]], GX[cc[1]])); bc = set(box_cells(ctr.x, ctr.y, hx, hy, 1)); board_cells_all |= bc
    h["board"] = dict(center=ctr, hx=hx, hy=hy, cost=round(_t, 1))
    for p in (A, B):
        blk2 = base_block | (all_slots - slot_cells(p)) | dev_cells | board_cells_all
        p["cells"] = route(p["slot"], ring_goals((ctr.x, ctr.y, hx, hy), blk2), blk2, h["id"]); p["end_kind"] = "board"; mark(p["cells"], h["id"])
    blk3 = base_block | all_slots | dev_cells | (board_cells_all - bc)
    cm = route(ctr, side_goals(h, h["bus_side"], blk3), blk3, h["id"], relax=max(hx, hy) + 2)
    k0 = 0
    while k0 < len(cm) - 1 and abs(GX[cm[k0][0]] - ctr.x) <= hx and abs(GX[cm[k0][1]] - ctr.y) <= hy: k0 += 1
    h["common_cells"] = cm[k0:]; mark(h["common_cells"], h["id"])
for p in [p for p in P if "pod" in p]:     # 角落最後繞（避開分接板）
    blk = base_block | (all_slots - slot_cells(p)) | dev_cells | board_cells_all
    goal, inward = POD_GOAL[p["pod"]]
    p["cells"] = route(p["slot"], ring_goals(goal, blk), blk, p["hub"]); p["end_kind"] = "pod"; p["inward"] = Vector(inward)
    mark(p["cells"], p["hub"])
for p in P:
    p["plug_runs"] = plug_runs(p["cells"])

# ---------- 3 台只驅動 OLED 的 HUB（簡化外形：板子＋銅柱＋兩排排針杜邦區） ----------
for h in HUBS:
    cx, cy = h["center"]; hx, hy = h["size"][0] / 2, h["size"][1] / 2
    pd = dict(W=lambda uu, vv, cx=cx, cy=cy: Vector((cx + uu, cy + vv, 0)))
    obj(f"1F_{h['id']}_板", lambda bm, pd=pd, hx=hx, hy=hy: frame_box(bm, pd, -hx, hx, -hy, hy, Z_DEV0, Z_DEV0 + 1.6), (0.15, 0.55, 0.3, 1))
    def posts(bm, pd=pd, hx=hx, hy=hy):
        for sx in (-1, 1):
            for sy in (-1, 1): frame_box(bm, pd, sx * (hx - 2.5) - 1.2, sx * (hx - 2.5) + 1.2, sy * (hy - 2.5) - 1.2, sy * (hy - 2.5) + 1.2, 117.62, Z_DEV0)
    obj(f"1F_{h['id']}_銅柱", posts, (0.8, 0.7, 0.3, 1))
    for nm_, sd in (("排針杜邦區", h["bus_side"]), ("排針杜邦區_電源側", h["pwr_side"])):
        v = D[sd]
        if v[1]: box = (-hx + 1, hx - 1, v[1] * (hy - 4), v[1] * (hy - 1))
        else: box = (v[0] * (hx - 4), v[0] * (hx - 1), -hy + 1, hy - 1)
        obj(f"1F_{h['id']}_{nm_}", lambda bm, pd=pd, b=box: frame_box(bm, pd, min(b[0], b[1]), max(b[0], b[1]), min(b[2], b[3]), max(b[2], b[3]), Z_DEV0 + 1.6, Z_DEV_TOP), (0.12, 0.12, 0.12, 1))
    # 短邊外的淨空（USB 插頭能不能插）：從短邊中點往外打水平射線到第一個障礙
    for sd in (("E", "W") if hx > hy else ("N", "S")):
        v = Vector((*D[sd], 0)); o0 = Vector((cx, cy, Z_DEV0 + 0.8)) + v * ((hx if abs(v.x) else hy) + 0.01)
        hh = B_obst.ray_cast(o0, v, 100); h.setdefault("end_clear", {})[sd] = round(hh[3], 1) if hh[0] is not None else 99
    if h.get("board"):
        bd = h["board"]; c = bd["center"]
        obj(f"1F_接線_{h['id']}_分接板", lambda bm, c=c, bd=bd: frame_box(bm, dict(W=lambda uu, vv: Vector((c.x + uu, c.y + vv, 0))), -bd["hx"], bd["hx"], -bd["hy"], bd["hy"], 118.0, 121.0), (0.85, 0.85, 0.75, 1))
# 電源（USB 轉杜邦 5V／GND）設備層內段：從 pwr_side 那排排針出線，繞到樓層盒外緣
for h in HUBS:
    blk = base_block | all_slots | dev_cells | board_cells_all
    st = edge_pt(h, h["pwr_side"], -3.0)
    h["pwr_cells"] = route(st, ring_goals(h["pwr_goal"], blk), blk, h["id"] + "_電源")
    mark(h["pwr_cells"], h["id"] + "_電源")
    h["pwr_plug_runs"] = plug_runs(h["pwr_cells"])
# HUB 板底下：不能壓在塞子頂面（排煙孔、排線孔要能拆）、上方到 2F 樓板要放得下
for h in HUBS:
    cx, cy = h["center"]; hx, hy = h["size"][0] / 2, h["size"][1] / 2; nplug = 0; nobs = 0
    for x in [cx - hx + k * 0.5 for k in range(int(2 * hx / 0.5) + 1)]:
        for y in [cy - hy + k * 0.5 for k in range(int(2 * hy / 0.5) + 1)]:
            hh = B_lid.ray_cast(Vector((x, y, 100)), Z, 30)
            if hh[0] is not None and hh[0].z < 109: nplug += 1
            hh = B_obst.ray_cast(Vector((x, y, 105.0)), Z, Z_DEV_TOP - 105.0 + 1)
            if hh[0] is not None and hh[0].z > 107.9: nobs += 1
    h["check"] = dict(plug=nplug, obstacle=nobs)
gaps_h = []
for i in range(len(HUBS)):
    for j in range(i + 1, len(HUBS)):
        a_, b_ = HUBS[i], HUBS[j]
        dx = abs(a_["center"][0] - b_["center"][0]) - (a_["size"][0] + b_["size"][0]) / 2; dy = abs(a_["center"][1] - b_["center"][1]) - (a_["size"][1] + b_["size"][1]) / 2
        gaps_h.append((round(max(dx, dy), 1), a_["id"], b_["id"]))

# ---------- 模組、雙面膠、排針、杜邦母座、線 ----------
for p in P:
    hu, hv = PW / 2, PH / 2; t = f"1F_OLED穿孔_{p['id']}"; sv = hv - PIN_ROW
    obj(f"{t}_玻璃", lambda bm, p=p: frame_box(bm, p, -GW / 2, GW / 2, -hv + GY0, -hv + GY0 + GH, Z_GLASS0, Z_PCB0), (0.03, 0.03, 0.03, 1))
    obj(f"{t}_顯示區", lambda bm, p=p: frame_box(bm, p, -AW / 2, AW / 2, ACY - hv - AH / 2, ACY - hv + AH / 2, Z_GLASS0 - 0.05, Z_GLASS0), (0.2, 0.85, 1.0, 1))
    obj(f"{t}_PCB", lambda bm, p=p: frame_box(bm, p, -hu, hu, -hv, hv, Z_PCB0, Z_BACK), (0.1, 0.25, 0.55, 1))
    obj(f"{t}_背面零件", lambda bm, p=p: frame_box(bm, p, -hu + 2.5, hu - 2.5, -hv + 4.0, sv - 2.5, Z_BACK, Z_BACK + BACK), (0.3, 0.3, 0.3, 1))
    def tape(bm, p=p):    # 雙面泡棉膠：排針對邊一條＋排針兩側各一塊（避開背面零件）
        frame_box(bm, p, -hu + 0.5, hu - 0.5, -hv + 0.5, -hv + 3.5, Z_BACK, CEIL - 0.02)
        frame_box(bm, p, -hu + 0.5, -hu + 2.3, -hv + 4.5, hv - 0.5, Z_BACK, CEIL - 0.02)
        frame_box(bm, p, hu - 2.3, hu - 0.5, -hv + 4.5, hv - 0.5, Z_BACK, CEIL - 0.02)
    obj(f"{t}_雙面膠", tape, (0.95, 0.85, 0.3, 1))
    obj(f"{t}_排針塑膠座", lambda bm, p=p: frame_box(bm, p, -5.08, 5.08, sv - 1.27, sv + 1.27, Z_BACK, Z_SP1), (0.1, 0.1, 0.1, 1))
    def pins(bm, p=p):
        for k in range(4):
            uu = (k - 1.5) * 2.54; frame_box(bm, p, uu - 0.32, uu + 0.32, sv - 0.32, sv + 0.32, Z_PCB0 + 0.01, Z_SP1 + PIN_ABOVE)
    obj(f"{t}_排針", pins, (0.85, 0.75, 0.3, 1))
    def dup(bm, p=p):
        for k in range(4):
            uu = (k - 1.5) * 2.54; frame_box(bm, p, uu - 1.25, uu + 1.25, sv - 1.25, sv + 1.25, Z_SP1 + 0.01, Z_DUP1)
    obj(f"{t}_杜邦母座", dup, (0.15, 0.15, 0.15, 1))


# ---------- 外接線：每塊 OLED 4 條杜邦線（紅 VCC、黑 GND、黃 SCL、綠 SDA），1.5 mm 間距排成扁排 ----------
LAY0, PITCH, R_W = 118.4, 1.6, 0.65          # 第一層線芯中心 z 118.4（封孔板頂面 117.6 上），杜邦線外徑約 1.3 mm
Z_RISE = Z_DEV_TOP + 3.0                     # 往 HUB 排針那段：從板邊外豎起到 z 142.7 再彎進母座（2F 樓板 z 150）
COND = (("GND", (0.04, 0.04, 0.04, 1)), ("VCC", (0.9, 0.08, 0.08, 1)), ("SCL", (0.95, 0.85, 0.05, 1)), ("SDA", (0.05, 0.65, 0.15, 1)))
CCOL = dict(COND); CCOL["3V3"] = CCOL["VCC"]; CCOL["5V"] = CCOL["VCC"]
HUBPIN = {"GND": "GND", "VCC": "3V3", "SCL": "SCL", "SDA": "SDA"}
PIN_DESC = {"3V3": "3V3", "GND": "GND", "SDA": "SDA（Pin3）", "SCL": "SCL（Pin4）"}
WIRES = []
def curve(name, pts, color, r=R_W):
    cu = bpy.data.curves.new(name, "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 2
    sp = cu.splines.new("POLY"); sp.points.add(len(pts) - 1)
    for k, q in enumerate(pts): sp.points[k].co = (q.x, q.y, q.z, 1)
    ob = bpy.data.objects.new(name, cu); coll.objects.link(ob); ob.color = color
    cu.materials.append(mat(name.split("_")[-1] + "線_mat", color)); WIRES.append(ob)
    return sum((pts[k + 1] - pts[k]).length for k in range(len(pts) - 1))
def offset2d(pts, d):
    out = []; n = len(pts)
    for k in range(n):
        a = pts[k].to_2d(); di = do = None
        for m in range(k - 1, -1, -1):
            v = a - pts[m].to_2d()
            if v.length > 1e-6: di = v.normalized(); break
        for m in range(k + 1, n):
            v = pts[m].to_2d() - a
            if v.length > 1e-6: do = v.normalized(); break
        di = di or do; do = do or di
        ni, no = Vector((-di.y, di.x)), Vector((-do.y, do.x)); mm = ni + no
        if mm.length < 1e-6: mm = ni
        mm.normalize(); c = max(0.3, mm.dot(ni)); q = a + mm * (d / c)
        out.append(Vector((q.x, q.y, pts[k].z)) if len(pts[k]) == 3 else q)
    return out
occ = {}
def lay_z(cells, skip=8):
    lay = max([occ.get(c, 0) for c in cells[skip:]] or [0]);
    for c in dilate(cells[skip:], 4): occ[c] = occ.get(c, 0) + 1
    return LAY0 + PITCH * lay, lay
def hub_tail(last, pin):
    return [Vector((last.x, last.y, Z_RISE)), Vector((pin.x, pin.y, Z_RISE)), Vector((pin.x, pin.y, Z_DEV_TOP))]
TAPES = []   # (中心 2D, 走向 2D, z, 註記)
def plan_fix(H, z, tag, first_skip=15.0, step=40.0):
    """膠帶固定點：每個轉角一處、直段每 40 mm 一處；起點 15 mm 內是服務環不貼。落在塞子頂面上的點不貼，記下來"""
    out = []; s0 = 0.0
    for k in range(len(H) - 1):
        a, b = H[k].to_2d(), H[k + 1].to_2d(); L_ = (b - a).length
        if L_ < 1e-6: continue
        t = (b - a) / L_; cand = [s for s in range(int(step), int(L_), int(step))] + ([L_] if k < len(H) - 2 else [])
        for s in cand:
            if s0 + s < first_skip: continue
            q = a + t * s; c = GI(q)
            n_ = Vector((-t.y, t.x)); bad = plug_cells | blocked
            def side_ok(sg): return not any(GI(q + t * du + n_ * sg * dv) in bad for du in (-5, 0, 5) for dv in (3.5, 5, 6.5))
            ext = (6.5 if side_ok(-1) else 0, 6.5 if side_ok(1) else 0)
            onplug = GI(q) in plug_cells or ext == (0, 0)          # 線排本身在塞子上、或兩側都沒有可貼的封孔板面 → 不貼
            if any((q - T[0]).length < 6 for T in TAPES): continue
            TAPES.append((q, t, z, tag, onplug, ext)); out.append(dict(at=[round(q.x, 1), round(q.y, 1)], tape=not onplug, one_side=(not onplug and 0 in ext)))
        s0 += L_
    return out
def ribbon(tag, names, starts, H, z, offs, tail_fn, start_lift=True):
    """names：導線名；starts：各導線起點（3D，None＝直接從 H 起）；H：中心線（2D 轉點）；tail_fn(k, last3d)→ 尾段點"""
    lens = {}
    for k, nm in enumerate(names):
        Ho = offset2d([Vector((q.x, q.y, z)) for q in H], offs[k]); pts = []
        if starts[k] is not None:
            s_ = starts[k]; pts += [s_, Vector((s_.x, s_.y, Z_DUP1 + 2.5))] if start_lift else [s_]
        pts += Ho + tail_fn(k, Ho[-1])
        lens[nm] = curve(f"{tag}_{nm}", pts, CCOL[nm])
    return lens
def path_txt(H): return " → ".join(f"({q.x:.0f},{q.y:.0f})" for q in H)
OFF4 = (-1.5 * PITCH, -0.5 * PITCH, 0.5 * PITCH, 1.5 * PITCH)
for p in sorted(P, key=lambda q: (q["end_kind"] == "board", "pod" in q)):
    sv = PH / 2 - PIN_ROW; s2 = p["slot"]
    cells = p["cells"]
    H = simplify(cells)
    # 起彎點：沿第一段 ≥ 4 mm 的直段方向，離長孔 WIRE_BEND；前面那幾 mm 的小折線併掉（線排從母座頂直接彎過去）
    j0 = next((k for k in range(len(H) - 1) if (H[k + 1] - H[k]).length >= 4), max(0, len(H) - 2))
    if len(H) > 1:
        d0 = (H[j0 + 1] - H[j0]).normalized(); along = max(0.0, (s2.to_2d() - H[j0]).dot(d0)) + WIRE_BEND
        along = min(along, (H[j0 + 1] - H[j0]).length - 0.5); bend = H[j0] + d0 * max(along, 0.0)
        Hc = [bend] + H[j0 + 1:]
    else:
        d0 = Vector((1, 0)); Hc = [s2.to_2d()]
    z, layer = lay_z(cells)
    pins = [p["W"]((k - 1.5) * 2.54, sv) for k in range(4)]
    n0 = Vector((-d0.y, d0.x)); ordk = sorted(range(4), key=lambda k: (pins[k].to_2d() - s2.to_2d()).dot(n0) + 1e-3 * k)
    offs = [OFF4[ordk.index(k)] for k in range(4)]
    starts = [Vector((q.x, q.y, Z_DUP1)) for q in pins]
    h = HUBD.get(p["hub"])
    if p["end_kind"] == "pod":
        iw = p["inward"]
        tail = lambda k, l: [Vector((l.x, l.y, 132.0)), Vector((l.x + iw.x, l.y + iw.y, 132.0))]
    elif p.get("split") or p["end_kind"] == "board":
        tail = lambda k, l: [Vector((l.x, l.y, 119.5))]
    else:
        tail = lambda k, l, h=h: hub_tail(l, h["bus_pin"][HUBPIN[COND[k][0]]])
    p["layer"] = layer; p["z"] = z; p["path"] = Hc
    p["cond_len"] = ribbon(f"1F_OLED穿孔_{p['id']}_杜邦線", [c[0] for c in COND], starts, Hc, z, offs, tail)
    p["fix"] = plan_fix(Hc, z, p["id"])

for h in HUBS:      # 分接板 → HUB 的共用段（1 組 4 條）
    if not h.get("common_cells"): continue
    c2 = h["common_cells"]; H2 = simplify(c2); z2, _ = lay_z(c2, 0)
    d1 = (H2[1] - H2[0]).normalized() if len(H2) > 1 else Vector((1, 0)); n1 = Vector((-d1.y, d1.x))
    lens2 = ribbon(f"1F_接線_{h['id']}_共用線", [c[0] for c in COND], [Vector((H2[0].x + n1.x * o, H2[0].y + n1.y * o, 119.5)) for o in OFF4],
                   H2, z2, OFF4, lambda k, l, h=h: hub_tail(l, h["bus_pin"][HUBPIN[COND[k][0]]]), start_lift=False)
    h["common"] = dict(len=lens2, path=H2, z=z2, fix=plan_fix(H2, z2, h["id"] + "共用", first_skip=5.0), plug_runs=plug_runs(c2))

# ---------- 電源 ----------
#   出口：南、北兩處。設備層（1F 天花板 z 116 到 2F 樓板 z 150）四周本來就是開的（1F 樓層盒牆只到 z 108），線直接從這個開口出去，不用在牆上開孔
#   每個出口在模型外側桌面放一台有外接變壓器的 4 埠 USB 集線器（5 V 3 A）
OUTLET = {"S": Vector((0, -182)), "N": Vector((0, 182))}
ZT = 11.5          # 桌面（ASM_Ground z 9.9）上的線芯高度：出樓層盒後沿外牆／麵包板座端面垂下來，在桌面上走到集線器
for nm_, c in OUTLET.items():
    obj(f"電源出口_{'南' if nm_ == 'S' else '北'}_USB集線器", lambda bm, c=c: frame_box(bm, dict(W=lambda uu, vv: Vector((c.x + uu, c.y + vv, 0))), -22, 22, -12, 12, ZT - 1.6, ZT + 16.4), (0.25, 0.25, 0.3, 1))
POWER = []
# 3 台 OLED HUB：USB 轉杜邦（USB-A 公 → 5V 紅、GND 黑兩條杜邦母頭）
LANE = {"H5": ("S", 6.0, -156.0), "H7": ("S", -6.0, -156.0), "H6": ("N", -6.0, 156.0)}
for h in HUBS:
    side, lx, ly = LANE[h["id"]]; sg = 1 if side == "N" else -1; oc = OUTLET[side]
    Hp = simplify(h["pwr_cells"]); e = Hp[-1]
    zP, _ = lay_z(h["pwr_cells"], 0)
    v = Vector(D[h["pwr_side"]]); r0 = edge_pt(h, h["pwr_side"], -3.0)
    inside = [Vector((r0.x, r0.y, zP))] + [Vector((q.x, q.y, zP)) for q in Hp[1:]]
    outside = [Vector((e.x, sg * 121.0, zP)), Vector((e.x, sg * 126.0, 126.0)), Vector((e.x, sg * 126.0, ZT)), Vector((e.x, ly, ZT)), Vector((lx, ly, ZT)),
               Vector((lx, oc.y - sg * 11, ZT))]
    C3 = inside + outside
    lens = {}
    for k, nm in enumerate(("5V", "GND")):
        o = (k - 0.5) * PITCH; pin = h["pwr_pin"][nm]
        Co = offset2d(C3, o)
        pts = [Vector((pin.x, pin.y, Z_DEV_TOP)), Vector((pin.x, pin.y, Z_RISE)), Vector((Co[0].x, Co[0].y, Z_RISE))] + Co
        lens[nm] = curve(f"1F_{h['id']}_電源線_{nm}", pts, CCOL[nm])
    h["usb_len"] = max(lens.values()); h["pwr_route"] = [(round(q.x, 1), round(q.y, 1)) for q in Hp]
    h["pwr_fix"] = plan_fix(Hp, zP, h["id"] + "電源")
    POWER.append(dict(hub=h["id"], kind="USB 轉杜邦（5V／GND）", outlet=side, inside_mm=round(sum((inside[k + 1] - inside[k]).length for k in range(len(inside) - 1)) + (Z_RISE - Z_DEV_TOP) * 2, 1),
                      total_mm=round(h["usb_len"], 1), exit=[round(e.x, 1), round(sg * 121.0, 1)], path=path_txt([q.to_2d() for q in C3]), plug_runs=h["pwr_plug_runs"]))
# 4 台鏡頭 HUB：原始模型沒有畫 USB 線。設計：USB-A → USB-C 線從麵包板座外側端的開口（端牆 z 130.2 以上是開的）出座，沿外牆走到出口
CAM_USB = {
    "S": [(0, -142.3, 135), (0, -147, 135), (0, -147, 11.5), (0, -171, 11.5)],
    "W": [(-142.3, 0, 135), (-147, 0, 135), (-147, 0, 11.5), (-147, -161, 11.5), (-12, -161, 11.5), (-12, -171, 11.5)],
    "N": [(0, 142.3, 135), (0, 147, 135), (0, 147, 11.5), (0, 171, 11.5)],
    "E": [(142.3, 0, 135), (147, 0, 135), (147, 0, 11.5), (147, 161, 11.5), (6, 161, 11.5), (6, 171, 11.5)],
}
for pod, pl in CAM_USB.items():
    pts = [Vector(q) for q in pl]; L_ = curve(f"1F_鏡頭HUB_{pod}_USB線", pts, (0.18, 0.18, 0.2, 1), r=1.5)
    POWER.append(dict(hub=f"鏡頭 HUB {pod}", kind="USB-A → USB-C", outlet="S" if pod in "SW" else "N", inside_mm=None, total_mm=round(L_, 1),
                      exit=[round(pl[1][0], 1), round(pl[1][1], 1)], path=path_txt([Vector(q[:2]) for q in pl]), plug_runs=[]))
# 膠帶（一條物件）：10 mm 寬紙膠帶橫跨線排貼在封孔板頂面
def tapes(bm):
    for q, t, z, tag, onplug, ext in TAPES:
        if onplug: continue
        n = Vector((-t.y, t.x))
        frame_box(bm, dict(W=lambda uu, vv, q=q, t=t, n=n: (q + n * uu + t * vv).to_3d()), -max(ext[0], 3.3), max(ext[1], 3.3), -5, 5, z + R_W + 0.05, z + R_W + 0.25)
obj("1F_接線_固定膠帶", tapes, (0.97, 0.97, 0.9, 1))
for p in P: p["wire_len"] = max(p["cond_len"].values())

# ---------- 上方淨空：長條孔正上方（含母座＋線彎），到第一個既有零件的距離 ----------
others = [o for o in sc.objects if o.type == "MESH" and o not in made and o.visible_get() and not o.name.startswith("ASM_")
          and o.name not in ("1F_天花板", "1F_天花板封孔板", "1F_樓層")]
OB = {o.name: bvh(o) for o in others}
for p in P:
    zmin, who = 999.0, ""
    for q in rect_pts(p, -SLOT_U / 2 - 1.5, SLOT_U / 2 + 1.5, PH / 2 - PIN_ROW - SLOT_V / 2 - 1.5, PH / 2 - PIN_ROW + SLOT_V / 2 + 1.5, step=1.0):
        for n, b in OB.items():
            h = b.ray_cast(Vector((q.x, q.y, 117.7)), Z, 200)
            if h[0] is not None and h[0].z < zmin: zmin, who = h[0].z, n
    p["check"]["headroom_top"] = (round(zmin, 1), who)

# ---------- 干涉與鏡頭 ----------
EB = {o.name: bvh(o) for o in sc.objects if o.type == "MESH" and o not in made and o.visible_get() and not o.name.startswith("ASM_")}
inter = []
for ob in made:
    if "顯示區" in ob.name: continue
    t = bvh(ob); hits = [n for n, b in EB.items() if t.overlap(b)]
    if hits: inter.append(f"{ob.name} ↔ {', '.join(hits)}")
dg = bpy.context.evaluated_depsgraph_get(); winter = []
for w in WIRES:
    me = w.evaluated_get(dg).to_mesh(); M = w.matrix_world
    t = BVHTree.FromPolygons([M @ v.co for v in me.vertices], [f.vertices[:] for f in me.polygons])
    hits = [n for n, b in EB.items() if t.overlap(b)]
    if hits: winter.append(f"{w.name} ↔ {', '.join(hits)}")
# 導線之間：不同線排（不同 OLED／共用段／電源）的線芯互穿
wb = {}
for w in WIRES:
    me = w.evaluated_get(dg).to_mesh(); M = w.matrix_world
    wb[w.name] = (w.name.rsplit("_", 1)[0], BVHTree.FromPolygons([M @ v.co for v in me.vertices], [f.vertices[:] for f in me.polygons]))
ww = []
names_ = list(wb)
for i in range(len(names_)):
    for j in range(i + 1, len(names_)):
        ga, ba = wb[names_[i]]; gb_, bb_ = wb[names_[j]]
        if ga != gb_ and ba.overlap(bb_): ww.append(f"{names_[i]} ↔ {names_[j]}")
CAMS = {"N": 0.0, "W": 90.0, "E": -90.0, "S": 180.0}
occ = [b for n, b in EB.items() if "Lens" not in n and "HUB8735" not in n]
seen = []; min_ang = 180
for fl, dz in (("1F", 0.0), ("2F", 150.0)):
    for cn, rz in CAMS.items():
        Rz = Matrix.Rotation(math.radians(rz), 3, "Z"); cpos = Rz @ Vector((0, 92, 111 + dz))
        ax = Rz @ Matrix.Rotation(math.radians(-18), 3, "X") @ Vector((0, 0, -1))
        for p in P:
            vis = 0
            for ob in made:
                if not ob.name.startswith(f"1F_OLED穿孔_{p['id']}_") or ob.name.endswith(("排針", "杜邦母座")): continue
                M = ob.matrix_world
                for f in ob.data.polygons:
                    n = (M.to_3x3() @ f.normal).normalized()
                    for q in [M @ f.center] + [M @ ob.data.vertices[k].co for k in f.vertices]:
                        q = q + n * 0.05
                        if q.z > CEIL: continue
                        d = q - cpos; ang = math.degrees(ax.angle(d))
                        if fl == "1F": min_ang = min(min_ang, ang)
                        if ang > 65: continue
                        if not any(b.ray_cast(cpos, d.normalized(), d.length - 0.05)[0] is not None for b in occ): vis += 1
            if vis: seen.append(f"{fl}{cn}→{p['id']}（{vis} 點）")
# 逐像素：576×320 畫面、等立體角魚眼 f = 2.9821 mm、感光寬 5.6 mm（evac.py）。外框內每個像素打一條射線，先打到 OLED 才算看到
IW, IH, FL, SWD = 576, 320, 2.9821, 5.6; SC = IW / SWD
pix = []; pix_total = 0
for fl, dz in (("1F", 0.0), ("2F", 150.0)):
    for cn, rz in CAMS.items():
        Rz = Matrix.Rotation(math.radians(rz), 3, "Z"); cpos = Rz @ Vector((0, 92, 111 + dz))
        Rc = Rz @ Matrix.Rotation(math.radians(-18), 3, "X"); Rt = Rc.transposed()
        for p in P:
            obs = [ob for ob in made if ob.name.startswith(f"1F_OLED穿孔_{p['id']}_") and not ob.name.endswith(("排針", "杜邦母座"))]
            vs = [ob.matrix_world @ v.co for ob in obs for v in ob.data.vertices]
            uv = []
            for P3 in vs:
                q = Rt @ (P3 - cpos)
                if q.length < 1e-6: continue
                th = math.acos(max(-1, min(1, -q.z / q.length)))
                if th > math.radians(89): continue
                r = 2 * FL * math.sin(th / 2); ph = math.atan2(q.y, q.x)
                uv.append((IW / 2 + r * math.cos(ph) * SC, IH / 2 - r * math.sin(ph) * SC))
            if not uv: continue
            u0, u1 = max(0, int(min(t[0] for t in uv)) - 1), min(IW - 1, int(max(t[0] for t in uv)) + 1)
            v0, v1 = max(0, int(min(t[1] for t in uv)) - 1), min(IH - 1, int(max(t[1] for t in uv)) + 1)
            if u0 > u1 or v0 > v1: continue
            Bm = BVHTree.FromPolygons(vs, [tuple(b + i for i in f.vertices) for b, ob in zip(
                [sum(len(o.data.vertices) for o in obs[:k]) for k in range(len(obs))], obs) for f in ob.data.polygons])
            n = 0
            for u in range(u0, u1 + 1):
                for v in range(v0, v1 + 1):
                    xs_, ys_ = (u + 0.5 - IW / 2) / SC, (IH / 2 - v - 0.5) / SC; rr = math.hypot(xs_, ys_)
                    th = 2 * math.asin(min(1.0, rr / (2 * FL))); ph = math.atan2(ys_, xs_)
                    d = (Rc @ Vector((math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), -math.cos(th)))).normalized()
                    hm = Bm.ray_cast(cpos, d, 600)
                    if hm[0] is None: continue
                    if any((h := b.ray_cast(cpos, d, hm[3] - 0.05))[0] is not None for b in occ): continue
                    n += 1
            pix_total += n
            if n: pix.append(f"{fl}{cn}→{p['id']}（{n} 像素）")

# ---------- 邊中點與中心：最近候選位置（search_through_hole.py 的結果）與失敗原因 ----------
FAIL = [
    dict(id="N", J=(0, 99), nearest=(0.0, 66.0), offset=30.6, reason="模組只能放十字北臂（路口正中是鏡頭孔、環廊兩側是排線孔塞子）；長條孔正上方是麵包板座實心底座（z 115 起），沒有杜邦母座空間；且往下凸出 5 mm 會被 1F N 鏡頭拍到（離光軸約 37°）。有上方空間的最近位置在 91.6 mm 外（已是角落）"),
    dict(id="E", J=(99, 0), nearest=(66.0, 0.0), offset=30.6, reason="同 N（東臂、1F E 鏡頭）"),
    dict(id="S", J=(0, -99), nearest=(0.0, -66.0), offset=30.6, reason="同 N（南臂、1F S 鏡頭）"),
    dict(id="W", J=(-99, 0), nearest=(-66.0, 0.0), offset=30.6, reason="同 N（西臂、1F W 鏡頭）"),
]

# ---------- 報告 ----------
def dn(v): return {(0, 1): "北", (0, -1): "南", (1, 0): "東", (-1, 0): "西"}[(round(v.x), round(v.y))]
L = ["1F 天花板 OLED「穿孔＋雙面膠」方案模擬  —  build_through_hole.py", "",
     f"疊層：玻璃底 z {Z_GLASS0:.1f}（往下凸出 {CEIL - Z_GLASS0:.1f} mm）、PCB {Z_PCB0:.1f}～{Z_BACK:.1f}、雙面膠 {TAPE} mm、塑膠座 {Z_BACK:.1f}～{Z_SP1:.1f}（伸進孔 {Z_SP1 - CEIL:.1f} mm）、杜邦母座頂 z {Z_DUP1:.1f}、線彎到 z {Z_DUP1 + WIRE_BEND:.1f}",
     f"長條孔 {SLOT_U}×{SLOT_V} mm，貫穿 1F_天花板與封孔板頂板（z 108～117.6）", "",
     "路口  顯示區中心          離路口  畫面上方  孔中心            孔上方第一個零件 z       HUB  位址   線長"]
table = []
for p in P:
    off = (p["aa"].to_2d() - Vector(p["J"])).length; c = p["check"]
    L.append(f"{p['id']:3s}  ({p['aa'].x:6.1f},{p['aa'].y:6.1f})  {off:5.1f}   {dn(p['u'])}       ({p['slot'].x:6.1f},{p['slot'].y:6.1f})  {c['headroom_top'][0]:6.1f} {c['headroom_top'][1]:16s}  {p['hub']}    {p['addr']}  {p['wire_len'] / 10:.1f} cm")
    table.append(dict(id=p["id"], junction=list(p["J"]), feasible=True, mount="tape+through_hole", module="0.96", pcb_center=list(p["center"]),
                      active_center=[round(p["aa"].x, 1), round(p["aa"].y, 1)], offset_mm=round(off, 1), protrusion_mm=round(CEIL - Z_GLASS0, 1),
                      screen_up=dn(p["u"]), screen_right=dn(p["r"]), slot_center=[round(p["slot"].x, 2), round(p["slot"].y, 2)],
                      slot_size=[SLOT_U, SLOT_V], slot_long_axis=dn(p["r"]) + "－" + dn(-p["r"]), hub=p["hub"], bus="Wire", addr=p["addr"],
                      wire_cm=round(p["wire_len"] / 10, 1)))
    if p.get("cover_area"): table[-1]["covers_from_below_mm2"] = p["cover_area"]
    table[-1]["bus"] = "Wire"; table[-1]["resolder_to_0x3D"] = p["addr"] == "0x3D"
    if p.get("ring_cover_len"): table[-1]["arm_slot_covered_length_mm"] = p["ring_cover_len"]
    if p.get("slot_plug"): table[-1]["slot_through"] = "十字臂插槽塞子（封孔板的一部分）"
L += ["", "中心模組從下方蓋住的面積（mm²，模組本體 27.8×27.3）：" + "、".join(f"{k} {v}" for k, v in next(p for p in P if p.get("cover"))["cover_area"].items())]
for p in P:
    if p.get("cover_area") and p["id"] != "C":
        L.append(f"{p['id']} 模組從下方蓋住（mm²）：" + "、".join(f"{k} {v}" for k, v in p["cover_area"].items())
                 + (f"；自己那支十字臂的插槽（塞子全長約 34 mm）沿走廊方向被蓋住 {p['ring_cover_len']} mm，長孔 {SLOT_U}×{SLOT_V} mm 開在該塞子上" if p.get("ring_cover_len") else ""))
L += ["", "方案 D：3 台只驅動 OLED 的 HUB（只用 Wire；0x3C＋0x3D），不用 TCA9548A、不用 Wire1"]
for h in HUBS:
    mine = [p for p in P if p["hub"] == h["id"]]
    L.append(f"  {h['id']}：板子中心 {h['center']}（{h['size'][0]}×{h['size'][1]} mm，架高 4 mm），底下塞子點數 {h['check']['plug']}、上方障礙點數 {h['check']['obstacle']}（應為 0）；"
             + "、".join(f"{p['id']}＝{p['addr']}（{p['wire_len'] / 10:.1f} cm）" for p in mine)
             + f"；電源線（USB 轉杜邦 5V／GND）從{dict(N='北', E='東', S='南', W='西')[h['pwr_side']]}側出線，走 {h['usb_len'] / 10:.1f} cm 到樓層盒外緣；"
             + "短邊外淨空 " + "、".join(f"{dict(N='北', E='東', S='南', W='西')[k]} {v} mm" for k, v in h["end_clear"].items()) + "（USB-C 插頭需 ≥ 15 mm）")
L.append(f"  HUB 板之間最小間距：{min(gaps_h)[0]} mm（{min(gaps_h)[1]}–{min(gaps_h)[2]}）")
L.append("  要改焊成 0x3D（背面電阻 0x78 → 0x7A）的只有：" + "、".join(p["id"] for p in P if p["addr"] == "0x3D") + "；角落 4 塊都維持出廠 0x3C")
for h in HUBS:
    table.append(dict(id=h["id"], role="只驅動 OLED 的 HUB-8735（Wire）", board_center=list(h["center"]), board_size=list(h["size"]),
                      oleds={p["id"]: p["addr"] for p in P if p["hub"] == h["id"]}, power="USB 轉杜邦 5V/GND（短邊淨空不足，USB-C 插不進）",
                      power_exit_side=h["pwr_side"], power_route=[list(map(float, t)) for t in h["pwr_route"]], power_cm=round(h["usb_len"] / 10, 1), end_clearance_mm=h["end_clear"]))
L += ["", "模組四周 0.6 mm 內碰到塞子／鏡頭孔／銷孔（中心只查貫穿孔）：" + ", ".join(f"{p['id']}={p['check']['bad']}" for p in P) + "（應為 0）",
      "模組下方有牆或擋條（含 0.4 mm）：" + ", ".join(f"{p['id']}={p['check']['below']}" for p in P) + "（應為 0）",
      "長條孔（含 0.8 mm 壁）碰到排線溝／塞子／孔：" + ", ".join(f"{p['id']}={p['check']['slot_bad']}" for p in P) + "（應為 0；孔處天花板是 108～116 實心＋封孔板頂板 116～117.6）",
      f"杜邦母座＋線彎需要到 z {Z_DUP1 + WIRE_BEND:.1f}；孔上方第一個零件：" + ", ".join(f"{p['id']} z {p['check']['headroom_top'][0]}（{p['check']['headroom_top'][1]}）" for p in P),
      f"新零件與既有零件互穿：{len(inter)}（應為 0）" + "".join("\n  " + s for s in inter),
      f"杜邦線與既有零件互穿：{len(winter)}（應為 0）" + "".join("\n  " + s for s in winter),
      f"不同線排的導線互穿：{len(ww)}（應為 0）" + "".join(chr(10) + "  " + s for s in ww[:20]),
      f"鏡頭（576×320 逐像素，判定標準）：8 台 × {len(P)} 塊共 {pix_total} 像素看得到 OLED（應為 0）" + ("：" + "、".join(pix) if pix else ""),
      f"鏡頭（參考：65° 圓錐＋頂點射線，比實際長方形畫面寬）：{len(seen)} 組" + ("：" + "、".join(seen) if seen else "") + f"；1F 鏡頭軸到任一取樣點的最小夾角 {min_ang:.0f}°",
      f"非流形邊：1F_天花板 {NM0[0]}→{NM1[0]}、封孔板 {NM0[1]}→{NM1[1]}",
      f"走廊淨高：地板 z 8 到玻璃底 z {Z_GLASS0:.1f} = {Z_GLASS0 - 8:.1f} mm（人偶約 40 mm）"]
# ---------- 閘門塊 Gate_Plug：99.5 → 94 mm（2026-11-10 使用者決定） ----------
#   形狀：開口朝下的空心盒（側壁 1.6／2.8 mm、頂板 z 97.5～99.5 有開孔），直接放在走廊地板上，側面靠走廊牆定位；
#   沒有插進天花板或地板槽的榫頭。→ 從「頂端」減高：z > 50 的頂點全部往下移 5.5 mm（頂板厚度、開孔、側壁、底面外框都不變）
GATE_H0, GATE_H1 = 99.5, 94.0
gate_meshes = {}
for gname in ("Gate_Plug", "Gate_Plug_spare", "Gate_Plug_G36", "Gate_Plug_G42"):
    go = bpy.data.objects.get(gname)
    if go is None or go.data.name in gate_meshes: continue
    me = go.data; z0 = max(v.co.z for v in me.vertices)
    if abs(z0 - GATE_H0) < 0.01:
        for v in me.vertices:
            if v.co.z > 50: v.co.z -= GATE_H0 - GATE_H1
        me.update()
    zs = sorted(set(round(v.co.z, 2) for v in me.vertices))
    xy = (round(max(v.co.x for v in me.vertices) * 2, 1), round(max(v.co.y for v in me.vertices) * 2, 1))
    gate_meshes[me.name] = (go, zs, xy)
L += ["", f"閘門塊 Gate_Plug：高 {GATE_H0} → {GATE_H1} mm，從頂端減高（頂板與開孔整個下移 5.5 mm；底面外框與側壁厚度不變）"]
for mn, (go, zs, xy) in gate_meshes.items():
    L.append(f"  {go.name}（網格 {mn}）：外框 {xy[0]}×{xy[1]} mm，頂點高度 {zs}，非流形邊 {nonmanifold(go)}")
# 放到 1F 的 12 段走廊中點（Floor1_New 的 G36＝環廊型、G42＝十字臂型），量和 9 塊 OLED 的最小間隙
G36, G42 = bpy.data.objects["Gate_Plug_G36"].data, bpy.data.objects["Gate_Plug_G42"].data
spots = [(f"環廊 ({sx * 51},{sy * 99})", G36, (sx * 51, sy * 99), 0) for sx in (-1, 1) for sy in (-1, 1)] + \
        [(f"環廊 ({sx * 99},{sy * 51})", G36, (sx * 99, sy * 51), 90) for sx in (-1, 1) for sy in (-1, 1)] + \
        [(f"十字臂 ({sx * 51},0)", G42, (sx * 51, 0), 0) for sx in (-1, 1)] + [(f"十字臂 (0,{sy * 51})", G42, (0, sy * 51), 90) for sy in (-1, 1)]
oled_pts = {}
for p in P:
    pts = []
    for ob in made:
        if not ob.name.startswith(f"1F_OLED穿孔_{p['id']}_") or ob.name.endswith(("排針", "杜邦母座")): continue
        M = ob.matrix_world
        for f in ob.data.polygons:
            pts.append(M @ f.center); pts += [M @ ob.data.vertices[k].co for k in f.vertices]
    oled_pts[p["id"]] = pts
gate_lines = []; gate_min = 1e9
for lab, gme, (gx, gy), rot in spots:
    M = Matrix.Translation((gx, gy, 8.0)) @ Matrix.Rotation(math.radians(rot), 4, "Z")
    gb = BVHTree.FromPolygons([M @ v.co for v in gme.vertices], [f.vertices[:] for f in gme.polygons])
    gtop = 8.0 + max(v.co.z for v in gme.vertices)
    best = (1e9, "")
    for oid, pts in oled_pts.items():
        for q in pts:
            h = gb.find_nearest(q)
            if h[0] is not None and h[3] < best[0]: best = (h[3], oid)
    hits = [n for n, b in EB.items() if n.startswith("1F_") and n not in ("1F_樓層",) and gb.overlap(b)]
    gate_min = min(gate_min, best[0])
    gate_lines.append(f"  {lab}（{'G36 環廊型' if gme is G36 else 'G42 十字臂型'}，頂 z {gtop:.1f}）：離最近 OLED（{best[1]}）{best[0]:.2f} mm" + (f"；另碰到 {', '.join(hits)}" if hits else ""))
L.append(f"閘門塊放在 12 段走廊中點時，和 9 塊 OLED 的最小間隙：{gate_min:.2f} mm（應 ≥ 0.5；OLED 玻璃底 z {Z_GLASS0:.1f}，閘門頂 z {8.0 + GATE_H1:.1f}）")
L += gate_lines
# ---------- 接線表（36 條 OLED 導線＋分接板共用段＋電源） ----------
STD = (100, 200, 300, 400)
def dupont(mm):   # 需要長度＝走線長＋兩端各 15 mm 服務環；挑最短的標準長度
    need = mm + 30
    return need, next((s for s in STD if s >= need), None)
WL = ["外接線接線表（build_through_hole.py 自動產生；座標 mm，z 為線芯中心高度）", "",
      "顏色：紅 VCC／3V3／5V、黑 GND、黃 SCL、綠 SDA。OLED 排針順序（從下方看、排針在上）由左到右 GND、VCC、SCL、SDA。",
      "HUB-8735 Ultra：SDA＝Pin3、SCL＝Pin4（Wire）；3V3 與 GND 用板上排針。模型中 HUB 排針位置是示意排列，接線時以板上絲印為準。",
      "長度＝模型走線長（OLED 母座頂 → 終點）；建議長度＝走線長＋兩端各 15 mm 服務環（角落另加麵包板座內約 60 mm）。", ""]
for p in P:
    h = HUBD.get(p["hub"]); s = p["slot"]
    WL.append(f"■ OLED {p['id']}（{p['addr']}，{'鏡頭 HUB ' + p['hub'] if 'pod' in p else p['hub']}）  長孔 ({s.x:.1f},{s.y:.1f})  線排高度 z {p['z']:.1f}（第 {p['layer'] + 1} 層）")
    WL.append(f"   路徑（線排中心）：{path_txt(p['path'])}" + ("（→ 伸進麵包板座內側端窗口，z 132）" if "pod" in p else "（→ 分接板）" if p.get("split") or p["end_kind"] == "board" else f"（→ 板邊豎起到 z {Z_RISE:.1f} → 插 {p['hub']} 排針）"))
    for nm, _c in COND:
        L_ = p["cond_len"][nm]; extra = 60 if "pod" in p else 0; need, std = dupont(L_ + extra)
        if "pod" in p: end = f"鏡頭 HUB {p['hub']} 的 {PIN_DESC[HUBPIN[nm]]}（{p['pod']} 麵包板座內，經座內側端窗口；母－公杜邦，公頭插麵包板同一列）"
        elif p["end_kind"] == "board": end = f"{h['id']} 分接板輸入 {'A' if p['addr'] == '0x3C' else 'B'} 的 {nm} 公針（再由共用段接 {h['id']} {PIN_DESC[HUBPIN[nm]]}）"
        else: end = f"{h['id']} 的 {PIN_DESC[HUBPIN[nm]]} 排針（母－母杜邦）"
        p.setdefault("cond_rows", []).append(dict(conductor=nm, start=f"OLED {p['id']} 排針 {nm}", end=end, length_mm=round(L_, 1), need_mm=round(need, 1), dupont_mm=std))
        WL.append(f"   {nm:3s}  起點 OLED {p['id']} 排針 {nm} → 終點 {end}；走線 {L_:.0f} mm，需 {need:.0f} mm → {std or '超過 400'} mm 杜邦線")
    pr = p["plug_runs"]
    WL.append("   壓到塞子頂面：" + ("無" if not pr else "、".join(f"({r['start'][0]},{r['start'][1]})→({r['end'][0]},{r['end'][1]}) {r['mm']} mm" + ("（長孔本身就開在這個十字臂插槽塞子上，無法避免）" if (Vector(r['start']) - s.to_2d()).length < 9 else "（繞不開）") for r in pr)))
    nt = sum(1 for f in p["fix"] if f["tape"]); ns = [f["at"] for f in p["fix"] if not f["tape"]]
    WL.append(f"   固定：母座出孔後 15 mm 留服務環（不貼）；之後 {nt} 處 10 mm 紙膠帶橫貼在封孔板頂面（轉角各一、直段每 40 mm）" + (f"；在塞子頂面上不貼的點 {ns}" if ns else "")
              + ("；進窗口前用 1 段膠帶貼在麵包板座側牆外面" if "pod" in p else ""))
    WL.append("")
for h in HUBS:
    if h.get("common"):
        cm = h["common"]; bd = h["board"]
        WL.append(f"■ {h['id']} 分接板（洞洞板 20×14 mm，泡棉膠貼封孔板頂面，中心 ({bd['center'].x:.0f},{bd['center'].y:.0f})，{'沿 x 長' if bd['hx'] > bd['hy'] else '沿 y 長'}；位置＝兩條 OLED 線＋共用段加權長度總和最小處）")
        WL.append(f"   板上：3 組 4 pin 直角公排針（輸入 A、輸入 B、輸出），同名腳背面焊錫連通（GND↔GND、VCC↔VCC、SCL↔SCL、SDA↔SDA），等於把兩塊 OLED 並聯在同一組 SDA／SCL／3V3／GND 上")
        WL.append(f"   共用段路徑：{path_txt(cm['path'])} → 板邊豎起到 z {Z_RISE:.1f} → 插 {h['id']} 排針")
        for nm, _c in COND:
            L_ = cm["len"][nm]; need, std = dupont(L_)
            WL.append(f"   {nm:3s}  起點 分接板輸出 {nm} → 終點 {h['id']} {PIN_DESC[HUBPIN[nm]]}；走線 {L_:.0f} mm，需 {need:.0f} mm → {std} mm 杜邦線")
        WL.append("   壓到塞子頂面：" + ("無" if not cm["plug_runs"] else str(cm["plug_runs"])))
        WL.append(f"   固定：分接板兩側各 1 條 2.5×100 mm 束線帶把進出的線排束在一起；共用段 {sum(1 for f in cm['fix'] if f['tape'])} 處膠帶；豎起段用 1 條束線帶綁在最近的銅柱上")
        WL.append("")
WL.append("■ 電源（7 台 HUB 都用 USB 供電，集中到南、北 2 個出口）")
for pw in POWER:
    WL.append(f"   {pw['hub']}：{pw['kind']}，出口 {'南' if pw['outlet'] == 'S' else '北'}；模型走線 {pw['total_mm'] / 10:.1f} cm" + (f"（設備層內 {pw['inside_mm'] / 10:.1f} cm）" if pw["inside_mm"] else "（另加麵包板座內一段，原始模型沒畫鏡頭 HUB 的 USB 座位置，預留 10 cm）")
              + f"；離開樓層盒處 {pw['exit']}；路徑 {pw['path']}" + ("；壓到塞子頂面 " + str(pw["plug_runs"]) if pw["plug_runs"] else ""))
open(os.path.join(OUT, "接線表.txt"), "w", encoding="utf-8").write("\n".join(WL))
ntape = sum(1 for T in TAPES if not T[4]); nskip = sum(1 for T in TAPES if T[4]); none_side = sum(1 for T in TAPES if not T[4] and 0 in T[5])
L += ["", "接線設計（詳見 接線表.txt）：",
      f"  36 條 OLED 導線＋{sum(1 for h in HUBS if h.get('common')) * 4} 條分接板共用段＋{len(HUBS) * 2} 條 OLED HUB 電源杜邦線＋4 條鏡頭 HUB USB 線；固定膠帶 {ntape} 處（其中 {none_side} 處只能貼一側；落在塞子頂面而不貼的點 {nskip} 處）",
      "  每塊 OLED 線排離開長孔後壓到塞子頂面：" + "、".join(f"{p['id']} {sum(r['mm'] for r in p['plug_runs'])} mm" for p in P) + "（N／E／S／W 的長孔本身就開在十字臂插槽塞子上）",
      "  線排疊層：" + "、".join(f"{p['id']} z {p['z']:.1f}" for p in P),
      "  最長導線：" + "、".join(f"{p['id']} {max(p['cond_len'].values()) / 10:.1f} cm" for p in P)]
for p, t in zip(P, table):
    t["wiring"] = dict(layer_z=round(p["z"], 1), path=[[round(q.x, 1), round(q.y, 1)] for q in p["path"]], conductors=p["cond_rows"],
                       plug_crossings=p["plug_runs"], fixings=p["fix"], end=("鏡頭 HUB 麵包板座窗口" if "pod" in p else "分接板" if (p.get("split") or p["end_kind"] == "board") else "HUB 排針"))
for t in table:
    h = HUBD.get(t["id"])
    if h is None: continue
    t["bus_side"] = h["bus_side"]; t["bus_pins"] = {k: [round(v.x, 2), round(v.y, 2)] for k, v in h["bus_pin"].items()}
    t["power_pins"] = {k: [round(v.x, 2), round(v.y, 2)] for k, v in h["pwr_pin"].items()}
    if h.get("board"):
        bd = h["board"]; t["splitter_board"] = dict(center=[bd["center"].x, bd["center"].y], size=[bd["hx"] * 2, bd["hy"] * 2],
                                                     common_len_mm={k: round(v, 1) for k, v in h["common"]["len"].items()}, common_path=[[q.x, q.y] for q in h["common"]["path"]])
table.append(dict(id="POWER", outlets={k: [v.x, v.y] for k, v in OUTLET.items()}, cables=POWER))
open(os.path.join(OUT, "檢查報告.txt"), "w", encoding="utf-8").write("\n".join(L))
json.dump(table, open(os.path.join(OUT, "placements.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n".join(L))
for o in sc.objects: o.select_set(False)
for o, fn in ((ceil, "1F_天花板_穿孔.stl"), (lid, "1F_天花板封孔板_穿孔.stl")):
    o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.wm.stl_export(filepath=os.path.join(OUT, fn), export_selected_objects=True, apply_modifiers=True); o.select_set(False)
for go, fn in ((bpy.data.objects["Gate_Plug_G36"], "閘門塊_G36環廊型_94mm.stl"), (bpy.data.objects["Gate_Plug_G42"], "閘門塊_G42十字臂型_94mm.stl"),
               (bpy.data.objects["Gate_Plug"], "閘門塊_Gate_Plug舊版型_94mm.stl")):
    tmp = bpy.data.objects.new("_gate_export", go.data); sc.collection.objects.link(tmp)
    for o in sc.objects: o.select_set(False)
    tmp.select_set(True); bpy.context.view_layer.objects.active = tmp
    bpy.ops.wm.stl_export(filepath=os.path.join(OUT, fn), export_selected_objects=True, apply_modifiers=True)
    bpy.data.objects.remove(tmp, do_unlink=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "fire_model_oled_through_hole.blend"), copy=True)
