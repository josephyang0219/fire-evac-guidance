import json, sys, base64, os, glob
seq = json.load(open(sys.argv[1]))
imgdir = sys.argv[2] if len(sys.argv) > 2 else None
images = {}
if imgdir:
    for k in range(len(seq)):
        for p in glob.glob(os.path.join(imgdir, f"step{k}", "F*_*.jpg")):
            fl, cam = os.path.basename(p)[1:-4].split("_")
            images[f"{k}:{fl}{cam}"] = "data:image/jpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()
for s in seq:
    s.pop("dist", None)
html = open(os.path.join(os.path.dirname(__file__), "static", "index.html"), encoding="utf-8").read()
inject = "<script>window.__EMBED__=" + json.dumps({"seq": seq, "images": images}, ensure_ascii=False) + ";</script>\n"
i = html.index("<script>")
open(sys.argv[3] if len(sys.argv) > 3 else "replay.html", "w", encoding="utf-8").write(html[:i] + inject + html[i:])
print("ok", len(images))
