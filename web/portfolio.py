"""Public case-study content; no connection to private project stores."""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LINKEDIN = "https://www.linkedin.com/in/techntrek"

CASES = {
    "fundbot": {
        "title": "FundBot",
        "subtitle": "Knowledge-backed conversations and donor outreach workflows.",
        "category": "RAG + workflow automation",
        "color": "#926000",
        "problem": "An NGO needs a way to answer common supporter questions and prepare outreach for different donor segments.",
        "approach": "The deployed Lambda code retrieves context from a Bedrock knowledge base, generates replies with Llama 3, reads donor segments from DynamoDB, and includes a separate SES email workflow.",
        "capabilities": ["Knowledge-base retrieval", "Context-augmented model prompts", "Conversation history", "Donor segmentation", "Personalized outreach integration"],
        "stack": ["Python", "AWS Lambda", "Bedrock Knowledge Bases", "Llama 3", "DynamoDB", "SES", "API Gateway", "S3 Vectors"],
        "evidence": ["Inspected emailbot-handler and donor-processor Lambda source.", "Verified knowledge-base, vector-bucket and donor-table resources exist.", "Code contains chat, donor and segmented email routes; no campaign was sent during the audit."],
        "limitations": "Code and resources were audited; the full older application was not tested end to end. The public Nova Lite adapter performs sample retrieval, segmentation and drafting; it does not invoke the old Llama/SES backend. A client rollout needs consent controls, authentication, pagination, monitoring and an explicit send approval.",
        "architecture": ["Supporter question", "Retrieve NGO context", "Generate response", "Select donor segment", "Prepare outreach"],
        "demoTitle": "Prepare a segmented campaign draft",
        "demoDescription": "The live assistant retrieves a synthetic FAQ, filters supporters and drafts outreach. A deterministic walkthrough is also available.",
        "options": [{"value": "education", "label": "Learning materials campaign"}, {"value": "meals", "label": "Community meal campaign"}],
        "secondary": [{"value": "all", "label": "All sample supporters"}, {"value": "education", "label": "Education supporters"}, {"value": "community", "label": "Community supporters"}],
        "action": "Preview campaign draft",
        "lesson": "Connect the model to approved knowledge and deterministic workflow data. Treat drafting and external communication as separate steps.",
    },
    "post-discharge": {
        "title": "Post-discharge assistant",
        "subtitle": "Conversation, care-plan tools and follow-up workflows in one prototype.",
        "category": "Conversational agents + persistent workflows",
        "color": "#08725e",
        "problem": "After leaving hospital, patients need to find their existing care instructions, medication schedule and follow-up information without losing conversation context.",
        "approach": "The chat Lambda uses Nova Pro with a bounded tool loop, routes requests to separate patient, medication and follow-up functions, and stores recent conversation messages in DynamoDB.",
        "capabilities": ["Persistent conversation sessions", "Model-to-Lambda tool routing", "Patient-data operations", "Medication tracking", "Follow-up and appointment operations"],
        "stack": ["Python", "Nova Pro", "Bedrock Converse", "Lambda", "DynamoDB", "API Gateway", "S3", "CloudFront"],
        "evidence": ["Inspected chat and four supporting Lambda implementations.", "Chat code limits the tool loop to five rounds and retains up to 20 history messages.", "Verified session, patient and follow-up tables, APIs and an existing AgentCore runtime."],
        "limitations": "An existing prototype, not a validated clinical service. The audit found tool-dispatch contracts that need integration tests before a live rollout. The public demo reads synthetic instructions and changes only temporary browser state; it does not change medical advice or book appointments.",
        "architecture": ["Patient question", "Load session history", "Choose relevant tool", "Read care-plan data", "Save conversation"],
        "demoTitle": "Explore a sample follow-up workflow",
        "demoDescription": "Inspect a synthetic care plan, record a sample task, or see the next follow-up. This demonstrates workflow state, not treatment advice.",
        "options": [{"value": "plan", "label": "View care-plan checklist"}, {"value": "confirm", "label": "Confirm a sample care-plan task"}, {"value": "followup", "label": "View the next follow-up"}],
        "secondary": [],
        "action": "Run sample workflow",
        "lesson": "Persistent state and clear tool contracts matter as much as the conversational model. Validate every tool interface before connecting a live care workflow.",
    },
    "clinical-fhir": {
        "title": "Clinical / FHIR tools",
        "subtitle": "Structured observation lookup and a separate clinical tool-use prototype.",
        "category": "Healthcare data integration",
        "color": "#2445bf",
        "problem": "Clinical information arrives in structured bundles. A useful assistant needs to retrieve the requested observation without treating an entire record as unstructured prose.",
        "approach": "The FHIR lookup Lambda finds a patient bundle in S3, maps supported observation names to LOINC codes, selects the latest matching observation, and handles component values such as blood pressure. A separate Nova Lite prototype exposes patient and appointment tool schemas with stub results.",
        "capabilities": ["FHIR Patient and Observation parsing", "LOINC-based lookup", "Latest-observation selection", "Component-value extraction", "Model tool-schema design"],
        "stack": ["Python", "FHIR JSON", "LOINC mappings", "AWS Lambda", "S3", "Bedrock Converse", "Nova Lite"],
        "evidence": ["Inspected fhir-tool source, including patient parsing and observation selection.", "Verified the clinical-data bucket and clinical Lambda resources exist.", "Inspected clinical-mcp-server: it uses Bedrock tool calls and sample tool responses, not a verified MCP protocol implementation."],
        "limitations": "Observation extraction and the clinical chat are separate prototypes. The chat's registration, records and appointment responses are stubs, not a production hospital integration. No interoperability certification or clinical validation is claimed. The live public adapter queries a synthetic FHIR fixture through real deterministic tools.",
        "architecture": ["Requested observation", "Map to LOINC code", "Match FHIR resources", "Choose latest record", "Return structured values"],
        "demoTitle": "Query a synthetic FHIR bundle",
        "demoDescription": "Choose an observation to inspect its code, dated values and source. The lookup operates on a small synthetic fixture.",
        "options": [{"value": "blood-pressure", "label": "Blood pressure"}, {"value": "heart-rate", "label": "Heart rate"}, {"value": "weight", "label": "Weight"}],
        "secondary": [],
        "action": "Look up observation",
        "lesson": "Keep structured clinical data structured. Show the observation's identity, code, date and source rather than asking a model to invent missing fields.",
    },
    "aid": {
        "title": "AID clinician dashboard",
        "subtitle": "A patient-context interface for an agent with external evidence tools.",
        "category": "Agent interfaces + evidence orchestration",
        "color": "#6142b6",
        "problem": "A clinician-facing workspace needs a clear way to select patient context, ask focused questions and distinguish record facts from external evidence.",
        "approach": "The existing static dashboard sends a patient ID and prompt to an API Gateway/Lambda adapter. The AgentCore source uses a Nova Pro tool loop to read FHIR data and selectively query guidelines, medication recalls, environmental context and recent therapy evidence.",
        "capabilities": ["Patient-context dashboard", "API-to-AgentCore integration", "Selective tool orchestration", "Source-aware brief design", "Separation of facts and AI interpretation"],
        "stack": ["HTML / JavaScript", "CloudFront", "S3", "API Gateway", "Lambda", "AgentCore", "Nova Pro", "Bedrock KB", "openFDA", "NOAA"],
        "evidence": ["Inspected the existing dashboard HTML and aid-chat-api Lambda.", "Downloaded and inspected the AgentCore entry point and tool implementation.", "Source asks for patient facts, AI interpretation and external evidence labels; the runtime reports READY."],
        "limitations": "Runtime configuration and code were verified, not the quality of every clinical brief. A full end-to-end clinical evaluation was not performed. The live public assistant uses synthetic record tools and explains evidence gaps; it provides no diagnoses, treatment recommendations or live regulatory claims.",
        "architecture": ["Select patient context", "Submit focused question", "Read FHIR record", "Choose evidence tools", "Render a sourced brief"],
        "demoTitle": "Explore an example evidence-review plan",
        "demoDescription": "Select a synthetic profile and inspect which tools could be relevant. The live chat uses Nova Lite with synthetic record tools; the optional walkthrough remains scripted.",
        "options": [{"value": "followup", "label": "Sample follow-up profile"}, {"value": "medication", "label": "Sample medication-review profile"}],
        "secondary": [],
        "action": "Show example review plan",
        "lesson": "A good agent interface makes context and provenance visible. Tool implementation, model interpretation and clinical validation are separate layers.",
    },
}

LINKEDIN_COPY = """LINKEDIN SERVICES DESCRIPTION

I’m Anamika Singh, founder of Talent Vector Lab. I build AI applications and websites, with a focus on useful workflows, deliberate colour, clear language and storytelling. My services include RAG assistants, workflow agents, website design and AWS/Vercel integration.

Explore two newly launched websites—Talent Vector Lab (https://www.talentvector.in/) and Story Lab (https://www.aikid.in/)—alongside five AI projects: an RxDx RAG Q&A bot; FundBot's supporter and outreach workflows; a post-discharge assistant prototype; clinical/FHIR observation tools; and an AID clinician dashboard with evidence tools.

The portfolio includes a live RxDx bot, code-audited case studies, and live AI demos with synthetic data. Prototype features and limitations are clearly identified. Development is AI-assisted, with attention to testable behavior, source traceability and practical cloud integration.

View my services and project demonstrations:
https://anamikasingh.vercel.app/#services

Discuss your project:
https://www.linkedin.com/in/techntrek

SHORT HEADLINE
Founder, Talent Vector Lab | AI applications, website design & storytelling

FEATURED LINK TITLE
Anamika Singh — AI projects, demos and services

FEATURED LINK
https://anamikasingh.vercel.app/

POST DRAFT
I’ve brought two newly launched websites, Talent Vector Lab and Story Lab, alongside five AI projects in one portfolio: a deployed RxDx RAG Q&A bot, supporter outreach workflows, a post-discharge assistant, FHIR observation tools and a clinician-facing agent dashboard.

Each case study explains the problem, architecture, implemented behavior and remaining work. RxDx has a live bot; the other projects have live synthetic-data assistants alongside details verified from the older deployed source code.

I’m open to discussing website design, brand language, knowledge assistants, workflow automation and AI application integration.

Explore the work and services: https://anamikasingh.vercel.app/
"""


def case_page(slug: str) -> str | None:
    if slug == "rxdx":
        return (ROOT / "rxdx-case.html").read_text()
    case = CASES.get(slug)
    if case is None:
        return None
    data = json.dumps({**case, "slug": slug}, ensure_ascii=False).replace("<", "\\u003c")
    return ((ROOT / "project-case.html").read_text()
            .replace("__TITLE__", html.escape(case["title"]))
            .replace("__SUBTITLE__", html.escape(case["subtitle"]))
            .replace("__DATA__", data))
