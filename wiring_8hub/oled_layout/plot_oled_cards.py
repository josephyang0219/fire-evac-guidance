"""18 塊天花板 OLED 的個別位置配置圖（8 台鏡頭 HUB 方案，資料來自交接 repo wiring_8hub/wiring_8hub.json）。
用法：python plot_oled_cards.py <wiring_8hub.json> <輸出資料夾>
輸出：OLED個別配置_1F.png、OLED個別配置_2F.png、OLED個別配置表.md
座標：俯視（從設備層往下看），北在上，原點＝樓層中心（十字路口中心），單位 mm。
"""
import json, sys, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle, FancyArrow

for f in ("Noto Sans CJK TC", "Microsoft JhengHei", "Microsoft YaHei"):
    if any(f in x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break
plt.rcParams["axes.unicode_minus"] = False

MOD_ACROSS, MOD_ALONG = 27.8, 27.3     # 模組：垂直於「畫面上緣」方向 27.8、沿上緣方向 27.3（排針在上緣）
SLOT_L, SLOT_W = 11.4, 3.4             # 長條孔
HDR_OFF = 12.0                         # 排針中心離模組中心
DIRV = {"N": (0, 1), "E": (1, 0), "S": (0, -1), "W": (-1, 0)}
DIRZH = {"N": "北", "E": "東", "S": "南", "W": "西"}
GRID = {"NW": (0, 0), "N": (0, 1), "NE": (0, 2), "W": (1, 0), "C": (1, 1), "E": (1, 2), "SW": (2, 0), "S": (2, 1), "SE": (2, 2)}
NAMEZH = {"NW": "西北角", "N": "北臂中點", "NE": "東北角", "W": "西臂中點", "C": "中心", "E": "東臂中點",
          "SW": "西南角", "S": "南臂中點", "SE": "東南角"}
HUBCOL = {"N": "#d64541", "E": "#2e9e55", "S": "#d4a017", "W": "#8e55d6"}


def bus_txt(o):
    return {"Wire0": "Wire（Pin3/4）", "Wire1": "Wire1（Pin0/1）", "Soft": "軟體 I²C（Pin18/19）"}[o["bus"]]


def wire_cm(o):
    return 10 if o["entry"] == "inner" and o["id"] != "C" else 20


def card(ax, o):
    cx, cy = o["center"]
    ux, uy = DIRV[o["up"]]
    px, py = -uy, ux                       # 垂直方向
    hub_seat = o["hub"][1]
    col = HUBCOL[hub_seat]
    R = 26
    ax.set_xlim(cx - R, cx + R); ax.set_ylim(cy - R, cy + R); ax.set_aspect("equal")
    ax.grid(True, lw=0.3, alpha=0.5)
    # 模組外框
    w = MOD_ACROSS * abs(px) + MOD_ALONG * abs(ux)
    h = MOD_ACROSS * abs(py) + MOD_ALONG * abs(uy)
    ax.add_patch(Rectangle((cx - w / 2, cy - h / 2), w, h, fc="#23262d", ec=col, lw=2.2))
    # 顯示區（示意，約 23×12，偏下緣）
    dw = 23 * abs(px) + 12 * abs(ux); dh = 23 * abs(py) + 12 * abs(uy)
    dcx, dcy = cx - ux * 2.5, cy - uy * 2.5
    ax.add_patch(Rectangle((dcx - dw / 2, dcy - dh / 2), dw, dh, fc="#3a6ea5", ec="none", alpha=0.75))
    # 長條孔（排針）
    sx, sy = o["slot"]
    sw = SLOT_L * abs(px) + SLOT_W * abs(ux); shh = SLOT_L * abs(py) + SLOT_W * abs(uy)
    ax.add_patch(Rectangle((sx - sw / 2, sy - shh / 2), sw, shh, fc="white", ec="black", lw=0.8))
    # 畫面上緣箭頭
    ax.add_patch(FancyArrow(dcx - ux * 4, dcy - uy * 4, ux * 7, uy * 7, width=1.0, head_width=3.2, head_length=2.6, color="white"))
    # 中心十字
    ax.plot([cx], [cy], marker="+", color="#ff5252", ms=9, mew=1.5)
    title = f"{o['oid']}　{NAMEZH[o['id']]}　J{'2' if o['floor'] == 2 else ''}({o['J'][0]},{o['J'][1]})"
    ax.set_title(title, fontsize=9.5, color=col, weight="bold")
    info = (f"中心 ({cx:g}, {cy:g})・長條孔中心 ({sx:g}, {sy:g})\n"
            f"HUB {o['hub']}・{bus_txt(o)}・{o['addr']}\n"
            f"畫面上緣（排針）朝{DIRZH[o['up']]}・線 {wire_cm(o)} cm × 4"
            + (f"\n比 1F 外移 {abs(o['shift'][0]) + abs(o['shift'][1]):g} mm" if o.get("shift") else ""))
    ax.text(0.5, -0.08, info, transform=ax.transAxes, ha="center", va="top", fontsize=7.4)
    ax.tick_params(labelsize=6)


def floor_fig(oleds, fl, out):
    fig, axs = plt.subplots(3, 3, figsize=(12, 14))
    for o in oleds:
        r, c = GRID[o["id"]]
        card(axs[r][c], o)
    fig.suptitle(f"{fl}F　9 塊 OLED 個別位置（俯視、北在上，原點＝樓層中心，mm）", fontsize=14, weight="bold")
    fig.text(0.5, 0.012,
             "深色＝OLED 模組 27.8×27.3（外框色＝負責的 HUB：N 紅、E 綠、S 黃、W 紫）；藍＝顯示區示意；白箭頭＝畫面上緣（排針那一側）；"
             "白框＝天花板長條孔 11.4×3.4。\n座標是從設備層往下看。人在房間裡往上看時左右相反，但「畫面上緣朝哪個方位」不變。"
             "OLED 尺寸是標稱值，量實物後若不同要回報。", ha="center", fontsize=8.5)
    fig.tight_layout(rect=(0, 0.04, 1, 0.97), h_pad=6.5)
    fig.savefig(out, dpi=130)
    plt.close(fig)


def main():
    src, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    d = json.load(open(src, encoding="utf-8"))
    rows = ["| OLED | 路口 | 位置 | 模組中心 (x, y) | 長條孔中心 (x, y) | 畫面上緣朝 | HUB | 匯流排 | 位址 | 杜邦線 |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for fl in (1, 2):
        ol = [o for o in d["oleds"] if o["floor"] == fl]
        floor_fig(ol, fl, os.path.join(outdir, f"OLED個別配置_{fl}F.png"))
        for o in sorted(ol, key=lambda o: list(GRID).index(o["id"])):
            j = f"J{'2' if fl == 2 else ''}({o['J'][0]},{o['J'][1]})"
            rows.append(f"| {o['oid']} | {j} | {NAMEZH[o['id']]} | ({o['center'][0]:g}, {o['center'][1]:g}) | "
                        f"({o['slot'][0]:g}, {o['slot'][1]:g}) | {DIRZH[o['up']]} | {o['hub']} | "
                        f"{bus_txt(o)} | {o['addr']} | {wire_cm(o)} cm × 4 |")
    with open(os.path.join(outdir, "OLED個別配置表.md"), "w", encoding="utf-8") as f:
        f.write("# 18 塊天花板 OLED 個別配置表（8 台鏡頭 HUB 方案）\n\n"
                "資料來源：交接 repo `wiring_8hub/wiring_8hub.json`。座標為俯視、北在上、原點＝該層樓層中心，單位 mm；2F 的高度另加 150 mm。\n\n"
                + "\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
