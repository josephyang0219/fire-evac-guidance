"""
十字臂整段（邊中點 → 中心）的可行／不可行區間平面圖。讀 arm_sweep_result.json。
  blender -b <fire_model.blend 的複本> --python plan_arms.py -- <arm_sweep_result.json> <輸出資料夾>
"""
import bpy, bmesh, sys, os, json
from mathutils import Vector

A = sys.argv[sys.argv.index("--") + 1:]; RES, OUT = A[0], A[1]; os.makedirs(OUT, exist_ok=True)
T = json.load(open(RES, encoding="utf-8"))
sc = bpy.data.scenes["Assembly_Full"]
sc.render.engine = "BLENDER_WORKBENCH"; sh = sc.display.shading; sh.light = "STUDIO"; sh.color_type = "OBJECT"; sh.show_cavity = True
for o in sc.objects:
    if o.name == "1F_天花板": o.color = (0.82, 0.82, 0.8, 1)
    if "麵包版座" in o.name: o.color = (0.55, 0.5, 0.45, 1)
    if o.name.startswith(("2F_", "樓梯塔", "ASM_Ground")) or o.name == "1F_天花板封孔板" or any(k in o.name for k in ("Breadboard", "HUB8735", "銷")):
        o.hide_render = True
def rect(x0, x1, y0, y1, z, color):
    me = bpy.data.meshes.new("r"); bm = bmesh.new(); r = bmesh.ops.create_cube(bm, size=1.0)
    for v in r["verts"]: v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0), z + v.co.z * 0.3))
    bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new("r", me); sc.collection.objects.link(ob); ob.color = color
def text(s, loc, size, color, rot=0.0):
    cu = bpy.data.curves.new("t", "FONT"); cu.body = s; cu.size = size; cu.align_x = "CENTER"; cu.align_y = "CENTER"
    ob = bpy.data.objects.new("t", cu); sc.collection.objects.link(ob); ob.location = loc; ob.color = color; ob.rotation_euler = (0, 0, rot)
ARMS = {"N": ((0, 99), (0, -1), (1, 0)), "E": ((99, 0), (-1, 0), (0, 1)), "S": ((0, -99), (0, 1), (1, 0)), "W": ((-99, 0), (1, 0), (0, 1))}
GREEN, RED, ORANGE, GREY = (0.1, 0.7, 0.2, 1), (0.85, 0.15, 0.1, 1), (0.95, 0.55, 0.0, 1), (0.3, 0.3, 0.3, 1)
Z = 148.0
for arm, (J, a, b) in ARMS.items():
    rows = T[arm]; ok = [r["s"] for r in rows if "up" in r]; s0, s1 = min(ok), max(ok)
    segs = [(0, 29.5, RED, "module over lens hole"), (29.5, s0 - 0.5, ORANGE, "slot under pod base"), (s0 - 0.5, s1 + 0.5, GREEN, f"OK s {s0}-{s1}"),
            (s1 + 0.5, 99, RED, "hits centre OLED")]
    for lo, hi, col, lab in segs:
        p0 = Vector(J) + Vector(a) * lo; p1 = Vector(J) + Vector(a) * hi
        x0, x1 = sorted((p0.x, p1.x)); y0, y1 = sorted((p0.y, p1.y))
        w = 3.0
        if a[0] == 0: rect(x0 - w, x1 + w, y0, y1, Z, col) if False else rect(-w, w, y0, y1, Z, col)
        else: rect(x0, x1, -w, w, Z, col)
        mid = (p0 + p1) / 2; off = Vector(b) * 13
        rot = 1.5708 if a[0] == 0 else 0.0
        text(lab, (mid.x + off.x, mid.y + off.y, Z + 0.5), 3.2, col if col != GREEN else (0.0, 0.45, 0.1, 1), rot)
    for s_ in (41, 50, 60, s1):
        p = Vector(J) + Vector(a) * s_
        rect(p.x - 2.2, p.x + 2.2, p.y - 2.2, p.y + 2.2, Z + 0.6, (1, 1, 1, 1))
rect(-13.9, 13.9, -8.15, 19.15, Z - 0.5, (0.2, 0.75, 0.9, 1)); text("centre OLED", (0, 5.5, Z + 0.5), 3.0, (0.05, 0.05, 0.05, 1))
rect(-45.25, -14.75, 9.1, 26.9, Z - 0.5, (0.2, 0.3, 0.75, 1)); text("TCA9548A (movable)", (-30, 30, Z + 0.5), 2.8, (0.1, 0.1, 0.5, 1))
text("white squares: candidates s41 / s50 / s60 / max  (s = display distance from edge junction)", (0, -128, Z), 3.4, (0.05, 0.05, 0.05, 1))
cd = bpy.data.cameras.new("c"); cd.type = "ORTHO"; cd.ortho_scale = 270
cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); cam.location = (0, -4, 400); sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = 1400, 1400
sc.render.filepath = os.path.join(OUT, "平面圖_十字臂可行區間.png"); bpy.ops.render.render(write_still=True)
print("plan done")
