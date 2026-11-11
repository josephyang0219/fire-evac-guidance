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
    dict(id="NW", J=(-99, 99), center=(-97.0, 100.0), up="E", hub="N", addr="0x3D",
         route=[(-95.0, 100.0), (-95.0, 45.0), (-4.0, 45.0), (-4.0, 49.0)]),       # 先往西繞開房間角的支撐柱
    dict(id="NE", J=(99, 99), center=(100.0, 97.0), up="S", hub="E", addr="0x3D",
         route=[(100.0, 92.0), (45.0, 92.0), (45.0, 4.0), (49.0, 4.0)]),
    dict(id="SE", J=(99, -99), center=(99.0, -101.0), up="S", hub="S", addr="0x3D",
         route=[(99.0, -32.0), (4.0, -32.0), (4.0, -45.0), (4.0, -49.0)]),   # 先沿東側環廊往北，避開 SE 房間頂上的第 5 台 HUB
    dict(id="SW", J=(-99, -99), center=(-100.0, -97.0), up="N", hub="W", addr="0x3D",
         route=[(-100.0, -40.0), (-45.0, -40.0), (-45.0, -4.0), (-49.0, -4.0)]),
    # 中心（2026-11-10 使用者同意：模組可以從下方蓋住十字臂插槽塞子的一部分）。search_center.py 比較三種長孔位置後，
    #   選長孔完全落在路口中央實心區（x −9～6、y −9～6）的位置：不切任何塞子或排線溝，代價是顯示區往北偏 7.65 mm
    dict(id="C", J=(0, 0), center=(0.0, 5.5), up="S", hub="H5", addr="TCA9548A ch0／0x3C", cover=True, route=None),
    # 邊中點（2026-11-10 定稿，arm_inward/ 的 s = 50）：十字臂中點，顯示區離邊中點 50 mm、離中心 49 mm；排針朝中心，
    #   長孔過了麵包板座朝中心的一端（離中心 47 mm），穿過十字臂插槽的塞子（slot_plug）。576×320 逐像素：鏡頭看不到
    dict(id="N", J=(0, 99), center=(0.0, 46.85), up="S", hub="H5", addr="TCA9548A ch1／0x3C", cover=True, slot_plug=True, route=None),
    dict(id="E", J=(99, 0), center=(46.85, 0.0), up="W", hub="H5", addr="TCA9548A ch2／0x3C", cover=True, slot_plug=True, route=None),
    dict(id="S", J=(0, -99), center=(0.0, -46.85), up="N", hub="H5", addr="TCA9548A ch3／0x3C", cover=True, slot_plug=True, route=None),
    dict(id="W", J=(-99, 0), center=(-46.85, 0.0), up="E", hub="H5", addr="TCA9548A ch4／0x3C", cover=True, slot_plug=True, route=None),
]
# 第 5 台 HUB-8735（只驅動 OLED）與 TCA9548A I²C 多工器：設備層裡避開麵包板座、支撐柱、塞子頂面與各長條孔的最大空位
#   search_hub5_rects.py（依定稿的 9 個長孔重算）：最大空位只有 44×31 mm（SW 房間頂）與 30×44 mm（SW 房間西側）→ 連 170 孔迷你麵包板 47×35 都放不下
H5 = dict(center=(-52.0, -84.0), size=(40.5, 27.0), name="HUB5")        # HUB-8735 Ultra 板子約 40.5×27（由模型量得）
MUX = dict(center=(-30.0, 23.0), size=(30.5, 17.8), name="TCA9548A")    # 中心西北側空位；往北移 5 mm，和 W 臂長孔之間留出餘裕
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

# ---------- 設備層走線：1 mm 網格，障礙＝封孔板頂面以上 12 mm 內有既有零件、其他長條孔的母座、HUB5／多工器 ----------
from collections import deque
HUB_COLOR = {"N": (0.9, 0.2, 0.2, 1), "E": (0.2, 0.7, 0.2, 1), "S": (0.95, 0.75, 0.1, 1), "W": (0.6, 0.3, 0.9, 1), "H5": (0.1, 0.8, 0.85, 1)}
obst_objs = [o for o in sc.objects if o.type == "MESH" and o.visible_get() and not o.name.startswith("ASM_")
             and o.name not in ("1F_天花板", "1F_天花板封孔板", "1F_樓層") and o not in made and (o.name.startswith("1F_") or o.name.startswith("2F_"))]
vs_, fs_ = [], []
dg0 = bpy.context.evaluated_depsgraph_get()
for o in obst_objs:
    me = o.evaluated_get(dg0).to_mesh(); M = o.matrix_world; b = len(vs_)
    vs_ += [M @ v.co for v in me.vertices]; fs_ += [tuple(b + i for i in f.vertices) for f in me.polygons]
B_obst = BVHTree.FromPolygons(vs_, fs_)
GX = [x for x in range(-117, 118)]; NG = len(GX)
blocked = [[False] * NG for _ in GX]
for i, x in enumerate(GX):
    for j, y in enumerate(GX):
        h = B_obst.ray_cast(Vector((x, y, 105.0)), Z, 24.65)     # 從天花板下方往上打，才不會從零件內部起算而漏掉（例如麵包板座側牆）
        if h[0] is not None and h[0].z > 107.9: blocked[i][j] = True
def box_cells(cx, cy, hx, hy, grow):
    return [(i, j) for i, x in enumerate(GX) for j, y in enumerate(GX) if abs(x - cx) <= hx + grow and abs(y - cy) <= hy + grow]
def dilate(cells, r=2):
    out = set()
    for i, j in cells:
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if 0 <= i + di < NG and 0 <= j + dj < NG: out.add((i + di, j + dj))
    return out
base_block = set((i, j) for i in range(NG) for j in range(NG) if blocked[i][j])
base_block = dilate(base_block, 2)
dev_cells = set(box_cells(*H5["center"], H5["size"][0] / 2, H5["size"][1] / 2, 1)) | set(box_cells(*MUX["center"], MUX["size"][0] / 2, MUX["size"][1] / 2, 1))
def slot_cells(p, grow=3):
    long_x = abs(p["r"].x) > 0.5; hx, hy = (SLOT_U / 2, SLOT_V / 2) if long_x else (SLOT_V / 2, SLOT_U / 2)
    return set(box_cells(p["slot"].x, p["slot"].y, hx, hy, grow))
def route(start, goal_box, extra_block):
    blk = base_block | extra_block
    gi = lambda v: (int(round(v[0])) + 117, int(round(v[1])) + 117)
    si = gi(start); cx, cy, hx, hy = goal_box
    goals = set(c for c in box_cells(cx, cy, hx, hy, 3) if c not in blk) - set(box_cells(cx, cy, hx, hy, 1.5))
    prev = {si: None}; q = deque([si]); end = None
    while q:
        c = q.popleft()
        if c in goals: end = c; break
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c[0] + di, c[1] + dj)
            if 0 <= n[0] < NG and 0 <= n[1] < NG and n not in prev and (n not in blk or max(abs(n[0] - si[0]), abs(n[1] - si[1])) <= 6):
                prev[n] = c; q.append(n)
    assert end is not None, f"no route from {start}"
    path = []; c = end
    while c is not None: path.append((GX[c[0]], GX[c[1]])); c = prev[c]
    path.reverse(); simp = [path[0]]
    for k in range(1, len(path) - 1):
        a, b, c2 = simp[-1], path[k], path[k + 1]
        if (b[0] - a[0]) * (c2[1] - b[1]) != (b[1] - a[1]) * (c2[0] - b[0]): simp.append(b)
    simp.append(path[-1]); return simp
mux_box = (*MUX["center"], MUX["size"][0] / 2, MUX["size"][1] / 2)
for p in P:
    if p["route"] is not None: continue
    others_slots = set().union(*[slot_cells(o) for o in P if o is not p])
    pts2 = route((p["slot"].x, p["slot"].y), mux_box, others_slots | dev_cells)
    p["route"] = [(float(x), float(y)) for x, y in pts2[1:]] + [MUX["center"]]
    p["end_z"] = Z_DEV_TOP + 1.5
h5_route = route((H5["center"][0], H5["center"][1] + H5["size"][1] / 2 + 2.5), mux_box,
                 set().union(*[slot_cells(o) for o in P]) | set(box_cells(*H5["center"], H5["size"][0] / 2, H5["size"][1] / 2, 1)))

# ---------- 第 5 台 HUB 與多工器（簡化外形：板子＋排針杜邦區） ----------
for dev, col in ((H5, (0.15, 0.55, 0.3, 1)), (MUX, (0.2, 0.3, 0.75, 1))):
    cx, cy = dev["center"]; hx, hy = dev["size"][0] / 2, dev["size"][1] / 2
    pd = dict(W=lambda uu, vv, cx=cx, cy=cy: Vector((cx + uu, cy + vv, 0)))
    obj(f"1F_{dev['name']}_板", lambda bm, pd=pd, hx=hx, hy=hy: frame_box(bm, pd, -hx, hx, -hy, hy, Z_DEV0, Z_DEV0 + 1.6), col)
    def posts(bm, pd=pd, hx=hx, hy=hy):
        for sx in (-1, 1):
            for sy in (-1, 1): frame_box(bm, pd, sx * (hx - 2.5) - 1.2, sx * (hx - 2.5) + 1.2, sy * (hy - 2.5) - 1.2, sy * (hy - 2.5) + 1.2, 117.62, Z_DEV0)
    obj(f"1F_{dev['name']}_銅柱", posts, (0.8, 0.7, 0.3, 1))
    obj(f"1F_{dev['name']}_排針杜邦區", lambda bm, pd=pd, hx=hx, hy=hy: frame_box(bm, pd, -hx + 1, hx - 1, -hy + 1, -hy + 4, Z_DEV0 + 1.6, Z_DEV_TOP), (0.12, 0.12, 0.12, 1))
pts = [Vector((H5["center"][0], H5["center"][1] + H5["size"][1] / 2 - 3, Z_DEV_TOP + 1.5)), Vector((h5_route[0][0], h5_route[0][1], Z_DEV_TOP + 1.5)),
       Vector((h5_route[0][0], h5_route[0][1], 119.5))] + [Vector((x, y, 119.5)) for x, y in h5_route[1:]]
pts += [Vector((pts[-1].x, pts[-1].y, Z_DEV_TOP + 1.5)), Vector((*MUX["center"], Z_DEV_TOP + 1.5))]
cu = bpy.data.curves.new("1F_HUB5_I2C主線", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 1.3; cu.bevel_resolution = 2
sp = cu.splines.new("POLY"); sp.points.add(len(pts) - 1)
for k, q in enumerate(pts): sp.points[k].co = (q.x, q.y, q.z, 1)
h5wire = bpy.data.objects.new("1F_HUB5_I2C主線", cu); coll.objects.link(h5wire); h5wire.color = (0.1, 0.8, 0.85, 1)
cu.materials.append(mat("杜邦線H5_mat", (0.1, 0.8, 0.85, 1)))
H5["wire_len"] = sum((pts[k + 1] - pts[k]).length for k in range(len(pts) - 1)); H5["route"] = h5_route

# 第 5 台 HUB／多工器底下：不能壓在塞子頂面（排煙孔、排線孔要能拆）、上方到 2F 樓板要放得下
for dev in (H5, MUX):
    cx, cy = dev["center"]; hx, hy = dev["size"][0] / 2, dev["size"][1] / 2; nplug = 0; nobs = 0
    for x in [cx - hx + k * 0.5 for k in range(int(2 * hx / 0.5) + 1)]:
        for y in [cy - hy + k * 0.5 for k in range(int(2 * hy / 0.5) + 1)]:
            h = B_lid.ray_cast(Vector((x, y, 100)), Z, 30)
            if h[0] is not None and h[0].z < 109: nplug += 1
            h = B_obst.ray_cast(Vector((x, y, 105.0)), Z, Z_DEV_TOP - 105.0 + 1)
            if h[0] is not None and h[0].z > 107.9: nobs += 1
    dev["check"] = dict(plug=nplug, obstacle=nobs)

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
    # 線：母座頂 → 彎到封孔板頂面上 1 mm → 沿頂面走到負責 HUB 座的內側端窗口（z 127～140）
    s = p["slot"]; pts = [Vector((s.x, s.y, Z_DUP1)), Vector((s.x, s.y, Z_DUP1 + 2.5))]
    lay = 119.5
    first = Vector((*p["route"][0], 0)); d0 = (first - s.to_2d().to_3d()); d0.z = 0
    pts.append(Vector((s.x, s.y, Z_DUP1 + 2.5)) + d0.normalized() * WIRE_BEND)
    pts[-1].z = lay
    for x, y in p["route"][:-1]: pts.append(Vector((x, y, lay)))
    ez = p.get("end_z", 132.0)
    ex, ey = p["route"][-1]; pts.append(Vector((pts[-1].x, pts[-1].y, ez))); pts.append(Vector((ex, ey, ez)))
    cu = bpy.data.curves.new(f"{t}_杜邦線", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 1.3; cu.bevel_resolution = 2
    sp = cu.splines.new("POLY"); sp.points.add(len(pts) - 1)
    for k, q in enumerate(pts): sp.points[k].co = (q.x, q.y, q.z, 1)
    wob = bpy.data.objects.new(f"{t}_杜邦線", cu); coll.objects.link(wob); wob.color = HUB_COLOR[p["hub"]]
    cu.materials.append(mat(f"杜邦線{p['hub']}_mat", HUB_COLOR[p["hub"]]))
    p["wire_obj"] = wob; p["wire_len"] = sum((pts[k + 1] - pts[k]).length for k in range(len(pts) - 1))

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
for p in P + [dict(wire_obj=h5wire)]:
    w = p["wire_obj"]; me = w.evaluated_get(dg).to_mesh(); M = w.matrix_world
    t = BVHTree.FromPolygons([M @ v.co for v in me.vertices], [f.vertices[:] for f in me.polygons])
    hits = [n for n, b in EB.items() if t.overlap(b)]
    if hits: winter.append(f"{w.name} ↔ {', '.join(hits)}")
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
    if p["hub"] == "H5": table[-1]["bus"] = "Wire→TCA9548A"
    if p.get("ring_cover_len"): table[-1]["arm_slot_covered_length_mm"] = p["ring_cover_len"]
    if p.get("slot_plug"): table[-1]["slot_through"] = "十字臂插槽塞子（封孔板的一部分）"
L += ["", "中心模組從下方蓋住的面積（mm²，模組本體 27.8×27.3）：" + "、".join(f"{k} {v}" for k, v in next(p for p in P if p.get("cover"))["cover_area"].items())]
for p in P:
    if p.get("cover_area") and p["id"] != "C":
        L.append(f"{p['id']} 模組從下方蓋住（mm²）：" + "、".join(f"{k} {v}" for k, v in p["cover_area"].items())
                 + (f"；自己那支十字臂的插槽（塞子全長約 34 mm）沿走廊方向被蓋住 {p['ring_cover_len']} mm，長孔 {SLOT_U}×{SLOT_V} mm 開在該塞子上" if p.get("ring_cover_len") else ""))
L += ["", f"第 5 台 HUB（只驅動 OLED）：板子中心 {H5['center']}（{H5['size'][0]}×{H5['size'][1]} mm，架高 4 mm），底下塞子點數 {H5['check']['plug']}、上方障礙點數 {H5['check']['obstacle']}（應為 0）",
      f"TCA9548A 多工器：中心 {MUX['center']}（{MUX['size'][0]}×{MUX['size'][1]} mm），底下塞子點數 {MUX['check']['plug']}、上方障礙點數 {MUX['check']['obstacle']}（應為 0）",
      f"HUB5 → 多工器 I²C 主線：{H5['wire_len'] / 10:.1f} cm，路徑 " + " → ".join(f"({x},{y})" for x, y in H5["route"]),
      "多工器 → OLED（各 4 線，長度含母座頂彎線與兩端上升）：" + "、".join(f"{p['id']} {p['wire_len'] / 10:.1f} cm" for p in P if p["hub"] == "H5")]
table.append(dict(id="HUB5", role="第 5 台 HUB-8735，只驅動中心與 4 個邊中點 OLED", board_center=list(H5["center"]), board_size=list(H5["size"]),
                  mux="TCA9548A", mux_center=list(MUX["center"]), trunk_cm=round(H5["wire_len"] / 10, 1)))
L += ["", "模組四周 0.6 mm 內碰到塞子／鏡頭孔／銷孔（中心只查貫穿孔）：" + ", ".join(f"{p['id']}={p['check']['bad']}" for p in P) + "（應為 0）",
      "模組下方有牆或擋條（含 0.4 mm）：" + ", ".join(f"{p['id']}={p['check']['below']}" for p in P) + "（應為 0）",
      "長條孔（含 0.8 mm 壁）碰到排線溝／塞子／孔：" + ", ".join(f"{p['id']}={p['check']['slot_bad']}" for p in P) + "（應為 0；孔處天花板是 108～116 實心＋封孔板頂板 116～117.6）",
      f"杜邦母座＋線彎需要到 z {Z_DUP1 + WIRE_BEND:.1f}；孔上方第一個零件：" + ", ".join(f"{p['id']} z {p['check']['headroom_top'][0]}（{p['check']['headroom_top'][1]}）" for p in P),
      f"新零件與既有零件互穿：{len(inter)}（應為 0）" + "".join("\n  " + s for s in inter),
      f"杜邦線與既有零件互穿：{len(winter)}（應為 0）" + "".join("\n  " + s for s in winter),
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
