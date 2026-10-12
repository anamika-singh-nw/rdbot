"""Hosted web app for both bots (Vercel, FastAPI). Answers via the Anthropic API.

Configuration, all through environment variables (Vercel → Project → Settings → Environment
Variables) — nothing secret lives in the repository:
    ANTHROPIC_API_KEY   required
    RATE_PER_HOUR       messages per visitor per hour (default 15)
    RATE_PER_DAY        messages per instance per day, a backstop (default 400)

Spend protection is layered. The limits here are per server instance and best-effort; the
hard guarantee is the monthly spend limit set on the API key in the Anthropic Console.

Local run:  pip install -r requirements.txt && ANTHROPIC_API_KEY=... uvicorn app:app
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

import anthropic
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from web import core

RATE_PER_HOUR = int(os.environ.get("RATE_PER_HOUR", "15"))
RATE_PER_DAY = int(os.environ.get("RATE_PER_DAY", "400"))

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

_lock = threading.Lock()
_per_ip: dict[str, deque] = defaultdict(deque)
_day: deque = deque()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _allow(ip: str) -> str | None:
    """None if allowed, else a message for the visitor."""
    now = time.time()
    with _lock:
        q = _per_ip[ip]
        while q and now - q[0] > 3600:
            q.popleft()
        while _day and now - _day[0] > 86400:
            _day.popleft()
        if len(_day) >= RATE_PER_DAY:
            return "The demo has reached its daily limit. Please try again tomorrow."
        if len(q) >= RATE_PER_HOUR:
            return f"You've reached the limit of {RATE_PER_HOUR} questions an hour for this demo. Please try again later."
        q.append(now)
        _day.append(now)
        if len(_per_ip) > 10_000:  # bound memory: drop idle visitors
            for k in [k for k, v in _per_ip.items() if not v]:
                del _per_ip[k]
    return None


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(core.page())


@app.get("/health")
def health():
    return {"ok": True, "api_key_configured": core.api_configured()}


async def _handle(kind: str, request: Request):
    if not core.api_configured():
        return JSONResponse({"error": "The bot isn't configured yet (no API key on the server)."}, 503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Bad request."}, 400)
    message = str(body.get("message", "")).strip()
    if not message:
        return JSONResponse({"error": "Please type a question."}, 400)
    if len(message) > core.MAX_MESSAGE:
        return JSONResponse({"error": f"Please keep questions under {core.MAX_MESSAGE} characters."}, 400)
    limited = _allow(_client_ip(request))
    if limited:
        return JSONResponse({"error": limited}, 429)
    try:
        # Sync SDK call; FastAPI runs plain functions in its threadpool via run_in_threadpool.
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(core.answer, kind, message, body.get("history"), "api")
    except anthropic.RateLimitError:
        return JSONResponse({"error": "The service is busy right now. Please try again in a minute."}, 503)
    except anthropic.APIStatusError as e:
        # Never echo upstream error bodies to visitors; they can include account details.
        print(f"anthropic error {e.status_code}")
        return JSONResponse({"error": "The bot couldn't answer just now. Please try again."}, 502)
    except anthropic.APIConnectionError:
        return JSONResponse({"error": "The bot couldn't reach its model. Please try again."}, 502)


@app.post("/api/qna")
async def qna(request: Request):
    return await _handle("qna", request)


@app.post("/api/nav")
async def nav(request: Request):
    return await _handle("nav", request)
