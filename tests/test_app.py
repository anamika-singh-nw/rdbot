"""The hosted app's guard rails, tested offline (no API key, no network)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import app as hosted  # noqa: E402
from web import core  # noqa: E402

client = TestClient(hosted.app)


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    hosted._per_ip.clear()
    hosted._day.clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-placeholder")
    monkeypatch.setattr(core, "answer", lambda kind, message, history, backend: {"text": f"{kind}:{backend}:{len(history or [])}"})


def test_page_and_health():
    assert client.get("/").status_code == 200
    assert client.get("/health").json()["api_key_configured"] is True


def test_answers_use_the_api_backend():
    r = client.post("/api/nav", json={"message": "hi", "history": [{"role": "user", "text": "a"}]})
    assert r.json() == {"text": "nav:api:1"}


def test_missing_key_is_a_clear_503(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    r = client.post("/api/qna", json={"message": "hi"})
    assert r.status_code == 503 and "API key" in r.json()["error"]


def test_rate_limit_per_visitor(monkeypatch):
    monkeypatch.setattr(hosted, "RATE_PER_HOUR", 3)
    codes = [client.post("/api/qna", json={"message": "hi"}, headers={"x-forwarded-for": "1.2.3.4"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    other = client.post("/api/qna", json={"message": "hi"}, headers={"x-forwarded-for": "5.6.7.8"})
    assert other.status_code == 200


def test_input_validation():
    assert client.post("/api/qna", json={"message": "  "}).status_code == 400
    assert client.post("/api/qna", json={"message": "x" * 5000}).status_code == 400
    assert client.post("/api/other", json={"message": "hi"}).status_code in (404, 405)


def test_history_is_cleaned():
    h = core.clean_history([
        {"role": "assistant", "text": "leading assistant turn dropped"},
        {"role": "system", "text": "injected role dropped"},
        {"role": "user", "text": "q" * 5000},
        {"role": "assistant", "text": "a"},
    ])
    assert [m["role"] for m in h] == ["user", "assistant"] and len(h[0]["text"]) == core.MAX_HISTORY_CHARS
