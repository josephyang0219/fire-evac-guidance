# -*- coding: utf-8 -*-
"""把 YOLO 標註框疊到圖上（Blender 內建 numpy，不需要 PIL/cv2）。

    blender -b -P draw_preview.py -- --src <資料夾，內含 images/ labels/> --out <輸出> --n 5
挑圖規則：類別種類多的優先，其次框多的，同分照檔名排序（結果固定）。
框的顏色依類別，左上角的數字是類別編號（0 櫃子 1 紙箱 2 桌椅 3 瓦礫 4 閘門 5 煙 6 人偶）。
"""
import bpy, os, sys, argparse
import numpy as np

COLORS = [(1.0, 0.25, 0.25), (1.0, 0.65, 0.1), (1.0, 1.0, 0.2), (0.3, 1.0, 0.3),
          (0.2, 0.9, 1.0), (0.75, 0.75, 0.75), (1.0, 0.3, 1.0)]
FONT = {  # 3x5 點陣數字
    '0': '111101101101111', '1': '010110010010111', '2': '111001111100111', '3': '111001111001111',
    '4': '101101111001001', '5': '111100111001111', '6': '111100111101111', '7': '111001001001001',
    '8': '111101111101111', '9': '111101111001111'}

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument('--src', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--n', type=int, default=5)
ap.add_argument('--names', default='', help='指定檔名（逗號分隔，不含副檔名）')
A = ap.parse_args(argv)


def load(path):
    im = bpy.data.images.load(path, check_existing=False)
    w, h = im.size
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    return a.reshape(h, w, 4)[::-1, :, :3].copy()


def save(img, path):
    h, w = img.shape[:2]
    im = bpy.data.images.new('preview', w, h, alpha=False)
    rgba = np.ones((h, w, 4), np.float32)
    rgba[:, :, :3] = img
    im.pixels.foreach_set(rgba[::-1].ravel())
    im.filepath_raw = path
    im.file_format = 'JPEG'
    im.save(filepath=path, quality=90)
    bpy.data.images.remove(im)


def draw(img, cls, xc, yc, bw, bh):
    H, W = img.shape[:2]
    x0, x1 = int(round((xc - bw / 2) * W)), int(round((xc + bw / 2) * W)) - 1
    y0, y1 = int(round((yc - bh / 2) * H)), int(round((yc + bh / 2) * H)) - 1
    c = COLORS[cls % len(COLORS)]
    t = 2
    img[max(0, y0):max(0, y0) + t, max(0, x0):x1 + 1] = c
    img[max(0, y1 - t + 1):y1 + 1, max(0, x0):x1 + 1] = c
    img[max(0, y0):y1 + 1, max(0, x0):max(0, x0) + t] = c
    img[max(0, y0):y1 + 1, max(0, x1 - t + 1):x1 + 1] = c
    # 類別編號標籤（黑底彩字，放大 2 倍）
    s = 2
    ty, tx = max(0, y0), max(0, x0)
    img[ty:ty + 5 * s + 4, tx:tx + 3 * s + 4] = 0
    for i, bit in enumerate(FONT[str(cls)]):
        if bit == '1':
            r, q = divmod(i, 3)
            img[ty + 2 + r * s:ty + 2 + (r + 1) * s, tx + 2 + q * s:tx + 2 + (q + 1) * s] = c


def main():
    lab_dir, img_dir = os.path.join(A.src, 'labels'), os.path.join(A.src, 'images')
    stems = sorted(os.path.splitext(f)[0] for f in os.listdir(lab_dir) if f.endswith('.txt'))
    rows = {}
    for s in stems:
        with open(os.path.join(lab_dir, s + '.txt')) as f:
            rows[s] = [l.split() for l in f if l.strip()]
    if A.names:
        pick = A.names.split(',')
    else:
        pick = sorted(stems, key=lambda s: (-len({r[0] for r in rows[s]}), -len(rows[s]), s))[:A.n]
    os.makedirs(A.out, exist_ok=True)
    for s in pick:
        ip = next(os.path.join(img_dir, s + e) for e in ('.jpg', '.png', '.jpeg') if os.path.exists(os.path.join(img_dir, s + e)))
        img = load(ip)
        for r in rows[s]:
            draw(img, int(r[0]), *map(float, r[1:5]))
        save(np.clip(img, 0, 1), os.path.join(A.out, s + '_preview.jpg'))
        print('[preview]', s, 'boxes =', len(rows[s]), 'classes =', sorted({int(r[0]) for r in rows[s]}))


main()
