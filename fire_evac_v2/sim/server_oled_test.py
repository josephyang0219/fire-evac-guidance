"""⚠ 2026-11-18 起由 server_oled8_test.py 取代（H5/H6/H7 已取消，這支會失敗，只留作參考）。

End-to-end test of the 9 1F ceiling OLEDs: real server + emulated firmware (4 camera HUBs + H5/H6/H7).

python server_oled_test.py [port]        default 8766; starts app/server.py itself, prints a markdown report

- OLED tables are read from the sketches themselves (hub_node.ino OLED_MAP, hub_oled.ino SLOTS per NODE_ID), so the test
  breaks if the tables stop covering the 9 junctions exactly once.
- The 4 camera HUBs post like the firmware does (POST /api/dev/<MAC>/detections); their positions come from a
  temporary app/devices.json (backed up and restored). H5/H6/H7 poll GET /api/junctions?node=Hn&seq=N.
- Each board's reply is applied the way EvacOled::applyJson() does (innermost {"id","dir"} objects, matching id).
- Scenarios and YOLO boxes are the ones of server_smoke_test.py; expected directions = evac in-process on the same
  boxes, and junction_check_output.md.
"""
import sys, os, re, json, time, shutil, subprocess, tempfile, urllib.request
import evac as E, states as ST, junction_check as J
import server_smoke_test as T

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
T.BASE = f"http://127.0.0.1:{PORT}"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
APP = os.path.join(ROOT, "app")
DISPLAYS = ("H5", "H6", "H7")
MACS = {"1N": "0000000000A1", "1E": "0000000000A2", "1S": "0000000000A3", "1W": "0000000000A4"}
SIGNS = {"OFF", "N", "NE", "E", "SE", "S", "SW", "W", "NW", "UP", "DOWN", "X", "", "NONE", "BLOCKED"}


def read_tables():
    node = open(os.path.join(ROOT, "firmware", "hub_node", "hub_node.ino"), encoding="utf-8").read()
    ho = open(os.path.join(ROOT, "firmware", "hub_oled", "hub_oled.ino"), encoding="utf-8").read()
    corner = re.search(r"#define EVAC_CORNER_ADDR (0x\w+)", node).group(1)
    cams = [dict(board=s, id=j, bus=b, addr=a.replace("EVAC_CORNER_ADDR", corner), ch=c)
            for s, j, b, a, c in re.findall(r'\{"(\w+)", OLED\("(J\([-0-9,]+\))",\s*Bus::(\w+),\s*(\w+),\s*(\w+)\)\}', node)]
    nodes = []                                       # one SLOTS[] per "#if / #elif NODE_ID == n" block
    for n, block in re.findall(r"#(?:el)?if NODE_ID == (\d+)\n(.*?)(?=\n#)", ho, re.S):
        nodes += [dict(board=f"H{n}", id=j, bus="Wire0", addr=a, ch="kNoMux")
                  for j, a in re.findall(r'OLED\("(J\([-0-9,]+\))",\s*(0x\w+)\)', block)]
    return cams + nodes


def apply_json(body, ids, shown):
    """port of EvacOled::applyJson(): innermost {...} with "id" and "dir"; returns how many were applied"""
    n = 0
    for obj in re.findall(r"\{([^{}]*)\}", body):
        i, d = re.search(r'"id"\s*:\s*"([^"]*)"', obj), re.search(r'"dir"\s*:\s*"([^"]*)"', obj)
        if i and d and i.group(1) in ids and d.group(1).upper() in SIGNS:
            shown[i.group(1)] = d.group(1).upper(); n += 1
    return n


def start_server(log):
    devf = os.path.join(APP, "devices.json")
    backup = devf + ".bak_oledtest" if os.path.exists(devf) else None
    if backup:
        shutil.copy(devf, backup)
    json.dump({m: dict(name=f"test {s}", slot=s) for s, m in MACS.items()}, open(devf, "w", encoding="utf-8"))
    p = subprocess.Popen([sys.executable, "server.py", "--port", str(PORT)], cwd=APP, stdout=log, stderr=subprocess.STDOUT,
                         env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    for _ in range(100):
        try:
            T.http("GET", "/api/junctions"); break
        except Exception:
            time.sleep(0.2)
    return p, devf, backup


def main():
    out = [f"# 1F 9 塊 OLED 端對端測試（{time.strftime('%Y-%m-%d %H:%M')}，伺服器 port {PORT}）", ""]
    ok = True
    rows = read_tables()
    ids = [r["id"] for r in rows]
    cover = sorted(ids) == sorted(E.junction_id(ij) for ij in E.JUNCTION_ORDER)
    ok &= cover
    out.append("## OLED 設定表（從韌體原始碼讀出）")
    out.append("")
    out.append("| 路口 | 板子 | 匯流排 | 位址 | 多工器通道 |\n|---|---|---|---|---|")
    by_id = {r["id"]: r for r in rows}
    for ij in E.JUNCTION_ORDER:
        r = by_id.get(E.junction_id(ij))
        out.append(f"| {E.junction_id(ij)} {J.NAMES[ij]} | " + (f"{r['board']} | {r['bus']} | {r['addr']} | {'—' if r['ch'] == 'kNoMux' else 'ch' + r['ch']} |" if r else "（沒有） | | | |"))
    out.append("")
    out.append(f"9 個路口各出現一次：{'是' if cover else '**否**'}")
    out.append("")

    logpath = os.path.join(tempfile.gettempdir(), "server_oled_test.log")
    log = open(logpath, "w", encoding="utf-8")
    proc, devf, backup = start_server(log)
    try:
        seq = 100
        hseq = {n: 0 for n in DISPLAYS}
        _, raw = T.http("GET", "/api/displays")
        before = json.loads(raw)["displays"]
        pre_ok = all(n in before and not before[n]["online"] for n in DISPLAYS)
        ok &= pre_ok
        out.append(f"還沒有顯示節點輪詢時，`GET /api/displays` 列出 {sorted(before)}，全部 offline：{'是' if pre_ok else '**否**'}")
        out.append("")
        for k, title, items in T.SCENARIOS:
            dets = {h: [] for h in T.HUBS}
            for name, seg, strength in items:
                r = T.box_for(name, seg, strength=strength)
                if r is None:
                    out.append(f"（{title}：{name} {seg} 找不到鏡頭）"); ok = False; continue
                dets[f"1{r[0]}"].append(r[1])
            shown = {i: "OFF" for i in ids}          # what each display shows (boot = dark)
            keys_ok = True
            for slot in ("1N", "1S", "1W", "1E"):
                seq += 1
                st, raw = T.http("POST", f"/api/dev/{MACS[slot]}/detections", {"seq": seq, "fps": 5, "fw": "2.2", "dets": dets[slot]})
                resp = json.loads(raw)
                keys_ok &= st == 200 and set(resp) == {"blink", "junctions", "leds", "node", "slot", "snap"} and resp["slot"] == slot
            # every camera HUB applies the reply it would get now (state settled after the 4 posts)
            for slot in ("1N", "1S", "1W", "1E"):
                seq += 1
                _, raw = T.http("POST", f"/api/dev/{MACS[slot]}/detections", {"seq": seq, "fps": 5, "fw": "2.2", "dets": dets[slot]})
                resp = json.loads(raw)
                mine = [r["id"] for r in rows if r["board"] == resp["slot"]]
                apply_json(raw.decode(), mine, shown)
            napplied = {}
            for node in DISPLAYS:
                hseq[node] += 2 if (node == "H7" and k == T.SCENARIOS[-1][0]) else 1   # H7 skips one seq at the end
                st, raw = T.http("GET", f"/api/junctions?node={node}&seq={hseq[node]}&fw=holed-1.0")
                mine = [r["id"] for r in rows if r["board"] == node]
                napplied[node] = (apply_json(raw.decode(), mine, shown), len(mine))
                ok &= st == 200 and napplied[node][0] == len(mine)
            ok &= keys_ok

            stl = E.fuse({(1, h[1]): [tuple(b) for b in v] for h, v in dets.items()})
            leds, _ = E.plan(stl, fire=ST.fire_estimate(stl))
            local = {o["id"]: o["dir"] for o in E.junctions(leds)}
            table = T.expected_from_table(k)
            same = all(shown[i] == local[i] for i in ids)
            same_t = all(shown[i] == table[i] for i in ids)
            errs = J.check(stl, leds, ST.fire_estimate(stl))
            ok &= same and not errs

            out.append(f"## {title}（junction_check 情境 {k}）")
            out.append("")
            out.append("螢幕上看到的（從下往上看的地圖方位，北在上）：")
            out.append("```")
            for j in (1, 0, -1):
                out.append("  ".join(f"{shown[E.junction_id((i, j))]:>4}" for i in (-1, 0, 1)))
            out.append("```")
            out.append("| 路口 | 由誰顯示 | 螢幕 | 本機 evac | junction_check 表 |\n|---|---|---|---|---|")
            for ij in E.JUNCTION_ORDER:
                i = E.junction_id(ij)
                r = by_id[i]
                out.append(f"| {i} {J.NAMES[ij]} | {r['board']} {r['addr']} | {shown[i]} | {local[i]} | {table[i]}{'' if shown[i] == table[i] else ' ≠'} |")
            out.append("")
            out.append(f"鏡頭 HUB 回應欄位不變（blink junctions leds node slot snap）：{'是' if keys_ok else '**否**'}；顯示節點套用 " + "、".join(f"{n} {a}/{b}" for n, (a, b) in napplied.items()))
            out.append(f"9 塊螢幕＝本機 evac：{'一致' if same else '**不一致**'}；＝junction_check 表：{'一致' if same_t else '有差異'}；"
                       f"規則檢查：{'通過' if not errs else '失敗：' + '；'.join(errs)}")
            out.append("")

        _, raw = T.http("GET", "/api/displays")
        disp = json.loads(raw)["displays"]
        n_sc = len(T.SCENARIOS)
        want = {"H5": 0.0, "H6": 0.0, "H7": round(100 * 1 / (n_sc + 1), 1)}    # H7 skipped one seq -> 1 lost
        out.append("## 顯示節點心跳（`GET /api/displays`）")
        out.append("")
        out.append("| 節點 | online | 輪詢次數 n | loss % | 預期 loss % |\n|---|---|---|---|---|")
        hb = True
        for node in DISPLAYS:
            d = disp.get(node) or {}
            good = d.get("online") and d.get("n") == n_sc and d.get("loss") == want[node]
            hb &= bool(good)
            out.append(f"| {node} | {d.get('online')} | {d.get('n')} | {d.get('loss')} | {want[node]}{'' if good else ' ≠'} |")
        out.append("")
        out.append(f"H7 在最後一個情境故意跳過一個 seq，用來確認伺服器有從 seq 算掉包。判定：{'正確' if hb else '**不正確**'}")
        ok &= hb
        out.append("")
    finally:
        proc.terminate(); proc.wait(timeout=10); log.close()
        if backup:
            shutil.move(backup, devf)
        else:
            os.remove(devf)

    # server gone: H5 (and the camera HUBs) get no reply -> after LINK_TIMEOUT_MS the displays go dark
    try:
        T.http("GET", "/api/junctions?node=H5&seq=999"); reach = "仍然連得到（不正常）"; ok = False
    except Exception as e:
        reach = f"連不上（{type(e).__name__}）"
    out.append("## 伺服器停掉之後")
    out.append("")
    out.append(f"顯示節點輪詢：{reach}。韌體規則：超過 LINK_TIMEOUT_MS = 3000 ms 沒有有效回應 → H5/H6/H7 的螢幕全部 Off（全黑）；"
               "鏡頭 HUB 同樣在 3 秒後把自己的角落螢幕關掉。")
    out.append("")
    srv = open(logpath, encoding="utf-8").read()
    reqs = re.findall(r'"(GET|POST) (\S+) HTTP/1.1" (\d+)', srv)
    bad = [r for r in reqs if r[2] != "200"]
    out.append(f"伺服器 log：{len(reqs)} 個請求，非 200 的 {len(bad)} 個，Traceback {srv.count('Traceback')} 個")
    ok &= not bad and "Traceback" not in srv
    out.append("")
    out.append(f"**總結：{'全部通過' if ok else '有失敗項目'}**")
    print("\n".join(out))
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
