from PIL import Image, ImageDraw, ImageFont
import os, glob

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONTB = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
CLS = ["櫃子", "箱子", "桌椅", "瓦礫", "閘門", "煙"]
COL = [(230, 70, 60), (90, 200, 90), (70, 150, 240), (240, 200, 40), (220, 80, 220), (80, 220, 230)]
BG = (18, 20, 24); FG = (235, 235, 235); MUTED = (150, 155, 165)


def f(sz, bold=False):
    return ImageFont.truetype(FONTB if bold else FONT, sz)


def thumb(path, dets, w=300, off=False):
    if off or not os.path.exists(path):
        im = Image.new("RGB", (w, int(w * 9 / 16)), (40, 10, 10))
        d = ImageDraw.Draw(im); d.text((w // 2, w * 9 // 32), "鏡頭離線", fill=(255, 120, 120), font=f(22, True), anchor="mm")
        return im
    im = Image.open(path).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    for c, cx, cy, bw, bh, conf in dets:
        x0, y0, x1, y1 = (cx - bw / 2) * W, (cy - bh / 2) * H, (cx + bw / 2) * W, (cy + bh / 2) * H
        d.rectangle([x0, y0, x1, y1], outline=COL[c], width=3)
        d.text((x0 + 3, max(0, y0 - 22)), f"{CLS[c]} {conf:.2f}", fill=COL[c], font=f(18, True))
    return im.resize((w, int(w * H / W)))


def frame(stepdir, step, dets, seg_rows, leds_txt, out):
    Wf, Hf = 1920, 1080
    can = Image.new("RGB", (Wf, Hf), BG)
    d = ImageDraw.Draw(can)
    d.text((40, 28), "火災避難障礙物辨識系統 — 模擬世界運作", fill=FG, font=f(34, True))
    d.text((40, 78), f"t = {step['t']}　{step['note']}", fill=(255, 200, 90), font=f(28))
    for k, fl in enumerate((2, 1)):
        p = os.path.join(stepdir, f"over_F{fl}.png")
        if os.path.exists(p):
            ov = Image.open(p).convert("RGB").resize((560, 560))
            can.paste(ov, (40 + k * 590, 130))
        d.text((40 + k * 590 + 10, 136), f"{fl}F", fill=FG, font=f(30, True))
    # camera grid
    x0, y0 = 1230, 130
    d.text((x0, y0 - 2), "鏡頭畫面（YOLO 偵測結果）", fill=MUTED, font=f(20))
    i = 0
    for fl in (2, 1):
        for cam in "NWES":
            off = not os.path.exists(os.path.join(stepdir, f"F{fl}_{cam}.png"))
            t = thumb(os.path.join(stepdir, f"F{fl}_{cam}.png"), dets.get(f"{fl}{cam}", []), w=320, off=off)
            px, py = x0 + (i % 2) * 330, y0 + 28 + (i // 2) * 190
            can.paste(t, (px, py)); d.text((px + 6, py + 4), f"{fl}F-{cam}", fill=(255, 255, 255), font=f(16, True))
            i += 1
    # segment table
    ty = 715
    d.text((40, ty), "走廊段狀態（障礙率 / 煙）", fill=MUTED, font=f(22))
    for k, row in enumerate(seg_rows[:12]):
        cx, cy = 40 + (k % 3) * 390, ty + 36 + (k // 3) * 34
        d.text((cx, cy), row, fill=FG, font=f(20))
    d.text((40, 1000), leds_txt, fill=(120, 230, 140), font=f(22))
    can.save(out)
