"""Local web demo for both bots, answered through the logged-in `claude` CLI (no API key).

    cd rdbot && rag-qna/.venv/bin/python demo/server.py      # then open http://127.0.0.1:8765

Binds to 127.0.0.1 only — it runs on your Claude subscription, so it is not for sharing.
The hosted version is app.py (API backend). Both serve web/index.html through web/core.py.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from web import core  # noqa: E402

HOST, PORT = "127.0.0.1", 8765


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, core.page(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        kind = {"/api/qna": "qna", "/api/nav": "nav"}.get(self.path)
        if kind is None:
            return self._send(404, b"not found", "text/plain")
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            message = str(req.get("message", "")).strip()
            if not message:
                raise ValueError("empty message")
            out = core.answer(kind, message, req.get("history"), backend="cli")
            self._send(200, json.dumps(out, ensure_ascii=False).encode(), "application/json")
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")


if __name__ == "__main__":
    print(f"RxDx bots demo on http://{HOST}:{PORT}  (Ctrl-C to stop)")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
