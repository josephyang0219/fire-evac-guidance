"""
在 fire_model.blend 的 1F 天花板，為井字型路網的 8 個路口各裝一塊面朝下的 0.96 吋 OLED（中心不放；不修改原檔，另存新檔）。
  - 4 個邊中點（N/E/S/W）：嵌入天花板凹槽，玻璃與天花板底面平齊（鏡頭孔就在路口正中，外接會被自己那台鏡頭看到）
  - 4 個角落（NW/NE/SE/SW）：外接——3D 列印外殼貼在天花板底面（雙面膠），天花板不切；焊線從 5×5 路口孔上去

用法（Blender 5.2，背景執行；參數路徑只能用英文）：
  blender -b <fire_model.blend 的複本> --python add_ceiling_oled.py -- <輸出資料夾>

位置由 survey_1f_ceiling.py 的搜尋結果選定（見 README.md）；本腳本只建模，並用原始網格重新做一次獨立檢查：
  - 模組凹槽、焊線槽、螺絲導孔不切到排煙孔／排線孔塞子、鏡頭孔、5×5 路口孔、定位銷孔（留 ≥0.8 mm 壁）
  - 凹槽可以切開天花板內的排線溝底（2026-11-05 使用者同意），焊線沿排線溝走到 HUB 座
  - 模組整片在走廊正上方（下方沒有牆、擋條）；天花板剩餘厚度；新零件與既有零件無互穿
  - 8 台鏡頭看不到任何顯示區（角度＋遮擋射線）；改過的天花板網格封閉
座標：1 BU = 1 mm，場景 Assembly_Full。面朝下的模組：玻璃底面與天花板底面 z = 108 平齊。
OLED 尺寸是常見模組的標稱值（各廠差 0.5～1 mm），列印前必須量實物並改 VARIANTS 重跑。
"""
import bpy, bmesh, sys, os, math, json
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

OUT_DIR = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT_DIR, exist_ok=True)
sc = bpy.context.scene
assert sc.name == "Assembly_Full", sc.name

# ---------- OLED 模組（局部座標以 PCB 中心為原點：u = 從正面看的右、v = 從正面看的上） ----------
#   0.96 吋：排針在上緣（+v）；0.91 吋：排針在左短邊（−u）。排針拆掉，改從 PCB 背面焊線。
VARIANTS = {
    "0.96": dict(name="0.96吋128x64", pw=27.3, ph=27.8, pt=1.6, gw=26.7, gh=19.3, gt=1.4, gx0=0.3, gy0=1.0,
                 aw=21.7, ah=10.9, acx=13.65, acy=11.5, back=1.5, pads=(0.0, 13.9 - 1.68), pads_along="u",
                 screws=[(-11.65, 11.8), (11.65, 11.8)]),           # 排針側兩個 Ø2 安裝孔（玻璃以外）
    "0.91": dict(name="0.91吋128x32", pw=38.0, ph=12.0, pt=1.2, gw=30.0, gh=11.5, gt=1.3, gx0=6.5, gy0=0.25,
                 aw=22.4, ah=5.6, acx=21.5, acy=6.0, back=1.2, pads=(-19.0 + 1.68, 0.0), pads_along="v",
                 screws=[]),                                          # 沒有安裝孔 → 凹槽定位＋點膠
}
CEIL = 108.0           # 天花板底面
# 外接外殼（角落）：底框 1.0（開窗）＋玻璃 1.4＋PCB 1.6＋排針塑膠座 2.5 = 6.5 mm，外框 ≤ 31×31；上面 1.0 mm 雙面泡棉膠
BEZEL, WALL, TAPE, SPACER = 1.0, 1.2, 1.0, 2.5
H_TOP = CEIL - TAPE                    # 外殼頂面 z 107.0
H_BOT = H_TOP - (BEZEL + 1.4 + 1.6 + SPACER)   # 外殼底面 z 100.5
WIN_MARGIN = 1.2       # 開窗比顯示區每邊大
CLR = 0.2              # 凹槽與 PCB 間隙
CH_TOP = 113.8         # 焊線槽頂（排線溝底 z 112，溝頂 115／116；麵包板座下方頂皮 115 − 113.8 = 1.2 mm）
WIRE_Z = 113.8         # 焊線束在排線溝內的中心高度
WIRE_R = 0.6           # 4 條 30 AWG（外徑約 0.5 mm）並排／絞成約 Ø1.2 的線束
MARGIN = 0.8           # 切削到既有孔、塞子的最小壁厚（凹槽與凹槽之間也一樣）
ROOF_MIN = 1.2         # 焊線槽、導孔上方最少頂皮（列印 6 層 @0.2 mm）

# ---------- 9 個路口的配置（survey_1f_ceiling.py 的最佳解） ----------
#   center：PCB 中心；up：從正面看「畫面上方」在世界座標的方向；route：焊線沿排線溝的折點（第一點是焊盤）
#   排線溝中心線：x = −91、11、113；y = −91、11、113（102 間距、偏 +11，和 99 間距的路口錯開）
D = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}
P = [
    # 角落：外接外殼。位置用精確射線量測（survey/fit_corner_housing.py）：外殼到房間角柱、外牆、塞子都留 ≥ 0.6 mm。
    #   焊線在外殼與天花板之間 1 mm 的膠層空隙走到 5×5 路口孔，往上進排線溝。SE 角東側是東梯出入口，外殼只能偏西，
    #   路口孔落在外殼外 0.3 mm → 外殼東牆頂與膠層開一個線槽讓線出去
    dict(id="NW", J=(-1, 1), mount="surface", center=(-98.0, 101.25), up="E", hub="N", bus="Wire", addr="0x3D",
         hole=(-91, 113), route=[(11, 113), (11, 95)]),
    dict(id="N", J=(0, 1), mount="embed", center=(0.0, 66.0), up="S", hub="N", bus="Wire", addr="0x3C",
         route=[(11, None), (11, 95)]),
    dict(id="NE", J=(1, 1), mount="surface", center=(99.5, 101.2), up="E", hub="E", bus="Wire", addr="0x3D",
         hole=(113, 113), route=[(113, 11), (95, 11)]),
    dict(id="W", J=(-1, 0), mount="embed", center=(-66.0, 0.0), up="E", hub="W", bus="Wire", addr="0x3C",
         route=[(None, 11), (-95, 11)]),     # 西側緊貼鏡頭孔（壁 0.9 mm），不能再靠近路口
    dict(id="E", J=(1, 0), mount="embed", center=(66.0, 0.0), up="W", hub="E", bus="Wire", addr="0x3C",
         route=[(None, 11), (95, 11)]),
    dict(id="SW", J=(-1, -1), mount="surface", center=(-98.0, -101.3), up="E", hub="W", bus="Wire", addr="0x3D",
         hole=(-91, -91), route=[(-91, -8.5)]),
    dict(id="S", J=(0, -1), mount="embed", center=(0.0, -66.0), up="N", hub="S", bus="Wire", addr="0x3C",
         route=[(11, None), (11, -95)]),
    dict(id="SE", J=(1, -1), mount="surface", center=(95.5, -101.25), up="W", hub="S", bus="Wire", addr="0x3D",
         hole=(113, -91), route=[(11, -91), (11, -95)]),
]
for p in P: p["var"] = "0.96"
Z = Vector((0, 0, 1))
for p in P:
    V = VARIANTS[p["var"]]
    if "up" in p:   # 面朝下：從下方看，畫面右方 = ẑ × 畫面上方
        up = Vector((*D[p["up"]], 0)); right = Z.cross(up)
    else:
        right = Vector((*D[p["right"]], 0)); up = right.cross(Z)
    p["r"], p["u"] = right, up
    c = Vector((*p["center"], 0))
    p["W"] = lambda uu, vv, c=c, r=right, u=up: c + uu * r + vv * u
    p["pads_w"] = p["W"](*V["pads"])
    p["aa_w"] = p["W"](V["acx"] - V["pw"] / 2, V["acy"] - V["ph"] / 2)
    p["pocket_top"] = CEIL + V["gt"] + V["pt"] + V["back"] + 0.1
    p["z0"] = CEIL if p["mount"] == "embed" else H_BOT + BEZEL      # 玻璃底面
    # 焊線路徑：焊盤 → 垂直走到第一條排線溝（外接：先到 5×5 路口孔）→ 沿溝 → 進 HUB 座
    pts = [Vector((p["pads_w"].x, p["pads_w"].y))]
    if p["mount"] == "surface":
        h = Vector(p["hole"]); pts += [Vector((h.x, pts[0].y)) if abs(p["u"].x) < 0.5 else Vector((pts[0].x, h.y)), h]
    for x, y in (p["route"] if p["mount"] == "embed" else []):
        pts.append(Vector((pts[-1].x if x is None else x, pts[-1].y if y is None else y)))
    p["path2d"] = pts

# ---------- 幾何工具 ----------
def frame_box(bm, p, u0, u1, v0, v1, z0, z1):
    """在模組局部座標 (u,v) 建立矩形塊"""
    W = p["W"]; q = [W(u0, v0), W(u1, v0), W(u1, v1), W(u0, v1)]
    vs = [bm.verts.new((a.x, a.y, z)) for z in (z0, z1) for a in q]
    if (q[1] - q[0]).cross(q[2] - q[1]).z < 0: vs = vs[:4][::-1] + vs[4:][::-1]
    bm.faces.new(vs[3::-1]); bm.faces.new(vs[4:])
    for i in range(4):
        j = (i + 1) % 4; bm.faces.new((vs[i], vs[j], vs[4 + j], vs[4 + i]))

def world_box(bm, x0, x1, y0, y1, z0, z1):
    r = bmesh.ops.create_cube(bm, size=1.0)
    for v in r["verts"]:
        v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0), (z0 + z1) / 2 + v.co.z * (z1 - z0)))

def cyl(bm, x, y, z0, z1, d, seg=20):
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=d / 2, radius2=d / 2, depth=z1 - z0)
    bmesh.ops.translate(bm, vec=Vector((x, y, (z0 + z1) / 2)), verts=r["verts"])

def material(key, color):
    m = bpy.data.materials.get(key) or bpy.data.materials.new(key); m.diffuse_color = color; return m

def mesh_obj(name, build, coll, color):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); build(bm); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob); ob.color = color
    me.materials.append(material(name.split("_")[1] + "_mat", color))
    return ob

def bvh(ob):
    dg = bpy.context.evaluated_depsgraph_get(); me = ob.evaluated_get(dg).to_mesh(); M = ob.matrix_world
    return BVHTree.FromPolygons([M @ v.co for v in me.vertices], [p.vertices[:] for p in me.polygons])

def apply_boolean(ob, tools):
    for i, b in enumerate(tools):
        me = bpy.data.meshes.new(f"_tool{i}"); bm = bmesh.new(); b(bm); bm.to_mesh(me); bm.free()
        t = bpy.data.objects.new(f"_tool{i}", me); sc.collection.objects.link(t)
        m = ob.modifiers.new("b", "BOOLEAN"); m.operation = "DIFFERENCE"; m.object = t; m.solver = "EXACT"
        bpy.context.view_layer.objects.active = ob
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.data.objects.remove(t, do_unlink=True); bpy.data.meshes.remove(me)

def nonmanifold(ob):
    bm = bmesh.new(); bm.from_mesh(ob.data); n = sum(1 for e in bm.edges if not e.is_manifold); bm.free(); return n

# ---------- 原始網格（檢查用） ----------
ceil = sc.objects["1F_天花板"]; lid = sc.objects["1F_天花板封孔板"]; floor = sc.objects["1F_樓層"]
B_ceil0, B_lid, B_floor = bvh(ceil), bvh(lid), bvh(floor)
NM0 = nonmanifold(ceil)

def column(x, y):
    """垂直射線：回傳 (天花板＋封孔板從 z108 起連續實體的頂, 是否排線溝, 下方是否有牆/擋條)"""
    iv = []
    for t in (B_ceil0, B_lid):
        z, hits = 100.0, []
        while True:
            h = t.ray_cast(Vector((x, y, z)), Vector((0, 0, 1)), 40)
            if h[0] is None: break
            hits.append(h[0].z); z = h[0].z + 1e-3
        iv += [(hits[i], hits[i + 1]) for i in range(0, len(hits) - 1, 2)]
    iv.sort(); top = None
    if iv and abs(iv[0][0] - CEIL) < 0.05:
        top = iv[0][1]
        for a, b in iv[1:]:
            if a <= top + 0.05: top = max(top, b)
            else: break
    z, hits = -1.0, []
    while True:
        h = B_floor.ray_cast(Vector((x, y, z)), Vector((0, 0, 1)), 200)
        if h[0] is None: break
        hits.append(h[0].z); z = h[0].z + 1e-3
    wall = any(hits[i + 1] > 9 and hits[i] < 107.5 for i in range(0, len(hits) - 1, 2))
    rib = (B_ceil0.ray_cast(Vector((x, y, 100)), Vector((0, 0, 1)), 10)[0] or Vector((0, 0, 999))).z < 107
    return top, top is not None and abs(top - 112.0) < 0.05, wall or rib

def rect_samples(p, u0, u1, v0, v1, grow=0.0, step=0.5):
    out = []; nu = max(2, int((u1 - u0 + 2 * grow) / step) + 1); nv = max(2, int((v1 - v0 + 2 * grow) / step) + 1)
    for i in range(nu):
        for j in range(nv):
            out.append(p["W"](u0 - grow + (u1 - u0 + 2 * grow) * i / (nu - 1), v0 - grow + (v1 - v0 + 2 * grow) * j / (nv - 1)))
    return out

# ---------- 建立切削工具與零件 ----------
coll = bpy.data.collections.new("OLED_1F天花板"); sc.collection.children.link(coll)
housings = []
wcoll = bpy.data.collections.new("OLED_1F焊線"); sc.collection.children.link(wcoll)
tools, tool_owner, made, report, table = [], [], [], [], []
HUB_COLOR = {"N": (0.9, 0.2, 0.2, 1), "E": (0.2, 0.7, 0.2, 1), "S": (0.95, 0.75, 0.1, 1), "W": (0.6, 0.3, 0.9, 1)}

def build_module(p, V, hu, hv):
    gx0, gy0 = -hu + V["gx0"], -hv + V["gy0"]
    z0 = p["z0"]
    z_g1 = z0 + V["gt"]; z_p1 = z_g1 + V["pt"]
    tag = f"1F_OLED_{p['id']}"
    made.append(mesh_obj(f"{tag}_玻璃", lambda bm: frame_box(bm, p, gx0, gx0 + V["gw"], gy0, gy0 + V["gh"], z0, z_g1), coll, (0.03, 0.03, 0.03, 1)))
    ax, ay = V["acx"] - hu, V["acy"] - hv
    made.append(mesh_obj(f"{tag}_顯示區", lambda bm: frame_box(bm, p, ax - V["aw"] / 2, ax + V["aw"] / 2, ay - V["ah"] / 2, ay + V["ah"] / 2, z0 - 0.05, z0), coll, (0.2, 0.85, 1.0, 1)))
    def pcb(bm):
        frame_box(bm, p, -hu, hu, -hv, hv, z_g1, z_p1)
        frame_box(bm, p, gx0 + 2, gx0 + V["gw"] - 2, -hv + 1.5, hv - 1.5, z_p1, z_p1 + V["back"])  # 背面零件包絡
        if p["mount"] == "surface":   # 已焊的 4 pin 排針：塑膠座 2.5 mm，針剪到與塑膠座齊平後焊線
            pu, pv = V["pads"]; frame_box(bm, p, pu - 5.08, pu + 5.08, pv - 1.27, pv + 1.27, z_p1, z_p1 + SPACER)
    made.append(mesh_obj(f"{tag}_PCB", pcb, coll, (0.1, 0.25, 0.55, 1)))

def build_surface(p, V, hu, hv):
    """角落外接：外殼（開窗底框＋四面牆、上面開口）、膠層、模組、焊線"""
    ou, ov = hu + CLR + WALL, hv + CLR + WALL; iu, iv = hu + CLR, hv + CLR
    ax, ay = V["acx"] - hu, V["acy"] - hv; ww, wh = V["aw"] / 2 + WIN_MARGIN, V["ah"] / 2 + WIN_MARGIN
    p["housing"] = (ou, ov)
    def housing(bm, p=p):
        frame_box(bm, p, -ou, ou, -ov, ov, H_BOT, H_TOP)
    hob = mesh_obj(f"1F_OLED_{p['id']}_外殼", housing, coll, (0.92, 0.92, 0.9, 1))
    p["housing_ops"] = [lambda bm, p=p: frame_box(bm, p, -iu, iu, -iv, iv, H_BOT + BEZEL, H_TOP + 1),
                        lambda bm, p=p: frame_box(bm, p, ax - ww, ax + ww, ay - wh, ay + wh, H_BOT - 1, H_BOT + BEZEL + 0.5)]
    hpt = Vector((*p["hole"], 0)) - p["W"](0, 0)
    p["notch"] = None
    if not (abs(hpt.dot(p["r"])) < ou - 1 and abs(hpt.dot(p["u"])) < ov - 1):   # 孔不在外殼內 → 牆頂開線槽
        b2 = p["path2d"][-2]; h2 = p["path2d"][-1]; m = b2.lerp(h2, 0.5)
        d = (h2 - b2).normalized(); n = Vector((-d.y, d.x)); L2 = (h2 - b2).length / 2 + 0.5
        cs = [m + d * L2 + n * 1.5, m + d * L2 - n * 1.5, m - d * L2 + n * 1.5, m - d * L2 - n * 1.5]
        p["notch"] = (min(c.x for c in cs), max(c.x for c in cs), min(c.y for c in cs), max(c.y for c in cs))
        p["housing_ops"].append(lambda bm, p=p: world_box(bm, *p["notch"], H_TOP - 1.0, H_TOP + 1))
    apply_boolean(hob, p["housing_ops"])
    made.append(hob); housings.append((p, hob))
    def tape(bm, p=p):   # 牆頂一圈雙面泡棉膠（1.3 mm 寬）
        for u0, u1, v0, v1 in ((-ou, ou, iv, ov), (-ou, ou, -ov, -iv), (-ou, -iu, -iv, iv), (iu, ou, -iv, iv)):
            frame_box(bm, p, u0, u1, v0, v1, H_TOP, CEIL - 0.02)
    tob = mesh_obj(f"1F_OLED_{p['id']}_雙面膠", tape, coll, (0.95, 0.85, 0.3, 1))
    if p["notch"]: apply_boolean(tob, [lambda bm, p=p: world_box(bm, *p["notch"], H_TOP - 1.0, CEIL + 1)])
    made.append(tob)
    build_module(p, V, hu, hv)
    pts3 = [Vector((q.x, q.y, CEIL - 0.65)) for q in p["path2d"]]   # 焊盤 → 路口孔：在膠層空隙內（z 107.35）
    pts3[0].z = H_TOP - 0.6                                           # 焊盤在排針塑膠座頂（剪短的針上焊線）
    h = pts3[-1]; pts3.append(Vector((h.x, h.y, WIRE_Z)))            # 從 5×5 路口孔往上進排線溝
    for x, y in p["route"]: pts3.append(Vector((x, y, WIRE_Z)))
    build_wire(p, pts3)

def build_wire(p, pts3):
    tag = f"1F_OLED_{p['id']}"
    end = pts3[-1]; zt = end.z
    others = [o for o in sc.objects if o.type == "MESH" and o.name.startswith("1F_") and o.name not in ("1F_天花板", "1F_天花板封孔板", "1F_樓層") and "OLED" not in o.name]
    hits = [h for h in (bvh(o).ray_cast(end, Vector((0, 0, 1)), 60) for o in others) if h[0] is not None]
    zt = (min(h[0].z for h in hits) if hits else 140) - 4.0
    pts3.append(Vector((end.x, end.y, zt)))
    cu = bpy.data.curves.new(f"{tag}_焊線", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = WIRE_R; cu.bevel_resolution = 2
    sp = cu.splines.new("POLY"); sp.points.add(len(pts3) - 1)
    for k, q in enumerate(pts3): sp.points[k].co = (q.x, q.y, q.z, 1)
    wob = bpy.data.objects.new(f"{tag}_焊線", cu); wcoll.objects.link(wob); wob.color = HUB_COLOR[p["hub"]]
    cu.materials.append(material(f"焊線{p['hub']}_mat", HUB_COLOR[p["hub"]]))
    L = sum((pts3[k + 1] - pts3[k]).length for k in range(len(pts3) - 1))
    p["wire_len"] = L; p["riser"] = (end.x, end.y, zt)

for p in P:
    V = VARIANTS[p["var"]]; hu, hv = V["pw"] / 2, V["ph"] / 2; pt = p["pocket_top"]
    p["screws_w"] = []; p["chan_rect"] = None
    if p["mount"] == "surface":
        build_surface(p, V, hu, hv); continue
    # 凹槽（從下方切入，深到背面零件頂 + 0.1）
    tool_owner += [p["id"] + "凹槽"]
    tools.append(lambda bm, p=p, hu=hu, hv=hv, pt=pt: frame_box(bm, p, -hu - CLR, hu + CLR, -hv - CLR, hv + CLR, CEIL - 1, pt))
    # 焊線槽：焊盤列 → 第一條排線溝（在凹槽範圍內，加深到 CH_TOP）
    a, b = p["path2d"][0], p["path2d"][1]
    pu = (V["pads"][0], V["pads"][1])
    span = 10.16 / 2 + 0.6
    ax_ = (p["r"] if V["pads_along"] == "u" else p["u"]).to_2d()   # 焊盤排列方向（與世界軸平行）
    ext = [a - span * ax_, a + span * ax_, b - 1.5 * ax_, b + 1.5 * ax_]
    perp = Vector((-ax_.y, ax_.x))   # 垂直方向再各加 1.5 mm（線束 Ø1.8）
    ext += [a + 1.5 * perp, a - 1.5 * perp, b + 1.5 * perp, b - 1.5 * perp]
    p["chan_rect"] = (min(e.x for e in ext), max(e.x for e in ext), min(e.y for e in ext), max(e.y for e in ext))
    def chan(bm, p=p):
        x0, x1, y0, y1 = p["chan_rect"]; world_box(bm, x0, x1, y0, y1, p["pocket_top"] - 0.5, CH_TOP)
    tool_owner.append(p["id"] + "焊線槽"); tools.append(chan)
    for su, sv in V["screws"]:   # 選配 M2×5 自攻（圓柱頭 k ≤ 1.3，頭在玻璃旁的 1.4 mm 空隙內）；導孔上方要留 ≥0.8 mm 才做
        s = p["W"](su, sv); top, gr, _ = column(s.x, s.y)
        if gr or top is None or top < pt + 1.6 + ROOF_MIN: continue
        p["screws_w"].append(s)
        tool_owner.append(p["id"] + "導孔"); tools.append(lambda bm, s=s, pt=pt: cyl(bm, s.x, s.y, pt - 0.5, pt + 1.6, 1.6))
    build_module(p, V, hu, hv)
    # 焊線束（曲線）：焊盤 → 溝 → HUB 座內上升
    pts3 = [Vector((q.x, q.y, WIRE_Z)) for q in p["path2d"]]
    pts3[0].z = pts3[1].z = 113.1            # 焊盤 → 溝：走在焊線槽內（背面零件頂 112.5 與槽頂 113.8 之間）
    pts3.insert(2, Vector((pts3[1].x, pts3[1].y, WIRE_Z)))
    build_wire(p, pts3)

# ---------- 切削前：用原始網格逐點檢查 ----------
bad_lines = []
EMB = [p for p in P if p["mount"] == "embed"]; SUR = [p for p in P if p["mount"] == "surface"]
for p in EMB:
    V = VARIANTS[p["var"]]; hu, hv = V["pw"] / 2 + CLR, V["ph"] / 2 + CLR
    nbad = nbelow = 0; rem = 99.0; groove_cells = 0
    for q in rect_samples(p, -hu, hu, -hv, hv, grow=MARGIN - 0.01):   # 壁厚恰為 0.8 時，取樣點不要剛好落在孔壁上
        top, gr, _ = column(q.x, q.y)
        if gr: groove_cells += 1; continue
        if top is None or top < p["pocket_top"] + 1.0:
            nbad += 1; p.setdefault("bad_pts", []).append((round(q.x, 1), round(q.y, 1), top))
    for q in rect_samples(p, -hu, hu, -hv, hv):
        top, gr, below = column(q.x, q.y); nbelow += below
        if top is not None and not gr: rem = min(rem, top - p["pocket_top"])
    p["check"] = dict(bad=nbad, below=nbelow, rem=rem, groove=groove_cells > 0)
    if nbad or nbelow: bad_lines.append(p["id"])
# 外接外殼：整片在走廊天花板下（下方無牆／擋條）、不蓋排煙／排線孔塞子與鏡頭孔（留 1 mm）；可以蓋 5×5 路口孔
def first_hit(t, x, y):
    h = t.ray_cast(Vector((x, y, 100)), Vector((0, 0, 1)), 30); return h[0].z if h[0] else None
for p in SUR:
    ou, ov = p["housing"]; nbad = nbelow = 0
    for q in rect_samples(p, -ou, ou, -ov, ov, grow=0.6):
        zc, zl = first_hit(B_ceil0, q.x, q.y), first_hit(B_lid, q.x, q.y)
        blind = zc is None and zl is not None and zl > 115.9          # 5×5 路口孔（上面被封孔板頂板蓋住）
        if (zl is not None and zl < 109) or ((zc is None or zc > CEIL + 0.05) and not blind):
            nbad += 1; p.setdefault("bad_pts", []).append((round(q.x, 1), round(q.y, 1), zc, zl))
    for q in rect_samples(p, -ou, ou, -ov, ov, grow=0.4):
        nbelow += column(q.x, q.y)[2]
    h = Vector((*p["hole"], 0)); c0 = p["W"](0, 0)
    covers = abs((h - c0).dot(p["r"])) < ou and abs((h - c0).dot(p["u"])) < ov
    p["check"] = dict(bad=nbad, below=nbelow, rem=99.0, groove=False, chan_rem=99.0, chan_bad=0, screw_rem=99.0, covers_hole=covers)

# 焊線槽與螺絲導孔：槽頂上方剩餘厚度
for p in EMB:
    x0, x1, y0, y1 = p["chan_rect"]; rem = 99.0; nbad = 0
    nx, ny = int((x1 - x0 + 1.6) / 0.5) + 1, int((y1 - y0 + 1.6) / 0.5) + 1
    for i in range(nx):
        for j in range(ny):
            x, y = x0 - 0.8 + (x1 - x0 + 1.6) * i / (nx - 1), y0 - 0.8 + (y1 - y0 + 1.6) * j / (ny - 1)
            top, gr, _ = column(x, y)
            if gr: continue
            if top is None or top < CH_TOP + 0.8: nbad += 1
            elif x0 <= x <= x1 and y0 <= y <= y1: rem = min(rem, top - CH_TOP)
    p["check"]["chan_rem"] = rem; p["check"]["chan_bad"] = nbad
    V = VARIANTS[p["var"]]; srem = 99.0
    for s in p["screws_w"]:
        top, gr, _ = column(s.x, s.y)
        srem = min(srem, (top or 0) - (p["pocket_top"] + 1.6))
    p["check"]["screw_rem"] = srem

# 凹槽與凹槽之間的壁厚
def pocket_rect(p):
    V = VARIANTS[p["var"]]; hu, hv = V["pw"] / 2 + CLR, V["ph"] / 2 + CLR
    cs = [p["W"](su * hu, sv * hv) for su in (-1, 1) for sv in (-1, 1)]
    return min(c.x for c in cs), max(c.x for c in cs), min(c.y for c in cs), max(c.y for c in cs)
gaps = []
for i in range(len(EMB)):
    for j in range(i + 1, len(EMB)):
        a_, b_ = pocket_rect(EMB[i]), pocket_rect(EMB[j])
        dx = max(a_[0] - b_[1], b_[0] - a_[1], 0); dy = max(a_[2] - b_[3], b_[2] - a_[3], 0)
        gaps.append((math.hypot(dx, dy), EMB[i]["id"], EMB[j]["id"]))
gaps.sort()
# 切削工具不可碰到封孔板（封孔板完全不改）
def tool_bvh(b):
    me = bpy.data.meshes.new("_t"); bm = bmesh.new(); b(bm); bm.to_mesh(me); bm.free()
    t = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [f.vertices[:] for f in me.polygons]); bpy.data.meshes.remove(me); return t
lid_hits = [n for n, b in zip(tool_owner, tools) if tool_bvh(b).overlap(B_lid)]

# ---------- 切削：複製原天花板保留比較，再在場景中的 1F_天花板 開孔 ----------
keep = bpy.data.collections.new("_原始1F天花板_未開孔（僅供比較）"); sc.collection.children.link(keep)
orig = ceil.copy(); orig.data = ceil.data.copy(); orig.name = "1F_天花板_原始"; keep.objects.link(orig)
orig.hide_render = True; orig.hide_viewport = True
ceil.data = ceil.data.copy(); ceil.data.name = "1F_天花板_OLED開孔"
apply_boolean(ceil, tools)
bpy.context.view_layer.layer_collection.children[keep.name].exclude = True
NM1 = nonmanifold(ceil)

# ---------- 切削後檢查 ----------
existing = [o for o in sc.objects if o.type == "MESH" and o not in made and not o.name.startswith("ASM_") and o.visible_get()]
EB = {o.name: bvh(o) for o in existing}
inter = []
for ob in made:
    if "顯示區" in ob.name: continue
    t = bvh(ob); hits = [n for n, b in EB.items() if t.overlap(b)]
    if hits: inter.append(f"{ob.name} ↔ {', '.join(hits)}")
winter = []
dg = bpy.context.evaluated_depsgraph_get()
for wob in wcoll.objects:
    me = wob.evaluated_get(dg).to_mesh(); M = wob.matrix_world
    t = BVHTree.FromPolygons([M @ v.co for v in me.vertices], [p.vertices[:] for p in me.polygons])
    hits = [n for n, b in EB.items() if t.overlap(b)]
    if hits: winter.append(f"{wob.name} ↔ {', '.join(hits)}")
    wob.evaluated_get(dg).to_mesh_clear()

# 鏡頭：fire_evac_v2/app/evac.py 的光學模型（位置 rot(rz)·(0,92,111)，往中心傾斜 18°，對角半角 65°）
CAMS = {"N": 0.0, "W": 90.0, "E": -90.0, "S": 180.0}
scene_b = [b for n, b in EB.items() if "Lens" not in n]   # 只用既有零件當遮擋物（外接件自己互相遮擋不算，偏保守）
cam_lines = []; seen = 0; min_ang = 180.0
def sample_pts(p):
    """顯示區取 15 點；外接件再取外殼、膠層、模組全部網格頂點與面中心（沿法線往外推 0.05 mm）"""
    V = VARIANTS[p["var"]]; hu, hv = V["pw"] / 2, V["ph"] / 2; axc, ayc = V["acx"] - hu, V["acy"] - hv; pts = []
    for i in range(5):
        for j in range(3):
            q = p["W"](axc + V["aw"] * (i / 4 - 0.5), ayc + V["ah"] * (j / 2 - 0.5)); q.z = p["z0"] - 0.02; pts.append(q)
    if p["mount"] == "surface":
        for ob in made:
            if not ob.name.startswith(f"1F_OLED_{p['id']}_"): continue
            me = ob.data; M = ob.matrix_world
            for f in me.polygons:
                n = (M.to_3x3() @ f.normal).normalized()
                pts.append(M @ f.center + n * 0.05)
                pts += [M @ me.vertices[k].co + n * 0.05 for k in f.vertices]
    return pts
for p in P: p["pts"] = sample_pts(p)
for fl, dz in (("1F", 0.0), ("2F", 150.0)):
    for cn, rz in CAMS.items():
        R = Matrix.Rotation(math.radians(rz), 3, "Z") @ Matrix.Rotation(math.radians(-18), 3, "X")
        cpos = Matrix.Rotation(math.radians(rz), 3, "Z") @ Vector((0, 92, 111 + dz))
        ax = R @ Vector((0, 0, -1))
        for p in P:
            vis = 0; amin = 180.0
            for q in p["pts"]:
                d = q - cpos; ang = math.degrees(ax.angle(d)); amin = min(amin, ang)
                if ang > 65: continue
                if not any(b.ray_cast(cpos, d.normalized(), d.length - 0.05)[0] is not None for b in scene_b): vis += 1
            if fl == "1F": min_ang = min(min_ang, amin)
            if vis: seen += 1; cam_lines.append(f"⚠ {fl} 鏡頭{cn} 看得到 OLED {p['id']}（{vis} 點）")
            elif fl == "1F" and amin < 65: cam_lines.append(f"  1F 鏡頭{cn} → OLED {p['id']}：在 65° 內（最小 {amin:.0f}°），但被天花板擋住")

# ---------- 報告 ----------
def dirname(v):
    return {(0, 1): "北", (0, -1): "南", (1, 0): "東", (-1, 0): "西"}[(round(v.x), round(v.y))]
report.append("1F 天花板 OLED（8 個路口，中心不放）自動檢查  —  add_ceiling_oled.py")
report.append("")
report.append("路口  模組／安裝        PCB 中心          顯示區中心        離路口  畫面上方  最低點 z  往下凸出  HUB  匯流排  位址   焊線長")
for p in P:
    c = p["check"]; J = Vector((p["J"][0] * 99, p["J"][1] * 99, 0)); off = (p["aa_w"].to_2d() - J.to_2d()).length
    low = CEIL if p["mount"] == "embed" else H_BOT
    report.append(f"{p['id']:4s}  0.96吋 {'嵌入凹槽' if p['mount'] == 'embed' else '外接外殼'}  ({p['center'][0]:6.1f},{p['center'][1]:6.1f})  "
                  f"({p['aa_w'].x:6.1f},{p['aa_w'].y:6.1f})  {off:5.1f}   {dirname(p['u'])}       {low:6.1f}   {CEIL - low:4.1f} mm   "
                  f"{p['hub']}    {p['bus']:5s}   {p['addr']}  {p['wire_len'] / 10:4.1f} cm")
    table.append(dict(id=p["id"], junction=[p["J"][0] * 99, p["J"][1] * 99], module=p["var"], mount=p["mount"], protrusion_mm=round(CEIL - low, 1), pcb_center=list(p["center"]),
                      active_center=[round(p["aa_w"].x, 1), round(p["aa_w"].y, 1)], offset_mm=round(off, 1),
                      screen_up=dirname(p["u"]), screen_right=dirname(p["r"]), hub=p["hub"], bus=p["bus"], addr=p["addr"],
                      wire_cm=round(p["wire_len"] / 10, 1), riser=[round(a, 1) for a in p["riser"]],
                      path=[[round(q.x, 1), round(q.y, 1)] for q in p["path2d"]]))
report.append("")
GX, GY = (-91, 11, 113), (-91, 11, 113)
report.append("嵌入（邊中點）：切開的排線溝（溝寬 4 mm，凹槽範圍內的溝底被打開）與焊線路徑：")
for p in EMB:
    x0, x1, y0, y1 = pocket_rect(p); segs = []
    for gx in GX:
        if x0 < gx + 2 and x1 > gx - 2: segs.append(f"x={gx} 溝 y {y0:.1f}～{y1:.1f}")
    for gy in GY:
        if y0 < gy + 2 and y1 > gy - 2: segs.append(f"y={gy} 溝 x {x0:.1f}～{x1:.1f}")
    path = " → ".join(f"({q.x:.1f},{q.y:.1f})" for q in p["path2d"])
    report.append(f"  {p['id']:3s} 凹槽 x {x0:.1f}～{x1:.1f}、y {y0:.1f}～{y1:.1f}；切開：{'；'.join(segs)}")
    report.append(f"      焊線：焊盤 {path} → 在 {p['hub']} 座內上升到 z {p['riser'][2]:.1f}（共 {p['wire_len'] / 10:.1f} cm，再加約 10 cm 到麵包板）")
report.append("  邊中點的路口 5×5 孔沒有使用；焊線從 OLED 背面焊盤經焊線槽直接進溝。")
report.append(f"外接（角落）：外殼 {2 * SUR[0]['housing'][0]:.1f}×{2 * SUR[0]['housing'][1]:.1f}×{H_TOP - H_BOT:.1f} mm＋雙面泡棉膠 {TAPE} mm，天花板不切：")
for p in SUR:
    path = " → ".join(f"({q.x:.1f},{q.y:.1f})" for q in p["path2d"]) + " ↑孔 → " + " → ".join(f"({x},{y})" for x, y in p["route"])
    report.append(f"  {p['id']:3s} 外殼蓋住路口孔 {p['hole']}：{'是' if p['check']['covers_hole'] else '否'}；焊線：焊盤 {path} → 在 {p['hub']} 座內上升到 z {p['riser'][2]:.1f}（共 {p['wire_len'] / 10:.1f} cm）")
report.append(f"走廊淨高：地板 z 8 到外殼底 z {H_BOT:.1f} = {H_BOT - 8:.1f} mm（人偶約 40 mm）")
report.append("")
report.append(f"凹槽碰到既有孔／塞子／鏡頭孔／銷孔（含 {MARGIN} mm 壁厚）：" + ", ".join(f"{p['id']}={p['check']['bad']}" for p in EMB) + "  （應全為 0）")
report.append("外殼蓋到排煙／排線孔塞子、鏡頭孔，或不在天花板平面下（含 0.6 mm）：" + ", ".join(f"{p['id']}={p['check']['bad']}" for p in SUR) + "  （應全為 0）")
report.append("焊線槽碰到孔：" + ", ".join(f"{p['id']}={p['check']['chan_bad']}" for p in EMB) + "  （應全為 0）")
report.append("模組／外殼下方有牆或擋條（不在走廊上方）：" + ", ".join(f"{p['id']}={p['check']['below']}" for p in P) + "  （應全為 0）")
report.append("凹槽切開排線溝底（焊線由此進溝）：" + ", ".join(p["id"] for p in EMB if p["check"]["groove"]))
report.append(f"凹槽頂上方最小剩餘厚：{min(p['check']['rem'] for p in EMB):.1f} mm（麵包板座下方天花板頂 115、其他 116／117.6）")
report.append(f"焊線槽頂上方最小剩餘厚：{min(p['check']['chan_rem'] for p in EMB):.1f} mm（應 ≥ {ROOF_MIN}）")
sr = [p["check"]["screw_rem"] for p in P if p["screws_w"]]
if sr:
    report.append(f"M2 導孔（深 1.6 mm）頂上方最小剩餘厚：{min(sr):.1f} mm；有導孔的路口：" + ", ".join(f"{p['id']}×{len(p['screws_w'])}" for p in P if p["screws_w"]))
else:
    report.append(f"M2 導孔：邊中點 4 塊的安裝孔都在麵包板座下方，導孔上方頂皮不到 {ROOF_MIN} mm → 不開，模組用點膠固定")
for p in P:
    if p.get("bad_pts"): report.append(f"  {p['id']} 不合格取樣點（x, y, 實體頂）：{p['bad_pts'][:12]}")
report.append(f"凹槽與凹槽最小壁厚：{gaps[0][0]:.2f} mm（{gaps[0][1]}–{gaps[0][2]}；應 ≥ {MARGIN}）")
report.append(f"切削工具碰到封孔板：{len(lid_hits)} 個（應為 0；封孔板完全不改）" + (" " + ", ".join(lid_hits) if lid_hits else ""))
report.append(f"新零件與既有零件互穿：{len(inter)} 件（應為 0）" + ("".join("\n  " + s for s in inter)))
report.append(f"焊線束與既有零件互穿：{len(winter)} 條（應為 0）" + ("".join("\n  " + s for s in winter)))
report.append(f"鏡頭視野：8 台鏡頭 × {len(P)} 塊 OLED 中看得到 {seen} 組（應為 0；外接件每塊取 {min(len(p['pts']) for p in SUR)} 點以上）；1F 鏡頭軸到任一取樣點的最小夾角 {min_ang:.0f}°")
report += cam_lines
report.append(f"1F_天花板非流形邊：原始 {NM0} → 開孔後 {NM1}")
report.append("")
report.append("面朝下的螢幕從下方看：畫面右方 = ẑ × 畫面上方，所以和俯視平面圖東西左右相反（見 README 韌體換算表）。")
open(os.path.join(OUT_DIR, "檢查報告.txt"), "w", encoding="utf-8").write("\n".join(report))
json.dump(table, open(os.path.join(OUT_DIR, "placements.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n".join(report))

# ---------- 輸出 STL 與 .blend ----------
for o in sc.objects: o.select_set(False)
ceil.select_set(True); bpy.context.view_layer.objects.active = ceil
bpy.ops.wm.stl_export(filepath=os.path.join(OUT_DIR, "1F_天花板_OLED開孔.stl"), export_selected_objects=True, apply_modifiers=True)
# 外殼 STL：4 個角落同一形狀；移到原點、底框（開窗面）朝下列印，不需支撐
hp, hob = housings[0]
proto = hob.copy(); proto.data = hob.data.copy(); sc.collection.objects.link(proto)
proto.data.transform(Matrix.Translation((-hp["center"][0], -hp["center"][1], -H_BOT)))
for o in sc.objects: o.select_set(False)
proto.select_set(True); bpy.context.view_layer.objects.active = proto
bpy.ops.wm.stl_export(filepath=os.path.join(OUT_DIR, "OLED外接外殼_0.96吋_x4.stl"), export_selected_objects=True, apply_modifiers=True)
nm_h = nonmanifold(proto); bpy.data.objects.remove(proto, do_unlink=True)
open(os.path.join(OUT_DIR, "檢查報告.txt"), "a", encoding="utf-8").write(f"\n外殼 STL 非流形邊：{nm_h}（0 = 可直接切片）\n")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT_DIR, "fire_model_oled_ceiling_1f.blend"), copy=True)
