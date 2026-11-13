"""
拉遠的 3D 全景（從斜下方看整個 1F）：渲染時切掉樓層盒的地板（只留半透明的牆，看得出走廊），，9 塊 OLED 顯示區亮色並標路口名稱。只出圖，不存檔。
  blender -b fire_model_oled_through_hole.blend --python render_panorama.py -- <輸出資料夾>
"""
import bpy, sys, os, math, json
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index("--") + 1]; os.makedirs(OUT, exist_ok=True)
sc = bpy.data.scenes["Assembly_Full"]
T = [t for t in json.load(open(os.path.join(os.path.dirname(bpy.data.filepath), "placements.json"), encoding="utf-8")) if "junction" in t]
sc.render.engine = "CYCLES"; sc.cycles.samples = 96; sc.cycles.use_denoising = True; sc.view_settings.view_transform = "Standard"
if sc.world is None: sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True; bg = sc.world.node_tree.nodes.get("Background"); bg.inputs[0].default_value = (0.93, 0.94, 0.97, 1); bg.inputs[1].default_value = 0.5

def mat(name, color, emit=0.0, alpha=1.0):
    m = bpy.data.materials.new("P_" + name); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear(); out = nt.nodes.new("ShaderNodeOutputMaterial")
    if emit:
        e = nt.nodes.new("ShaderNodeEmission"); e.inputs[0].default_value = color; e.inputs[1].default_value = emit; nt.links.new(e.outputs[0], out.inputs[0])
    else:
        b = nt.nodes.new("ShaderNodeBsdfPrincipled"); b.inputs["Base Color"].default_value = color; b.inputs["Alpha"].default_value = alpha
        b.inputs["Roughness"].default_value = 0.6; nt.links.new(b.outputs[0], out.inputs[0])
    return m
def setmat(o, m):
    if o.type in ("MESH", "CURVE", "FONT"): o.data.materials.clear(); o.data.materials.append(m)
ceil, lid, floor, pod = mat("ceil", (0.86, 0.86, 0.83, 1)), mat("lid", (0.62, 0.68, 0.85, 1)), mat("floor", (0.3, 0.33, 0.4, 1), alpha=0.55), mat("pod", (0.6, 0.55, 0.48, 1))
aa, glass, pcb, lens = mat("aa", (0.1, 1.0, 1.0, 1), emit=8), mat("glass", (0.02, 0.02, 0.02, 1)), mat("pcb", (0.1, 0.25, 0.6, 1)), mat("lens", (0.9, 0.15, 0.15, 1), emit=1.5)
other, lab = mat("other", (0.5, 0.5, 0.52, 1)), mat("lab", (1.0, 0.85, 0.1, 1), emit=6)
for o in sc.objects:
    n = o.name
    if n.startswith(("2F_", "樓梯塔", "ASM_Ground")): o.hide_render = True; continue
    if any(k in n for k in ("杜邦線", "共用線", "電源線", "USB線")): setmat(o, mat("w" + str(tuple(o.color)), tuple(o.color), emit=1.0)); continue
    setmat(o, ceil if n == "1F_天花板" else lid if n == "1F_天花板封孔板" else floor if n == "1F_樓層" else pod if "麵包版座" in n
           else aa if "顯示區" in n else glass if "玻璃" in n else pcb if ("_PCB" in n or "背面零件" in n) else lens if "Lens" in n else other)

# 切掉樓層盒的地板（z < 8.5），只留牆；只在這次渲染，不存檔
import bmesh
fb = sc.objects["1F_樓層"]; fb.data = fb.data.copy()
cme = bpy.data.meshes.new("cut"); bm = bmesh.new(); r_ = bmesh.ops.create_cube(bm, size=1.0)
for v in r_["verts"]: v.co = Vector((v.co.x * 300, v.co.y * 300, 3.75 + v.co.z * 9.5))
bm.to_mesh(cme); bm.free(); cut = bpy.data.objects.new("cut", cme); sc.collection.objects.link(cut)
m_ = fb.modifiers.new("b", "BOOLEAN"); m_.operation = "DIFFERENCE"; m_.object = cut; m_.solver = "EXACT"
with bpy.context.temp_override(object=fb, active_object=fb): bpy.ops.object.modifier_apply(modifier=m_.name)
bpy.data.objects.remove(cut, do_unlink=True)

def label(body, loc, size):
    cu = bpy.data.curves.new("l", "FONT"); cu.body = body; cu.size = size; cu.align_x = "CENTER"; cu.align_y = "CENTER"; cu.extrude = 0.2
    ob = bpy.data.objects.new("l_" + body, cu); sc.collection.objects.link(ob); ob.location = loc; setmat(ob, lab); return ob
CAM = Vector((-170, -290, -260)); TGT = Vector((0, 0, 100))
for t in T:
    a = t["active_center"]; ob = label(t["id"], (a[0], a[1] - 22 if t["id"] in ("N", "S", "C") else a[1], 96), 12)
    ob.rotation_euler = (CAM - ob.location).to_track_quat("Z", "Y").to_euler()
light = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); light.data.energy = 4.0e5; light.data.size = 200
sc.collection.objects.link(light); light.location = (0, 0, -120); light.rotation_euler = (Vector((0, 0, 100)) - light.location).to_track_quat("-Z", "Y").to_euler()
cd = bpy.data.cameras.new("c"); cd.lens = 42; cd.clip_start = 1; cd.clip_end = 5000
cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam)
f = (TGT - CAM).normalized(); u = Vector((0, 0, 1)); r = f.cross(u).normalized(); u = r.cross(f)
cam.matrix_world = Matrix.Translation(CAM) @ Matrix((r, u, -f)).transposed().to_4x4(); sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = 2000, 1400
sc.render.filepath = os.path.join(OUT, "3D_拉遠全景_九塊OLED.png"); bpy.ops.render.render(write_still=True)
print("pano done")
