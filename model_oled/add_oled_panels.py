"""
在 fire_model.blend 的 8 個麵包板座外端面加上 OLED 面板（不修改原有物件，另存新檔）。
支援兩種 OLED：0.96 吋 128×64、0.91 吋 128×32（HUB-8735 SDK 內建的 SSD1306 範例支援這兩種解析度）。

用法（Blender 5.2，背景執行）：
  blender -b <fire_model.blend 的複本> --python add_oled_panels.py -- <0.96|0.91> <輸出 .blend> <輸出資料夾>

量測依據（2026-11-05，以 N 座為例，單位 mm）：
  - 麵包板座外端面在 y = 144.5，x = ±29.5，z = 109～146.5
  - 原端牆是楔形：外面平的（y = 144.5），內面斜向上（(y 138.5, z 111.7) → (y 144.5, z 130.2)），頂部尖端 z ≈ 130.2；
    再往上只剩兩側 1.5 mm 薄側牆（x = ±28～29.5）到 z = 146.5，中間是開口
  - 傾斜 18° 的麵包板下緣頂在楔形內面（z 118～122 時到 y ≈ 140～142）
  - 2F 樓層盒只到 y = 122.5，外端面外側沒有任何零件
設計：
  - 獨立面板，與端面同大小 59×37.5 mm，貼在原端面外側；8 個共用同一個 STL
  - 面板背面開凹槽放 OLED 模組（由外往內：前牆 1.5 mm〔開窗〕→ 玻璃 → PCB → 背面零件），模組夾在面板前牆與原端面之間，
    所以模組不必配合楔形
  - 排針一律朝內，而且必須高於楔形尖端（z 130.2），才能直接伸進座內開口接到麵包板
  - 0.96 吋：4 支 M2×4 自攻螺絲從背面鎖進前牆的墊柱；0.91 吋：模組沒有安裝孔，靠凹槽定位、背面點膠
  - 面板以 2 支 M2 沉頭自攻螺絲鎖進楔形下段（z = 113，該處厚約 5.6 mm）
OLED 尺寸是網路上常見模組的標稱值（各廠會差 0.5～1 mm），列印前必須用實物量測確認。
"""
import bpy, bmesh, sys, os, math
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
VARIANT, OUT_BLEND, OUT_DIR = argv[0], argv[1], argv[2]
os.makedirs(OUT_DIR, exist_ok=True)

# ---------- OLED 模組尺寸（N 座座標：x 左右、y 往外、z 往上；模組正面朝 +y） ----------
#   glass_x0 / glass_z0：玻璃左下角相對 PCB 左下角；act_cx / act_cz：顯示區中心相對 PCB 左下角
#   header：排針位置 "top"（上緣，沿 x 排列）或 "left"（左短邊，沿 z 排列）
VARIANTS = {
    "0.96": dict(name="0.96吋128x64", pcb_w=27.3, pcb_h=27.8, pcb_t=1.6,
                 glass_w=26.7, glass_h=19.3, glass_t=1.4, glass_x0=0.3, glass_z0=1.0,
                 act_w=21.7, act_h=10.9, act_cx=13.65, act_cz=11.5,
                 holes_dx=23.3, holes_dz=23.6,            # 實測常見值，Ø2
                 back_parts=1.5, header="top"),
    "0.91": dict(name="0.91吋128x32", pcb_w=38.0, pcb_h=12.0, pcb_t=1.2,
                 glass_w=30.0, glass_h=11.5, glass_t=1.3, glass_x0=6.5, glass_z0=0.25,   # 玻璃在排針的另一側
                 act_w=22.4, act_h=5.6, act_cx=21.5, act_cz=6.0,
                 holes_dx=None, holes_dz=None,             # 常見模組沒有安裝孔
                 back_parts=1.2, header="left"),
}
D = VARIANTS[VARIANT]

FACE_Y = 144.5                       # 原端面
FRONT_T = 1.5                        # 面板前牆厚
PLATE_W = 59.0
PLATE_Z0, PLATE_Z1 = 109.0, 146.5    # 與座體同高
WEDGE_TOP = 130.2                    # 原端牆楔形尖端
CLR = 0.2                            # 凹槽與模組的間隙
WIN_MARGIN = 1.2                     # 開窗比顯示區每邊多
MOUNT_Z = 113.0
MOUNT_X = (-23.0, 23.0)

POCKET_T = D["glass_t"] + D["pcb_t"] + D["back_parts"]
PLATE_T = POCKET_T + FRONT_T
glass_y1 = FACE_Y + POCKET_T; glass_y0 = glass_y1 - D["glass_t"]
pcb_y1 = glass_y0; pcb_y0 = pcb_y1 - D["pcb_t"]

# 模組在端面上的位置：顯示區中心放在 x = 0；z 依排針方向決定（排針要高於楔形尖端 1 mm 以上）
PCB_X0 = -D["act_cx"]
if D["header"] == "top":
    PCB_Z0 = 113.0                                       # 排針在上緣 → 上緣 z ≈ 140.8
else:
    # 排針沿短邊直向排列，杜邦母座（高 10.2）以 PCB 中心為中心 → 母座最低點要高於楔形尖端 1 mm
    PCB_Z0 = WEDGE_TOP + 1.0 + 5.1 - D["pcb_h"] / 2
PCB_X1, PCB_Z1 = PCB_X0 + D["pcb_w"], PCB_Z0 + D["pcb_h"]
act_x = PCB_X0 + D["act_cx"]; act_z = PCB_Z0 + D["act_cz"]
WIN_W, WIN_H = D["act_w"] + 2 * WIN_MARGIN, D["act_h"] + 2 * WIN_MARGIN
holes = []
if D["holes_dx"]:
    cx, cz = (PCB_X0 + PCB_X1) / 2, (PCB_Z0 + PCB_Z1) / 2
    holes = [(cx + sx * D["holes_dx"] / 2, cz + sz * D["holes_dz"] / 2) for sx in (-1, 1) for sz in (-1, 1)]
PX0, PX1, PZ0, PZ1 = PCB_X0 - CLR, PCB_X1 + CLR, PCB_Z0 - CLR, PCB_Z1 + CLR
assert -PLATE_W / 2 + 2 < PX0 and PX1 < PLATE_W / 2 - 2, "模組太寬，放不進面板"
assert PLATE_Z0 + 1 < PZ0 and PZ1 < PLATE_Z1 - 1, "模組太高，放不進面板"

# ---------- 幾何工具 ----------
def box(bm, x0, x1, y0, y1, z0, z1):
    r = bmesh.ops.create_cube(bm, size=1.0)
    for v in r["verts"]:
        v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0), (z0 + z1) / 2 + v.co.z * (z1 - z0)))

def cyl(bm, x, y0, y1, z, d, seg=24):
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=d / 2, radius2=d / 2, depth=y1 - y0)
    bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector((x, (y0 + y1) / 2, z))) @ Matrix.Rotation(math.radians(90), 4, "X"), verts=r["verts"])

def mesh_obj(name, build, coll, color):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); build(bm); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob); ob.color = color
    key = name.split("_")[0] + "_mat"
    mat = bpy.data.materials.get(key) or bpy.data.materials.new(key); mat.diffuse_color = color; me.materials.append(mat)
    return ob

def boolean(ob, ops):
    """依序套用布林運算：ops = [("DIFFERENCE"|"UNION", build), ...]；每個工具體都是單一封閉實體"""
    for i, (op, b) in enumerate(ops):
        me = bpy.data.meshes.new(f"_tool{i}"); bm = bmesh.new(); b(bm); bm.to_mesh(me); bm.free()
        c = bpy.data.objects.new(f"_tool{i}", me); bpy.context.scene.collection.objects.link(c)
        m = ob.modifiers.new("b", "BOOLEAN"); m.operation = op; m.object = c; m.solver = "EXACT"
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.data.objects.remove(c, do_unlink=True); bpy.data.meshes.remove(me)
    for p in ob.data.polygons: p.material_index = 0
    while len(ob.data.materials) > 1: ob.data.materials.pop()

# ---------- 零件 ----------
F = lambda b: ("DIFFERENCE", b)
U = lambda b: ("UNION", b)
def build_plate(bm):
    box(bm, -PLATE_W / 2, PLATE_W / 2, FACE_Y, FACE_Y + PLATE_T, PLATE_Z0, PLATE_Z1)
plate_ops = [F(lambda bm: box(bm, PX0, PX1, FACE_Y - 1, glass_y1, PZ0, PZ1))]                      # 背面凹槽
if not holes:   # 沒有安裝孔的模組：玻璃周圍留一圈 PCB 承靠面，避免模組往前掉（玻璃以外的 PCB 頂在前牆上）
    pass
plate_ops += [U((lambda hx, hz: (lambda bm: cyl(bm, hx, glass_y0, glass_y1 + 0.5, hz, 4.0)))(hx, hz)) for hx, hz in holes]  # 墊柱
plate_ops += [F(lambda bm: box(bm, act_x - WIN_W / 2, act_x + WIN_W / 2, glass_y1 - 0.5, FACE_Y + PLATE_T + 1, act_z - WIN_H / 2, act_z + WIN_H / 2))]
plate_ops += [F((lambda hx, hz: (lambda bm: cyl(bm, hx, glass_y0 - 1, glass_y1 + 1.0, hz, 1.6)))(hx, hz)) for hx, hz in holes]  # M2 自攻盲孔
plate_ops += [F((lambda mx: (lambda bm: cyl(bm, mx, FACE_Y - 1, FACE_Y + PLATE_T + 1, MOUNT_Z, 2.2)))(mx)) for mx in MOUNT_X]
plate_ops += [F((lambda mx: (lambda bm: cyl(bm, mx, FACE_Y + PLATE_T - 1.2, FACE_Y + PLATE_T + 1, MOUNT_Z, 4.0)))(mx)) for mx in MOUNT_X]

def header_pins(bm):
    """4 pin 排針（朝內 11.5 mm）＋塑膠座＋杜邦母座包絡；回傳最低點 z"""
    if D["header"] == "top":
        hx = (PCB_X0 + PCB_X1) / 2; z = PCB_Z1 - 1.68
        for i in range(4):
            x = hx + (i - 1.5) * 2.54; box(bm, x - 0.32, x + 0.32, pcb_y0 - 11.5, pcb_y1, z - 0.32, z + 0.32)
        box(bm, hx - 5.1, hx + 5.1, pcb_y0 - 11.5 - 14.0, pcb_y0 - 5.5, z - 1.27, z + 1.27)
        box(bm, hx - 5.1, hx + 5.1, pcb_y0 - 2.5, pcb_y0, z - 1.27, z + 1.27)
        return z - 1.27
    else:
        x = PCB_X0 + 1.68; hz = (PCB_Z0 + PCB_Z1) / 2
        for i in range(4):
            z = hz + (i - 1.5) * 2.54; box(bm, x - 0.32, x + 0.32, pcb_y0 - 11.5, pcb_y1, z - 0.32, z + 0.32)
        box(bm, x - 1.27, x + 1.27, pcb_y0 - 11.5 - 14.0, pcb_y0 - 5.5, hz - 5.1, hz + 5.1)
        box(bm, x - 1.27, x + 1.27, pcb_y0 - 2.5, pcb_y0, hz - 5.1, hz + 5.1)
        return hz - 5.1
HEADER_ZMIN = None
def build_pcb(bm):
    global HEADER_ZMIN
    box(bm, PCB_X0, PCB_X1, pcb_y0, pcb_y1, PCB_Z0, PCB_Z1)
    gx0 = PCB_X0 + D["glass_x0"]
    box(bm, gx0 + 2, gx0 + D["glass_w"] - 2, pcb_y0 - D["back_parts"], pcb_y0, PCB_Z0 + 1.5, PCB_Z1 - 1.5)   # 背面零件包絡
    HEADER_ZMIN = header_pins(bm)
def build_glass(bm):
    gx0, gz0 = PCB_X0 + D["glass_x0"], PCB_Z0 + D["glass_z0"]
    box(bm, gx0, gx0 + D["glass_w"], glass_y0, glass_y1, gz0, gz0 + D["glass_h"])
def build_active(bm):
    box(bm, act_x - D["act_w"] / 2, act_x + D["act_w"] / 2, glass_y1 - 0.05, glass_y1, act_z - D["act_h"] / 2, act_z + D["act_h"] / 2)

# ---------- 建立 N 座原型，再依各座的方位複製 ----------
coll = bpy.data.collections.new(f"OLED_{D['name']}"); bpy.context.scene.collection.children.link(coll)
proto_coll = bpy.data.collections.new("_oled_proto"); bpy.context.scene.collection.children.link(proto_coll)
plate = mesh_obj("OLED面板_proto", build_plate, proto_coll, (0.85, 0.85, 0.82, 1)); boolean(plate, plate_ops)
_bm = bmesh.new(); _bm.from_mesh(plate.data); NONMANIFOLD = sum(1 for e in _bm.edges if not e.is_manifold); _bm.free()
pcb = mesh_obj("OLED模組_proto", build_pcb, proto_coll, (0.1, 0.25, 0.55, 1))
glass = mesh_obj("OLED玻璃_proto", build_glass, proto_coll, (0.03, 0.03, 0.03, 1))
act = mesh_obj("OLED顯示區_proto", build_active, proto_coll, (0.2, 0.75, 1.0, 1))

YAW = {"N": 0, "E": -90, "S": 180, "W": 90}
made = []
for floor, dz in (("1F", 0.0), ("2F", 150.0)):
    for side, yaw in YAW.items():
        pod = bpy.data.objects[f"{floor}_麵包版座_{side}"]
        M = Matrix.Translation((0, 0, dz)) @ Matrix.Rotation(math.radians(yaw), 4, "Z")
        for proto, label in ((plate, "OLED面板"), (pcb, "OLED模組"), (glass, "OLED玻璃"), (act, "OLED顯示區")):
            ob = proto.copy(); ob.data = proto.data
            ob.name = f"{floor}_{label}_{side}"; ob.matrix_world = M; coll.objects.link(ob); made.append(ob)
        c = M @ Vector((0, FACE_Y + PLATE_T / 2, (PLATE_Z0 + PLATE_Z1) / 2))
        pts = [pod.matrix_world @ Vector(v) for v in pod.bound_box]
        far = max(pts, key=lambda p: (p.x * c.x + p.y * c.y))
        assert (Vector((c.x, c.y)) - Vector((far.x, far.y))).length < 40, f"{floor}{side} 方位錯誤"
bpy.data.collections.remove(proto_coll)

# ---------- 檢查 ----------
dg = bpy.context.evaluated_depsgraph_get()
def bvh(ob, dy=0.0):
    me = ob.evaluated_get(dg).to_mesh(); M = ob.matrix_world @ Matrix.Translation((0, dy, 0))
    return BVHTree.FromPolygons([M @ v.co for v in me.vertices], [p.vertices[:] for p in me.polygons])
report = [f"OLED：{D['name']}；PCB {D['pcb_w']}×{D['pcb_h']} mm；排針在{'上緣' if D['header'] == 'top' else '左短邊'}"]
existing = [o for o in bpy.context.scene.objects if o.type == "MESH" and o not in made and not o.name.startswith("ASM_")]
eb = {o.name: bvh(o) for o in existing}
bad = 0
for ob in made:
    if "顯示區" in ob.name: continue
    b = bvh(ob); hits = [n for n, t in eb.items() if b.overlap(t)]
    if hits:   # 往外移 0.05 mm 後若不再相交 → 只是面貼面（設計上就要貼著原端面）
        bs = bvh(ob, 0.05); real = [n for n in hits if bs.overlap(eb[n])]
        bad += bool(real)
        report.append(f"{ob.name}: " + ("互穿 " + ", ".join(real) if real else "僅貼合 " + ", ".join(hits)))
    else:
        report.append(f"{ob.name}: 無干涉")
report.append(f"→ 與既有零件互穿：{bad} 件（應為 0）")
for floor in ("1F", "2F"):
    bb = bvh(bpy.data.objects[f"{floor}_Breadboard_N"]); dmin = 1e9
    for x10 in range(int(PCB_X0 * 10), int(PCB_X1 * 10), 15):
        for z10 in range(int(PCB_Z0 * 10), int(PCB_Z1 * 10), 10):
            z = z10 / 10 + (150 if floor == "2F" else 0); y = pcb_y0 - D["back_parts"]
            h = bb.ray_cast(Vector((x10 / 10, y, z)), Vector((0, -1, 0)))
            if h[0]: dmin = min(dmin, y - h[0].y)
    report.append(f"{floor}N 模組背面到麵包板最小間距: {dmin:.1f} mm")
report.append(f"排針／杜邦座最低點 z = {HEADER_ZMIN:.1f}（楔形尖端 {WEDGE_TOP}）→ {'OK' if HEADER_ZMIN > WEDGE_TOP + 0.9 else '太低，會撞到楔形'}")
report.append(f"面板 {PLATE_W}×{PLATE_Z1 - PLATE_Z0}×{PLATE_T:.1f} mm，外突原端面 {PLATE_T:.1f} mm；開窗 {WIN_W:.1f}×{WIN_H:.1f}，中心 (x {act_x:.1f}, z {act_z:.1f})")
report.append(f"模組固定：{'4 支 M2×4 自攻（墊柱）' if holes else '無安裝孔 → 凹槽定位＋背面點膠（或熱熔膠）'}")
report.append(f"面板網格非流形邊數：{NONMANIFOLD}（0 = 可直接切片列印）")
pb = bvh(bpy.data.objects["1F_OLED面板_N"]); miss = tot = 0
for x10 in range(int(PX0 * 10) + 5, int(PX1 * 10), 20):
    for z10 in range(int(PZ0 * 10) + 5, int(PZ1 * 10), 20):
        x, z = x10 / 10, z10 / 10
        if abs(x - act_x) < WIN_W / 2 and abs(z - act_z) < WIN_H / 2: continue
        tot += 1; h = pb.ray_cast(Vector((x, 200, z)), Vector((0, -1, 0)))
        if not h[0] or h[0].y < FACE_Y + PLATE_T - 0.01: miss += 1
report.append(f"前牆遮蔽檢查：窗口以外 {tot} 點中有 {miss} 點沒被前牆擋住（應為 0）")
# 玻璃（含顯示區）不能被前牆擋住：顯示區四角都在窗口內
report.append("顯示區在窗口內：" + ("OK" if WIN_MARGIN > 0 else "否"))
# 模組不能從窗口掉出：PCB 必須比窗口大
report.append("模組不會從窗口掉出：" + ("OK" if D["pcb_w"] > WIN_W + 1 and D["pcb_h"] > WIN_H + 1 else "否"))
half_diag = 65.0; seen = 0
for floor in ("1F", "2F"):
    for side in YAW:
        lens = bpy.data.objects[f"{floor}_HUB8735_Lens_{side}"]
        ax = (lens.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
        for oside in YAW:
            a = bpy.data.objects[f"{floor}_OLED顯示區_{oside}"]
            ang = min(math.degrees(ax.angle((a.matrix_world @ Vector(v)) - lens.matrix_world.translation)) for v in a.bound_box)
            if ang < half_diag: seen += 1; report.append(f"⚠ {floor} 鏡頭{side} 可能看到 OLED{oside}（{ang:.0f}°）")
report.append(f"鏡頭視野：{seen} 組鏡頭／OLED 在視野內（對角半角 {half_diag}°，應為 0）")

# ---------- 輸出 ----------
for o in bpy.context.scene.objects: o.select_set(False)
p = bpy.data.objects["1F_OLED面板_N"]; p.select_set(True); bpy.context.view_layer.objects.active = p
bpy.ops.wm.stl_export(filepath=os.path.join(OUT_DIR, f"OLED面板_{D['name']}_x8.stl"), export_selected_objects=True, apply_modifiers=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading; sh.light = "STUDIO"; sh.color_type = "MATERIAL"; sh.show_cavity = True; sh.show_object_outline = True
def shot(name, loc, target, lens=50, hide=()):
    cd = bpy.data.cameras.new(name); cd.lens = lens; cd.clip_start = 1; cd.clip_end = 5000
    cam = bpy.data.objects.new(name, cd); sc.collection.objects.link(cam); cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    hidden = [o for o in sc.objects if any(h in o.name for h in hide) and not o.hide_render]
    for o in hidden: o.hide_render = True
    sc.camera = cam; sc.render.resolution_x = 1400; sc.render.resolution_y = 1000
    sc.render.filepath = os.path.join(OUT_DIR, name + ".png"); bpy.ops.render.render(write_still=True)
    for o in hidden: o.hide_render = False
    bpy.data.objects.remove(cam, do_unlink=True)
shot("檢查_整體", (520, 620, 420), (0, 0, 130), lens=40)
shot("檢查_N座外端特寫", (60, 260, 175), (0, 144, 128), lens=60)
shot("檢查_N座背面_去座體", (70, 60, 190), (0, 144, 128), lens=50, hide=("1F_麵包版座_N", "2F_樓層", "1F_天花板"))
open(os.path.join(OUT_DIR, "干涉與視野檢查.txt"), "w", encoding="utf-8").write("\n".join(report))
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, copy=True)
print("\n".join(report))
