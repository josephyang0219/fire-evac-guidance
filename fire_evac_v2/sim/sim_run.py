import bpy, bmesh, math, os, json
from mathutils import Vector, Matrix, Euler

SCN = "Sim_Run"
OUT = os.path.join(os.path.dirname(bpy.data.filepath), "yolo_synth", "sim_run")
PITCH = 150.0
F_LENS, SW, SH = 2.9821, 5.6, 3.15
CAMS = [("N", 0.0), ("W", 90.0), ("E", -90.0), ("S", 180.0)]
FLOORS = {1: dict(tray="Floor_Tray_G", ringc=99.0, smoke="new"), 2: dict(tray="Floor_Tray", ringc=102.0, smoke="old")}
PORTS = [(-51.0, 102.0), (-51.0, -102.0), (0.0, -51.0), (51.0, 0.0)]
LEDS = [(0, 104), (-104, 0), (104, 0), (0, -104), (-91, 113), (113, 113), (113, -91), (-91, -91), (11, 11)]

# scripted scenario: each step lists what is in the building at that moment
STEPS = [
    dict(t="00:00", note="平常狀態，全部暢通", obs=[], smoke=None, gates=[], cams_off=[]),
    dict(t="00:30", note="一樓東側起火冒煙", obs=[], smoke=(1, 3, 18), gates=[], cams_off=[]),
    dict(t="01:00", note="煙擴散；一樓東出口前櫃子倒下", obs=[(1, "Cabinet_B_fallen", 99, 58, 90)], smoke=(1, 3, 40), gates=[], cams_off=[]),
    dict(t="01:30", note="二樓北側走廊箱子散落", obs=[(1, "Cabinet_B_fallen", 99, 58, 90), (2, "Boxes_B_scattered", 40, 102, 0), (2, "Rubble_A_pile", -60, 0, 30)], smoke=(1, 3, 65), gates=[], cams_off=[]),
    dict(t="02:00", note="一樓南側走廊被封鎖（閘門）", obs=[(1, "Cabinet_B_fallen", 99, 58, 90), (2, "Boxes_B_scattered", 40, 102, 0), (2, "Rubble_A_pile", -60, 0, 30)], smoke=(1, 3, 85), gates=[(1, "ring", -51.0, -99.0, 0.0)], cams_off=[]),
    dict(t="02:30", note="一樓東側鏡頭故障，改用其他鏡頭資訊", obs=[(1, "Cabinet_B_fallen", 99, 58, 90), (2, "Boxes_B_scattered", 40, 102, 0), (2, "Rubble_A_pile", -60, 0, 30)], smoke=(1, 3, 90), gates=[(1, "ring", -51.0, -99.0, 0.0)], cams_off=[(1, "E")]),
]


def rot_pt(x, y, rz):
    c, s = math.cos(math.radians(rz)), math.sin(math.radians(rz))
    return x * c - y * s, x * s + y * c


def link(scn, name, data, M):
    o = bpy.data.objects.get(name)
    if o:
        bpy.data.objects.remove(o)
    o = bpy.data.objects.new(name, data)
    scn.collection.objects.link(o)
    o.matrix_world = M
    return o


def setmat(o, m):
    if not o.material_slots:
        o.data.materials.append(m)
    for s in o.material_slots:
        s.link = 'OBJECT'; s.material = m


def mat(name, rgb, emit=0.0, rough=0.5):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough
    b.inputs["Emission Color"].default_value = (*rgb, 1); b.inputs["Emission Strength"].default_value = emit
    return m


def build():
    scn = bpy.data.scenes.get(SCN) or bpy.data.scenes.new(SCN)
    for o in list(scn.collection.objects):
        if o.name.startswith("R_"):
            bpy.data.objects.remove(o)
        else:
            scn.collection.objects.unlink(o)
    scn.unit_settings.scale_length = 0.001; scn.unit_settings.length_unit = 'MILLIMETERS'
    scn.render.engine = 'CYCLES'; scn.cycles.device = 'GPU'; scn.cycles.samples = 24; scn.cycles.use_denoising = True
    scn.render.resolution_x, scn.render.resolution_y = 640, 360
    scn.world = bpy.data.scenes["YOLO_Synth"].world
    black = bpy.data.materials["PLA_Black"]
    for fl, F in FLOORS.items():
        z = (fl - 1) * PITCH
        setmat(link(scn, f"R_Tray_{fl}", bpy.data.objects[F["tray"]].data, Matrix.Translation((0, 0, z))), black)
        setmat(link(scn, f"R_Lid_{fl}", bpy.data.objects["Floor_Lid"].data, Matrix.Translation((0, 0, z))), black)
        for n, rz in CAMS:
            x, y = rot_pt(0.0, 92.0, rz)
            c = link(scn, f"R_Cam_{fl}{n}", bpy.data.cameras["S_CamData"], Matrix.Translation((x, y, 111.0 + z)) @ Euler((math.radians(-18), 0, math.radians(rz))).to_matrix().to_4x4())
        for k, (x, y) in enumerate(LEDS):
            ld = bpy.data.lights.get(f"R_LedL_{fl}_{k}") or bpy.data.lights.new(f"R_LedL_{fl}_{k}", 'POINT')
            ld.energy = 32000; ld.shadow_soft_size = 3; ld.color = (1, 0.97, 0.92)
            link(scn, f"R_LedL_{fl}_{k}", ld, Matrix.Translation((x, y, 106 + z)))
    scn.view_settings.exposure = 0.9
    dom = bpy.data.objects["SIM_Domain"]
    if dom.name not in scn.collection.objects:
        scn.collection.objects.link(dom)
    return scn


def place_step(scn, step):
    white = bpy.data.materials["PLA_White"]
    for o in list(scn.objects):
        if o.name.startswith(("R_obs_", "R_gate_", "R_inc_")):
            bpy.data.objects.remove(o)
    for k, (fl, src, x, y, rz) in enumerate(step["obs"]):
        o = link(scn, f"R_obs_{k}", bpy.data.objects[src].data, Matrix.Translation((x, y, 8 + (fl - 1) * PITCH)) @ Matrix.Rotation(math.radians(rz), 4, 'Z'))
        setmat(o, white)
    for k, (fl, kind, x, y, rz) in enumerate(step["gates"]):
        src = "Gate_Plug_G36" if fl == 1 else "Gate_Plug"
        o = link(scn, f"R_gate_{k}", bpy.data.objects[src].data, Matrix.Translation((x, y, 8 + (fl - 1) * PITCH)) @ Matrix.Rotation(math.radians(rz), 4, 'Z'))
        setmat(o, white)
    dom = bpy.data.objects["SIM_Domain"]
    if step["smoke"]:
        fl, pi, fr = step["smoke"]
        d = dom.modifiers["Fluid"].domain_settings
        d.cache_directory = os.path.join(os.path.dirname(bpy.data.filepath), "smoke_cache", f"{FLOORS[fl]['smoke']}_p{pi}")
        dom.location = (0, 0, (fl - 1) * PITCH)
        dom.hide_render = False
        bpy.data.materials["SIM_SmokeMat"].node_tree.nodes["DEN"].inputs[1].default_value = 4.0
        scn.frame_set(fr)
    else:
        dom.hide_render = True


def render_cams(scn, idx, step):
    os.makedirs(os.path.join(OUT, f"step{idx}"), exist_ok=True)
    for fl in FLOORS:
        for n, _ in CAMS:
            if (fl, n) in [tuple(c) for c in step["cams_off"]]:
                continue
            scn.camera = scn.objects[f"R_Cam_{fl}{n}"]
            scn.render.filepath = os.path.join(OUT, f"step{idx}", f"F{fl}_{n}.png")
            bpy.ops.render.render(write_still=True, scene=scn.name)


# ---------- overview with LED arrows ----------
def arrow_mesh():
    me = bpy.data.meshes.get("R_ArrowMesh")
    if me:
        return me
    bm = bmesh.new()
    pts = [(-2.5, -9), (2.5, -9), (2.5, 1), (6.5, 1), (0, 10), (-6.5, 1), (-2.5, 1)]
    vs = [bm.verts.new((x, y, 0)) for x, y in pts]; vt = [bm.verts.new((x, y, 1.5)) for x, y in pts]
    bm.faces.new(vs[::-1]); bm.faces.new(vt)
    for i in range(len(pts)):
        j = (i + 1) % len(pts); bm.faces.new((vs[i], vs[j], vt[j], vt[i]))
    me = bpy.data.meshes.new("R_ArrowMesh"); bm.to_mesh(me); bm.free()
    return me


def cross_mesh():
    me = bpy.data.meshes.get("R_CrossMesh")
    if me:
        return me
    bm = bmesh.new()
    for a in (45, -45):
        bmesh.ops.create_cube(bm, size=1, matrix=Matrix.Rotation(math.radians(a), 4, 'Z') @ Matrix.Diagonal((18, 4, 1.5, 1)))
    me = bpy.data.meshes.new("R_CrossMesh"); bm.to_mesh(me); bm.free()
    return me


def show_leds(scn, leds):
    """leds: {"1,-1,1": "N"|"E"|"S"|"W"|"DOWN"|"UP"|"X"}"""
    for o in list(scn.objects):
        if o.name.startswith("R_led_"):
            bpy.data.objects.remove(o)
    g = mat("R_LedGreen", (0.1, 1.0, 0.25), emit=6.0); r = mat("R_LedRed", (1.0, 0.08, 0.05), emit=6.0); b = mat("R_LedBlue", (0.2, 0.5, 1.0), emit=6.0)
    ang = {"N": 0, "W": 90, "S": 180, "E": -90}
    for k, (x, y) in enumerate(((109.0, 51.0), (-109.0, -51.0))):
        bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1, matrix=Matrix.Diagonal((5, 34, 2, 1))); me = bpy.data.meshes.new("R_exitmesh"); bm.to_mesh(me); bm.free()
        o = link(scn, f"R_led_exit_{k}", me, Matrix.Translation((x, y, 9))); setmat(o, g)
    for key, d in leds.items():
        fl, i, j = map(int, key.split(","))
        c = FLOORS[fl]["ringc"]
        P = Vector((i * c, j * c, 9 + (fl - 1) * PITCH))
        if d in ang:
            o = link(scn, f"R_led_{key}", arrow_mesh(), Matrix.Translation(P) @ Matrix.Rotation(math.radians(ang[d]), 4, 'Z')); setmat(o, g)
        elif d in ("DOWN", "UP"):
            o = link(scn, f"R_led_{key}", arrow_mesh(), Matrix.Translation(P + Vector((0, 0, 1))) @ Matrix.Rotation(math.radians(0 if d == "UP" else 180), 4, 'Z') @ Matrix.Diagonal((1.2, 1.2, 1, 1))); setmat(o, b)
        else:
            o = link(scn, f"R_led_{key}", cross_mesh(), Matrix.Translation(P)); setmat(o, r)


def render_overview(scn, idx, res=(1280, 720)):
    """cut-away view: lids hidden, both floors side by side via two cameras -> two images"""
    cd = bpy.data.cameras.get("R_OverCam") or bpy.data.cameras.new("R_OverCam")
    cd.type = 'ORTHO'; cd.ortho_scale = 300; cd.clip_start = 1; cd.clip_end = 5000
    oc = bpy.data.objects.get("R_Over") or link(scn, "R_Over", cd, Matrix.Identity(4))
    rx, ry = scn.render.resolution_x, scn.render.resolution_y
    scn.render.resolution_x, scn.render.resolution_y = 900, 900
    saved = {o.name: o.hide_render for o in scn.objects}
    for fl in FLOORS:
        z = (fl - 1) * PITCH
        oc.matrix_world = Matrix.Translation((0, 0, z + 400))
        for o in scn.objects:
            if o.type in ('CAMERA', 'LIGHT') or o.name == "R_Over":
                continue
            ofl = 2 if o.matrix_world.translation.z >= 140 else 1
            if o.name.startswith("R_Stair") or o.name.startswith("R_Lid_"):
                o.hide_render = True
            elif o.name.startswith(("R_Tray_", "R_obs_", "R_gate_", "R_led_", "R_inc_", "SIM_Domain")):
                o.hide_render = saved[o.name] or (ofl != fl)
        scn.camera = oc
        scn.render.filepath = os.path.join(OUT, f"step{idx}", f"over_F{fl}.png")
        bpy.ops.render.render(write_still=True, scene=scn.name)
    for o in scn.objects:
        if o.name in saved:
            o.hide_render = saved[o.name]
    scn.render.resolution_x, scn.render.resolution_y = rx, ry
