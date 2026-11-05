import json, os, sys, subprocess
import compose as C
from PIL import Image, ImageDraw

run = sys.argv[1]; seq = json.load(open(os.path.join(run, "sequence_det.json"), encoding="utf-8"))
JN = {"-1,1": "西北角", "0,1": "北口", "1,1": "東北角", "-1,0": "西口", "0,0": "中央", "1,0": "東口", "-1,-1": "西南角", "0,-1": "南口", "1,-1": "東南角"}
DN = {"N": "北", "S": "南", "E": "東", "W": "西", "DOWN": "下樓", "UP": "上樓", "X": "停"}
frames = []
for k, s in enumerate(seq):
    sd = os.path.join(run, f"step{k}")
    dets = {cid: [tuple(d) for d in v] for cid, v in s.get("dets", {}).items()}
    rows = []
    for g in sorted(s["segments"], key=lambda g: -g["risk"]):
        if g["risk"] < 0.05 and not g["unknown"]:
            continue
        name = f"{g['floor']}F {JN[','.join(map(str, g['a']))]}–{JN[','.join(map(str, g['b']))]}"
        tag = "封鎖" if g["gate"] else f"障礙 {int(g['rate'] * 100)}%"
        rows.append(f"{name}　{tag}　煙 {int(g['smoke'] * 100)}%" + ("　未確認" if g["unknown"] else ""))
    if not rows:
        rows = ["全部走廊暢通"]
    leds = "燈號　2F：" + " ".join(DN[s["leds"][f"2,{i},{j}"]] for j in (1, 0, -1) for i in (-1, 0, 1)) + "　｜　1F：" + " ".join(DN[s["leds"][f"1,{i},{j}"]] for j in (1, 0, -1) for i in (-1, 0, 1))
    out = os.path.join(run, f"frame{k}.png")
    C.frame(sd, s, dets, rows, leds, out)
    frames.append(out)


def card(path, title, sub):
    im = Image.new("RGB", (1920, 1080), C.BG); d = ImageDraw.Draw(im)
    d.text((960, 470), title, fill=C.FG, font=C.f(76, True), anchor="mm")
    d.text((960, 580), sub, fill=C.MUTED, font=C.f(34), anchor="mm")
    im.save(path); return path


intro = card(os.path.join(run, "intro.png"), "火災避難障礙物辨識系統", "模擬世界運作展示：YOLO 辨識 → 障礙率 → 最佳逃生路線 → LED 指引")
outro = card(os.path.join(run, "outro.png"), "下一步：實體模型 Demo", "同一套辨識模型與路徑演算法，燒錄到 HUB 8735 Ultra 上運作")
seqf = [(intro, 3)] + [(f, 4.5) for f in frames] + [(outro, 3)]
lst = os.path.join(run, "frames.txt")
with open(lst, "w") as fh:
    for p, d in seqf:
        fh.write(f"file '{os.path.abspath(p)}'\nduration {d}\n")
    fh.write(f"file '{os.path.abspath(seqf[-1][0])}'\n")
mp4 = os.path.join(run, "fire_evac_sim.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "20", mp4], check=True)
print(mp4)
