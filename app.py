"""Hosted web app for both bots (Vercel, FastAPI). Bedrock or Anthropic API.

Configuration, all through environment variables (Vercel → Project → Settings → Environment
Variables) — nothing secret lives in the repository:
    BOT_BACKEND        bedrock for AWS, api for Anthropic (default)
    AWS_ROLE_ARN       required for Bedrock; scoped Vercel OIDC role
    BEDROCK_MODEL_ID   deployed model: us.amazon.nova-lite-v1:0
    AWS_REGION         deployed region: us-east-1
    ANTHROPIC_API_KEY   required only for the api backend
    RATE_PER_HOUR       messages per visitor per hour (default 15)
    RATE_PER_DAY        messages per instance per day, a backstop (default 400)

Spend protection is layered. The limits here are per server instance and best-effort; the
AWS is kept on its Free account plan, which stops when credits expire or run out.
For Anthropic, set a monthly spend limit in the Anthropic Console.

Local run:  pip install -r requirements.txt && ANTHROPIC_API_KEY=... uvicorn app:app
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

# Vercel's filesystem is read-only except /tmp. The embedding model is downloaded from
# Hugging Face on first use, and both the hub client and fastembed default to caches under
# $HOME — so point them at /tmp before anything imports them.
os.environ.setdefault("HF_HOME", "/tmp/hf")
os.environ.setdefault("FASTEMBED_CACHE_PATH", "/tmp/fastembed")

import anthropic
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from web import core
from web import portfolio as portfolio_content
from web import live_demos

RATE_PER_HOUR = int(os.environ.get("RATE_PER_HOUR", "15"))
RATE_PER_DAY = int(os.environ.get("RATE_PER_DAY", "400"))

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/portfolio-assets", StaticFiles(directory=core.REPO / "web" / "portfolio_assets"), name="portfolio-assets")

_lock = threading.Lock()
_per_ip: dict[str, deque] = defaultdict(deque)
_day: deque = deque()


def _html(content: str | bytes) -> HTMLResponse:
    """Attach the same privacy controls to every public HTML page."""
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    content = content.replace("</head>", '<link rel="stylesheet" href="/portfolio-assets/privacy.css"><script defer src="/portfolio-assets/privacy.js?v=2"></script></head>')
    content = content.replace("</body>", '<aside class="privacy-links" aria-label="Privacy controls"><a href="/privacy">Privacy &amp; cookies</a><button type="button" data-cookie-settings>Cookie settings</button><button type="button" data-privacy-reset>Withdraw AI permission / reset</button></aside></body>')
    return HTMLResponse(content, headers={"Referrer-Policy": "strict-origin-when-cross-origin", "X-Content-Type-Options": "nosniff"})


@app.get("/privacy", response_class=HTMLResponse)
def privacy_notice():
    return _html((core.REPO / "web" / "privacy.html").read_bytes())


@app.get("/enquiry", response_class=HTMLResponse)
def project_enquiry():
    return _html((core.REPO / "web" / "enquiry.html").read_bytes())


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _allow(ip: str) -> str | None:
    """None if allowed, else a message for the visitor."""
    now = time.time()
    with _lock:
        for key in [key for key, values in _per_ip.items() if not values or now - values[-1] > 3600]:
            del _per_ip[key]
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
def index(request: Request):
    if request.url.hostname == "anamikasingh.vercel.app":
        return _html((core.REPO / "web" / "portfolio.html").read_bytes())
    return _html(core.page())


@app.get("/bots", response_class=HTMLResponse)
def bots():
    return _html(core.page())


@app.get("/portfolio", response_class=HTMLResponse)
def portfolio():
    return _html((core.REPO / "web" / "portfolio.html").read_bytes())


@app.get("/portfolio/deck")
def portfolio_deck():
    return FileResponse(
        core.REPO / "outputs" / "anamika-singh-rxdx-rag-portfolio.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="Anamika-Singh-RxDx-RAG-Case-Study.pptx",
    )


@app.get("/portfolio/linkedin", response_class=PlainTextResponse)
def linkedin_copy():
    return PlainTextResponse(portfolio_content.LINKEDIN_COPY)


@app.get("/portfolio/{project}", response_class=HTMLResponse)
def project_case(project: str):
    page = portfolio_content.case_page(project)
    if page is None:
        return HTMLResponse("Project not found. <a href='/portfolio'>View all projects</a>.", status_code=404)
    return _html(page)


@app.get("/health")
def health(deep: bool = False):
    out = {"ok": True, "api_key_configured": core.api_configured(),
           "backend": os.environ.get("BOT_BACKEND", "api")}
    if deep:  # exercises retrieval and the tools without calling the model (no cost)
        t = time.time()
        out["retrieval_top"] = core.retriever().search("dermatologist in Whitefield", k=1)[0].chunk.id
        out["tool_ok"] = '"total_matches"' in core.toolbox().run(
            "find_doctors",
            {"speciality": "ENT", "branch": None, "day": "Saturday", "mode": "any", "language": None, "name": None},
        )
        out["seconds"] = round(time.time() - t, 2)
    return out


async def _handle(kind: str, request: Request):
    if not core.api_configured():
        return JSONResponse({"error": "The bot isn't configured yet (API key or AWS role missing on the server)."}, 503)
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

        backend = os.environ.get("BOT_BACKEND", "api")
        if backend == "bedrock":
            return await run_in_threadpool(core.answer, kind, message, body.get("history"), backend,
                                          request.headers.get("x-vercel-oidc-token"))
        return await run_in_threadpool(core.answer, kind, message, body.get("history"), backend)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        print(f"bedrock error {code}")
        if code in ("ThrottlingException", "ServiceUnavailableException"):
            return JSONResponse({"error": "The service is busy right now. Please try again in a minute."}, 503)
        return JSONResponse({"error": "The bot couldn't answer just now. Please try again."}, 502)
    except BotoCoreError:
        return JSONResponse({"error": "The bot couldn't reach its model. Please try again."}, 502)
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


@app.post("/api/portfolio/{project}")
async def portfolio_chat(project: str, request: Request):
    if project not in live_demos.PROJECT_TOOLS:
        return JSONResponse({"error": "Unknown demo project."}, 404)
    if not os.environ.get("AWS_ROLE_ARN"):
        return JSONResponse({"error": "The live demo's AWS connection isn't configured yet."}, 503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Send a valid JSON request."}, 400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "Send a message object."}, 400)
    message = body.get("message", "")
    history, state = body.get("history", []), body.get("state", {})
    if (not isinstance(message, str) or not message.strip() or len(message) > core.MAX_MESSAGE
            or not isinstance(history, list) or len(history) > core.MAX_HISTORY
            or not isinstance(state, dict)):
        return JSONResponse({"error": "Provide a question under 1,000 characters and valid recent history."}, 400)
    limited = _allow(_client_ip(request))
    if limited:
        return JSONResponse({"error": limited}, 429)
    from starlette.concurrency import run_in_threadpool
    try:
        return await run_in_threadpool(live_demos.answer, project, message.strip(), history, state,
                                      request.headers.get("x-vercel-oidc-token"))
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "Unknown")
        print(f"live demo AWS error {code}")
        status = 503 if code in ("ThrottlingException", "ServiceUnavailableException") else 502
        return JSONResponse({"error": "The live assistant couldn't answer just now. Please try again shortly."}, status)
    except BotoCoreError:
        return JSONResponse({"error": "The live assistant couldn't reach AWS. Please try again."}, 502)
