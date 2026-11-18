"""End-to-end test of the 18 ceiling OLEDs driven by the 8 camera HUBs (2026-11-18 layout, wiring_8hub/).

python server_oled8_test.py [port]        default 8767; starts app/server.py itself, prints a markdown report

- The OLED table is read from hub_node.ino (OLED_MAP), so the test breaks if it stops covering the 18 junctions
  (1F J(i,j), 2F J2(i,j)) exactly once, if a board has more than 3, or if two displays on one bus share an address.
- The 8 camera HUBs post like the firmware does (POST /api/dev/<MAC>/detections); positions come from a temporary
  app/devices.json (backed up and restored). Each reply is applied the way EvacOled::applyJson() does.
- Scenarios = server_smoke_test.py, placed on 1F and (same corridors) on 2F; expected = evac in-process on the same boxes.
"""
import sys, os, re, json, time, shutil, subprocess, tempfile
import evac as E, states as ST
import server_smoke_test as T

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8767
T.BASE = f"http://127.0.0.1:{PORT}"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
APP = os.path.join(ROOT, "app")
SLOTS = ["1N", "1E", "1S", "1W", "2N", "2E", "2S", "2W"]
MACS = {s: f"0000000000B{k}" for k, s in enumerate(SLOTS)}
SIGNS = {"OFF", "N", "NE", "E", "SE", "S", "SW", "W", "NW", "UP", "DOWN", "X", "", "NONE", "BLOCKED"}


def read_table():
    node = open(os.path.join(ROOT, "firmware", "hub_node", "hub_node.ino"), encoding="utf-8").read()
    corner = re.search(r"#define EVAC_CORNER_ADDR (0x\w+)", node).group(1)
    return [dict(board=s, id=j, bus=b, addr=a.replace("EVAC_CORNER_ADDR", corner), top=t)
            for s, j, b, a, t in re.findall(r'\{"(\w+)", OLED\("(J\d?\([-0-9,]+\))",\s*Bus::(\w+),\s*(\w+),\s*(\w+)\)\}', node)]


def apply_json(body, ids, shown):
    n = 0
    for obj in re.findall(r"\{([^{}]*)\}", body):
        i, d = re.search(r'"id"\s*:\s*"([^"]*)"', obj), re.search(r'"dir"\s*:\s*"([^"]*)"', obj)
        if i and d and i.group(1) in ids and d.group(1).upper() in SIGNS:
            shown[i.group(1)] = d.group(1).upper(); n += 1
    return n


def main():
    out = [f"# 8 台鏡頭 HUB × 18 塊 OLED 端對端測試（{time.strftime('%Y-%m-%d %H:%M')}，伺服器 port {PORT}）", ""]
    ok = True
    rows = read_table()
    want = sorted(E.junction_id(ij, fl) for fl in (1, 2) for ij in E.JUNCTION_ORDER)
    cover = sorted(r["id"] for r in rows) == want
    per_board = {s: [r for r in rows if r["board"] == s] for s in SLOTS}
    max3 = all(1 <= len(v) <= 3 for v in per_board.values())
    addr_ok = all(len({(r["bus"], r["addr"]) for r in v}) == len(v) for v in per_board.values())
    floor_ok = all(all((r["id"].startswith("J2(") if s[0] == "2" else r["id"].startswith("J(")) for r in v) for s, v in per_board.items())
    ok &= cover and max3 and addr_ok and floor_ok
    out += ["## OLED 設定表（從 hub_node.ino 讀出）", "", "| 板子 | 路口 | 匯流排 | 位址 | 螢幕上緣 |", "|---|---|---|---|---|"]
    out += [f"| {r['board']} | {r['id']} | {r['bus']} | {r['addr']} | {r['top']} |" for r in rows]
    out += ["", f"18 個路口各出現一次：{'是' if cover else '**否**'}；每台 1～3 塊：{'是' if max3 else '**否**'}；"
                f"同一台同一匯流排沒有重複位址：{'是' if addr_ok else '**否**'}；每台只接自己樓層：{'是' if floor_ok else '**否**'}", ""]

    devf = os.path.join(APP, "devices.json"); backup = devf + ".bak_oled8" if os.path.exists(devf) else None
    if backup: shutil.copy(devf, backup)
    json.dump({m: dict(name=f"test {s}", slot=s) for s, m in MACS.items()}, open(devf, "w", encoding="utf-8"))
    logpath = os.path.join(tempfile.gettempdir(), "server_oled8_test.log"); log = open(logpath, "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "server.py", "--port", str(PORT)], cwd=APP, stdout=log, stderr=subprocess.STDOUT,
                            env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    try:
        for _ in range(150):
            try: T.http("GET", "/api/junctions"); break
            except Exception: time.sleep(0.2)
        _, raw = T.http("GET", "/api/junctions?floor=2"); j2 = json.loads(raw)["junctions"]
        g2 = len(j2) == 9 and all(o["id"].startswith("J2(") for o in j2); ok &= g2
        _, raw = T.http("GET", "/api/displays"); nodisp = json.loads(raw)["displays"] == {}; ok &= nodisp
        out += [f"`GET /api/junctions?floor=2` 回 9 筆 2F 代號：{'是' if g2 else '**否**'}；`GET /api/displays` 已沒有 H5/H6/H7：{'是' if nodisp else '**否**'}", ""]
        seq = 100
        for k, title, items in T.SCENARIOS:
            dets = {s: [] for s in SLOTS}
            for fl in (1, 2):
                for name, seg, strength in items:
                    r = T.box_for(name, seg, fl=fl, strength=strength)
                    if r is None:
                        out.append(f"（{fl}F {title}：{name} {seg} 找不到鏡頭）"); ok = False; continue
                    dets[f"{fl}{r[0]}"].append(r[1])
            shown = {r["id"]: "OFF" for r in rows}
            for rnd in range(2):                     # round 1 settles the state, round 2 = what each board shows
                for s in SLOTS:
                    seq += 1
                    st, raw = T.http("POST", f"/api/dev/{MACS[s]}/detections", {"seq": seq, "fps": 5, "fw": "2.3", "dets": dets[s]})
                    resp = json.loads(raw)
                    ok &= st == 200 and resp["slot"] == s and len(resp["junctions"]) == 9
                    if rnd:
                        mine = [r["id"] for r in per_board[s]]
                        n = apply_json(raw.decode(), mine, shown); ok &= n == len(mine)
            stl = E.fuse({(int(s[0]), s[1]): [tuple(b) for b in v] for s, v in dets.items()})
            leds, _ = E.plan(stl, fire=ST.fire_estimate(stl))
            local = {o["id"]: o["dir"] for fl in (1, 2) for o in E.junctions(leds, fl)}
            same = all(shown[i] == local[i] for i in want); ok &= same
            out += [f"## {title}（junction_check 情境 {k}，1F 與 2F 放同樣的狀況）", "", "```"]
            for fl in (1, 2):
                out.append(f"{fl}F")
                for j in (1, 0, -1):
                    out.append("  ".join(f"{shown[E.junction_id((i, j), fl)]:>4}" for i in (-1, 0, 1)))
            out += ["```", f"18 塊螢幕＝本機 evac：{'一致' if same else '**不一致** ' + str({i: (shown[i], local[i]) for i in want if shown[i] != local[i]})}", ""]
    finally:
        proc.terminate(); proc.wait(timeout=10); log.close()
        if backup: shutil.move(backup, devf)
        else: os.remove(devf)
    srv = open(logpath, encoding="utf-8").read()
    reqs = re.findall(r'"(GET|POST) (\S+) HTTP/1.1" (\d+)', srv); bad = [r for r in reqs if r[2] != "200"]
    ok &= not bad and "Traceback" not in srv
    out += [f"伺服器 log：{len(reqs)} 個請求，非 200 的 {len(bad)} 個，Traceback {srv.count('Traceback')} 個", "",
            f"**總結：{'全部通過' if ok else '有失敗項目'}**"]
    print("\n".join(out))
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
