"""The hosted app's guard rails, tested offline (no API key, no network)."""

import sys
import re
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


def test_personal_domain_homepage_opens_portfolio():
    response = client.get("/", headers={"host": "anamikasingh.vercel.app"})
    assert response.status_code == 200
    assert "View my services" in response.text


def test_bot_has_a_stable_path_on_the_personal_domain():
    response = client.get("/bots", headers={"host": "anamikasingh.vercel.app"})
    assert response.status_code == 200
    assert "Care Navigator" in response.text


def test_portfolio_explains_the_original_rag_brief():
    response = client.get("/portfolio")
    assert response.status_code == 200
    assert "Develop a QnA bot for RxDx" in response.text
    assert 'href="/portfolio/deck"' in response.text


def test_portfolio_deck_is_downloadable():
    response = client.get("/portfolio/deck")
    assert response.status_code == 200
    assert response.content[:2] == b"PK"
    assert "attachment" in response.headers["content-disposition"]


@pytest.mark.parametrize("slug,title", [
    ("rxdx", "The original assignment"),
    ("fundbot", "FundBot"),
    ("post-discharge", "Post-discharge"),
    ("clinical-fhir", "Clinical / FHIR"),
    ("aid", "AID"),
])
def test_portfolio_project_pages(slug, title):
    response = client.get(f"/portfolio/{slug}")
    assert response.status_code == 200
    assert title in response.text
    if slug != "rxdx":
        assert "Synthetic data" in response.text
        assert not re.search(r"\b\d{12}\b|arn:aws:", response.text)


def test_portfolio_links_to_linkedin_and_each_project():
    response = client.get("/portfolio")
    assert 'https://www.linkedin.com/in/techntrek' in response.text
    for slug in ("rxdx", "fundbot", "post-discharge", "clinical-fhir", "aid"):
        assert f'href="/portfolio/{slug}"' in response.text


def test_unknown_portfolio_project_is_not_served():
    assert client.get("/portfolio/unknown-project").status_code == 404


def test_linkedin_services_copy_is_available():
    response = client.get("/portfolio/linkedin")
    assert response.status_code == 200
    assert "https://anamikasingh.vercel.app/#services" in response.text


def test_live_demo_route_uses_bedrock_and_passes_history(monkeypatch):
    from web import live_demos
    monkeypatch.setenv("AWS_ROLE_ARN", "arn:aws:iam::123456789012:role/demo")
    def answer(project, message, history, state, token):
        assert project == "fundbot" and message == "Draft an education campaign"
        assert history == [] and token == "signed-token"
        return {"text": "Live draft", "live_ai": True, "tool_calls": [], "state": {}}
    monkeypatch.setattr(live_demos, "answer", answer)
    response = client.post("/api/portfolio/fundbot", headers={"x-vercel-oidc-token": "signed-token"},
                           json={"message": "Draft an education campaign", "history": []})
    assert response.status_code == 200 and response.json()["live_ai"] is True


def test_live_demo_input_validation(monkeypatch):
    monkeypatch.setenv("AWS_ROLE_ARN", "arn:aws:iam::123456789012:role/demo")
    for payload in ([1], {"message": ""}, {"message": "x" * 1001}, {"message": "hi", "history": "bad"}, {"message": "hi", "state": []}):
        assert client.post("/api/portfolio/fundbot", json=payload).status_code == 400
    assert client.post("/api/portfolio/unknown", json={"message": "hi"}).status_code == 404


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


def test_bedrock_can_answer_without_anthropic_key(monkeypatch):
    from types import SimpleNamespace
    from navigator import bedrock

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("BOT_BACKEND", "bedrock")
    monkeypatch.setenv("AWS_ROLE_ARN", "arn:aws:iam::123456789012:role/bot")
    monkeypatch.setattr(core, "answer", _real_answer)
    monkeypatch.setattr(bedrock, "client", lambda token: SimpleNamespace(converse=lambda **kw: {
        "output": {"message": {"role": "assistant", "content": [{"text": "Here are the clinics."}]}},
        "stopReason": "end_turn", "usage": {"inputTokens": 1, "outputTokens": 1},
    }) if token == "signed-token" else None)
    response = client.post("/api/nav", json={"message": "Which clinics are available?"},
                           headers={"x-vercel-oidc-token": "signed-token"})
    assert response.status_code == 200
    assert response.json()["text"] == "Here are the clinics."


def test_bedrock_errors_do_not_expose_account_details(monkeypatch):
    from botocore.exceptions import ClientError

    monkeypatch.setenv("BOT_BACKEND", "bedrock")
    monkeypatch.setenv("AWS_ROLE_ARN", "arn:aws:iam::123456789012:role/bot")
    def fail(*args, **kwargs):
        raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "private account details"}}, "Converse")
    monkeypatch.setattr(core, "answer", fail)
    response = client.post("/api/nav", json={"message": "hello"})
    assert response.status_code == 502
    assert "private" not in response.text


_real_answer = core.answer


@pytest.mark.parametrize('path', ['/privacy', '/enquiry', '/portfolio', '/bots', '/portfolio/rxdx', '/portfolio/fundbot'])
def test_public_pages_share_privacy_controls(path):
    response = client.get(path)
    assert response.status_code == 200
    assert '/portfolio-assets/privacy.js?v=2' in response.text
    assert 'data-cookie-settings' in response.text
    assert 'data-privacy-reset' in response.text
    assert response.headers['referrer-policy'] == 'strict-origin-when-cross-origin'
    assert 'set-cookie' not in response.headers


def test_privacy_notice_matches_deployed_processing():
    page = client.get('/privacy').text
    assert 'ana@talentvector.in' in page
    assert 'portfolio_privacy' in page
    assert '180 days' in page
    assert 'United States' in page
    assert 'not a certification' in page


def test_rate_limit_removes_inactive_visitor_entries(monkeypatch):
    monkeypatch.setattr(hosted.time, 'time', lambda: 10000)
    hosted._per_ip['old-visitor'].append(6399)
    hosted._per_ip['recent-visitor'].append(9999)
    assert hosted._allow('new-visitor') is None
    assert 'old-visitor' not in hosted._per_ip
    assert 'recent-visitor' in hosted._per_ip
