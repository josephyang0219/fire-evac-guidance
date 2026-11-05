"""
1F 天花板 OLED 的檢查渲染圖（Workbench）。在 add_ceiling_oled.py 輸出的 .blend 上執行：
  blender -b fire_model_oled_ceiling_1f.blend --python render_checks.py -- <輸出資料夾>
"""
import bpy, sys, os, math, json
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index("--") + 1]
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading; sh.light = "STUDIO"; sh.color_type = "OBJECT"; sh.show_cavity = True; sh.show_object_outline = True
sc.render.film_transparent = False
sc.world.color = (0.05, 0.05, 0.06) if sc.world else None

COL = {"1F_天花板": (0.82, 0.82, 0.80, 1), "1F_天花板封孔板": (0.35, 0.45, 0.85, 1), "1F_樓層": (0.25, 0.25, 0.27, 1)}
for o in sc.objects:
    if o.name in COL: o.color = COL[o.name]
    elif "焊線" in o.name: pass
    elif "Lens" in o.name: o.color = (0.9, 0.15, 0.15, 1)
    elif "麵包版座" in o.name: o.color = (0.55, 0.5, 0.45, 1)
    elif "顯示區" in o.name: o.color = (0.2, 0.9, 1.0, 1)
    elif "OLED" in o.name and "玻璃" in o.name: o.color = (0.02, 0.02, 0.02, 1)
    elif "OLED" in o.name and "PCB" in o.name: o.color = (0.1, 0.3, 0.7, 1)

# 標籤：放在天花板下方，鏡像後由下往上看才是正的
P = json.load(open(os.path.join(os.path.dirname(bpy.data.filepath), "placements.json"), encoding="utf-8")) \
    if os.path.exists(os.path.join(os.path.dirname(bpy.data.filepath), "placements.json")) else []
labels, top_labels = [], []
def label(text, x, y, z=106.5, size=7, color=(1, 0.9, 0.2, 1), top=False):
    cu = bpy.data.curves.new("lbl", "FONT"); cu.body = text; cu.size = size; cu.align_x = "CENTER"; cu.align_y = "CENTER"
    ob = bpy.data.objects.new("lbl_" + text, cu); sc.collection.objects.link(ob)
    ob.location = (x, y, z); ob.scale = (1 if top else -1, 1, 1); ob.color = color
    (top_labels if top else labels).append(ob); return ob
for p in P:
    a = p["active_center"]; j = p["junction"]
    label(p["id"], a[0], a[1] - 0.0, size=6)
    label("+", j[0], j[1], size=8, color=(1, 0.3, 0.9, 1))
    label(p["id"] + "→" + p["hub"], a[0], a[1], z=119, size=6, color=(1, 1, 1, 1), top=True)

def shot(name, loc, target, lens=35, ortho=None, hide=(), up=(0, 1, 0), res=(1400, 1000), xray=False, show_labels=True, clip=1, top=False):
    cd = bpy.data.cameras.new(name); cd.clip_start = clip; cd.clip_end = 5000
    if ortho: cd.type = "ORTHO"; cd.ortho_scale = ortho
    else: cd.lens = lens
    cam = bpy.data.objects.new(name, cd); sc.collection.objects.link(cam); cam.location = loc
    f = (Vector(target) - Vector(loc)).normalized(); u = Vector(up); r = f.cross(u).normalized(); u = r.cross(f)
    cam.matrix_world = Matrix.Translation(loc) @ Matrix((r, u, -f)).transposed().to_4x4()
    hidden = [o for o in sc.objects if any(h in o.name for h in hide) and not o.hide_render]
    for o in hidden: o.hide_render = True
    for o in labels: o.hide_render = not show_labels
    for o in top_labels: o.hide_render = not top
    sh.show_xray = xray; sh.xray_alpha = 0.45
    sc.camera = cam; sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(OUT, name + ".png"); bpy.ops.render.render(write_still=True)
    for o in hidden: o.hide_render = False
    bpy.data.objects.remove(cam, do_unlink=True)

UP_HIDE = ("2F_", "樓梯塔", "ASM_Ground", "Obstacle", "Gate")
# 1. 由下往上看整個 1F 天花板（相機在室內 z 40 往上，牆被裁切成深色帶）。注意：由下往上看東西左右相反
shot("仰視_1F天花板全體_東在左", (0, 0, 40), (0, 0, 200), ortho=262, hide=UP_HIDE, up=(0, 1, 0), clip=0.5, res=(1300, 1300))
# 2～4. 路口特寫（人站在走廊往上看）
shot("仰視_N邊中點特寫", (0, 40, 20), (0, 82, 108), lens=24, hide=UP_HIDE + ("1F_樓層",), show_labels=False)
shot("仰視_NW角落特寫", (-75, 70, 30), (-99, 96, 108), lens=24, hide=UP_HIDE + ("1F_樓層",), show_labels=False)
shot("仰視_SE角落外接特寫", (75, -80, 30), (97, -100, 104), lens=24, hide=UP_HIDE + ("1F_樓層",), show_labels=False)
# 5. 俯視、拿掉封孔板頂板與設備，看排線溝、焊線（顏色＝負責的 HUB：N 紅、E 綠、S 黃、W 紫）
shot("俯視_去封孔板_排線溝與焊線", (0, 0, 400), (0, 0, 0), ortho=262,
     hide=UP_HIDE + ("1F_天花板封孔板", "麵包版座", "Breadboard", "HUB8735", "支撐柱", "銷"), up=(0, 1, 0), show_labels=False, top=True, res=(1300, 1300))
# 6. 斜下方剖視（拿掉樓層盒）
shot("斜仰視_拿掉樓層盒", (230, -260, -40), (0, 0, 108), lens=40, hide=UP_HIDE + ("1F_樓層",), show_labels=True)
# 7. 鏡頭視角模擬（evac.py 光學模型：位置 (0,92,111)、往中心傾斜 18°；Workbench 只能透視投影，用水平 112° 近似）
for cn, rz in (("N", 0.0), ("E", -90.0)):
    R = Matrix.Rotation(math.radians(rz), 3, "Z")
    pos = R @ Vector((0, 92, 111)); ax = R @ Matrix.Rotation(math.radians(-18), 3, "X") @ Vector((0, 0, -1))
    up = R @ Matrix.Rotation(math.radians(-18), 3, "X") @ Vector((0, -1, 0))
    cd_lens = 36 / (2 * math.tan(math.radians(112 / 2)))
    shot(f"鏡頭視角_1F{cn}_水平112度", tuple(pos), tuple(pos + ax * 50), lens=cd_lens, hide=("2F_", "樓梯塔", "ASM_Ground", "Lens_" + cn),
         up=tuple(up), res=(1280, 720), show_labels=False, clip=0.5)
print("renders done")
