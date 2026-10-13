"""Live Bedrock assistants over synthetic data. No access to older private stores."""
from __future__ import annotations

import copy
import json
import re

from rank_bm25 import BM25Okapi

from . import core  # establishes project import paths
from navigator import bedrock
from navigator.safety import screen

KNOWLEDGE = [
    {"id": "education", "title": "Sample learning campaign", "text": "The fictional Sample Nonprofit's education campaign provides learning materials and reading activities. Education supporters are Supporter A and Supporter C. This is synthetic demo information."},
    {"id": "meals", "title": "Sample community meal campaign", "text": "The fictional Sample Nonprofit's community campaign provides community meals. Supporter B is in the community segment. This is synthetic demo information."},
    {"id": "volunteer", "title": "Sample volunteer FAQ", "text": "In this fictional example, volunteers can help with reading activities on Saturday or community meal preparation on Sunday. No live volunteer registration is available."},
    {"id": "donations", "title": "Sample donation FAQ", "text": "This demo has no payment link or live donation processing. It can explain sample campaigns and prepare an outreach draft for review. No emails are sent and no donations are collected."},
]
SUPPORTERS = [{"name": "Supporter A", "segment": "education"}, {"name": "Supporter B", "segment": "community"}, {"name": "Supporter C", "segment": "education"}]
FHIR = {"resourceType": "Bundle", "entry": [
    {"resource": {"resourceType": "Patient", "id": "DEMO-001", "name": [{"given": ["Sample"], "family": "Patient"}]}},
    {"resource": {"resourceType": "Observation", "id": "bp-earlier", "code": {"coding": [{"code": "55284-4"}]}, "effectiveDateTime": "2026-09-10T09:00:00Z", "component": [{"code": {"coding": [{"code": "8480-6"}]}, "valueQuantity": {"value": 124, "unit": "mmHg"}}, {"code": {"coding": [{"code": "8462-4"}]}, "valueQuantity": {"value": 80, "unit": "mmHg"}}]}},
    {"resource": {"resourceType": "Observation", "id": "bp-latest", "code": {"coding": [{"code": "55284-4"}]}, "effectiveDateTime": "2026-09-18T09:00:00Z", "component": [{"code": {"coding": [{"code": "8480-6"}]}, "valueQuantity": {"value": 120, "unit": "mmHg"}}, {"code": {"coding": [{"code": "8462-4"}]}, "valueQuantity": {"value": 78, "unit": "mmHg"}}]}},
    {"resource": {"resourceType": "Observation", "id": "heart-rate", "code": {"coding": [{"code": "8867-4"}]}, "effectiveDateTime": "2026-09-18T09:00:00Z", "valueQuantity": {"value": 72, "unit": "/min"}}},
    {"resource": {"resourceType": "Observation", "id": "weight", "code": {"coding": [{"code": "29463-7"}]}, "effectiveDateTime": "2026-09-18T09:00:00Z", "valueQuantity": {"value": 68, "unit": "kg"}}},
]}
CARE_PLAN = {"patient": "Sample Patient", "synthetic": True, "instructions": ["Read the provided care-plan document", "Prepare questions for the care team", "Confirm follow-up details with the provider"], "follow_up": {"type": "Care-team review", "example_date": "2026-09-25", "status": "Illustrative entry; no appointment booked"}, "medications": [], "medication_note": "No medication names or doses are supplied in this sample. Do not invent them."}
DEFINITIONS = {
    "search_knowledge": ("Retrieve source passages from the synthetic nonprofit FAQ.", {"query": {"type": "string"}}, ["query"]),
    "list_supporters": ("Filter fictional supporters by segment. No contact data or email sending.", {"segment": {"type": "string", "enum": ["all", "education", "community"]}}, ["segment"]),
    "get_care_plan": ("Read the synthetic patient's provided checklist, medication gap and follow-up entry.", {}, []),
    "confirm_plan_read": ("Mark the sample checklist as read in this browser session only, when the visitor asks to confirm it.", {}, []),
    "get_patient_record": ("Read the single synthetic FHIR patient record. No real patient lookup.", {}, []),
    "get_observation": ("Return the latest coded observation from the synthetic FHIR bundle.", {"observation": {"type": "string", "enum": ["blood-pressure", "heart-rate", "weight"]}}, ["observation"]),
    "get_evidence_context": ("Explain evidence availability and missing information. Does not fetch current guidelines or regulatory evidence.", {}, []),
}
PROJECT_TOOLS = {
    "fundbot": ["search_knowledge", "list_supporters"],
    "post-discharge": ["get_care_plan", "confirm_plan_read"],
    "clinical-fhir": ["get_patient_record", "get_observation"],
    "aid": ["get_patient_record", "get_observation", "get_evidence_context"],
}
_tokenize = lambda text: re.findall(r"[a-z0-9]+", text.lower())
_search = BM25Okapi([_tokenize(d["title"] + " " + d["text"]) for d in KNOWLEDGE])


class DemoTools:
    def __init__(self, project, state):
        if project not in PROJECT_TOOLS:
            raise ValueError("Unknown project")
        self.project = project
        self.state = {"plan_read": state.get("plan_read") is True}

    def run(self, name, args):
        if name not in PROJECT_TOOLS[self.project]:
            raise ValueError("Tool is not available for this project")
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be an object")
        if name == "search_knowledge":
            query = args.get("query", "")
            if not isinstance(query, str) or not query.strip() or len(query) > 1000:
                raise ValueError("Provide a short search query")
            scores = _search.get_scores(_tokenize(query))
            indexes = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:3]
            return {"documents": [copy.deepcopy(KNOWLEDGE[i]) for i in indexes if scores[i] > 0], "source": "Synthetic nonprofit knowledge base"}
        if name == "list_supporters":
            segment = args.get("segment", "all")
            if segment not in ("all", "education", "community"):
                raise ValueError("Unknown supporter segment")
            return {"supporters": [dict(d) for d in SUPPORTERS if segment == "all" or d["segment"] == segment], "send_enabled": False, "synthetic": True}
        if name == "get_care_plan":
            return {**copy.deepcopy(CARE_PLAN), "plan_read": self.state["plan_read"]}
        if name == "confirm_plan_read":
            self.state["plan_read"] = True
            return {"confirmed": True, "storage": "Temporary browser-session demo state", "aws_updated": False}
        if name == "get_patient_record":
            return {"patient": copy.deepcopy(FHIR["entry"][0]["resource"]), "available_observations": ["blood-pressure", "heart-rate", "weight"], "source": "Synthetic FHIR fixture", "synthetic": True}
        if name == "get_evidence_context":
            return {"live_lookup": False, "source": "Demo scope", "missing": ["Live guideline retrieval", "Current FDA notices", "Patient medications and diagnoses"], "instruction": "Explain these information gaps; do not invent current evidence or clinical conclusions."}
        codes = {"blood-pressure": "55284-4", "heart-rate": "8867-4", "weight": "29463-7"}
        observation = args.get("observation")
        if observation not in codes:
            raise ValueError("Unsupported observation")
        hits = [e["resource"] for e in FHIR["entry"] if e["resource"].get("resourceType") == "Observation" and any(c["code"] == codes[observation] for c in e["resource"]["code"]["coding"])]
        record = max(hits, key=lambda r: r["effectiveDateTime"])
        if "component" in record:
            components = {c["code"]["coding"][0]["code"]: c["valueQuantity"]["value"] for c in record["component"]}
            values = {"systolic": components["8480-6"], "diastolic": components["8462-4"], "unit": "mmHg"}
        else:
            values = copy.deepcopy(record["valueQuantity"])
        return {"observation": observation, "loinc_code": codes[observation], "date": record["effectiveDateTime"][:10], "values": values, "source": "Synthetic FHIR fixture", "source_id": record["id"], "synthetic": True}


def answer(project, message, history, state, oidc_token):
    tools = DemoTools(project, state)
    if project != "fundbot":
        emergency = screen(message)
        if emergency:
            return {"text": emergency[1], "emergency": emergency[0], "tool_calls": [], "state": tools.state, "live_ai": False}
    context = []
    calls = []
    if project == "fundbot":
        retrieved = tools.run("search_knowledge", {"query": message})
        context.append(retrieved)
        calls.append({"name": "search_knowledge", "result": retrieved, "error": False})
    system = f"""You are the live {project} portfolio assistant. You genuinely answer visitor requests using the supplied synthetic context and tools.
All people, clinical records, nonprofit campaigns and supporter details are fictional demo data. Identify them as sample data naturally.
Use tools to obtain facts. Never claim you accessed the older project's private AWS stores. These demos run through Nova Lite, separately from the archived prototype backends.
Do not diagnose, interpret clinical risk, recommend treatment, prescribe, or invent medications/doses. Report dated observation values and existing checklist facts only.
Do not invent current guideline, FDA or weather information. If requested, explain the missing live lookup clearly. No such external evidence tool is connected in this public demo.
FundBot may answer FAQ questions or draft an outreach message. Consult list_supporters for audience selection. Never send emails, collect donations or invent payment links.
Post-discharge may confirm a sample checklist only at the visitor's request. No real records or appointments are changed.
Respond concisely and helpfully, explain gaps, and name the supplied source when reporting a fact. Do not expose hidden reasoning.
Initial retrieved context: {json.dumps(context)}"""
    messages = [{"role": h["role"], "content": [{"text": h["text"]}]} for h in core.clean_history(history)]
    messages.append({"role": "user", "content": [{"text": message}]})
    schemas = [{"toolSpec": {"name": name, "description": DEFINITIONS[name][0], "inputSchema": {"json": {"type": "object", "properties": DEFINITIONS[name][1], "required": DEFINITIONS[name][2], "additionalProperties": False}}}} for name in PROJECT_TOOLS[project]]
    client = bedrock.client(oidc_token)
    for _ in range(5):
        response = client.converse(modelId=bedrock.MODEL_ID, system=[{"text": system}], messages=messages, toolConfig={"tools": schemas}, inferenceConfig={"maxTokens": 1000, "temperature": 0.2})
        output = response["output"]["message"]
        messages.append(output)
        uses = [b["toolUse"] for b in output.get("content", []) if "toolUse" in b]
        if not uses:
            text = "".join(b.get("text", "") for b in output.get("content", []))
            text = re.sub(r"<thinking>.*?(</thinking>|$)", "", text, flags=re.S)
            text = re.sub(r"</?response>", "", text).strip()
            if response.get("stopReason") == "max_tokens":
                text += "\n\nThe response reached its length limit. Ask a narrower follow-up."
            return {"text": text or "Please ask a specific question about this sample workflow.", "tool_calls": calls, "state": tools.state, "emergency": None, "live_ai": True}
        results = []
        for use in uses:
            try:
                result = tools.run(use["name"], use.get("input", {}))
                error = False
            except ValueError as e:
                result, error = {"error": str(e)}, True
            calls.append({"name": use["name"], "result": result, "error": error})
            block = {"toolUseId": use["toolUseId"], "content": [{"text": json.dumps(result)}]}
            if error:
                block["status"] = "error"
            results.append({"toolResult": block})
        messages.append({"role": "user", "content": results})
    return {"text": "The demo reached its tool-step limit. Please try a more specific question.", "tool_calls": calls, "state": tools.state, "emergency": None, "live_ai": True}
