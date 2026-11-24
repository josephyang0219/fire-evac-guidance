# -*- coding: utf-8 -*-
"""把多個來源（渲染、空場景、教室負樣本、實拍）合併成 YOLOv7 資料集，並打包成 zip 給 Colab。
只用標準函式庫。

    python retrain/tools/make_dataset.py --out %USERPROFILE%\\fire_retrain\\datasets\\fire7 ^
        --src out/dr_s001 --src out/empty_s002 --src out/neg_classroom --src real/model_photos:3 --zip

--src 路徑可以是 --work 底下的相對路徑；`:3` 表示這個來源在訓練集重複 3 次（實拍照片少，加重權重）。
`@train`／`@val` 結尾：這個來源全部放 train 或全部放 val，不用 hash 切（例如 val 用另外幾組煙霧模擬渲染，
避免同一團煙同時出現在 train 和 val）。例：--src out/dr_s601@train --src out/dr_s603_val@val
切分：用檔名的 hash 決定 train / val（預設 val 15%），重跑結果一樣；重複只套用在 train。
輸出：
  <out>/images/{train,val}/*.jpg  <out>/labels/{train,val}/*.txt
  <out>/data.yaml（path 寫 /content/fire7，Colab 解壓到 /content 就能直接用）
  <out>/sources.csv（每張圖來自哪裡、在哪個 split）
"""
import sys as _sys
_sys.stdout.reconfigure(errors='replace')  # Windows 主控台是 cp950，印不出的字元用 ? 代替
import argparse, csv, hashlib, os, shutil

NAMES = ['cabinet', 'boxes', 'furniture', 'rubble', 'gate', 'smoke', 'person']
IMG_EXT = ('.jpg', '.jpeg', '.png')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--src', action='append', required=True)
    ap.add_argument('--work', default=os.path.join(os.path.expanduser('~'), 'fire_retrain'))
    ap.add_argument('--val', type=float, default=0.15)
    ap.add_argument('--colab-path', default='/content/fire7')
    ap.add_argument('--zip', action='store_true')
    ap.add_argument('--quant', type=int, default=0,
                    help='另外挑 N 張 val 圖打包成量化校正圖 zip（各來源平均分配，Realtek 轉檔用）')
    a = ap.parse_args()

    out = os.path.abspath(a.out)
    if os.path.exists(out):
        shutil.rmtree(out)
    for sp in ('train', 'val'):
        os.makedirs(os.path.join(out, 'images', sp))
        os.makedirs(os.path.join(out, 'labels', sp))
    rows, count = [], {'train': 0, 'val': 0}
    for spec in a.src:
        force = None
        if spec.endswith(('@train', '@val')):
            spec, force = spec.rsplit('@', 1)
        head, _, tail = spec.rpartition(':')
        path, rep = (head, int(tail)) if head and tail.isdigit() else (spec, 1)  # 不會誤吃 C:\ 的冒號
        src = path if os.path.isabs(path) else os.path.join(a.work, path)
        tag = os.path.basename(os.path.normpath(src))
        n = 0
        for fn in sorted(os.listdir(os.path.join(src, 'images'))):
            stem, ext = os.path.splitext(fn)
            if ext.lower() not in IMG_EXT:
                continue
            lab = os.path.join(src, 'labels', stem + '.txt')
            if not os.path.exists(lab):
                raise SystemExit(f'{src}: {stem} 沒有標註檔（負樣本也要有空的 .txt）')
            h = int(hashlib.sha256(stem.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
            sp = force or ('val' if h < a.val else 'train')
            for k in range(rep if sp == 'train' else 1):
                name = f'{tag}__{stem}' + (f'__r{k}' if k else '')
                shutil.copy2(os.path.join(src, 'images', fn), os.path.join(out, 'images', sp, name + ext.lower()))
                shutil.copy2(lab, os.path.join(out, 'labels', sp, name + '.txt'))
                rows.append([name, src, sp])
                count[sp] += 1
            n += 1
        print(f'{tag}: {n} 張（train 重複 {rep} 次）' + (f'，全部放 {force}' if force else ''))
    with open(os.path.join(out, 'data.yaml'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(f'# 火場避難 7 類（0-5 沿用原本順序，6 = person）\n')
        f.write(f'train: {a.colab_path}/images/train\nval: {a.colab_path}/images/val\n')
        f.write(f'nc: {len(NAMES)}\nnames: {NAMES}\n')
    with open(os.path.join(out, 'sources.csv'), 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows([['name', 'source', 'split']] + rows)
    print(f'train {count["train"]} / val {count["val"]} → {out}')
    if a.quant:
        qdir = out + '_quant_images'
        shutil.rmtree(qdir, ignore_errors=True)
        os.makedirs(qdir)
        by_src = {}
        for name, src, sp in rows:
            if sp == 'val':
                by_src.setdefault(src, []).append(name)
        pick, k = [], 0
        while len(pick) < a.quant and any(by_src.values()):  # 輪流從每個來源拿一張
            for src in sorted(by_src):
                if by_src[src] and len(pick) < a.quant:
                    lst = by_src[src]
                    pick.append(lst.pop(int(hashlib.sha256(f'{k}'.encode()).hexdigest(), 16) % len(lst)))
                    k += 1
        for name in pick:
            fn = next(f for f in os.listdir(os.path.join(out, 'images', 'val')) if os.path.splitext(f)[0] == name)
            shutil.copy2(os.path.join(out, 'images', 'val', fn), os.path.join(qdir, fn))
        z = shutil.make_archive(qdir, 'zip', qdir)
        print(f'量化校正圖 {len(pick)} 張 → {z}')
    if a.zip:
        z = shutil.make_archive(out, 'zip', os.path.dirname(out), os.path.basename(out))
        print('zip →', z, f'{os.path.getsize(z) / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
