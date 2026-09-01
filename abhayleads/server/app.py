"""The `abhayleads serve` HTTP server: a JSON API (for the desktop app's
RemoteDatabase client) plus a small mobile-friendly HTML UI (for
browsing/editing leads from a phone browser), both backed by one local
Database file. See docs/SERVER_SETUP.md for deployment.

Auth is a single shared secret (server.token in config.yaml) - this is a
single-user personal tool, not a multi-tenant service, so there's no
user/password system, just one bearer token the API expects and one
cookie (holding that same token) the HTML pages expect. Constant-time
comparison (secrets.compare_digest) either way. This is only safe
because deployment is HTTPS-only (see docs/SERVER_SETUP.md) - the token
would be trivially sniffable over plain HTTP.
"""

import secrets
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..db import Database, row_to_dict
from ..models import STAGES, LeadCandidate
from .fetch_job import FetchJob

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


# -- request bodies ---------------------------------------------------------


class UpsertCandidateBody(BaseModel):
    source: str
    source_detail: str = ""
    company: str = ""
    contact_name: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    url: str = ""
    keyword_matched: str = ""
    raw_text: str = ""
    score: int = 0


class UpdateLeadBody(BaseModel):
    stage: Optional[str] = None
    notes: Optional[str] = None
    next_follow_up: Optional[str] = None
    clear_follow_up: bool = False
    company: Optional[str] = None
    contact_name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    url: Optional[str] = None


class ResetBody(BaseModel):
    confirm: bool = False


class FetchRunStartBody(BaseModel):
    sources_run: list[str] = []


class FetchRunFinishBody(BaseModel):
    new_leads: int = 0
    updated_leads: int = 0
    errors: list[str] = []


class DigestLastBody(BaseModel):
    last_digest_at: str


class FetchStartBody(BaseModel):
    source: Optional[str] = None


def create_app(db_path: Path, config: dict[str, Any]) -> FastAPI:
    token = (config.get("server", {}) or {}).get("token", "")
    if not token:
        raise RuntimeError(
            "server.token is not set in config.yaml - run `abhayleads server-token` "
            "to generate one, add it under `server:`, then try again. See docs/SERVER_SETUP.md."
        )

    app = FastAPI(title="Abhay Leads Server")
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    fetch_job = FetchJob()

    def get_db():
        # A generator dependency, not a plain return - FastAPI runs the
        # code after `yield` once the response is built, even if the
        # route raised, so the connection always gets closed instead of
        # leaking on every request that errors partway through.
        db = Database(db_path)
        try:
            yield db
        finally:
            db.close()

    def check_api_token(authorization: str = Header(default="")) -> None:
        expected = f"Bearer {token}"
        if not authorization or not secrets.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    def web_auth_redirect(request: Request) -> Optional[RedirectResponse]:
        """Call at the top of every HTML route. Returns a redirect to
        /login if not authenticated, otherwise None -
        `if r := web_auth_redirect(request): return r`.
        """
        cookie = request.cookies.get("session_token", "")
        if not cookie or not secrets.compare_digest(cookie, token):
            return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)
        return None

    # -- health (no auth - for uptime checks) --------------------------------

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # -- JSON API (bearer token) --------------------------------------------
    # Every route below gets check_api_token applied automatically via
    # this sub-app's `dependencies=` - simpler than repeating
    # Depends(check_api_token) on all twenty of them, and FastAPI already
    # turns a raised HTTPException into a proper JSON error response.

    api = FastAPI(dependencies=[Depends(check_api_token)])

    @api.post("/leads/upsert")
    def api_upsert_lead(body: UpsertCandidateBody, db: Database = Depends(get_db)):
        candidate = LeadCandidate(
            source=body.source,
            source_detail=body.source_detail,
            company=body.company,
            contact_name=body.contact_name,
            title=body.title,
            email=body.email,
            phone=body.phone,
            url=body.url,
            keyword_matched=body.keyword_matched,
            raw_text=body.raw_text,
        )
        lead_id, is_new = db.upsert_candidate(candidate, body.score)
        return {"id": lead_id, "is_new": is_new}

    @api.get("/leads")
    def api_list_leads(
        stage: Optional[str] = None,
        source: Optional[str] = None,
        min_score: int = 0,
        due_only: bool = False,
        search: Optional[str] = None,
        db: Database = Depends(get_db),
    ):
        leads = db.list_leads(stage=stage, source=source, min_score=min_score, due_only=due_only, search=search)
        return [row_to_dict(lead) for lead in leads]

    @api.get("/leads/{lead_id}")
    def api_get_lead(lead_id: int, db: Database = Depends(get_db)):
        lead = db.get_lead(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="No such lead")
        return row_to_dict(lead)

    @api.get("/leads/{lead_id}/history")
    def api_lead_history(lead_id: int, db: Database = Depends(get_db)):
        return [row_to_dict(row) for row in db.stage_history(lead_id)]

    @api.patch("/leads/{lead_id}")
    def api_update_lead(lead_id: int, body: UpdateLeadBody, db: Database = Depends(get_db)):
        try:
            db.update_lead(
                lead_id,
                stage=body.stage,
                notes=body.notes,
                next_follow_up=body.next_follow_up,
                clear_follow_up=body.clear_follow_up,
                company=body.company,
                contact_name=body.contact_name,
                title=body.title,
                email=body.email,
                phone=body.phone,
                url=body.url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @api.delete("/leads/{lead_id}")
    def api_delete_lead(lead_id: int, db: Database = Depends(get_db)):
        db.delete_lead(lead_id)
        return {"ok": True}

    @api.post("/reset")
    def api_reset(body: ResetBody, db: Database = Depends(get_db)):
        if not body.confirm:
            raise HTTPException(status_code=400, detail="Pass confirm=true to delete all leads")
        return {"removed": db.delete_all_leads()}

    @api.post("/dedupe")
    def api_dedupe(db: Database = Depends(get_db)):
        return db.merge_exact_duplicate_osm_leads()

    @api.get("/stats")
    def api_stats(db: Database = Depends(get_db)):
        return db.stats()

    @api.post("/fetch_runs")
    def api_start_fetch_run(body: FetchRunStartBody, db: Database = Depends(get_db)):
        return {"run_id": db.start_fetch_run(body.sources_run)}

    @api.patch("/fetch_runs/{run_id}")
    def api_finish_fetch_run(run_id: int, body: FetchRunFinishBody, db: Database = Depends(get_db)):
        db.finish_fetch_run(run_id, body.new_leads, body.updated_leads, body.errors)
        return {"ok": True}

    @api.get("/fetch_runs/last")
    def api_last_fetch_run(db: Database = Depends(get_db)):
        return row_to_dict(db.last_fetch_run())

    @api.get("/digest/last")
    def api_digest_last(db: Database = Depends(get_db)):
        return {"last_digest_at": db.get_last_digest_at()}

    @api.post("/digest/last")
    def api_digest_set_last(body: DigestLastBody, db: Database = Depends(get_db)):
        db.set_last_digest_at(body.last_digest_at)
        return {"ok": True}

    @api.get("/digest/summary")
    def api_digest_summary(since: Optional[str] = None, db: Database = Depends(get_db)):
        return db.summarize_since(since)

    @api.post("/fetch/start")
    def api_fetch_start(body: FetchStartBody):
        try:
            fetch_job.start(db_path, config, only_source=body.source)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True}

    @api.get("/fetch/status")
    def api_fetch_status():
        return fetch_job.status()

    @api.post("/fetch/stop")
    def api_fetch_stop():
        fetch_job.stop()
        return {"ok": True}

    app.mount("/api", api, name="api")

    # -- HTML UI (cookie session) --------------------------------------------

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, next: str = "/"):
        return templates.TemplateResponse(request, "login.html", {"next": next, "error": None})

    @app.post("/login")
    def login_submit(request: Request, token_input: str = Form(...), next: str = Form("/")):
        if not secrets.compare_digest(token_input, token):
            return templates.TemplateResponse(
                request, "login.html", {"next": next, "error": "Wrong token."}, status_code=401
            )
        response = RedirectResponse(url=next or "/", status_code=303)
        response.set_cookie(
            "session_token", token, httponly=True, secure=True, samesite="lax", max_age=60 * 60 * 24 * 90
        )
        return response

    @app.post("/logout")
    def logout():
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("session_token")
        return response

    @app.get("/", response_class=HTMLResponse)
    def leads_list(
        request: Request,
        stage: str = "",
        min_score: int = 0,
        due_only: bool = False,
        search: str = "",
        db: Database = Depends(get_db),
    ):
        if redirect := web_auth_redirect(request):
            return redirect
        leads = db.list_leads(stage=stage or None, min_score=min_score, due_only=due_only, search=search or None)
        return templates.TemplateResponse(
            request,
            "leads_list.html",
            {
                "leads": [row_to_dict(lead) for lead in leads],
                "stats": db.stats(),
                "stages": STAGES,
                "filters": {"stage": stage, "min_score": min_score, "due_only": due_only, "search": search},
            },
        )

    @app.get("/leads/new", response_class=HTMLResponse)
    def lead_new_form(request: Request):
        if redirect := web_auth_redirect(request):
            return redirect
        return templates.TemplateResponse(request, "lead_form.html", {"lead": None, "stages": STAGES})

    @app.post("/leads/new")
    def lead_new_submit(
        request: Request,
        company: str = Form(""),
        contact_name: str = Form(""),
        title: str = Form(""),
        email: str = Form(""),
        phone: str = Form(""),
        url: str = Form(""),
        stage: str = Form("New"),
        notes: str = Form(""),
        next_follow_up: str = Form(""),
        db: Database = Depends(get_db),
    ):
        if redirect := web_auth_redirect(request):
            return redirect
        candidate = LeadCandidate(
            source="manual",
            source_detail=f"manual-{uuid.uuid4().hex}",
            company=company.strip(),
            contact_name=contact_name.strip(),
            title=title.strip(),
            email=email.strip(),
            phone=phone.strip(),
            url=url.strip(),
            raw_text="Added by hand.",
        )
        lead_id, _ = db.upsert_candidate(candidate, score=0)
        db.update_lead(
            lead_id,
            stage=stage,
            notes=notes,
            next_follow_up=next_follow_up or None,
            clear_follow_up=not next_follow_up,
        )
        return RedirectResponse(url=f"/leads/{lead_id}", status_code=303)

    @app.get("/leads/{lead_id}", response_class=HTMLResponse)
    def lead_detail(request: Request, lead_id: int, saved: bool = False, db: Database = Depends(get_db)):
        if redirect := web_auth_redirect(request):
            return redirect
        lead = db.get_lead(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="No such lead")
        history = db.stage_history(lead_id)
        return templates.TemplateResponse(
            request,
            "lead_form.html",
            {
                "lead": row_to_dict(lead),
                "stages": STAGES,
                "history": [row_to_dict(row) for row in history],
                "saved": saved,
            },
        )

    @app.post("/leads/{lead_id}")
    def lead_detail_submit(
        request: Request,
        lead_id: int,
        company: str = Form(""),
        contact_name: str = Form(""),
        title: str = Form(""),
        email: str = Form(""),
        phone: str = Form(""),
        url: str = Form(""),
        stage: str = Form("New"),
        notes: str = Form(""),
        next_follow_up: str = Form(""),
        db: Database = Depends(get_db),
    ):
        if redirect := web_auth_redirect(request):
            return redirect
        if db.get_lead(lead_id) is None:
            raise HTTPException(status_code=404, detail="No such lead")
        db.update_lead(
            lead_id,
            stage=stage,
            notes=notes,
            company=company.strip(),
            contact_name=contact_name.strip(),
            title=title.strip(),
            email=email.strip(),
            phone=phone.strip(),
            url=url.strip(),
            next_follow_up=next_follow_up or None,
            clear_follow_up=not next_follow_up,
        )
        return RedirectResponse(url=f"/leads/{lead_id}?saved=1", status_code=303)

    @app.post("/leads/{lead_id}/delete")
    def lead_delete(request: Request, lead_id: int, db: Database = Depends(get_db)):
        if redirect := web_auth_redirect(request):
            return redirect
        db.delete_lead(lead_id)
        return RedirectResponse(url="/", status_code=303)

    @app.get("/fetch", response_class=HTMLResponse)
    def fetch_page(request: Request):
        if redirect := web_auth_redirect(request):
            return redirect
        return templates.TemplateResponse(request, "fetch.html", {"status": fetch_job.status()})

    @app.post("/fetch/start")
    def fetch_start_web(request: Request, source: str = Form("")):
        if redirect := web_auth_redirect(request):
            return redirect
        try:
            fetch_job.start(db_path, config, only_source=source or None)
        except RuntimeError:
            pass  # already running - the status page will just show that
        return RedirectResponse(url="/fetch", status_code=303)

    @app.post("/fetch/stop")
    def fetch_stop_web(request: Request):
        if redirect := web_auth_redirect(request):
            return redirect
        fetch_job.stop()
        return RedirectResponse(url="/fetch", status_code=303)

    @app.get("/tools", response_class=HTMLResponse)
    def tools_page(request: Request):
        if redirect := web_auth_redirect(request):
            return redirect
        return templates.TemplateResponse(request, "tools.html", {})

    @app.post("/tools/dedupe")
    def tools_dedupe(request: Request, db: Database = Depends(get_db)):
        if redirect := web_auth_redirect(request):
            return redirect
        db.merge_exact_duplicate_osm_leads()
        return RedirectResponse(url="/tools", status_code=303)

    @app.post("/tools/reset")
    def tools_reset(request: Request, confirm: str = Form(""), db: Database = Depends(get_db)):
        if redirect := web_auth_redirect(request):
            return redirect
        if confirm == "DELETE":
            db.delete_all_leads()
        return RedirectResponse(url="/tools", status_code=303)

    return app
