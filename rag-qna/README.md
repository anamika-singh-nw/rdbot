# RxDx QnA bot (RAG)

Ask questions about RxDx Clinics — doctors, specialities, branches, schedules, services —
and get short answers where every claim is cited back to the rxdx.in page it came from.

```
$ python -m rxdx_qna ask "Is there a dermatologist in Whitefield on Mondays?"
Yes — Dr Madhu R, a dermatologist, sees patients in-clinic at RxDx Clinics, Whitefield on
Monday, Thursday and Saturday.[1] Schedules can change, so please confirm on
+91 901 409 1111 before visiting.[2]

Sources:
  [1] Dr Madhu R — https://rxdx.in/consultants/dr-madhu-r/
  [2] Contact RxDx Clinics — https://rxdx.in/contact-us/
```

*(Illustrative output. The facts shown are the ones in the knowledge base.)*

> Independent project built from rxdx.in's public pages. It is not affiliated with RxDx, and it does not
> give medical advice.

## How it works

```
data/rxdx.json ──► chunking ──► 427 chunks ──┬─► BM25 (exact terms: names, clinics)
 (343 records)                               └─► bge-small embeddings (meaning)
                                                        │
question ──► hybrid search (reciprocal-rank fusion) ──► top 8 chunks
                                                        │
                       Claude (document blocks, citations on) ──► answer + [n] sources
```

**Chunking** (`rxdx_qna/chunking.py`): there are four kinds of record, and each is handled differently.
- **Doctors (254):** one chunk per doctor, holding the profile plus a readable schedule. A question about a doctor almost always needs both.
- **Pages (26):** split into ~1,200-character windows of body lines, overlapping by two lines.
- **Branch and speciality archives:** once the site chrome is removed, these are just lists of consultants.
- **Site chrome:** every page repeats the same enquiry forms, banners and blog teasers. Left in, that text would dominate retrieval, so any line seen in 10 or more records is dropped. The contact details it carried live on in a single `contact` chunk.

**Retrieval** (`rxdx_qna/index.py`): BM25 and dense embeddings, fused by rank. Each one alone is weaker on this corpus:

| retriever | hit@1 | hit@3 | hit@8 | MRR |
| --- | --- | --- | --- | --- |
| BM25 only | 0.67 | 0.80 | 0.90 | 0.75 |
| dense only | 0.77 | 0.93 | 1.00 | 0.85 |
| **hybrid** | **0.83** | **0.93** | **1.00** | **0.89** |

These scores come from `eval/retrieval.jsonl`: 30 questions covering named doctors, lay terms ("skin doctor", "kidney specialist"), branches, services and policies. With only 427 chunks, a numpy matrix is the whole vector store. A full scan takes under a millisecond, so a vector database would add nothing.

**Generation** (`rxdx_qna/answer.py`): the retrieved chunks are sent to `claude-opus-5-5` as `document` blocks with citations enabled. The API returns each sentence with the passage it quotes, which is more reliable than asking the model to write `[3]` markers itself. The system prompt sets four rules:
- Answer only from the documents provided.
- If the answer isn't there, say so and give the clinic's phone number.
- Don't diagnose or recommend treatment.
- For emergencies, send people to 108 first.

Conversation history is append-only, so each turn's documents stay with the question they answered. A follow-up like "what days is she in?" is retrieved together with the previous question. `fallbacks: "default"` is set so that if a safety classifier declines a request, it is retried on Anthropic's recommended fallback model rather than failing.

## Setup

Requires Python 3.10+.

```bash
cd rag-qna
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m rxdx_qna build          # chunks + embeds (~25s; downloads a 67 MB model once)
python -m rxdx_qna search "child specialist in Malleshwaram"   # retrieval only, no key needed
```

Answering needs Claude API access. Set it in your shell or in a `.env` you source yourself
(`.env` is gitignored; `.env.example` shows the variable name):

```bash
export ANTHROPIC_API_KEY=...       # or: ant auth login
python -m rxdx_qna ask "Do you do home sample collection?"
python -m rxdx_qna chat -v         # multi-turn; -v shows retrieved chunks and token usage
```

## Tests and evals

```bash
python -m pytest                   # 17 tests, offline, no API key
python eval/run_retrieval.py --misses
```

- `test_chunking` checks that chrome is stripped, schedules are present, day ranges ("Monday to Saturday") are expanded, and IDs are unique.
- `test_retrieval` fails if hit@8 drops below 0.95 or MRR below 0.80.
- `test_answer` checks the request shape, citation rendering, append-only history and refusal handling, using a stub client.
- `test_no_secrets` fails if anything that looks like an API key, token or private key is in the repository.

## Credentials

The only credential is the Anthropic API key. It is read from the environment by the SDK and never appears in code, logs or files. `test_no_secrets` enforces this on every test run.

## Limitations

- The knowledge base is a snapshot of rxdx.in from 2026-08-26 (`../data/rxdx.json`, shared with the other projects). Schedules change, so the bot tells users to confirm before visiting.
- The source has gaps: 12 doctors map to no branch, 25 have no published days, and clinic addresses and opening hours were not part of the scrape. The bot says it doesn't know rather than guessing.
- Answer quality has only been tested offline: retrieval against the eval set, and generation plumbing against a stub. A graded answer eval run against the live API is the next step.
