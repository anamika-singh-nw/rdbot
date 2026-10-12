"""Retrieval eval: does the right chunk land in the top k? Runs offline, no API key.

    python eval/run_retrieval.py            # hit@1 / hit@3 / hit@8 and MRR
    python eval/run_retrieval.py --misses   # also list the questions that missed at k=8

An expectation is either a chunk-id prefix ("doctor:dr-chirag-d", "page:home-healthcare")
or "dept:<text>", which accepts any doctor whose department line contains that text — for a
question like "kidney specialist", any nephrologist is a correct retrieval.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rxdx_qna.index import Retriever  # noqa: E402

KS = (1, 3, 8)


def matches(chunk, expect: list[str]) -> bool:
    for e in expect:
        if e.startswith("dept:"):
            if chunk.kind == "doctor" and e[5:].lower() in chunk.text.split("\n")[1].lower():
                return True
        elif chunk.id.startswith(e):
            return True
    return False


def evaluate(retriever: Retriever, path: Path = ROOT / "eval" / "retrieval.jsonl") -> dict:
    cases = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    hits = {k: 0 for k in KS}
    rr = 0.0
    misses = []
    for case in cases:
        results = retriever.search(case["q"], k=max(KS))
        rank = next((i for i, h in enumerate(results) if matches(h.chunk, case["expect"])), None)
        if rank is None:
            misses.append((case["q"], [h.chunk.id for h in results[:3]]))
            continue
        rr += 1 / (rank + 1)
        for k in KS:
            hits[k] += rank < k
    n = len(cases)
    return {"n": n, **{f"hit@{k}": hits[k] / n for k in KS}, "mrr": rr / n, "misses": misses}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--misses", action="store_true")
    args = p.parse_args()
    r = evaluate(Retriever())
    print(f"n={r['n']}  " + "  ".join(f"hit@{k}={r[f'hit@{k}']:.2f}" for k in KS) + f"  mrr={r['mrr']:.3f}")
    if args.misses:
        for q, top in r["misses"]:
            print(f"  MISS  {q!r}  → {top}")


if __name__ == "__main__":
    main()
