# rdbot

Two AI projects built on the public content of [rxdx.in](https://rxdx.in) (RxDx Clinics, Bengaluru).

| # | Project | What it is |
| --- | --- | --- |
| 1 | [`rag-qna/`](rag-qna/) | RAG question-answering bot: hybrid BM25 + embedding retrieval over the clinic's doctors, branches and services, with cited answers from Claude |
| 2 | [`care-navigator/`](care-navigator/) | Tool-use agent: turns a patient's need and constraints (area, day, language, online/in-clinic) into specific doctors with real availability, and drafts a booking request — with a deterministic emergency screen in front of the model |

Independent work — not affiliated with RxDx, and not medical advice.

**No credentials are committed.** Each project reads its API keys from environment variables;
`.env` files are gitignored, and both projects' test suites (`tests/test_no_secrets.py`) scan the
whole repository for anything that looks like a key or token.

Both projects share one knowledge base, [`data/rxdx.json`](data/) — a 2026-08-26 snapshot of
rxdx.in (254 doctors, 14 branches, 49 specialities, 26 service pages).

## Try them in a browser (local demo)

```bash
rag-qna/.venv/bin/python demo/server.py     # after setting up rag-qna (see its README)
# open http://127.0.0.1:8765
```

One page with a tab for each bot. Answers come through your logged-in `claude` CLI, so no
API key is needed. The server only listens on this computer and runs on your Claude
subscription, so it's for demos, not for sharing.

## Hosted version

`app.py` serves the same page on Vercel, answered through the Anthropic API. The key is set
only in Vercel's environment variables (`ANTHROPIC_API_KEY`), never in the repository. Each
visitor is limited to 15 questions an hour (`RATE_PER_HOUR`); the hard cost ceiling is the
monthly spend limit on the key in the Anthropic Console. The search index (`rag-qna/index/`)
is committed so the server doesn't rebuild it; a test fails if it goes stale.
