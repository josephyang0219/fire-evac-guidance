# -*- coding: utf-8 -*-
"""小規模 7 類補訓（可行性評估，2026-11-18）：在有 NVIDIA GPU 的 Windows 電腦上一個階段一個階段跑。

  python small_retrain_pc.py setup            下載腳本／權重／yolov7、安裝套件、修 yolov7 相容性
  python small_retrain_pc.py render  [N] [E]  用 Blender（OptiX）渲染 N 張有目標物＋E 張空場景（預設 600＋80）
  python small_retrain_pc.py dataset          合併、切 train/val
  python small_retrain_pc.py train   [EP]     從 6 類 best.pt 微調成 7 類（預設 40 輪）
  python small_retrain_pc.py eval             各類 AP、人偶依大小的召回率、舊 6 類有沒有退步

工作資料夾 %USERPROFILE%\\fire_retrain7（英文路徑）。渲染來源用 GitHub 的
model_oled_ceiling/fire_model_oled_through_hole.blend（閘門已是 94 mm），複製成 fire_model_dr.blend 後才給 Blender。
"""
import sys, os, subprocess, urllib.request, zipfile, shutil, re, glob, json, time
sys.stdout.reconfigure(errors="replace")
WORK = os.path.join(os.path.expanduser("~"), "fire_retrain7")
RAW = "https://raw.githubusercontent.com/josephyang0219/fire-evac-guidance/claude/8hub-18oled-wiring/"
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
PY = sys.executable
FILES = {
    "retrain/render/dr_render.py": "scripts/dr_render.py",
    "retrain/tools/make_dataset.py": "scripts/make_dataset.py",
    "retrain/tools/check_labels.py": "scripts/check_labels.py",
    "retrain/config/yolov7-tiny-fire7.yaml": "cfg/yolov7-tiny-fire7.yaml",
    "retrain/config/hyp.ft7.yaml": "cfg/hyp.ft7.yaml",
    "model/weights/best.pt": "weights/best6.pt",
    "model_oled_ceiling/fire_model_oled_through_hole.blend": "fire_model_dr.blend",
}
CLASSES = ["cabinet", "boxes", "furniture", "rubble", "gate", "smoke", "person"]

def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)

def sh(cmd, cwd=None, env=None, logf=None):
    log("RUN", " ".join(map(str, cmd)))
    with open(logf, "a", encoding="utf-8", errors="replace") if logf else open(os.devnull, "w") as lf:
        p = subprocess.run(cmd, cwd=cwd, env=env, stdout=lf if logf else None, stderr=subprocess.STDOUT if logf else None)
    if p.returncode: raise SystemExit(f"失敗（{p.returncode}）：{cmd[:3]}")

def setup():
    os.makedirs(WORK, exist_ok=True)
    for src, dst in FILES.items():
        d = os.path.join(WORK, dst); os.makedirs(os.path.dirname(d), exist_ok=True)
        urllib.request.urlretrieve(RAW + src, d); log("got", dst, os.path.getsize(d))
    y7 = os.path.join(WORK, "yolov7")
    if not os.path.isdir(y7):
        z = os.path.join(WORK, "yolov7.zip")
        urllib.request.urlretrieve("https://codeload.github.com/WongKinYiu/yolov7/zip/refs/heads/main", z)
        zipfile.ZipFile(z).extractall(WORK); os.rename(os.path.join(WORK, "yolov7-main"), y7)
    def patch(pattern, repl, files):
        n = 0
        for p in files:
            s = open(p, encoding="utf-8").read(); s2, k = re.subn(pattern, repl, s)
            if k: open(p, "w", encoding="utf-8").write(s2); n += k
        return n
    py = glob.glob(os.path.join(y7, "*.py")) + glob.glob(os.path.join(y7, "utils", "*.py")) + glob.glob(os.path.join(y7, "models", "*.py"))
    loss = os.path.join(y7, "utils", "loss.py")
    log("patch np.int", patch(r"np\.int\b", "int", py), "np.float", patch(r"np\.float\b", "float", py),
        "loss device", patch(r'torch\.zeros_like\(cost, device="cpu"\)', "torch.zeros_like(cost)", [loss]),
        "clamp", patch(r"gj\.clamp_\(0, gain\[3\] - 1\), gi\.clamp_\(0, gain\[2\] - 1\)",
                       "gj.clamp_(0, gain[3].long() - 1), gi.clamp_(0, gain[2].long() - 1)", [loss]))
    sh([PY, "-m", "pip", "install", "-q", "opencv-python", "matplotlib", "pyyaml", "scipy", "tqdm", "seaborn", "pandas", "requests"],
       logf=os.path.join(WORK, "setup.log"))
    log("setup done")

def render(n=600, e=80):
    os.makedirs(os.path.join(WORK, "logs"), exist_ok=True)
    blend = os.path.join(WORK, "fire_model_dr.blend"); scr = os.path.join(WORK, "scripts", "dr_render.py")
    for args, tag in (([ "--count", str(n), "--seed", "101", "--out", os.path.join(WORK, "out", "dr_s101"), "--skip-existing"], "dr"),
                      (["--count", str(e), "--seed", "102", "--mode", "empty", "--prefix", "empty", "--out", os.path.join(WORK, "out", "empty_s102"), "--skip-existing"], "empty")):
        sh([BLENDER, "-b", blend, "--python", scr, "--"] + args, logf=os.path.join(WORK, "logs", f"render_{tag}.log"))
    log("render done")

def dataset():
    ds = os.path.join(WORK, "ds7")
    sh([PY, os.path.join(WORK, "scripts", "make_dataset.py"), "--out", ds, "--work", WORK, "--src", "out/dr_s101", "--src", "out/empty_s102",
        "--val", "0.2", "--colab-path", ds.replace("\\", "/")], logf=os.path.join(WORK, "logs", "dataset.log"))
    log(open(os.path.join(WORK, "logs", "dataset.log"), encoding="utf-8", errors="replace").read()[-400:])

def train(ep=40):
    y7 = os.path.join(WORK, "yolov7"); env = dict(os.environ, TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="1", PYTHONIOENCODING="utf-8")
    sh([PY, "train.py", "--device", "0", "--workers", "2", "--batch-size", "16", "--data", os.path.join(WORK, "ds7", "data.yaml"),
        "--img", "576", "576", "--cfg", os.path.join(WORK, "cfg", "yolov7-tiny-fire7.yaml"), "--hyp", os.path.join(WORK, "cfg", "hyp.ft7.yaml"),
        "--weights", os.path.join(WORK, "weights", "best6.pt"), "--epochs", str(ep), "--project", os.path.join(WORK, "runs"),
        "--name", "small7", "--exist-ok", "--cache-images"], cwd=y7, env=env, logf=os.path.join(WORK, "logs", "train.log"))
    log("train done")

def evaluate():
    y7 = os.path.join(WORK, "yolov7"); env = dict(os.environ, TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="1", PYTHONIOENCODING="utf-8")
    w = os.path.join(WORK, "runs", "small7", "weights", "best.pt")
    lf = os.path.join(WORK, "logs", "eval.log")
    if os.path.exists(lf): os.remove(lf)
    sh([PY, "test.py", "--data", os.path.join(WORK, "ds7", "data.yaml"), "--img", "576", "--batch", "16", "--conf", "0.001", "--iou", "0.65",
        "--weights", w, "--task", "val", "--verbose", "--project", os.path.join(WORK, "runs"), "--name", "small7_val", "--exist-ok"],
       cwd=y7, env=env, logf=lf)
    # 人偶依框高（像素）分組的召回率、各類在 conf 0.4 的 precision/recall（上板門檻）
    code = r'''
import sys, os, glob, json, torch, numpy as np, cv2
sys.path.insert(0, os.getcwd())
from models.experimental import attempt_load
from utils.general import non_max_suppression, xywh2xyxy, box_iou
from utils.datasets import letterbox
W, DS = sys.argv[1], sys.argv[2]
m = attempt_load(W, map_location="cuda").eval()
bins = [(0, 12), (12, 20), (20, 30), (30, 45), (45, 1000)]
hit = {b: [0, 0] for b in bins}; tp = [0]*7; fp = [0]*7; fn = [0]*7
for ip in sorted(glob.glob(os.path.join(DS, "images", "val", "*"))):
    im0 = cv2.imread(ip); h0, w0 = im0.shape[:2]
    im = letterbox(im0, 576, stride=32, auto=False)[0][:, :, ::-1].transpose(2, 0, 1).copy()
    t = torch.from_numpy(im).float().cuda()[None] / 255
    with torch.no_grad(): det = non_max_suppression(m(t)[0], 0.4, 0.5)[0].cpu()
    r = min(576 / h0, 576 / w0); pw, ph = (576 - w0 * r) / 2, (576 - h0 * r) / 2
    if len(det): det[:, [0, 2]] = (det[:, [0, 2]] - pw) / r; det[:, [1, 3]] = (det[:, [1, 3]] - ph) / r
    lab = np.loadtxt(ip.replace("images", "labels").rsplit(".", 1)[0] + ".txt", ndmin=2).reshape(-1, 5)
    g = torch.tensor(lab); gb = xywh2xyxy(g[:, 1:]) * torch.tensor([w0, h0, w0, h0]) if len(g) else torch.zeros((0, 4))
    used = set()
    for k in range(len(g)):
        c = int(g[k, 0]); best = None
        for j in range(len(det)):
            if j in used or int(det[j, 5]) != c: continue
            iou = box_iou(gb[k:k+1], det[j:j+1, :4])[0, 0].item()
            if iou >= 0.5 and (best is None or iou > best[1]): best = (j, iou)
        if best: used.add(best[0]); tp[c] += 1
        else: fn[c] += 1
        if c == 6:
            hpx = (gb[k, 3] - gb[k, 1]).item()
            for b in bins:
                if b[0] <= hpx < b[1]: hit[b][1] += 1; hit[b][0] += 1 if best else 0
    for j in range(len(det)):
        if j not in used: fp[int(det[j, 5])] += 1
print(json.dumps({"person_recall_by_height_px": {f"{a}-{b}": h for (a, b), h in hit.items()},
                  "at_conf_0.4": {n: dict(tp=tp[i], fp=fp[i], fn=fn[i]) for i, n in enumerate(["cabinet","boxes","furniture","rubble","gate","smoke","person"])}}))
'''
    open(os.path.join(y7, "size_eval.py"), "w", encoding="utf-8").write(code)
    sh([PY, "size_eval.py", w, os.path.join(WORK, "ds7")], cwd=y7, env=env, logf=lf)
    log(open(lf, encoding="utf-8", errors="replace").read()[-3500:])

if __name__ == "__main__":
    st = sys.argv[1]; a = [int(x) for x in sys.argv[2:]]
    {"setup": setup, "render": render, "dataset": dataset, "train": train, "eval": evaluate}[st](*a)
