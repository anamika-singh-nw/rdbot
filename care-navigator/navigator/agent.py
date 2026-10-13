"""The care-navigator agent: a hand-written tool-use loop around Claude.

A manual loop rather than the SDK's beta tool runner, because the loop is the product:
- it caps the number of model calls per turn, so a confused run cannot spin forever;
- it records every tool call as a trace, which is what the scenario eval grades;
- it is testable offline against a scripted stub client.

The API key is read from the environment by the SDK (ANTHROPIC_API_KEY or an
`ant auth login` profile). It is never passed in code, logged, or written to disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

from .safety import screen
from .tools import TOOLS, Toolbox, ToolError

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_STEPS = 8

SYSTEM = """You are the RxDx Care Navigator. RxDx Clinics is a multispeciality outpatient \
network in Bengaluru. You help patients and families get from "here is my problem and my \
constraints" to "this doctor, at this branch, on this day" — and, when they are ready, a \
booking request they can send.

How to work:
- Use the tools for every fact about doctors, branches and days. Never name a doctor, branch \
or day that did not come back from a tool in this conversation.
- Work out the constraints that matter: the concern, area/branch, days they can come, \
in-clinic or teleconsultation, language, a child or an adult. Ask one short question only \
when a missing detail would change the recommendation; otherwise search with what you have. \
Once a concern maps to a speciality, call find_doctors before asking anything — show options \
first, then ask what would narrow them.
- Map the concern to a speciality yourself (ear infections in a child → Paediatric ENT or \
Paediatrics; knee pain from running → Orthopaedics or Sports Medicine). If unsure of the exact \
name, call list_specialities. If a search finds nothing, relax one constraint at a time and \
say which one you relaxed.
- Recommend two or three doctors at most, with the branch and days for each, and say why \
they fit. Prefer doctors with published days. If a result carries a warning, pass it on.
- Each doctor result carries review_search_links (Google, Practo). Share them when the \
patient asks about ratings or reputation. They are searches, not ratings: never state or \
guess a rating, review count or reputation yourself.
- Only call prepare_booking_request once the patient has picked a doctor, branch, day and \
mode. Make clear it is a request RxDx will confirm, not a booking.

Boundaries:
- You are not a clinician. Do not diagnose, interpret test results, or suggest treatment or \
medication. Saying which speciality usually handles a concern is fine.
- If anything suggests an emergency, tell them to call 108 or go to the nearest emergency \
department first; RxDx clinics are outpatient clinics.
- Schedules on the website can change; suggest confirming with RxDx (+91 901 409 1111) \
before travelling.

Be brief and concrete. Plain sentences, short lists where they help."""


@dataclass
class ToolCall:
    name: str
    input: dict
    output: str
    is_error: bool


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str | None = None
    emergency: str | None = None
    steps: int = 0
    usage: dict = field(default_factory=lambda: {"input": 0, "output": 0, "cache_read": 0})


class Navigator:
    """One conversation. `messages` is append-only: assistant turns are stored exactly as
    returned (thinking blocks included), and tool results are appended, never edited."""

    def __init__(self, toolbox: Toolbox | None = None, client=None, effort: str = "medium"):
        self.toolbox = toolbox or Toolbox()
        self.client = client or anthropic.Anthropic()
        self.effort = effort
        self.messages: list[dict] = []

    def _call(self):
        return self.client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            tools=TOOLS,
            messages=self.messages,
            output_config={"effort": self.effort},
            cache_control={"type": "ephemeral"},
            betas=[FALLBACK_BETA],
            extra_body={"fallbacks": "default"},
        )

    def _execute(self, block) -> ToolCall:
        try:
            out = self.toolbox.run(block.name, dict(block.input))
            return ToolCall(block.name, dict(block.input), out, False)
        except ToolError as e:
            return ToolCall(block.name, dict(block.input), str(e), True)
        except TypeError as e:  # arguments that don't fit the function — report, don't crash
            return ToolCall(block.name, dict(block.input), f"Bad arguments: {e}", True)

    def ask(self, message: str) -> Turn:
        hit = screen(message)
        if hit:
            category, reply = hit
            # Recorded in history so later turns know it was said, but no model call is made.
            self.messages.append({"role": "user", "content": message})
            self.messages.append({"role": "assistant", "content": reply})
            return Turn(reply, emergency=category, stop_reason="emergency_screen")

        self.messages.append({"role": "user", "content": message})
        turn = Turn(text="")
        for step in range(1, MAX_STEPS + 1):
            resp = self._call()
            turn.steps = step
            turn.stop_reason = resp.stop_reason
            for k, attr in (("input", "input_tokens"), ("output", "output_tokens"), ("cache_read", "cache_read_input_tokens")):
                turn.usage[k] += getattr(resp.usage, attr, 0) or 0
            self.messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason == "refusal":
                turn.text = "I can't help with that here. Please call RxDx on +91 901 409 1111."
                return turn
            uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not uses:
                turn.text = "".join(b.text for b in resp.content if b.type == "text").strip()
                if resp.stop_reason == "max_tokens":
                    turn.text += "\n\n(Answer cut short — please ask again more narrowly.)"
                return turn

            calls = [self._execute(b) for b in uses]
            turn.tool_calls.extend(calls)
            # All results in one user message — splitting them discourages parallel calls.
            self.messages.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": b.id, "content": c.output, "is_error": c.is_error}
                    for b, c in zip(uses, calls)
                ],
            })

        turn.text = (
            "I couldn't finish working that out. Please call RxDx on +91 901 409 1111, "
            "or try asking with one constraint at a time."
        )
        turn.stop_reason = "max_steps"
        return turn


def trace(turn: Turn) -> str:
    lines = []
    for c in turn.tool_calls:
        args = ", ".join(f"{k}={v!r}" for k, v in c.input.items() if v is not None)
        summary = c.output if c.is_error else _brief(c.name, c.output)
        lines.append(f"  {'✗' if c.is_error else '→'} {c.name}({args})  {summary}")
    return "\n".join(lines)


def _brief(name: str, output: str) -> str:
    data = json.loads(output)
    if name == "find_doctors":
        return f"{data['total_matches']} match(es)"
    if name == "get_doctor":
        return data["name"]
    if name == "prepare_booking_request":
        return "draft ready"
    return f"{len(next(iter(data.values())))} item(s)"


CLI_PROTOCOL = """

Tools are called through structured output. Each reply is a JSON object:
- To call tools: put one or more calls in "tool_calls" (each with "name" and "arguments" as a \
JSON-encoded string matching that tool's input schema, every property present, null where \
unspecified) and leave "reply" empty. You will get the results and be asked again.
- To answer the patient: leave "tool_calls" empty and write the answer in "reply".

Available tools:
{tools}"""

CLI_SCHEMA = {
    "type": "object",
    "properties": {
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": [t["name"] for t in TOOLS]},
                    "arguments": {"type": "string"},
                },
                "required": ["name", "arguments"],
                "additionalProperties": False,
            },
        },
        "reply": {"type": "string"},
    },
    "required": ["tool_calls", "reply"],
    "additionalProperties": False,
}


class CliNavigator:
    """The same agent driven through the local `claude` CLI (no API key), for local demos.

    The CLI has no client-side tool calls, so each step asks for structured output — tool
    calls or a final reply — and this loop runs the tools and feeds results back. Same tools,
    same emergency screen, same step cap as `Navigator`."""

    def __init__(self, toolbox: Toolbox | None = None, effort: str = "medium", ask=None):
        from . import claude_cli

        self.toolbox = toolbox or Toolbox()
        self.effort = effort
        self._ask = ask or claude_cli.ask
        tools = json.dumps(
            [{k: t[k] for k in ("name", "description", "input_schema")} for t in TOOLS], indent=1
        )
        self.system = SYSTEM + CLI_PROTOCOL.format(tools=tools)
        self.transcript: list[str] = []

    def ask(self, message: str) -> Turn:
        hit = screen(message)
        if hit:
            category, reply = hit
            self.transcript += [f"PATIENT: {message}", f"YOU: {reply}"]
            return Turn(reply, emergency=category, stop_reason="emergency_screen")

        self.transcript.append(f"PATIENT: {message}")
        turn = Turn(text="")
        for step in range(1, MAX_STEPS + 1):
            turn.steps = step
            out = self._ask("\n\n".join(self.transcript), self.system, schema=CLI_SCHEMA, effort=self.effort)
            calls = out.get("tool_calls") or []
            if not calls:
                turn.text = (out.get("reply") or "").strip()
                turn.stop_reason = "end_turn"
                self.transcript.append(f"YOU: {turn.text}")
                return turn
            results = []
            for c in calls:
                try:
                    args = json.loads(c["arguments"] or "{}")
                    call = self._execute(c["name"], args)
                except json.JSONDecodeError as e:
                    call = ToolCall(c["name"], {}, f"Arguments were not valid JSON: {e}", True)
                turn.tool_calls.append(call)
                results.append(
                    f"TOOL {call.name}({json.dumps(call.input, ensure_ascii=False)}) → "
                    f"{'ERROR: ' if call.is_error else ''}{call.output}"
                )
            self.transcript.append("\n".join(results))

        turn.text = (
            "I couldn't finish working that out. Please call RxDx on +91 901 409 1111, "
            "or try asking with one constraint at a time."
        )
        turn.stop_reason = "max_steps"
        return turn

    def _execute(self, name: str, args: dict) -> ToolCall:
        try:
            return ToolCall(name, args, self.toolbox.run(name, args), False)
        except ToolError as e:
            return ToolCall(name, args, str(e), True)
        except TypeError as e:
            return ToolCall(name, args, f"Bad arguments: {e}", True)


def strip_reasoning(text: str) -> str:
    """Nova sometimes writes its reasoning inline as <thinking>…</thinking> and wraps the
    answer in <response> tags. Patients should see only the answer."""
    import re

    text = re.sub(r"<thinking>.*?(</thinking>|$)", "", text, flags=re.S)
    return re.sub(r"</?response>", "", text).strip()


def _bedrock_schema(schema: dict) -> dict:
    """Strict-mode schemas say "not specified" with an explicit null. For Bedrock models,
    nullable properties become plain optional ones; the executor fills omitted ones."""
    props, required = {}, []
    for name, spec in schema["properties"].items():
        spec = dict(spec)
        t = spec.get("type")
        if isinstance(t, list):
            spec["type"] = next(x for x in t if x != "null")
            if "enum" in spec:
                spec["enum"] = [v for v in spec["enum"] if v is not None]
        else:
            required.append(name)
        props[name] = spec
    return {"type": "object", "properties": props, "required": required}


BEDROCK_TOOLS = {
    "tools": [
        {"toolSpec": {"name": t["name"], "description": t["description"],
                      "inputSchema": {"json": _bedrock_schema(t["input_schema"])}}}
        for t in TOOLS
    ]
}
_DEFAULTS = {t["name"]: {k: ("any" if k == "mode" else None) for k in t["input_schema"]["properties"]} for t in TOOLS}


class BedrockNavigator:
    """The same agent on a Bedrock model (default Amazon Nova Pro) via the Converse API, which
    has native tool use. Same tools, emergency screen, step cap and append-only history."""

    def __init__(self, toolbox: Toolbox | None = None, client=None, model_id: str | None = None):
        from . import bedrock

        self.toolbox = toolbox or Toolbox()
        self.client = client or bedrock.client()
        self.model_id = model_id or bedrock.MODEL_ID
        self.messages: list[dict] = []

    def ask(self, message: str) -> Turn:
        hit = screen(message)
        if hit:
            category, reply = hit
            self.messages += [{"role": "user", "content": [{"text": message}]},
                              {"role": "assistant", "content": [{"text": reply}]}]
            return Turn(reply, emergency=category, stop_reason="emergency_screen")

        self.messages.append({"role": "user", "content": [{"text": message}]})
        turn = Turn(text="")
        for step in range(1, MAX_STEPS + 1):
            resp = self.client.converse(
                modelId=self.model_id,
                system=[{"text": SYSTEM}],
                messages=self.messages,
                toolConfig=BEDROCK_TOOLS,
                inferenceConfig={"maxTokens": 2000, "temperature": 0.2},
            )
            turn.steps = step
            turn.stop_reason = resp.get("stopReason")
            u = resp.get("usage", {})
            turn.usage["input"] += u.get("inputTokens", 0)
            turn.usage["output"] += u.get("outputTokens", 0)
            out = resp["output"]["message"]
            self.messages.append(out)

            uses = [b["toolUse"] for b in out.get("content", []) if "toolUse" in b]
            if turn.stop_reason != "tool_use" or not uses:
                turn.text = strip_reasoning("".join(b.get("text", "") for b in out.get("content", [])))
                if turn.stop_reason == "max_tokens":
                    turn.text += "\n\n(Answer cut short — please ask again more narrowly.)"
                return turn

            results = []
            for u in uses:
                args = {**_DEFAULTS.get(u["name"], {}), **(u.get("input") or {})}
                try:
                    call = ToolCall(u["name"], args, self.toolbox.run(u["name"], args), False)
                except ToolError as e:
                    call = ToolCall(u["name"], args, str(e), True)
                except TypeError as e:
                    call = ToolCall(u["name"], args, f"Bad arguments: {e}", True)
                turn.tool_calls.append(call)
                block = {"toolUseId": u["toolUseId"], "content": [{"text": call.output}]}
                if call.is_error:
                    block["status"] = "error"
                results.append({"toolResult": block})
            self.messages.append({"role": "user", "content": results})

        turn.text = (
            "I couldn't finish working that out. Please call RxDx on +91 901 409 1111, "
            "or try asking with one constraint at a time."
        )
        turn.stop_reason = "max_steps"
        return turn
