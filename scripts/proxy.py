#!/usr/bin/env python3
"""本机 Kimi 代理，给网页版 AI 搭配用。

Kimi 的接口不返回 CORS 头，浏览器无法直连；而部署在云上的代理（如
Cloudflare Worker）会被 Kimi 的反滥用防护拦截（403）。所以走本机：
本机直连 Kimi 是正常的。

跑起来：
    .venv/bin/python scripts/proxy.py          # 监听 127.0.0.1:8643

然后本地打开网站（http://localhost:8642），AI Styling 的 API 地址填
http://127.0.0.1:8643 即可。Key 由本脚本从 .env 读取并注入，
浏览器里不用填、也不会存任何密钥。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_ORIGINS = {"http://localhost:8642", "http://127.0.0.1:8642"}
PORT = 8643


def load_env() -> tuple[str, str]:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
    key = os.environ.get("KIMI_CODE_API_KEY")
    if not key:
        sys.exit("缺少 KIMI_CODE_API_KEY（见 .env）")
    base = os.environ.get("KIMI_CODE_BASE_URL", "https://api.kimi.com/coding/v1").rstrip("/")
    return key, base


class Handler(BaseHTTPRequestHandler):
    key = ""
    base = ""

    def _cors(self, origin: str) -> None:
        self.send_header("Access-Control-Allow-Origin", origin if origin in ALLOWED_ORIGINS else "null")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Vary", "Origin")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors(self.headers.get("Origin", ""))
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        origin = self.headers.get("Origin", "")
        if origin not in ALLOWED_ORIGINS:
            self.send_response(403)
            self._cors(origin)
            self.end_headers()
            self.wfile.write(b"origin not allowed")
            return

        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as f:
            f.write(body)
            req_path = f.name
        # 用 curl 转发：与 kimi_ai.py 一致，避开系统代理的自签证书问题
        proc = subprocess.run(
            ["curl", "-sS", "-m", "300", f"{self.base}{self.path}",
             "-H", f"Authorization: Bearer {self.key}",
             "-H", "Content-Type: application/json",
             "-d", f"@{req_path}"],
            capture_output=True, timeout=320,
        )
        Path(req_path).unlink(missing_ok=True)

        payload = proc.stdout or json.dumps(
            {"error": {"message": proc.stderr.decode("utf-8", "replace")[:300]}}
        ).encode()
        self.send_response(200 if proc.returncode == 0 else 502)
        self._cors(origin)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("proxy: " + fmt % args + "\n")


def main() -> None:
    Handler.key, Handler.base = load_env()
    print(f"Kimi 本机代理已启动 → http://127.0.0.1:{PORT}")
    print(f"转发到 {Handler.base}，仅接受来自 {' / '.join(sorted(ALLOWED_ORIGINS))} 的请求")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
