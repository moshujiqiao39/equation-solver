"""启动本地方程求解器。"""

from __future__ import annotations

import json
import socket
import sys
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from multiprocessing import Process, Queue, freeze_support
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
}

PREVIEW = None
MP_ENTRY = None


def ensure_sympy() -> None:
    try:
        import sympy  # noqa: F401
    except ImportError:
        import subprocess

        print("正在安装 SymPy，请稍候...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "sympy>=1.12"])


def pick_port(start: int = 8756) -> int:
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise SystemExit("没有可用的本地端口。")


def solve_guarded(payload: dict) -> dict:
    queue: Queue = Queue()
    process = Process(target=MP_ENTRY, args=(payload, queue))
    process.start()
    try:
        result = queue.get(timeout=30)
    except Exception:
        result = {
            "ok": False,
            "error": "求解超过 30 秒，已停止等待。可以降低次数、减少未知数，或把方程写得更具体。",
        }
    if process.is_alive():
        process.terminate()
        process.join(3)
    else:
        process.join(1)
    return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        try:
            print("[%s] %s" % (self.log_date_time_string(), fmt % args))
        except Exception:
            pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: dict, code: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        spec = FILES.get(path)
        if not spec:
            self._send(404, "未找到页面".encode("utf-8"), "text/plain; charset=utf-8")
            return
        name, content_type = spec
        folder = ROOT if name == "index.html" else STATIC
        self._send(200, (folder / name).read_bytes(), content_type)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            self._json({"ok": False, "error": "请求不是有效的 JSON。"})
            return
        try:
            if path == "/api/preview":
                result = PREVIEW(payload)
            elif path == "/api/solve":
                result = solve_guarded(payload)
            else:
                self._json({"ok": False, "error": "没有这个接口。"}, 404)
                return
        except Exception as exc:
            traceback.print_exc()
            result = {"ok": False, "error": f"服务出错：{exc}"}
        self._json(result)


def main() -> None:
    global PREVIEW, MP_ENTRY
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ensure_sympy()
    from solver import mp_entry, preview_request

    PREVIEW = preview_request
    MP_ENTRY = mp_entry
    port = pick_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print("方程求解器已启动", flush=True)
    print(f"在浏览器中打开：{url}", flush=True)
    print("关闭本窗口，或按 Ctrl+C，即可退出。", flush=True)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    freeze_support()
    main()
