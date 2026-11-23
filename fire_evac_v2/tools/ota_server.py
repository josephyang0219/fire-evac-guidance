"""多台 HUB 的 OTA 伺服器（筆電端，只用 Python 標準函式庫）。以 ota_test/ota_server.py（老闆分支 48d15cf9）為基礎。

和主伺服器（fire_evac_v2/app/server.py，port 8000）分開跑，預設 port 3000。

板子（SDK 的 AmebaOTA，hub_node 用 08_OTAMode=Enable 編譯時）：
  1. 每約 4 秒 POST /api/connectedclients  {"OTA_state": "OTA_STATE_IDLE" ...}；只有狀態，伺服器用來源 IP 分辨板子。
  2. 在自己的 TCP 5000 等「start_ota」，收到後 GET /api/uploadfile 下載韌體，寫進另一個分區後重開機。
  3. 更新失敗時狀態停在 OTA_STATE_DOWNLOAD_FIRMWARE_COMPLETED，要按 RST 才能再更新。
hub_node 另外每 30 秒 POST /api/nodeinfo  {"mac","fw","slot","ota"}，讓這裡能叫出「1N」這種名字、並在重開後確認版本。

用法：
  python ota_server.py serve --bin ota.bin [--port 3000] [--expect-fw 2.4] [--keep-going]
      --bin 要推送的檔案：ameba_pro2_tools/<版本>/ota.bin（firmware.bin＋4 bytes 檢查碼）。推 firmware.bin 板子會報 checksum wrong。
      --expect-fw 更新後板子回報的 FW 要等於這個才算成功（強烈建議填，等於 hub_node.ino 的 FW）。
  python ota_server.py status [--server http://127.0.0.1:3000]          列出每台狀態
  python ota_server.py update all | 1N 2S 192.168.137.50 ... [--server ...]   依序一台一台更新
  python ota_server.py trigger <板子IP>                                   直接送 start_ota（不經排程，除錯用）

依序更新每一台時的判定（任何一步逾時或出錯 = 這台失敗，原因寫在 status 的「結果」欄）：
  線上且 IDLE → 送 start_ota → 開始下載 → 下載完整 → 離線（重開機）→ 回來 IDLE、FW 等於 --expect-fw
  預設一台失敗就停下，後面的標成「略過」；--keep-going 則繼續下一台。
"""
import argparse, datetime, json, os, re, socket, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
BOARDS = {}           # ip -> dict(state, seen, mac, fw, slot, ota, dl_sent, dl_total, dl_start, dl_done, result, note)
JOB = dict(running=False, queue=[], current=None, log=[])
CFG = dict(bin=None, data=b"", expect_fw=None, keep_going=False,
           online_s=10.0, start_s=30.0, download_s=180.0, reboot_s=150.0, gap_s=6.0, poll_s=0.5)
SLOT_ORDER = [f"{f}{c}" for f in (1, 2) for c in "NESW"]


def now():
    return datetime.datetime.now().strftime("%H:%M:%S")


def log(msg):
    line = f"[{now()}] {msg}"
    print(line, flush=True)
    with LOCK:
        JOB["log"] = (JOB["log"] + [line])[-200:]


def board(ip):
    return BOARDS.setdefault(ip, dict(state="?", seen=0.0, mac="", fw="", slot="", ota="", info_at=0.0,
                                      dl_sent=0, dl_total=0, dl_start=0.0, dl_done=0.0, dl_err="", result="", note=""))


def name(ip):
    b = BOARDS.get(ip) or {}
    s = b.get("slot") if b.get("slot") not in ("", "?") else ""
    tail = f"…{b['mac'][-4:]}" if b.get("mac") else ""
    return f"{s or '未指派'}（{ip}{(' ' + tail) if tail else ''}）"


def online(b, t=None):
    return (t or time.time()) - b["seen"] < CFG["online_s"]


def snapshot():
    t = time.time()
    with LOCK:
        rows = []
        for ip, b in BOARDS.items():
            rows.append(dict(ip=ip, name=name(ip), slot=b["slot"], mac=b["mac"], fw=b["fw"], state=b["state"],
                             online=online(b, t), age=round(t - b["seen"], 1) if b["seen"] else None,
                             download=f"{b['dl_sent']}/{b['dl_total']}" if b["dl_total"] else "",
                             result=b["result"], note=b["note"]))
        job = dict(running=JOB["running"], current=JOB["current"], queue=list(JOB["queue"]), log=JOB["log"][-30:])
    rows.sort(key=lambda r: (SLOT_ORDER.index(r["slot"]) if r["slot"] in SLOT_ORDER else 99, r["ip"]))
    return dict(bin=os.path.basename(CFG["bin"] or ""), size=len(CFG["data"]), expect_fw=CFG["expect_fw"], boards=rows, job=job)


def status_text(snap):
    out = [f"推送檔案 {snap['bin']}（{snap['size']:,} bytes），預期更新後 FW = {snap['expect_fw'] or '（未指定）'}", ""]
    out.append(f"{'板子':<28}{'線上':<5}{'OTA 狀態':<42}{'FW':<8}{'下載':<20}結果")
    for r in snap["boards"]:
        out.append(f"{r['name']:<28}{'是' if r['online'] else '否':<5}{r['state']:<42}{r['fw'] or '-':<8}{r['download'] or '-':<20}"
                   f"{r['result']}{('：' + r['note']) if r['note'] else ''}")
    if not snap["boards"]:
        out.append("（還沒有板子連線）")
    j = snap["job"]
    out += ["", f"排程：{'進行中，目前 ' + j['current'] if j['running'] else '閒置'}；等待中 {j['queue'] or '無'}"]
    return "\n".join(out)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _reply(self, code, body=b"", ctype="text/plain; charset=utf-8"):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return self.rfile.read(n).decode("utf-8", "replace") if n else ""
        except (ConnectionResetError, ConnectionAbortedError):
            return ""

    def do_POST(self):
        ip, body = self.client_address[0], self._body()
        if self.path.startswith("/api/connectedclients"):
            states = re.findall(r'"OTA_state"\s*:\s*"([^"]+)"', body)
            st = states[-1] if states else "?"
            with LOCK:
                b = board(ip); old = b["state"]; b["state"] = st; b["seen"] = time.time()
            if old != st:
                log(f"{name(ip)}：{old if old != '?' else '（新連線）'} → {st}")
            self._reply(200, b"ok")
        elif self.path.startswith("/api/nodeinfo"):
            try:
                d = json.loads(body)
            except ValueError:
                return self._reply(400, b"bad json")
            with LOCK:
                b = board(ip); old_fw = b["fw"]
                b.update(mac=str(d.get("mac", ""))[:12], fw=str(d.get("fw", ""))[:16], slot=str(d.get("slot", ""))[:4],
                         ota=str(d.get("ota", ""))[:48], info_at=time.time())
            if old_fw != b["fw"]:
                log(f"{name(ip)}：FW {old_fw or '?'} → {b['fw']}")
            self._reply(200, b"ok")
        elif self.path.startswith("/api/update"):
            try:
                targets = json.loads(body or "{}").get("targets") or []
            except ValueError:
                return self._reply(400, b"bad json")
            ok, msg = start_job(targets)
            self._reply(200 if ok else 409, msg.encode("utf-8"))
        else:
            self._reply(404)

    def do_GET(self):
        ip = self.client_address[0]
        if self.path.startswith("/api/uploadfile"):
            data = CFG["data"]
            with LOCK:
                b = board(ip); b.update(dl_sent=0, dl_total=len(data), dl_start=time.time(), dl_done=0.0, dl_err="")
            log(f"{name(ip)} 開始下載 {os.path.basename(CFG['bin'])}（{len(data):,} bytes）")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                for i in range(0, len(data), 4096):
                    self.wfile.write(data[i:i + 4096])
                    with LOCK:
                        b["dl_sent"] = min(len(data), i + 4096)
                self.wfile.flush()
                with LOCK:
                    b["dl_done"] = time.time()
                log(f"{name(ip)} 下載完成 {b['dl_sent']:,} bytes")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
                with LOCK:
                    b["dl_err"] = type(e).__name__
                log(f"{name(ip)} 下載中斷，送出 {b['dl_sent']:,}/{len(data):,} bytes：{e}")
        elif self.path.startswith("/api/status"):
            self._reply(200, json.dumps(snapshot(), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path in ("/", "/status"):
            self._reply(200, status_text(snapshot()).encode("utf-8"))
        else:
            self._reply(404)


def send_start(ip):
    with socket.create_connection((ip, 5000), timeout=5) as s:
        s.sendall(b"start_ota")


def resolve(targets):
    """'all' / slot names / IPs -> IPs in slot order"""
    snap = snapshot()["boards"]
    if not targets or "all" in targets:
        return [r["ip"] for r in snap if r["online"]]
    out = []
    for t in targets:
        hit = [r["ip"] for r in snap if t in (r["ip"], r["slot"], r["mac"])]
        out += hit or [t]
    return out


def start_job(targets):
    with LOCK:
        if JOB["running"]:
            return False, "已經有一個更新排程在跑"
    ips = resolve(targets)
    if not ips:
        return False, "沒有要更新的板子（沒有線上的板子，或名稱找不到）"
    with LOCK:
        JOB.update(running=True, queue=list(ips), current=None)
        for ip in ips:
            b = board(ip); b["result"] = "排隊中"; b["note"] = ""
    threading.Thread(target=run_job, daemon=True).start()
    return True, "開始依序更新：" + "、".join(name(ip) for ip in ips)


def wait_for(cond, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with LOCK:
            r = cond()
        if r:
            return r
        time.sleep(CFG["poll_s"])
    return None


def update_one(ip):
    """returns (ok, note)"""
    b = board(ip)
    with LOCK:
        if not online(b):
            return False, "離線（沒有收到 OTA 回報）"
        if b["state"] != "OTA_STATE_IDLE":
            return False, f"不是 IDLE（{b['state']}），要先按 RST"
        old_fw = b["fw"]
        b.update(dl_sent=0, dl_total=0, dl_start=0.0, dl_done=0.0, dl_err="")
    t_start = time.time()
    try:
        send_start(ip)
    except OSError as e:
        return False, f"送 start_ota 到 {ip}:5000 失敗：{e}"
    log(f"{name(ip)}：已送 start_ota")
    if not wait_for(lambda: b["dl_start"] >= t_start, CFG["start_s"]):
        return False, f"送出 start_ota 後 {CFG['start_s']:.0f} 秒內沒有開始下載（狀態 {b['state']}）"
    if not wait_for(lambda: b["dl_done"] or b["dl_err"], CFG["download_s"]) or not b["dl_done"]:
        why = f"連線中斷 {b['dl_err']}" if b["dl_err"] else f"{CFG['download_s']:.0f} 秒內沒下載完"
        return False, f"下載沒有完成（{why}，送出 {b['dl_sent']:,}/{b['dl_total']:,} bytes）"
    t_done = b["dl_done"]
    # reboot: reports stop for a while, then the board comes back IDLE (and hub_node reports its FW again)
    # still reporting COMPLETED well after the download = the board rejected the image (no reboot)
    rejected = lambda: (b["state"] == "OTA_STATE_DOWNLOAD_FIRMWARE_COMPLETED" and b["seen"] > t_done
                        and time.time() - t_done > 2 * CFG["gap_s"] and time.time() - b["seen"] < CFG["gap_s"])
    went_down = wait_for(lambda: time.time() - b["seen"] > CFG["gap_s"] or rejected(), CFG["reboot_s"])
    with LOCK:
        if went_down and rejected():
            return False, "下載完但沒有重開（板子拒收映像，例如檢查碼錯），狀態停在 COMPLETED；要按 RST"
    if not went_down:
        return False, f"下載完 {CFG['reboot_s']:.0f} 秒內沒有重開機"
    back = wait_for(lambda: b["seen"] > t_done + CFG["gap_s"] and online(b) and b["state"] == "OTA_STATE_IDLE"
                    and (not CFG["expect_fw"] or b["info_at"] > t_done), CFG["reboot_s"])
    if not back:
        return False, f"重開後 {CFG['reboot_s']:.0f} 秒內沒有回到 IDLE" + ("、也沒有回報 FW" if CFG["expect_fw"] else "")
    with LOCK:
        fw = b["fw"]
    if CFG["expect_fw"] and fw != CFG["expect_fw"]:
        return False, f"重開了，但 FW 是 {fw or '?'}，不是 {CFG['expect_fw']}（可能開回舊分區）"
    return True, f"FW {old_fw or '?'} → {fw or '?'}，用時 {time.time() - t_start:.0f} 秒"


def run_job():
    stop = False
    while True:
        with LOCK:
            if not JOB["queue"]:
                JOB.update(running=False, current=None)
                break
            ip = JOB["queue"].pop(0)
            JOB["current"] = ip
        b = board(ip)
        if stop:
            with LOCK:
                b["result"], b["note"] = "略過", "前面有板子失敗（要繼續請用 --keep-going）"
            continue
        with LOCK:
            b["result"] = "更新中"
        log(f"── 開始更新 {name(ip)}")
        try:
            ok, note = update_one(ip)
        except Exception as e:          # never leave the job hanging
            ok, note = False, f"伺服器例外：{e!r}"
        with LOCK:
            b["result"], b["note"] = ("成功" if ok else "失敗"), note
        log(f"── {name(ip)}：{'成功' if ok else '失敗'}，{note}")
        if not ok and not CFG["keep_going"]:
            stop = True
    log("排程結束")


def serve(a):
    CFG.update(bin=os.path.abspath(a.bin), expect_fw=a.expect_fw, keep_going=a.keep_going)
    for k in ("online_s", "start_s", "download_s", "reboot_s", "gap_s", "poll_s"):
        if getattr(a, k) is not None:
            CFG[k] = getattr(a, k)
    if not os.path.isfile(CFG["bin"]):
        sys.exit(f"找不到韌體檔：{CFG['bin']}")
    CFG["data"] = open(CFG["bin"], "rb").read()
    if os.path.basename(CFG["bin"]).lower().startswith("firmware"):
        print("注意：看起來是 firmware.bin。要推的是 ota.bin（多 4 bytes 檢查碼），否則板子會報 checksum wrong。", flush=True)

    class Quiet(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            if isinstance(sys.exc_info()[1], (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
                return            # 板子回報完 0.5 秒就主動斷線，屬正常
            super().handle_error(request, client_address)

    srv = Quiet((a.host, a.port), Handler)
    log(f"OTA 伺服器啟動：port {a.port}，推送 {CFG['bin']}（{len(CFG['data']):,} bytes），預期 FW {CFG['expect_fw'] or '（未指定）'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def api(server, path, body=None):
    req = urllib.request.Request(server.rstrip("/") + path, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--bin", required=True); s.add_argument("--port", type=int, default=3000); s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--expect-fw"); s.add_argument("--keep-going", action="store_true")
    for k, h in (("online_s", "幾秒沒回報算離線"), ("start_s", "送 start_ota 後多久要開始下載"), ("download_s", "下載時限"),
                 ("reboot_s", "下載完到重開回來的時限"), ("gap_s", "幾秒沒回報算正在重開"), ("poll_s", "排程檢查間隔")):
        s.add_argument("--" + k.replace("_", "-"), dest=k, type=float, help=h)
    st = sub.add_parser("status"); st.add_argument("--server", default="http://127.0.0.1:3000"); st.add_argument("--json", action="store_true")
    u = sub.add_parser("update"); u.add_argument("targets", nargs="+"); u.add_argument("--server", default="http://127.0.0.1:3000")
    t = sub.add_parser("trigger"); t.add_argument("ip")
    a = ap.parse_args()
    if a.cmd == "serve":
        serve(a)
    elif a.cmd == "status":
        code, txt = api(a.server, "/api/status" if a.json else "/status"); print(txt)
    elif a.cmd == "update":
        code, txt = api(a.server, "/api/update", {"targets": a.targets}); print(txt); sys.exit(0 if code == 200 else 1)
    else:
        send_start(a.ip); print(f"已送出 start_ota 給 {a.ip}:5000")


if __name__ == "__main__":
    main()
