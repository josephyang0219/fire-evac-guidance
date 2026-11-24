# -*- coding: utf-8 -*-
"""用 Blender 流體模擬（Mantaflow）預先做「會擴散的煙」，給 dr_render.py 隨機取用（2026-11-24）。

第一次訓練（10/22，舊 6 類模型）就是用流體模擬的煙；之後的 dr_render.py 改成靜止的一團體積，
煙又細又淡，框裡大多看不到煙（小規模補訓 v1～v4 煙學不起來的主因）。

用法（在 fire_model.blend 的複本上執行）：
    blender -b fire_model_dr.blend -P bake_smoke.py -- --out <lib 資料夾> --n 3 --seed 1 [--frames 120] [--res 96] [--preview]

每一組模擬：
  - 煙源：地板上隨機位置的小球（線香／悶燒），持續冒煙；煙量、溫度（上升速度）、渦度隨機
  - 地板（Floor_Tray_G）、蓋子（Floor_Lid）當碰撞物，煙會被牆擋住、碰到天花板後往旁邊散
  - 結果存在 <out>/sim_XXX/（Mantaflow 快取，OpenVDB）＋ sim_XXX.json（參數）
--preview：每組另外用最近的鏡頭渲染第 20、45、75、110 幀（576×320），存成 sim_XXX_fNNN.png
"""
import bpy, bmesh, sys, os, json, math, random, argparse, time
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument('--out', required=True)
ap.add_argument('--n', type=int, default=3)
ap.add_argument('--start', type=int, default=0)
ap.add_argument('--seed', type=int, default=1)
ap.add_argument('--frames', type=int, default=120)
ap.add_argument('--res', type=int, default=96)
ap.add_argument('--preview', action='store_true')
A = ap.parse_args(argv)
if os.path.basename(bpy.data.filepath).lower() == 'fire_model.blend':
    raise SystemExit('拒絕執行：請用複本')
os.makedirs(A.out, exist_ok=True)

SC = bpy.data.scenes['FireModel']
COL = SC.collection
FLOOR_Z = 8.0
LID_Z = 105.0
HALF = 121.0
RING_C, RING_HW, CROSS_HW = 99.0, 18.0, 21.0

tray = bpy.data.objects['Floor_Tray_G']
if tray.name not in COL.objects:
    COL.objects.link(tray)
for n in ('Floor_Tray',):
    o = bpy.data.objects.get(n)
    if o and o.name in COL.objects:
        COL.objects.unlink(o)


def add_mod(o, kind):
    m = o.modifiers.new('Fluid', 'FLUID')
    m.fluid_type = kind
    return m


def rand_source(rng):
    """在走廊地板上隨機取一點：環廊（中心 ±99、半寬 18）或十字走廊（半寬 21）。"""
    while True:
        if rng.random() < 0.55:  # 環廊
            side = rng.choice('NESW'); t = rng.uniform(-RING_C, RING_C); d = rng.uniform(-RING_HW + 5, RING_HW - 5)
            x, y = {'N': (t, RING_C + d), 'S': (t, -RING_C + d), 'E': (RING_C + d, t), 'W': (-RING_C + d, t)}[side]
        else:  # 十字走廊
            t = rng.uniform(25, RING_C - RING_HW); d = rng.uniform(-CROSS_HW + 5, CROSS_HW - 5)
            x, y = rng.choice([(t, d), (-t, d), (d, t), (d, -t)])
        if abs(x) < HALF - 8 and abs(y) < HALF - 8:
            return x, y


# ---- 碰撞物
for o in (tray, bpy.data.objects.get('Floor_Lid')):
    if o and not any(m.type == 'FLUID' for m in o.modifiers):
        m = add_mod(o, 'EFFECTOR')
        m.effector_settings.effector_type = 'COLLISION'
        m.effector_settings.use_effector = True
        m.effector_settings.surface_distance = 0.5

# ---- 模擬範圍（1F 室內）
bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
me = bpy.data.meshes.new('SIM_DomainMesh'); bm.to_mesh(me); bm.free()
dom = bpy.data.objects.new('SIM_Domain', me); COL.objects.link(dom)
dom.scale = (2 * HALF, 2 * HALF, LID_Z - FLOOR_Z)
dom.location = (0, 0, (FLOOR_Z + LID_Z) / 2)
dm = add_mod(dom, 'DOMAIN')
ds = dm.domain_settings
ds.domain_type = 'GAS'
ds.resolution_max = A.res
ds.cache_type = 'ALL'
ds.cache_data_format = 'OPENVDB'
ds.use_adaptive_domain = False
ds.cache_frame_start = 1
ds.cache_frame_end = A.frames
# 煙用的體積材質：density 屬性 × DEN，灰白色；dr_render 取用時會再隨機顏色、濃度
mat = bpy.data.materials.new('SIM_SmokeMat'); mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
at = nt.nodes.new('ShaderNodeAttribute'); at.attribute_name = 'density'
mu = nt.nodes.new('ShaderNodeMath'); mu.operation = 'MULTIPLY'; mu.name = 'DEN'; mu.inputs[1].default_value = 4.0
vol = nt.nodes.new('ShaderNodeVolumePrincipled'); vol.name = 'VOL'
vol.inputs['Color'].default_value = (0.75, 0.75, 0.75, 1)
outn = nt.nodes.new('ShaderNodeOutputMaterial')
nt.links.new(at.outputs['Fac'], mu.inputs[0]); nt.links.new(mu.outputs['Value'], vol.inputs['Density'])
nt.links.new(vol.outputs['Volume'], outn.inputs['Volume'])
me.materials.append(mat)

# ---- 煙源
bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=1.0)
sme = bpy.data.meshes.new('SIM_SrcMesh'); bm.to_mesh(sme); bm.free()
src = bpy.data.objects.new('SIM_Source', sme); COL.objects.link(src)
fm = add_mod(src, 'FLOW')
fs = fm.flow_settings
fs.flow_type = 'SMOKE'
fs.flow_behavior = 'INFLOW'
fs.flow_source = 'MESH'
src.hide_render = True

SC.frame_start, SC.frame_end = 1, A.frames
cams = {o.name: o for o in SC.objects if o.type == 'CAMERA'}


def nearest_cam(x, y):
    return min(cams.values(), key=lambda c: (c.location.x - x) ** 2 + (c.location.y - y) ** 2)


for i in range(A.start, A.start + A.n):
    rng = random.Random(A.seed * 1000 + i)
    x, y = rand_source(rng)
    P = dict(idx=i, x=round(x, 1), y=round(y, 1),
             src_r=rng.uniform(2.0, 5.0),                       # 煙源大小（線香 2 mm ～ 悶燒 5 mm）
             temp=rng.uniform(0.8, 2.5),                        # 溫度差：越大上升越快
             density=rng.uniform(0.6, 1.0),
             vorticity=rng.uniform(0.05, 0.35),
             alpha=rng.uniform(0.6, 1.2), beta=rng.uniform(0.8, 1.6),
             time_scale=rng.uniform(0.6, 1.0))
    src.location = (x, y, FLOOR_Z + P['src_r'] + 1)
    src.scale = (P['src_r'],) * 3
    fs.temperature = P['temp']; fs.density = P['density']
    ds.vorticity = P['vorticity']; ds.alpha = P['alpha']; ds.beta = P['beta']; ds.time_scale = P['time_scale']
    cdir = os.path.join(A.out, f'sim_{i:03d}')
    ds.cache_directory = cdir
    t0 = time.time()
    with bpy.context.temp_override(scene=SC, object=dom, active_object=dom, selected_objects=[dom]):
        bpy.ops.fluid.free_all()
        bpy.ops.fluid.bake_all()
    P['bake_sec'] = round(time.time() - t0, 1)
    P['frames'] = A.frames; P['res'] = A.res
    P['domain'] = dict(loc=list(dom.location), scale=list(dom.scale))
    json.dump(P, open(os.path.join(A.out, f'sim_{i:03d}.json'), 'w'), indent=1)
    print('[bake]', P, flush=True)
    if A.preview:
        r = SC.render
        r.engine = 'CYCLES'; r.resolution_x, r.resolution_y, r.resolution_percentage = 576, 320, 100
        SC.cycles.samples = 32; SC.cycles.use_denoising = True; SC.cycles.volume_bounces = 1
        try:
            prefs = bpy.context.preferences.addons['cycles'].preferences
            prefs.compute_device_type = 'OPTIX'; prefs.refresh_devices()
            for d in prefs.devices:
                d.use = d.type == 'OPTIX'
            SC.cycles.device = 'GPU'
        except Exception as e:
            print('GPU 設定失敗', e)
        SC.camera = nearest_cam(x, y)
        for f in (20, 45, 75, min(110, A.frames)):
            SC.frame_set(f)
            r.filepath = os.path.join(A.out, f'sim_{i:03d}_f{f:03d}.png')
            bpy.ops.render.render(write_still=True, scene=SC.name)
print('[bake] done', flush=True)
