# -*- coding: utf-8 -*-
"""Blender 啟動器（只用 Python 標準函式庫，系統 Python 3 就能跑）。

做三件事，確保「原檔不改、傳給 Blender 的路徑全是英文」：
  1. 把 實體模型檔案/fire_model.blend 複製成 <work>/fire_model_dr.blend（原檔變了才重新複製）
  2. 把 retrain/ 底下的 Blender 腳本複製到 <work>/scripts/
  3. 用背景模式執行 Blender，log 存到 <work>/logs/，只印最後幾行

<work> 預設 %USERPROFILE%\\fire_retrain，必須是英文路徑。

用法（在 repo 根目錄）：
  python retrain/tools/run_blender.py render  --count 200 --seed 1           # 有目標物的渲染
  python retrain/tools/run_blender.py empty   --count 100 --seed 2           # 空場景負樣本
  python retrain/tools/run_blender.py preview --src out/dr_s001 --n 5        # 疊框預覽圖
  python retrain/tools/run_blender.py negatives --src D:\\教室照片 --name classroom
render/empty/preview 的 --out、--src 是 <work> 底下的相對路徑（預設 out/dr_s<seed>）。
"""
import sys as _sys
_sys.stdout.reconfigure(errors='replace')  # Windows 主控台是 cp950，印不出的字元用 ? 代替
import argparse, hashlib, os, shutil, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RETRAIN = os.path.join(REPO, 'retrain')
DEFAULT_BLENDER = r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
SCRIPTS = {'render': 'render/dr_render.py', 'empty': 'render/dr_render.py',
           'preview': 'render/draw_preview.py', 'negatives': 'negatives/prepare_negatives.py'}
IMG_EXT = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp')


def find_original_blend():
    # worktree 裡沒有這個檔（沒進 git），往上找主資料夾的 實體模型檔案/
    d = REPO
    for _ in range(6):
        p = os.path.join(d, '實體模型檔案', 'fire_model.blend')
        if os.path.isfile(p):
            return p
        d = os.path.dirname(d)
    raise SystemExit('找不到 實體模型檔案/fire_model.blend，請用 --blend 指定')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def ensure_ascii(path, what):
    if not path.isascii():
        raise SystemExit(f'{what} 必須是英文路徑：{path}')


def prepare_copy(orig, work):
    copy = os.path.join(work, 'fire_model_dr.blend')
    stamp = copy + '.source_sha256'
    src_hash = sha256(orig)
    if not (os.path.isfile(copy) and os.path.isfile(stamp) and open(stamp).read().strip() == src_hash):
        shutil.copy2(orig, copy)
        with open(stamp, 'w') as f:
            f.write(src_hash + '\n')
        print(f'[run] 已複製原檔 → {copy}')
    return copy, src_hash


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=sorted(SCRIPTS))
    ap.add_argument('--work', default=os.path.join(os.path.expanduser('~'), 'fire_retrain'))
    ap.add_argument('--blender', default=DEFAULT_BLENDER)
    ap.add_argument('--blend', default=None, help='原始 .blend（預設自動找 實體模型檔案/fire_model.blend）')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--count', type=int, default=200)
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--out', default=None)
    ap.add_argument('--src', default=None)
    ap.add_argument('--n', type=int, default=5)
    ap.add_argument('--name', default='classroom')
    ap.add_argument('--skip-existing', action='store_true')
    ap.add_argument('--samples', type=int, default=32)
    a, extra = ap.parse_known_args()

    work = os.path.abspath(a.work)
    ensure_ascii(work, '工作資料夾 --work')
    for d in ('scripts', 'logs', 'out'):
        os.makedirs(os.path.join(work, d), exist_ok=True)
    for rel in set(SCRIPTS.values()):
        dst = os.path.join(work, 'scripts', os.path.basename(rel))
        shutil.copy2(os.path.join(RETRAIN, rel), dst)
    script = os.path.join(work, 'scripts', os.path.basename(SCRIPTS[a.cmd]))

    blend_args, sargs = [], []
    orig, orig_hash = None, None
    if a.cmd in ('render', 'empty'):
        orig = os.path.abspath(a.blend) if a.blend else find_original_blend()
        copy, orig_hash = prepare_copy(orig, work)
        out = os.path.join(work, a.out or f'out/{"empty" if a.cmd == "empty" else "dr"}_s{a.seed:03d}')
        blend_args = [copy]
        sargs = ['--out', out, '--count', str(a.count), '--start', str(a.start), '--seed', str(a.seed),
                 '--samples', str(a.samples), '--prefix', 'empty' if a.cmd == 'empty' else 'dr']
        if a.cmd == 'empty':
            sargs += ['--mode', 'empty']
        if a.skip_existing:
            sargs.append('--skip-existing')
    elif a.cmd == 'preview':
        src = os.path.join(work, a.src or f'out/dr_s{a.seed:03d}')
        sargs = ['--src', src, '--out', os.path.join(src, 'preview'), '--n', str(a.n)]
    elif a.cmd == 'negatives':
        if not a.src:
            raise SystemExit('negatives 需要 --src <照片資料夾>')
        # 照片資料夾可能有中文：先複製成英文檔名到 <work>/neg_src/<name>/
        stage = os.path.join(work, 'neg_src', a.name)
        ensure_ascii(stage, '暫存資料夾')
        os.makedirs(stage, exist_ok=True)
        n, names = 0, []
        for root, _, files in os.walk(a.src):
            for fn in sorted(files):
                if fn.lower().endswith(IMG_EXT):
                    full = os.path.join(root, fn)
                    h = sha256(full)[:16]
                    shutil.copy2(full, os.path.join(stage, f'{h}{os.path.splitext(fn)[1].lower()}'))
                    names.append(f'{h},{os.path.relpath(full, a.src)}')
                    n += 1
        with open(os.path.join(stage, 'source_names.csv'), 'w', encoding='utf-8') as f:  # hash → 原始檔名
            f.write('hash,original\n' + '\n'.join(names) + '\n')
        print(f'[run] 已暫存 {n} 張照片 → {stage}')
        sargs = ['--src', stage, '--out', os.path.join(work, a.out or f'out/neg_{a.name}'), '--name', a.name]
    sargs += extra

    cmd = [a.blender, '-b'] + blend_args + ['--python-exit-code', '1', '-P', script, '--'] + sargs
    for c in cmd[1:]:
        ensure_ascii(c, 'Blender 參數')
    log = os.path.join(work, 'logs', f'{a.cmd}_{time.strftime("%Y%m%d_%H%M%S")}.log')
    print('[run]', ' '.join(f'"{c}"' if ' ' in c else c for c in cmd))
    print('[run] log →', log)
    with open(log, 'w', encoding='utf-8', errors='replace') as f:
        rc = subprocess.call(cmd, stdout=f, stderr=subprocess.STDOUT)
    with open(log, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    errs = [l for l in lines if 'Error' in l or 'Traceback' in l]
    print(''.join(lines[-8:]))
    if errs:
        print('[run] log 裡的錯誤行：\n' + ''.join(errs[:20]))
    if orig and sha256(orig) != orig_hash:
        print('[run] 警告：原檔在執行期間被改過！')
    sys.exit(rc)


if __name__ == '__main__':
    main()
