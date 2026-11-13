"""
把 views_D 的單張圖排成兩張組合圖（在空白場景用影像平面＋文字渲染；Cycles、全部 emission，顏色不變）：
  組合圖_方案D_多視角.png：3×3（拉遠全景、等角斜視剖切、人眼視角×3、四方位側視×4）
  組合圖_方案D_接線.png：2×3（設備層俯視、H5／H6／H7 接線特寫、電源出口南／北）
每格上方有標題，最下面一列是圖例（OLED 顏色、導線顏色、HUB 代號）。
  blender -b --factory-startup --python make_composites.py -- <views_D 資料夾>
"""
import bpy, sys, os

D = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = 8; sc.cycles.use_denoising = False; sc.cycles.pixel_filter_type = "BOX"; sc.cycles.filter_width = 1.0
sc.view_settings.view_transform = "Standard"; sc.render.resolution_percentage = 100
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
FONT = bpy.data.fonts.load("C:/Windows/Fonts/msjh.ttc"); FONTB = bpy.data.fonts.load("C:/Windows/Fonts/msjhbd.ttc")

def emit_mat(name, color=None, image=None):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); e = nt.nodes.new("ShaderNodeEmission"); nt.links.new(e.outputs[0], out.inputs[0])
    if image:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = image; t.interpolation = "Cubic"; nt.links.new(t.outputs[0], e.inputs[0])
    else: e.inputs[0].default_value = color
    return m
def rect(x, y, wd, ht, mat, z=0.0):
    me = bpy.data.meshes.new("r"); me.from_pydata([(x, y, z), (x + wd, y, z), (x + wd, y + ht, z), (x, y + ht, z)], [], [(0, 1, 2, 3)])
    me.uv_layers.new(); uv = me.uv_layers[0].data
    for i, c in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))): uv[i].uv = c
    ob = bpy.data.objects.new("r", me); sc.collection.objects.link(ob); me.materials.append(mat); return ob
BLACK = emit_mat("k", (0.05, 0.05, 0.05, 1))
def text(body, x, y, size, color=None, bold=False, align="LEFT"):
    cu = bpy.data.curves.new("t", "FONT"); cu.body = body; cu.size = size; cu.font = FONTB if bold else FONT; cu.align_x = align; cu.align_y = "BOTTOM"
    ob = bpy.data.objects.new("t", cu); sc.collection.objects.link(ob); ob.location = (x, y, 1.0)
    cu.materials.append(emit_mat("tc", color) if color else BLACK); return ob

def composite(fname, title, cells, cols, cell_w, cell_h, legend):
    M, TH, LH = 24, 54, 230
    rows = (len(cells) + cols - 1) // cols
    W = cols * cell_w + (cols + 1) * M; H = 110 + rows * (TH + cell_h + M) + LH
    for o in list(sc.objects): bpy.data.objects.remove(o, do_unlink=True)
    text(title, M, H - 80, 46, bold=True)
    for k, (img, cap) in enumerate(cells):
        r, c = divmod(k, cols)
        x0 = M + c * (cell_w + M); ytop = H - 110 - r * (TH + cell_h + M)
        text(cap, x0 + 4, ytop - TH + 12, 30, bold=True)
        im = bpy.data.images.load(os.path.join(D, img)); iw, ih = im.size; s = min(cell_w / iw, cell_h / ih)
        wd, ht = iw * s, ih * s; rect(x0 + (cell_w - wd) / 2, ytop - TH - cell_h + (cell_h - ht) / 2, wd, ht, emit_mat("im", image=im))
        rect(x0 - 2, ytop - TH - cell_h - 2, cell_w + 4, cell_h + 4, emit_mat("fr", (0.8, 0.8, 0.8, 1)), z=-0.5)
        rect(x0, ytop - TH - cell_h, cell_w, cell_h, emit_mat("bgc", (1, 1, 1, 1)), z=-0.2)
    # 圖例
    y = LH - 60; x = M
    text("圖例", x, y + 4, 32, bold=True); x += 110
    for item in legend:
        if item is None: y -= 70; x = M + 110; continue
        col, lab = item
        rect(x, y, 44, 34, emit_mat("lg", col)); text(lab, x + 56, y + 2, 28); x += 56 + 30 * len(lab) * 0.95 + 46
    cam_d = bpy.data.cameras.new("c"); cam_d.type = "ORTHO"; cam_d.ortho_scale = max(W, H)
    cam = bpy.data.objects.new("c", cam_d); sc.collection.objects.link(cam); cam.location = (W / 2, H / 2, 100); sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = int(W), int(H)
    sc.render.filepath = os.path.join(D, fname); bpy.ops.render.render(write_still=True)

LEG_COMMON = [((0.1, 1.0, 1.0, 1), "OLED 顯示區（9 塊）"), ((0.9, 0.08, 0.08, 1), "紅＝VCC／3V3／5V"), ((0.04, 0.04, 0.04, 1), "黑＝GND"),
              ((0.95, 0.85, 0.05, 1), "黃＝SCL"), ((0.05, 0.65, 0.15, 1), "綠＝SDA"), ((0.3, 0.3, 0.33, 1), "灰＝USB 線"), None,
              ((0.15, 0.55, 0.3, 1), "H5／H6／H7＝只驅動 OLED 的 HUB（Wire，0x3C＋0x3D）"), ((0.6, 0.5, 0.4, 1), "鏡頭 HUB N／E／S／W（麵包板座內）"),
              ((1.0, 0.55, 0.12, 1), "塞子頂面（要能拆）"), ((0.95, 0.7, 0.25, 1), "分接板"), ((0.97, 0.97, 0.9, 1), "固定膠帶")]
composite("組合圖_方案D_多視角.png", "方案 D：9 塊 OLED、7 台 HUB（4 台鏡頭 HUB＋H5／H6／H7）多視角",
          [("3D_拉遠全景_九塊OLED.png", "拉遠全景（從斜下方）"), ("等角斜視剖切_拿掉2F與外牆_天花板半透明.png", "等角斜視剖切（拿掉 2F 與外牆）"),
           ("人眼視角1_站在中心路口往北看.png", "人眼視角 1：中心路口往北"), ("人眼視角2_站在北邊中點鏡頭孔下方往中心看.png", "人眼視角 2：北邊中點往中心"),
           ("人眼視角3_站在西北角落路口.png", "人眼視角 3：西北角落"), ("側視_從東往西看.png", "側視：從東往西"),
           ("側視_從南往北看.png", "側視：從南往北"), ("側視_從西往東看.png", "側視：從西往東"), ("側視_從北往南看.png", "側視：從北往南")],
          3, 1000, 640, LEG_COMMON)
composite("組合圖_方案D_接線.png", "方案 D 外接線：每塊 OLED 4 條杜邦線、2 塊分接板、7 台 HUB 的 USB 電源集中到南北 2 個出口",
          [("接線_設備層俯視_7台HUB與全部外接線.png", "設備層俯視（拿掉 2F 與麵包板座）"), ("接線特寫_H5.png", "H5：S（0x3C）＋E（0x3D）經分接板"),
           ("接線特寫_H6.png", "H6：W（0x3C）＋N（0x3D）經分接板"), ("接線特寫_H7.png", "H7：C（0x3C）直接到排針"),
           ("電源出口特寫_南.png", "南出口：鏡頭 S、W＋H5、H7"), ("電源出口特寫_北.png", "北出口：鏡頭 N、E＋H6")],
          3, 1000, 900, LEG_COMMON)
print("composites done")
