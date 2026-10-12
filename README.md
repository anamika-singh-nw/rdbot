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
