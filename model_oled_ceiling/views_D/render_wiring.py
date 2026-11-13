"""
方案 D 的接線圖（Workbench、物件顏色；只出圖，不存檔、不改模型）：
  接線_設備層俯視_7台HUB與全部外接線.png：拿掉 2F、麵包板座與麵包板（只畫外框），看得到 7 台 HUB、全部外接線、2 個電源出口
  接線特寫_H5.png／_H6.png／_H7.png：每台 OLED HUB 與它的 OLED、分接板、共用段、電源出線；橘色＝塞子頂面（排煙孔、排線孔、十字臂插槽，要能拆）
  電源出口特寫_南.png／_北.png：USB 線從設備層開口（1F 天花板 z 116 到 2F 樓板 z 150）出樓層盒、沿外牆到桌面上的 USB 集線器
導線顏色：紅 VCC／3V3／5V、黑 GND、黃 SCL、綠 SDA、灰 USB。
  blender -b fire_model_oled_through_hole.blend --python render_wiring.py -- <輸出資料夾>
"""
import bpy, bmesh, sys, os, math, json
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

OUT = sys.argv[sys.argv.index("--") + 1]; os.makedirs(OUT, exist_ok=True)
sc = bpy.data.scenes["Assembly_Full"]
ALL = json.load(open(os.path.join(os.path.dirname(bpy.data.filepath), "placements.json"), encoding="utf-8"))
T = [t for t in ALL if "junction" in t]; HUBT = {t["id"]: t for t in ALL if t.get("board_center")}
try: FONT = bpy.data.fonts.load("C:/Windows/Fonts/msjh.ttc")
except Exception: FONT = None
sc.render.engine = "BLENDER_WORKBENCH"; sh = sc.display.shading
sh.light = "STUDIO"; sh.color_type = "OBJECT"; sh.show_shadows = False; sh.show_cavity = False; sh.show_object_outline = False
sc.view_settings.view_transform = "Standard"
if sc.world is None: sc.world = bpy.data.worlds.new("w")
sc.world.color = (1, 1, 1)

COL = [("1F_天花板封孔板", (0.80, 0.84, 0.92, 1)), ("1F_天花板", (0.86, 0.86, 0.83, 1)), ("1F_樓層", (0.6, 0.6, 0.64, 1)), ("支撐柱", (0.5, 0.5, 0.56, 1)),
       ("銷", (0.5, 0.5, 0.56, 1)), ("HUB8735_PCB", (0.15, 0.5, 0.3, 1)), ("HUB8735_Headers", (0.1, 0.1, 0.1, 1)), ("HUB8735_Parts", (0.3, 0.3, 0.3, 1)),
       ("HUB8735_Lens", (0.85, 0.15, 0.15, 1)), ("麵包版座", (0.6, 0.5, 0.4, 1)), ("Breadboard", (0.93, 0.93, 0.9, 1)), ("樓梯塔", (0.7, 0.68, 0.62, 1)),
       ("2F_樓層", (0.75, 0.75, 0.78, 1))]
for o in sc.objects:
    if o.name.startswith(("1F_OLED穿孔", "1F_H5", "1F_H6", "1F_H7", "1F_接線", "1F_鏡頭HUB", "電源出口")): continue     # 建模時已設好顏色
    for k, c in COL:
        if k in o.name: o.color = c; break
for o in sc.objects:
    if "分接板" in o.name: o.color = (0.95, 0.7, 0.25, 1)
def hide_set(names, v=True):
    for o in sc.objects:
        if any(o.name.startswith(n) or n in o.name for n in names): o.hide_render = v
for o in sc.objects:
    if o.name.startswith(("ASM_", "Gate_Plug")) or o.type not in ("MESH", "CURVE"): o.hide_render = True
extra = []
def new_obj(name, bm, color):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob); ob.color = color; extra.append(ob); return ob
def box(bm, x0, x1, y0, y1, z0, z1):
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) @ Matrix.Diagonal((x1 - x0, y1 - y0, z1 - z0, 1)))
# 塞子頂面（橘）：從下方往上打射線，封孔板在 z 109 以下就有實體的格子＝塞子
dg = bpy.context.evaluated_depsgraph_get(); lid = sc.objects["1F_天花板封孔板"]; me = lid.evaluated_get(dg).to_mesh(); M = lid.matrix_world
B_lid = BVHTree.FromPolygons([M @ v.co for v in me.vertices], [f.vertices[:] for f in me.polygons])
bm = bmesh.new()
for x in range(-119, 120):
    run = None
    for y in list(range(-119, 120)) + [999]:
        h = B_lid.ray_cast(Vector((x, y, 100.0)), Vector((0, 0, 1)), 30) if y != 999 else (None,)
        isp = h[0] is not None and h[0].z < 109
        if isp and run is None: run = y
        if not isp and run is not None:
            box(bm, x - 0.5, x + 0.5, run - 0.5, y - 0.5, 117.62, 117.7); run = None
plug_ov = new_obj("示意_塞子頂面", bm, (1.0, 0.55, 0.12, 1))
# 麵包板座外框（俯視時拿掉座本體，只畫外框）
bm = bmesh.new()
for o in sc.objects:
    if "麵包版座" in o.name:
        bb = [o.matrix_world @ Vector(c) for c in o.bound_box]; x0, x1 = min(v.x for v in bb), max(v.x for v in bb); y0, y1 = min(v.y for v in bb), max(v.y for v in bb)
        for a in ((x0, x1, y0, y0 + 0.8), (x0, x1, y1 - 0.8, y1), (x0, x0 + 0.8, y0, y1), (x1 - 0.8, x1, y0, y1)): box(bm, *a, 146.0, 146.5)
pod_ol = new_obj("示意_麵包板座外框", bm, (0.45, 0.3, 0.15, 1))
labels = []
def label(body, loc, size, color=(0.05, 0.05, 0.05, 1), rot=None, tag="all"):
    cu = bpy.data.curves.new("lbl", "FONT"); cu.body = body; cu.size = size; cu.align_x = "CENTER"; cu.align_y = "CENTER"
    if FONT: cu.font = FONT
    ob = bpy.data.objects.new("lbl_" + body[:20], cu); sc.collection.objects.link(ob); ob.location = loc; ob.color = color
    if rot: ob.rotation_euler = rot
    ob["tag"] = tag; labels.append(ob); return ob
def shot(fname, loc, target, ortho=None, lens=35, res=(1800, 1800), up=(0, 0, 1), tag=None, hide=(), show=()):
    cd = bpy.data.cameras.new("c"); cd.clip_start = 1; cd.clip_end = 5000
    if ortho: cd.type = "ORTHO"; cd.ortho_scale = ortho
    else: cd.lens = lens
    cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam)
    f = (Vector(target) - Vector(loc)).normalized(); u = Vector(up)
    if abs(f.dot(u.normalized())) > 0.99: u = Vector((0, 1, 0))
    r = f.cross(u).normalized(); u = r.cross(f)
    cam.matrix_world = Matrix.Translation(loc) @ Matrix((r, u, -f)).transposed().to_4x4()
    for o in labels:
        o.hide_render = o["tag"] not in (tag, "all")
        if not ortho: o.rotation_euler = (Vector(loc) - o.location).to_track_quat("Z", "Y").to_euler()
    changed = []
    for o in sc.objects:
        if o in labels: continue
        want = None
        if any(n in o.name for n in hide): want = True
        if any(n in o.name for n in show): want = False
        if want is not None and o.hide_render != want: changed.append((o, o.hide_render)); o.hide_render = want
    sc.camera = cam; sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(OUT, fname + ".png"); bpy.ops.render.render(write_still=True)
    for o, v in changed: o.hide_render = v
    bpy.data.objects.remove(cam, do_unlink=True)

TOP_HIDE = ("2F_", "樓梯塔", "麵包版座_", "Breadboard", "顯示區", "1F_樓層")     # 樓層盒也拿掉（否則從麵包板座的天花板開口會看到 1F 地板）
# ---------- 1. 設備層俯視 ----------
Z_L = 152
for k, c in (("N", (0, 118)), ("E", (118, 0)), ("S", (0, -118)), ("W", (-118, 0))):
    label(f"鏡頭 HUB {k}", (c[0], c[1], Z_L), 6.5, tag="top")
for hid, t in HUBT.items():
    bx, by = t["board_center"]
    label(f"{hid}（只驅動 OLED）", (bx, by + 5, Z_L), 4.6, tag="top")
    label("、".join(f"{k} {v}" for k, v in t["oleds"].items()), (bx, by - 2, Z_L), 3.8, tag="top")
    if t.get("splitter_board"):
        c = t["splitter_board"]["center"]; label(f"{hid} 分接板", (c[0], c[1] + (11 if hid == "H5" else 0), Z_L), 3.4, tag="top")
for t in T:
    s = t["slot_center"]; label(f"{t['id']}（{t['addr']}）", (s[0], s[1] + (-6 if s[1] > 0 else 6), Z_L), 3.6, (0.0, 0.25, 0.6, 1), tag="top")
label("南出口：4 埠 USB 集線器（鏡頭 S、W＋H5、H7）", (0, -200, Z_L), 6.0, (0.6, 0.05, 0.05, 1), tag="top")
label("北出口：4 埠 USB 集線器（鏡頭 N、E＋H6）", (0, 200, Z_L), 6.0, (0.6, 0.05, 0.05, 1), tag="top")
label("樓層盒外緣 ±122.5（設備層四周開口，USB 線直接出去，不用開孔）", (0, -128, Z_L), 4.2, (0.3, 0.3, 0.3, 1), tag="top")
shot("接線_設備層俯視_7台HUB與全部外接線", (0, 0, 600), (0, 0, 0), ortho=430, up=(0, 1, 0), tag="top", hide=TOP_HIDE)
# ---------- 2. 每台 OLED HUB 特寫 ----------
PINS = ("3V3", "GND", "SDA", "SCL")
for hid, t in HUBT.items():
    pts = [t["board_center"]] + [x["slot_center"] for x in T if x["hub"] == hid] + ([t["splitter_board"]["center"]] if t.get("splitter_board") else [])
    pts += [list(t["power_pins"].values())[0]]
    x0, x1 = min(p[0] for p in pts) - 26, max(p[0] for p in pts) + 26; y0, y1 = min(p[1] for p in pts) - 26, max(p[1] for p in pts) + 26
    sz = max(x1 - x0, y1 - y0); cx, cy = (x0 + x1) / 2, (y0 + y1) / 2; tg = "c" + hid
    for nm, p in t["bus_pins"].items():
        off = Vector((0, 3.2)) if t["bus_side"] in "NS" else Vector((3.2, 0))
        sgn = 1 if t["bus_side"] in "NE" else -1
        label(nm, (p[0] + off.x * sgn, p[1] + off.y * sgn, Z_L), 1.5, rot=(0, 0, math.radians(90)) if t["bus_side"] in "NS" else None, tag=tg)
    for nm, p in t["power_pins"].items():
        sgn = -1 if t["power_exit_side"] in "SW" else 1; off = Vector((0, 3.2)) if t["power_exit_side"] in "NS" else Vector((3.2, 0))
        label(nm, (p[0] + off.x * sgn, p[1] + off.y * sgn, Z_L), 1.5, (0.6, 0.0, 0.0, 1), tag=tg)
    bx, by = t["board_center"]; label(f"{hid}", (bx, by, Z_L), 6, (1, 1, 1, 1), tag=tg)
    for x in T:
        if x["hub"] != hid: continue
        s = x["slot_center"]; label(f"OLED {x['id']}（{x['addr']}）", (s[0], s[1] + (-7 if s[1] > 0 else 7), Z_L), 3.2, (0.0, 0.25, 0.6, 1), tag=tg)
    if t.get("splitter_board"):
        c = t["splitter_board"]["center"]; label("分接板", (c[0], c[1], Z_L), 3.0, tag=tg)
    label(f"{hid} 接線特寫（俯視，北在上；橘＝塞子頂面）", (cx, cy + sz / 2 - 5, Z_L), 4.0, tag=tg)
    shot(f"接線特寫_{hid}", (cx, cy, 600), (cx, cy, 0), ortho=sz, res=(1500, 1500), up=(0, 1, 0), tag=tg, hide=TOP_HIDE)
# ---------- 3. 電源出口特寫 ----------
label("南出口 USB 集線器（5 V 3 A 變壓器）", (0, -182, 30), 6, (0.6, 0.05, 0.05, 1), tag="ps")
label("設備層開口 z 116～150：線直接出去，不用開孔", (-90, -170, 175), 5, tag="ps")
label("北出口 USB 集線器（5 V 3 A 變壓器）", (0, 182, 30), 6, (0.6, 0.05, 0.05, 1), tag="pn")
label("設備層開口 z 116～150：線直接出去，不用開孔", (90, 170, 175), 5, tag="pn")
for pw in [t for t in ALL if t["id"] == "POWER"][0]["cables"]:
    ex = pw["exit"]; side = pw["outlet"]
    label(pw["hub"].replace("鏡頭 HUB ", "鏡頭 ") + (" USB" if "鏡頭" in pw["hub"] else " 5V/GND"), (ex[0] * 1.08, ex[1] * 1.08 + (0 if abs(ex[1]) > 140 else 0), 142), 3.6, tag="ps" if side == "S" else "pn")
shot("電源出口特寫_南", (-170, -400, 230), (-10, -150, 95), lens=40, res=(1800, 1200), tag="ps", hide=("2F_", "Breadboard", "示意_塞子", "示意_麵包板座外框"))
shot("電源出口特寫_北", (170, 400, 230), (10, 150, 95), lens=40, res=(1800, 1200), tag="pn", hide=("2F_", "Breadboard", "示意_塞子", "示意_麵包板座外框"))
print("wiring done")
