"""Local web demo for both bots: one page, two tabs, answers via the logged-in `claude` CLI.

    cd rdbot && rag-qna/.venv/bin/python demo/server.py      # then open http://127.0.0.1:8765

Binds to 127.0.0.1 only — it runs on your Claude subscription, so it is not for sharing.
Standard library only (plus the two projects).
"""

from __future__ import annotations

import json
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "rag-qna"), str(REPO / "care-navigator")]

from navigator.agent import CliNavigator  # noqa: E402
from rxdx_qna.answer import CliQnABot  # noqa: E402
from rxdx_qna.index import Retriever  # noqa: E402

HOST, PORT = "127.0.0.1", 8765
PAGE = (Path(__file__).resolve().parent / "index.html").read_bytes()

retriever = Retriever()
sessions: dict[str, object] = {}
lock = threading.Lock()


def session(kind: str, sid: str):
    key = f"{kind}:{sid}"
    with lock:
        if key not in sessions:
            sessions[key] = CliQnABot(retriever) if kind == "qna" else CliNavigator()
        return sessions[key]


def answer(kind: str, sid: str, message: str) -> dict:
    bot = session(kind, sid)
    if kind == "qna":
        a = bot.ask(message)
        return {
            "text": a.text,
            "sources": [{"n": s.n, "title": s.title, "url": s.url, "reviews": s.reviews} for s in a.sources],
        }
    t = bot.ask(message)
    return {
        "text": t.text,
        "emergency": t.emergency,
        "tool_calls": [
            {"name": c.name, "args": {k: v for k, v in c.input.items() if v is not None}, "error": c.is_error,
             "summary": _summary(c)}
            for c in t.tool_calls
        ],
    }


def _summary(c) -> str:
    if c.is_error:
        return c.output
    data = json.loads(c.output)
    if c.name == "find_doctors":
        return f"{data['total_matches']} match(es)"
    if c.name == "get_doctor":
        return data["name"]
    if c.name == "prepare_booking_request":
        return "draft ready"
    return f"{len(next(iter(data.values())))} item(s)"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        kind = {"/api/qna": "qna", "/api/nav": "nav"}.get(self.path)
        if kind is None:
            return self._send(404, b"not found", "text/plain")
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            message = str(req.get("message", "")).strip()[:2000]
            sid = str(req.get("session") or uuid.uuid4())
            if not message:
                raise ValueError("empty message")
            out = answer(kind, sid, message)
            self._send(200, json.dumps(out, ensure_ascii=False).encode(), "application/json")
        except Exception as e:  # surface the reason in the page rather than hanging it
            self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")


if __name__ == "__main__":
    print(f"RxDx bots demo on http://{HOST}:{PORT}  (Ctrl-C to stop)")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
