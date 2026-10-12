# rdbot

AI projects built on the public content of [rxdx.in](https://rxdx.in) (RxDx Clinics, Bengaluru).

| # | Project | What it is |
| --- | --- | --- |
| 1 | [`rag-qna/`](rag-qna/) | RAG question-answering bot: hybrid BM25 + embedding retrieval over the clinic's doctors, branches and services, with cited answers from Claude |
| 2 | *coming next* | |

Independent work — not affiliated with RxDx, and not medical advice.

**No credentials are committed.** Each project reads its API keys from environment variables;
`.env` files are gitignored, and `rag-qna/tests/test_no_secrets.py` scans the whole repository
for anything that looks like a key or token.
