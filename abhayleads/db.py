"""SQLite storage for leads, stage history and fetch-run summaries.

Kept as plain sqlite3 (no ORM) so the packaged .exe has one less
dependency to bundle and nothing that needs a native build step.
"""

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Optional

from .models import STAGES, Lead, LeadCandidate, utcnow_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key TEXT UNIQUE NOT NULL,
    company TEXT DEFAULT '',
    contact_name TEXT DEFAULT '',
    title TEXT DEFAULT '',
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    url TEXT DEFAULT '',
    source TEXT NOT NULL,
    source_detail TEXT DEFAULT '',
    keyword_matched TEXT DEFAULT '',
    raw_text TEXT DEFAULT '',
    score INTEGER DEFAULT 0,
    stage TEXT DEFAULT 'New',
    notes TEXT DEFAULT '',
    next_follow_up TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stage_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    changed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fetch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    sources_run TEXT NOT NULL,
    new_leads INTEGER DEFAULT 0,
    updated_leads INTEGER DEFAULT 0,
    errors TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS digest_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_digest_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score);
CREATE INDEX IF NOT EXISTS idx_leads_follow_up ON leads(next_follow_up);
"""


def make_dedup_key(candidate: LeadCandidate) -> str:
    basis = candidate.source_detail or candidate.url or f"{candidate.company}|{candidate.contact_name}"
    raw = f"{candidate.source}:{basis}".strip().lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    """JSON-friendly conversion, used by the server (`abhayleads serve`)
    to turn query results into API responses."""
    return dict(row) if row is not None else None


class Database:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        # WAL lets one connection write while another reads without either
        # blocking/erroring - needed now that a fetch (writing, on a
        # background thread) and the GUI's own periodic refresh (reading,
        # on the main thread) run against the same file at the same time.
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # -- fetch runs -----------------------------------------------------

    def start_fetch_run(self, sources_run: list[str]) -> int:
        cur = self.conn.execute(
            "INSERT INTO fetch_runs (started_at, sources_run) VALUES (?, ?)",
            (utcnow_iso(), json.dumps(sources_run)),
        )
        self.conn.commit()
        return cur.lastrowid

    def finish_fetch_run(self, run_id: int, new_leads: int, updated_leads: int, errors: list[str]):
        self.conn.execute(
            "UPDATE fetch_runs SET finished_at=?, new_leads=?, updated_leads=?, errors=? WHERE id=?",
            (utcnow_iso(), new_leads, updated_leads, json.dumps(errors), run_id),
        )
        self.conn.commit()

    def last_fetch_run(self) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM fetch_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()

    def recent_fetch_runs(self, limit: int = 10) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM fetch_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    # -- leads: ingest ----------------------------------------------------

    def upsert_candidate(self, candidate: LeadCandidate, score: int) -> tuple[int, bool]:
        """Insert a new lead, or refresh an existing one's last_seen_at/score.

        Returns (lead_id, is_new). Existing stage/notes are never overwritten -
        those are the user's CRM data.
        """
        dedup_key = make_dedup_key(candidate)
        now = utcnow_iso()
        existing = self.conn.execute(
            "SELECT id, score FROM leads WHERE dedup_key = ?", (dedup_key,)
        ).fetchone()

        if existing is None:
            cur = self.conn.execute(
                """INSERT INTO leads
                   (dedup_key, company, contact_name, title, email, phone, url,
                    source, source_detail, keyword_matched, raw_text, score,
                    stage, notes, next_follow_up, created_at, updated_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New', '', NULL, ?, ?, ?)""",
                (
                    dedup_key, candidate.company, candidate.contact_name, candidate.title,
                    candidate.email, candidate.phone, candidate.url, candidate.source,
                    candidate.source_detail, candidate.keyword_matched, candidate.raw_text,
                    score, now, now, now,
                ),
            )
            lead_id = cur.lastrowid
            self.conn.execute(
                "INSERT INTO stage_history (lead_id, stage, changed_at) VALUES (?, 'New', ?)",
                (lead_id, now),
            )
            self.conn.commit()
            return lead_id, True

        lead_id = existing["id"]
        new_score = max(existing["score"], score)
        self.conn.execute(
            "UPDATE leads SET last_seen_at=?, score=?, updated_at=? WHERE id=?",
            (now, new_score, now, lead_id),
        )
        self.conn.commit()
        return lead_id, False

    # -- leads: read ------------------------------------------------------

    def list_leads(
        self,
        stage: Optional[str] = None,
        source: Optional[str] = None,
        min_score: int = 0,
        due_only: bool = False,
        search: Optional[str] = None,
        order_by: str = "score DESC, updated_at DESC",
    ) -> list[sqlite3.Row]:
        query = "SELECT * FROM leads WHERE score >= ?"
        params: list = [min_score]
        if stage:
            query += " AND stage = ?"
            params.append(stage)
        if source:
            query += " AND source = ?"
            params.append(source)
        if due_only:
            query += " AND next_follow_up IS NOT NULL AND next_follow_up <= ?"
            params.append(utcnow_iso()[:10])
        if search:
            query += " AND (company LIKE ? OR contact_name LIKE ? OR title LIKE ? OR raw_text LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like, like])
        query += f" ORDER BY {order_by}"
        return self.conn.execute(query, params).fetchall()

    def get_lead(self, lead_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    def stage_history(self, lead_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM stage_history WHERE lead_id = ? ORDER BY changed_at", (lead_id,)
        ).fetchall()

    def stats(self) -> dict:
        by_stage = {
            row["stage"]: row["n"]
            for row in self.conn.execute(
                "SELECT stage, COUNT(*) as n FROM leads GROUP BY stage"
            ).fetchall()
        }
        by_source = {
            row["source"]: row["n"]
            for row in self.conn.execute(
                "SELECT source, COUNT(*) as n FROM leads GROUP BY source"
            ).fetchall()
        }
        due = self.conn.execute(
            "SELECT COUNT(*) as n FROM leads WHERE next_follow_up IS NOT NULL AND next_follow_up <= ?",
            (utcnow_iso()[:10],),
        ).fetchone()["n"]
        total = self.conn.execute("SELECT COUNT(*) as n FROM leads").fetchone()["n"]
        return {
            "total": total,
            "by_stage": {s: by_stage.get(s, 0) for s in STAGES},
            "by_source": by_source,
            "due_for_follow_up": due,
        }

    # -- digest (for the daily phone-notification summary) ------------------

    def get_last_digest_at(self) -> Optional[str]:
        row = self.conn.execute("SELECT last_digest_at FROM digest_state WHERE id = 1").fetchone()
        return row["last_digest_at"] if row else None

    def set_last_digest_at(self, when: str):
        self.conn.execute(
            "INSERT INTO digest_state (id, last_digest_at) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET last_digest_at = excluded.last_digest_at",
            (when,),
        )
        self.conn.commit()

    def summarize_since(self, since: Optional[str]) -> dict:
        """Counts of what changed since `since` (an ISO timestamp, or None
        for "everything") - the basis of the daily digest notification.

        Strictly-greater-than on purpose: `since` is normally the exact
        timestamp the previous digest stamped, and timestamps here only
        have second precision - a lead created in that same second must
        not be reported as new again on the next digest too.
        """
        if since is None:
            new_leads = self.conn.execute("SELECT COUNT(*) as n FROM leads").fetchone()["n"]
            updated_leads = 0  # nothing to call "updated since" on a first-ever digest
        else:
            new_leads = self.conn.execute(
                "SELECT COUNT(*) as n FROM leads WHERE created_at > ?", (since,)
            ).fetchone()["n"]
            updated_leads = self.conn.execute(
                "SELECT COUNT(*) as n FROM leads WHERE updated_at > ? AND created_at <= ?", (since, since)
            ).fetchone()["n"]
        due = self.conn.execute(
            "SELECT COUNT(*) as n FROM leads WHERE next_follow_up IS NOT NULL AND next_follow_up <= ?",
            (utcnow_iso()[:10],),
        ).fetchone()["n"]
        return {"new_leads": new_leads, "updated_leads": updated_leads, "due_for_follow_up": due}

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
        lead = self.get_lead(lead_id)
        if lead is None:
            raise ValueError(f"No lead with id {lead_id}")

        fields, params = [], []
        now = utcnow_iso()

        if stage is not None and stage != lead["stage"]:
            if stage not in STAGES:
                raise ValueError(f"Unknown stage {stage!r}, must be one of {STAGES}")
            fields.append("stage = ?")
            params.append(stage)
            self.conn.execute(
                "INSERT INTO stage_history (lead_id, stage, changed_at) VALUES (?, ?, ?)",
                (lead_id, stage, now),
            )

        if notes is not None:
            fields.append("notes = ?")
            params.append(notes)

        if clear_follow_up:
            fields.append("next_follow_up = NULL")
        elif next_follow_up is not None:
            fields.append("next_follow_up = ?")
            params.append(next_follow_up)

        # Contact/identifying fields - these come in from the source (OSM,
        # Google News, ...) but are frequently incomplete (no phone/email),
        # so the CRM lets you fill them in by hand once you've actually
        # called/visited the place.
        editable_text_fields = {
            "company": company,
            "contact_name": contact_name,
            "title": title,
            "email": email,
            "phone": phone,
            "url": url,
        }
        for column, value in editable_text_fields.items():
            if value is not None:
                fields.append(f"{column} = ?")
                params.append(value)

        if not fields:
            return

        fields.append("updated_at = ?")
        params.append(now)
        params.append(lead_id)
        self.conn.execute(f"UPDATE leads SET {', '.join(fields)} WHERE id = ?", params)
        self.conn.commit()

    def delete_lead(self, lead_id: int):
        self.conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        self.conn.commit()

    def delete_all_leads(self) -> int:
        """Wipes every lead, its stage history, and fetch-run log - used to
        start over from scratch. Does not touch config.yaml. Returns how
        many leads were removed."""
        count = self.conn.execute("SELECT COUNT(*) as n FROM leads").fetchone()["n"]
        self.conn.execute("DELETE FROM stage_history")
        self.conn.execute("DELETE FROM leads")
        self.conn.execute("DELETE FROM fetch_runs")
        self.conn.commit()
        return count

    def merge_exact_duplicate_osm_leads(self) -> list[dict]:
        """Collapses osm_places leads that share an identical company name
        within the same locality - typically the same building mapped
        twice in OpenStreetMap - into a single lead.

        Deliberately exact-match only: "Prakrtii CHS G Block" and
        "...F Block" are different strings and stay as separate leads,
        since they're genuinely different named entities that may need
        separate outreach. Only a literal repeated name is a duplicate.

        If you've already worked one of the duplicates (changed its stage
        or added notes), that one is kept; otherwise the earliest-added
        one is kept. Returns one summary dict per group actually merged.
        """
        rows = self.conn.execute(
            "SELECT id, company, title, stage, notes, created_at FROM leads "
            "WHERE source = 'osm_places' ORDER BY id"
        ).fetchall()

        groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
        for row in rows:
            match = re.search(r"\(([^)]+)\)\s*$", row["title"] or "")
            locality = match.group(1) if match else ""
            key = (row["company"].strip().lower(), locality)
            groups.setdefault(key, []).append(row)

        def already_worked(row: sqlite3.Row) -> bool:
            return row["stage"] != "New" or bool((row["notes"] or "").strip())

        merged_summaries = []
        for (_, locality), group_rows in groups.items():
            if len(group_rows) < 2:
                continue

            worked_rows = [r for r in group_rows if already_worked(r)]
            primary = worked_rows[0] if worked_rows else group_rows[0]
            duplicates = [r for r in group_rows if r["id"] != primary["id"]]

            for dup in duplicates:
                self.conn.execute("DELETE FROM leads WHERE id = ?", (dup["id"],))

            merged_summaries.append(
                {
                    "company": group_rows[0]["company"],
                    "locality": locality,
                    "kept_id": primary["id"],
                    "removed_ids": [d["id"] for d in duplicates],
                }
            )

        self.conn.commit()
        return merged_summaries
