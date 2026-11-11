"""
邊中點 OLED 沿十字臂往中心移動的候選位置：在負責那台鏡頭的 576×320 畫面裡落在哪裡、遮掉它會損失多少走廊地面。
用 fire_evac_v2/app/evac.py 的光學模型（等立體角魚眼 f = 2.9821 mm、感光 5.6×3.15 mm、位置 rot(rz)·(0,92,111)、往中心傾斜 18°）。
  blender -b <fire_model.blend 的複本> --python camera_view_candidates.py -- <輸出資料夾>
輸出：每個候選位置一張鏡頭視角模擬圖（Cycles 等立體角魚眼，OLED 紅色、像素外框黃色）＋ candidates.json
"""
import bpy, bmesh, sys, os, math, json
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

OUT = sys.argv[sys.argv.index("--") + 1]; os.makedirs(OUT, exist_ok=True)
sc = bpy.data.scenes["Assembly_Full"]; bpy.context.window.scene = sc if bpy.context.window else None
F_LENS, SW, SH = 2.9821, 5.6, 3.15
W, H = 576, 320
SCALE = W / SW                                   # px / mm
FLOOR_Z = 8.0
# 十字臂往中心的候選（arm_sweep.py）：N 臂 s = 顯示區離 N 邊中點的距離；cam = 拿哪台鏡頭渲染
CAM_RZ = {"N": 0.0, "E": -90.0, "S": 180.0, "W": 90.0}
CANDS = [
    dict(name="N臂_s41_離中心58mm", edge="N", off=41, center=(0.0, 55.85), up="S", cuts_plug=True, render=True),
    dict(name="N臂_s50_離中心49mm", edge="N", off=50, center=(0.0, 46.85), up="S", cuts_plug=True, render=True),
    dict(name="N臂_s60_離中心39mm", edge="N", off=60, center=(0.0, 36.85), up="S", cuts_plug=True, render=True),
    dict(name="N臂_s65_離中心34mm", edge="N", off=65, center=(-2.15, 34.0), up="W", cuts_plug=False, render=True),
    dict(name="N臂_s50_從1F_E看", edge="N", cam="E", off=50, center=(0.0, 46.85), up="S", cuts_plug=True, render=True),
    dict(name="N臂_s50_從1F_W看", edge="N", cam="W", off=50, center=(0.0, 46.85), up="S", cuts_plug=True, render=True),
    dict(name="N臂_s50_從1F_S看", edge="N", cam="S", off=50, center=(0.0, 46.85), up="S", cuts_plug=True, render=True),
]
D = {"N": (0, 1), "E": (1, 0), "S": (0, -1), "W": (-1, 0)}
PW, PH, PROT = 27.8, 27.3, 5.0

def cam_pose(rz):
    Rz = Matrix.Rotation(math.radians(rz), 3, "Z")
    R = Rz @ Matrix.Rotation(math.radians(-18), 3, "X")
    return Rz @ Vector((0, 92, 111)), R
def project(R, p, P):
    q = R.transposed() @ (P - p)
    th = math.acos(max(-1, min(1, -q.z / q.length))); r = 2 * F_LENS * math.sin(th / 2); ph = math.atan2(q.y, q.x)
    return W / 2 + r * math.cos(ph) * SCALE, H / 2 - r * math.sin(ph) * SCALE, math.degrees(th)
def pix_dir(R, u, v):
    xs, ys = (u - W / 2) / SCALE, (H / 2 - v) / SCALE; r = math.hypot(xs, ys)
    th = 2 * math.asin(min(1.0, r / (2 * F_LENS))); ph = math.atan2(ys, xs)
    return (R @ Vector((math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), -math.cos(th)))).normalized(), math.degrees(th)

dg = bpy.context.evaluated_depsgraph_get()
def bvh_of(objs):
    vs, fs = [], []
    for o in objs:
        me = o.evaluated_get(dg).to_mesh(); M = o.matrix_world; b = len(vs)
        vs += [M @ v.co for v in me.vertices]; fs += [tuple(b + i for i in f.vertices) for f in me.polygons]
    return BVHTree.FromPolygons(vs, fs)
scene_objs = [o for o in sc.objects if o.type == "MESH" and o.visible_get() and (o.name.startswith("1F_") or o.name.startswith("2F_"))
              and "Lens" not in o.name and "HUB8735" not in o.name]
B_scene = bvh_of(scene_objs)

def module_corners(c):
    up = Vector((*D[c["up"]], 0)); r = Vector((0, 0, 1)).cross(up); ctr = Vector((*c["center"], 0))
    hu, hv = PW / 2, PH / 2
    return [ctr + su * hu * r + sv * hv * up for su in (-1, 1) for sv in (-1, 1)], up, r, ctr

def make_module(c):
    cs, up, r, ctr = module_corners(c)
    me = bpy.data.meshes.new("cand"); bm = bmesh.new()
    rr = bmesh.ops.create_cube(bm, size=1.0)
    for v in rr["verts"]:
        v.co = ctr + v.co.x * PW * r + v.co.y * PH * up + Vector((0, 0, 108 - PROT / 2 + v.co.z * PROT))
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new("候選OLED", me); sc.collection.objects.link(ob)
    ob.visible_diffuse = False; ob.visible_glossy = False; ob.visible_transmission = False; ob.visible_shadow = False   # 只讓鏡頭直接看到，不照亮場景
    m = bpy.data.materials.new("cand_red"); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear(); e = nt.nodes.new("ShaderNodeEmission"); e.inputs[0].default_value = (1, 0.05, 0.05, 1); e.inputs[1].default_value = 1.5
    o = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(e.outputs[0], o.inputs[0]); me.materials.append(m)
    return ob

# ---------- 渲染設定：Cycles 等立體角魚眼，和 evac.py 相同的鏡頭參數 ----------
sc.render.engine = "CYCLES"; sc.cycles.samples = 48; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = W, H; sc.render.resolution_percentage = 100
if sc.world is None: sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True; bg = sc.world.node_tree.nodes.get("Background")
if bg: bg.inputs[0].default_value = (1, 1, 1, 1); bg.inputs[1].default_value = 0.4
for o in sc.objects:
    if o.name.startswith(("2F_", "樓梯塔", "ASM_Ground")) or "Lens" in o.name: o.hide_render = True
cd = bpy.data.cameras.new("ps5268"); cd.type = "PANO"
cd.panorama_type = "FISHEYE_EQUISOLID"; cd.fisheye_lens = F_LENS; cd.fisheye_fov = math.pi
cd.sensor_fit = "HORIZONTAL"; cd.sensor_width = SW; cd.sensor_height = SH; cd.clip_start = 0.5
cam = bpy.data.objects.new("ps5268_1FN", cd); sc.collection.objects.link(cam)
sc.camera = cam
ld = bpy.data.lights.new("headlight", "POINT"); ld.energy = 1.2e4; ld.shadow_soft_size = 5.0
head = bpy.data.objects.new("headlight", ld); sc.collection.objects.link(head)   # 鏡頭旁的照明，讓室內看得清楚

def draw_rect(path, box, color=(1, 0.9, 0.1, 1)):
    img = bpy.data.images.load(path); w, h = img.size; px = list(img.pixels)
    u0, v0, u1, v1 = [int(round(t)) for t in box]
    def put(u, v):
        if 0 <= u < w and 0 <= v < h:
            k = ((h - 1 - v) * w + u) * 4; px[k:k + 4] = color
    for t in range(2):
        for u in range(u0, u1 + 1): put(u, v0 - t); put(u, v1 + t)
        for v in range(v0, v1 + 1): put(u0 - t, v); put(u1 + t, v)
    img.pixels[:] = px; img.filepath_raw = path; img.save(); bpy.data.images.remove(img)

def in_corridor(x, y):
    """1F 走廊（環廊中心線 ±99、半寬 18；十字走廊半寬 21）"""
    ring = (abs(abs(x) - 99) <= 18 and abs(y) <= 117) or (abs(abs(y) - 99) <= 18 and abs(x) <= 117)
    cross = (abs(x) <= 21 and abs(y) <= 81) or (abs(y) <= 21 and abs(x) <= 81)
    return ring or cross

out = []
for c in CANDS:
    P0, R0 = cam_pose(CAM_RZ[c.get("cam", c["edge"])]); cam.matrix_world = Matrix.Translation(P0) @ R0.to_4x4()
    head.location = P0 + R0 @ Vector((0, 0, -6))
    ob = make_module(c)
    B_mod = bvh_of([ob])
    # 像素：OLED 外框 8 個角投影 → 外接框，再逐像素確認哪些真的先打到 OLED
    cs, up, r, ctr = module_corners(c)
    pts = [Vector((p.x, p.y, z)) for p in cs for z in (108 - PROT, 108)]
    uv = [project(R0, P0, p) for p in pts]
    u0 = max(0, int(min(t[0] for t in uv)) - 2); u1 = min(W - 1, int(max(t[0] for t in uv)) + 2)
    v0 = max(0, int(min(t[1] for t in uv)) - 2); v1 = min(H - 1, int(max(t[1] for t in uv)) + 2)
    hit_px = []; floor_pts = []; ang_min = 999; behind = {"天花板": 0, "牆／障礙物": 0, "走廊地面": 0, "房間地面或其他": 0}
    for u in range(u0, u1 + 1):
        for v in range(v0, v1 + 1):
            d, th = pix_dir(R0, u + 0.5, v + 0.5)
            if th > 90: continue
            hm = B_mod.ray_cast(P0, d, 500); hs = B_scene.ray_cast(P0, d, 500)
            if hm[0] is None or (hs[0] is not None and hs[2] < hm[2]): continue
            hit_px.append((u, v)); ang_min = min(ang_min, th)
            z = hs[0].z if hs[0] is not None else 999
            k = "天花板" if z > 100 else ("走廊地面" if abs(z - FLOOR_Z) < 0.6 and in_corridor(hs[0].x, hs[0].y) else ("房間地面或其他" if abs(z - FLOOR_Z) < 0.6 else "牆／障礙物"))
            behind[k] += 1
            if hs[0] is not None and abs(hs[0].z - FLOOR_Z) < 0.6 and in_corridor(hs[0].x, hs[0].y):
                floor_pts.append((hs[0].x, hs[0].y, (hs[0] - P0).length))
    res = dict(name=c["name"], offset_mm=c["off"], pcb_center=list(c["center"]), screen_up=c["up"], slot_cuts_ring_plug=c["cuts_plug"],
               camera="1F " + c.get("cam", c["edge"]), oled_pixels=len(hit_px))
    if hit_px:
        us = [p[0] for p in hit_px]; vs = [p[1] for p in hit_px]
        res.update(pixel_box=[min(us), min(vs), max(us), max(vs)], min_angle_from_axis_deg=round(ang_min, 1),
                   image_fraction_pct=round(100 * len(hit_px) / (W * H), 2),
                   at_edge=bool(min(us) <= 5 or max(us) >= W - 6 or min(vs) <= 5 or max(vs) >= H - 6),
                   masked_floor_pixels=len(floor_pts), behind_oled_pixels=behind)
        if floor_pts:
            res.update(masked_floor_x=[round(min(p[0] for p in floor_pts), 1), round(max(p[0] for p in floor_pts), 1)],
                       masked_floor_y=[round(min(p[1] for p in floor_pts), 1), round(max(p[1] for p in floor_pts), 1)])
    out.append(res)
    if c["render"]:
        path = os.path.join(OUT, f"鏡頭1F{c.get('cam', c['edge'])}視角_{c['name']}.png")
        sc.render.filepath = path; bpy.ops.render.render(write_still=True)
        if hit_px: draw_rect(path, res["pixel_box"])
    bpy.data.objects.remove(ob, do_unlink=True)
    print("CAND", json.dumps(res, ensure_ascii=False), flush=True)
json.dump(out, open(os.path.join(OUT, "candidates.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
