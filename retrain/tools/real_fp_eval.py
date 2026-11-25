# -*- coding: utf-8 -*-
"""空場景誤判率（2026-11-25）：對中控台抓下來的實景快照跑 v6（7 類）與舊 6 類 best6.pt，場景裡沒有任何物件，所以任何偵測都算誤判。

    python real_fp_eval.py <yolov7 資料夾> <快照資料夾（<mac>/*.jpg）> <輸出資料夾>

快照用 fire_evac_v2/tools/capture_frames.py 從中控台抓。輸出 fp_summary.json（conf 0.25／0.4／0.6 的誤判張數比例、每類框數、每台）、
fp_raw.json、fp_examples.jpg（每台一張，左舊模型右 v6，conf ≥ 0.4）。權重路徑寫在 W（使用者電腦上的 fire_retrain7）。
"""
import sys, os, glob, json, torch, cv2, numpy as np, warnings; warnings.filterwarnings("ignore")
Y7, DATA, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, Y7); os.chdir(Y7)
from models.experimental import attempt_load
from utils.general import non_max_suppression
from utils.datasets import letterbox
W = {"v6": r"C:\Users\waipj\fire_retrain7\runs\small7_v6\weights\best.pt", "old6": r"C:\Users\waipj\fire_retrain7\weights\best6.pt"}
NAMES = ["櫃子", "紙箱", "桌椅", "瓦礫", "閘門", "煙", "人偶"]
EN = ["cabinet", "boxes", "furniture", "rubble", "gate", "smoke", "person"]
os.makedirs(OUT, exist_ok=True)
imgs = sorted(glob.glob(os.path.join(DATA, "*", "*.jpg")))
res = {}
for tag, wp in W.items():
    m = attempt_load(wp, map_location="cuda").eval()
    per = []
    for ip in imgs:
        im0 = cv2.imread(ip); h0, w0 = im0.shape[:2]
        im = letterbox(im0, 576, stride=32, auto=False)[0][:, :, ::-1].transpose(2, 0, 1).copy()
        t = torch.from_numpy(im).float().cuda()[None] / 255
        with torch.no_grad(): det = non_max_suppression(m(t)[0], 0.1, 0.5)[0].cpu().numpy()
        r = min(576 / h0, 576 / w0); pw, ph = (576 - w0 * r) / 2, (576 - h0 * r) / 2
        if len(det): det[:, [0, 2]] = (det[:, [0, 2]] - pw) / r; det[:, [1, 3]] = (det[:, [1, 3]] - ph) / r
        per.append(dict(file=os.path.relpath(ip, DATA), mac=os.path.basename(os.path.dirname(ip)), dets=det.tolist()))
    res[tag] = per
json.dump(res, open(os.path.join(OUT, "fp_raw.json"), "w"))
summary = {"n_images": len(imgs), "boards": sorted({p["mac"] for p in res["v6"]})}
for tag, per in res.items():
    for th in (0.25, 0.4, 0.6):
        frames = sum(1 for p in per if any(d[4] >= th for d in p["dets"]))
        cls = {}
        for p in per:
            for d in p["dets"]:
                if d[4] >= th: cls[EN[int(d[5])]] = cls.get(EN[int(d[5])], 0) + 1
        by = {}
        for p in per:
            b = by.setdefault(p["mac"][-4:], [0, 0]); b[1] += 1; b[0] += any(d[4] >= th for d in p["dets"])
        summary[f"{tag}@{th}"] = dict(frames_with_fp=frames, rate=round(frames / max(1, len(per)), 3), boxes=sum(cls.values()),
                                       per_frame=round(sum(cls.values()) / max(1, len(per)), 2), by_class=cls, by_board=by)
json.dump(summary, open(os.path.join(OUT, "fp_summary.json"), "w"), indent=1)
# 範例圖：每台各取一張，左舊模型右 v6（conf ≥ 0.4）
COL = [(32, 160, 240), (43, 130, 217), (98, 174, 47), (224, 102, 160), (253, 139, 61), (200, 179, 159), (122, 79, 255)]
macs = summary["boards"]
rows = []
for mac in macs:
    ks = [k for k, p in enumerate(res["v6"]) if p["mac"] == mac]; i = ks[len(ks) // 2]
    ip = os.path.join(DATA, res["v6"][i]["file"]); pair = []
    for tag in ("old6", "v6"):
        im = cv2.imread(ip)
        for d in res[tag][i]["dets"]:
            if d[4] < 0.4: continue
            c = int(d[5]); x0, y0, x1, y1 = map(int, d[:4])
            cv2.rectangle(im, (x0, y0), (x1, y1), COL[c], 2)
            cv2.putText(im, f"{EN[c]} {d[4]:.2f}", (x0 + 2, max(14, y0 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COL[c], 2)
        cv2.putText(im, ("OLD 6-class" if tag == "old6" else "v6 7-class") + f"  {mac[-4:]}", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        pair.append(cv2.resize(im, (480, 360)))
    rows.append(np.hstack(pair))
cv2.imwrite(os.path.join(OUT, "fp_examples.jpg"), np.vstack(rows))
print(json.dumps(summary, ensure_ascii=False))
