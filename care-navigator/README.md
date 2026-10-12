# RxDx Care Navigator (tool-use agent)

An agent that turns a patient's problem and constraints into a specific doctor, branch and
day, and drafts a booking request when they're ready.

```
you › My 6 year old keeps getting ear infections. We can only come on Saturdays.

  → find_doctors(speciality='Paediatric ENT', day='Saturday', mode='any')  0 match(es)
  → find_doctors(speciality='ENT', day='Saturday', mode='in_clinic')       9 match(es)
  → find_doctors(speciality='Paediatrics', day='Saturday', mode='in_clinic') …

No paediatric ENT specialist is listed on Saturdays, so I widened the search to ENT
consultants who see children. Here are a few options …
```

*(Illustrative: the shape of a run with `-v`. Every doctor, branch and day in a real answer comes from a tool.)*

> Independent project built from rxdx.in's public pages. It is not affiliated with RxDx, it does not give
> medical advice, and it does not book appointments.

## Why an agent, not RAG

[`rag-qna`](../rag-qna) retrieves passages of text to answer questions. That's the wrong tool for "an ENT doctor in Whitefield who's in on Saturdays and speaks Kannada". That is a **filter over fields**, and a filter can be exact. Here Claude handles the judgement:
- mapping "ear infections in a child" to a speciality;
- deciding which constraint to relax when nothing matches;
- explaining the trade-offs.

Deterministic tools handle every fact:

| tool | what it does |
| --- | --- |
| `find_doctors` | filter by speciality, branch, day, in-clinic or tele, language and name; returns real availability |
| `get_doctor` | full profile: qualifications, experience, overview |

Every doctor result also carries `review_search_links`: a Google search and a Practo search for that doctor. These are searches, **not ratings**. Matching a star rating to a doctor by name alone is unreliable (namesakes, initials), and a wrong rating on a doctor would mislead patients, so the agent is told never to state a rating itself.
| `list_specialities` / `list_branches` | the valid vocabulary, used when the model is unsure |
| `prepare_booking_request` | a WhatsApp-ready **draft**; it fails if the doctor isn't at that branch on that day |

## How it works

- **`navigator/directory.py`** normalises the scrape into fields:
  - 25 clinic spellings resolve to 14 branches.
  - Day ranges ("Monday to Saturday") are expanded.
  - Speciality matching compares word roots, so Dermatologist = Dermatology and Pediatrics = Paediatrician. It never matches substrings, so "ENT" doesn't match inside "appointment".
- **Mislabelled profiles:** 21 profiles on rxdx.in show another consultant's name and title; the scraper picked up the wrong heading, and "Dr Sireesh V" appears on 11 pages. For these, the name is rebuilt from the page URL, the unreliable title and overview are dropped, and the tool tells the model to have the patient confirm with the clinic. The same fix is applied in `rag-qna`.
- **`navigator/safety.py`** screens every message *before* the model sees it. Red flags (chest pain, stroke signs, breathing difficulty, seizures, self-harm, a fever in a newborn, …) get a fixed reply: call 108, or Tele-MANAS on 14416 for self-harm. The model is never called, because the response to "crushing chest pain" shouldn't depend on sampling. Negated mentions ("no chest pain") pass through.
- **`navigator/agent.py`** is a hand-written tool loop around `claude-opus-5-5`:
  - Tool schemas are `strict`, so arguments always validate.
  - Tool errors go back to the model as `is_error` results so it can correct course; they never crash the loop.
  - Parallel tool calls are answered in a single message.
  - There is a cap of 8 model calls per turn.
  - History is append-only.
  - `fallbacks: "default"` retries a safety-classifier decline on Anthropic's recommended fallback model.

## Setup

Requires Python 3.10+. Uses the shared knowledge base at `../data/rxdx.json`.

```bash
cd care-navigator
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Tools work without any API key:
python -m navigator tool find_doctors '{"speciality": "Dermatology", "branch": "Whitefield", "day": "Monday"}'

# The agent needs Claude API access (env var, or `ant auth login`). See .env.example.
export ANTHROPIC_API_KEY=...
python -m navigator chat -v          # -v prints every tool call
```

**No API key? Use your Claude Code login instead.** Add `--backend cli` to `ask` or `chat` and the agent calls the local `claude` CLI in headless mode. That CLI is locked down: no tools, none of your MCP connectors, no skills and no local settings. It runs on your Claude subscription, so use it only for local demos. Anything other people use should run on the API. Over the CLI, each step returns structured JSON (tool calls or a reply), and the same loop runs the same tools.

## Tests and evals

```bash
python -m pytest                     # 52 tests, offline, no API key
python eval/run_scenarios.py         # 12 live scenarios — calls the API, costs money
```

**Offline tests:**
- `test_directory` checks the normalisation, the mislabel fix, and that filters are exact.
- `test_tools` checks the strict schemas, the errors the model can recover from, and that booking requests are validated.
- `test_safety` checks that emergencies are caught and routine requests (including negated ones) pass.
- `test_agent` drives the loop with a stub client. It covers tool execution, parallel results, error results, append-only history, the emergency short-circuit, the step cap and refusals.
- `test_no_secrets` fails if anything that looks like a credential is in the repository.

**The scenario eval** is graded by code, not by another model. A navigation answer passes if every doctor it names:
- was returned by a tool during that turn, so nothing is invented;
- **and** actually meets the scenario's constraints, checked against the directory.

Other scenarios check that emergencies are caught, that a vague request gets a clarifying question, and that a non-existent branch is reported as missing.

## Limitations

- The scenario eval has not been run yet; it uses the API backend. The agent has been run live through the CLI backend: a Saturday, Kannada-speaking ENT request returned six doctors, and all six were checked against the directory.
- Booking requests are drafts. Nothing is sent and nothing is booked.
- The directory is a snapshot from 2026-08-26. Of the 254 doctors, 12 map to no branch and 25 have no published days, and the agent says so rather than guessing.
- The safety screen is keyword-based and leans towards firing. It's a backstop, not triage.
