"""The agent loop, driven offline by a scripted stub client — no API key, no network."""

from types import SimpleNamespace as NS

from navigator.agent import MAX_STEPS, MODEL, Navigator

USAGE = NS(input_tokens=100, output_tokens=20, cache_read_input_tokens=50)
FIND = {"speciality": "Dermatology", "branch": "Whitefield", "day": "Monday", "mode": "in_clinic", "language": None, "name": None}


def tool_use(id, name, input):
    return NS(type="tool_use", id=id, name=name, input=input)


def text(t):
    return NS(type="text", text=t)


def resp(content, stop):
    return NS(content=content, stop_reason=stop, usage=USAGE)


class Script:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})
        return self.responses.pop(0)


def test_tool_loop_runs_tools_and_returns_final_text():
    script = Script(
        resp([NS(type="thinking", thinking=""), tool_use("t1", "find_doctors", FIND)], "tool_use"),
        resp([text("Dr Madhu R is in Whitefield on Monday.")], "end_turn"),
    )
    nav = Navigator(client=script)
    turn = nav.ask("skin doctor in Whitefield on Monday")

    assert turn.text == "Dr Madhu R is in Whitefield on Monday."
    assert [c.name for c in turn.tool_calls] == ["find_doctors"] and not turn.tool_calls[0].is_error
    assert "dr-madhu-r" in turn.tool_calls[0].output
    assert turn.steps == 2 and turn.usage == {"input": 200, "output": 40, "cache_read": 100}

    req = script.requests[0]
    assert req["model"] == MODEL and req["extra_body"] == {"fallbacks": "default"}
    assert "server-side-fallback-2026-07-01" in req["betas"]
    # History: user, assistant(tool_use, thinking kept), user(tool_result), assistant(final)
    assert [m["role"] for m in nav.messages] == ["user", "assistant", "user", "assistant"]
    assert nav.messages[1]["content"][0].type == "thinking"
    assert nav.messages[2]["content"][0]["tool_use_id"] == "t1"


def test_parallel_tool_results_go_back_in_one_message():
    script = Script(
        resp([tool_use("a", "list_branches", {}), tool_use("b", "list_specialities", {})], "tool_use"),
        resp([text("ok")], "end_turn"),
    )
    nav = Navigator(client=script)
    nav.ask("what do you have?")
    results = nav.messages[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"]


def test_tool_errors_are_returned_to_the_model_not_raised():
    bad = {**FIND, "branch": "Hebbal"}
    script = Script(resp([tool_use("t1", "find_doctors", bad)], "tool_use"), resp([text("Hebbal has no branch.")], "end_turn"))
    nav = Navigator(client=script)
    turn = nav.ask("dermatologist in Hebbal")
    assert turn.tool_calls[0].is_error
    assert nav.messages[2]["content"][0]["is_error"] is True


def test_history_is_append_only_across_turns():
    script = Script(resp([text("Which area?")], "end_turn"), resp([text("Sure.")], "end_turn"))
    nav = Navigator(client=script)
    nav.ask("I need a dermatologist")
    snapshot = list(nav.messages)
    nav.ask("Whitefield")
    assert nav.messages[: len(snapshot)] == snapshot
    assert script.requests[1]["messages"][: len(snapshot)] == snapshot


def test_emergency_short_circuits_the_model():
    script = Script()
    nav = Navigator(client=script)
    turn = nav.ask("my dad has chest pain and is sweating, which cardiologist?")
    assert turn.emergency == "chest pain" and "108" in turn.text
    assert script.requests == []


def test_step_cap_stops_a_looping_agent():
    loop = resp([tool_use("t", "list_branches", {})], "tool_use")
    nav = Navigator(client=Script(*[loop] * MAX_STEPS))
    turn = nav.ask("anything")
    assert turn.stop_reason == "max_steps" and turn.steps == MAX_STEPS and "901 409 1111" in turn.text


def test_refusal_is_handled():
    nav = Navigator(client=Script(resp([], "refusal")))
    turn = nav.ask("something")
    assert turn.stop_reason == "refusal" and "901 409 1111" in turn.text


def test_cli_navigator_runs_tool_calls_then_answers():
    import json as _json

    from navigator.agent import CLI_SCHEMA, CliNavigator

    steps = [
        {"tool_calls": [{"name": "find_doctors", "arguments": _json.dumps(FIND)}], "reply": ""},
        {"tool_calls": [{"name": "get_doctor", "arguments": "not json"}], "reply": ""},
        {"tool_calls": [], "reply": "Dr Madhu R, Whitefield, Monday."},
    ]
    prompts = []

    def fake_ask(prompt, system, schema, effort):
        assert schema is CLI_SCHEMA and "find_doctors" in system
        prompts.append(prompt)
        return steps.pop(0)

    nav = CliNavigator(ask=fake_ask)
    turn = nav.ask("skin doctor in Whitefield on Monday")
    assert turn.text == "Dr Madhu R, Whitefield, Monday." and turn.steps == 3
    assert [c.is_error for c in turn.tool_calls] == [False, True]
    assert "dr-madhu-r" in prompts[1] and "not valid JSON" in prompts[2]


def test_cli_navigator_emergency_skips_the_cli():
    from navigator.agent import CliNavigator

    nav = CliNavigator(ask=lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    assert nav.ask("she can't breathe").emergency == "breathing"


def test_reasoning_tags_are_stripped():
    from navigator.agent import strip_reasoning

    assert strip_reasoning("<thinking>plan</thinking> <response>Dr A, Monday.</response>") == "Dr A, Monday."
    assert strip_reasoning("<thinking>unterminated") == ""


def test_bedrock_navigator_tool_loop():
    from navigator.agent import BedrockNavigator

    turns = [
        {"stopReason": "tool_use", "usage": {"inputTokens": 5, "outputTokens": 1},
         "output": {"message": {"role": "assistant", "content": [
             {"toolUse": {"toolUseId": "u1", "name": "find_doctors", "input": {"speciality": "Dermatology", "branch": "Whitefield", "day": "Monday"}}}]}}},
        {"stopReason": "end_turn", "usage": {"inputTokens": 5, "outputTokens": 1},
         "output": {"message": {"role": "assistant", "content": [{"text": "<thinking>x</thinking>Dr Madhu R, Monday."}]}}},
    ]
    sent = []
    client = NS(converse=lambda **kw: sent.append(kw) or turns.pop(0))
    nav = BedrockNavigator(client=client, model_id="test-model")
    turn = nav.ask("skin doctor Whitefield Monday")
    assert turn.text == "Dr Madhu R, Monday."
    assert turn.tool_calls[0].input["mode"] == "any"  # omitted optional args are filled
    assert "dr-madhu-r" in turn.tool_calls[0].output
    result = nav.messages[2]["content"][0]["toolResult"]
    assert result["toolUseId"] == "u1" and "status" not in result
    schema = sent[0]["toolConfig"]["tools"][2]["toolSpec"]["inputSchema"]["json"]
    assert schema["properties"]["day"]["type"] == "string" and None not in schema["properties"]["day"]["enum"]
