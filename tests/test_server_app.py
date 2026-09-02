"""Tests for the `abhayleads serve` FastAPI app (JSON API + web UI), using
FastAPI's in-process TestClient - no real network or subprocess involved."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from abhayleads.server.app import create_app

TOKEN = "test-token-123"
PUBLIC_TOKEN = "public-intake-token-456"


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        app = create_app(db_path, {"server": {"token": TOKEN}})
        yield TestClient(app)


@pytest.fixture
def public_intake_client():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        app = create_app(db_path, {"server": {"token": TOKEN, "public_intake_token": PUBLIC_TOKEN}})
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


def _embedded_points(html: str) -> list:
    import json as _json

    marker = "var points = "
    start = html.index(marker) + len(marker)
    end = html.index(";\n", start)
    return _json.loads(html[start:end])


def test_map_requires_login(client):
    resp = client.get("/map", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


def test_map_page_empty_state_when_no_leads_have_coordinates(client):
    client.cookies.set("session_token", TOKEN)
    client.post(
        "/api/leads/upsert",
        headers=auth_headers(),
        json={"source": "manual", "source_detail": "no-coords", "company": "No Map Co", "score": 10},
    )

    resp = client.get("/map")
    assert resp.status_code == 200
    assert "No leads with a map location yet" in resp.text
    assert "leads-map" not in resp.text  # the map div itself shouldn't render


def test_map_page_includes_only_leads_with_coordinates(client):
    client.cookies.set("session_token", TOKEN)
    client.post(
        "/api/leads/upsert",
        headers=auth_headers(),
        json={
            "source": "osm_places",
            "source_detail": "with-coords",
            "company": "Mapped Hospital",
            "lat": 18.55,
            "lon": 73.78,
            "score": 30,
        },
    )
    client.post(
        "/api/leads/upsert",
        headers=auth_headers(),
        json={"source": "manual", "source_detail": "no-coords", "company": "Unmapped Co", "score": 10},
    )

    resp = client.get("/map")
    assert resp.status_code == 200
    points = _embedded_points(resp.text)
    assert len(points) == 1
    assert points[0]["company"] == "Mapped Hospital"
    assert points[0]["lat"] == 18.55
    assert points[0]["lon"] == 73.78


def test_map_page_filters_by_stage(client):
    client.cookies.set("session_token", TOKEN)
    resp = client.post(
        "/api/leads/upsert",
        headers=auth_headers(),
        json={
            "source": "osm_places", "source_detail": "a", "company": "A",
            "lat": 1.0, "lon": 2.0, "score": 30,
        },
    )
    lead_id = resp.json()["id"]
    client.post(
        "/api/leads/upsert",
        headers=auth_headers(),
        json={
            "source": "osm_places", "source_detail": "b", "company": "B",
            "lat": 3.0, "lon": 4.0, "score": 30,
        },
    )
    client.patch(f"/api/leads/{lead_id}", headers=auth_headers(), json={"stage": "Contacted"})

    resp = client.get("/map", params={"stage": "Contacted"})
    points = _embedded_points(resp.text)
    assert len(points) == 1
    assert points[0]["company"] == "A"


def test_map_page_escapes_company_name_to_avoid_breaking_out_of_script_tag(client):
    client.cookies.set("session_token", TOKEN)
    client.post(
        "/api/leads/upsert",
        headers=auth_headers(),
        json={
            "source": "osm_places", "source_detail": "xss", "company": "</script><script>alert(1)</script>",
            "lat": 1.0, "lon": 2.0, "score": 30,
        },
    )

    resp = client.get("/map")
    assert "</script><script>alert(1)</script>" not in resp.text
    points = _embedded_points(resp.text)
    assert points[0]["company"] == "</script><script>alert(1)</script>"  # decodes back correctly


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


def test_public_intake_not_mounted_when_no_token_configured(client):
    resp = client.post("/public/intake/anything", json={"name": "Someone"})
    assert resp.status_code == 404


def test_public_intake_wrong_token_is_404(public_intake_client):
    resp = public_intake_client.post("/public/intake/wrong-token", json={"name": "Someone"})
    assert resp.status_code == 404


def test_public_intake_creates_a_lead(public_intake_client):
    resp = public_intake_client.post(
        f"/public/intake/{PUBLIC_TOKEN}",
        json={
            "name": "Jane Doe",
            "company": "Acme Society",
            "phone": "9999999999",
            "message": "Interested in pricing",
            "segment": "Housing society",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    resp = public_intake_client.get("/api/leads", headers=auth_headers())
    leads = resp.json()
    assert len(leads) == 1
    lead = leads[0]
    assert lead["source"] == "website_form"
    assert lead["company"] == "Acme Society"
    assert lead["contact_name"] == "Jane Doe"
    assert lead["phone"] == "9999999999"
    assert "Interested in pricing" in lead["raw_text"]
    assert "Housing society" in lead["raw_text"]


def test_public_intake_requires_name_or_company(public_intake_client):
    resp = public_intake_client.post(
        f"/public/intake/{PUBLIC_TOKEN}", json={"message": "hi", "phone": "123"}
    )
    assert resp.status_code == 400

    resp = public_intake_client.get("/api/leads", headers=auth_headers())
    assert resp.json() == []


def test_public_intake_honeypot_silently_no_ops(public_intake_client):
    resp = public_intake_client.post(
        f"/public/intake/{PUBLIC_TOKEN}",
        json={"name": "Bot", "company": "Spamco", "website": "http://filled-in-by-a-bot.example"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}  # looks like success to the bot...

    resp = public_intake_client.get("/api/leads", headers=auth_headers())
    assert resp.json() == []  # ...but nothing was actually saved


def test_public_intake_rate_limited_per_ip(public_intake_client):
    from abhayleads.server.app import PUBLIC_INTAKE_RATE_LIMIT

    for i in range(PUBLIC_INTAKE_RATE_LIMIT):
        resp = public_intake_client.post(
            f"/public/intake/{PUBLIC_TOKEN}", json={"name": f"Person {i}"}
        )
        assert resp.status_code == 200

    resp = public_intake_client.post(f"/public/intake/{PUBLIC_TOKEN}", json={"name": "One too many"})
    assert resp.status_code == 429


def test_public_intake_allows_cross_origin_requests(public_intake_client):
    resp = public_intake_client.options(
        f"/public/intake/{PUBLIC_TOKEN}",
        headers={
            "Origin": "https://some-other-website.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"
