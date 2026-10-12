"""Generation plumbing, tested offline with a stub client — no API key, no network."""

from types import SimpleNamespace as NS

from rxdx_qna.answer import MODEL, QnABot, _documents, _render
from rxdx_qna.chunking import Chunk
from rxdx_qna.index import Hit

A = Chunk("doctor:a", "doctor", "Dr A", "https://rxdx.in/consultants/a/", "Dr A sees patients on Monday.")
B = Chunk("page:p#0", "page", "Pharmacy", "https://rxdx.in/pharmacy/", "We deliver medicines.")
HITS = [Hit(A, 1.0), Hit(B, 0.5)]


def cite(title):
    return NS(type="char_location", document_title=title, cited_text="x")


def test_documents_enable_citations():
    docs = _documents(HITS)
    assert all(d["citations"] == {"enabled": True} for d in docs)
    assert docs[0]["title"] == "Dr A" and docs[0]["source"]["data"] == A.text


def test_render_numbers_sources_by_page():
    content = [
        NS(type="thinking", thinking=""),
        NS(type="text", text="Dr A is in on Monday.", citations=[cite("Dr A")]),
        NS(type="text", text=" Medicines are delivered.", citations=[cite("Pharmacy"), cite("Dr A")]),
    ]
    text, sources = _render(content, HITS)
    assert text == "Dr A is in on Monday.[1] Medicines are delivered.[2][1]"
    assert [(s.n, s.url) for s in sources] == [(1, A.url), (2, B.url)]


class StubStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


def make_bot(msg, calls):
    bot = QnABot.__new__(QnABot)
    bot.retriever = NS(search=lambda q, k: calls.setdefault("queries", []).append(q) or HITS)
    bot.k, bot.effort, bot.messages, bot._last_question = 8, "medium", [], None

    def stream(**kw):
        calls.setdefault("requests", []).append(kw)
        return StubStream(msg)

    bot.client = NS(beta=NS(messages=NS(stream=stream)))
    return bot


def reply(text="Monday.", stop="end_turn"):
    usage = NS(input_tokens=10, output_tokens=2, cache_read_input_tokens=0)
    return NS(content=[NS(type="text", text=text, citations=[cite("Dr A")])], stop_reason=stop, model=MODEL, usage=usage)


def test_request_shape_and_append_only_history():
    calls = {}
    bot = make_bot(reply(), calls)
    bot.ask("When is Dr A in?")
    bot.ask("And on weekends?")

    req = calls["requests"][-1]
    assert req["model"] == MODEL
    assert req["extra_body"] == {"fallbacks": "default"}
    assert "server-side-fallback-2026-07-01" in req["betas"]
    # First turn is untouched by the second: same object, documents still attached.
    first = bot.messages[0]["content"]
    assert [b["type"] for b in first] == ["document", "document", "text"]
    assert [m["role"] for m in bot.messages] == ["user", "assistant", "user", "assistant"]
    # Follow-up retrieval carries the previous question.
    assert calls["queries"] == ["When is Dr A in?", "When is Dr A in? And on weekends?"]


def test_refusal_is_not_rendered_as_an_answer():
    bot = make_bot(reply(text="", stop="refusal"), {})
    ans = bot.ask("something")
    assert ans.stop_reason == "refusal" and "901 409 1111" in ans.text and ans.sources == []


def test_doctor_sources_get_review_links_pages_do_not():
    content = [NS(type="text", text="See Dr A or the pharmacy.", citations=[cite("Dr A"), cite("Pharmacy")])]
    _, sources = _render(content, HITS)
    doctor, page = sources
    assert set(doctor.reviews) == {"google", "practo"} and '%22A%22' in doctor.reviews["google"]
    assert page.reviews is None


def test_cli_markers_map_to_sources_and_bogus_ones_are_dropped():
    from rxdx_qna.answer import _render_numbered

    text, sources = _render_numbered("Dr A is in Monday [1][1]. Medicines are delivered [2]. Also [9].", HITS)
    assert text == "Dr A is in Monday [1]. Medicines are delivered [2]. Also ."
    assert [(s.n, s.url) for s in sources] == [(1, A.url), (2, B.url)]
    assert sources[0].reviews and sources[1].reviews is None


def test_cli_bot_sends_numbered_passages_and_keeps_history():
    from rxdx_qna.answer import CliQnABot

    seen = []
    bot = CliQnABot.__new__(CliQnABot)
    bot.retriever = NS(search=lambda q, k: HITS)
    bot.k, bot.effort, bot.history, bot._last_question = 8, "medium", [], None
    bot.cli = NS(ask=lambda prompt, system, effort: seen.append((prompt, system)) or "Monday [1].")
    bot.ask("When is Dr A in?")
    ans = bot.ask("Anything else?")
    prompt, system = seen[-1]
    assert "[1] Dr A (https://rxdx.in/consultants/a/)" in prompt and "[2] Pharmacy" in prompt
    assert "Patient: When is Dr A in?" in prompt and "square brackets" in system
    assert ans.text == "Monday [1]." and ans.sources[0].url == A.url
