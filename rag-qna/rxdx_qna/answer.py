"""Generation: answer from retrieved chunks with Claude, citing every claim.

Chunks go to the model as `document` blocks with citations enabled, so the API itself ties
each sentence of the answer to the passage it came from. That is stronger than asking the
model to write "[3]" by hand: a citation the API returns is guaranteed to quote text that
was actually in the document.

The API key is read from the environment by the SDK (ANTHROPIC_API_KEY, or an
`ant auth login` profile). It is never passed in code, logged, or written to disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote

import anthropic

from .index import Hit, Retriever

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM = """You are the help-desk assistant for RxDx Clinics, a multispeciality outpatient \
network in Bengaluru. You answer questions from patients and visitors about doctors, \
specialities, clinic branches, schedules and services.

Answer only from the documents provided with each question. If they do not contain the \
answer, say so plainly and suggest calling +91 901 409 1111 or WhatsApp +91 90199 61402 — \
never fill the gap from general knowledge, and never invent a doctor, a day, a price or a \
phone number.

You are not a clinician. Do not diagnose, interpret symptoms, or recommend treatment or \
medication; you may say which speciality usually handles a concern and who at RxDx \
practises it. If someone describes an emergency (chest pain, difficulty breathing, severe \
bleeding, stroke signs, loss of consciousness), tell them first to call 108 or go to the \
nearest emergency department — RxDx clinics are outpatient clinics.

Keep answers short and practical: lead with the direct answer, then the details a patient \
needs to act on it (which doctor, which clinic, which days). Schedules on the website can \
change, so suggest confirming before visiting."""


def review_links(name: str) -> dict[str, str]:
    """Search links for a doctor's public reviews — searches, not ratings.

    No rating is fetched or shown: matching a rating to a doctor by name is unreliable
    (namesakes, initials), and a wrong rating on a doctor misleads patients. The quoted
    name plus "RxDx"/"Bengaluru" narrows the search; the patient judges the results.
    Practo is reached through a site-restricted Google search because its own search URLs
    are not stable.
    """
    bare = re.sub(r"^(Dr|Ms|Mr|Mrs)\.?\s+", "", name).replace("(PT)", "").strip()
    return {
        "google": "https://www.google.com/search?q=" + quote(f'"{bare}" RxDx Bengaluru reviews'),
        "practo": "https://www.google.com/search?q=" + quote(f'site:practo.com "{bare}" Bangalore'),
    }


@dataclass
class Source:
    n: int
    title: str
    url: str
    reviews: dict[str, str] | None = None  # doctors only


@dataclass
class Answer:
    text: str
    sources: list[Source]
    hits: list[Hit]
    stop_reason: str | None
    model: str | None = None
    usage: dict = field(default_factory=dict)


def _documents(hits: list[Hit]) -> list[dict]:
    return [
        {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": h.chunk.text},
            "title": h.chunk.title,
            "context": f"Source: {h.chunk.url}",
            "citations": {"enabled": True},
        }
        for h in hits
    ]


def _render(content, hits: list[Hit]) -> tuple[str, list[Source]]:
    """Inline the API's citations as [n] markers, numbered by distinct source page."""
    by_title = {h.chunk.title: h.chunk for h in hits}
    sources: dict[str, Source] = {}
    out: list[str] = []
    for block in content:
        if block.type != "text":
            continue
        out.append(block.text)
        marks: list[int] = []
        for c in getattr(block, "citations", None) or []:
            chunk = by_title.get(getattr(c, "document_title", None) or "")
            if chunk is None:
                continue
            if chunk.url not in sources:
                reviews = review_links(chunk.title) if chunk.kind == "doctor" else None
                sources[chunk.url] = Source(len(sources) + 1, chunk.title, chunk.url, reviews)
            if sources[chunk.url].n not in marks:
                marks.append(sources[chunk.url].n)
        if marks:
            out.append("".join(f"[{n}]" for n in marks))
    return "".join(out).strip(), list(sources.values())


class QnABot:
    """A conversation. History is append-only: each turn's documents stay in the turn that
    asked for them, and assistant turns are stored exactly as returned. Rewriting earlier
    turns would invalidate both the prompt cache and the model's preserved thinking."""

    def __init__(self, retriever: Retriever | None = None, k: int = 8, effort: str = "medium"):
        self.retriever = retriever or Retriever()
        self.client = anthropic.Anthropic()
        self.k = k
        self.effort = effort
        self.messages: list[dict] = []
        self._last_question: str | None = None

    def ask(self, question: str) -> Answer:
        # Follow-ups ("what days is she in?") carry no searchable terms of their own, so the
        # previous question rides along in the retrieval query — but not in the prompt.
        query = f"{self._last_question} {question}" if self._last_question else question
        hits = self.retriever.search(query, k=self.k)
        self._last_question = question

        self.messages.append(
            {"role": "user", "content": [*_documents(hits), {"type": "text", "text": question}]}
        )
        with self.client.beta.messages.stream(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=self.messages,
            output_config={"effort": self.effort},
            cache_control={"type": "ephemeral"},
            betas=[FALLBACK_BETA],
            extra_body={"fallbacks": "default"},
        ) as stream:
            msg = stream.get_final_message()
        self.messages.append({"role": "assistant", "content": msg.content})

        if msg.stop_reason == "refusal":
            text = "I can't help with that here. Please call RxDx on +91 901 409 1111."
            return Answer(text, [], hits, msg.stop_reason, msg.model)
        text, sources = _render(msg.content, hits)
        usage = {
            "input": msg.usage.input_tokens,
            "output": msg.usage.output_tokens,
            "cache_read": getattr(msg.usage, "cache_read_input_tokens", 0) or 0,
        }
        return Answer(text, sources, hits, msg.stop_reason, msg.model, usage)
