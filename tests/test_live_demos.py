"""Live demo contracts: real retrieval/tools, scripted external model only."""
from types import SimpleNamespace

import pytest

from web import live_demos


def test_fundbot_retrieves_fixture_facts_and_filters_supporters():
    tools = live_demos.DemoTools("fundbot", {})
    result = tools.run("search_knowledge", {"query": "education learning materials"})
    assert any("learning materials" in doc["text"].lower() for doc in result["documents"])
    result = tools.run("list_supporters", {"segment": "education"})
    assert [d["name"] for d in result["supporters"]] == ["Supporter A", "Supporter C"]


def test_fhir_latest_observation_and_components():
    result = live_demos.DemoTools("clinical-fhir", {}).run("get_observation", {"observation": "blood-pressure"})
    assert result["date"] == "2026-09-18"
    assert result["values"] == {"systolic": 120, "diastolic": 78, "unit": "mmHg"}
    assert result["source"] == "Synthetic FHIR fixture"


def test_post_discharge_updates_only_returned_demo_state():
    state = {}
    tools = live_demos.DemoTools("post-discharge", state)
    result = tools.run("confirm_plan_read", {})
    assert result["confirmed"] is True
    assert state == {}
    assert tools.state["plan_read"] is True


def test_wrong_project_cannot_use_another_projects_tool():
    with pytest.raises(ValueError):
        live_demos.DemoTools("fundbot", {}).run("get_observation", {"observation": "weight"})


def test_live_model_calls_real_tools_and_preserves_followup_history(monkeypatch):
    requests = []
    responses = [
        {"output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": "get_observation", "input": {"observation": "weight"}}}]}}, "stopReason": "tool_use"},
        {"output": {"message": {"role": "assistant", "content": [{"text": "The sample weight is 68 kg."}]}}, "stopReason": "end_turn"},
    ]
    def converse(**request):
        requests.append(request)
        return responses.pop(0)
    from navigator import bedrock
    monkeypatch.setattr(bedrock, "client", lambda token: SimpleNamespace(converse=converse))
    result = live_demos.answer("clinical-fhir", "And the weight?", [
        {"role": "user", "text": "Show the sample blood pressure"},
        {"role": "assistant", "text": "120 / 78 mmHg"},
    ], {}, "token")
    assert result["text"] == "The sample weight is 68 kg."
    assert result["tool_calls"][0]["result"]["values"]["value"] == 68
    assert requests[0]["messages"][0]["content"] == [{"text": "Show the sample blood pressure"}]


def test_aid_context_has_explicit_evidence_boundaries():
    tools = live_demos.DemoTools("aid", {})
    assert tools.run("get_patient_record", {})["synthetic"] is True
    assert tools.run("get_evidence_context", {})["live_lookup"] is False


def test_medical_emergency_short_circuits_model(monkeypatch):
    from navigator import bedrock
    def fail(*args):
        raise AssertionError("No model call for emergency")
    monkeypatch.setattr(bedrock, "client", fail)
    result = live_demos.answer("post-discharge", "crushing chest pain", [], {}, None)
    assert result["emergency"]
    assert result["tool_calls"] == []
