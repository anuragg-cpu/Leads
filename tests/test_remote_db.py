"""Tests for RemoteDatabase, the HTTP client `abhayleads` uses when pointed
at someone else's `abhayleads serve` instance. No real network - a fake
requests.Session records calls and returns canned responses."""

import pytest

from abhayleads.models import LeadCandidate
from abhayleads.remote_db import RemoteDatabase, RemoteDatabaseError


class FakeResponse:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json_body = json_body
        self.content = b"1" if json_body is not None else b""
        self.ok = status_code < 400

    def json(self):
        return self._json_body


class FakeSession:
    def __init__(self, responses):
        # responses: dict of (method, path) -> FakeResponse, or a single
        # FakeResponse reused for every call.
        self.responses = responses
        self.headers = {}
        self.calls = []

    def request(self, method, url, timeout=None, **kwargs):
        self.calls.append((method, url, kwargs))
        if isinstance(self.responses, dict):
            key = (method, url)
            return self.responses[key]
        return self.responses

    def close(self):
        pass


def make_db(monkeypatch, responses, base_url="http://example.com", token="tok"):
    db = RemoteDatabase(base_url, token)
    fake = FakeSession(responses)
    monkeypatch.setattr(db, "session", fake)
    return db, fake


def test_requires_base_url_and_token():
    with pytest.raises(ValueError):
        RemoteDatabase("", "tok")
    with pytest.raises(ValueError):
        RemoteDatabase("http://example.com", "")


def test_sets_bearer_auth_header():
    db = RemoteDatabase("http://example.com", "secret-tok")
    assert db.session.headers["Authorization"] == "Bearer secret-tok"


def test_upsert_candidate_sends_expected_payload_and_parses_response(monkeypatch):
    db, fake = make_db(
        monkeypatch,
        {("POST", "http://example.com/api/leads/upsert"): FakeResponse(200, {"id": 7, "is_new": True})},
    )
    candidate = LeadCandidate(source="manual", source_detail="s1", company="Acme", raw_text="hi")
    lead_id, is_new = db.upsert_candidate(candidate, 42)

    assert (lead_id, is_new) == (7, True)
    method, url, kwargs = fake.calls[0]
    assert kwargs["json"]["company"] == "Acme"
    assert kwargs["json"]["score"] == 42


def test_list_leads_builds_query_params(monkeypatch):
    db, fake = make_db(monkeypatch, {("GET", "http://example.com/api/leads"): FakeResponse(200, [])})
    db.list_leads(stage="New", source="hackernews", min_score=5, due_only=True, search="acme")
    _, _, kwargs = fake.calls[0]
    assert kwargs["params"] == {
        "min_score": 5,
        "stage": "New",
        "source": "hackernews",
        "due_only": "true",
        "search": "acme",
    }


def test_get_lead_returns_none_on_404(monkeypatch):
    db, _ = make_db(monkeypatch, {("GET", "http://example.com/api/leads/1"): FakeResponse(404, {"detail": "no"})})
    assert db.get_lead(1) is None


def test_get_lead_returns_dict_on_success(monkeypatch):
    db, _ = make_db(
        monkeypatch, {("GET", "http://example.com/api/leads/1"): FakeResponse(200, {"id": 1, "company": "Acme"})}
    )
    assert db.get_lead(1) == {"id": 1, "company": "Acme"}


def test_401_raises_with_status_code(monkeypatch):
    db, _ = make_db(monkeypatch, {("GET", "http://example.com/api/stats"): FakeResponse(401, {"detail": "no"})})
    with pytest.raises(RemoteDatabaseError) as exc_info:
        db.stats()
    assert exc_info.value.status_code == 401


def test_other_http_errors_include_detail(monkeypatch):
    db, _ = make_db(
        monkeypatch,
        {("POST", "http://example.com/api/reset"): FakeResponse(400, {"detail": "Pass confirm=true"})},
    )
    with pytest.raises(RemoteDatabaseError) as exc_info:
        db.delete_all_leads()
    assert exc_info.value.status_code == 400
    assert "Pass confirm=true" in str(exc_info.value)


def test_connection_error_is_wrapped(monkeypatch):
    import requests

    db = RemoteDatabase("http://example.com", "tok")

    def raise_conn_error(*args, **kwargs):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(db.session, "request", raise_conn_error)
    with pytest.raises(RemoteDatabaseError):
        db.stats()


def test_update_lead_sends_all_fields(monkeypatch):
    db, fake = make_db(monkeypatch, {("PATCH", "http://example.com/api/leads/5"): FakeResponse(200, {"ok": True})})
    db.update_lead(5, stage="Contacted", notes="called")
    _, _, kwargs = fake.calls[0]
    assert kwargs["json"]["stage"] == "Contacted"
    assert kwargs["json"]["notes"] == "called"
    assert kwargs["json"]["company"] is None


def test_delete_all_leads_returns_removed_count(monkeypatch):
    db, fake = make_db(
        monkeypatch, {("POST", "http://example.com/api/reset"): FakeResponse(200, {"removed": 12})}
    )
    assert db.delete_all_leads() == 12
    _, _, kwargs = fake.calls[0]
    assert kwargs["json"] == {"confirm": True}


def test_fetch_run_lifecycle(monkeypatch):
    db, fake = make_db(
        monkeypatch,
        {
            ("POST", "http://example.com/api/fetch_runs"): FakeResponse(200, {"run_id": 9}),
            ("PATCH", "http://example.com/api/fetch_runs/9"): FakeResponse(200, {"ok": True}),
            ("GET", "http://example.com/api/fetch_runs/last"): FakeResponse(200, {"id": 9, "new_leads": 3}),
        },
    )
    run_id = db.start_fetch_run(["hackernews"])
    assert run_id == 9
    db.finish_fetch_run(9, new_leads=3, updated_leads=1, errors=[])
    last = db.last_fetch_run()
    assert last["id"] == 9


def test_digest_get_set_and_summary(monkeypatch):
    db, fake = make_db(
        monkeypatch,
        {
            ("GET", "http://example.com/api/digest/last"): FakeResponse(200, {"last_digest_at": "2026-01-01"}),
            ("POST", "http://example.com/api/digest/last"): FakeResponse(200, {"ok": True}),
            ("GET", "http://example.com/api/digest/summary"): FakeResponse(200, {"new_leads": 2}),
        },
    )
    assert db.get_last_digest_at() == "2026-01-01"
    db.set_last_digest_at("2026-02-02")
    summary = db.summarize_since(None)
    assert summary == {"new_leads": 2}
    _, _, kwargs = fake.calls[-1]
    assert kwargs["params"] == {}
