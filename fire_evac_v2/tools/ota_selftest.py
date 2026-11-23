"""Self-test of ota_server.py with 8 simulated boards (no hardware). Prints a markdown report.

python ota_selftest.py [port]      default 3000; starts ota_server.py itself with short timeouts, stops it afterwards

Each fake board has its own loopback address 127.0.0.11..18 (so the server tells them apart by IP, as on the hotspot),
reports {"OTA_state": ...} like the SDK, posts /api/nodeinfo like hub_node, listens on <its ip>:5000 for start_ota,
downloads /api/uploadfile and checks it against the file the server was given. Then it "reboots" (goes quiet) and
comes back IDLE with FW 2.4. Three of them misbehave on purpose:
  1S  drops the connection halfway through the download        -> download interrupted
  2E  downloads everything but rejects the image (stays COMPLETED, never reboots, like a checksum error)
  2W  is already stuck in COMPLETED before the run (needs RST)  -> refused up front
Run 1: update all --keep-going   -> 5 succeed, the 3 above fail with the right reason
Run 2: update all (stop at the first failure) on fresh boards with 1S failing -> 1N 1E ok, 1S fails, the rest skipped
"""
import sys, os, json, time, socket, threading, subprocess, tempfile, hashlib, urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
HERE = os.path.dirname(os.path.abspath(__file__))
SLOTS = ["1N", "1E", "1S", "1W", "2N", "2E", "2S", "2W"]
REPORT_S = 0.3


class FakeBoard:
    def __init__(self, k, slot, mode, data):
        self.ip, self.slot, self.mode, self.data = f"127.0.0.{11 + k}", slot, mode, data
        self.mac = f"0200000000{11 + k:02X}"
        self.state = "OTA_STATE_DOWNLOAD_FIRMWARE_COMPLETED" if mode == "stuck" else "OTA_STATE_IDLE"
        self.fw, self.down, self.alive, self.got = "2.3", False, True, None
        self.lsock = socket.socket(); self.lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.lsock.bind((self.ip, 5000)); self.lsock.listen(2); self.lsock.settimeout(0.5)
        for f in (self.report_loop, self.listen_loop):
            threading.Thread(target=f, daemon=True).start()

    def post(self, path, body):
        s = socket.create_connection(("127.0.0.1", PORT), timeout=3, source_address=(self.ip, 0))
        data = json.dumps(body).encode()
        s.sendall(f"POST {path} HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nContent-Length: {len(data)}\r\n"
                  f"Connection: close\r\n\r\n".encode() + data)
        s.recv(256); s.close()

    def report_loop(self):
        n = 0
        while self.alive:
            if not self.down:
                try:
                    self.post("/api/connectedclients", {"OTA_state": self.state})
                    if n % 5 == 0:
                        self.post("/api/nodeinfo", {"mac": self.mac, "fw": self.fw, "slot": self.slot, "ota": self.state})
                except OSError:
                    pass
                n += 1
            time.sleep(REPORT_S)

    def listen_loop(self):
        while self.alive:
            try:
                c, _ = self.lsock.accept()
            except OSError:
                continue
            msg = c.recv(64); c.sendall(msg); c.close()
            if b"start_ota" in msg and self.state == "OTA_STATE_IDLE":
                threading.Thread(target=self.update, daemon=True).start()

    def update(self):
        self.state = "OTA_STATE_DOWNLOAD_FIRMWARE_IN_PROGRESS"
        s = socket.create_connection(("127.0.0.1", PORT), timeout=5, source_address=(self.ip, 0))
        s.sendall(b"GET /api/uploadfile HTTP/1.1\r\nHost: x\r\n\r\n")
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += s.recv(4096)
        head, body = buf.split(b"\r\n\r\n", 1)
        total = int([l for l in head.split(b"\r\n") if l.lower().startswith(b"content-length")][0].split(b":")[1])
        while len(body) < total:
            if self.mode == "cut" and len(body) > total // 2:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")   # RST
                s.close(); self.state = "OTA_STATE_DOWNLOAD_FIRMWARE_COMPLETED"; self.got = len(body); return
            chunk = s.recv(65536)
            if not chunk:
                break
            body += chunk
        s.close()
        self.got = hashlib.sha256(body).hexdigest() == hashlib.sha256(self.data).hexdigest()
        self.state = "OTA_STATE_DOWNLOAD_FIRMWARE_COMPLETED"
        if self.mode == "reject":
            return                                         # stays COMPLETED and keeps reporting
        self.state = "OTA_STATE_REBOOT"
        self.down = True; time.sleep(2.5)                  # rebooting: silent
        self.fw, self.state, self.down = "2.4", "OTA_STATE_IDLE", False

    def close(self):
        self.alive = False; self.lsock.close()


def api(path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def run(modes, keep_going, binpath, data, out, title, expect):
    args = [sys.executable, os.path.join(HERE, "ota_server.py"), "serve", "--bin", binpath, "--port", str(PORT), "--host", "127.0.0.1",
            "--expect-fw", "2.4", "--online-s", "2", "--start-s", "3", "--download-s", "10", "--reboot-s", "8", "--gap-s", "1",
            "--poll-s", "0.1"] + (["--keep-going"] if keep_going else [])
    logpath = os.path.join(tempfile.gettempdir(), f"ota_selftest_server_{os.getpid()}.log")
    logf = open(logpath, "w", encoding="utf-8")
    srv = subprocess.Popen(args, stdout=logf, stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    boards = []
    try:
        for _ in range(50):
            try:
                api("/api/status"); break
            except OSError:
                time.sleep(0.1)
        boards = [FakeBoard(k, s, modes.get(s, "ok"), data) for k, s in enumerate(SLOTS)]
        time.sleep(2.5)                                    # let every board report and send node info
        code, msg = api("/api/update", {"targets": ["all"]})
        t0 = time.time()
        while time.time() - t0 < 120:
            snap = json.loads(api("/api/status")[1])
            if not snap["job"]["running"]:
                break
            time.sleep(0.5)
        code_s, text = api("/status")
        snap = json.loads(api("/api/status")[1])
    finally:
        for b in boards:
            b.close()
        srv.terminate(); srv.wait(timeout=10)
    got = {r["slot"]: (r["result"], r["note"]) for r in snap["boards"]}
    ok = all(got.get(s, ("", ""))[0] == want for s, want in expect.items())
    out.append(f"## {title}\n")
    out.append(f"`update all` → {code}：{msg}\n")
    out.append("| 板子 | IP | 預期 | 結果 | 原因／說明 | 板子收到的檔案 |\n|---|---|---|---|---|---|")
    for b in boards:
        res, note = got.get(b.slot, ("?", ""))
        if b.got is None:
            recv = "—"
        elif isinstance(b.got, bool):
            recv = "完整、sha256 相同" if b.got else "內容不符"
        else:
            recv = f"中斷，只收到 {b.got:,} bytes"
        out.append(f"| {b.slot} | {b.ip} | {expect[b.slot]} | {res}{'' if res == expect[b.slot] else ' ≠'} | {note} | {recv} |")
    out.append("\n`python ota_server.py status` 的畫面：\n```\n" + text + "\n```\n")
    logf.close(); lines = open(logpath, encoding="utf-8").read().splitlines(); os.unlink(logpath)
    out.append("伺服器 log（節錄）：\n```\n" + "\n".join(l for l in lines if "──" in l or "失敗" in l or "中斷" in l)[:3000] + "\n```\n")
    out.append(f"判定：{'通過' if ok else '**不通過**'}\n")
    return ok


def main():
    data = os.urandom(300_000) + b"\x12\x34\x56\x78"       # stands in for ota.bin (firmware + 4-byte checksum)
    binpath = os.path.join(tempfile.gettempdir(), "ota_selftest_ota.bin")
    open(binpath, "wb").write(data)
    out = [f"# OTA 伺服器自測（{time.strftime('%Y-%m-%d %H:%M')}，port {PORT}，8 台模擬板子，假 ota.bin {len(data):,} bytes）\n"]
    ok1 = run({"1S": "cut", "2E": "reject", "2W": "stuck"}, True, binpath, data, out, "第 1 輪：update all --keep-going，3 台故意出錯",
              {"1N": "成功", "1E": "成功", "1S": "失敗", "1W": "成功", "2N": "成功", "2E": "失敗", "2S": "成功", "2W": "失敗"})
    ok2 = run({"1S": "cut"}, False, binpath, data, out, "第 2 輪：update all（預設一台失敗就停），1S 下載中斷",
              {"1N": "成功", "1E": "成功", "1S": "失敗", "1W": "略過", "2N": "略過", "2E": "略過", "2S": "略過", "2W": "略過"})
    os.unlink(binpath)
    out.append(f"**總結：{'全部通過' if ok1 and ok2 else '有失敗項目'}**")
    print("\n".join(out))
    return ok1 and ok2


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
