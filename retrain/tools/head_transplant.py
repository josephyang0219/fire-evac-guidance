# -*- coding: utf-8 -*-
"""把 6 類 best.pt 的偵測頭「搬」到 7 類模型上，當微調的起點（2026-11-18）。

為什麼：yolov7 的 train.py 從 6 類權重接 7 類時，偵測頭的輸出通道數不同（3×11 → 3×12），
整個偵測頭會被丟掉重學，舊 6 類學過的分類能力全部歸零。小資料、少輪數時舊類別就會掉很多。
這支程式把舊頭每個 anchor 的 11 列（x y w h obj + 6 類）複製到新頭對應的位置，只有第 7 類（person）是新的。
IDetect 的 ImplicitM（乘法隱式層，通道數也是 3×11）用同樣方式對應。

用法（在 yolov7 資料夾裡執行）：
  python head_transplant.py <6類 best.pt> <7類 cfg.yaml> <輸出.pt>
"""
import os, sys, torch
sys.path.insert(0, os.getcwd())
from models.yolo import Model

src, cfg, dst = sys.argv[1:4]
ck = torch.load(src, map_location="cpu", weights_only=False)
old = (ck.get("ema") or ck["model"]).float()
new = Model(cfg, ch=3, nc=7)
so, sn = old.state_dict(), new.state_dict()
det = new.model[-1]
na, no_o, no_n = det.na, 6 + 5, 7 + 5
rn = [a * no_n + k for a in range(na) for k in range(no_o)]
ro = [a * no_o + k for a in range(na) for k in range(no_o)]
n_same = n_head = 0; skipped = []
for k, v in sn.items():
    if k not in so:
        skipped.append(k); continue
    ov = so[k]
    if ov.shape == v.shape:
        sn[k] = ov.clone(); n_same += 1
    elif ov.dim() >= 1 and ov.shape[0] == na * no_o and v.shape[0] == na * no_n and ov.shape[1:] == v.shape[1:]:
        t = v.clone(); t[rn] = ov[ro]; sn[k] = t; n_head += 1          # 輸出卷積的 weight／bias
    elif ov.dim() == 4 and ov.shape[1] == na * no_o and v.shape[1] == na * no_n:
        t = v.clone(); t[:, rn] = ov[:, ro]; sn[k] = t; n_head += 1    # ImplicitM (1, C, 1, 1)
    else:
        skipped.append(f"{k} {tuple(ov.shape)}->{tuple(v.shape)}")
new.load_state_dict(sn)
new.names = ["cabinet", "boxes", "furniture", "rubble", "gate", "smoke", "person"]
torch.save({"epoch": -1, "best_fitness": None, "training_results": None, "model": new.half(),
            "ema": None, "updates": None, "optimizer": None, "wandb_id": None}, dst)
print(f"相同形狀直接複製 {n_same} 個；偵測頭對應複製 {n_head} 個；沒複製 {len(skipped)} 個：{skipped[:8]}")
