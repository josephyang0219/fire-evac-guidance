"""
9 塊 OLED 定稿配置的多角度圖（Cycles）。只出圖，不存檔、不改模型。
  blender -b fire_model_oled_through_hole.blend --python render_views.py -- <輸出資料夾>
人眼視角 3 張、等角斜視剖切 1 張、東南西北側視 4 張（方案 D 起導線依物件顏色上色：紅 VCC／3V3／5V、黑 GND、黃 SCL、綠 SDA、灰 USB）。人偶是示意（40 mm 高的圓柱＋球），閘門塊用 94 mm 版的網格放在槽位上。
"""
import bpy, bmesh, sys, os, math, json
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index("--") + 1]; os.makedirs(OUT, exist_ok=True)
sc = bpy.data.scenes["Assembly_Full"]
if bpy.context.window: bpy.context.window.scene = sc
T = [t for t in json.load(open(os.path.join(os.path.dirname(bpy.data.filepath), "placements.json"), encoding="utf-8")) if "junction" in t]

sc.render.engine = "CYCLES"; sc.cycles.samples = 64; sc.cycles.use_denoising = True
sc.render.film_transparent = False
if sc.world is None: sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True; bg = sc.world.node_tree.nodes.get("Background"); bg.inputs[0].default_value = (0.9, 0.92, 0.95, 1); bg.inputs[1].default_value = 0.6
sc.view_settings.view_transform = "Standard"

def mat(name, color, emit=0.0, alpha=1.0):
    m = bpy.data.materials.get("V_" + name) or bpy.data.materials.new("V_" + name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear(); out = nt.nodes.new("ShaderNodeOutputMaterial")
    if emit:
        e = nt.nodes.new("ShaderNodeEmission"); e.inputs[0].default_value = color; e.inputs[1].default_value = emit; nt.links.new(e.outputs[0], out.inputs[0])
    else:
        b = nt.nodes.new("ShaderNodeBsdfPrincipled"); b.inputs["Base Color"].default_value = color; b.inputs["Roughness"].default_value = 0.6
        b.inputs["Alpha"].default_value = alpha; nt.links.new(b.outputs[0], out.inputs[0])
    return m
M = dict(ceil=mat("ceil", (0.85, 0.85, 0.82, 1)), lid=mat("lid", (0.62, 0.68, 0.85, 1)), floor=mat("floor", (0.35, 0.35, 0.38, 1)),
         pod=mat("pod", (0.6, 0.55, 0.48, 1)), glass=mat("glass", (0.02, 0.02, 0.02, 1)), aa=mat("aa", (0.1, 1.0, 1.0, 1), emit=6),
         pcb=mat("pcb", (0.1, 0.25, 0.6, 1)), tape=mat("tape", (0.95, 0.8, 0.2, 1)), dup=mat("dup", (0.08, 0.08, 0.08, 1)),
         pins=mat("pins", (0.85, 0.7, 0.3, 1)), lens=mat("lens", (0.85, 0.15, 0.15, 1)), bb=mat("bb", (0.95, 0.95, 0.93, 1)),
         hub=mat("hub", (0.15, 0.5, 0.3, 1)), mux=mat("mux", (0.2, 0.3, 0.8, 1)), pillar=mat("pillar", (0.45, 0.45, 0.5, 1)),
         gate=mat("gate", (0.95, 0.5, 0.1, 1)), fig=mat("fig", (0.95, 0.85, 0.75, 1)), label=mat("label", (1.0, 0.95, 0.2, 1), emit=4),
         labeld=mat("labeld", (0.05, 0.05, 0.05, 1)), ceil_t=mat("ceil_t", (0.85, 0.85, 0.82, 1), alpha=0.28), lid_t=mat("lid_t", (0.62, 0.68, 0.85, 1), alpha=0.22),
         ref=mat("ref", (0.75, 0.05, 0.05, 1)), wtape=mat("wtape", (0.97, 0.97, 0.92, 1)), split=mat("split", (0.9, 0.82, 0.55, 1)),
         usbhub=mat("usbhub", (0.25, 0.25, 0.3, 1)))
WIRE = {}
def setmat(o, m):
    if o.type not in ("MESH", "CURVE", "FONT"): return
    o.data.materials.clear(); o.data.materials.append(m)
for o in sc.objects:
    n = o.name
    if n == "1F_天花板": setmat(o, M["ceil"])
    elif n == "1F_天花板封孔板": setmat(o, M["lid"])
    elif n == "1F_樓層": setmat(o, M["floor"])
    elif "麵包版座" in n: setmat(o, M["pod"])
    elif "顯示區" in n: setmat(o, M["aa"])
    elif "玻璃" in n: setmat(o, M["glass"])
    elif n.endswith("_PCB") or n.endswith("背面零件"): setmat(o, M["pcb"])
    elif "雙面膠" in n: setmat(o, M["tape"])
    elif "杜邦母座" in n or "排針塑膠座" in n or "排針杜邦區" in n: setmat(o, M["dup"])
    elif n.endswith("排針") or "銅柱" in n: setmat(o, M["pins"])
    elif any(k in n for k in ("杜邦線", "I2C主線", "共用線", "電源線", "USB線")):     # 導線用物件顏色（紅 VCC、黑 GND、黃 SCL、綠 SDA、灰 USB）
        c = tuple(o.color); key = str(c); WIRE.setdefault(key, mat("wire" + str(len(WIRE)), c, emit=0.8)); setmat(o, WIRE[key])
    elif n.endswith("_板") and n.startswith(("1F_H5", "1F_H6", "1F_H7")): setmat(o, M["hub"])
    elif "固定膠帶" in n: setmat(o, M["wtape"])
    elif "分接板" in n: setmat(o, M["split"])
    elif n.startswith("電源出口"): setmat(o, M["usbhub"])
    elif "Lens" in n: setmat(o, M["lens"])
    elif "Breadboard" in n: setmat(o, M["bb"])
    elif "HUB8735" in n: setmat(o, M["hub"])
    elif "支撐柱" in n or "銷" in n: setmat(o, M["pillar"])
for o in sc.objects:
    if o.name.startswith(("2F_", "樓梯塔", "ASM_Ground")): o.hide_render = True

# 閘門塊（94 mm）放回槽位：環廊型 G36 在 N 環廊東段、十字臂型 G42 在東臂
extra = []
for gname, loc, rot in (("Gate_Plug_G36", (51, 99, 8), 0), ("Gate_Plug_G42", (51, 0, 8), 0)):
    g = bpy.data.objects.new("示意_" + gname, bpy.data.objects[gname].data.copy()); sc.collection.objects.link(g)
    g.location = loc; g.rotation_euler = (0, 0, math.radians(rot)); setmat(g, M["gate"]); extra.append(g)
# 人偶示意（40 mm：身體圓柱 30 mm＋頭 Ø10）
def figure(x, y):
    me = bpy.data.meshes.new("fig"); bm = bmesh.new()
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=6, radius2=5, depth=30); bmesh.ops.translate(bm, vec=Vector((x, y, 8 + 15)), verts=r["verts"])
    r = bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=5); bmesh.ops.translate(bm, vec=Vector((x, y, 8 + 35)), verts=r["verts"])
    bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new("示意_人偶", me); sc.collection.objects.link(ob); setmat(ob, M["fig"]); extra.append(ob); return ob
FIGS = [figure(-18, -18), figure(14, 52), figure(-82, 82), figure(70, -12)]

labels = []
def label(body, loc, size, m=None):
    cu = bpy.data.curves.new("lbl", "FONT"); cu.body = body; cu.size = size; cu.align_x = "CENTER"; cu.align_y = "CENTER"; cu.extrude = 0.05
    ob = bpy.data.objects.new("lbl_" + body, cu); sc.collection.objects.link(ob); ob.location = loc; setmat(ob, m or M["label"]); labels.append(ob); return ob
JL = {"NW": "NW corner", "NE": "NE corner", "SE": "SE corner", "SW": "SW corner", "C": "CENTER", "N": "N arm", "E": "E arm", "S": "S arm", "W": "W arm"}
oled_labels = {t["id"]: label(JL[t["id"]], (t["active_center"][0], t["active_center"][1], 99.0), 4.0) for t in T}

def face(obj, cam_loc):
    d = Vector(cam_loc) - obj.location
    obj.rotation_euler = d.to_track_quat("Z", "Y").to_euler()

light_d = bpy.data.lights.new("head", "POINT"); light_d.energy = 4.0e4; light_d.shadow_soft_size = 8
head = bpy.data.objects.new("head", light_d); sc.collection.objects.link(head)
sun_d = bpy.data.lights.new("sun", "SUN"); sun_d.energy = 3.0
sun = bpy.data.objects.new("sun", sun_d); sc.collection.objects.link(sun); sun.rotation_euler = (math.radians(50), 0, math.radians(30))

def shot(fname, loc, target, lens=18, ortho=None, res=(1600, 1000), up=(0, 0, 1), headlight=True, hide=(), show_labels=True, clip=0.5):
    cd = bpy.data.cameras.new("c"); cd.clip_start = clip; cd.clip_end = 5000
    if ortho: cd.type = "ORTHO"; cd.ortho_scale = ortho
    else: cd.lens = lens
    cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam)
    f = (Vector(target) - Vector(loc)).normalized(); u = Vector(up)
    if abs(f.dot(u.normalized())) > 0.99: u = Vector((0, 1, 0))
    r = f.cross(u).normalized(); u = r.cross(f)
    cam.matrix_world = Matrix.Translation(loc) @ Matrix((r, u, -f)).transposed().to_4x4()
    head.location = Vector(loc) + f * 3; head.hide_render = not headlight
    hidden = [o for o in sc.objects if any(h in o.name for h in hide) and not o.hide_render]
    for o in hidden: o.hide_render = True
    for o in labels: o.hide_render = not show_labels; face(o, loc)
    sc.camera = cam; sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(OUT, fname + ".png"); bpy.ops.render.render(write_still=True)
    for o in hidden: o.hide_render = False
    bpy.data.objects.remove(cam, do_unlink=True)

EYE = 8 + 40.0
# 1. 人眼視角（相機在走廊、高 40 mm，往上看）
shot("人眼視角1_站在中心路口往北看", (0, -24, EYE), (0, 34, 104), lens=12)
shot("人眼視角2_站在北邊中點鏡頭孔下方往中心看", (0, 92, EYE), (0, 20, 104), lens=12)
shot("人眼視角3_站在西北角落路口", (-108, 108, EYE), (-75, 70, 105), lens=12)
# 2. 等角斜視剖切：拿掉 2F 與樓層盒（含外牆），天花板與封孔板半透明
for o in sc.objects:
    if o.name == "1F_天花板": setmat(o, M["ceil_t"])
    if o.name == "1F_天花板封孔板": setmat(o, M["lid_t"])
for t in T: oled_labels[t["id"]].location.z = 140
dev_l = [label(f"{k} (OLED)", (*c, 145), 5) for k, c in (("H5", (52, -84)), ("H6", (-84, 52)), ("H7", (-52, -84)))]
ALL = json.load(open(os.path.join(os.path.dirname(bpy.data.filepath), "placements.json"), encoding="utf-8"))
dev_l += [label(f"{t['id']} split", (*t["splitter_board"]["center"], 128), 3.5) for t in ALL if t.get("splitter_board")]
pod_l = [label(f"HUB {k}", p, 6) for k, p in (("N", (0, 95, 152)), ("E", (95, 0, 152)), ("S", (0, -95, 152)), ("W", (-95, 0, 152)))]
floor_box = bpy.data.objects["1F_樓層"]
shot("等角斜視剖切_拿掉2F與外牆_天花板半透明", (290, -290, 380), (0, 0, 110), ortho=330, res=(1800, 1400), headlight=False, hide=("1F_樓層",))
for o in sc.objects:
    if o.name == "1F_天花板": setmat(o, M["ceil"])
    if o.name == "1F_天花板封孔板": setmat(o, M["lid"])
for o in (*dev_l, *pod_l): o.hide_render = True; labels.remove(o)
# 3. 四個方位側視（拿掉牆＝隱藏樓層盒，另加一片地板），標出高度
me = bpy.data.meshes.new("floorplate"); bm = bmesh.new(); r = bmesh.ops.create_cube(bm, size=1.0)
for v in r["verts"]: v.co = Vector((v.co.x * 245, v.co.y * 245, 4 + v.co.z * 8))
bm.to_mesh(me); bm.free(); fp = bpy.data.objects.new("示意_地板", me); sc.collection.objects.link(fp); setmat(fp, M["floor"])
refs = []
for z, txt in ((108.0, "ceiling z 108"), (103.0, "OLED bottom z 103 (5 mm)"), (102.0, "gate top z 102 (94 mm)"), (48.0, "figure top z 48 (40 mm)"), (8.0, "floor z 8")):
    me = bpy.data.meshes.new("ref"); bm = bmesh.new(); r = bmesh.ops.create_cube(bm, size=1.0)
    for v in r["verts"]: v.co = Vector((v.co.x * 300, v.co.y * 300, z + v.co.z * 0.4))   # 側視時是一條水平線
    bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new("示意_參考線", me); sc.collection.objects.link(ob); setmat(ob, M["ref"]); refs.append((ob, z, txt))
for t in T: oled_labels[t["id"]].location.z = 92; oled_labels[t["id"]].scale = (0.8, 0.8, 0.8)
for name, d, up_rot in (("側視_從東往西看", Vector((1, 0, 0)), None), ("側視_從南往北看", Vector((0, -1, 0)), None),
                        ("側視_從西往東看", Vector((-1, 0, 0)), None), ("側視_從北往南看", Vector((0, 1, 0)), None)):
    side = Vector((-d.y, d.x, 0))     # 畫面右方的反向（標籤放左側）
    for ob, z, txt in refs: ob.hide_render = False
    DZ = {108.0: 6.0, 103.0: 1.2, 102.0: -3.6, 48.0: 2.8, 8.0: 2.8}     # 108／103／102 三條線很近，標籤上下錯開
    tl = [label(txt, tuple(d * 200 + side * -110 + Vector((0, 0, z + DZ[z]))), 3.0, M["labeld"]) for ob, z, txt in refs]   # 放在模型前方，不會被擋住
    shot(name, tuple(d * 400 + Vector((0, 0, 70))), (0, 0, 70), ortho=330, res=(1800, 900), headlight=False, hide=("1F_樓層",))
    for o in tl: o.hide_render = True; labels.remove(o)
print("views done")
