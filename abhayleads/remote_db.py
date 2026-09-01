"""HTTP client that implements the same method surface as db.Database.

The point: cli.py and the GUI construct either a local `Database(path)`
or a `RemoteDatabase(base_url, token)` and use it identically - nothing
else in the app needs to know or care which one it's talking to. See
docs/SERVER_SETUP.md for what's on the other end of this (`abhayleads
serve`, run on a server both your desktop app and your phone can reach).

Every method here does exactly what its `Database` counterpart does,
just over HTTPS instead of direct sqlite3 calls - list_leads still
returns dict-like rows (plain dicts, which support the same `row["x"]`
indexing the rest of the codebase already uses), update_lead still only
touches fields you pass, etc.
"""

from typing import Optional

import requests

from .models import LeadCandidate


class RemoteDatabaseError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class RemoteDatabase:
    def __init__(self, base_url: str, token: str, timeout: int = 30):
        if not base_url:
            raise ValueError("server.base_url is not configured - see docs/SERVER_SETUP.md")
        if not token:
            raise ValueError("server.token is not configured - see docs/SERVER_SETUP.md")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def _request(self, method: str, path: str, **kwargs):
        try:
            resp = self.session.request(method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise RemoteDatabaseError(f"Couldn't reach {self.base_url}: {exc}") from exc

        if resp.status_code == 401:
            raise RemoteDatabaseError(
                "Server rejected the access token - check server.token matches on both ends.",
                status_code=401,
            )
        if not resp.ok:
            detail = ""
            try:
                detail = resp.json().get("detail", "")
            except Exception:  # noqa: BLE001 - body wasn't JSON, just report the status
                pass
            raise RemoteDatabaseError(
                f"HTTP {resp.status_code} from {method} {path}" + (f": {detail}" if detail else ""),
                status_code=resp.status_code,
            )
        return resp.json() if resp.content else None

    def close(self):
        self.session.close()

    # -- leads: ingest ----------------------------------------------------

    def upsert_candidate(self, candidate: LeadCandidate, score: int) -> tuple[int, bool]:
        payload = {
            "source": candidate.source,
            "source_detail": candidate.source_detail,
            "company": candidate.company,
            "contact_name": candidate.contact_name,
            "title": candidate.title,
            "email": candidate.email,
            "phone": candidate.phone,
            "url": candidate.url,
            "keyword_matched": candidate.keyword_matched,
            "raw_text": candidate.raw_text,
            "score": score,
        }
        data = self._request("POST", "/api/leads/upsert", json=payload)
        return data["id"], data["is_new"]

    # -- leads: read --------------------------------------------------------

    def list_leads(
        self,
        stage: Optional[str] = None,
        source: Optional[str] = None,
        min_score: int = 0,
        due_only: bool = False,
        search: Optional[str] = None,
        order_by: str = "score DESC, updated_at DESC",  # kept for signature parity; server always uses this
    ) -> list[dict]:
        params: dict = {"min_score": min_score}
        if stage:
            params["stage"] = stage
        if source:
            params["source"] = source
        if due_only:
            params["due_only"] = "true"
        if search:
            params["search"] = search
        return self._request("GET", "/api/leads", params=params)

    def get_lead(self, lead_id: int) -> Optional[dict]:
        try:
            return self._request("GET", f"/api/leads/{lead_id}")
        except RemoteDatabaseError as exc:
            if exc.status_code == 404:
                return None
            raise

    def stage_history(self, lead_id: int) -> list[dict]:
        return self._request("GET", f"/api/leads/{lead_id}/history")

    def stats(self) -> dict:
        return self._request("GET", "/api/stats")

    # -- leads: update ------------------------------------------------------

    def update_lead(
        self,
        lead_id: int,
        stage: Optional[str] = None,
        notes: Optional[str] = None,
        next_follow_up: Optional[str] = None,
        clear_follow_up: bool = False,
        company: Optional[str] = None,
        contact_name: Optional[str] = None,
        title: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        url: Optional[str] = None,
    ):
        payload = {
            "stage": stage,
            "notes": notes,
            "next_follow_up": next_follow_up,
            "clear_follow_up": clear_follow_up,
            "company": company,
            "contact_name": contact_name,
            "title": title,
            "email": email,
            "phone": phone,
            "url": url,
        }
        self._request("PATCH", f"/api/leads/{lead_id}", json=payload)

    def delete_lead(self, lead_id: int):
        self._request("DELETE", f"/api/leads/{lead_id}")

    def delete_all_leads(self) -> int:
        data = self._request("POST", "/api/reset", json={"confirm": True})
        return data["removed"]

    def merge_exact_duplicate_osm_leads(self) -> list[dict]:
        return self._request("POST", "/api/dedupe")

    # -- fetch runs -----------------------------------------------------

    def start_fetch_run(self, sources_run: list[str]) -> int:
        data = self._request("POST", "/api/fetch_runs", json={"sources_run": sources_run})
        return data["run_id"]

    def finish_fetch_run(self, run_id: int, new_leads: int, updated_leads: int, errors: list[str]):
        self._request(
            "PATCH",
            f"/api/fetch_runs/{run_id}",
            json={"new_leads": new_leads, "updated_leads": updated_leads, "errors": errors},
        )

    def last_fetch_run(self) -> Optional[dict]:
        return self._request("GET", "/api/fetch_runs/last")

    # -- digest -----------------------------------------------------------

    def get_last_digest_at(self) -> Optional[str]:
        data = self._request("GET", "/api/digest/last")
        return data.get("last_digest_at")

    def set_last_digest_at(self, when: str):
        self._request("POST", "/api/digest/last", json={"last_digest_at": when})

    def summarize_since(self, since: Optional[str]) -> dict:
        params = {"since": since} if since else {}
        return self._request("GET", "/api/digest/summary", params=params)
