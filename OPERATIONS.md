# Setup, deployment and demo scope

Additional operational details for the [AI projects portfolio](README.md).

## Backend configuration

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

## Additional demo scope

their older AWS prototypes were inspected
and preserved separately. This repository publishes the new Nova Lite adapters,
synthetic fixtures, browser demos and case-study descriptions. It does not contain
private Lambda source archives, donor stores, real patient data or the full older
AgentCore implementations. Existing business/clinical integrations are not claimed
to be validated end to end. The filename of an older clinical prototype is not proof
of a functioning MCP protocol implementation.

## Source maintenance

The 26 August 2026 snapshot includes 254 doctors, 14 branches, 49 speciality archives and 26 pages. Current gaps include 21 suspect identity profiles, 12 doctors with no mapped branch and 18 with no published days. The code preserves that uncertainty.

Rebuild the committed index after changing the corpus:

```bash
PYTHONPATH=rag-qna python -m rxdx_qna build
```
