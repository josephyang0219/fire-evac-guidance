"""
穿孔方案的平面圖與 3D 圖（Workbench）。在 build_through_hole.py 輸出的 .blend 上執行：
  blender -b fire_model_oled_through_hole.blend --python render_through_hole.py -- <輸出資料夾>
"""
import bpy, sys, os, json, math
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index("--") + 1]
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading; sh.light = "STUDIO"; sh.color_type = "OBJECT"; sh.show_cavity = True; sh.show_object_outline = True
T = json.load(open(os.path.join(os.path.dirname(bpy.data.filepath), "placements.json"), encoding="utf-8"))
HUBC = {"N": (0.9, 0.2, 0.2, 1), "E": (0.2, 0.7, 0.2, 1), "S": (0.95, 0.75, 0.1, 1), "W": (0.6, 0.3, 0.9, 1), "H5": (0.1, 0.8, 0.85, 1), "H6": (0.95, 0.4, 0.75, 1), "H7": (0.55, 0.85, 0.25, 1)}
COL = {"1F_天花板": (0.82, 0.82, 0.80, 1), "1F_天花板封孔板": (0.62, 0.68, 0.85, 1), "1F_樓層": (0.25, 0.25, 0.27, 1)}
for o in sc.objects:
    if o.name in COL: o.color = COL[o.name]
    elif "麵包版座" in o.name: o.color = (0.55, 0.5, 0.45, 1)
    elif "Lens" in o.name: o.color = (0.9, 0.15, 0.15, 1)
    elif "支撐柱" in o.name: o.color = (0.4, 0.4, 0.45, 1)

extra = []
def text(body, loc, size=4.0, color=(1, 1, 1, 1), rot=(0, 0, 0), mirror=False, tag="all"):
    cu = bpy.data.curves.new("t", "FONT"); cu.body = body; cu.size = size; cu.align_x = "CENTER"; cu.align_y = "CENTER"
    ob = bpy.data.objects.new("lbl", cu); sc.collection.objects.link(ob); ob.location = loc; ob.rotation_euler = rot
    if mirror: ob.scale = (-1, 1, 1)
    ob.color = color; ob["tag"] = tag; extra.append(ob); return ob

def outline(cx, cy, hx, hy, z, w, color, tag):
    import bmesh
    me = bpy.data.meshes.new("ol"); bm = bmesh.new()
    for x0, x1, y0, y1 in ((cx - hx, cx + hx, cy + hy - w, cy + hy), (cx - hx, cx + hx, cy - hy, cy - hy + w),
                           (cx - hx, cx - hx + w, cy - hy, cy + hy), (cx + hx - w, cx + hx, cy - hy, cy + hy)):
        r = bmesh.ops.create_cube(bm, size=1.0)
        for v in r["verts"]: v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0), z + v.co.z * 0.4))
    bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new("ol", me); sc.collection.objects.link(ob); ob.color = color; ob["tag"] = tag; extra.append(ob)

# 平面圖標註（放在封孔板頂面上方）
DEVS = [t for t in T if t["id"] in ("H5", "H6", "H7")]
T = [t for t in T if "junction" in t]
for D_ in DEVS:
    bx, by = D_["board_center"]; bw, bh = D_["board_size"]
    outline(bx, by, bw / 2, bh / 2, 141.0, 0.8, HUBC[D_["id"]], "plan")
    text(f"{D_['id']} (OLED only)", (bx, by + 4, 141.2), 3.4, (0.05, 0.05, 0.05, 1), tag="plan")
    text("  ".join(f"{k} {v}" for k, v in D_["oleds"].items()), (bx, by - 2, 141.2), 2.8, (0.05, 0.05, 0.05, 1), tag="plan")
    text(f"power {D_['power_cm']} cm", (bx, by - 7, 141.2), 2.6, (0.05, 0.05, 0.05, 1), tag="plan")
for t in T:
    J = t["junction"]
    if t["feasible"]:
        cx, cy = t["pcb_center"]; long_y = t["screen_up"] in ("東", "西")
        hx, hy = (27.3 / 2, 27.8 / 2) if long_y else (27.8 / 2, 27.3 / 2)
        outline(cx, cy, hx, hy, 118.6, 0.8, HUBC[t["hub"]], "plan")
        sx, sy = t["slot_center"]
        text(f"{t['id']}  HUB {t['hub']} " + t['addr'] + f"  {t.get('wire_cm', '')} cm", (cx, cy + (6 if cy < 0 else -6), 119), 3.6, (0.05, 0.05, 0.05, 1), tag="plan")
        text(f"slot {t['slot_size'][0]}x{t['slot_size'][1]}", (cx, cy + (1 if cy < 0 else -1), 119), 3.0, (0.05, 0.05, 0.05, 1), tag="plan")
        text(f"AA {t['offset_mm']} mm", (cx, cy + (-4 if cy < 0 else 4), 119), 3.0, (0.05, 0.05, 0.05, 1), tag="plan")
    else:
        cx, cy = t["nearest_pcb_center"]
        outline(cx, cy, 13.9, 13.9, 147.5, 0.8, (0.9, 0.1, 0.1, 1), "plan")
        text("X", (J[0] + (14 if J[0] == 0 and J[1] == 0 else 0), J[1] + (14 if J[0] == 0 and J[1] == 0 else 0), 147.6), 9, (0.9, 0.1, 0.1, 1), tag="plan")
        msg = {"C": "C: no fit (arm slots)", "N": "N: pod above / cam N", "S": "S: pod above / cam S", "E": "E: pod above / cam E", "W": "W: pod above / cam W"}[t["id"]]
        rot = (0, 0, math.radians(90)) if t["id"] in ("E", "W") else (0, 0, 0)
        text(msg, (cx + (8 if t["id"] == "E" else -8 if t["id"] == "W" else 0), cy + (8 if t["id"] == "N" else -8 if t["id"] in ("S",) else 0) + (18 if t["id"] == "C" else 0), 147.6), 3.4, (0.9, 0.1, 0.1, 1), rot=rot, tag="plan")
text("N", (0, 128, 119), 8, (0.1, 0.1, 0.1, 1), tag="plan")
# 仰視標籤（鏡像後由下往上看是正的）
for t in T:
    if t["feasible"]:
        a = t["active_center"]; text(t["id"], (a[0], a[1], 102.5), 5, (1, 0.9, 0.2, 1), mirror=True, tag="up")
    J = t["junction"]; text("+", (J[0], J[1], 102.5), 7, (1, 0.3, 0.9, 1), mirror=True, tag="up")

def shot(name, loc, target, up=(0, 1, 0), lens=35, ortho=None, hide=(), tag=None, res=(1300, 1300), clip=0.5):
    cd = bpy.data.cameras.new(name); cd.clip_start = clip; cd.clip_end = 5000
    if ortho: cd.type = "ORTHO"; cd.ortho_scale = ortho
    else: cd.lens = lens
    cam = bpy.data.objects.new(name, cd); sc.collection.objects.link(cam)
    f = (Vector(target) - Vector(loc)).normalized(); u = Vector(up); r = f.cross(u).normalized(); u = r.cross(f)
    cam.matrix_world = Matrix.Translation(loc) @ Matrix((r, u, -f)).transposed().to_4x4()
    hidden = [o for o in sc.objects if any(h in o.name for h in hide) and not o.hide_render]
    for o in hidden: o.hide_render = True
    for o in extra: o.hide_render = o.get("tag") not in (tag, "all")
    sc.camera = cam; sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(OUT, name + ".png"); bpy.ops.render.render(write_still=True)
    for o in hidden: o.hide_render = False
    bpy.data.objects.remove(cam, do_unlink=True)

UP_HIDE = ("2F_", "樓梯塔", "ASM_Ground", "_原始")
# 1. 平面圖（俯視；北在上、東在右）：封孔板頂面、麵包板座、4 個長條孔與模組外框（顏色＝負責 HUB）、不可行路口標 X
shot("平面圖_穿孔位置與HUB", (0, 0, 400), (0, 0, 0), ortho=262, hide=UP_HIDE + ("Breadboard", "HUB8735", "銷"), tag="plan")
# 2. 由下往上看整體（東西左右相反）
shot("3D_仰視整體_東在左", (0, 0, 40), (0, 0, 200), ortho=262, hide=UP_HIDE, tag="up")
shot("3D_斜仰視_拿掉樓層盒", (230, -260, -40), (0, 0, 108), lens=40, hide=UP_HIDE + ("1F_樓層",), tag="up", res=(1400, 1000))
# 3. NW 路口剖面：剖面 x = 孔中心，從西往東看（排針 4 支、杜邦母座穿過天花板＋封孔板頂板、上方到 2F 樓板的淨空）
nw = next(t for t in T if t["id"] == "NW"); sx, sy = nw["slot_center"]
for z, s in ((103.0, "OLED glass  z 103.0 (5.0 mm below ceiling)"), (107.0, "foam tape 2.0 mm"), (112.0, "1F ceiling  z 108-116"),
             (116.8, "lid sheet  z 116-117.6"), (122.5, "Dupont top  z 122.5 (+5 mm bend)"), (150.8, "2F floor  z 150  (clearance 27.5 mm)")):
    text(s, (sx + 1, sy + 33, z), 1.8, (1, 1, 1, 1), rot=(math.radians(90), 0, math.radians(-90)), tag="sec")
shot("3D_剖面_NW路口穿孔", (sx - 200, sy + 12, 125), (sx, sy + 12, 125), up=(0, 0, 1), ortho=62, hide=("2F_樓梯", "樓梯塔", "ASM_Ground", "_原始"),
     tag="sec", res=(1400, 1400), clip=199.9)
# 3b. N 邊中點剖面：長孔穿過十字臂（北臂）插槽的塞子（封孔板的一部分）；剖面 y = 孔中心，從南往北看
ne = next(t for t in T if t["id"] == "N"); ex_, ey_ = ne["slot_center"]
for z, s_ in ((103.0, "OLED glass  z 103.0 (5.0 mm below ceiling)"), (107.0, "foam tape 2.0 mm"), (112.0, "ArmN slot plug (lid part)  z 108.2-117.6, slot cut through"),
              (122.5, "Dupont top  z 122.5 (+5 mm bend)"), (150.8, "2F floor  z 150")):
    text(s_, (ex_ + 33, ey_ + 1, z), 1.8, (1, 1, 1, 1), rot=(math.radians(90), 0, 0), tag="esec")
shot("3D_剖面_N邊中點穿過塞子", (ex_ + 12, ey_ - 200, 125), (ex_ + 12, ey_, 125), up=(0, 0, 1), ortho=62, hide=("2F_樓梯", "樓梯塔", "ASM_Ground", "_原始"),
     tag="esec", res=(1400, 1400), clip=199.9)
# 4. 中心放大平面圖（俯視、拿掉封孔板：十字臂插槽在天花板上是開口，可看出模組外框蓋住哪些插槽）
c = next(t for t in T if t["id"] == "C"); cx, cy = c["pcb_center"]; csx, csy = c["slot_center"]
outline(cx, cy, 27.8 / 2, 27.3 / 2, 116.6, 0.6, (0.95, 0.75, 0.1, 1), "cplan")
for t_ in T:
    if t_["id"] in "NESW":
        hx_, hy_ = (27.3 / 2, 27.8 / 2) if t_["screen_up"] in ("東", "西") else (27.8 / 2, 27.3 / 2)
        outline(*t_["pcb_center"], hx_, hy_, 116.6, 0.6, (0.1, 0.8, 0.85, 1), "cplan")
        text(f"{t_['id']}  s50 / 49 mm from C", (t_["pcb_center"][0], t_["pcb_center"][1] + (16 if t_['id'] in 'EW' else 0) + (0 if t_['id'] in 'EW' else (16 if t_['id'] == 'N' else -16)), 116.8), 2.6, (0.05, 0.05, 0.05, 1), tag="cplan")
for (x, y, s, sz) in ((-17, 30, "ArmN slot", 3.0), (-28, -16, "ArmW slot", 3.0), (28, -16, "ArmE slot", 3.0), (-18, -30, "ArmS slot", 3.0),
                      (cx, cy + 9, "C  0.96in 27.8x27.3", 2.6), (csx, csy - 4, "slot 11.4x3.4 (solid ceiling)", 2.4),
                      (cx, cy + 5, "H7  Wire 0x3C", 2.4), (0, -1.0, "+ junction (0,0)", 2.2)):
    text(s, (x, y, 116.8), sz, (0.05, 0.05, 0.05, 1), tag="cplan")
shot("平面圖_十字臂與中心放大_拿掉封孔板", (0, 0, 400), (0, 0, 0), ortho=150, hide=UP_HIDE + ("1F_天花板封孔板", "Breadboard", "HUB8735", "銷"), tag="cplan")
# 5. 中心剖面：剖面 y = 長條孔中心，從南往北看（4 支排針與杜邦母座排成一列穿過天花板＋封孔板頂板）
for z, s in ((103.0, "OLED glass  z 103.0 (5.0 mm)"), (107.0, "foam tape 2.0 mm"), (112.0, "1F ceiling  z 108-116 (solid here)"),
             (116.8, "lid sheet  z 116-117.6"), (122.5, "Dupont top  z 122.5"), (150.8, "2F floor  z 150")):
    text(s, (csx + 33, csy + 1, z), 1.8, (1, 1, 1, 1), rot=(math.radians(90), 0, 0), tag="csec")
shot("3D_剖面_中心路口穿孔", (csx + 12, csy - 200, 125), (csx + 12, csy, 125), up=(0, 0, 1), ortho=62, hide=("2F_樓梯", "樓梯塔", "ASM_Ground", "_原始"),
     tag="csec", res=(1400, 1400), clip=199.9)
# 6. 中心由下往上看（近景）
shot("3D_仰視_中心近景", (25, -30, 30), (0, 3, 106), lens=24, hide=UP_HIDE + ("1F_樓層",), tag="up", res=(1400, 1000))
print("renders done")
