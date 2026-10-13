"""Exercise the real hosted adapters, replacing only external model inference."""
from types import SimpleNamespace

import pytest

from web import core
from navigator import bedrock as nav_bedrock
from rxdx_qna import bedrock as qna_bedrock
from rxdx_qna.chunking import Chunk
from rxdx_qna.index import Hit


@pytest.mark.parametrize("kind,module", [("nav", nav_bedrock), ("qna", qna_bedrock)])
def test_bedrock_replays_conversation_and_returns_answer(monkeypatch, kind, module):
    requests = []
    def converse(**request):
        requests.append(request)
        return {"output": {"message": {"role": "assistant", "content": [{"text": "Monday.[1]"}]}},
                "stopReason": "end_turn", "usage": {"inputTokens": 1, "outputTokens": 1}}
    monkeypatch.setattr(module, "client", lambda token: SimpleNamespace(converse=converse))
    chunk = Chunk("doctor:a", "doctor", "Dr A", "https://rxdx.in/consultants/a/", "Dr A works Monday.")
    monkeypatch.setattr(core, "retriever", lambda: SimpleNamespace(search=lambda query, k: [Hit(chunk, 1.0)]))
    result = core.answer(kind, "Which day?", [
        {"role": "user", "text": "Tell me about Dr A"},
        {"role": "assistant", "text": "Dr A is a consultant."},
    ], "bedrock", "token")
    assert result["text"] == "Monday.[1]"
    assert requests[0]["messages"][:2] == [
        {"role": "user", "content": [{"text": "Tell me about Dr A"}]},
        {"role": "assistant", "content": [{"text": "Dr A is a consultant."}]},
    ]
    if kind == "qna":
        assert result["sources"][0]["url"] == "https://rxdx.in/consultants/a/"
