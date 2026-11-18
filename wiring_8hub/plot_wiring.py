"""畫 8 台 HUB／18 塊 OLED 的平面接線圖（俯視，北在上）。用法：python plot_wiring.py <wiring_8hub.json> <輸出.png>"""
import json, sys, math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon
from matplotlib import font_manager

for f in ("Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Sans CJK SC"):
    if any(f in x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f; break
plt.rcParams["axes.unicode_minus"] = False

R = json.load(open(sys.argv[1], encoding="utf-8")); OUTP = sys.argv[2]
SEAT_C = {"N": "#d6453d", "E": "#2e9e4f", "S": "#d9a400", "W": "#8a4fd1"}
D = {"N": (0, 1), "E": (1, 0), "S": (0, -1), "W": (-1, 0)}
ROOM = {1: 85.5, 2: 88.0}            # 四角房間塊延伸到 ±85.5（1F）／±88（2F）
WIN = R["checks"]["seat_windows"]

def rot(seat, x, y):
    a = {"N": 0, "E": -90, "S": 180, "W": 90}[seat]; c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return (c * x - s * y, s * x + c * y)

fig, axes = plt.subplots(1, 2, figsize=(17, 8.9), dpi=130)
for ax, fl in zip(axes, (1, 2)):
    ax.set_aspect("equal"); ax.set_xlim(-150, 150); ax.set_ylim(-150, 150)
    ax.add_patch(Rectangle((-122.5, -122.5), 245, 245, fill=False, lw=1.5, ec="#333"))
    for sx in (-1, 1):
        for sy in (-1, 1):
            r0 = ROOM[fl]
            ax.add_patch(Rectangle((min(sx * 60, sx * r0), min(sy * 60, sy * r0)), abs(r0 - 60), abs(r0 - 60), fc="#e9e6df", ec="#bbb", lw=0.6))
            ax.add_patch(Rectangle((sx * 80.5 - 6, sy * 80.5 - 6), 12, 12, fc="#c9c3b5", ec="none"))   # 設備層支撐柱
    for seat in "NESW":
        pts = [rot(seat, x, y) for x, y in ((-29.5, 47), (29.5, 47), (29.5, 144.5), (-29.5, 144.5))]
        ax.add_patch(Polygon(pts, closed=True, fc=SEAT_C[seat] + "22", ec=SEAT_C[seat], lw=1.3))
        hub = [rot(seat, x, y) for x, y in ((-13.5, 52.6), (13.5, 52.6), (13.5, 91.1), (-13.5, 91.1))]
        ax.add_patch(Polygon(hub, closed=True, fc="#1f6b4a", ec="#0d3d29", lw=0.8, alpha=0.85))
        cx, cy = rot(seat, 0, 72); ax.text(cx, cy, f"HUB {fl}{seat}", ha="center", va="center", color="white", fontsize=8, rotation=0, weight="bold")
        w = WIN[f"{fl}{seat}"]; lo, hi = w["lo"], w["hi"]
        ax.add_patch(Rectangle((lo[0], lo[1]), hi[0] - lo[0], hi[1] - lo[1], fc="#ff7f0e", ec="#b35500", lw=0.8))
        iw = [rot(seat, x, y) for x, y in ((-24, 46), (24, 46), (24, 48), (-24, 48))]
        ax.add_patch(Polygon(iw, closed=True, fc="#57a0d3", ec="#2b6a99", lw=0.6))
    for o in [o for o in R["oleds"] if o["floor"] == fl]:
        cx, cy = o["center"]; ux, uy = D[o["up"]]; rx, ry = uy, -ux   # 從上往下看：模組朝下，排針側 = up
        hw, hh = 27.8 / 2, 27.3 / 2
        corners = [(cx + a * rx * hw + b * ux * hh, cy + a * ry * hw + b * uy * hh) for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        col = SEAT_C[o["hub"][1]]
        ax.add_patch(Polygon(corners, closed=True, fc="#11131a", ec=col, lw=1.4, alpha=0.9))
        sx, sy = o["slot"]; horiz = ux == 0      # 長條孔沿排針那條邊（與 up 垂直）
        ax.add_patch(Rectangle((sx - (5.7 if horiz else 1.7), sy - (1.7 if horiz else 5.7)), 11.4 if horiz else 3.4, 3.4 if horiz else 11.4, fc="white", ec="black", lw=0.5))
        path = o["path"]; xs = [sx] + [p[0] for p in path]; ys = [sy] + [p[1] for p in path]
        ax.plot(xs, ys, color=col, lw=3.2, solid_capstyle="round", alpha=0.95)
        lab = f"{o['id']}\n{'Wire' if o['bus'] == 'Wire0' else 'Wire1'} {o['addr']}\n{o['len']['total']:.0f} mm"
        ax.text(cx, cy, lab, ha="center", va="center", fontsize=6.6, color="white")
        if o.get("shift"):
            ax.annotate(f"比 1F 外移 {math.hypot(*o['shift']):.2f} mm", (cx, cy), xytext=(cx * 1.08, cy * 1.27), fontsize=6.5, color="#b00020",
                        arrowprops=dict(arrowstyle="-", color="#b00020", lw=0.6), ha="center")
    ax.set_title(f"{fl}F　9 塊 OLED → 4 台鏡頭 HUB（每塊 4 條 20 cm 母－公線）", fontsize=11)
    ax.set_xticks(range(-150, 151, 50)); ax.set_yticks(range(-150, 151, 50)); ax.grid(lw=0.3, alpha=0.4)
    ax.text(-147, 143, "北 ↑", fontsize=9)
fig.text(0.5, 0.015, "設備層俯視（封孔板頂面 z 117.6 以上；2F 加 150 mm）。深色方塊＝OLED（字＝匯流排、位址、單條線需要長度），白條＝長條孔，粗線＝線排路徑；"
         "橘色＝本次新開的麵包板座側窗（角落線進座），藍色＝座朝中心的既有窗口（十字臂、中心線進座）；綠色＝HUB 板。",
         ha="center", fontsize=8.5)
plt.tight_layout(rect=(0, 0.03, 1, 1)); plt.savefig(OUTP); print("saved", OUTP)
