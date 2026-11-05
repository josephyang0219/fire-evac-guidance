# -*- coding: utf-8 -*-
"""檢查 YOLO 標註（只用標準函式庫）。

    python retrain/tools/check_labels.py <資料夾> [<資料夾> ...] [--nc 7] [--json 報告.json]

每個資料夾要有 images/ 和 labels/；有 meta/（渲染輸出）時會一併檢查：
  1. 格式：每行 5 個數字、類別是 0..nc-1 的整數、中心與寬高都在 (0,1]、框不超出畫面
  2. 對應：每張圖都有標註檔（空檔＝負樣本），沒有多餘的標註檔
  3. 渲染交叉驗證（meta）：
     - 遮罩框必須落在魚眼投影框內（容許 3 px）——兩種獨立方法算出的位置一致
     - 標註檔的行數 = meta 裡 labeled=True 的物件數，而且框一致
     - 遮罩裡沒有不認識的物件編號（unknown_mask_ids 為空）
有任何錯誤時 exit code = 1。
"""
import sys as _sys
_sys.stdout.reconfigure(errors='replace')  # Windows 主控台是 cp950，印不出的字元用 ? 代替
import argparse, json, os, sys
from collections import Counter

NAMES = ['cabinet', 'boxes', 'furniture', 'rubble', 'gate', 'smoke', 'person']
W, H = 576, 320
IMG_EXT = ('.jpg', '.jpeg', '.png')


def check_dir(d, nc, errs, stats):
    img_dir, lab_dir, meta_dir = (os.path.join(d, x) for x in ('images', 'labels', 'meta'))
    imgs = {os.path.splitext(f)[0] for f in os.listdir(img_dir) if f.lower().endswith(IMG_EXT)}
    labs = {os.path.splitext(f)[0] for f in os.listdir(lab_dir) if f.endswith('.txt')}
    for s in sorted(imgs - labs):
        errs.append(f'{d}: {s} 沒有標註檔')
    for s in sorted(labs - imgs):
        errs.append(f'{d}: {s}.txt 沒有對應的圖')
    has_meta = os.path.isdir(meta_dir)
    for s in sorted(imgs & labs):
        stats['images'] += 1
        rows = []
        with open(os.path.join(lab_dir, s + '.txt'), encoding='ascii') as f:
            for i, line in enumerate(f, 1):
                if not line.strip():
                    continue
                p = line.split()
                where = f'{d}: {s}.txt 第 {i} 行'
                if len(p) != 5:
                    errs.append(f'{where} 欄位數 {len(p)} ≠ 5'); continue
                try:
                    c = int(p[0]); xc, yc, w, h = map(float, p[1:])
                except ValueError:
                    errs.append(f'{where} 不是數字'); continue
                if not 0 <= c < nc:
                    errs.append(f'{where} 類別 {c} 超出 0..{nc - 1}')
                if not (0 < w <= 1 and 0 < h <= 1 and 0 <= xc <= 1 and 0 <= yc <= 1):
                    errs.append(f'{where} 數值超出範圍')
                if xc - w / 2 < -1e-4 or xc + w / 2 > 1 + 1e-4 or yc - h / 2 < -1e-4 or yc + h / 2 > 1 + 1e-4:
                    errs.append(f'{where} 框超出畫面')
                rows.append((c, xc, yc, w, h))
                stats['boxes'][c] += 1
                stats['area'][c] += w * h
        if not rows:
            stats['empty'] += 1
        if has_meta and os.path.exists(os.path.join(meta_dir, s + '.json')):
            m = json.load(open(os.path.join(meta_dir, s + '.json'), encoding='utf-8'))
            stats['meta'] += 1
            if m.get('unknown_mask_ids'):
                errs.append(f'{d}: {s} 遮罩有不認識的編號 {m["unknown_mask_ids"]}')
            labeled = [o for o in m['objects'] if o.get('labeled')]
            if len(labeled) != len(rows):
                errs.append(f'{d}: {s} 標註 {len(rows)} 行，meta 有 {len(labeled)} 個物件')
            for o, r in zip(labeled, rows):
                x0, y0, x1, y1 = o['mask_bbox']
                exp = (o['cls'], (x0 + x1) / 2 / W, (y0 + y1) / 2 / H, (x1 - x0) / W, (y1 - y0) / H)
                if exp[0] != r[0] or max(abs(a - b) for a, b in zip(exp[1:], r[1:])) > 1e-5:
                    errs.append(f'{d}: {s} 標註與 meta 不一致 {r} vs {exp}')
            for o in m['objects']:
                if 'inside_proj' in o:
                    stats['proj_checked'] += 1
                    if not o['inside_proj']:
                        errs.append(f'{d}: {s} 物件 {o["id"]}({o["name"]}) 遮罩框 {o["mask_bbox"]} 超出投影框 {o["proj_bbox"]}')
                elif o.get('labeled'):
                    stats['proj_skipped'] += 1  # 有頂點在鏡頭後方（通常是很靠近鏡頭的閘門），投影不能當上界
                if not o.get('labeled'):
                    stats['unlabeled'][o['cls']] += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dirs', nargs='+')
    ap.add_argument('--nc', type=int, default=7)
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    errs = []
    stats = dict(images=0, empty=0, meta=0, proj_checked=0, proj_skipped=0,
                 boxes=Counter(), area=Counter(), unlabeled=Counter())
    for d in a.dirs:
        check_dir(d, a.nc, errs, stats)
    print(f'圖 {stats["images"]} 張（空標註 {stats["empty"]}），框 {sum(stats["boxes"].values())} 個')
    for c in range(a.nc):
        n = stats['boxes'][c]
        avg = stats['area'][c] / n * W * H if n else 0
        print(f'  {c} {NAMES[c] if c < len(NAMES) else c:<9} {n:5d} 框  平均面積 {avg:7.0f} 像素'
              + (f'  （另有 {stats["unlabeled"][c]} 個看不到或太小，沒標）' if stats['meta'] else ''))
    if stats['meta']:
        bad = sum('超出投影框' in e for e in errs)
        print(f'投影交叉驗證：檢查 {stats["proj_checked"]} 個物件，{bad} 個失敗；'
              f'{stats["proj_skipped"]} 個標註物件因頂點在鏡頭後方而略過')
    print(f'錯誤 {len(errs)} 個')
    for e in errs[:50]:
        print('  ' + e)
    if a.json:
        out = dict(stats, boxes=dict(stats['boxes']), area=dict(stats['area']), unlabeled=dict(stats['unlabeled']),
                   errors=errs)
        json.dump(out, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    sys.exit(1 if errs else 0)


if __name__ == '__main__':
    main()
