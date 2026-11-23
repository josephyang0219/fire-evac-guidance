"""筆電端 OTA 伺服器（配合 SDK AmebaOTA 函式庫，只用 Python 標準函式庫）。

板子那邊（AmebaOTA）的行為：
  1. 每約 4 秒 POST http://<筆電>:<port>/api/connectedclients，內容 {"OTA_state": "..."}。
  2. 在板子自己的 TCP 5000 等待，收到含 "start_ota" 的字串就開始更新。
  3. 更新時 GET http://<筆電>:<port>/api/uploadfile 下載韌體，寫入另一個韌體分區後重開機。

用法：
  python ota_server.py serve --bin firmware_v2.bin [--port 3000]
      顯示每台板子的 IP 與 OTA 狀態，並提供韌體下載。
  python ota_server.py trigger <板子IP>
      叫那台板子開始更新（另開一個視窗執行，serve 要保持開著）。

要推送的檔案是編譯後 ameba_pro2_tools/<版本>/ota.bin（firmware.bin 再加 4 bytes 檢查碼）。
推 firmware.bin 會在板子上出現「The checksume is wrong!」而不更新（2026-11-23 實測）。
加 --auto：板子回報 OTA_STATE_IDLE 時自動送 start_ota。
注意：板子更新失敗後狀態會停在 COMPLETED，要按 RST 回到 IDLE 才能再更新。
"""
import argparse, datetime, os, re, socket, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CLIENTS = {}          # ip -> (state, last_seen)
LOCK = threading.Lock()
BIN_PATH = None
AUTO = False          # --auto：板子回報 IDLE 時自動叫它更新（每台每次啟動伺服器只一次）
TRIGGERED = set()


def now():
    return datetime.datetime.now().strftime("%H:%M:%S")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _reply(self, code, body=b"", ctype="text/plain"):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        except (ConnectionResetError, ConnectionAbortedError):
            body = ""
        if self.path.startswith("/api/connectedclients"):
            states = re.findall(r'"OTA_state"\s*:\s*"([^"]+)"', body)
            state = states[-1] if states else "?"
            ip = self.client_address[0]
            with LOCK:
                old = CLIENTS.get(ip, (None, None))[0]
                CLIENTS[ip] = (state, now())
            if old != state:
                print(f"[{now()}] 板子 {ip}：{old or '（新連線）'} → {state}", flush=True)
                if AUTO and state == "OTA_STATE_IDLE" and ip not in TRIGGERED:
                    TRIGGERED.add(ip)
                    threading.Thread(target=send_start, args=(ip,), daemon=True).start()
            self._reply(200, b"ok")
        else:
            self._reply(404)

    def do_GET(self):
        if self.path.startswith("/api/uploadfile"):
            data = open(BIN_PATH, "rb").read()
            ip = self.client_address[0]
            print(f"[{now()}] 板子 {ip} 開始下載 {os.path.basename(BIN_PATH)}（{len(data):,} bytes）", flush=True)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                sent = 0
                for i in range(0, len(data), 4096):
                    self.wfile.write(data[i:i + 4096])
                    sent += len(data[i:i + 4096])
                print(f"[{now()}] 板子 {ip} 下載完成 {sent:,} bytes", flush=True)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
                print(f"[{now()}] 板子 {ip} 下載中斷：{e}", flush=True)
        elif self.path in ("/", "/status"):
            with LOCK:
                lines = [f"{ip}\t{st}\t{t}" for ip, (st, t) in sorted(CLIENTS.items())]
            self._reply(200, ("\n".join(lines) or "（還沒有板子連線）").encode("utf-8"), "text/plain; charset=utf-8")
        else:
            self._reply(404)


def send_start(ip):
    try:
        with socket.create_connection((ip, 5000), timeout=5) as s:
            s.sendall(b"start_ota")
        print(f"[{now()}] 已自動叫 {ip} 開始更新", flush=True)
    except OSError as e:
        print(f"[{now()}] 叫 {ip} 更新失敗：{e}", flush=True)


def serve(args):
    global BIN_PATH, AUTO
    AUTO = args.auto
    BIN_PATH = os.path.abspath(args.bin)
    if not os.path.isfile(BIN_PATH):
        sys.exit(f"找不到韌體檔：{BIN_PATH}")
    class Quiet(ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            if isinstance(sys.exc_info()[1], (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
                return            # 板子回報完 0.5 秒就主動斷線，屬正常
            super().handle_error(request, client_address)

    srv = Quiet(("0.0.0.0", args.port), Handler)
    print(f"[{now()}] OTA 伺服器啟動：port {args.port}，推送檔案 {BIN_PATH}（{os.path.getsize(BIN_PATH):,} bytes）", flush=True)
    print("        板子連上後會顯示 IP 與狀態；另開視窗執行  python ota_server.py trigger <板子IP>", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def trigger(args):
    with socket.create_connection((args.ip, 5000), timeout=5) as s:
        s.sendall(b"start_ota")
        s.settimeout(3)
        try:
            echo = s.recv(64)
        except socket.timeout:
            echo = b""
    print(f"已送出 start_ota 給 {args.ip}:5000，板子回應：{echo!r}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("serve"); a.add_argument("--bin", required=True); a.add_argument("--port", type=int, default=3000)
    a.add_argument("--auto", action="store_true")
    b = sub.add_parser("trigger"); b.add_argument("ip")
    args = ap.parse_args()
    (serve if args.cmd == "serve" else trigger)(args)


if __name__ == "__main__":
    main()
