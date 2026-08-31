"""Tests for the `abhayleads serve` FastAPI app (JSON API + web UI), using
FastAPI's in-process TestClient - no real network or subprocess involved."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from abhayleads.server.app import create_app

TOKEN = "test-token-123"


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        app = create_app(db_path, {"server": {"token": TOKEN}})
        yield TestClient(app)


def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_create_app_requires_a_token():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        with pytest.raises(RuntimeError):
            create_app(db_path, {"server": {"token": ""}})


def test_health_requires_no_auth(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_api_rejects_missing_or_wrong_token(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 401

    resp = client.get("/api/stats", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_api_lead_crud_roundtrip(client):
    resp = client.post(
        "/api/leads/upsert",
        headers=auth_headers(),
        json={"source": "manual", "source_detail": "s1", "company": "Acme", "raw_text": "hi", "score": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    lead_id = body["id"]
    assert body["is_new"] is True

    resp = client.get(f"/api/leads/{lead_id}", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["company"] == "Acme"

    resp = client.get("/api/leads/999999", headers=auth_headers())
    assert resp.status_code == 404

    resp = client.patch(f"/api/leads/{lead_id}", headers=auth_headers(), json={"stage": "Contacted"})
    assert resp.status_code == 200

    resp = client.get(f"/api/leads/{lead_id}/history", headers=auth_headers())
    assert resp.status_code == 200
    assert [row["stage"] for row in resp.json()] == ["New", "Contacted"]

    resp = client.patch("/api/leads/999999", headers=auth_headers(), json={"stage": "Contacted"})
    assert resp.status_code == 400

    resp = client.delete(f"/api/leads/{lead_id}", headers=auth_headers())
    assert resp.status_code == 200
    resp = client.get(f"/api/leads/{lead_id}", headers=auth_headers())
    assert resp.status_code == 404


def test_api_list_leads_and_stats(client):
    client.post(
        "/api/leads/upsert",
        headers=auth_headers(),
        json={"source": "manual", "source_detail": "s1", "company": "Acme", "score": 10},
    )
    resp = client.get("/api/leads", headers=auth_headers())
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.get("/api/stats", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_api_fetch_runs_and_digest(client):
    resp = client.post("/api/fetch_runs", headers=auth_headers(), json={"sources_run": ["manual"]})
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    resp = client.patch(
        f"/api/fetch_runs/{run_id}", headers=auth_headers(), json={"new_leads": 3, "updated_leads": 1}
    )
    assert resp.status_code == 200

    resp = client.get("/api/fetch_runs/last", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["new_leads"] == 3

    resp = client.get("/api/digest/last", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["last_digest_at"] is None

    resp = client.post(
        "/api/digest/last", headers=auth_headers(), json={"last_digest_at": "2026-01-01T00:00:00+00:00"}
    )
    assert resp.status_code == 200

    resp = client.get("/api/digest/last", headers=auth_headers())
    assert resp.json()["last_digest_at"] == "2026-01-01T00:00:00+00:00"

    resp = client.get("/api/digest/summary", headers=auth_headers())
    assert resp.status_code == 200


def test_api_reset_requires_explicit_confirm(client):
    client.post(
        "/api/leads/upsert",
        headers=auth_headers(),
        json={"source": "manual", "source_detail": "s1", "company": "Acme", "score": 10},
    )

    resp = client.post("/api/reset", headers=auth_headers(), json={"confirm": False})
    assert resp.status_code == 400
    assert client.get("/api/stats", headers=auth_headers()).json()["total"] == 1

    resp = client.post("/api/reset", headers=auth_headers(), json={"confirm": True})
    assert resp.status_code == 200
    assert resp.json()["removed"] == 1
    assert client.get("/api/stats", headers=auth_headers()).json()["total"] == 0


def test_api_dedupe(client):
    resp = client.post("/api/dedupe", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json() == []


def test_web_pages_redirect_to_login_without_cookie(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


def test_web_login_flow(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "token_input" in resp.text

    resp = client.post("/login", data={"token_input": "wrong", "next": "/"})
    assert resp.status_code == 401

    resp = client.post("/login", data={"token_input": TOKEN, "next": "/"}, follow_redirects=False)
    assert resp.status_code == 303
    assert "session_token" in resp.cookies

    client.cookies.set("session_token", TOKEN)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Abhay Leads" in resp.text

    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_web_lead_form_add_edit_delete(client):
    client.cookies.set("session_token", TOKEN)

    resp = client.post(
        "/leads/new",
        data={"company": "Web Co", "contact_name": "Priya", "stage": "New", "notes": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    lead_url = resp.headers["location"]

    resp = client.get(lead_url)
    assert resp.status_code == 200
    assert "Web Co" in resp.text

    lead_id = lead_url.rstrip("/").rsplit("/", 1)[-1]
    resp = client.post(
        f"/leads/{lead_id}",
        data={"company": "Web Co", "contact_name": "Priya", "stage": "Contacted", "notes": "called"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    resp = client.get(f"/leads/{lead_id}")
    assert "Contacted" in resp.text or "selected" in resp.text

    # Editing a lead that no longer exists should 404, not crash.
    resp = client.post(
        "/leads/999999",
        data={"company": "x", "contact_name": "", "stage": "New", "notes": ""},
    )
    assert resp.status_code == 404

    resp = client.post(f"/leads/{lead_id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    resp = client.get(f"/leads/{lead_id}")
    assert resp.status_code == 404


def test_web_fetch_and_tools_pages_render(client):
    client.cookies.set("session_token", TOKEN)
    assert client.get("/fetch").status_code == 200
    assert client.get("/tools").status_code == 200
    assert client.get("/leads/new").status_code == 200


def test_web_tools_reset_requires_typed_delete(client):
    client.cookies.set("session_token", TOKEN)
    client.post("/leads/new", data={"company": "Web Co", "contact_name": "", "stage": "New", "notes": ""})

    client.post("/tools/reset", data={"confirm": "nope"})
    assert "1 total" in client.get("/").text

    client.post("/tools/reset", data={"confirm": "DELETE"})
    assert "0 total" in client.get("/").text
