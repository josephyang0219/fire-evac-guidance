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

OUT = None
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
# 角落：位置由 search_through_hole.py 選出（顯示區中心離路口最近、四周 ≥ 0.6 mm、孔不碰溝與孔、上方有空間、鏡頭看不到）
#   up = 畫面上方（排針那一側）在世界座標的方向；route = 母座頂以上焊線沿封孔板頂面走到麵包板座內側端窗口
P = [
    dict(id="NW", J=(-99, 99), center=(-101.5, 99.0), up="W", hub="N", addr="0x3D",
         route=[(-113.5, 45.0), (-4.0, 45.0), (-4.0, 49.0)]),
    dict(id="NE", J=(99, 99), center=(99.5, 96.5), up="S", hub="E", addr="0x3D",
         route=[(99.5, 92.0), (45.0, 92.0), (45.0, 4.0), (49.0, 4.0)]),   # 先往北繞過房間角的支撐柱
    dict(id="SE", J=(99, -99), center=(99.0, -101.5), up="S", hub="S", addr="0x3D",
         route=[(60.0, -113.5), (60.0, -45.0), (4.0, -45.0), (4.0, -49.0)]),
    dict(id="SW", J=(-99, -99), center=(-96.5, -99.5), up="E", hub="W", addr="0x3D",
         route=[(-45.0, -99.5), (-45.0, -4.0), (-49.0, -4.0)]),
]
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
    hu, hv = PW / 2, PH / 2; bad = []; below = 0
    for q in rect_pts(p, -hu, hu, -hv, hv, grow=0.6):       # 模組四周 0.6 mm 內：天花板底面要是平的 z 108（不能是塞子、鏡頭孔、銷孔）
        iv, wall = stack(q.x, q.y)
        if not iv or abs(iv[0][0] - CEIL) > 0.05 and not (iv[0][2] and iv[0][0] > 115.9): bad.append((round(q.x, 1), round(q.y, 1)))
    for q in rect_pts(p, -hu, hu, -hv, hv, grow=0.4): below += stack(q.x, q.y)[1]
    sbad = []; top = 99.0
    for q in rect_pts(p, -SLOT_U / 2, SLOT_U / 2, PH / 2 - PIN_ROW - SLOT_V / 2, PH / 2 - PIN_ROW + SLOT_V / 2, grow=0.8):
        iv, _ = stack(q.x, q.y)
        # 長條孔＋0.8 mm 壁：天花板從 108 連續實體到頂（中間不能有排線溝的空腔、不能是塞子或孔）
        ok = iv and abs(iv[0][0] - CEIL) < 0.05 and not iv[0][2]
        zt = iv[0][1] if ok else 0
        for a, b, _l in iv[1:]:
            if a <= zt + 0.05: zt = max(zt, b)
            else: ok = False
        if not ok or zt < 114.9: sbad.append((round(q.x, 1), round(q.y, 1)))
        else: top = min(top, zt)
    p["check"] = dict(bad=len(bad), below=below, slot_bad=len(sbad), ceil_top=top)


# ---------- 精確搜尋：每個角落 × 4 方向 × 路口 ±7 mm，取顯示區中心離路口最近且全部條件通過者 ----------
import itertools
cache = {}
def st_cached(x, y):
    k = (round(x, 2), round(y, 2))
    if k not in cache: cache[k] = stack(x, y)
    return cache[k]
def ok_footprint(p):
    hu, hv = PW / 2, PH / 2
    for q in rect_pts(p, -hu, hu, -hv, hv, grow=0.6, step=0.5):
        iv, _ = st_cached(q.x, q.y)
        if not iv or abs(iv[0][0] - CEIL) > 0.05 and not (iv[0][2] and iv[0][0] > 115.9): return False
    for q in rect_pts(p, -hu, hu, -hv, hv, grow=0.4, step=0.5):
        if st_cached(q.x, q.y)[1]: return False
    return True
def ok_slot(p):
    for q in rect_pts(p, -SLOT_U / 2, SLOT_U / 2, PH / 2 - PIN_ROW - SLOT_V / 2, PH / 2 - PIN_ROW + SLOT_V / 2, grow=0.8, step=0.5):
        iv, _ = st_cached(q.x, q.y)
        if not iv or abs(iv[0][0] - CEIL) > 0.05 or iv[0][2]: return False
        zt = iv[0][1]
        for a, b, _l in iv[1:]:
            if a <= zt + 0.05: zt = max(zt, b)
            else: return False
        if zt < 114.9: return False
    return True
res = {}
for J in [(-99, 99), (99, 99), (99, -99), (-99, -99)]:
    cands = []
    for up in "NESW":
        for dx in [i * 0.5 for i in range(-14, 15)]:
            for dy in [i * 0.5 for i in range(-14, 15)]:
                p = dict(center=(J[0] + dx, J[1] + dy), up=up)
                u = Vector((*D[up], 0)); r = Z.cross(u); c = Vector((*p["center"], 0))
                p["W"] = lambda uu, vv, c=c, r=r, u=u: c + uu * r + vv * u
                aa = p["W"](0, ACY - PH / 2)
                cands.append(((aa.to_2d() - Vector(J)).length, up, p))
    cands.sort(key=lambda t: t[0])
    for off, up, p in cands:
        if ok_footprint(p) and ok_slot(p):
            res[J] = (round(off, 2), up, p["center"]); break
    print("FIT", J, res.get(J), flush=True)
