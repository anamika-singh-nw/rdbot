"""Scenario eval for the navigator. Calls the live API — it costs money (about 12 scenarios ×
2–4 model calls). Needs ANTHROPIC_API_KEY or an `ant auth login` profile.

    python eval/run_scenarios.py            # all scenarios
    python eval/run_scenarios.py kidney     # just the ones whose id contains "kidney"
    python eval/run_scenarios.py --backend bedrock   # Amazon Nova Pro on AWS credits

Grading is code, not a judge model. For navigation scenarios a run passes when:
  - at least one doctor is named, and every doctor named in the answer
  - was returned by a tool during the turn (grounded — nothing invented), and
  - satisfies the scenario's constraints, checked against the directory itself.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from navigator.agent import BedrockNavigator, Navigator, trace  # noqa: E402
from navigator.directory import Directory  # noqa: E402
from navigator.tools import Toolbox  # noqa: E402

D = Directory()


def named_doctors(text: str):
    text = re.sub(r"\b(Dr|Ms|Mr|Mrs)\.", r"\1", text)  # "Dr. Madhu R" names Dr Madhu R
    return [d for d in D.doctors.values() if d.name in text]


def grade(case: dict, turn) -> list[str]:
    e = case["expect"]
    if e.get("emergency"):
        return [] if turn.emergency else ["emergency not caught"]
    if e.get("clarify"):
        fails = []
        if "?" not in turn.text:
            fails.append("did not ask a clarifying question")
        if any(c.name == "prepare_booking_request" for c in turn.tool_calls):
            fails.append("drafted a booking without enough information")
        return fails

    fails = []
    returned = " ".join(c.output for c in turn.tool_calls if not c.is_error)
    docs = named_doctors(turn.text)
    if e.get("must_say_no_branch"):
        if not any(c.is_error and "branch" in c.output for c in turn.tool_calls) and "Hebbal" not in turn.text:
            fails.append("did not tell the user there is no such branch")
        return fails
    if not docs:
        return ["no doctor named"]
    for d in docs:
        if d.slug not in returned:
            fails.append(f"{d.name}: not returned by any tool (ungrounded)")
        if "named" in e:
            continue
        if not any(D.matches_speciality(d, s) for s in e.get("speciality", [])):
            fails.append(f"{d.name}: wrong speciality {d.departments}")
        branch = D.resolve_branch(e["branch"]) if e.get("branch") else None
        mode = e.get("mode", "any")
        if (branch or e.get("day") or mode != "any") and not d.available(e.get("day"), mode, branch):
            fails.append(f"{d.name}: not available for {e.get('branch')}/{e.get('day')}/{mode}")
        if e.get("language") and e["language"] not in d.languages:
            fails.append(f"{d.name}: does not list {e['language']}")
    for want in e.get("named", []):
        if want not in re.sub(r"\b(Dr|Ms|Mr|Mrs)\.", r"\1", turn.text):
            fails.append(f"did not mention {want}")
    return fails


def main() -> None:
    args = sys.argv[1:]
    backend = "api"
    if "--backend" in args:
        i = args.index("--backend")
        backend = args[i + 1]
        del args[i : i + 2]
    only = args[0] if args else ""
    make = {"api": Navigator, "bedrock": BedrockNavigator}[backend]
    cases = [json.loads(l) for l in (ROOT / "eval" / "scenarios.jsonl").read_text().splitlines() if l.strip()]
    cases = [c for c in cases if only in c["id"]]
    toolbox = Toolbox(D)
    passed = 0
    for case in cases:
        turn = make(toolbox).ask(case["message"])
        fails = grade(case, turn)
        passed += not fails
        print(f"{'PASS' if not fails else 'FAIL'}  {case['id']}  (steps={turn.steps}, tools={len(turn.tool_calls)})")
        for f in fails:
            print(f"      - {f}")
        if fails:
            print(trace(turn))
            print("      answer: " + turn.text.replace("\n", " ")[:400])
    print(f"\n{passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
