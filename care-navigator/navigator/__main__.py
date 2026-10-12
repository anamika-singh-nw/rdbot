"""CLI.

    python -m navigator tool find_doctors '{"speciality": "ENT", "day": "Saturday"}'   # no API key needed
    python -m navigator ask "My son has ear pain, we're near Whitefield, Saturdays only"
    python -m navigator chat -v      # -v prints each tool call the agent makes
    python -m navigator chat -v --backend cli   # use the logged-in `claude` CLI, no API key
"""

from __future__ import annotations

import argparse
import json
import sys

from .tools import TOOLS, Toolbox, ToolError


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="navigator", description="RxDx care-navigator agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tool", help="call one tool directly (debugging)")
    t.add_argument("name", choices=[x["name"] for x in TOOLS])
    t.add_argument("args", nargs="?", default="{}", help="JSON arguments; omitted filters default to null")
    a = sub.add_parser("ask", help="one request")
    a.add_argument("message")
    c = sub.add_parser("chat", help="interactive conversation")
    for sp in (a, c):
        sp.add_argument("-v", "--verbose", action="store_true")
        sp.add_argument(
            "--backend", choices=["api", "cli"], default="api",
            help="api: Anthropic API key (default). cli: your logged-in `claude` CLI, for local demos.",
        )
    args = p.parse_args(argv)

    if args.cmd == "tool":
        schema = next(x for x in TOOLS if x["name"] == args.name)["input_schema"]
        given = json.loads(args.args)
        full = {k: given.get(k, "any" if k == "mode" else None) for k in schema["properties"]}
        try:
            print(json.dumps(json.loads(Toolbox().run(args.name, full)), indent=2, ensure_ascii=False))
        except ToolError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        return 0

    from .agent import CliNavigator, Navigator, trace  # deferred: `tool` must work without the SDK configured

    nav = CliNavigator() if args.backend == "cli" else Navigator()

    def show(turn):
        if args.verbose and turn.tool_calls:
            print(trace(turn) + "\n")
        print(turn.text)
        if args.verbose:
            print(f"\n[stop={turn.stop_reason} steps={turn.steps} usage={turn.usage}]")

    if args.cmd == "ask":
        show(nav.ask(args.message))
        return 0

    print("RxDx Care Navigator — tell me what you need and when you can come. Ctrl-D to quit.")
    while True:
        try:
            msg = input("\nyou › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if msg:
            print()
            show(nav.ask(msg))


if __name__ == "__main__":
    sys.exit(main())
