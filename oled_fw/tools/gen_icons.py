"""產生 EvacOled 的圖示點陣（C 標頭）與 PNG 預覽。

圖示只定義一次（本檔），韌體用的 EvacIconData.h 與 preview/*.png 都由這裡產生，
預覽圖是把寫出的標頭再解析回來畫的，所以看到的就是燒進板子的資料。

用法：python -I oled_fw/tools/gen_icons.py
不需要 Pillow（PNG 用 zlib 自己寫）。
"""
import math
import os
import re
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HEADER = os.path.join(ROOT, "libraries", "EvacOled", "src", "EvacIconData.h")
PREVIEW = os.path.join(ROOT, "preview")

W = 128
SIZES = (64, 32)
MARGIN = 2

# 圖示順序必須和 EvacOled.h 的 IconId 一致
# 0..7 = 螢幕上的箭頭方向（0 = 螢幕上方，順時針每格 45°）
ARROW_NAMES = ["UP", "UP_RIGHT", "RIGHT", "DOWN_RIGHT", "DOWN", "DOWN_LEFT", "LEFT", "UP_LEFT"]
ICON_NAMES = ["ARROW_" + n for n in ARROW_NAMES] + ["STAIRS_UP", "STAIRS_DOWN", "BLOCKED"]


# ---------- 幾何 ----------

def inside(poly, x, y):
    """偶奇法判斷點是否在多邊形內（箭頭是凹多邊形）。"""
    c = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                c = not c
    return c


def fill(img, poly):
    h = len(img)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    for y in range(max(0, int(min(ys))), min(h, int(math.ceil(max(ys))) + 1)):
        for x in range(max(0, int(min(xs))), min(W, int(math.ceil(max(xs))) + 1)):
            if inside(poly, x + 0.5, y + 0.5):
                img[y][x] = 1


def arrow_right(length, cross):
    """以原點為尾端中心、指向 +x 的箭頭。回傳多邊形。"""
    # 短箭頭（0.91 吋的上下）放寬到至少 44 px，遠看才不會只剩一個點
    head_w = min(cross, max(1.1 * length, 44))
    head_len = min(0.85 * head_w, 0.55 * length)
    shaft = 0.44 * head_w
    b = length - head_len
    return [(0, -shaft / 2), (b, -shaft / 2), (b, -head_w / 2), (length, 0),
            (b, head_w / 2), (b, shaft / 2), (0, shaft / 2)]


def transform(poly, ang_deg, box):
    """把指向 +x 的多邊形旋轉 ang（螢幕座標，順時針），再放進 box 置中。"""
    a = math.radians(ang_deg)
    ca, sa = math.cos(a), math.sin(a)
    pts = [(x * ca - y * sa, x * sa + y * ca) for x, y in poly]
    x0, y0, x1, y1 = box
    minx = min(p[0] for p in pts); maxx = max(p[0] for p in pts)
    miny = min(p[1] for p in pts); maxy = max(p[1] for p in pts)
    s = min((x1 - x0) / (maxx - minx), (y1 - y0) / (maxy - miny))
    cx = (x0 + x1) / 2 - (minx + maxx) / 2 * s
    cy = (y0 + y1) / 2 - (miny + maxy) / 2 * s
    return [(cx + x * s, cy + y * s) for x, y in pts]


def draw_arrow(img, screen_dir, box):
    """screen_dir: 0 = 上，順時針 45° 一格。"""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    if screen_dir % 2 == 0:
        # 正方向：沿長軸塞滿，不做等比縮放
        horizontal = screen_dir in (2, 6)
        length, cross = (bw, bh) if horizontal else (bh, bw)
        poly = arrow_right(length, cross)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        out = []
        for x, y in poly:
            x -= length / 2
            if screen_dir == 2:
                out.append((cx + x, cy + y))
            elif screen_dir == 6:
                out.append((cx - x, cy + y))
            elif screen_dir == 0:
                out.append((cx + y, cy - x))
            else:
                out.append((cx + y, cy + x))
        fill(img, out)
    else:
        # 斜向：等比例旋轉後放進框內，保持真正的 45°
        poly = arrow_right(100, 70)
        fill(img, transform(poly, screen_dir * 45 - 90, box))


def draw_stairs(img, box, up):
    """樓梯剖面（4 階）；up=True 往右上升。"""
    x0, y0, x1, y1 = box
    steps = 4
    sw = (x1 - x0) / steps
    sh = (y1 - y0) / steps
    for i in range(steps):
        k = i if up else steps - 1 - i
        top = y1 - (k + 1) * sh
        fill(img, [(x0 + i * sw, top), (x0 + (i + 1) * sw, top),
                   (x0 + (i + 1) * sw, y1), (x0 + i * sw, y1)])


def draw_x(img, box):
    x0, y0, x1, y1 = box
    side = min(x1 - x0, y1 - y0)
    hw = min(x1 - x0, side * 1.6) / 2  # 允許稍寬的 X，0.91 吋才夠大
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half = side / 2
    t = side * 0.14  # 線寬的一半
    for sgn in (1, -1):
        # 沿對角線的粗線段
        ax, ay = cx - hw, cy - sgn * half
        bx, by = cx + hw, cy + sgn * half
        dx, dy = bx - ax, by - ay
        ln = math.hypot(dx, dy)
        nx, ny = -dy / ln * t, dx / ln * t
        # 兩端縮進一點，避免四角被方框裁成尖刺
        ux, uy = dx / ln * t * 0.5, dy / ln * t * 0.5
        fill(img, [(ax + ux + nx, ay + uy + ny), (bx - ux + nx, by - uy + ny),
                   (bx - ux - nx, by - uy - ny), (ax + ux - nx, ay + uy - ny)])


def draw_frame(img, t):
    h = len(img)
    for y in range(h):
        for x in range(W):
            if x < t or x >= W - t or y < t or y >= h - t:
                img[y][x] = 1


def render(name, h):
    img = [[0] * W for _ in range(h)]
    box = (MARGIN, MARGIN, W - MARGIN, h - MARGIN)
    if name.startswith("ARROW_"):
        draw_arrow(img, ARROW_NAMES.index(name[6:]), box)
    elif name in ("STAIRS_UP", "STAIRS_DOWN"):
        up = name == "STAIRS_UP"
        split = int(W * 0.55)
        draw_stairs(img, (MARGIN, MARGIN, split - 4, h - MARGIN), up)
        draw_arrow(img, 0 if up else 4, (split + 2, MARGIN, W - MARGIN, h - MARGIN))
    elif name == "BLOCKED":
        # 外框＋置中的粗 X：遠看和「箭頭」的輪廓差很多，不容易誤認
        t = 3 if h == 64 else 2
        draw_frame(img, t)
        draw_x(img, (MARGIN + t + 2, MARGIN + t + 2, W - MARGIN - t - 2, h - MARGIN - t - 2))
    else:
        raise ValueError(name)
    return img


# ---------- SSD1306 頁格式 ----------

def to_pages(img):
    h = len(img)
    out = bytearray(W * h // 8)
    for p in range(h // 8):
        for x in range(W):
            b = 0
            for bit in range(8):
                if img[p * 8 + bit][x]:
                    b |= 1 << bit
            out[p * W + x] = b
    return bytes(out)


def from_pages(data, h):
    img = [[0] * W for _ in range(h)]
    for p in range(h // 8):
        for x in range(W):
            b = data[p * W + x]
            for bit in range(8):
                img[p * 8 + bit][x] = (b >> bit) & 1
    return img


def write_header():
    lines = [
        "// 由 oled_fw/tools/gen_icons.py 自動產生，請勿手改。",
        "// 格式：SSD1306 頁模式，index = page*128 + x，bit n = 該頁第 n 列。",
        "#pragma once",
        "#include <stdint.h>",
        "",
        "#define EVAC_ICON_COUNT %d" % len(ICON_NAMES),
        "// " + ", ".join("%d=%s" % (i, n) for i, n in enumerate(ICON_NAMES)),
        "",
    ]
    for h in SIZES:
        lines.append("static const uint8_t EVAC_ICON_%d[EVAC_ICON_COUNT][%d] = {" % (h, W * h // 8))
        for n in ICON_NAMES:
            data = to_pages(render(n, h))
            lines.append("  { // %s" % n)
            for i in range(0, len(data), 16):
                lines.append("    " + ",".join("0x%02X" % b for b in data[i:i + 16]) + ",")
            lines.append("  },")
        lines.append("};")
        lines.append("")
    os.makedirs(os.path.dirname(HEADER), exist_ok=True)
    with open(HEADER, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


def read_header():
    """從標頭解析回點陣，確保預覽 = 韌體資料。"""
    text = open(HEADER, encoding="utf-8").read()
    out = {}
    for h in SIZES:
        m = re.search(r"EVAC_ICON_%d\[EVAC_ICON_COUNT\]\[\d+\] = \{(.*?)\n\};" % h, text, re.S)
        blocks = re.findall(r"\{ // (\w+)\n(.*?)\n  \},", m.group(1), re.S)
        for name, body in blocks:
            data = bytes(int(v, 16) for v in re.findall(r"0x([0-9A-F]{2})", body))
            assert len(data) == W * h // 8, (name, h, len(data))
            out[(name, h)] = from_pages(data, h)
    return out


# ---------- PNG ----------

def write_png(path, rows):
    """rows: list of list of (r,g,b)。"""
    hgt, wid = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(c for px in r for c in px) for r in rows)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", wid, hgt, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


ON = (235, 245, 255)
OFF = (18, 22, 30)
GAP = (0, 0, 0)
BG = (60, 60, 60)


def scaled(img, s):
    """每個像素放大成 s×s，留 1 px 縫，模擬 OLED 點陣。"""
    rows = []
    for r in img:
        line = []
        for v in r:
            line += [ON if v else OFF] * (s - 1) + [GAP]
        for _ in range(s - 1):
            rows.append(list(line))
        rows.append([GAP] * len(line))
    return rows


def paste(canvas, rows, ox, oy):
    for y, r in enumerate(rows):
        canvas[oy + y][ox:ox + len(r)] = r


COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def icon_for(sign, top, ceiling):
    """與 EvacOled.cpp 的 iconFor() 相同的換算。"""
    k = COMPASS.index(sign)
    t = COMPASS.index(top)
    return ICON_NAMES[((t - k) if ceiling else (k - t)) % 8]


def write_mapping(icons):
    """同一組伺服器指令，在『一般安裝』與『朝下裝天花板』時螢幕各顯示什麼。
    兩欄都是螢幕上緣朝北；每列一個方向 N/E/S/W。"""
    s = 2
    pad = 8
    rows = ["N", "E", "S", "W"]
    cw, chh = W * s, 64 * s
    canvas = [[BG] * (pad + 2 * (cw + pad)) for _ in range(pad + len(rows) * (chh + pad))]
    for i, d in enumerate(rows):
        for col, ceiling in enumerate((False, True)):
            img = icons[(icon_for(d, "N", ceiling), 64)]
            paste(canvas, scaled(img, s), pad + col * (cw + pad), pad + i * (chh + pad))
    write_png(os.path.join(PREVIEW, "mapping_top_N_wall_vs_ceiling.png"), canvas)


def main():
    write_header()
    icons = read_header()
    os.makedirs(PREVIEW, exist_ok=True)
    s = 4
    for (name, h), img in icons.items():
        write_png(os.path.join(PREVIEW, "%s_128x%d.png" % (name, h)), scaled(img, s))
    # 總覽：左欄 128×64、右欄 128×32，各圖示一列
    pad = 12
    cw = W * s
    ch64, ch32 = 64 * s, 32 * s
    cols = 2
    row_h = ch64 + pad
    canvas = [[BG] * (pad + cols * (cw + pad)) for _ in range(pad + len(ICON_NAMES) * row_h)]
    for i, n in enumerate(ICON_NAMES):
        y = pad + i * row_h
        paste(canvas, scaled(icons[(n, 64)], s), pad, y)
        paste(canvas, scaled(icons[(n, 32)], s), pad * 2 + cw, y + (ch64 - ch32) // 2)
    write_png(os.path.join(PREVIEW, "contact_sheet.png"), canvas)
    # 實際尺寸（1:1）的縮圖，看遠距離觀感
    small = [[BG] * (W * 2 + 3 * 4) for _ in range(len(ICON_NAMES) * 68 + 4)]
    for i, n in enumerate(ICON_NAMES):
        for col, h in enumerate(SIZES):
            img = icons[(n, h)]
            for y in range(h):
                for x in range(W):
                    small[4 + i * 68 + y][4 + col * (W + 4) + x] = ON if img[y][x] else OFF
    write_png(os.path.join(PREVIEW, "contact_sheet_1x.png"), small)
    write_mapping(icons)
    print("header:", os.path.relpath(HEADER, ROOT), "icons:", len(icons))


if __name__ == "__main__":
    main()
