"""Shared request handling for the browser page — used by the hosted app (API backend) and
the local demo server (claude-CLI backend).

Stateless by design: hosting can route consecutive messages to different instances, so the
page sends the recent conversation with each message and a fresh bot is seeded from it.
Only plain text is replayed — never thinking blocks or tool payloads — so each request is a
self-contained conversation from the model's point of view.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "rag-qna"), str(REPO / "care-navigator")]

from navigator.agent import BedrockNavigator, CliNavigator, Navigator  # noqa: E402
from navigator.tools import Toolbox  # noqa: E402
from rxdx_qna.answer import BedrockQnABot, CliQnABot, QnABot  # noqa: E402

MAX_MESSAGE = 1000
MAX_HISTORY = 6  # messages (3 exchanges)
MAX_HISTORY_CHARS = 2000

_retriever = None
_toolbox = None


def retriever():
    global _retriever
    if _retriever is None:
        from rxdx_qna.index import Retriever

        _retriever = Retriever()
    return _retriever


def toolbox():
    global _toolbox
    if _toolbox is None:
        _toolbox = Toolbox()
    return _toolbox


def clean_history(raw) -> list[dict]:
    out = []
    for m in (raw or [])[-MAX_HISTORY:]:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        text = str(m.get("text", "")).strip()[:MAX_HISTORY_CHARS]
        if text:
            out.append({"role": m["role"], "text": text})
    while out and out[0]["role"] != "user":  # the API requires a user turn first
        out.pop(0)
    return out


def _seed_api(bot, history: list[dict]):
    bot.messages = [{"role": m["role"], "content": m["text"]} for m in history]


def answer(kind: str, message: str, history: list[dict], backend: str, oidc_token: str | None = None) -> dict:
    message = message.strip()[:MAX_MESSAGE]
    history = clean_history(history)
    last_user = next((m["text"] for m in reversed(history) if m["role"] == "user"), None)

    if kind == "qna":
        if backend in ("cli", "bedrock"):
            if backend == "bedrock":
                from rxdx_qna import bedrock
                bot = BedrockQnABot(retriever(), client=bedrock.client(oidc_token))
            else:
                bot = CliQnABot(retriever())
            pairs = zip(history[::2], history[1::2])
            bot.history = [(u["text"], a["text"]) for u, a in pairs if u["role"] == "user"]
        else:
            bot = QnABot(retriever())
            _seed_api(bot, history)
        bot._last_question = last_user
        a = bot.ask(message)
        return {
            "text": a.text,
            "sources": [{"n": s.n, "title": s.title, "url": s.url, "reviews": s.reviews} for s in a.sources],
        }

    if backend == "cli":
        bot = CliNavigator(toolbox())
        bot.transcript = [f"{'PATIENT' if m['role'] == 'user' else 'YOU'}: {m['text']}" for m in history]
    elif backend == "bedrock":
        from navigator import bedrock
        bot = BedrockNavigator(toolbox(), client=bedrock.client(oidc_token))
        bot.messages = [{"role": m["role"], "content": [{"text": m["text"]}]} for m in history]
    else:
        bot = Navigator(toolbox())
        _seed_api(bot, history)
    t = bot.ask(message)
    return {
        "text": t.text,
        "emergency": t.emergency,
        "tool_calls": [
            {"name": c.name, "args": {k: v for k, v in c.input.items() if v is not None},
             "error": c.is_error, "summary": _summary(c)}
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


def page() -> bytes:
    return (REPO / "web" / "index.html").read_bytes()


def api_configured() -> bool:
    if os.environ.get("BOT_BACKEND", "api") == "bedrock":
        return bool(os.environ.get("AWS_ROLE_ARN"))
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
