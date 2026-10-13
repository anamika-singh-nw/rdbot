"""CLI.

    python -m rxdx_qna build                     # chunk + embed the knowledge base
    python -m rxdx_qna search "skin doctor"      # retrieval only — no API key needed
    python -m rxdx_qna ask "Who is a paediatrician in Malleshwaram?"
    python -m rxdx_qna chat                      # multi-turn
    python -m rxdx_qna chat --backend cli        # use the logged-in `claude` CLI, no API key
"""

from __future__ import annotations

import argparse
import sys

from .index import Retriever, build_index


def _print_answer(ans, verbose: bool) -> None:
    print(ans.text)
    if ans.sources:
        print("\nSources:")
        for s in ans.sources:
            print(f"  [{s.n}] {s.title} — {s.url}")
            if s.reviews:
                print(f"      reviews: Google {s.reviews['google']}")
                print(f"               Practo {s.reviews['practo']}")
    if verbose:
        print("\nRetrieved:")
        for h in ans.hits:
            print(f"  {h.score:.4f}  {h.chunk.id}")
        print(f"\nmodel={ans.model} stop={ans.stop_reason} usage={ans.usage}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rxdx_qna", description="RAG question answering over rxdx.in")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="build the retrieval index")
    s = sub.add_parser("search", help="show retrieved chunks for a query")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=8)
    a = sub.add_parser("ask", help="answer one question")
    a.add_argument("question")
    c = sub.add_parser("chat", help="interactive multi-turn chat")
    for sp in (a, c):
        sp.add_argument("-v", "--verbose", action="store_true")
        sp.add_argument(
            "--backend", choices=["api", "cli", "bedrock"], default="api",
            help="api: Anthropic API key (default). cli: your logged-in `claude` CLI. bedrock: Amazon Bedrock (Nova Pro) on AWS credits.",
        )
    args = p.parse_args(argv)

    if args.cmd == "build":
        print(f"Indexed {build_index()} chunks.")
        return 0

    retriever = Retriever()
    if args.cmd == "search":
        for h in retriever.search(args.query, k=args.k):
            print(f"{h.score:.4f}  {h.chunk.id:45}  {h.chunk.text[:90].replace(chr(10), ' ')}")
        return 0

    from .answer import BedrockQnABot, CliQnABot, QnABot  # deferred: `search` must work without the SDK configured

    bot = {"cli": CliQnABot, "bedrock": BedrockQnABot}.get(args.backend, QnABot)(retriever)
    if args.cmd == "ask":
        _print_answer(bot.ask(args.question), args.verbose)
        return 0

    print("RxDx assistant — ask about doctors, clinics, schedules and services. Ctrl-D to quit.")
    while True:
        try:
            q = input("\nyou › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if q:
            print()
            _print_answer(bot.ask(q), args.verbose)


if __name__ == "__main__":
    sys.exit(main())
