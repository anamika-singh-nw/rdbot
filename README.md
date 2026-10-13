# AI projects by Anamika Singh

Source code for the RxDx RAG Q&A bot, its Care Navigator extension, and four live AI
portfolio demonstrations. Built with Python, FastAPI, retrieval, structured tools and
Amazon Bedrock. The public demos use Amazon Nova Lite; alternative Anthropic API and
local Claude CLI adapters are also included for RxDx.

**Explore the deployed AI projects:** [portfolio](https://anamikasingh.vercel.app/#work)
· [RxDx bots](https://anamikasingh.vercel.app/bots)

The original assignment was: **“First has to be RAG based. Develop a QnA bot for RxDx
for now.”** The navigator complements that RAG solution. This is independent work,
not affiliated with RxDx, and is not a medical advice or clinical service.

## Code to review

| AI project | What this repository implements | Start here |
| --- | --- | --- |
| **RxDx RAG Q&A** | Source cleanup, overlapping chunks, BM25 + embedding retrieval, reciprocal-rank fusion and source-linked answers over public clinic information | [chunking](rag-qna/rxdx_qna/chunking.py), [retrieval](rag-qna/rxdx_qna/index.py), [answer adapters](rag-qna/rxdx_qna/answer.py) |
| **Care Navigator** — RxDx extension | Exact doctor filters, normalised branches/days/specialities, bounded tool use, emergency backstop and validated booking **drafts** | [directory](care-navigator/navigator/directory.py), [tools](care-navigator/navigator/tools.py), [agent](care-navigator/navigator/agent.py) |
| **FundBot** | Live retrieval over a synthetic nonprofit FAQ, fictional supporter segmentation and outreach drafting; no sends or payments | [fixtures and tools](web/live_demos.py#L16), [live API](app.py), [demo tests](tests/test_live_demos.py) |
| **Post-discharge assistant** | Synthetic care-plan lookup and temporary checklist confirmation state; no patient writes or appointments | [project tool allowlists and state](web/live_demos.py), [client](web/portfolio_assets/live-client.mjs), [tests](tests/test_live_demos.py) |
| **Clinical / FHIR** | Coded Patient/Observation lookup, latest-observation selection and blood-pressure component extraction from a fictional bundle | [FHIR fixture and lookup tools](web/live_demos.py), [tests](tests/test_live_demos.py) |
| **AID assistant demo** | Synthetic patient/observation tools and explicit missing-evidence reporting; no live guideline, FDA or weather lookup | [evidence tool and bounded model loop](web/live_demos.py), [case-study scope](web/portfolio.py) |

**Scope of the four additional demos:** their older AWS prototypes were inspected
and preserved separately. This repository publishes the new Nova Lite adapters,
synthetic fixtures, browser demos and case-study descriptions. It does not contain
private Lambda source archives, donor stores, real patient data or the full older
AgentCore implementations. Existing business/clinical integrations are not claimed
to be validated end to end. The filename of an older clinical prototype is not proof
of a functioning MCP protocol implementation.

## Architecture

```text
RxDx Q&A
public source snapshot -> clean/chunk -> BM25 + local embeddings -> fused passages
visitor question + recent history -> retrieved evidence -> model -> answer + sources

RxDx navigation
visitor constraints -> emergency screen -> model/tool loop -> exact directory tools
                     -> validated options or a booking-request draft

Four portfolio assistants
browser + page permission -> POST /api/portfolio/{project} -> validate and rate-limit
                          -> allowlisted synthetic tools <-> Bedrock Converse
                          -> answer, visible tool calls and temporary demo state
```

`app.py` serves FastAPI routes. `web/core.py` cleans browser history and selects the
RxDx backend. `web/live_demos.py` contains the four public assistants. The small
FundBot fixture uses BM25; RxDx uses the hybrid BM25/embedding index. Those retrieval
implementations are intentionally distinct.

The browser resends the last six plain-text messages rather than relying on a
persistent chat database. Four portfolio assistants are capped at five model rounds;
the navigator at eight calls. These are bounded demos, not unconstrained agents.

## Run locally

Use Python 3.12 to match the last verified Vercel build, and Node.js 20 or newer for
the JavaScript checks. Create your own environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open `/portfolio` for the portfolio and deterministic previews, `/bots` for RxDx,
and `/health` for configuration status. The pages and synthetic previews work
without inference credentials. Live model requests require your own authorised
backend configuration and consume inference usage.

Copy the root `.env.example` if useful, supply your own values, and export them in
your shell; FastAPI does not automatically load that file:

```bash
cp .env.example .env
# Edit .env with your own configuration. It is gitignored.
set -a
source .env
set +a
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

For local Bedrock, set `AWS_ROLE_ARN` to your own approved role ARN as well as
configuring your own authorised AWS credential chain. The current configuration
guard requires that role value even locally; local requests use boto3 credentials
and do not assume the role without a Vercel OIDC token. For hosted
Vercel, configure a role with the exact team/project/production OIDC trust and model
permissions. The published app's AWS role is not a shared credential you can reuse.
For Anthropic, select `BOT_BACKEND=api` and provide your own API key. See
[RxDx setup](rag-qna/README.md) and [navigator setup](care-navigator/README.md) for
project CLI commands; their older notes contain historical model defaults and counts.

The local `demo/server.py` is an additional localhost-only option using an already
configured Claude CLI login. It is not the production authentication path.

## Test and evaluate

After installing `requirements-dev.txt`, run from the repository root:

```bash
python -m pytest --import-mode=importlib \
  tests rag-qna/tests care-navigator/tests
node --test tests/test_live_client.mjs tests/test_portfolio_demos.mjs
python rag-qna/eval/run_retrieval.py --misses
```

Last verified on 13 October 2026: **117 Python tests + 13 Node tests passed**.
These cover API contracts, tool behaviour, retrieval, history, emergency-screen
examples, source checks, the browser fetch-receiver regression and privacy refusal.
They do not constitute a full browser, clinical or regulatory evaluation.

The 26 August 2026 public source snapshot has **343 records**: 254 doctors,
14 branches, 49 speciality archives and 26 pages, producing **427 chunks**. The
committed index is about 1.3 MB and uses a NumPy vector matrix, not a hosted vector
database. Rebuild it after changing the corpus:

```bash
PYTHONPATH=rag-qna python -m rxdx_qna build
```

On the 30-question retrieval evaluation, the hybrid retriever produced
hit@1 **0.83**, hit@3 **0.93**, hit@8 **1.00** and MRR **0.889**. These are retrieval
results on a small curated set, not generated-answer accuracy. Current source gaps
include 21 suspect identity profiles, 12 doctors with no mapped branch, and 18 with
no published days; code preserves uncertainty rather than inventing availability.

## Hosting and authentication

Production is hosted by the existing Vercel project with a personal-domain alias.
The configuration selects:

```text
BOT_BACKEND=bedrock
BEDROCK_MODEL_ID=us.amazon.nova-lite-v1:0
AWS_REGION=us-east-1
AWS_ROLE_ARN=<your scoped role, configured outside source control>
```

A request's Vercel OIDC token is exchanged through AWS STS for short-lived role
credentials. The role's trust is limited to the intended team, project and production
environment, and permissions are scoped to model invocation. Permanent AWS access
keys and model API keys are not committed or needed on the deployed Bedrock path.

The deployed demos use AWS Free-plan credits. Inference is **not unlimited free
compute**. Eligibility, remaining credits and account-plan limits depend on the
account; use your own authorised configuration and check your costs.

Default rate limits are 15 messages per visitor per hour and 400 per instance per
day. In-memory counters are best-effort and are not a durable global spending cap.
Embedding caches use `/tmp` on Vercel. The committed index avoids rebuilding the
corpus during each request.

## Privacy and sharing boundaries

The public notice is `/privacy`. No analytics or advertising trackers are installed.
A first-party preference cookie is saved only when requested; visitors can continue
without it. Separate page-local permission precedes browser AI requests, and the
portfolio client fails closed if that controller is unavailable. These frontend
controls are not a server-side consent ledger or certification of DPDP/GDPR compliance.

Public healthcare demos use fictional records; RxDx uses published clinic data.
Do not enter personal health records, confidential business information or credentials.
The project-brief builder runs in browser memory and does not submit or send a
message automatically.

Private learning notes, local account/configuration directories, `.env` files and
virtual environments are excluded from Git. This repository
does not publish source for the separate business websites. Its HTML/CSS files are
the AI portfolio and demonstration interfaces, not those standalone websites.

The public RxDx case-study deck is included because `/portfolio/deck` serves it;
it is separate from the private learning handbook, which is excluded.
