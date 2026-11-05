# -*- coding: utf-8 -*-
"""教室實景照片 → 576×320 負樣本＋空標註（Blender 內建 numpy，不需要 PIL/cv2）。

由 run_blender.py negatives 啟動（它會先把照片複製成英文檔名）：
    blender -b -P prepare_negatives.py -- --src <照片> --out <輸出> --name classroom [--crops 3]

每張照片輸出：中央裁切 1 張 ＋ 隨機裁切 (crops-1) 張，長寬比 576:320，縮到 576×320。
隨機裁切用照片內容的 hash 當種子 → 重跑結果一樣。
輸出 images/*.jpg、labels/*.txt（空檔）、manifest.csv（來源檔、裁切範圍）。

注意：照片裡「不能有任何目標物」（櫃子、紙箱、桌椅、瓦礫、閘門、煙、人偶）。
教室本身的桌椅、櫃子是真的家具，但不是模型裡的道具——它們正是這次要壓下去的誤判來源，
所以要當負樣本；只是人偶、模型道具、線香煙不能入鏡。
"""
import bpy, os, sys, csv, random, hashlib, argparse
import numpy as np

W, H = 576, 320
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument('--src', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--name', default='classroom')
ap.add_argument('--crops', type=int, default=3)
ap.add_argument('--min-scale', type=float, default=0.5, help='隨機裁切最小邊長比例')
A = ap.parse_args(argv)


def load(path):
    im = bpy.data.images.load(path, check_existing=False)
    w, h = im.size
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    return a.reshape(h, w, 4)[::-1, :, :3].copy()


def resize(img, w, h):
    # 區域平均縮小（先整數倍 box，再雙線性），避免鋸齒
    ih, iw = img.shape[:2]
    f = max(1, min(iw // w, ih // h) // 2)
    if f > 1:
        img = img[:ih // f * f, :iw // f * f].reshape(ih // f, f, iw // f, f, 3).mean((1, 3))
        ih, iw = img.shape[:2]
    ys = (np.arange(h) + 0.5) * ih / h - 0.5
    xs = (np.arange(w) + 0.5) * iw / w - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, ih - 1); y1 = np.clip(y0 + 1, 0, ih - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, iw - 1); x1 = np.clip(x0 + 1, 0, iw - 1)
    wy = np.clip(ys - y0, 0, 1)[:, None, None]; wx = np.clip(xs - x0, 0, 1)[None, :, None]
    a = img[y0][:, x0] * (1 - wx) + img[y0][:, x1] * wx
    b = img[y1][:, x0] * (1 - wx) + img[y1][:, x1] * wx
    return a * (1 - wy) + b * wy


def save(img, path):
    im = bpy.data.images.new('neg', W, H, alpha=False)
    rgba = np.ones((H, W, 4), np.float32)
    rgba[:, :, :3] = np.clip(img, 0, 1)
    im.pixels.foreach_set(rgba[::-1].ravel())
    im.filepath_raw = path
    im.file_format = 'JPEG'
    im.save(filepath=path, quality=92)
    bpy.data.images.remove(im)


def main():
    for d in ('images', 'labels'):
        os.makedirs(os.path.join(A.out, d), exist_ok=True)
    files = sorted(f for f in os.listdir(A.src) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff')))
    rows = []
    for fn in files:
        path = os.path.join(A.src, fn)
        img = load(path)
        ih, iw = img.shape[:2]
        seed = int(hashlib.sha256(open(path, 'rb').read()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        # 576:320 的最大裁切框
        cw, ch = (iw, int(iw * H / W)) if iw * H / W <= ih else (int(ih * W / H), ih)
        for k in range(A.crops):
            if k == 0:
                s, x, y = 1.0, (iw - cw) // 2, (ih - ch) // 2
            else:
                s = rng.uniform(A.min_scale, 1.0)
                x, y = rng.randint(0, iw - int(cw * s)), rng.randint(0, ih - int(ch * s))
            w_, h_ = int(cw * s), int(ch * s)
            out = resize(img[y:y + h_, x:x + w_], W, H)
            stem = f'neg_{A.name}_{os.path.splitext(fn)[0]}_{k}'
            save(out, os.path.join(A.out, 'images', stem + '.jpg'))
            open(os.path.join(A.out, 'labels', stem + '.txt'), 'w').close()
            rows.append([stem, fn, iw, ih, x, y, w_, h_])
        print('[neg]', fn, f'{iw}x{ih}', '→', A.crops, 'crops')
    with open(os.path.join(A.out, 'manifest.csv'), 'w', newline='', encoding='utf-8') as f:
        wr = csv.writer(f)
        wr.writerow(['stem', 'source', 'src_w', 'src_h', 'crop_x', 'crop_y', 'crop_w', 'crop_h'])
        wr.writerows(rows)
    print(f'[neg] done: {len(files)} photos → {len(rows)} negatives in {A.out}')


main()
