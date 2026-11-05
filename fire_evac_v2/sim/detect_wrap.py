import sys, os
Y = "/tmp/claude-0/-home-claude/864ac11e-cc7b-56b0-b783-94d888562689/scratchpad/train/yolov7"
sys.path.insert(0, Y)
import torch
_tl = torch.load
torch.load = lambda *a, **k: _tl(*a, **{**k, "weights_only": False})
import numpy as np, cv2
from models.experimental import attempt_load
from utils.general import non_max_suppression
from utils.datasets import letterbox

_model = None


def load(w):
    global _model
    _model = attempt_load(w, map_location="cpu").eval()
    return _model


def detect(path, conf=0.35, iou=0.45, size=416):
    img0 = cv2.imread(path)
    H, W = img0.shape[:2]
    img, ratio, (dw, dh) = letterbox(img0, size, stride=32, auto=False)
    x = torch.from_numpy(img[:, :, ::-1].transpose(2, 0, 1).copy()).float()[None] / 255.0
    with torch.no_grad():
        pred = _model(x)[0]
    det = non_max_suppression(pred, conf, iou)[0]
    out = []
    for *xyxy, c, cls in det.tolist():
        x0 = (xyxy[0] - dw) / ratio[0]; x1 = (xyxy[2] - dw) / ratio[0]
        y0 = (xyxy[1] - dh) / ratio[1]; y1 = (xyxy[3] - dh) / ratio[1]
        x0, x1 = max(0, x0), min(W, x1); y0, y1 = max(0, y0), min(H, y1)
        out.append((int(cls), (x0 + x1) / 2 / W, (y0 + y1) / 2 / H, (x1 - x0) / W, (y1 - y0) / H, round(c, 3)))
    return out
