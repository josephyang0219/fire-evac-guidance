# -*- coding: utf-8 -*-
"""YOLOv7-tiny 重參數化：把訓練版（IDetect，含 ImplicitA / ImplicitM）合併成部署版（Detect）。

在 Colab 的 yolov7 資料夾裡執行（需要 repo 的 models/、utils/）：
    python reparam.py --weights runs/train/fire7/weights/best.pt \
        --cfg cfg/fire7/yolov7-tiny-fire7-deploy.yaml --out best_reparam.pt

IDetect 每個輸出層算的是  y = im * (W · (x + ia) + b)
展開後等於一般卷積      y = (im·W) · x + im·(b + W·ia)
所以新權重 W' = im·W、新偏差 b' = im·(b + Σ W·ia)，Detect 層換上 W'、b' 就和原本完全等價。
最後用隨機輸入（1×3×320×576，和板子一樣）比對兩個模型的輸出，差異要 < 1e-3 才存檔。
"""
import argparse, os
from copy import deepcopy

os.environ.setdefault('TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD', '1')  # PyTorch ≥ 2.6 預設 weights_only=True
import torch
from models.yolo import Model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--weights', required=True)
    ap.add_argument('--cfg', required=True, help='部署版 yaml（最後一層是 Detect）')
    ap.add_argument('--out', default='best_reparam.pt')
    a = ap.parse_args()

    ckpt = torch.load(a.weights, map_location='cpu', weights_only=False)
    train_m = (ckpt['model'] if ckpt.get('model') is not None else ckpt['ema']).float().eval()
    nc = train_m.nc
    dep = Model(a.cfg, ch=3, nc=nc).float().eval()
    sd, dsd = train_m.state_dict(), dep.state_dict()
    inter = {k: v for k, v in sd.items() if k in dsd and v.shape == dsd[k].shape}
    missing = [k for k in dsd if k not in inter]
    dep.load_state_dict(inter, strict=False)
    print(f'nc = {nc}, 複製 {len(inter)} 個張量，部署版待合併：{missing}')

    td, dd = train_m.model[-1], dep.model[-1]
    assert type(td).__name__ == 'IDetect' and type(dd).__name__ == 'Detect', (type(td), type(dd))
    with torch.no_grad():
        for i in range(td.nl):
            Wt, bt = td.m[i].weight, td.m[i].bias              # (na*(nc+5), C, 1, 1), (na*(nc+5),)
            ia = td.ia[i].implicit                             # (1, C, 1, 1)
            im = td.im[i].implicit.reshape(-1)                 # (na*(nc+5),)
            dd.m[i].weight.copy_(Wt * im.view(-1, 1, 1, 1))
            dd.m[i].bias.copy_((bt + (Wt * ia).sum(dim=(1, 2, 3))) * im)
    dep.names, dep.nc = train_m.names, nc

    x = torch.rand(1, 3, 320, 576)
    with torch.no_grad():
        y_t, y_d = train_m(x)[0], dep(x)[0]
    diff = (y_t - y_d).abs().max().item()
    print(f'訓練版 vs 部署版 最大差異 = {diff:.2e}（輸出形狀 {tuple(y_d.shape)}）')
    if diff > 1e-3:
        raise SystemExit('差異太大，沒有存檔：請確認 --cfg 是對應的 deploy yaml、nc 一致')

    torch.save({'model': deepcopy(dep).half(), 'optimizer': None, 'training_results': None, 'epoch': -1}, a.out)
    print(f'已存 {a.out}（{os.path.getsize(a.out) / 1e6:.1f} MB），類別：{dep.names}')


if __name__ == '__main__':
    main()
