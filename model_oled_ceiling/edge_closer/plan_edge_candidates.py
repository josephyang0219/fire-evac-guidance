"""
N 邊中點放大平面圖：現行 36.5 mm 與更近的候選位置（模組外框＋長條孔）。拿掉封孔板與麵包板座，看得到天花板上的鏡頭孔與排線孔開口。
  blender -b <fire_model.blend 的複本> --python plan_edge_candidates.py -- <輸出資料夾>
"""
import bpy, bmesh, sys, os, json
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index("--") + 1]; os.makedirs(OUT, exist_ok=True)
sc = bpy.data.scenes["Assembly_Full"]
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading; sh.light = "STUDIO"; sh.color_type = "OBJECT"; sh.show_cavity = True
for o in sc.objects:
    if o.name == "1F_天花板": o.color = (0.82, 0.82, 0.8, 1)
    if o.name.startswith(("2F_", "樓梯塔", "ASM_Ground")) or o.name in ("1F_天花板封孔板",) or any(k in o.name for k in ("麵包版座", "Breadboard", "HUB8735", "支撐柱", "銷")):
        o.hide_render = True
PW, PH, PIN = 27.8, 27.3, 27.3 / 2 - 1.68
D = {"N": (0, 1), "E": (1, 0), "S": (0, -1), "W": (-1, 0)}
C = [("36.5 mm (now, solid)", (-36.5, 96.0), "S", (0.1, 0.55, 0.9, 1)),
     ("29 mm (out of frame)", (31.1, 96.5), "E", (0.1, 0.7, 0.2, 1)),
     ("26 mm (right edge 0.5%)", (28.1, 96.5), "E", (0.95, 0.6, 0.0, 1)),
     ("23.4 mm (nearest, 2.3%)", (25.5, 97.0), "E", (0.9, 0.1, 0.1, 1))]
def rect(cx, cy, hx, hy, z, w, color, filled=False):
    me = bpy.data.meshes.new("r"); bm = bmesh.new()
    bars = [(cx - hx, cx + hx, cy - hy, cy + hy)] if filled else [(cx - hx, cx + hx, cy + hy - w, cy + hy), (cx - hx, cx + hx, cy - hy, cy - hy + w), (cx - hx, cx - hx + w, cy - hy, cy + hy), (cx + hx - w, cx + hx, cy - hy, cy + hy)]
    for x0, x1, y0, y1 in bars:
        r = bmesh.ops.create_cube(bm, size=1.0)
        for v in r["verts"]: v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0), z + v.co.z * 0.3))
    bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new("r", me); sc.collection.objects.link(ob); ob.color = color
def text(s, loc, size, color):
    cu = bpy.data.curves.new("t", "FONT"); cu.body = s; cu.size = size; cu.align_x = "CENTER"; cu.align_y = "CENTER"
    ob = bpy.data.objects.new("t", cu); sc.collection.objects.link(ob); ob.location = loc; ob.color = color
for k, (lab, (cx, cy), up, col) in enumerate(C):
    u = Vector((*D[up], 0)); hx, hy = (PH / 2, PW / 2) if up in "EW" else (PW / 2, PH / 2)
    z = 116.5 + 0.4 * k
    rect(cx, cy, hx, hy, z, 0.7, col)
    sx, sy = cx + u.x * PIN, cy + u.y * PIN; shx, shy = (3.4 / 2, 11.4 / 2) if up in "EW" else (11.4 / 2, 3.4 / 2)
    rect(sx, sy, shx, shy, z, 0, col, filled=True)
    ax, ay = cx - u.x * 2.15, cy - u.y * 2.15
    rect(ax, ay, 0.9, 0.9, z + 0.2, 0, col, filled=True)
    text(lab, (cx + (0 if k == 0 else 0), 124 - 4.2 * k if k else 75, 118), 3.0, col)
rect(0, 99, 0.6, 0.6, 118, 0, (1, 0, 1, 1), filled=True); text("junction (0,99)", (0, 103, 118), 2.6, (1, 0, 1, 1))
text("lens hole", (0, 90, 118), 2.6, (0.2, 0.2, 0.2, 1)); text("ring cable slot (plug removed in this view)", (57, 87, 118), 2.4, (0.2, 0.2, 0.2, 1))
text("N pod footprint x +-29.5 (above ceiling)", (0, 50, 118), 2.6, (0.4, 0.2, 0.0, 1))
rect(0, 83.5, 29.5, 36.5, 116.2, 0.5, (0.5, 0.3, 0.1, 1))
cd = bpy.data.cameras.new("c"); cd.type = "ORTHO"; cd.ortho_scale = 120
cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); cam.location = (0, 92, 300); sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = 1500, 1000
sc.render.filepath = os.path.join(OUT, "平面圖_N邊中點候選位置.png"); bpy.ops.render.render(write_still=True)
print("plan done")
