"""燒錄前檢查：SDK 裡 DEFAULT_YOLOV7TINY 用的 yolov7_tiny.nb 現在是哪一個模型。

本專案用「把 SDK 的 variants/common_nn_models/yolov7_tiny.nb 換成本組模型、程式用 DEFAULT_YOLOV7TINY」的方式燒錄
（任何資料夾的 sketch、任何一台電腦、遠端用 arduino-cli 都能直接燒）。缺點是換錯或被 SDK 更新蓋回去時不會報錯：
COCO 模型的類別 0 = person 會被伺服器當成櫃子。這支程式直接讀 .nb 檔頭的張量形狀，不靠檔名判斷。

用法：
  python check_sdk_model.py                     # 自動找 %LOCALAPPDATA%\\Arduino15\\...\\4.0.15-Release 的 SDK
  python check_sdk_model.py <某個 .nb>           # 檢查任一個 .nb
  python check_sdk_model.py --expect-classes 7   # 不符就 exit 1（可放在燒錄腳本最前面）
回傳值：0 = 符合預期，1 = 不符或讀不到。
"""
import sys, os, struct, hashlib, glob

def nb_info(path):
    b = open(path, "rb").read(8192)
    if b[:4] != b"VPMN":
        return dict(error="不是 VeriSilicon NBG（檔頭不是 VPMN）")
    inp = None
    for off in range(0, len(b) - 12, 4):
        w, h, c = struct.unpack_from("<III", b, off)
        if c == 3 and w % 32 == 0 and h % 32 == 0 and 64 <= w <= 1280 and 64 <= h <= 1280:
            inp = (w, h); break
    if not inp:
        return dict(error="找不到輸入張量形狀")
    w, h = inp; outs = []
    for s in (8, 16, 32):
        for off in range(0, len(b) - 12, 4):
            a, bb, c = struct.unpack_from("<III", b, off)
            if (a, bb) == (w // s, h // s) and c % 3 == 0 and 18 <= c <= 600:
                outs.append(c); break
    if len(outs) != 3 or len(set(outs)) != 1:
        return dict(input=inp, error=f"輸出張量形狀不完整：{outs}")
    return dict(input=inp, outputs=outs, classes=outs[0] // 3 - 5,
                size=os.path.getsize(path), md5=hashlib.md5(open(path, "rb").read()).hexdigest())

def main():
    args = sys.argv[1:]; expect = None
    if "--expect-classes" in args:
        i = args.index("--expect-classes"); expect = int(args[i + 1]); del args[i:i + 2]
    if args:
        path = args[0]
    else:
        base = os.path.expandvars(r"%LOCALAPPDATA%\Arduino15\packages\ideasHatch\hardware\AmebaPro2")
        cands = glob.glob(os.path.join(base, "*", "variants", "common_nn_models", "yolov7_tiny.nb"))
        if not cands:
            print("找不到 SDK 的 yolov7_tiny.nb；請把路徑當參數傳進來"); return 1
        path = sorted(cands)[-1]
    info = nb_info(path)
    print(f"檔案：{path}")
    if "error" in info:
        print("讀取失敗：", info["error"]); return 1
    w, h = info["input"]; nc = info["classes"]
    kind = {80: "官方 COCO 模型（80 類，類別 0 = person）", 6: "本組 6 類（櫃子 紙箱 桌椅 瓦礫 閘門 煙）",
            7: "本組 7 類（6 類＋人偶）"}.get(nc, f"{nc} 類（不認得）")
    print(f"輸入 {w}×{h}；輸出通道 {info['outputs']} → {nc} 類：{kind}")
    print(f"大小 {info['size']:,} bytes；MD5 {info['md5']}")
    ok = True
    if (w, h) != (576, 320):
        print("⚠ 輸入不是 576×320：韌體的 NNW/NNH 要跟著改，否則畫面會被壓扁或載入失敗"); ok = False
    if expect is not None and nc != expect:
        print(f"⚠ 預期 {expect} 類，實際 {nc} 類：先換對模型再燒錄"); ok = False
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
