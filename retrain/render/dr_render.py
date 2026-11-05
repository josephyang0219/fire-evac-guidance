# -*- coding: utf-8 -*-
"""火場模型 domain randomization 渲染（7 類 YOLO 標註）。

只能在 fire_model.blend 的「複本」上執行，由 run_blender.py 啟動：
    blender -b <work>/fire_model_dr.blend -P dr_render.py -- --out <dir> --count 200 --seed 1

每張圖做三次 Cycles 渲染：
  1. 彩色圖（32 spp + 降噪，存 EXR 線性值，之後自己做曝光、白平衡、模糊、雜訊、JPEG）
  2. 遮罩 A：所有物件換成「發光強度 = 物件編號」的材質，煙隱藏 → 0–4、6 類的可見像素
  3. 遮罩 B：煙也顯示（縮成 0.85 倍）→ 煙的可見像素（被牆擋住的部分不算）
框 = 遮罩裡該物件可見像素的外接矩形，所以被牆擋住、出畫面的部分都自動扣掉。
另外用魚眼（等立體角）公式把物件頂點投影到畫面，檢查遮罩框一定落在投影框內，
結果寫在 meta/*.json，check_labels.py 會彙整。

類別：0 cabinet 1 boxes 2 furniture 3 rubble 4 gate 5 smoke 6 person
"""
import bpy, bmesh, sys, os, json, math, random, colorsys, time, argparse
import numpy as np
from mathutils import Vector, Matrix, Euler

SMOKE_REL_DIFF = 0.06  # 有煙／無煙亮度相對差超過 6% 才算看得到煙
CLASSES = ['cabinet', 'boxes', 'furniture', 'rubble', 'gate', 'smoke', 'person']
W, H = 576, 320
ORIGINAL_NAME = 'fire_model.blend'

# ---------------------------------------------------------------- 參數
def parse_args():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True)
    p.add_argument('--count', type=int, default=200)
    p.add_argument('--start', type=int, default=0)
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--prefix', default='dr')
    p.add_argument('--mode', choices=['normal', 'empty'], default='normal',
                   help='empty = 空場景負樣本（只有干擾物，沒有任何目標物）')
    p.add_argument('--samples', type=int, default=32)
    p.add_argument('--empty-prob', type=float, default=0.08)
    p.add_argument('--lid-open-prob', type=float, default=0.25)
    p.add_argument('--min-pixels', type=int, default=40)
    p.add_argument('--skip-existing', action='store_true')
    p.add_argument('--cpu', action='store_true')
    return p.parse_args(argv)

ARGS = parse_args()
if os.path.basename(bpy.data.filepath).lower() == ORIGINAL_NAME:
    raise SystemExit('拒絕執行：這是原檔 fire_model.blend，請用 run_blender.py 產生的複本')
if not ARGS.out.isascii():
    raise SystemExit('輸出路徑必須是英文（ASCII）：' + ARGS.out)

SC = bpy.data.scenes['FireModel']
if bpy.context.window is not None:
    bpy.context.window.scene = SC
VL = SC.view_layers[0]
COL = SC.collection

# ---------------------------------------------------------------- 場景固定設定
def setup_scene():
    # 1F 新版地板（環廊半寬 18、十字走廊半寬 21）與對應的閘門塞子
    tray = bpy.data.objects['Floor_Tray_G']
    if tray.name not in COL.objects:
        COL.objects.link(tray)
    # 舊地板、舊閘門、場外的障礙物原型都移出場景（只留網格給複製用）。
    # 用 unlink 而不是 hide_render，因為 ray_cast 看不到 hide_render。
    protos = [bpy.data.objects[n] for n in ['Floor_Tray', 'Gate_Plug', 'Gate_Plug_spare']]
    protos += list(bpy.data.collections['Obstacles'].objects)
    for o in protos:
        for c in list(o.users_collection):
            if c == COL or c.name in [x.name for x in COL.children_recursive]:
                c.objects.unlink(o)
    # 樓梯門和閘門共用 FM_Plug，給它獨立材質，避免沒標註的門和閘門永遠同色
    door = bpy.data.objects['StairDoor_Panel']
    if door.active_material and door.active_material.name == 'FM_Plug':
        door.active_material = door.active_material.copy()
        door.active_material.name = 'FM_Plug_door'

    r = SC.render
    r.engine = 'CYCLES'
    r.resolution_x, r.resolution_y, r.resolution_percentage = W, H, 100
    r.use_compositing = False
    r.use_sequencer = False
    r.use_persistent_data = True
    SC.view_settings.view_transform = 'Standard'
    SC.view_settings.look = 'None'
    SC.view_settings.exposure = 0.0
    SC.view_settings.gamma = 1.0
    cy = SC.cycles
    cy.use_animated_seed = False
    cy.max_bounces = 6
    cy.diffuse_bounces = 3
    cy.glossy_bounces = 2
    cy.transmission_bounces = 4
    cy.volume_bounces = 1
    cy.transparent_max_bounces = 8

    dev = 'CPU'
    if not ARGS.cpu:
        try:
            prefs = bpy.context.preferences.addons['cycles'].preferences
            for t in ('OPTIX', 'CUDA'):
                try:
                    prefs.compute_device_type = t
                except TypeError:
                    continue
                prefs.refresh_devices()
                gpus = [d for d in prefs.devices if d.type == t]
                if gpus:
                    for d in prefs.devices:
                        d.use = d.type == t
                    dev = t
                    break
        except Exception as e:
            print('GPU 設定失敗，改用 CPU：', e)
    cy.device = 'GPU' if dev != 'CPU' else 'CPU'
    print('[dr] device =', dev)
    return dev

DEVICE = setup_scene()

# 地板高度：從蓋子下方往下打射線
VL.update()
def floor_z_at(x, y):
    hit, loc, *_ = SC.ray_cast(VL.depsgraph, Vector((x, y, 100.0)), Vector((0, 0, -1)))
    return loc.z if hit else None
_fz = [floor_z_at(x, y) for x, y in [(0, -99), (-99, 0), (99, -50), (-50, 99), (0, 50), (-50, -99)]]
_fz = sorted(z for z in _fz if z is not None)
FLOOR_Z = _fz[len(_fz) // 2] if _fz else 8.0
print('[dr] floor z =', FLOOR_Z, _fz)

CAMS = ['Cam_N', 'Cam_E', 'Cam_S', 'Cam_W']
CAM_MW = {n: bpy.data.objects[n].matrix_world.copy() for n in CAMS}

def cam_clearance(mw):
    # 正前方＋上下左右各一條射線，回傳最近的撞擊距離。
    # 鏡頭本體（HUB8735_Lens_*）就包在相機位置上，Cycles 會略過 clip_start（1 mm）以內的東西，
    # 所以射線也從 clip_start 開始打；偏移後若退進鏡頭本體裡，這個距離會變成 0 → 拒絕。
    o = mw.translation
    R = mw.to_3x3()
    cs = bpy.data.objects['Cam_N'].data.clip_start
    best = 1e9
    for ax, ay in [(0, 0), (45, 0), (-45, 0), (0, 25), (0, -25)]:
        d = (R @ (Euler((math.radians(ay), math.radians(-ax), 0)).to_matrix() @ Vector((0, 0, -1)))).normalized()
        hit, loc, *_ = SC.ray_cast(VL.depsgraph, o + d * cs, d)
        best = min(best, (loc - o).length if hit else 1e9)
    return best

# 走廊（俯視矩形，mm）：環廊中心 ±99 半寬 18；十字走廊半寬 21
CORRIDORS = [(-117, 117, 81, 117), (-117, 117, -117, -81), (81, 117, -117, 117), (-117, -81, -117, 117),
             (-117, 117, -21, 21), (-21, 21, -117, 117)]
PILLARS = [(sx * 80.5 - 6, sx * 80.5 + 6, sy * 80.5 - 6, sy * 80.5 + 6) for sx in (-1, 1) for sy in (-1, 1)]
# 閘門槽位（中心、是否轉 90°、用哪個塞子）
GATE_SLOTS = ([((sx * 51, sy * 99), False, 'Gate_Plug_G36') for sx in (-1, 1) for sy in (-1, 1)] +
              [((sx * 99, sy * 51), True, 'Gate_Plug_G36') for sx in (-1, 1) for sy in (-1, 1)] +
              [((sx * 51, 0), False, 'Gate_Plug_G42') for sx in (-1, 1)] +
              [((0, sy * 51), True, 'Gate_Plug_G42') for sy in (-1, 1)])

OBSTACLE_PROTOS = {0: ['Cabinet_A_upright', 'Cabinet_B_fallen'], 1: ['Boxes_A_stacked', 'Boxes_B_scattered'],
                   2: ['Chair_A', 'Table_B_overturned'], 3: ['Rubble_A_pile', 'Rubble_B_beam']}

LID_SET = (['Floor_Lid', 'Lid_Seal', 'Roof_Cap', 'Roof_Plate'] + [f'Spacer_{i}' for i in range(4)] +
           [f'Camera_Pod_{d}' for d in 'NEWS'] +
           [o.name for o in bpy.data.collections['Lid_Fillers'].objects] +
           [o.name for o in bpy.data.collections['Electronics'].objects if o.type == 'MESH'])
LID_SET = [n for n in LID_SET if n in SC.objects]
CAM_CLEAR = {n: cam_clearance(CAM_MW[n]) for n in CAMS}
print('[dr] camera clearance mm =', {k: round(v, 1) for k, v in CAM_CLEAR.items()})

# ---------------------------------------------------------------- 小工具
def srgb_to_lin(c):
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)

def hsv_lin(h, s, v):
    return srgb_to_lin(colorsys.hsv_to_rgb(h % 1.0, max(0, min(1, s)), max(0, min(1, v))))

def kelvin_rgb(k):
    t = k / 100.0
    r = 255 if t <= 66 else 329.7 * (t - 60) ** -0.1332
    g = 99.47 * math.log(t) - 161.12 if t <= 66 else 288.12 * (t - 60) ** -0.0755
    b = 255 if t >= 66 else (0 if t <= 19 else 138.52 * math.log(t - 10) - 305.04)
    return tuple(max(0, min(255, x)) / 255.0 for x in (r, g, b))

def sock(node, ident, out=False):
    for s in (node.outputs if out else node.inputs):
        if s.identifier == ident:
            return s
    raise KeyError(ident)

def principled(mat):
    for n in mat.node_tree.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            return n
    return None

# 場景材質加上「雜訊混色」節點，每張圖改參數
DR_MATS = {}
def prepare_material(mat):
    if mat.name in DR_MATS:
        return DR_MATS[mat.name]
    bsdf = principled(mat)
    if bsdf is None:
        return None
    nt = mat.node_tree
    base = tuple(bsdf.inputs['Base Color'].default_value)
    noise = nt.nodes.new('ShaderNodeTexNoise')
    mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'
    rng_ = nt.nodes.new('ShaderNodeMapRange')
    nt.links.new(sock(noise, 'Fac', True), rng_.inputs['Value'])
    nt.links.new(rng_.outputs['Result'], sock(mix, 'Factor_Float'))
    nt.links.new(sock(mix, 'Result_Color', True), bsdf.inputs['Base Color'])
    DR_MATS[mat.name] = dict(mat=mat, bsdf=bsdf, base=base, noise=noise, mix=mix, rng=rng_)
    return DR_MATS[mat.name]

def set_material(h, color, rng, rough=None, noise_amt=None):
    a = sock(h['mix'], 'A_Color'); b = sock(h['mix'], 'B_Color')
    a.default_value = (*color, 1.0)
    k = rng.uniform(0.55, 1.25)
    b.default_value = (*(min(1, c * k) for c in color), 1.0)
    h['noise'].inputs['Scale'].default_value = rng.uniform(2, 25)
    h['noise'].inputs['Detail'].default_value = rng.uniform(0, 6)
    h['rng'].inputs['To Max'].default_value = rng.uniform(0, 0.6) if noise_amt is None else noise_amt
    h['bsdf'].inputs['Roughness'].default_value = rng.uniform(0.3, 0.85) if rough is None else rough

def jitter_color(base, rng):
    r, g, b = [x ** (1 / 2.2) for x in base[:3]]
    hh, s, v = colorsys.rgb_to_hsv(r, g, b)
    if rng.random() < 0.25:  # 25% 完全隨機色，避免模型只認顏色
        return hsv_lin(rng.random(), rng.uniform(0.1, 0.9), rng.uniform(0.2, 0.95))
    return hsv_lin(hh + rng.uniform(-0.06, 0.06), s * rng.uniform(0.6, 1.35), v * rng.uniform(0.6, 1.4))

SCENE_MATS = ['FM_Tray', 'FM_Lid', 'FM_Plug', 'FM_Plug_door', 'FM_Pod', 'FM_Spacer', 'FM_Stair',
              'FM_Mark_C_diamond', 'OB_Cabinet', 'OB_Boxes', 'OB_Chair', 'OB_Table', 'OB_Rubble']
for n in SCENE_MATS:
    if n in bpy.data.materials:
        prepare_material(bpy.data.materials[n])

def new_mat(name, color, rough=0.5, metal=0.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = principled(m)
    b.inputs['Base Color'].default_value = (*color, 1.0)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    return m

# 遮罩用覆寫材質：發光強度 = 物件編號
MASK_MAT = bpy.data.materials.new('MASK_Override')
try:
    MASK_MAT.use_nodes = True
except Exception:
    pass
_nt = MASK_MAT.node_tree
for n in list(_nt.nodes):
    _nt.nodes.remove(n)
_info = _nt.nodes.new('ShaderNodeObjectInfo')
_em = _nt.nodes.new('ShaderNodeEmission')
_out = _nt.nodes.new('ShaderNodeOutputMaterial')
_em.inputs['Color'].default_value = (1, 1, 1, 1)
_nt.links.new(_info.outputs['Object Index'], _em.inputs['Strength'])
_nt.links.new(_em.outputs['Emission'], _out.inputs['Surface'])

# ---------------------------------------------------------------- 物件生成
def link(obj):
    COL.objects.link(obj)
    return obj

def mesh_from_proto(name, newname):
    p = bpy.data.objects[name]
    o = bpy.data.objects.new(newname, p.data)  # 共用網格，不改原型
    return link(o)

def local_bbox(me):
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    return co.min(0), co.max(0)

def place_on_floor(o, x, y, yaw, scale=1.0, z0=None):
    mn, mx = local_bbox(o.data)
    c = (mn + mx) / 2
    o.scale = (scale, scale, scale)
    o.rotation_euler = (0, 0, yaw)
    off = Matrix.Rotation(yaw, 3, 'Z') @ Vector((c[0] * scale, c[1] * scale, 0))
    o.location = (x - off.x, y - off.y, (FLOOR_Z if z0 is None else z0) - mn[2] * scale)
    return (mx[0] - mn[0]) * scale / 2, (mx[1] - mn[1]) * scale / 2

def in_rect(px, py, r, m=0.0):
    return r[0] + m <= px <= r[1] - m and r[2] + m <= py <= r[3] - m

def footprint_ok(x, y, hx, hy, yaw, placed, margin=1.5):
    c, s = math.cos(yaw), math.sin(yaw)
    pts = [(x + c * ax - s * ay, y + s * ax + c * ay) for ax in (-hx, 0, hx) for ay in (-hy, 0, hy)]
    for px, py in pts:
        if not any(in_rect(px, py, r, margin) for r in CORRIDORS):
            return False
        if any(in_rect(px, py, (p[0] - 1, p[1] + 1, p[2] - 1, p[3] + 1)) for p in PILLARS):
            return False
    rad = math.hypot(hx, hy) * 0.8
    return all(math.hypot(x - px, y - py) > rad + pr for px, py, pr in placed)

def sample_floor_point(rng, cam_xy, near, maxd=170):
    for _ in range(200):
        r = CORRIDORS[rng.randrange(len(CORRIDORS))]
        x, y = rng.uniform(r[0], r[1]), rng.uniform(r[2], r[3])
        if math.hypot(x - near[0], y - near[1]) < maxd:
            return x, y
    return near

def project_point(cam, p):
    pc = cam.matrix_world.inverted() @ Vector(p)
    d = pc.normalized()
    theta = math.acos(max(-1, min(1, -d.z)))
    if theta > cam.data.fisheye_fov / 2:
        return None
    phi = math.atan2(d.y, d.x)
    rr = 2 * cam.data.fisheye_lens * math.sin(theta / 2)
    sw = cam.data.sensor_width
    return (rr * math.cos(phi) / sw + 0.5) * W, (1 - (rr * math.sin(phi) / (sw * H / W) + 0.5)) * H

def visible_point(cam, x, y, z, margin=8):
    # 點要在畫面內，而且從鏡頭打過去不會先撞到牆
    pp = project_point(cam, (x, y, z))
    if pp is None or not (margin <= pp[0] <= W - margin and margin <= pp[1] <= H - margin):
        return False
    o = cam.matrix_world.translation
    v = Vector((x, y, z)) - o
    hit, loc, *_ = SC.ray_cast(VL.depsgraph, o, v.normalized(), distance=v.length)
    return (not hit) or (loc - o).length >= v.length - 3

def sample_visible(rng, cam, near, z_off, p_any=0.15):
    # 大多數取在鏡頭看得到的地方；少數（p_any）不檢查，保留被擋住、只露一角的情況
    check = rng.random() >= p_any
    for _ in range(80):
        x, y = sample_floor_point(rng, near, near)
        if not check or visible_point(cam, x, y, FLOOR_Z + z_off):
            return x, y
    return x, y

def make_person(name, rng):
    h = rng.uniform(36, 44)
    bm = bmesh.new()
    parts = []  # (verts, material index)
    def cyl(r1, r2, depth, mat, loc, rot=(0, 0, 0)):
        M = Matrix.Translation(loc) @ Euler(rot).to_matrix().to_4x4()
        res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=12, radius1=r1, radius2=r2,
                                    depth=depth, matrix=M)
        parts.append((res['verts'], mat))
    def sph(r, mat, loc, sz=1.0):
        M = Matrix.Translation(loc) @ Matrix.Diagonal((1, 1, sz, 1))
        res = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=r, matrix=M)
        parts.append((res['verts'], mat))
    z = 0.0
    if rng.random() < 0.5:  # 磁鐵底座
        bh = 0.05 * h
        cyl(0.25 * h, 0.25 * h, bh, 3, (0, 0, bh / 2))
        z = bh
    hb = h - z
    if rng.random() < 0.3:  # 木頭人偶型：圓柱身體＋球頭
        cyl(0.17 * hb, 0.13 * hb, 0.72 * hb, 1, (0, 0, z + 0.36 * hb))
        sph(0.14 * hb, 0, (0, 0, z + 0.86 * hb))
    else:
        leg = 0.45 * hb
        spread = rng.uniform(0.02, 0.09) * hb
        for sx in (-1, 1):
            cyl(0.065 * hb, 0.055 * hb, leg, 2, (sx * spread, 0, z + leg / 2), (0, sx * 0.05, 0))
        tz = z + leg
        cyl(0.15 * hb, 0.13 * hb, 0.32 * hb, 1, (0, 0, tz + 0.16 * hb))
        for sx in (-1, 1):
            a = rng.uniform(0.05, 0.6)
            cyl(0.05 * hb, 0.045 * hb, 0.34 * hb, 1, (sx * (0.17 * hb + 0.1 * hb * math.sin(a)), 0, tz + 0.15 * hb),
                (0, -sx * a, 0))
        sph(0.11 * hb, 0, (0, 0, tz + 0.32 * hb + 0.12 * hb), 1.1)
    bm.faces.ensure_lookup_table()
    for verts, mi in parts:
        vs = set(verts)
        for f in bm.faces:
            if f.verts[0] in vs:
                f.material_index = mi
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    skin = hsv_lin(rng.uniform(0.03, 0.11), rng.uniform(0.2, 0.6), rng.uniform(0.35, 0.95))
    if rng.random() < 0.3:
        skin = hsv_lin(rng.random(), rng.uniform(0, 0.8), rng.uniform(0.3, 0.95))  # 塗裝人偶
    me.materials.append(new_mat(name + '_skin', skin, 0.5))
    me.materials.append(new_mat(name + '_top', hsv_lin(rng.random(), rng.uniform(0, 1), rng.uniform(0.1, 0.95)), 0.6))
    me.materials.append(new_mat(name + '_bottom', hsv_lin(rng.random(), rng.uniform(0, 1), rng.uniform(0.1, 0.9)), 0.6))
    me.materials.append(new_mat(name + '_base', hsv_lin(0, 0, rng.uniform(0.05, 0.7)), 0.35, rng.choice([0.0, 1.0])))
    return link(bpy.data.objects.new(name, me)), h

def make_smoke(name, rng, x, y):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=0.5)
    bm.to_mesh(me); bm.free()
    o = link(bpy.data.objects.new(name, me))
    if rng.random() < 0.6:  # 從地板孔冒上來的煙柱
        d = rng.uniform(10, 35); hgt = rng.uniform(30, 95)
        o.scale = (d * rng.uniform(0.8, 1.3), d, hgt)
        o.location = (x, y, FLOOR_Z + hgt * 0.45)
    else:  # 天花板下的煙層
        d = rng.uniform(40, 130); hgt = rng.uniform(10, 35)
        o.scale = (d, d * rng.uniform(0.5, 1.0), hgt)
        o.location = (x, y, rng.uniform(65, 102 - hgt / 2))  # 煙層頂端不超過蓋子下緣
    o.rotation_euler = (0, 0, rng.uniform(0, math.pi))
    m = bpy.data.materials.new(name + '_vol')
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sub = nt.nodes.new('ShaderNodeVectorMath'); sub.operation = 'SUBTRACT'
    sub.inputs[1].default_value = (0.5, 0.5, 0.5)
    ln = nt.nodes.new('ShaderNodeVectorMath'); ln.operation = 'LENGTH'
    fall = nt.nodes.new('ShaderNodeMapRange')
    fall.inputs['From Min'].default_value = rng.uniform(0.15, 0.3)
    fall.inputs['From Max'].default_value = 0.5
    fall.inputs['To Min'].default_value = 1.0
    fall.inputs['To Max'].default_value = 0.0
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = rng.uniform(2.5, 8)
    nz.inputs['Detail'].default_value = rng.uniform(1, 6)
    nr = nt.nodes.new('ShaderNodeMapRange')
    nr.inputs['From Min'].default_value = rng.uniform(0.3, 0.5)
    nr.inputs['From Max'].default_value = 0.75
    mul = nt.nodes.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'
    mul2 = nt.nodes.new('ShaderNodeMath'); mul2.operation = 'MULTIPLY'
    mul2.inputs[1].default_value = math.exp(rng.uniform(math.log(0.01), math.log(0.09)))
    vol = nt.nodes.new('ShaderNodeVolumePrincipled')
    g = rng.uniform(0.45, 0.95)
    vol.inputs['Color'].default_value = (g, g, g * rng.uniform(0.92, 1.0), 1)
    vol.inputs['Anisotropy'].default_value = rng.uniform(0, 0.4)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    L = nt.links.new
    L(tc.outputs['Generated'], sub.inputs[0]); L(sub.outputs['Vector'], ln.inputs[0])
    L(ln.outputs['Value'], fall.inputs['Value'])
    L(tc.outputs['Object'], nz.inputs['Vector']); L(sock(nz, 'Fac', True), nr.inputs['Value'])
    L(fall.outputs['Result'], mul.inputs[0]); L(nr.outputs['Result'], mul.inputs[1])
    L(mul.outputs['Value'], mul2.inputs[0]); L(mul2.outputs['Value'], vol.inputs['Density'])
    L(vol.outputs['Volume'], out.inputs['Volume'])
    me.materials.append(m)
    return o

def make_distractor(name, rng):
    bm = bmesh.new()
    kind = rng.choice(['cyl', 'cyl', 'sphere', 'cone', 'sheet', 'cable'])
    if kind == 'cyl':
        r = rng.uniform(3, 10); d = rng.uniform(3, 25)
        bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=r, radius2=r, depth=d,
                              matrix=Matrix.Translation((0, 0, d / 2)))
    elif kind == 'sphere':
        r = rng.uniform(3, 8)
        bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=r, matrix=Matrix.Translation((0, 0, r)))
    elif kind == 'cone':
        r = rng.uniform(4, 10); d = rng.uniform(8, 25)
        bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=r, radius2=0.5, depth=d,
                              matrix=Matrix.Translation((0, 0, d / 2)))
    elif kind == 'sheet':  # 紙片、膠帶
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 0, 0.5)) @
                              Matrix.Diagonal((rng.uniform(8, 40), rng.uniform(4, 30), rng.uniform(0.3, 1.2), 1)))
    else:  # 電線
        r = rng.uniform(0.6, 1.5); d = rng.uniform(30, 100)
        bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=r, radius2=r, depth=d,
                              matrix=Matrix.Translation((0, 0, r)) @ Euler((0, math.pi / 2, 0)).to_matrix().to_4x4())
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    col = hsv_lin(rng.random(), rng.uniform(0, 1), rng.uniform(0.1, 0.95))
    me.materials.append(new_mat(name + '_m', col, rng.uniform(0.2, 0.9), rng.choice([0, 0, 0, 1])))
    return link(bpy.data.objects.new(name, me))

# ---------------------------------------------------------------- 每張圖
def cleanup():
    objs = [o for o in bpy.data.objects if o.name.startswith('DR_')]
    data = [o.data for o in objs if o.data is not None]
    bpy.data.batch_remove(objs)
    bpy.data.batch_remove([d for d in data if d.users == 0])
    bpy.data.batch_remove([m for m in bpy.data.materials if m.name.startswith('DR_') and m.users == 0])
    for im in list(bpy.data.images):
        if im.name.startswith('DRIMG_'):
            bpy.data.images.remove(im)

def build_frame(idx, rng):
    cleanup()
    meta = {'index': idx}
    cam_name = rng.choice(CAMS)
    base = CAM_MW[cam_name]
    cd = bpy.data.objects[cam_name].data.copy(); cd.name = 'DR_CamData'
    cd.sensor_fit = 'HORIZONTAL'
    cd.fisheye_lens *= rng.uniform(0.98, 1.02)
    cam = link(bpy.data.objects.new('DR_Cam', cd))
    # 鏡頭小幅偏移；偏移後鏡頭不能卡進鏡頭座／蓋子（射線淨空要有原位置的 80%）
    for _try in range(30):
        jt = Vector((rng.uniform(-3, 3), rng.uniform(-3, 3), rng.uniform(-3, 3)))
        jr = Euler([math.radians(rng.uniform(-2.5, 2.5)) for _ in range(3)])
        mw = base @ Matrix.Translation(jt) @ jr.to_matrix().to_4x4()
        if cam_clearance(mw) >= 0.8 * CAM_CLEAR[cam_name]:
            break
    else:
        jt, jr, mw = Vector(), Euler(), base.copy()
    cam.matrix_world = mw
    SC.camera = cam
    cpos = cam.matrix_world.translation
    fwd = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
    t = (cpos.z - FLOOR_Z) / max(1e-3, -fwd.z)
    look = (cpos.x + fwd.x * t, cpos.y + fwd.y * t)
    meta['camera'] = dict(name=cam_name, jitter_mm=list(jt), jitter_deg=[math.degrees(a) for a in jr],
                          fisheye_lens=cd.fisheye_lens, height_above_floor=cpos.z - FLOOR_Z)

    # 蓋子
    lid_open = rng.random() < ARGS.lid_open_prob
    for n in LID_SET:
        SC.objects[n].hide_render = lid_open
    meta['lid_open'] = lid_open

    # 材質
    for n, h in DR_MATS.items():
        if n in ('FM_Tray', 'FM_Lid', 'FM_Pod', 'FM_Spacer', 'FM_Stair'):
            kind = rng.random()
            if kind < 0.45:
                c = hsv_lin(rng.uniform(0, 1), rng.uniform(0, 0.12), rng.uniform(0.75, 0.97))  # 白／米色 PLA
            elif kind < 0.8:
                c = hsv_lin(rng.uniform(0, 1), rng.uniform(0, 0.1), rng.uniform(0.3, 0.75))   # 灰
            else:
                c = hsv_lin(rng.random(), rng.uniform(0.1, 0.6), rng.uniform(0.15, 0.9))       # 其他顏色
            set_material(h, c, rng)
        elif n in ('FM_Plug', 'FM_Plug_door'):
            c = jitter_color(h['base'], rng) if rng.random() < 0.5 else \
                hsv_lin(rng.random(), rng.uniform(0, 0.9), rng.uniform(0.2, 0.95))
            set_material(h, c, rng)
        else:
            set_material(h, jitter_color(h['base'], rng), rng)

    # 光照（偏亮的教室光；之後還會自動曝光到隨機的亮度目標）
    world = SC.world
    bg = next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND')
    wk = kelvin_rgb(rng.uniform(4000, 7500))
    bg.inputs['Color'].default_value = (*wk, 1)
    bg.inputs['Strength'].default_value = rng.uniform(0.3, 1.5)
    lights = []
    def add_light(kind, loc, power, kelvin, size, rot=(0, 0, 0)):
        ld = bpy.data.lights.new(f'DR_L{len(lights)}', kind)
        ld.energy = power
        ld.color = kelvin_rgb(kelvin)
        if kind == 'AREA':
            ld.shape = 'DISK'; ld.size = size
        elif kind in ('POINT', 'SPOT'):
            ld.shadow_soft_size = size
        lo = link(bpy.data.objects.new(f'DR_L{len(lights)}', ld))
        lo.location = loc; lo.rotation_euler = rot
        lo.visible_camera = False
        lights.append(dict(kind=kind, loc=list(loc), power=power, kelvin=kelvin, size=size))
    if lid_open:  # 頭頂日光燈
        add_light('AREA', (rng.uniform(-400, 400), rng.uniform(-400, 400), rng.uniform(1200, 2500)),
                  10 ** rng.uniform(8.2, 9.0), rng.uniform(4000, 6500), rng.uniform(400, 1200))
        if rng.random() < 0.4:
            sd = bpy.data.lights.new('DR_Sun', 'SUN'); sd.energy = rng.uniform(1, 5); sd.angle = rng.uniform(0.01, 0.2)
            so = link(bpy.data.objects.new('DR_Sun', sd))
            so.rotation_euler = (rng.uniform(0.3, 1.1), 0, rng.uniform(0, 2 * math.pi))
            lights.append(dict(kind='SUN', strength=sd.energy))
    for k in range(rng.randint(1, 3)):  # 模型內部的光（漏光、補光燈）；第一盞靠近畫面中心
        x, y = sample_floor_point(rng, look, look, 60 if k == 0 else 160)
        add_light(rng.choice(['AREA', 'POINT']), (x, y, rng.uniform(60, 100)),
                  10 ** rng.uniform(5.5, 6.8), rng.uniform(3200, 6800), rng.uniform(5, 40))
    meta['lights'] = lights
    meta['world_strength'] = bg.inputs['Strength'].default_value

    # 物件
    insts = []  # dict(obj, cls, kind)
    placed = []
    empty = ARGS.mode == 'empty' or rng.random() < ARGS.empty_prob
    meta['empty_scene'] = empty
    if not empty:
        slots = sorted(GATE_SLOTS, key=lambda s: math.hypot(s[0][0] - look[0], s[0][1] - look[1]))[:6]
        # 鏡頭正下方 50 mm 內的槽位：塞子頂面會蓋滿半個畫面、只剩一片平面，多數情況跳過
        slots = [s for s in slots if math.hypot(s[0][0] - cpos.x, s[0][1] - cpos.y) > 50 or rng.random() < 0.25]
        for (gx, gy), rot90, proto in rng.sample(slots, rng.choice([0, 0, 1, 1, 2])):
            o = mesh_from_proto(proto, f'DR_gate{len(insts)}')
            hx, hy = place_on_floor(o, gx, gy, math.pi / 2 if rot90 else 0.0, z0=0.0)
            placed.append((gx, gy, max(hx, hy) * 0.8))
            insts.append(dict(obj=o, cls=4))
        VL.update()  # 讓閘門參與後面的可見性射線
        for _ in range(rng.choice([0, 1, 1, 2, 2, 3, 4])):
            cls = rng.randrange(4)
            proto = rng.choice(OBSTACLE_PROTOS[cls])
            o = mesh_from_proto(proto, f'DR_obs{len(insts)}')
            for _try in range(60):
                x, y = sample_visible(rng, cam, look, 8)
                yaw = rng.uniform(0, 2 * math.pi)
                s = rng.uniform(0.85, 1.15)
                mn, mx = local_bbox(o.data)
                hx, hy = (mx[0] - mn[0]) * s / 2, (mx[1] - mn[1]) * s / 2
                if footprint_ok(x, y, hx, hy, yaw, placed):
                    place_on_floor(o, x, y, yaw, s)
                    placed.append((x, y, math.hypot(hx, hy) * 0.8))
                    insts.append(dict(obj=o, cls=cls))
                    break
            else:
                bpy.data.objects.remove(o)
        for _ in range(rng.choice([0, 1, 1, 2, 3, 4])):
            o, hgt = make_person(f'DR_person{len(insts)}', rng)
            for _try in range(60):
                x, y = sample_visible(rng, cam, look, 20)
                yaw = rng.uniform(0, 2 * math.pi)
                if footprint_ok(x, y, 6, 4, yaw, placed, 1.0):
                    place_on_floor(o, x, y, yaw)
                    placed.append((x, y, 6))
                    insts.append(dict(obj=o, cls=6))
                    break
            else:
                bpy.data.objects.remove(o)
        if rng.random() < 0.45:
            for _ in range(rng.choice([1, 1, 2])):
                x, y = sample_visible(rng, cam, look, 30)
                insts.append(dict(obj=make_smoke(f'DR_smoke{len(insts)}', rng, x, y), cls=5))
    for i in range(rng.choice([0, 1, 2, 3, 4])):  # 干擾物：不標註
        o = make_distractor(f'DR_distr{i}', rng)
        for _try in range(30):
            x, y = sample_visible(rng, cam, look, 3)
            yaw = rng.uniform(0, 2 * math.pi)
            mn, mx = local_bbox(o.data)
            if footprint_ok(x, y, (mx[0] - mn[0]) / 2, (mx[1] - mn[1]) / 2, yaw, placed, 0.5):
                place_on_floor(o, x, y, yaw)
                placed.append((x, y, 4))
                break
        else:
            bpy.data.objects.remove(o)
    for k, it in enumerate(insts, 1):
        it['obj'].pass_index = k
        it['id'] = k
    return insts, meta

# ---------------------------------------------------------------- 渲染
def set_exr(rgb_only=True):
    s = SC.render.image_settings
    if hasattr(s, 'media_type'):
        s.media_type = 'IMAGE'
    s.file_format = 'OPEN_EXR'
    s.color_mode = 'RGB'
    s.color_depth = '32'
    s.exr_codec = 'ZIP'

def load_exr(path):
    im = bpy.data.images.load(path, check_existing=False)
    im.name = 'DRIMG_' + os.path.basename(path)
    w, h = im.size
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    return a.reshape(h, w, 4)[::-1, :, :3].copy()

def render_to(path):
    SC.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=SC.name)
    return load_exr(path)

def render_beauty(tmp, seed, name='beauty.exr'):
    cy = SC.cycles
    cy.samples = ARGS.samples
    cy.use_adaptive_sampling = True
    cy.use_denoising = True
    cy.denoiser = 'OPTIX' if DEVICE == 'OPTIX' else 'OPENIMAGEDENOISE'
    cy.pixel_filter_type = 'BLACKMAN_HARRIS'
    cy.filter_width = 1.5
    cy.seed = seed
    SC.render.film_transparent = False
    VL.material_override = None
    return render_to(os.path.join(tmp, name))

def render_masks(tmp, insts):
    cy = SC.cycles
    cy.samples = 1
    cy.use_adaptive_sampling = False
    cy.use_denoising = False
    cy.pixel_filter_type = 'BOX'
    cy.filter_width = 0.01
    cy.seed = 0
    SC.render.film_transparent = True
    VL.material_override = MASK_MAT
    win = SC.objects['Window_Pane']; win_h = win.hide_render
    win.hide_render = True
    smokes = [it['obj'] for it in insts if it['cls'] == 5]
    for o in smokes:
        o.hide_render = True
    a = render_to(os.path.join(tmp, 'maskA.exr'))[:, :, 0]
    for o in smokes:
        o.hide_render = False
        o.scale = tuple(v * 0.85 for v in o.scale)
    b = render_to(os.path.join(tmp, 'maskB.exr'))[:, :, 0] if smokes else None
    for o in smokes:
        o.scale = tuple(v / 0.85 for v in o.scale)
    VL.update()  # 渲染會更新 matrix_world；縮放還原後要重新計算，投影驗證才用得到正確大小
    win.hide_render = win_h
    VL.material_override = None
    SC.render.film_transparent = False
    return np.rint(a).astype(np.int32), (np.rint(b).astype(np.int32) if b is not None else None)

# 魚眼（等立體角）投影：相機座標 → 像素，用來交叉驗證遮罩框
def project_bbox(obj, cam, shrink=1.0):
    dg = VL.depsgraph
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get('co', co)
    ed = np.empty(len(me.edges) * 2, np.int32)
    me.edges.foreach_get('vertices', ed)
    ev.to_mesh_clear()
    co = co.reshape(-1, 3) * shrink
    # 魚眼會把直線投影成曲線 → 沿每條邊取 9 點，投影框才是真正的上界
    ed = ed.reshape(-1, 2)
    t = np.linspace(0, 1, 9, dtype=np.float32)[None, :, None]
    co = np.concatenate([co, (co[ed[:, 0]][:, None] * (1 - t) + co[ed[:, 1]][:, None] * t).reshape(-1, 3)])
    M = np.array(cam.matrix_world.inverted() @ obj.matrix_world)
    pc = co @ M[:3, :3].T + M[:3, 3]
    d = pc / np.linalg.norm(pc, axis=1, keepdims=True)
    theta = np.arccos(np.clip(-d[:, 2], -1, 1))
    if (theta > cam.data.fisheye_fov / 2).any():
        return None  # 有頂點在鏡頭視野後方，投影框無法當上界
    phi = np.arctan2(d[:, 1], d[:, 0])
    rr = 2 * cam.data.fisheye_lens * np.sin(theta / 2)
    sw = cam.data.sensor_width
    sh = sw * H / W
    u = rr * np.cos(phi) / sw + 0.5
    v = rr * np.sin(phi) / sh + 0.5
    px, py = u * W, (1 - v) * H
    x0, x1 = max(0, px.min()), min(W, px.max())
    y0, y1 = max(0, py.min()), min(H, py.max())
    if x1 <= x0 or y1 <= y0:
        return [0, 0, 0, 0]
    return [float(x0), float(y0), float(x1), float(y1)]

# ---------------------------------------------------------------- 後處理（numpy）
def srgb_oetf(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)

def shift(img, dy, dx):
    p = max(abs(dy), abs(dx))
    if p == 0:
        return img
    pad = np.pad(img, ((p, p), (p, p), (0, 0)), mode='edge')
    return pad[p + dy:p + dy + img.shape[0], p + dx:p + dx + img.shape[1]]

def gauss_blur(img, sigma):
    r = int(math.ceil(sigma * 3))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    out = sum(k[i + r] * shift(img, 0, i) for i in range(-r, r + 1))
    return sum(k[i + r] * shift(out, i, 0) for i in range(-r, r + 1))

def motion_blur(img, length, ang):
    n = max(2, int(round(length)))
    acc = np.zeros_like(img)
    for t in np.linspace(-length / 2, length / 2, n):
        acc += shift(img, int(round(t * math.sin(ang))), int(round(t * math.cos(ang))))
    return acc / n

def postprocess(lin, rng, nrng):
    p = {}
    wb = np.array([rng.uniform(0.85, 1.15), 1.0, rng.uniform(0.85, 1.15)], np.float32)
    lin = np.maximum(lin, 0) * wb
    target = rng.uniform(0.38, 0.62)  # 偏亮：sRGB 平均亮度目標
    small = lin[::4, ::4]
    lo, hi = 1e-3, 1e4
    lum = lambda s: float(srgb_oetf(small * s).mean())
    for _ in range(40):
        mid = math.sqrt(lo * hi)
        lo, hi = (mid, hi) if lum(mid) < target else (lo, mid)
    s = math.sqrt(lo * hi)
    img = srgb_oetf(lin * s)
    gamma = rng.uniform(0.85, 1.15); contrast = rng.uniform(0.85, 1.25); sat = rng.uniform(0.7, 1.25)
    img = np.power(np.clip(img, 0, 1), gamma)
    img = np.clip((img - 0.5) * contrast + 0.5, 0, 1)
    gray = img.mean(2, keepdims=True)
    img = np.clip(gray + (img - gray) * sat, 0, 1)
    vig = rng.uniform(0, 0.35)
    yy, xx = np.mgrid[0:H, 0:W]
    rad = ((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (W / 2)) ** 2
    img = img * (1 - vig * rad)[:, :, None]
    p.update(wb=wb.tolist(), target_mean=target, exposure_gain=s, gamma=gamma, contrast=contrast,
             saturation=sat, vignette=vig)
    if rng.random() < 0.6:
        sg = rng.uniform(0.3, 1.3); img = gauss_blur(img, sg); p['gauss_blur'] = sg
    if rng.random() < 0.15:
        L, a = rng.uniform(2, 7), rng.uniform(0, math.pi); img = motion_blur(img, L, a); p['motion_blur'] = [L, a]
    rn, sn = rng.uniform(0.003, 0.025), rng.uniform(0, 0.04)
    img = img + nrng.normal(0, 1, img.shape).astype(np.float32) * (rn + sn * np.sqrt(np.clip(img, 0, 1)))
    p.update(read_noise=rn, shot_noise=sn)
    img = np.clip(img, 0, 1)
    p['jpeg_quality'] = rng.randint(55, 95)
    return img, p

def save_jpg(img, path, quality):
    h, w = img.shape[:2]
    im = bpy.data.images.new('DRIMG_out', w, h, alpha=False)
    rgba = np.ones((h, w, 4), np.float32)
    rgba[:, :, :3] = np.round(img * 255) / 255
    im.pixels.foreach_set(rgba[::-1].ravel())
    im.filepath_raw = path
    im.file_format = 'JPEG'
    SC.render.image_settings.quality = quality
    im.save(filepath=path, quality=quality)
    bpy.data.images.remove(im)

# ---------------------------------------------------------------- 主程式
def main():
    out = os.path.abspath(ARGS.out)
    for d in ('images', 'labels', 'meta', 'tmp'):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    tmp = os.path.join(out, 'tmp')
    t_all = time.time()
    for idx in range(ARGS.start, ARGS.start + ARGS.count):
        stem = f'{ARGS.prefix}_{ARGS.seed:03d}_{idx:05d}'
        if ARGS.skip_existing and os.path.exists(os.path.join(out, 'labels', stem + '.txt')):
            continue
        t0 = time.time()
        rng = random.Random(f'{ARGS.seed}-{idx}')  # 字串種子：相鄰編號不會相關
        nrng = np.random.default_rng([ARGS.seed, idx])
        insts, meta = build_frame(idx, rng)
        VL.update()
        set_exr()
        seed = rng.randrange(1 << 30)
        beauty = render_beauty(tmp, seed)
        smokes = [it['obj'] for it in insts if it['cls'] == 5]
        smoke_vis = None
        if smokes:
            # 同一個種子再渲一張「沒有煙」的，差異夠大的像素才算看得到煙
            for o in smokes:
                o.hide_render = True
            nos = render_beauty(tmp, seed, 'nosmoke.exr')
            for o in smokes:
                o.hide_render = False
            lb, ln = beauty.mean(2), nos.mean(2)
            rel = np.abs(lb - ln) / (np.maximum(lb, ln) + 0.02 * float(ln.mean()) + 1e-6)
            smoke_vis = rel > SMOKE_REL_DIFF
        mA, mB = render_masks(tmp, insts)
        cam = SC.camera
        lines, objs = [], []
        for it in insts:
            if it['cls'] == 5:
                full = mB == it['id']
                m = full & smoke_vis
                ys, xs = np.nonzero(m)
            else:
                ys, xs = np.nonzero(mA == it['id'])
            rec = dict(id=it['id'], cls=it['cls'], name=CLASSES[it['cls']], pixels=int(len(xs)),
                       loc=[round(v, 1) for v in it['obj'].matrix_world.translation],
                       dims=[round(v, 1) for v in it['obj'].dimensions])
            proj = project_bbox(it['obj'], cam, 0.85 if it['cls'] == 5 else 1.0)
            rec['proj_bbox'] = proj
            if it['cls'] == 5:
                rec['smoke_mask_pixels'] = int(full.sum())  # 煙的形狀範圍；pixels 是其中看得到的部分
            if len(xs):
                x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
                rec['mask_bbox'] = [x0, y0, x1, y1]
                if proj is not None:
                    tol = 3
                    rec['inside_proj'] = bool(x0 >= proj[0] - tol and y0 >= proj[1] - tol and
                                              x1 <= proj[2] + tol and y1 <= proj[3] + tol)
                ok = len(xs) >= ARGS.min_pixels and (x1 - x0) >= 4 and (y1 - y0) >= 4
                rec['labeled'] = ok
                if ok:
                    lines.append(f"{it['cls']} {(x0 + x1) / 2 / W:.6f} {(y0 + y1) / 2 / H:.6f} "
                                 f"{(x1 - x0) / W:.6f} {(y1 - y0) / H:.6f}")
            else:
                rec['labeled'] = False
            objs.append(rec)
        ids_seen = set(np.unique(mA).tolist()) - {0}
        meta['unknown_mask_ids'] = sorted(i for i in ids_seen if i > len(insts))
        img, pp = postprocess(beauty, rng, nrng)
        save_jpg(img, os.path.join(out, 'images', stem + '.jpg'), pp['jpeg_quality'])
        with open(os.path.join(out, 'labels', stem + '.txt'), 'w', encoding='ascii', newline='\n') as f:
            f.write('\n'.join(lines) + ('\n' if lines else ''))
        meta.update(objects=objs, post=pp, n_labels=len(lines), render_sec=round(time.time() - t0, 2),
                    seed=ARGS.seed, mode=ARGS.mode)
        with open(os.path.join(out, 'meta', stem + '.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=1, default=float)
        print(f'[dr] {stem} labels={len(lines)} objs={len(insts)} cam={meta["camera"]["name"]} '
              f'lid_open={meta["lid_open"]} {time.time() - t0:.1f}s', flush=True)
    cleanup()
    print(f'[dr] done {ARGS.count} frames in {time.time() - t_all:.0f}s')

main()
